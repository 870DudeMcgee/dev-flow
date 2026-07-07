from __future__ import annotations

import json
import shlex
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from devflow.control_room.paths import relative_path, task_dir, workspace_path
from devflow.control_room.persistence import append_event, atomic_write_text
from devflow.control_room.stage_artifact import load_stage_artifact


class BrainstormPipelineStage(BaseModel):
    id: str
    label: str
    status: str
    artifact_path: str | None = None
    evidence_paths: list[str] = Field(default_factory=list)
    worker_label: str | None = None       # e.g. "DeepSeek V4 Flash"
    next_action: str | None = None         # e.g. "Run quality gate before escalating"
    source: str | None = None              # e.g. "brainstorm", "builder_judge", "manual"


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
    lineage: dict[str, Any] | None = None


class BrainstormSessionArtifact(BaseModel):
    id: str
    label: str
    artifact_path: str | None = None
    exists: bool = False
    evidence_paths: list[str] = Field(default_factory=list)


class BrainstormSessionArtifacts(BaseModel):
    transcript: BrainstormSessionArtifact
    spec: BrainstormSessionArtifact
    plan: BrainstormSessionArtifact
    implementation: BrainstormSessionArtifact
    implementation_context: BrainstormImplementationContext | None = None


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
    lineage: dict[str, Any] | None = None


class BrainstormPostCreateAction(BaseModel):
    intent: str = "start_shell"
    label: str = "Start shell"
    command: str
    task_id: str
    safety_class: str = "approval_required_worker_runtime"
    requires_human_approval: bool = True
    reason: str = "Task is created; select it in the launchpad and choose the shell command to run."
    evidence_paths: list[str] = Field(default_factory=list)


class BrainstormLaunchpadSelection(BaseModel):
    selected_task_id: str
    focus_shell: bool = True
    command: str
    action_label: str = "Start shell"
    reason: str = "Created from Brainstorm; ready for the operator to start bounded shell work."
    evidence_paths: list[str] = Field(default_factory=list)


class BrainstormTaskBridgeAction(BaseModel):
    label: str
    command: str
    enabled: bool = True
    safety_class: str
    requires_human_approval: bool
    intent: str | None = None


class BrainstormTaskCreationResult(BaseModel):
    schema_version: int = 1
    status: str = "created"
    task_id: str
    title: str
    context_path: str
    actions: list[BrainstormTaskBridgeAction] = Field(default_factory=list)
    post_create_action: BrainstormPostCreateAction
    launchpad: BrainstormLaunchpadSelection
    evidence_paths: list[str] = Field(default_factory=list)
    lineage: dict[str, Any] = Field(default_factory=dict)
    pipeline_detail: dict[str, Any] | None = None


class BrainstormPipelineDetail(BaseModel):
    schema_version: int = 1
    session_id: str
    stage: str
    status: str
    artifacts: BrainstormSessionArtifacts
    has_transcript: bool
    has_spec: bool
    has_plan: bool
    has_implementation: bool
    definition_of_done: str | None = None
    stages: list[BrainstormPipelineStage] = Field(default_factory=list)
    artifact_path: str | None = None
    evidence_paths: list[str] = Field(default_factory=list)
    advisory_model: BrainstormAdvisoryModel | None = None
    task_action: BrainstormTaskCreationAction | None = None
    implementation_context: BrainstormImplementationContext | None = None
    post_create_action: BrainstormPostCreateAction | None = None
    launchpad_selection: BrainstormLaunchpadSelection | None = None
    created_task_ids: list[str] = Field(default_factory=list)
    lineage: dict[str, Any] | None = None
    next_step_label: str
    operator_summary: str


class BrainstormEscalationResult(BaseModel):
    schema_version: int = 1
    status: str = "ready"
    session_id: str
    stage: str
    artifact_path: str | None
    lineage: dict[str, Any] | None
    model_info: dict[str, Any] | None
    pipeline_detail: BrainstormPipelineDetail
    action: BrainstormTaskCreationAction | None = None
    implementation_context: str | None = None
    implementation_context_path: str | None = None


