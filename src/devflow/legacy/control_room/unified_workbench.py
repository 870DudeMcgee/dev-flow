from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel, Field

from devflow.legacy.control_room.architecture_evidence import (
    ArchitectureEvidenceProjection,
    build_architecture_evidence,
)
from devflow.legacy.control_room.brainstorm_pipeline import load_brainstorm_session_snapshot
from devflow.legacy.control_room.browser_action_policy import ACTION_APPROVAL_PHRASE
from devflow.legacy.control_room.builder_judge_loop import (
    DEFAULT_BUILDER_PROFILE,
    DEFAULT_JUDGE_PROFILE,
    DEFAULT_PASS_THRESHOLD,
    BuilderJudgeConfig,
    BuilderJudgeRun,
    builder_judge_run_path,
    list_builder_judge_loops,
    run_builder_judge_loop,
)
from devflow.legacy.control_room.paths import relative_path
from devflow.legacy.control_room.persistence import atomic_write_text
from devflow.legacy.control_room.project_create import create_project
from devflow.legacy.control_room.project_registry import load_project_metadata
from devflow.legacy.control_room.stage_artifact import write_stage_artifact


WORKBENCH_STAGE_ORDER = ("idea", "brainstorm", "spec", "plan", "implement")
GRAPHIFY_SOURCE = "safishamsi/graphify"
GRAPHIFY_PACKAGE = "graphifyy"
GRAPHIFY_CLI = "graphify"
PONYTAIL_SOURCE = "DietrichGebert/ponytail"
PONYTAIL_GATE_PATH = Path(".devflow/gates/ponytail.json")
PONYTAIL_LADDER = (
    "Apply the Ponytail simplification ladder in order: "
    "skip unnecessary work; delete what should not exist; reuse existing code; "
    "prefer the standard library, native platform behavior, or already-approved dependencies; "
    "then write only the minimum new code that works."
)
GRAPHIFY_SETUP_COMMAND = "devflow architecture audit --install-graphify --write-doc"


class WorkbenchError(ValueError):
    pass


class WorkbenchSetupAction(BaseModel):
    gate: str
    label: str
    kind: str
    requires_human_approval: bool = True
    source: str
    command: str | None = None
    endpoint: str = "/api/gates/setup"
    detail: str


class WorkbenchGateItem(BaseModel):
    id: str
    label: str
    status: str
    ready: bool
    detail: str
    source: str
    evidence_paths: list[str] = Field(default_factory=list)
    setup_action: WorkbenchSetupAction | None = None


class WorkbenchGateStatus(BaseModel):
    status: str
    ready: bool
    items: list[WorkbenchGateItem] = Field(default_factory=list)
    next_action: str


class WorkbenchState(BaseModel):
    schema_version: int = 1
    session_id: str | None = None
    project_id: str | None = None
    stage: str = "idea"
    stages: list[str] = Field(default_factory=lambda: list(WORKBENCH_STAGE_ORDER))
    artifact_paths: dict[str, str | None] = Field(default_factory=dict)
    gate_status: WorkbenchGateStatus
    active_loop_ids: list[str] = Field(default_factory=list)
    next_action: str


class WorkbenchImplementationPackage(BaseModel):
    definition_of_done: dict[str, Any]
    starting_point: dict[str, Any]
    definition_of_done_markdown: str
    starting_point_markdown: str


class WorkbenchImplementationResult(BaseModel):
    schema_version: int = 1
    status: str
    session_id: str
    loop_id: str | None = None
    implementation_path: str | None = None
    builder_judge_path: str | None = None
    final_score: int | None = None
    package: WorkbenchImplementationPackage
    gate_status: WorkbenchGateStatus
    next_action: str
    refactor_offer_path: str | None = None


def build_workbench_state(
    root: Path,
    *,
    project_id: str | None = None,
    first_viewport: Any | None = None,
) -> WorkbenchState:
    root = root.resolve()
    session_id = _first_viewport_session_id(first_viewport) or _latest_brainstorm_session_id(root)
    stage = _workbench_stage(root, session_id=session_id, first_viewport=first_viewport)
    artifacts = _artifact_paths(root, session_id)
    gate_status = build_gate_status(root)
    active_loop_ids = _active_workbench_loop_ids(root)
    return WorkbenchState(
        session_id=session_id,
        project_id=project_id,
        stage=stage,
        artifact_paths=artifacts,
        gate_status=gate_status,
        active_loop_ids=active_loop_ids,
        next_action=_state_next_action(stage, gate_status),
    )


