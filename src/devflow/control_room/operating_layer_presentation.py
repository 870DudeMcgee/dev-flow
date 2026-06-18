from __future__ import annotations

from pydantic import BaseModel, Field

from devflow.control_room.task_workbench import (
    TaskWorkbench,
    TaskWorkbenchControl,
    TaskWorkbenchEvidencePointer,
    TaskWorkbenchTask,
    TaskWorkbenchTaskEvent,
)


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


class FirstViewportLatestEvent(BaseModel):
    timestamp: str | None = None
    event: str
    summary: str = ""


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
    latest_event: FirstViewportLatestEvent | None = None


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


class FirstViewportPresentation(BaseModel):
    schema_version: int = 1
    active_task_count: int
    total_task_count: int
    worker_lanes: list[FirstViewportTaskCard] = Field(default_factory=list)
    review_queue: list[FirstViewportReviewCard] = Field(default_factory=list)
    evidence_stream: list[FirstViewportEvidenceCard] = Field(default_factory=list)
    launchpad: FirstViewportLaunchpad


def build_first_viewport_presentation(workbench: TaskWorkbench) -> FirstViewportPresentation:
    """Build renderable first-viewport slices from the task workbench."""
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

    return FirstViewportPresentation(
        active_task_count=workbench.counts.active_task_count,
        total_task_count=workbench.counts.total_tasks,
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
    )


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
        latest_event=_event_card(latest_event),
    )


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