class BrainstormSessionSnapshot(BaseModel):
    schema_version: int = 1
    session_id: str
    messages: list[dict[str, Any]] = Field(default_factory=list)
    spec: str | None = None
    plan: str | None = None
    implementation: str | None = None
    pipeline: BrainstormPipelineDetail


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
    source_idea_id: str | None = None,
    advisory_profile: dict[str, Any] | None = None,
) -> BrainstormPipelineDetail:
    """Build the shared Brainstorm -> Pipeline -> task creation story."""
    root = root.resolve()
    normalized_stage = str(stage or "").strip().lower()
    artifact_rel = relative_path(root, artifact_path) if artifact_path else None
    stages = _pipeline_stages(root, session_id, records=records, current_artifact=artifact_path)
    advisory_model = _advisory_model(model_info=model_info, advisory_profile=advisory_profile)
    evidence_paths = _evidence_paths(stages, artifact_rel, advisory_model)

    lineage = _lineage_payload(
        root,
        session_id=session_id,
        artifact_stage=normalized_stage,
        artifact_path=artifact_path,
        source_idea_id=source_idea_id,
    )

    task_action: BrainstormTaskCreationAction | None = None
    implementation_context: BrainstormImplementationContext | None = None

    normalized_definition_of_done = _definition_of_done(definition_of_done)
    if normalized_stage == "implementation" and title:
        impl_ctx = build_implementation_context(
            root,
            session_id=session_id,
            records=records,
            artifact_path=artifact_path,
            source_idea_id=source_idea_id,
            lineage=lineage,
        )
        implementation_context = impl_ctx
        task_action = build_task_creation_action(
            title=title,
            definition_of_done=normalized_definition_of_done,
            evidence_paths=evidence_paths,
            has_context=impl_ctx is not None,
            source_idea_id=source_idea_id,
            lineage=lineage,
        )

    artifacts = _session_artifacts(
        root,
        session_id,
        records=records,
        implementation_context=implementation_context,
    )
    has_transcript = artifacts.transcript.exists
    has_spec = artifacts.spec.exists
    has_plan = artifacts.plan.exists
    has_implementation = artifacts.implementation.exists
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
        artifacts=artifacts,
        has_transcript=has_transcript,
        has_spec=has_spec,
        has_plan=has_plan,
        has_implementation=has_implementation,
        definition_of_done=normalized_definition_of_done,
        stages=stages,
        artifact_path=artifact_rel,
        evidence_paths=evidence_paths,
        advisory_model=advisory_model,
        task_action=task_action,
        implementation_context=implementation_context,
        lineage=lineage,
        next_step_label=next_step_label,
        operator_summary=_operator_summary(normalized_stage, task_action, advisory_model, artifact_rel),
    )