def build_gate_status(root: Path) -> WorkbenchGateStatus:
    root = root.resolve()
    graphify = _graphify_gate(root)
    ponytail = _ponytail_gate(root)
    items = [graphify, ponytail]
    ready = all(item.ready for item in items)
    blocked = [item.label for item in items if not item.ready]
    return WorkbenchGateStatus(
        status="ready" if ready else "blocked",
        ready=ready,
        items=items,
        next_action=(
            "Implement is unlocked. Send the package to builder-judge."
            if ready
            else f"Repair gate evidence first: {', '.join(blocked)}."
        ),
    )


def setup_gate(root: Path, payload: dict[str, object]) -> dict[str, Any]:
    gate = str(payload.get("gate") or "").strip().lower()
    if gate not in {"graphify", "ponytail"}:
        raise WorkbenchError("gate must be one of: graphify, ponytail")

    if gate == "graphify":
        action = _graphify_setup_action()
        return {
            "status": "action_required",
            "gate": gate,
            "setup_action": action.model_dump(mode="json"),
            "message": "Run the approved command to refresh Graphify evidence before Implement.",
        }

    if payload.get("human_approved") is not True:
        raise WorkbenchError("Ponytail setup requires explicit human approval")
    if payload.get("approval_phrase") != ACTION_APPROVAL_PHRASE:
        raise WorkbenchError("Ponytail setup approval phrase did not match")
    if payload.get("approved_source") != PONYTAIL_SOURCE:
        raise WorkbenchError(f"Ponytail setup must approve source {PONYTAIL_SOURCE}")
    if payload.get("reviewed_lifecycle_hooks") is not True:
        raise WorkbenchError("Ponytail setup requires reviewed_lifecycle_hooks=true")

    record = {
        "schema_version": 1,
        "status": "approved",
        "source": PONYTAIL_SOURCE,
        "setup_path": "Codex marketplace/plugin plus reviewed/trusted lifecycle hooks",
        "reviewed_lifecycle_hooks": True,
        "approved_at": datetime.now(timezone.utc).isoformat(),
        "rules": _ponytail_rules(),
    }
    target = root.resolve() / PONYTAIL_GATE_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(target, json.dumps(record, indent=2, sort_keys=True) + "\n")
    return {
        "status": "recorded",
        "gate": gate,
        "path": PONYTAIL_GATE_PATH.as_posix(),
        "message": "Ponytail gate approval recorded for this local project.",
    }


def create_workbench_project(payload: dict[str, object]) -> dict[str, Any]:
    name = str(payload.get("name") or "").strip()
    if not name:
        raise WorkbenchError("name is required")
    private_context = bool(payload.get("private_context", False))
    result = create_project(name, private_context=private_context)
    return {
        "status": "created",
        "project": result.model_dump(mode="json"),
        "next_action": f"Open project {result.project_id}, then start the Idea stage.",
    }


def prepare_implementation_package(
    root: Path,
    *,
    session_id: str,
    title: str | None = None,
    definition_of_done: str | None = None,
) -> WorkbenchImplementationPackage:
    root = root.resolve()
    snapshot = load_brainstorm_session_snapshot(root, session_id=session_id)
    if not snapshot.messages:
        raise WorkbenchError(f"brainstorm session has no transcript: {session_id}")
    if not snapshot.spec:
        raise WorkbenchError("Spec artifact is required before Implement.")
    if not snapshot.plan:
        raise WorkbenchError("Plan artifact is required before Implement.")

    gate_status = build_gate_status(root)
    if not gate_status.ready:
        raise WorkbenchError(gate_status.next_action)

    graphify = build_architecture_evidence(root)
    project_context = _project_context(root)
    evidence_paths = _implementation_evidence_paths(root, session_id, graphify)
    resolved_title = (title or _title_from_session(snapshot.messages) or "Workbench implementation").strip()
    human_dod = str(definition_of_done or "").strip()

    definition_payload = {
        "title": resolved_title,
        "spec_criteria": _markdown_bullets(snapshot.spec),
        "plan_requirements": _markdown_bullets(snapshot.plan),
        "project_constraints": [
            "Stay local-first; do not push, publish, open PRs, or mutate remote state.",
            "Implement must produce an implementation.md artifact first; code-changing task creation remains a later explicit bridge.",
            "Preserve task evidence, worker identity, model identity, verification paths, and next safe action.",
        ],
        "graphify_requirements": [
            "Use Graphify evidence from safishamsi/graphify only.",
            "Package graphifyy must provide the graphify CLI.",
            "Treat stale or missing graph evidence as blocking.",
        ],
        "ponytail_simplification_rules": _ponytail_rules(),
        "human_definition_of_done": human_dod,
    }
    starting_payload = {
        "transcript": _transcript_text(snapshot.messages),
        "spec": snapshot.spec,
        "plan": snapshot.plan,
        "project_context": project_context,
        "graphify_summary": graphify.summary,
        "ponytail_checklist": _ponytail_rules(),
        "evidence_paths": evidence_paths,
    }
    dod_markdown = _render_definition_of_done(definition_payload)
    starting_markdown = _render_starting_point(starting_payload)
    return WorkbenchImplementationPackage(
        definition_of_done=definition_payload,
        starting_point=starting_payload,
        definition_of_done_markdown=dod_markdown,
        starting_point_markdown=starting_markdown,
    )


