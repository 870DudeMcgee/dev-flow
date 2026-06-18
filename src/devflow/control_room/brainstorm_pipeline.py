from __future__ import annotations

import json
import shlex
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from devflow.control_room.paths import relative_path
from devflow.control_room.persistence import atomic_write_text


class BrainstormPipelineStage(BaseModel):
    id: str
    label: str
    status: str
    artifact_path: str | None = None
    evidence_paths: list[str] = Field(default_factory=list)


class BrainstormAdvisoryModel(BaseModel):
    profile_id: str | None = None
    model: str | None = None
    provider: str | None = None
    adapter: str | None = None
    used_model: bool = False
    status: str = "not_requested"
    raw_response_path: str | None = None
    error: str | None = None
    usage: dict[str, Any] | None = None


class BrainstormImplementationContext(BaseModel):
    text: str
    source_paths: list[str] = Field(default_factory=list)
    artifact_path: str | None = None
    write_endpoint: str = "/api/task/write-context"
    target_path_template: str = ".devflow/workspaces/{task_id}/implementation-context.md"


class BrainstormTaskCreationAction(BaseModel):
    intent: str = "create_task"
    label: str = "Open Implementation Task"
    command: str
    title: str
    definition_of_done: str | None = None
    scope: str = "brainstorm"
    safety_class: str = "approval_required_task_state"
    requires_human_approval: bool = True
    supervisor_may_auto_run: bool = False
    reason: str = "Creates one Dev-Flow task from an approved brainstorm escalation."
    evidence_paths: list[str] = Field(default_factory=list)
    follow_up_intent: str = "start_shell"
    context_required: bool = False


class BrainstormPipelineDetail(BaseModel):
    schema_version: int = 1
    session_id: str
    stage: str
    status: str
    has_transcript: bool
    has_spec: bool
    has_plan: bool
    has_implementation: bool
    stages: list[BrainstormPipelineStage] = Field(default_factory=list)
    artifact_path: str | None = None
    evidence_paths: list[str] = Field(default_factory=list)
    advisory_model: BrainstormAdvisoryModel | None = None
    task_action: BrainstormTaskCreationAction | None = None
    implementation_context: BrainstormImplementationContext | None = None
    next_step_label: str
    operator_summary: str


def build_brainstorm_pipeline_detail(
    root: Path,
    *,
    session_id: str,
    stage: str,
    records: list[dict[str, Any]],
    artifact_path: Path | None = None,
    title: str | None = None,
    definition_of_done: str | None = None,
    model_info: dict[str, Any] | None = None,
    advisory_profile: dict[str, Any] | None = None,
) -> BrainstormPipelineDetail:
    """Build the shared Brainstorm -> Pipeline -> task creation story."""
    root = root.resolve()
    session_path = _session_dir(root, session_id)
    normalized_stage = str(stage or "").strip().lower()
    artifact_rel = relative_path(root, artifact_path) if artifact_path else None
    stages = _pipeline_stages(root, session_id, records=records, current_artifact=artifact_path)
    advisory_model = _advisory_model(model_info=model_info, advisory_profile=advisory_profile)
    evidence_paths = _evidence_paths(stages, artifact_rel, advisory_model)
    task_action: BrainstormTaskCreationAction | None = None
    implementation_context: BrainstormImplementationContext | None = None

    if normalized_stage == "implementation" and title:
        implementation_context = build_implementation_context(
            root,
            session_id=session_id,
            records=records,
            artifact_path=artifact_path,
        )
        task_action = build_task_creation_action(
            title=title,
            definition_of_done=definition_of_done,
            evidence_paths=evidence_paths,
            has_context=implementation_context is not None,
        )

    has_transcript = bool(records)
    has_spec = (session_path / "spec.md").exists()
    has_plan = (session_path / "plan.md").exists()
    has_implementation = (session_path / "implementation.md").exists()
    next_step_label = _next_step_label(
        stage=normalized_stage,
        has_transcript=has_transcript,
        has_spec=has_spec,
        has_plan=has_plan,
        has_implementation=has_implementation,
        task_action=task_action,
    )

    return BrainstormPipelineDetail(
        session_id=session_id,
        stage=normalized_stage,
        status="ready",
        has_transcript=has_transcript,
        has_spec=has_spec,
        has_plan=has_plan,
        has_implementation=has_implementation,
        stages=stages,
        artifact_path=artifact_rel,
        evidence_paths=evidence_paths,
        advisory_model=advisory_model,
        task_action=task_action,
        implementation_context=implementation_context,
        next_step_label=next_step_label,
        operator_summary=_operator_summary(normalized_stage, task_action, advisory_model, artifact_rel),
    )


