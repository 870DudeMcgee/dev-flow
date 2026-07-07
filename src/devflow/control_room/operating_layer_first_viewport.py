from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from devflow.control_room.brainstorm_pipeline import (
    BrainstormPipelineDetail,
    BrainstormPipelineStage,
    load_brainstorm_pipeline_detail,
)
from devflow.control_room.paths import relative_path
from devflow.control_room.pipeline_run import PipelineRunProjection
from devflow.control_room.task_workbench import (
    TaskWorkbench,
    TaskWorkbenchControl,
    TaskWorkbenchEvidencePointer,
    TaskWorkbenchTaskLockStatus,
    TaskWorkbenchTask,
    TaskWorkbenchTaskEvent,
)


BRAINSTORM_MODEL_LABEL = "Hermes Qwen 3.7 Plus"
BRAINSTORM_PROFILE_ID = "hermes-qwen37plus"

LANE_RANK: dict[str, int] = {
    "failed": 0,
    "blocked": 1,
    "running": 2,
    "needs_verification": 3,
    "needs_review": 4,
    "ready_to_promote": 5,
    "new": 6,
    "idle": 7,
}

PRIMARY_INTENTS: tuple[str, ...] = (
    "start_shell",
    "retry",
    "verify",
    "review_preview",
    "promote",
    "cleanup_preview",
    "inspect",
)

PIPELINE_STAGE_ACTION_LABELS: dict[str, str] = {
    "brainstorm": "Escalate to Spec ->",
    "spec": "Generate Spec ->",
    "plan": "Generate Plan ->",
    "implementation": "Create Task ->",
    "task": "View Tasks",
}

PIPELINE_COMPLETE_STATES = {"complete", "accepted", "passed", "draft"}


class FirstViewportLatestEvent(BaseModel):
    timestamp: str | None = None
    event: str
    summary: str = ""


class FirstViewportBrainstorm(BaseModel):
    session_id: str | None = None
    status: str = "empty"
    model_label: str = BRAINSTORM_MODEL_LABEL
    profile_id: str = BRAINSTORM_PROFILE_ID
    message_count: int = 0
    transcript_path: str | None = None
    latest_message: str = ""
    latest_message_at: str | None = None
    next_action_label: str = "Start brainstorm"


class FirstViewportPipelineStage(BaseModel):
    id: str
    label: str
    status: str
    artifact_path: str | None = None
    evidence_paths: list[str] = Field(default_factory=list)
    worker_label: str | None = None
    next_action: str | None = None
    source: str | None = None
    complete: bool = False
    active: bool = False
    locked: bool = False
    action_label: str = "Review ->"


class FirstViewportPipeline(BaseModel):
    session_id: str | None = None
    status: str = "empty"
    stages: list[FirstViewportPipelineStage] = Field(default_factory=list)
    first_incomplete_stage_id: str | None = None
    primary_stage_id: str | None = None
    primary_action_label: str = "Start Brainstorm"
    next_step_label: str = "Brainstorm"
    operator_summary: str = "Start a brainstorm to shape the next task."


class FirstViewportTaskCard(BaseModel):
    task_id: str
    title: str
    lane: str
    display_status: str
    tone: str
    worker_model_label: str
    verification_status: str
    latest: str = ""
    action_label: str
    command: str | None = None
    next_safe_action: str | None = None
    latest_event: FirstViewportLatestEvent | None = None
    lock_status: TaskWorkbenchTaskLockStatus | None = None


class FirstViewportReviewCard(BaseModel):
    task_id: str
    title: str
    lane: str
    priority: str
    reason: str
    action_label: str
    command: str | None = None
    evidence_paths: list[str] = Field(default_factory=list)
    review_state: str = "not_ready"
    review_score: int = 0
    operator_summary: str = ""
    blockers: list[str] = Field(default_factory=list)
    changed_files: list[str] = Field(default_factory=list)
    evidence_count: int = 0
    next_safe_action: str | None = None