def run_workbench_implementation(
    root: Path,
    *,
    session_id: str,
    title: str | None = None,
    definition_of_done: str | None = None,
    builder_profile_id: str = DEFAULT_BUILDER_PROFILE,
    judge_profile_id: str = DEFAULT_JUDGE_PROFILE,
    pass_threshold: int = DEFAULT_PASS_THRESHOLD,
    max_rounds: int = 3,
    loop_id: str | None = None,
    run_loop: Callable[[Path, BuilderJudgeConfig], BuilderJudgeRun] | None = None,
) -> WorkbenchImplementationResult:
    root = root.resolve()
    package = prepare_implementation_package(
        root,
        session_id=session_id,
        title=title,
        definition_of_done=definition_of_done,
    )
    gate_status = build_gate_status(root)
    config = BuilderJudgeConfig(
        definition_of_done=package.definition_of_done_markdown,
        starting_point=package.starting_point_markdown,
        builder_profile_id=builder_profile_id,
        judge_profile_id=judge_profile_id,
        pass_threshold=pass_threshold,
        max_rounds=max_rounds,
        escalate_on_max_rounds=True,
    )
    actual_loop_id = loop_id or _new_workbench_loop_id()
    runner = run_loop or (lambda repo_root, cfg: run_builder_judge_loop(repo_root, cfg, loop_id=actual_loop_id))
    run = runner(root, config)
    implementation_path = None
    refactor_offer_path = None
    if run.status == "passed" and run.final_draft:
        implementation_path = write_accepted_implementation(root, session_id=session_id, run=run)
        next_action = "implementation.md accepted. Create a Dev-Flow task from the brainstorm bridge."
    else:
        refactor_offer_path = _write_refactor_offer(root, session_id=session_id, run=run, package=package)
        next_action = "Builder-judge did not pass. Send to Refactor Loop with Graphify and Ponytail evidence attached."

    return WorkbenchImplementationResult(
        status=run.status,
        session_id=session_id,
        loop_id=run.loop_id,
        implementation_path=implementation_path,
        builder_judge_path=run.evidence_path,
        final_score=run.final_score,
        package=package,
        gate_status=gate_status,
        next_action=next_action,
        refactor_offer_path=refactor_offer_path,
    )


def write_accepted_implementation(root: Path, *, session_id: str, run: BuilderJudgeRun) -> str:
    if not run.final_draft:
        raise WorkbenchError("builder-judge run has no final draft")
    root = root.resolve()
    session_dir = root / ".devflow" / "brainstorms" / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    implementation_path = session_dir / "implementation.md"
    atomic_write_text(implementation_path, run.final_draft.rstrip() + "\n")
    quality_gate_path = root / run.evidence_path if run.evidence_path else builder_judge_run_path(root, run.loop_id)
    write_stage_artifact(
        root,
        session_id,
        "implementation",
        "builder_judge",
        "passed",
        implementation_path,
        quality_gate_path=quality_gate_path,
        score=run.final_score,
        next_action="Create a Dev-Flow task from the accepted implementation artifact.",
    )
    return relative_path(root, implementation_path)