def build_brainstorm_escalation_result(
    detail: BrainstormPipelineDetail,
    *,
    artifact_path: str | None = None,
    model_info: dict[str, Any] | None = None,
) -> BrainstormEscalationResult:
    """Build the typed Brainstorm escalation response consumed by adapters."""
    implementation_context = detail.implementation_context
    return BrainstormEscalationResult(
        status=detail.status,
        session_id=detail.session_id,
        stage=detail.stage,
        artifact_path=artifact_path or detail.artifact_path,
        lineage=detail.lineage,
        model_info=model_info,
        pipeline_detail=detail,
        action=detail.task_action,
        implementation_context=implementation_context.text if implementation_context else None,
        implementation_context_path=implementation_context.artifact_path if implementation_context else None,
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


def load_brainstorm_session_snapshot(root: Path, *, session_id: str) -> BrainstormSessionSnapshot:
    root = root.resolve()
    session_path = _session_dir(root, session_id)
    messages = _read_transcript(session_path / "transcript.jsonl")
    pipeline = load_brainstorm_pipeline_detail(root, session_id=session_id, records=messages)
    artifacts = pipeline.artifacts
    return BrainstormSessionSnapshot(
        session_id=session_id,
        messages=messages,
        spec=_read_artifact_text(root, artifacts.spec),
        plan=_read_artifact_text(root, artifacts.plan),
        implementation=_read_artifact_text(root, artifacts.implementation),
        pipeline=pipeline,
    )


def build_task_creation_action(
    *,
    title: str,
    definition_of_done: str | None = None,
    evidence_paths: list[str] | None = None,
    has_context: bool = False,
    source_idea_id: str | None = None,
    lineage: dict[str, Any] | None = None,
) -> BrainstormTaskCreationAction:
    command_parts = ["devflow", "task", "create"]
    if definition_of_done:
        command_parts.extend(["--definition-of-done", definition_of_done])
    command_parts.append(title)

    action_lineage = lineage
    if action_lineage is None and source_idea_id:
        action_lineage = {
            "schema_version": 1,
            "source_idea_id": source_idea_id,
        }

    return BrainstormTaskCreationAction(
        command=" ".join(shlex.quote(part) for part in command_parts),
        title=title,
        definition_of_done=definition_of_done,
        evidence_paths=evidence_paths or [],
        context_required=has_context,
        lineage=action_lineage,
    )


def create_task_from_brainstorm(
    root: Path,
    session_id: str,
    stage: str,
    title: str,
    definition_of_done: str | None = None,
    source_idea_id: str | None = None,
) -> dict[str, Any]:
    """Create a Dev-Flow task from a ready implementation-stage brainstorm.

    This is the single Brainstorm -> Pipeline -> Task Interface used by the
    server and browser adapters. It validates the session artifacts, creates the
    task, writes implementation context, records task evidence, updates the
    pipeline state, and returns the launchpad selection for the operator.
    """
    root = root.resolve()
    stage_lower = str(stage or "").lower().strip()
    if stage_lower != "implementation":
        raise ValueError("create_task_from_brainstorm only supports stage=implementation")

    session_path = _session_dir(root, session_id)
    transcript_path = session_path / "transcript.jsonl"
    implementation_artifact = session_path / "implementation.md"
    if not transcript_path.exists():
        raise ValueError(f"brainstorm session has no transcript: {session_id}")
    records = _read_transcript(transcript_path)
    if not records:
        raise ValueError(f"brainstorm session has no transcript records: {session_id}")
    if not implementation_artifact.exists():
        raise ValueError(
            f"brainstorm stage is not implementation for session {session_id}; "
            f"implementation.md missing."
        )

    normalized_title = str(title or "").strip()
    if not normalized_title:
        raise ValueError("title is required")
    normalized_definition_of_done = _definition_of_done(definition_of_done)
    resolved_source_idea_id = source_idea_id or _extract_source_idea_id(records)
    existing_detail = load_brainstorm_pipeline_detail(root, session_id=session_id, records=records)
    lineage = dict(
        existing_detail.lineage
        or _lineage_payload(
            root,
            session_id=session_id,
            artifact_stage=stage_lower,
            artifact_path=implementation_artifact,
            source_idea_id=resolved_source_idea_id,
        )
    )
    if resolved_source_idea_id:
        lineage["source_idea_id"] = resolved_source_idea_id

    detail = build_brainstorm_pipeline_detail(
        root,
        session_id=session_id,
        stage=stage_lower,
        records=records,
        artifact_path=implementation_artifact,
        title=normalized_title,
        definition_of_done=normalized_definition_of_done,
        source_idea_id=resolved_source_idea_id,
    )
    if existing_detail.advisory_model and detail.advisory_model is None:
        detail = detail.model_copy(update={"advisory_model": existing_detail.advisory_model})

    from devflow.control_room.service import create_task

    task_record = create_task(
        root=root,
        title=normalized_title,
        definition_of_done=normalized_definition_of_done,
    )
    task_id = task_record.id
    task_path = workspace_path(root, task_id)

    context = build_implementation_context(
        root=root,
        session_id=session_id,
        records=records,
        artifact_path=implementation_artifact,
        source_idea_id=resolved_source_idea_id,
        lineage=lineage,
    )
    if context is None:
        implementation_text = implementation_artifact.read_text(encoding="utf-8").strip()
        context = BrainstormImplementationContext(
            text=implementation_text,
            source_paths=[relative_path(root, implementation_artifact)],
            artifact_path=relative_path(root, implementation_artifact),
            lineage=lineage,
        )

    context_file = task_path / "implementation-context.md"
    atomic_write_text(context_file, context.text + "\n", encoding="utf-8")
    context_path = relative_path(root, context_file)

    append_event(
        root,
        task_id,
        "brainstorm_created",
        {
            "session_id": session_id,
            "source_idea_id": resolved_source_idea_id,
            "lineage": lineage,
            "definition_of_done": normalized_definition_of_done,
            "context_path": context_path,
        },
    )

    created_task_ids = _append_unique(existing_detail.created_task_ids, task_id)
    updated_lineage = dict(lineage)
    updated_lineage["created_task_id"] = task_id
    updated_lineage["created_task_ids"] = created_task_ids

    evidence_paths = _append_unique(
        [
            *detail.evidence_paths,
            context_path,
            relative_path(root, task_dir(root, task_id) / "task.yaml"),
            relative_path(root, task_dir(root, task_id) / "events.jsonl"),
        ]
    )
    post_create_action = _post_create_action(task_id, evidence_paths)
    launchpad_selection = _launchpad_selection(task_id, post_create_action, evidence_paths)
    updated_detail = detail.model_copy(
        update={
            "implementation_context": context,
            "artifacts": _session_artifacts(
                root,
                session_id,
                records=records,
                implementation_context=context,
            ),
            "evidence_paths": evidence_paths,
            "lineage": updated_lineage,
            "post_create_action": post_create_action,
            "launchpad_selection": launchpad_selection,
            "created_task_ids": created_task_ids,
            "operator_summary": f"Created `{normalized_title}` as {task_id}. Next: start shell work from the launchpad.",
            "next_step_label": "Start shell",
        }
    )
    write_brainstorm_pipeline_detail(root, updated_detail)

    result = BrainstormTaskCreationResult(
        task_id=task_id,
        title=normalized_title,
        context_path=context_path,
        actions=_bridge_actions(task_id),
        post_create_action=post_create_action,
        launchpad=launchpad_selection,
        evidence_paths=evidence_paths,
        lineage=updated_lineage,
        pipeline_detail=updated_detail.model_dump(mode="json"),
    )
    return result.model_dump(mode="json")


def build_implementation_context(
    root: Path,
    *,
    session_id: str,
    records: list[dict[str, Any]],
    artifact_path: Path | None = None,
    source_idea_id: str | None = None,
    lineage: dict[str, Any] | None = None,
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

    context_lineage = lineage
    if context_lineage is None:
        context_lineage = _lineage_payload(
            root,
            session_id=session_id,
            artifact_stage="implementation",
            artifact_path=artifact_path,
            source_idea_id=source_idea_id,
        )

    return BrainstormImplementationContext(
        text=text,
        source_paths=source_paths,
        artifact_path=relative_path(root, artifact_path) if artifact_path else None,
        lineage=context_lineage,
    )


def _session_artifacts(
    root: Path,
    session_id: str,
    *,
    records: list[dict[str, Any]],
    implementation_context: BrainstormImplementationContext | None,
) -> BrainstormSessionArtifacts:
    session_path = _session_dir(root, session_id)
    return BrainstormSessionArtifacts(
        transcript=_artifact(root, "transcript", "Transcript", session_path / "transcript.jsonl", bool(records)),
        spec=_artifact(root, "spec", "Spec", session_path / "spec.md"),
        plan=_artifact(root, "plan", "Plan", session_path / "plan.md"),
        implementation=_artifact(root, "implementation", "Implementation Task", session_path / "implementation.md"),
        implementation_context=implementation_context,
    )


def _artifact(
    root: Path,
    artifact_id: str,
    label: str,
    path: Path,
    present: bool | None = None,
) -> BrainstormSessionArtifact:
    exists = path.exists() if present is None else bool(present or path.exists())
    artifact_path = relative_path(root, path) if exists else None
    return BrainstormSessionArtifact(
        id=artifact_id,
        label=label,
        artifact_path=artifact_path,
        exists=exists,
        evidence_paths=[artifact_path] if artifact_path else [],
    )


def _read_artifact_text(root: Path, artifact: BrainstormSessionArtifact) -> str | None:
    if not artifact.artifact_path:
        return None
    path = root / artifact.artifact_path
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def _definition_of_done(value: str | None) -> str | None:
    text = str(value or "").strip()
    return text or None


def _post_create_action(task_id: str, evidence_paths: list[str]) -> BrainstormPostCreateAction:
    return BrainstormPostCreateAction(
        task_id=task_id,
        command=f"devflow task run {task_id} --worker shell -- <command>",
        evidence_paths=evidence_paths,
    )


def _launchpad_selection(
    task_id: str,
    post_create_action: BrainstormPostCreateAction,
    evidence_paths: list[str],
) -> BrainstormLaunchpadSelection:
    return BrainstormLaunchpadSelection(
        selected_task_id=task_id,
        command=post_create_action.command,
        action_label=post_create_action.label,
        reason=post_create_action.reason,
        evidence_paths=evidence_paths,
    )


def _bridge_actions(task_id: str) -> list[BrainstormTaskBridgeAction]:
    return [
        BrainstormTaskBridgeAction(
            label="Inspect",
            command=f"devflow task show {task_id}",
            safety_class="pure_read_only",
            requires_human_approval=False,
            intent="inspect",
        ),
        BrainstormTaskBridgeAction(
            label="Start shell",
            command=f"devflow task run {task_id} --worker shell -- <command>",
            safety_class="approval_required_worker_runtime",
            requires_human_approval=True,
            intent="start_shell",
        ),
        BrainstormTaskBridgeAction(
            label="Verify",
            command=f'devflow task verify {task_id} --shell "<command>"',
            safety_class="approval_required_worker_runtime",
            requires_human_approval=True,
            intent="verify",
        ),
    ]


def _append_unique(values: list[str], *extra_values: str) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in [*values, *extra_values]:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _extract_source_idea_id(records: list[dict[str, Any]]) -> str | None:
    for record in reversed(records):
        if record.get("kind") != "brainstorm_start":
            continue
        metadata = record.get("metadata")
        if not isinstance(metadata, dict):
            continue
        source_idea_id = str(metadata.get("source_idea_id") or "").strip()
        if source_idea_id:
            return source_idea_id
    return None


def _lineage_payload(
    root: Path,
    *,
    session_id: str,
    artifact_stage: str,
    artifact_path: Path | None = None,
    source_idea_id: str | None = None,
) -> dict[str, Any]:
    session_path = _session_dir(root, session_id)
    payload: dict[str, Any] = {
        "schema_version": 1,
        "brainstorm_session_id": session_id,
        "brainstorm_path": relative_path(root, session_path),
        "artifact_stage": artifact_stage,
    }
    if source_idea_id:
        payload["source_idea_id"] = source_idea_id
    if artifact_path is not None:
        payload["artifact_path"] = relative_path(root, artifact_path)

    for stage_id, filename in (
        ("spec", "spec.md"),
        ("plan", "plan.md"),
        ("implementation", "implementation.md"),
    ):
        candidate = artifact_path if artifact_stage == stage_id and artifact_path is not None else session_path / filename
        if candidate.exists():
            payload[f"{stage_id}_path"] = relative_path(root, candidate)
            sidecar = candidate.with_suffix(".lineage.json")
            if sidecar.exists():
                payload[f"{stage_id}_lineage_path"] = relative_path(root, sidecar)
    return payload


def _pipeline_stages(
    root: Path,
    session_id: str,
    *,
    records: list[dict[str, Any]],
    current_artifact: Path | None,
) -> list[BrainstormPipelineStage]:
    session_path = _session_dir(root, session_id)
    stage_artifacts = {
        "spec": load_stage_artifact(root, session_id, "spec"),
        "plan": load_stage_artifact(root, session_id, "plan"),
    }
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
    for stage_id, label, file_path, present in definitions:
        if current_artifact and current_artifact.resolve() == file_path.resolve():
            present = True
        stage_artifact = stage_artifacts.get(stage_id)
        evidence_paths: list[str] = []
        if stage_artifact is not None:
            stage_status = stage_artifact.status
            artifact_path = stage_artifact.artifact_path
            evidence_paths.append(stage_artifact.artifact_path)
            if stage_artifact.quality_gate_path:
                evidence_paths.append(stage_artifact.quality_gate_path)
        elif present:
            stage_status = "complete"
            artifact_path = relative_path(root, file_path)
            evidence_paths.append(artifact_path)
        else:
            stage_status = "pending"
            artifact_path = None

        stages.append(
            BrainstormPipelineStage(
                id=stage_id,
                label=label,
                status=stage_status,
                artifact_path=artifact_path,
                evidence_paths=evidence_paths,
                next_action=stage_artifact.next_action if stage_artifact else None,
                source=stage_artifact.source if stage_artifact else None,
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


# ---------------------------------------------------------------------------
# Classification gate (RLC-04) — rule-based, no LLM needed
# ---------------------------------------------------------------------------

# Known deterministic-tool commands that can be handled without models.
DETERMINISTIC_TOOL_COMMANDS: dict[str, str] = {
    "extract_module": "Extract a module using tree-sitter",
    "lint_check": "Run lint/format checks",
    "test_run": "Run test suite",
    "dependency_scan": "Scan dependency graph",
    "codebase_survey": "Survey codebase structure",
}

# Known loop presets for the repo-loop cockpit.
LOOP_PRESETS: dict[str, str] = {
    "single_file_edit": "Single-file edit with verification",
    "multi_file_refactor": "Multi-file refactor with builder-judge",
    "new_feature": "New feature scaffold with tests",
    "bug_fix": "Bug fix with regression test",
    "documentation": "Documentation update or generation",
    "performance": "Performance optimization pass",
}

# Keyword-to-work-type rules (ordered by specificity, first match wins).
_WORK_TYPE_RULES: list[tuple[list[str], str]] = [
    (["extract", "refactor", "rename", "move"], "refactor"),
    (["bug", "fix", "regression", "crash", "error"], "bug_fix"),
    (["test", "coverage", "spec", "assert"], "testing"),
    (["doc", "readme", "comment", "describe", "document"], "documentation"),
    (["perf", "speed", "slow", "optimize", "fast", "latency"], "performance"),
    (["feature", "add", "new", "implement", "build", "create", "scaffold"], "new_feature"),
    (["review", "audit", "check", "verify", "inspect"], "review"),
    (["cleanup", "tidy", "remove dead", "prune", "unused"], "cleanup"),
    (["config", "setup", "install", "deploy", "infra"], "infrastructure"),
]

# Keyword-to-deterministic-tool rules.
_DETERMINISTIC_TOOL_RULES: list[tuple[list[str], str]] = [
    (["extract module", "extract function", "tree-sitter"], "extract_module"),
    (["lint", "ruff", "format", "style check"], "lint_check"),
    (["test", "pytest", "unit test", "integration test"], "test_run"),
    (["dependen", "import", "graph"], "dependency_scan"),
    (["survey", "map", "scan codebase", "codebase structure"], "codebase_survey"),
]


class ClassificationResult(BaseModel):
    """Output of the brainstorm-to-classification gate.

    Rule-based classification that produces a serializable ``classification.json``
    artifact. No LLM calls — pure keyword/pattern matching.
    """

    schema_version: int = 1
    work_type: str
    rationale: str
    deterministic_tool_eligible: bool = False
    deterministic_tool_command: str | None = None
    eligible_presets: list[str] = Field(default_factory=list)
    recommended_preset: str | None = None
    why_not_alternatives: str = ""


def classify_brainstorm_intent(intent_text: str) -> ClassificationResult:
    """Classify brainstorm intent using rule-based keyword matching.

    Args:
        intent_text: The operator's brainstorm intent or implementation description.

    Returns:
        A ``ClassificationResult`` with work type, rationale, deterministic-tool
        eligibility, eligible presets, and a recommended preset.
    """
    text = str(intent_text or "").strip().lower()
    if not text:
        return ClassificationResult(
            work_type="unknown",
            rationale="No intent text provided for classification.",
            eligible_presets=list(LOOP_PRESETS.keys()),
            recommended_preset=None,
            why_not_alternatives="Cannot recommend without intent.",
        )

    # --- Work type classification ---
    work_type = "general"
    matched_keywords: list[str] = []
    for keywords, wt in _WORK_TYPE_RULES:
        for kw in keywords:
            if kw in text:
                work_type = wt
                matched_keywords.append(kw)
                break
        if matched_keywords:
            break

    rationale_parts: list[str] = []
    if matched_keywords:
        rationale_parts.append(
            f"Matched keyword(s): {', '.join(repr(k) for k in matched_keywords)}."
        )
    else:
        rationale_parts.append("No specific work-type keywords matched.")
    rationale_parts.append(f"Classified as '{work_type}' based on intent text.")
    rationale = " ".join(rationale_parts)

    # --- Deterministic-tool eligibility ---
    deterministic_tool_eligible = False
    deterministic_tool_command: str | None = None
    for keywords, command in _DETERMINISTIC_TOOL_RULES:
        for kw in keywords:
            if kw in text:
                deterministic_tool_eligible = True
                deterministic_tool_command = command
                break
        if deterministic_tool_eligible:
            break

    # --- Eligible presets ---
    eligible_presets = _eligible_presets_for_work_type(work_type)

    # --- Recommended preset ---
    recommended_preset = _recommend_preset(
        work_type, deterministic_tool_eligible, deterministic_tool_command
    )

    # --- Why not alternatives ---
    why_not = _build_why_not(
        work_type,
        recommended_preset,
        eligible_presets,
        deterministic_tool_eligible,
        deterministic_tool_command,
    )

    return ClassificationResult(
        work_type=work_type,
        rationale=rationale,
        deterministic_tool_eligible=deterministic_tool_eligible,
        deterministic_tool_command=deterministic_tool_command,
        eligible_presets=eligible_presets,
        recommended_preset=recommended_preset,
        why_not_alternatives=why_not,
    )


def build_classification_preview(payload: dict[str, Any]) -> dict[str, Any]:
    """Build a classification preview from a request payload.

    Validates required fields and returns a preview dict without writing
    any files. Used by the classification route for operator confirmation.

    Raises ``ValueError`` if ``operator_intent`` is missing.
    """
    operator_intent = payload.get("operator_intent")
    if not isinstance(operator_intent, str) or not operator_intent.strip():
        raise ValueError("operator_intent is required and must be a non-empty string")

    result = classify_brainstorm_intent(operator_intent.strip())
    return {
        "ok": True,
        "operator_intent": operator_intent.strip(),
        "classification": result.model_dump(mode="json"),
        "will_write_classification": True,
    }


def write_classification_to_pipeline_run(
    root: Path,
    run_id: str,
    classification: ClassificationResult,
) -> None:
    """Write classification.json into an existing pipeline run directory.

    Raises ``FileNotFoundError`` if the run does not exist.
    """
    from devflow.control_room.pipeline_run import (
        _run_dir,
        update_pipeline_run_record,
    )

    run_dir = _run_dir(root, run_id)
    if not run_dir.is_dir():
        raise FileNotFoundError(f"Pipeline run not found: {run_id}")
    update_pipeline_run_record(
        root, run_id, "classification.json", classification.model_dump(mode="json")
    )


def classify_and_attach_to_run(
    root: Path,
    run_id: str,
    operator_intent: str,
) -> dict[str, Any]:
    """Classify intent and write classification.json to a pipeline run.

    Convenience function combining classification and persistence.
    Returns the classification result plus run metadata.
    """
    from devflow.control_room.pipeline_run import _run_dir, pipeline_runs_dir

    classification = classify_brainstorm_intent(operator_intent)
    write_classification_to_pipeline_run(root, run_id, classification)
    run_dir = _run_dir(root, run_id)
    return {
        "ok": True,
        "run_id": run_id,
        "classification": classification.model_dump(mode="json"),
        "classification_path": str(run_dir / "classification.json"),
        "pipeline_runs_dir": str(pipeline_runs_dir(root)),
    }




# ---------------------------------------------------------------------------
# Intent Summary generation (rule-based, no LLM)
# ---------------------------------------------------------------------------

# Keyword/pattern rules for intent summary field extraction.
# Each rule: (pattern_list, field_name, default_text).
_WANTS_RULES: list[tuple[list[str], str]] = [
    (["i want", "we need", "add ", "build ", "create ", "implement ", "make "], "user_wants"),
    (["should ", "must ", "result ", "outcome ", "goal ", "deliver "], "product_outcome"),
]

_NON_NEGOTIABLE_PATTERNS: list[str] = [
    "must", "never", "always", "don't break", "regression", "no regress",
    "backward compatible", "backwards compatible", "mandatory", "required",
    "critical", "blocker", "non-negotiable",
]

_MISUNDERSTANDING_PATTERNS: list[str] = [
    "not ", "do not ", "don't ", "avoid ", "skip ", "no ", "without ",
    "except ", "only ", "just ", "simply ",
]

_DONE_CRITERIA_PATTERNS: list[str] = [
    "done when", "done looks like", "completion", "passing tests",
    "all tests pass", "verified", "working", "deployed",
]


def build_intent_summary_preview(intent_text: str) -> dict[str, Any]:
    """Build an intent summary preview from operator intent text.

    Rule-based extraction using keyword/pattern heuristics. Returns a
    preview dict without writing any files.
    """

    text = str(intent_text or "").strip()
    if not text:
        return _empty_intent_summary_preview()

    summary = _extract_intent_summary(text)
    return {
        "ok": True,
        "operator_intent": text,
        "intent_summary": summary.model_dump(mode="json"),
        "source": "generated",
    }


def build_manual_intent_summary(
    operator_intent: str,
    manual_summary: dict[str, Any],
) -> dict[str, Any]:
    """Build an intent summary from a manual override provided by the operator.

    Validates that the manual_summary contains at least one non-empty field.
    """
    from devflow.control_room.pipeline_run import IntentSummary

    intent_text = str(operator_intent or "").strip()
    if not intent_text:
        raise ValueError("operator_intent is required and must be a non-empty string")

    if not isinstance(manual_summary, dict) or not manual_summary:
        raise ValueError("manual_summary must be a non-empty dict")

    # Build from manual fields, falling back to empty defaults
    summary = IntentSummary(
        user_wants=str(manual_summary.get("user_wants", "") or ""),
        product_outcome=str(manual_summary.get("product_outcome", "") or ""),
        non_negotiables=[str(x) for x in (manual_summary.get("non_negotiables") or []) if str(x).strip()],
        worker_misunderstandings=[str(x) for x in (manual_summary.get("worker_misunderstandings") or []) if str(x).strip()],
        what_done_feels_like=str(manual_summary.get("what_done_feels_like", "") or ""),
        source="manual",
    )
    return {
        "ok": True,
        "operator_intent": intent_text,
        "intent_summary": summary.model_dump(mode="json"),
        "source": "manual",
    }


def write_intent_summary_to_run(
    root: Path,
    run_id: str,
    summary,
) -> None:
    """Write intent-summary.json into an existing pipeline run directory.

    Accepts an IntentSummary model or a dict. Raises ``FileNotFoundError``
    if the run does not exist.
    """
    from devflow.control_room.pipeline_run import _run_dir, update_pipeline_run_record

    run_dir = _run_dir(root, run_id)
    if not run_dir.is_dir():
        raise FileNotFoundError(f"Pipeline run not found: {run_id}")

    if hasattr(summary, "model_dump"):
        data = summary.model_dump(mode="json")
    elif isinstance(summary, dict):
        data = summary
    else:
        raise TypeError("summary must be an IntentSummary model or dict")

    update_pipeline_run_record(root, run_id, "intent-summary.json", data)


def classify_and_attach_intent_summary(
    root: Path,
    run_id: str,
    operator_intent: str,
) -> dict[str, Any]:
    """Generate intent summary and write intent-summary.json to a pipeline run.

    Convenience combining generation and persistence. Returns the summary
    result plus run metadata.
    """
    from devflow.control_room.pipeline_run import _run_dir, pipeline_runs_dir

    preview = build_intent_summary_preview(operator_intent)
    summary_data = preview["intent_summary"]
    write_intent_summary_to_run(root, run_id, summary_data)
    run_dir = _run_dir(root, run_id)
    return {
        "ok": True,
        "run_id": run_id,
        "intent_summary": summary_data,
        "intent_summary_path": str(run_dir / "intent-summary.json"),
        "pipeline_runs_dir": str(pipeline_runs_dir(root)),
        "source": "generated",
    }


def _empty_intent_summary_preview() -> dict[str, Any]:
    from devflow.control_room.pipeline_run import IntentSummary
    empty = IntentSummary()
    return {
        "ok": True,
        "operator_intent": "",
        "intent_summary": empty.model_dump(mode="json"),
        "source": "generated",
    }


def _extract_intent_summary(text: str):
    """Rule-based extraction of intent summary fields from text.

    Uses keyword/pattern matching heuristics — no LLM calls.
    """
    from devflow.control_room.pipeline_run import IntentSummary

    text_lower = text.lower()

    # user_wants: first sentence or up to 200 chars as the core want
    user_wants = _extract_first_meaningful_segment(text, max_chars=200)

    # product_outcome: sentences with outcome/goal/result language
    product_outcome = _extract_matching_sentences(text, [
        "result", "outcome", "goal", "deliver", "should", "will be",
        "produces", "enables", "provides",
    ], max_chars=200)

    # non_negotiables: sentences containing strong constraint language
    non_negotiables = _extract_matching_sentences_list(text_lower, text, _NON_NEGOTIABLE_PATTERNS)

    # worker_misunderstandings: sentences with negation/avoidance language
    worker_misunderstandings = _extract_matching_sentences_list(text_lower, text, _MISUNDERSTANDING_PATTERNS)

    # what_done_feels_like: sentences with completion criteria language
    what_done_feels_like = _extract_matching_sentences(text, _DONE_CRITERIA_PATTERNS, max_chars=200)

    return IntentSummary(
        user_wants=user_wants,
        product_outcome=product_outcome,
        non_negotiables=non_negotiables,
        worker_misunderstandings=worker_misunderstandings,
        what_done_feels_like=what_done_feels_like,
        source="generated",
    )


def _extract_first_meaningful_segment(text: str, max_chars: int = 200) -> str:
    """Extract the first sentence or segment as the core want."""
    # Try to get first sentence
    for sep in [".", "\n"]:
        if sep in text:
            segment = text.split(sep, 1)[0].strip()
            if len(segment) <= max_chars and len(segment) > 5:
                return segment
    # Fall back to truncation
    result = text.strip()
    if len(result) > max_chars:
        result = result[:max_chars].rsplit(" ", 1)[0] + "..."
    return result


def _extract_matching_sentences(
    original_text: str,
    patterns: list[str],
    max_chars: int = 200,
) -> str:
    """Extract sentences from original_text that match any of the patterns (case-insensitive)."""
    import re

    sentences = re.split(r'(?<=[.!?])\s+|\n+', original_text)
    matching = []
    for sentence in sentences:
        sent_lower = sentence.lower()
        for pat in patterns:
            if pat.lower() in sent_lower:
                matching.append(sentence.strip())
                break
        if sum(len(s) for s in matching) > max_chars:
            break
    return " ".join(matching)[:max_chars]


def _extract_matching_sentences_list(
    text_lower: str,
    original_text: str,
    patterns: list[str],
) -> list[str]:
    """Extract individual sentences matching patterns as a list."""
    import re

    sentences = re.split(r'(?<=[.!?])\s+|\n+', original_text)
    results: list[str] = []
    seen: set[str] = set()
    for sentence in sentences:
        sent_lower = sentence.lower().strip()
        for pat in patterns:
            if pat in sent_lower:
                cleaned = sentence.strip()
                if cleaned and cleaned not in seen:
                    seen.add(cleaned)
                    results.append(cleaned)
                break
    return results


def _eligible_presets_for_work_type(work_type: str) -> list[str]:
    """Return eligible presets for a given work type."""
    preset_map: dict[str, list[str]] = {
        "refactor": ["multi_file_refactor", "single_file_edit"],
        "bug_fix": ["bug_fix", "single_file_edit"],
        "testing": ["single_file_edit", "multi_file_refactor"],
        "documentation": ["documentation", "single_file_edit"],
        "performance": ["performance", "multi_file_refactor"],
        "new_feature": ["new_feature", "multi_file_refactor"],
        "review": ["single_file_edit"],
        "cleanup": ["single_file_edit", "multi_file_refactor"],
        "infrastructure": ["single_file_edit"],
        "general": list(LOOP_PRESETS.keys()),
        "unknown": list(LOOP_PRESETS.keys()),
    }
    return preset_map.get(work_type, list(LOOP_PRESETS.keys()))


def _recommend_preset(
    work_type: str,
    deterministic_tool_eligible: bool,
    deterministic_tool_command: str | None,
) -> str | None:
    """Recommend a preset based on work type and deterministic-tool eligibility."""
    if deterministic_tool_eligible and deterministic_tool_command:
        return None  # Deterministic tool lane, not a loop preset
    recommendations: dict[str, str] = {
        "refactor": "multi_file_refactor",
        "bug_fix": "bug_fix",
        "testing": "single_file_edit",
        "documentation": "documentation",
        "performance": "performance",
        "new_feature": "new_feature",
        "review": "single_file_edit",
        "cleanup": "single_file_edit",
        "infrastructure": "single_file_edit",
    }
    return recommendations.get(work_type)


def _build_why_not(
    work_type: str,
    recommended_preset: str | None,
    eligible_presets: list[str],
    deterministic_tool_eligible: bool,
    deterministic_tool_command: str | None,
) -> str:
    """Build explanation for why alternatives were not recommended."""
    parts: list[str] = []
    if deterministic_tool_eligible and deterministic_tool_command:
        parts.append(
            f"Deterministic tool '{deterministic_tool_command}' is eligible; "
            "a deterministic tool lane may handle this without a loop preset."
        )
        if recommended_preset is None:
            parts.append("No loop preset recommended — route to deterministic tool lane instead.")
    elif recommended_preset:
        alternatives = [p for p in eligible_presets if p != recommended_preset]
        if alternatives:
            parts.append(
                f"Recommended '{recommended_preset}' over "
                f"{', '.join(repr(a) for a in alternatives)} based on work type '{work_type}'."
            )
        else:
            parts.append(f"'{recommended_preset}' is the only eligible preset for '{work_type}'.")
    elif work_type in ("general", "unknown"):
        parts.append("Work type is general/unknown; no specific recommendation available.")
    else:
        parts.append(f"No preset recommendation for work type '{work_type}'.")
    return " ".join(parts)