class FirstViewportEvidenceCard(BaseModel):
    task_id: str
    kind: str
    text: str
    path: str | None = None
    command: str | None = None
    timestamp: str | None = None
    label: str = ""


class FirstViewportLaunchpad(BaseModel):
    selected_task_id: str | None = None
    active_task_ids: list[str] = Field(default_factory=list)
    switcher_task_ids: list[str] = Field(default_factory=list)
    command: str | None = None
    action_label: str = "Inspect task"
    reason: str | None = None


class FirstViewportNextTask(BaseModel):
    task_id: str
    title: str
    lane: str
    display_status: str
    worker_model_label: str
    verification_status: str
    latest: str = ""
    definition_of_done: str | None = None
    action_label: str
    command: str | None = None
    reason: str | None = None
    evidence_paths: list[str] = Field(default_factory=list)
    lock_status: TaskWorkbenchTaskLockStatus | None = None


class FirstViewportPresentation(BaseModel):
    schema_version: int = 1
    active_task_count: int
    total_task_count: int
    brainstorm: FirstViewportBrainstorm = Field(default_factory=FirstViewportBrainstorm)
    pipeline: FirstViewportPipeline = Field(default_factory=FirstViewportPipeline)
    next_task: FirstViewportNextTask | None = None
    worker_lanes: list[FirstViewportTaskCard] = Field(default_factory=list)
    review_queue: list[FirstViewportReviewCard] = Field(default_factory=list)
    evidence_stream: list[FirstViewportEvidenceCard] = Field(default_factory=list)
    launchpad: FirstViewportLaunchpad
    pipeline_run: PipelineRunProjection = Field(default_factory=PipelineRunProjection)


def build_first_viewport_presentation(
    workbench: TaskWorkbench,
    *,
    root: Path | None = None,
) -> FirstViewportPresentation:
    """Build renderable first-viewport slices from durable control-room state."""
    task_lookup = {task.id: task for task in workbench.tasks}
    active_tasks = [task for task in workbench.tasks if task.lane != "closed"]
    sorted_active_tasks = sorted(
        active_tasks,
        key=lambda task: (LANE_RANK.get(task.lane, 9), _reverse_task_id_sort(task.id)),
    )
    selected_task_id = workbench.focus_task_id or (sorted_active_tasks[0].id if sorted_active_tasks else None)
    switcher_tasks = sorted_active_tasks or workbench.tasks[:6]
    selected_task = task_lookup.get(selected_task_id or "")
    primary = _primary_control(selected_task) if selected_task else None
    brainstorm, pipeline = _brainstorm_and_pipeline(root)

    return FirstViewportPresentation(
        active_task_count=workbench.counts.active_task_count,
        total_task_count=workbench.counts.total_tasks,
        brainstorm=brainstorm,
        pipeline=pipeline,
        next_task=_next_task(selected_task, primary),
        worker_lanes=[_task_card(task) for task in sorted_active_tasks],
        review_queue=[
            FirstViewportReviewCard(
                task_id=item.task_id,
                title=item.title,
                lane=item.lane,
                priority=item.priority,
                reason=item.reason,
                action_label=_action_label(task_lookup.get(item.task_id)),
                command=item.command,
                next_safe_action=item.command,
                evidence_paths=item.evidence_paths,
                review_state=item.review_state,
                review_score=item.review_score,
                operator_summary=item.operator_summary,
                blockers=item.blockers,
                changed_files=item.changed_files,
                evidence_count=item.evidence_count,
            )
            for item in workbench.review_queue
        ],
        evidence_stream=[_evidence_card(item, task_lookup) for item in workbench.evidence_stream],
        launchpad=FirstViewportLaunchpad(
            selected_task_id=selected_task_id,
            active_task_ids=[task.id for task in active_tasks],
            switcher_task_ids=[task.id for task in switcher_tasks[:6]],
            command=primary.command if primary else selected_task.next_action.command if selected_task else None,
            action_label=_action_label(selected_task),
            reason=selected_task.next_action.reason if selected_task else None,
        ),
        pipeline_run=PipelineRunProjection(),
    )