def finalize_workbench_run(
    root: Path,
    *,
    session_id: str,
    run: BuilderJudgeRun,
    package: WorkbenchImplementationPackage,
) -> dict[str, Any]:
    if run.status == "passed" and run.final_draft:
        implementation_path = write_accepted_implementation(root, session_id=session_id, run=run)
        return {
            "implementation_path": implementation_path,
            "refactor_offer_path": None,
            "next_action": "implementation.md accepted. Create a Dev-Flow task from the brainstorm bridge.",
        }
    refactor_offer_path = _write_refactor_offer(root, session_id=session_id, run=run, package=package)
    return {
        "implementation_path": None,
        "refactor_offer_path": refactor_offer_path,
        "next_action": "Builder-judge did not pass. Send to Refactor Loop with Graphify and Ponytail evidence attached.",
    }


def workbench_running_payload(
    root: Path,
    *,
    session_id: str,
    loop_id: str,
    package: WorkbenchImplementationPackage,
    config: BuilderJudgeConfig,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "running",
        "session_id": session_id,
        "loop_id": loop_id,
        "config": config.model_dump(mode="json"),
        "package": package.model_dump(mode="json"),
        "gate_status": build_gate_status(root).model_dump(mode="json"),
        "started_at": datetime.now(timezone.utc).isoformat(),
        "next_action": "Builder-judge is generating implementation.md evidence.",
    }


def implementation_config_from_package(
    package: WorkbenchImplementationPackage,
    *,
    builder_profile_id: str,
    judge_profile_id: str,
    pass_threshold: int,
    max_rounds: int,
) -> BuilderJudgeConfig:
    return BuilderJudgeConfig(
        definition_of_done=package.definition_of_done_markdown,
        starting_point=package.starting_point_markdown,
        builder_profile_id=builder_profile_id,
        judge_profile_id=judge_profile_id,
        pass_threshold=pass_threshold,
        max_rounds=max_rounds,
        escalate_on_max_rounds=True,
    )


def _graphify_gate(root: Path) -> WorkbenchGateItem:
    evidence = build_architecture_evidence(root)
    paths = [artifact.path for artifact in evidence.artifacts]
    callflow_paths = [artifact.path for artifact in evidence.artifacts if "callflow" in artifact.path.lower()]
    missing: list[str] = []
    if not (root / "graphify-out" / "GRAPH_REPORT.md").exists():
        missing.append("GRAPH_REPORT.md")
    if not (root / "graphify-out" / "graph.json").exists():
        missing.append("graph.json")
    if not callflow_paths:
        missing.append("callflow HTML")
    freshness = evidence.freshness.status
    if freshness != "fresh":
        missing.append(f"freshness={freshness}")
    ready = not missing
    detail = (
        "Fresh Graphify evidence is present."
        if ready
        else "Missing or stale Graphify evidence: " + ", ".join(missing)
    )
    return WorkbenchGateItem(
        id="graphify",
        label="Graphify",
        status="ready" if ready else "blocked",
        ready=ready,
        detail=detail,
        source=GRAPHIFY_SOURCE,
        evidence_paths=paths,
        setup_action=None if ready else _graphify_setup_action(),
    )


def _ponytail_gate(root: Path) -> WorkbenchGateItem:
    path = root / PONYTAIL_GATE_PATH
    ready = False
    detail = "Ponytail plugin approval has not been recorded."
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            ready = (
                isinstance(payload, dict)
                and payload.get("status") == "approved"
                and payload.get("source") == PONYTAIL_SOURCE
                and payload.get("reviewed_lifecycle_hooks") is True
            )
            detail = (
                "Ponytail lifecycle hooks reviewed and simplification ladder approved."
                if ready
                else "Ponytail approval marker is incomplete."
            )
        except (OSError, json.JSONDecodeError):
            detail = "Ponytail approval marker is unreadable."
    return WorkbenchGateItem(
        id="ponytail",
        label="Ponytail",
        status="ready" if ready else "blocked",
        ready=ready,
        detail=detail,
        source=PONYTAIL_SOURCE,
        evidence_paths=[PONYTAIL_GATE_PATH.as_posix()] if path.exists() else [],
        setup_action=None if ready else _ponytail_setup_action(),
    )


def _graphify_setup_action() -> WorkbenchSetupAction:
    return WorkbenchSetupAction(
        gate="graphify",
        label="Repair Graphify evidence",
        kind="terminal_command",
        source=GRAPHIFY_SOURCE,
        command=GRAPHIFY_SETUP_COMMAND,
        detail=f"Installs {GRAPHIFY_PACKAGE} when needed, then runs the {GRAPHIFY_CLI} audit/export path.",
    )