def build_brainstorm_pipeline_state(
    root: Path,
    *,
    session_id: str,
    records: list[dict[str, Any]] | None = None,
) -> BrainstormPipelineDetail:
    root = root.resolve()
    transcript_path = _session_dir(root, session_id) / "transcript.jsonl"
    loaded_records = records if records is not None else _read_transcript(transcript_path)
    return build_brainstorm_pipeline_detail(
        root,
        session_id=session_id,
        stage=_current_stage(root, session_id, loaded_records),
        records=loaded_records,
    )


def write_brainstorm_pipeline_detail(root: Path, detail: BrainstormPipelineDetail) -> Path:
    path = _session_dir(root.resolve(), detail.session_id) / "pipeline.json"
    atomic_write_text(path, json.dumps(detail.model_dump(mode="json"), indent=2, sort_keys=True) + "\n")
    return path


def load_brainstorm_pipeline_detail(
    root: Path,
    *,
    session_id: str,
    records: list[dict[str, Any]] | None = None,
) -> BrainstormPipelineDetail:
    root = root.resolve()
    path = _session_dir(root, session_id) / "pipeline.json"
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                return BrainstormPipelineDetail.model_validate(payload)
        except (OSError, ValueError):
            pass
    return build_brainstorm_pipeline_state(root, session_id=session_id, records=records)


def build_task_creation_action(
    *,
    title: str,
    definition_of_done: str | None = None,
    evidence_paths: list[str] | None = None,
    has_context: bool = False,
) -> BrainstormTaskCreationAction:
    command_parts = ["devflow", "task", "create"]
    if definition_of_done:
        command_parts.extend(["--definition-of-done", definition_of_done])
    command_parts.append(title)
    return BrainstormTaskCreationAction(
        command=" ".join(shlex.quote(part) for part in command_parts),
        title=title,
        definition_of_done=definition_of_done,
        evidence_paths=evidence_paths or [],
        context_required=has_context,
    )


def build_implementation_context(
    root: Path,
    *,
    session_id: str,
    records: list[dict[str, Any]],
    artifact_path: Path | None = None,
) -> BrainstormImplementationContext | None:
    root = root.resolve()
    session_path = _session_dir(root, session_id)
    parts: list[str] = []
    source_paths: list[str] = []
    for stage_file in ("spec.md", "plan.md"):
        stage_path = session_path / stage_file
        if not stage_path.exists():
            continue
        content = stage_path.read_text(encoding="utf-8").strip()
        if not content:
            continue
        parts.append(content)
        source_paths.append(relative_path(root, stage_path))

    if not parts:
        for record in records[-8:]:
            role = str(record.get("role") or "unknown").title()
            content = str(record.get("content") or "").strip()
            if content:
                parts.append(f"### {role}\n\n{content}")
        if parts:
            source_paths.append(relative_path(root, session_path / "transcript.jsonl"))

    text = "\n\n---\n\n".join(parts).strip()
    if not text:
        return None
    return BrainstormImplementationContext(
        text=text,
        source_paths=source_paths,
        artifact_path=relative_path(root, artifact_path) if artifact_path else None,
    )