def _brainstorm_and_pipeline(root: Path | None) -> tuple[FirstViewportBrainstorm, FirstViewportPipeline]:
    if root is None:
        return FirstViewportBrainstorm(), FirstViewportPipeline()
    session_dir = _latest_brainstorm_session(root)
    if session_dir is None:
        return FirstViewportBrainstorm(), FirstViewportPipeline()

    records = _read_transcript(session_dir / "transcript.jsonl")
    detail = load_brainstorm_pipeline_detail(root, session_id=session_dir.name, records=records)
    return _brainstorm(root, session_dir, records, detail), _pipeline(detail)


def _latest_brainstorm_session(root: Path) -> Path | None:
    sessions_dir = root.resolve() / ".devflow" / "brainstorms"
    if not sessions_dir.exists():
        return None
    candidates = [
        path
        for path in sessions_dir.iterdir()
        if path.is_dir() and ((path / "transcript.jsonl").exists() or (path / "pipeline.json").exists())
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def _brainstorm(
    root: Path,
    session_dir: Path,
    records: list[dict[str, Any]],
    detail: BrainstormPipelineDetail,
) -> FirstViewportBrainstorm:
    latest = records[-1] if records else {}
    transcript = session_dir / "transcript.jsonl"
    status = "active" if records and not detail.has_implementation else "task_ready" if detail.has_implementation else "empty"
    latest_message = str(latest.get("content") or "").strip()
    return FirstViewportBrainstorm(
        session_id=session_dir.name,
        status=status,
        message_count=len(records),
        transcript_path=relative_path(root, transcript) if transcript.exists() else None,
        latest_message=latest_message[:180],
        latest_message_at=str(latest.get("created_at") or "") or None,
        next_action_label=detail.next_step_label,
    )


def _pipeline(detail: BrainstormPipelineDetail) -> FirstViewportPipeline:
    stages = [_pipeline_stage(stage) for stage in detail.stages]
    first_incomplete = next((stage for stage in stages if not stage.complete), None)
    primary_stage = first_incomplete if first_incomplete and first_incomplete.id != "brainstorm" else None
    for stage in stages:
        stage.active = bool(first_incomplete and stage.id == first_incomplete.id)
        stage.locked = not stage.complete and not stage.active

    return FirstViewportPipeline(
        session_id=detail.session_id,
        status=detail.status,
        stages=stages,
        first_incomplete_stage_id=first_incomplete.id if first_incomplete else None,
        primary_stage_id=primary_stage.id if primary_stage else None,
        primary_action_label=_pipeline_primary_action_label(primary_stage, stages),
        next_step_label=detail.next_step_label,
        operator_summary=detail.operator_summary,
    )


def _pipeline_stage(stage: BrainstormPipelineStage) -> FirstViewportPipelineStage:
    complete = stage.status.lower() in PIPELINE_COMPLETE_STATES
    return FirstViewportPipelineStage(
        id=stage.id,
        label=stage.label,
        status=stage.status,
        artifact_path=stage.artifact_path,
        evidence_paths=stage.evidence_paths,
        worker_label=stage.worker_label,
        next_action=stage.next_action,
        source=stage.source,
        complete=complete,
        action_label=PIPELINE_STAGE_ACTION_LABELS.get(stage.id, "Review ->"),
    )


def _pipeline_primary_action_label(
    primary_stage: FirstViewportPipelineStage | None,
    stages: list[FirstViewportPipelineStage],
) -> str:
    if primary_stage is not None:
        return PIPELINE_STAGE_ACTION_LABELS.get(primary_stage.id, "Review ->")
    first_incomplete = next((stage for stage in stages if not stage.complete), None)
    if first_incomplete and first_incomplete.id == "brainstorm":
        return "Start Brainstorm"
    task_exists = any(stage.id == "task" and stage.status for stage in stages)
    return "View Tasks" if task_exists else "Review ->"


def _task_card(task: TaskWorkbenchTask) -> FirstViewportTaskCard:
    primary = _primary_control(task)
    latest_event = task.detail.recent_events[-1] if task.detail.recent_events else None
    return FirstViewportTaskCard(
        task_id=task.id,
        title=task.title,
        lane=task.lane,
        display_status=task.display_status,
        tone=_status_tone(task.lane),
        worker_model_label=task.worker_model_label,
        verification_status=task.verification_status or "not_run",
        latest=task.latest,
        action_label=_action_label(task),
        command=primary.command if primary else task.next_action.command,
        next_safe_action=_task_next_safe_action(task, primary),
        latest_event=_event_card(latest_event),
        lock_status=task.lock_status,
    )


def _next_task(
    task: TaskWorkbenchTask | None,
    primary: TaskWorkbenchControl | None,
) -> FirstViewportNextTask | None:
    if task is None:
        return None
    return FirstViewportNextTask(
        task_id=task.id,
        title=task.title,
        lane=task.lane,
        display_status=task.display_status,
        worker_model_label=task.worker_model_label,
        verification_status=task.verification_status or "not_run",
        latest=task.latest,
        definition_of_done=task.definition_of_done,
        action_label=_action_label(task),
        command=primary.command if primary else task.next_action.command,
        reason=task.next_action.reason,
        evidence_paths=task.evidence_paths or task.detail.evidence_paths,
        lock_status=task.lock_status,
    )


def _task_next_safe_action(
    task: TaskWorkbenchTask | None,
    primary: TaskWorkbenchControl | None,
) -> str | None:
    if task is None:
        return None
    return task.next_safe_action or (primary.command if primary else None) or task.next_action.command


def _evidence_card(
    item: TaskWorkbenchEvidencePointer,
    task_lookup: dict[str, TaskWorkbenchTask],
) -> FirstViewportEvidenceCard:
    path = item.path or item.verification_log_path or item.result_path or item.log_path
    command = item.command or item.verification_command
    kind = item.kind or (
        "verification"
        if item.verification_log_path
        else "result"
        if item.result_path
        else "worker log"
        if item.log_path
        else "evidence"
    )
    task = task_lookup.get(item.task_id)
    timestamp = item.timestamp or (_latest_event(task).timestamp if task and _latest_event(task) else None)
    return FirstViewportEvidenceCard(
        task_id=item.task_id,
        kind=kind,
        text=item.text or command or path or f"task {item.task_id}",
        path=path,
        command=command,
        timestamp=timestamp,
        label=kind,
    )


def _event_card(event: TaskWorkbenchTaskEvent | None) -> FirstViewportLatestEvent | None:
    if event is None:
        return None
    return FirstViewportLatestEvent(
        timestamp=event.timestamp,
        event=event.event,
        summary=event.summary,
    )


def _latest_event(task: TaskWorkbenchTask | None) -> TaskWorkbenchTaskEvent | None:
    if not task or not task.detail.recent_events:
        return None
    return task.detail.recent_events[-1]


def _primary_control(task: TaskWorkbenchTask | None) -> TaskWorkbenchControl | None:
    if task is None:
        return None
    controls = [control for control in task.controls if control.enabled]
    next_command = task.next_action.command or ""
    if next_command:
        for control in controls:
            if control.command == next_command:
                return control
    for intent in PRIMARY_INTENTS:
        for control in controls:
            if control.intent == intent:
                return control
    return controls[0] if controls else None


def _action_label(task: TaskWorkbenchTask | None) -> str:
    primary = _primary_control(task)
    if primary:
        return primary.label
    if task and task.next_action.label:
        return task.next_action.label
    return "Inspect task"


def _status_tone(lane: str) -> str:
    if lane in {"failed", "blocked"}:
        return "bad"
    if lane in {"needs_verification", "needs_review", "running"}:
        return "warn"
    if lane == "ready_to_promote":
        return "good"
    return "neutral"


def _reverse_task_id_sort(task_id: str) -> tuple[int, int | str]:
    parts = task_id.rsplit("-", 1)
    if len(parts) == 2 and parts[1].isdigit():
        return (0, -int(parts[1]))
    return (1, task_id)


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