def _ponytail_setup_action() -> WorkbenchSetupAction:
    return WorkbenchSetupAction(
        gate="ponytail",
        label="Record Ponytail approval",
        kind="codex_plugin_approval",
        source=PONYTAIL_SOURCE,
        detail="Install the Codex Ponytail plugin, review/trust lifecycle hooks, then record approval.",
    )


def _first_viewport_session_id(first_viewport: Any | None) -> str | None:
    if first_viewport is None:
        return None
    pipeline = getattr(first_viewport, "pipeline", None)
    value = getattr(pipeline, "session_id", None) if pipeline is not None else None
    return str(value).strip() or None


def _latest_brainstorm_session_id(root: Path) -> str | None:
    sessions_dir = root / ".devflow" / "brainstorms"
    if not sessions_dir.exists():
        return None
    sessions = [path for path in sessions_dir.iterdir() if path.is_dir() and (path / "transcript.jsonl").exists()]
    if not sessions:
        return None
    return max(sessions, key=lambda path: path.stat().st_mtime).name


def _workbench_stage(root: Path, *, session_id: str | None, first_viewport: Any | None) -> str:
    if not session_id:
        return "idea"
    pipeline = getattr(first_viewport, "pipeline", None) if first_viewport is not None else None
    primary = str(getattr(pipeline, "primary_stage_id", "") or "").strip()
    if primary == "implementation":
        return "implement"
    if primary in {"spec", "plan"}:
        return primary
    session_dir = root / ".devflow" / "brainstorms" / session_id
    if not (session_dir / "spec.md").exists():
        return "brainstorm"
    if not (session_dir / "plan.md").exists():
        return "plan"
    return "implement"


def _artifact_paths(root: Path, session_id: str | None) -> dict[str, str | None]:
    result: dict[str, str | None] = {stage: None for stage in WORKBENCH_STAGE_ORDER}
    if not session_id:
        return result
    session_dir = root / ".devflow" / "brainstorms" / session_id
    mapping = {
        "brainstorm": session_dir / "transcript.jsonl",
        "spec": session_dir / "spec.md",
        "plan": session_dir / "plan.md",
        "implement": session_dir / "implementation.md",
    }
    for stage, path in mapping.items():
        if path.exists():
            result[stage] = relative_path(root, path)
    return result


def _active_workbench_loop_ids(root: Path) -> list[str]:
    try:
        loops = list_builder_judge_loops(root)
    except (OSError, ValueError):
        return []
    return [
        str(loop.get("loop_id"))
        for loop in loops[:6]
        if str(loop.get("loop_id") or "").startswith("workbench-implement-")
        and loop.get("status") in {"running", "escalated", "max_rounds"}
    ]


def _state_next_action(stage: str, gates: WorkbenchGateStatus) -> str:
    if stage == "idea":
        return "Capture or select an idea."
    if stage == "brainstorm":
        return "Use the Brainstorm chat until the idea is clear, then generate Spec."
    if stage == "spec":
        return "Review the Spec artifact, then generate Plan."
    if stage == "plan":
        return "Review the Plan artifact, then prepare Implement."
    if not gates.ready:
        return gates.next_action
    return "Implement is ready for builder-judge."


def _implementation_evidence_paths(root: Path, session_id: str, graphify: ArchitectureEvidenceProjection) -> list[str]:
    paths = []
    for value in _artifact_paths(root, session_id).values():
        if value:
            paths.append(value)
    paths.extend(artifact.path for artifact in graphify.artifacts)
    ponytail = root / PONYTAIL_GATE_PATH
    if ponytail.exists():
        paths.append(PONYTAIL_GATE_PATH.as_posix())
    return _dedupe(paths)


def _project_context(root: Path) -> dict[str, str]:
    try:
        metadata = load_project_metadata(root)
        return {
            "project_id": metadata.project_id,
            "name": metadata.name,
            "root_path": metadata.root_path,
            "source_control": metadata.source_control.mode,
        }
    except Exception:
        return {
            "project_id": "",
            "name": root.name,
            "root_path": root.as_posix(),
            "source_control": "unknown",
        }