def _pipeline_stages(
    root: Path,
    session_id: str,
    *,
    records: list[dict[str, Any]],
    current_artifact: Path | None,
) -> list[BrainstormPipelineStage]:
    session_path = _session_dir(root, session_id)
    definitions = (
        ("brainstorm", "Brainstorm", session_path / "transcript.jsonl", bool(records)),
        ("spec", "Spec", session_path / "spec.md", (session_path / "spec.md").exists()),
        ("plan", "Plan", session_path / "plan.md", (session_path / "plan.md").exists()),
        (
            "implementation",
            "Implementation Task",
            session_path / "implementation.md",
            (session_path / "implementation.md").exists(),
        ),
    )
    stages: list[BrainstormPipelineStage] = []
    for stage_id, label, path, present in definitions:
        if current_artifact and current_artifact.resolve() == path.resolve():
            present = True
        artifact_path = relative_path(root, path) if present else None
        stages.append(
            BrainstormPipelineStage(
                id=stage_id,
                label=label,
                status="complete" if present else "pending",
                artifact_path=artifact_path,
                evidence_paths=[artifact_path] if artifact_path else [],
            )
        )
    return stages


def _advisory_model(
    *,
    model_info: dict[str, Any] | None,
    advisory_profile: dict[str, Any] | None,
) -> BrainstormAdvisoryModel | None:
    if not model_info and not advisory_profile:
        return None
    profile = advisory_profile or {}
    info = model_info or {}
    used = bool(info.get("used_model"))
    error = str(info.get("error")) if info.get("error") else None
    return BrainstormAdvisoryModel(
        profile_id=str(info.get("profile_id") or profile.get("profile_id") or "") or None,
        model=str(info.get("model") or profile.get("model") or "") or None,
        provider=str(profile.get("provider") or "") or None,
        adapter=str(profile.get("adapter") or "") or None,
        used_model=used,
        status="used" if used else ("error" if error else "available"),
        raw_response_path=str(info.get("raw_response_path") or "") or None,
        error=error,
        usage=info.get("usage") if isinstance(info.get("usage"), dict) else None,
    )


def _evidence_paths(
    stages: list[BrainstormPipelineStage],
    artifact_path: str | None,
    advisory_model: BrainstormAdvisoryModel | None,
) -> list[str]:
    values: list[str | None] = [artifact_path]
    for stage in stages:
        values.extend(stage.evidence_paths)
    if advisory_model and advisory_model.raw_response_path:
        values.append(advisory_model.raw_response_path)
    seen: set[str] = set()
    paths: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        paths.append(value)
    return paths


def _next_step_label(
    *,
    stage: str,
    has_transcript: bool,
    has_spec: bool,
    has_plan: bool,
    has_implementation: bool,
    task_action: BrainstormTaskCreationAction | None,
) -> str:
    if task_action:
        return "Create task"
    if not has_transcript:
        return "Brainstorm"
    if not has_spec:
        return "Escalate to spec"
    if not has_plan:
        return "Generate plan"
    if not has_implementation or stage == "implementation":
        return "Create task"
    return "Start selected task"


def _operator_summary(
    stage: str,
    task_action: BrainstormTaskCreationAction | None,
    advisory_model: BrainstormAdvisoryModel | None,
    artifact_path: str | None,
) -> str:
    if task_action:
        context = " with implementation context" if task_action.context_required else ""
        return f"Ready to create `{task_action.title}`{context}."
    if advisory_model and advisory_model.used_model:
        return f"{stage.title()} artifact generated by {advisory_model.model or advisory_model.profile_id}."
    if advisory_model and advisory_model.error:
        return f"{stage.title()} artifact written after advisory model error."
    if artifact_path:
        return f"{stage.title()} artifact written to {artifact_path}."
    return "Brainstorm pipeline state is ready."


def _current_stage(root: Path, session_id: str, records: list[dict[str, Any]]) -> str:
    session_path = _session_dir(root, session_id)
    if (session_path / "implementation.md").exists():
        return "implementation"
    if (session_path / "plan.md").exists():
        return "plan"
    if (session_path / "spec.md").exists():
        return "spec"
    return "brainstorm" if records else "empty"


def _read_transcript(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            records.append(value)
    return records


def _session_dir(root: Path, session_id: str) -> Path:
    return root / ".devflow" / "brainstorms" / session_id