def _transcript_text(records: list[dict[str, Any]]) -> str:
    lines = []
    for record in records:
        role = str(record.get("role") or "unknown").title()
        content = str(record.get("content") or "").strip()
        if content:
            lines.append(f"### {role}\n\n{content}")
    return "\n\n".join(lines)


def _markdown_bullets(text: str) -> list[str]:
    bullets: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(("- ", "* ")):
            bullets.append(stripped[2:].strip())
    if bullets:
        return bullets[:20]
    headings = [line.strip("# ").strip() for line in text.splitlines() if line.startswith("#")]
    return [heading for heading in headings if heading][:10]


def _title_from_session(records: list[dict[str, Any]]) -> str | None:
    for record in records:
        if record.get("role") != "user":
            continue
        content = str(record.get("content") or "").strip()
        if content:
            return re.sub(r"\s+", " ", content)[:80].strip()
    return None


def _ponytail_rules() -> list[str]:
    return [
        "Skip unnecessary work.",
        "Delete what should not exist.",
        "Reuse existing code before writing new code.",
        "Prefer stdlib, native platform behavior, or already-approved dependencies.",
        "Write only the minimum new code that works.",
    ]


def _render_definition_of_done(payload: dict[str, Any]) -> str:
    lines = [
        f"# Definition of Done: {payload['title']}",
        "",
        "## Required Output",
        "",
        "Produce a concise `implementation.md` package that can later become one Dev-Flow task. Do not mutate code.",
        "",
        "## Spec Criteria",
        "",
        *_bullet_lines(payload.get("spec_criteria") or ["Spec artifact must be satisfied."]),
        "",
        "## Plan Requirements",
        "",
        *_bullet_lines(payload.get("plan_requirements") or ["Plan artifact must be followed."]),
        "",
        "## Project Constraints",
        "",
        *_bullet_lines(payload.get("project_constraints") or []),
        "",
        "## Graphify Requirements",
        "",
        *_bullet_lines(payload.get("graphify_requirements") or []),
        "",
        "## Ponytail Simplification Rules",
        "",
        *_bullet_lines(payload.get("ponytail_simplification_rules") or []),
    ]
    human_dod = str(payload.get("human_definition_of_done") or "").strip()
    if human_dod:
        lines.extend(["", "## Operator Definition of Done", "", human_dod])
    return "\n".join(lines).strip()


def _render_starting_point(payload: dict[str, Any]) -> str:
    context = payload.get("project_context") or {}
    evidence_paths = payload.get("evidence_paths") or []
    lines = [
        "# Workbench Starting Point",
        "",
        "## Project Context",
        "",
        *(f"- {key}: {value}" for key, value in context.items()),
        "",
        "## Transcript",
        "",
        str(payload.get("transcript") or "No transcript text."),
        "",
        "## Spec",
        "",
        str(payload.get("spec") or "No spec artifact."),
        "",
        "## Plan",
        "",
        str(payload.get("plan") or "No plan artifact."),
        "",
        "## Graphify Summary",
        "",
        str(payload.get("graphify_summary") or "No Graphify summary."),
        "",
        "## Ponytail Checklist",
        "",
        *_bullet_lines(payload.get("ponytail_checklist") or []),
        "",
        "## Evidence Paths",
        "",
        *_bullet_lines(evidence_paths),
    ]
    return "\n".join(lines).strip()


def _bullet_lines(values: list[Any]) -> list[str]:
    return [f"- {value}" for value in values if str(value).strip()]


def _write_refactor_offer(
    root: Path,
    *,
    session_id: str,
    run: BuilderJudgeRun,
    package: WorkbenchImplementationPackage,
) -> str:
    target = root / ".devflow" / "brainstorms" / session_id / "refactor-offer.json"
    payload = {
        "schema_version": 1,
        "status": "available",
        "session_id": session_id,
        "loop_id": run.loop_id,
        "builder_judge_status": run.status,
        "final_score": run.final_score,
        "graphify_evidence": package.starting_point.get("evidence_paths", []),
        "ponytail_rules": _ponytail_rules(),
        "action": {
            "label": "Send to Refactor Loop",
            "endpoint": "/api/refactor/start",
            "requires_human_approval": True,
        },
    }
    atomic_write_text(target, json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return relative_path(root, target)


def _new_workbench_loop_id() -> str:
    return "workbench-implement-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def new_workbench_loop_id() -> str:
    return _new_workbench_loop_id()


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
