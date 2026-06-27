from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from devflow.control_room.browser_task_capabilities import (
    build_browser_task_capability,
    intent_for_command,
    scope_task_command,
)
from devflow.control_room.dashboard import (
    DashboardHealth,
    DashboardNextAction,
    collect_dashboard_state,
    collect_multi_project_dashboard_state,
)
from devflow.control_room.agent_catalog import build_agent_catalog
from devflow.control_room.freshness import FreshnessReport, run_freshness_loop
from devflow.control_room.idea_greenhouse_projection import (
    OperatingLayerIdeaGreenhouse,
    build_idea_greenhouse,
)
from devflow.control_room.local_model_inventory import build_local_model_inventory
from devflow.control_room.local_model_runtime_lock import list_local_model_runtime_status
from devflow.control_room.operator_readiness import OperatorReadinessSnapshot
from devflow.control_room.paths import goals_dir, relative_path
from devflow.control_room.project_registry import ProjectRegistryError, load_project_metadata
from devflow.control_room.question_resume import QuestionSnapshot, build_question_snapshot
from devflow.control_room.scheduler_projection import SchedulerSnapshot, build_scheduler_snapshot
from devflow.control_room.serial_local_agent_run import serial_local_agent_run_snapshot
from devflow.control_room.status_projection import TaskStatusProjection
from devflow.control_room.operating_layer_first_viewport import (
    FirstViewportPresentation,
    build_first_viewport_presentation,
)
from devflow.control_room.task_workbench import (
    TaskWorkbenchEvidencePointer,
    TaskWorkbenchGateReceipt,
    TaskWorkbenchLane,
    TaskWorkbenchPromotionCandidate,
    TaskWorkbenchReviewLoop,
    TaskWorkbenchTask,
    TaskWorkbenchWorkerActivity,
    build_task_workbench,
)


OPERATING_LAYER_SCHEMA_VERSION = 1
DECISION_INBOX_KINDS = {"question", "blocked_task", "task_attention", "human_decision"}


class OperatingLayerProject(BaseModel):
    root: str
    project_id: str | None = None
    branch: str | None = None
    working_tree: str | None = None
    context_loaded: bool | None = None


class OperatingLayerAction(BaseModel):
    label: str
    command: str
    scope: str
    safety_class: str
    requires_human_approval: bool
    supervisor_may_auto_run: bool
    intent: str | None = None
    required_inputs: list[str] = Field(default_factory=list)
    reason: str | None = None


class OperatingLayerGoal(BaseModel):
    goal_id: str
    title: str
    goal_state: str
    lifecycle: str = "missing"
    lifecycle_reason: str = ""
    loop_state: str
    total_slices: int
    active_task_count: int
    completed_slice_count: int
    ready_parallel_lane_count: int
    ready_parallel_batch_count: int
    ready_worker_batch_count: int
    ready_verification_batch_count: int
    blocked_lane_count: int
    next_action: str


class OperatingLayerQuestion(BaseModel):
    question_id: str
    task_id: str
    title: str
    question: str
    command: str


class OperatingLayerInboxItem(BaseModel):
    id: str
    kind: str
    priority: int
    scope: str
    title: str
    message: str
    task_id: str | None = None
    goal_id: str | None = None
    path: str | None = None
    command: str | None = None
    action: OperatingLayerAction | None = None


class OperatingLayerFreshness(BaseModel):
    status: str
    snapshot_path: str
    stale_count: int
    needs_human_decision_count: int
    next_action: str


class OperatingLayerSpecSlice(BaseModel):
    slice_id: str
    title: str
    state: str
    risk: str | None = None
    execution_mode: str | None = None
    parallel_safe: bool | None = None
    linked_task_ids: list[str] = Field(default_factory=list)


class OperatingLayerSpecReference(BaseModel):
    path: str
    kind: str
    title: str
    source: str
    status: str


class OperatingLayerSpecBoardGoal(BaseModel):
    goal_id: str
    title: str
    state: str
    spec_path: str
    slice_count: int
    slices: list[OperatingLayerSpecSlice] = Field(default_factory=list)
    references: list[OperatingLayerSpecReference] = Field(default_factory=list)


class OperatingLayerGoalBoardLane(BaseModel):
    slice_id: str
    title: str
    lane_state: str
    recommendation: str
    command: str | None = None
    actions: list[OperatingLayerAction] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    shared_files: list[str] = Field(default_factory=list)
    linked_task_ids: list[str] = Field(default_factory=list)
    parallel_safe: bool
    risk: str
    execution_mode: str


class OperatingLayerGoalBoardBatch(BaseModel):
    batch_id: str
    kind: str
    lane_ids: list[str] = Field(default_factory=list)
    task_ids: list[str] = Field(default_factory=list)
    command_count: int
    commands: list[str] = Field(default_factory=list)
    actions: list[OperatingLayerAction] = Field(default_factory=list)
    shared_files: list[str] = Field(default_factory=list)
    verification_scope: str | None = None
    reason: str


class OperatingLayerGoalBoardGoal(BaseModel):
    goal_id: str
    title: str
    goal_state: str
    lifecycle: str = "missing"
    lifecycle_reason: str = ""
    loop_state: str
    total_slices: int
    completed_slice_count: int
    active_task_count: int
    blocked_lane_count: int
    ready_parallel_lane_count: int
    ready_parallel_batch_count: int
    ready_worker_batch_count: int
    ready_verification_batch_count: int
    next_action: str
    actions: list[OperatingLayerAction] = Field(default_factory=list)
    lanes: list[OperatingLayerGoalBoardLane] = Field(default_factory=list)
    blocked_lanes: list[OperatingLayerGoalBoardLane] = Field(default_factory=list)
    ready_lanes: list[OperatingLayerGoalBoardLane] = Field(default_factory=list)
    parallel_batches: list[OperatingLayerGoalBoardBatch] = Field(default_factory=list)
    worker_batches: list[OperatingLayerGoalBoardBatch] = Field(default_factory=list)
    verification_batches: list[OperatingLayerGoalBoardBatch] = Field(default_factory=list)


class OperatingLayerProjectSummary(BaseModel):
    project_id: str
    name: str
    path: str
    status: str
    path_status: str
    source_control_mode: str
    branch: str | None = None
    working_tree: str | None = None
    total_tasks: int = 0
    active_tasks: int = 0
    needs_verification: int = 0
    ready_to_promote: int = 0
    detail: str | None = None
    next_action: str


class OperatingLayerMultiProject(BaseModel):
    registry_path: str
    projects_root: str
    total_projects: int
    active_projects: int
    missing_projects: int
    total_tasks: int
    active_tasks: int
    needs_verification: int
    ready_to_promote: int
    projects: list[OperatingLayerProjectSummary] = Field(default_factory=list)


class OperatingLayerMissionFeedItem(BaseModel):
    id: str
    tone: str
    label: str
    title: str
    detail: str
    command: str | None = None
    task_id: str | None = None
    goal_id: str | None = None
    timestamp: str | None = None


class OperatingLayerScheduler(BaseModel):
    status: str
    counts: dict[str, int] = Field(default_factory=dict)
    max_parallel_recommendation: int
    next_safe_action: str
    stale_tasks: list[str] = Field(default_factory=list)
    retry_candidates: list[str] = Field(default_factory=list)
    batch_count: int = 0


class OperatingLayerSnapshot(BaseModel):
    schema_version: int = OPERATING_LAYER_SCHEMA_VERSION
    generated_at: str
    project: OperatingLayerProject
    health: DashboardHealth
    next_action: DashboardNextAction
    goals: list[OperatingLayerGoal] = Field(default_factory=list)
    focus_goal_id: str | None = None
    focus_task_id: str | None = None
    lanes: list[TaskWorkbenchLane] = Field(default_factory=list)
    tasks: list[TaskWorkbenchTask] = Field(default_factory=list)
    first_viewport: FirstViewportPresentation
    questions: list[OperatingLayerQuestion] = Field(default_factory=list)
    inbox: list[OperatingLayerInboxItem] = Field(default_factory=list)
    promotion_desk: list[TaskWorkbenchPromotionCandidate] = Field(default_factory=list)
    evidence: list[TaskWorkbenchEvidencePointer] = Field(default_factory=list)
    freshness: OperatingLayerFreshness | None = None
    goal_board: list[OperatingLayerGoalBoardGoal] = Field(default_factory=list)
    spec_board: list[OperatingLayerSpecBoardGoal] = Field(default_factory=list)
    gate_receipts: list[TaskWorkbenchGateReceipt] = Field(default_factory=list)
    multi_project: OperatingLayerMultiProject | None = None
    worker_activity: list[TaskWorkbenchWorkerActivity] = Field(default_factory=list)
    mission_feed: list[OperatingLayerMissionFeedItem] = Field(default_factory=list)
    review_loop: TaskWorkbenchReviewLoop
    scheduler: OperatingLayerScheduler | None = None
    idea_greenhouse: OperatingLayerIdeaGreenhouse | None = None
    operator_readiness: OperatorReadinessSnapshot | None = None
    agent_catalog: dict[str, Any] = Field(default_factory=dict)
    local_model_inventory: dict[str, Any] = Field(default_factory=dict)
    local_model_runtime: dict[str, Any] = Field(default_factory=dict)
    serial_local_agent_run: dict[str, Any] = Field(default_factory=dict)
    action_rail: list[OperatingLayerAction] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def build_operating_layer_snapshot(repo_root: Path | None = None, *, project_id: str | None = None) -> OperatingLayerSnapshot:
    root = (repo_root or Path.cwd()).resolve()
    dashboard = collect_dashboard_state(root)
    warnings: list[str] = []
    project_id = project_id or _project_id(root, warnings)
    freshness = _try_freshness(root, warnings)
    scheduler = _try_scheduler(root, warnings)
    question_snapshot = build_question_snapshot(root)
    task_workbench = build_task_workbench(root, project_id=project_id, projections=dashboard.tasks)
    warnings.extend(task_workbench.warnings)
    focus_goal_id = dashboard.goals.focus_goal.goal_id if dashboard.goals and dashboard.goals.focus_goal else None
    questions = _questions(question_snapshot, dashboard.tasks)
    inbox = _inbox_items(dashboard.tasks, freshness, question_snapshot=question_snapshot, project_id=project_id)
    goal_board = _goal_board(root, freshness, project_id=project_id)
    idea_greenhouse = build_idea_greenhouse(root, warnings)

    dashboard_next_action = DashboardNextAction(**dashboard.next_action.model_dump())
    if dashboard_next_action.command:
        dashboard_next_action.command = scope_task_command(dashboard_next_action.command, project_id)
    agent_catalog = _agent_catalog_card(root, warnings)

    return OperatingLayerSnapshot(
        generated_at=datetime.now(timezone.utc).isoformat(),
        project=OperatingLayerProject(**dashboard.project.model_dump(), project_id=project_id),
        health=dashboard.health,
        next_action=dashboard_next_action,
        goals=_goal_cards(root, freshness),
        focus_goal_id=focus_goal_id,
        focus_task_id=task_workbench.focus_task_id,
        lanes=task_workbench.lanes,
        tasks=task_workbench.tasks,
        first_viewport=build_first_viewport_presentation(task_workbench, root=root),
        questions=questions,
        inbox=inbox,
        promotion_desk=task_workbench.promotion_candidates,
        evidence=task_workbench.evidence_stream,
        freshness=_freshness_card(freshness),
        goal_board=goal_board,
        spec_board=_spec_board(root, freshness),
        gate_receipts=task_workbench.gate_receipts,
        multi_project=_multi_project_card(warnings),
        worker_activity=task_workbench.worker_activity,
        mission_feed=_mission_feed(
            task_workbench.tasks,
            inbox=inbox,
            questions=questions,
            promotion_desk=task_workbench.promotion_candidates,
            gate_receipts=task_workbench.gate_receipts,
            evidence=task_workbench.evidence_stream,
            goal_board=goal_board,
            focus_goal_id=focus_goal_id,
        ),
        review_loop=_review_loop_with_inbox_pressure(task_workbench.review_loop, inbox=inbox),
        scheduler=_scheduler_card(scheduler),
        idea_greenhouse=idea_greenhouse,
        operator_readiness=dashboard.operator_readiness,
        agent_catalog=agent_catalog,
        local_model_inventory=build_local_model_inventory(agent_catalog),
        local_model_runtime=list_local_model_runtime_status(root),
        serial_local_agent_run=_serial_local_agent_run_card(root, warnings),
        action_rail=_project_actions(project_id),
        warnings=warnings,
    )


def render_operating_layer_snapshot_json(repo_root: Path | None = None, *, project_id: str | None = None) -> str:
    snapshot = build_operating_layer_snapshot(repo_root, project_id=project_id)
    return json.dumps(snapshot.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"


def _review_loop_with_inbox_pressure(
    review_loop: TaskWorkbenchReviewLoop,
    *,
    inbox: list[OperatingLayerInboxItem],
) -> TaskWorkbenchReviewLoop:
    payload = review_loop.model_dump()
    blocked_decisions = [item for item in inbox if item.kind in DECISION_INBOX_KINDS]
    if blocked_decisions:
        decision_count = len(blocked_decisions)
        payload.update(
            status="needs_human_decision",
            headline=(
                f"{decision_count} decision item{'s' if decision_count != 1 else ''} "
                f"{'need' if decision_count != 1 else 'needs'} attention"
            ),
            blocked_decision_count=decision_count,
        )
        command = next((item.command for item in blocked_decisions if item.command), None)
        if command:
            payload["next_safe_action"] = command
    return TaskWorkbenchReviewLoop(**payload)


def _try_freshness(root: Path, warnings: list[str]) -> FreshnessReport | None:
    try:
        return run_freshness_loop(root, write_snapshot=False)
    except Exception as exc:  # pragma: no cover - defensive projection boundary
        warnings.append(f"freshness unavailable: {exc}")
        return None


def _try_scheduler(root: Path, warnings: list[str]) -> SchedulerSnapshot | None:
    try:
        return build_scheduler_snapshot(root)
    except Exception as exc:  # pragma: no cover - defensive projection boundary
        warnings.append(f"scheduler unavailable: {exc}")
        return None


def _scheduler_card(snapshot: SchedulerSnapshot | None) -> OperatingLayerScheduler | None:
    if snapshot is None:
        return None
    return OperatingLayerScheduler(
        status=snapshot.status,
        counts=snapshot.counts,
        max_parallel_recommendation=snapshot.max_parallel_recommendation,
        next_safe_action=snapshot.next_safe_action,
        stale_tasks=snapshot.stale_tasks,
        retry_candidates=snapshot.retry_candidates,
        batch_count=len(snapshot.batches),
    )


def _agent_catalog_card(root: Path, warnings: list[str]) -> dict[str, Any]:
    try:
        return build_agent_catalog(root)
    except Exception as exc:  # pragma: no cover - defensive dashboard projection
        warnings.append(f"agent catalog unavailable: {exc}")
        return {
            "schema_version": 1,
            "providers": [],
            "profiles": [],
            "local_ollama": {"status": "unavailable", "error": str(exc), "installed_models": [], "unregistered_models": []},
            "actions": [],
        }


def _serial_local_agent_run_card(root: Path, warnings: list[str]) -> dict[str, Any]:
    try:
        return serial_local_agent_run_snapshot(root)
    except Exception as exc:  # pragma: no cover - defensive dashboard projection
        warnings.append(f"serial local-agent run snapshot unavailable: {exc}")
        return {
            "schema_version": 1,
            "status": "unavailable",
            "run_state": "unavailable",
            "verification_status": "unknown",
            "status_source": "projection_error",
            "read_only": True,
            "latest_run": None,
            "run_count": 0,
            "runs": [],
            "browser_actions": [],
            "next_safe_action": "Inspect .devflow/local-agent-runs manually before launching local workers.",
            "error": str(exc),
        }


def _goal_cards(root: Path, freshness: FreshnessReport | None) -> list[OperatingLayerGoal]:
    if not freshness:
        return []
    goals: list[OperatingLayerGoal] = []
    for goal in freshness.goal_loop:
        lifecycle, lifecycle_reason = _goal_board_lifecycle(root, goal.goal_id, fallback=goal.goal_state)
        goals.append(
            OperatingLayerGoal(
                goal_id=goal.goal_id,
                title=goal.title,
                goal_state=goal.goal_state,
                lifecycle=lifecycle,
                lifecycle_reason=lifecycle_reason,
                loop_state=goal.loop_state,
                total_slices=goal.total_slices,
                active_task_count=goal.active_task_count,
                completed_slice_count=goal.completed_slice_count,
                ready_parallel_lane_count=goal.ready_parallel_lane_count,
                ready_parallel_batch_count=goal.ready_parallel_batch_count,
                ready_worker_batch_count=goal.ready_worker_batch_count,
                ready_verification_batch_count=goal.ready_verification_batch_count,
                blocked_lane_count=goal.blocked_lane_count,
                next_action=goal.next_action,
            )
        )
    return goals


def _mission_feed(
    tasks: list[TaskWorkbenchTask],
    *,
    inbox: list[OperatingLayerInboxItem],
    questions: list[OperatingLayerQuestion],
    promotion_desk: list[TaskWorkbenchPromotionCandidate],
    gate_receipts: list[TaskWorkbenchGateReceipt],
    evidence: list[TaskWorkbenchEvidencePointer],
    goal_board: list[OperatingLayerGoalBoardGoal],
    focus_goal_id: str | None,
) -> list[OperatingLayerMissionFeedItem]:
    scoped_ids = set(_mission_feed_task_ids(goal_board, focus_goal_id))
    scoped_tasks = [task for task in tasks if not scoped_ids or task.id in scoped_ids]
    task_titles = {task.id: task.title for task in tasks}
    rows: list[tuple[int, str, int, OperatingLayerMissionFeedItem]] = []

    def in_scope(task_id: str | None) -> bool:
        return not scoped_ids or bool(task_id and task_id in scoped_ids)

    def push(rank: int, item: OperatingLayerMissionFeedItem) -> None:
        if item.task_id and not in_scope(item.task_id):
            return
        rows.append((rank, item.timestamp or "", len(rows), item))

    for item in inbox[:4]:
        command = item.command or (item.action.command if item.action else None)
        push(
            0,
            OperatingLayerMissionFeedItem(
                id=f"inbox:{item.id}",
                tone="urgent",
                label=_plain_feed_kind(item.kind),
                title=item.title or item.task_id or "Human attention",
                detail=item.message or item.scope or "Needs human input",
                command=command,
                task_id=item.task_id,
                goal_id=item.goal_id,
            ),
        )

    for item in questions[:4]:
        push(
            1,
            OperatingLayerMissionFeedItem(
                id=f"question:{item.question_id}",
                tone="urgent",
                label="Question",
                title=item.task_id or "Worker question",
                detail=item.question or "Needs direction",
                command=item.command,
                task_id=item.task_id,
            ),
        )

    for item in promotion_desk[:4]:
        push(
            2,
            OperatingLayerMissionFeedItem(
                id=f"promotion:{item.task_id}",
                tone="ready",
                label="Ready for review",
                title=item.title or item.task_id,
                detail=", ".join(item.blockers) if item.blockers else "Review preview is ready.",
                command=item.command,
                task_id=item.task_id,
            ),
        )

    for gate in sorted(
        (gate for gate in gate_receipts if in_scope(gate.task_id)),
        key=lambda gate: _gate_feed_sort(gate.next_gate),
    )[:4]:
        complete = sum(
            1
            for step in ("intake", "worker_evidence", "verification", "promotion_readiness", "human_decision")
            if getattr(gate, step)
        )
        closed = gate.next_gate == "closed"
        push(
            8 if closed else 3,
            OperatingLayerMissionFeedItem(
                id=f"gate:{gate.task_id}",
                tone="done" if closed else "verify",
                label="Task progress",
                title=task_titles.get(gate.task_id, gate.task_id),
                detail=f"{complete}/5 required steps done. Next: {_plain_gate_name(gate.next_gate)}.",
                command=gate.command or f"devflow task show {gate.task_id}",
                task_id=gate.task_id,
            ),
        )

    task_events = [
        (task, event)
        for task in scoped_tasks
        for event in (task.detail.recent_events if task.detail else [])
    ]
    for task, event in sorted(
        task_events,
        key=lambda pair: pair[1].timestamp or "",
        reverse=True,
    )[:5]:
        push(
            4,
            OperatingLayerMissionFeedItem(
                id=f"event:{task.id}:{event.timestamp or len(rows)}",
                tone="event",
                label="Task update",
                title=task.title or task.id,
                detail=event.summary or event.event or task.latest or task.display_status,
                command=_short_time_label(event.timestamp),
                task_id=task.id,
                timestamp=event.timestamp,
            ),
        )

    for item in [item for item in evidence if in_scope(item.task_id)][:5]:
        detail = item.log_path or item.result_path or item.verification_log_path or item.verification_command
        push(
            5,
            OperatingLayerMissionFeedItem(
                id=f"evidence:{item.task_id}",
                tone="evidence",
                label="Evidence",
                title=task_titles.get(item.task_id, item.task_id),
                detail=detail or "Task evidence recorded.",
                command=item.verification_command or f"devflow task show {item.task_id}",
                task_id=item.task_id,
            ),
        )

    return [row[3] for row in sorted(rows, key=lambda row: (row[0], row[2]))[:6]]


def _gate_feed_sort(next_gate: str) -> int:
    return 9 if next_gate == "closed" else 0


def _mission_feed_task_ids(goal_board: list[OperatingLayerGoalBoardGoal], focus_goal_id: str | None) -> list[str]:
    if not goal_board:
        return []
    goal = next((candidate for candidate in goal_board if candidate.goal_id == focus_goal_id), None) or goal_board[0]
    task_ids: list[str] = []
    for lane in goal.lanes:
        for task_id in lane.linked_task_ids:
            if task_id not in task_ids:
                task_ids.append(task_id)
    return task_ids


def _plain_feed_kind(kind: str) -> str:
    labels = {
        "question": "Question",
        "blocked_task": "Blocked task",
        "task_attention": "Task attention",
        "human_decision": "Human decision",
    }
    return labels.get(kind, _plain_label(kind))


def _plain_gate_name(next_gate: str) -> str:
    labels = {
        "run_worker": "run a worker",
        "verify": "verify the task",
        "verification": "verify the task",
        "promotion_preview": "prepare review preview",
        "promotion_readiness": "prepare review",
        "human_decision": "human review",
        "closed": "closed",
    }
    return labels.get(next_gate, next_gate.replace("_", " "))


def _short_time_label(timestamp: str | None) -> str:
    if not timestamp:
        return "latest"
    value = timestamp.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return timestamp[:19].replace("T", " ")
    return parsed.strftime("%I:%M %p").lstrip("0")


def _plain_label(value: str) -> str:
    parts = [part for part in value.replace("_", "-").split("-") if part]
    return " ".join(part[:1].upper() + part[1:] for part in parts) or "Item"


def _project_id(root: Path, warnings: list[str]) -> str | None:
    try:
        return load_project_metadata(root).project_id
    except ProjectRegistryError:
        return None
    except Exception as exc:  # pragma: no cover - defensive metadata boundary
        warnings.append(f"project metadata unavailable: {exc}")
        return None


def _scrub_quarantined_checkout(value: str) -> str:
    return value.replace("/Users/jewelbait/Desktop/DevFlow", "<quarantined-devflow>")


def _scrub_project_root(root: Path, value: str) -> str:
    scrubbed = _scrub_quarantined_checkout(value)
    candidates = {root.as_posix(), root.resolve().as_posix()}
    for candidate in sorted(candidates, key=len, reverse=True):
        scrubbed = scrubbed.replace(candidate, "<repo-root>")
    return scrubbed


def _questions(
    question_snapshot: QuestionSnapshot,
    projections: list[TaskStatusProjection],
) -> list[OperatingLayerQuestion]:
    task_titles = {projection.task.id: projection.task.title for projection in projections}
    questions: list[OperatingLayerQuestion] = []
    for question in question_snapshot.questions:
        if question.status != "open":
            continue
        questions.append(
            OperatingLayerQuestion(
                question_id=question.question_id,
                task_id=question.task_id,
                title=task_titles.get(question.task_id, question.task_id),
                question=question.question,
                command=f'devflow question answer {question.question_id} --answer "<answer>"',
            )
        )
    return questions


def _inbox_items(
    projections: list[TaskStatusProjection],
    freshness: FreshnessReport | None,
    *,
    question_snapshot: QuestionSnapshot,
    project_id: str | None,
) -> list[OperatingLayerInboxItem]:
    items: list[OperatingLayerInboxItem] = []
    task_titles = {projection.task.id: projection.task.title for projection in projections}
    question_task_ids: set[str] = set()
    for question in question_snapshot.questions:
        if question.status != "open":
            continue
        question_task_ids.add(question.task_id)
        command = f'devflow question answer {question.question_id} --answer "<answer>"'
        items.append(
            OperatingLayerInboxItem(
                id=f"question:{question.question_id}",
                kind="question",
                priority=10,
                scope="task",
                title=f"{question.task_id} - {task_titles.get(question.task_id, question.task_id)}",
                message=question.question,
                task_id=question.task_id,
                path=question.evidence_paths[0] if question.evidence_paths else question.source_path,
                command=command,
                action=_action("Answer question", command, "question"),
            )
        )
    for projection in projections:
        task = projection.task
        if projection.manual_agent_question:
            if task.id in question_task_ids:
                continue
            command = scope_task_command(f"devflow task show {task.id}", project_id)
            items.append(
                OperatingLayerInboxItem(
                    id=f"question:{task.id}",
                    kind="question",
                    priority=10,
                    scope="task",
                    title=f"{task.id} - {task.title}",
                    message=projection.manual_agent_question,
                    task_id=task.id,
                    path=projection.manual_agent_handoff_path,
                    command=command,
                    action=_action("Inspect blocker", command, "task"),
                )
            )
            continue
        if projection.is_blocked:
            command = scope_task_command(f"devflow task show {task.id}", project_id)
            items.append(
                OperatingLayerInboxItem(
                    id=f"blocked:{task.id}",
                    kind="blocked_task",
                    priority=20,
                    scope="task",
                    title=f"{task.id} - {task.title}",
                    message=projection.latest or projection.display_status,
                    task_id=task.id,
                    command=command,
                    action=_action("Inspect blocked task", command, "task"),
                )
            )
            continue
        if projection.failed_verification or projection.is_worker_failed or projection.is_timeout:
            command = projection.dashboard_next_action.command or f"devflow task show {task.id}"
            command = scope_task_command(command, project_id)
            items.append(
                OperatingLayerInboxItem(
                    id=f"attention:{task.id}",
                    kind="task_attention",
                    priority=30,
                    scope="task",
                    title=f"{task.id} - {task.title}",
                    message=projection.dashboard_next_action.reason,
                    task_id=task.id,
                    command=command,
                    action=_action(projection.dashboard_next_action.label, command, "task"),
                )
            )

    if freshness:
        for finding in freshness.findings:
            if finding.severity != "needs_human_decision":
                continue
            command = finding.suggested_action
            items.append(
                OperatingLayerInboxItem(
                    id=f"freshness:{finding.id}",
                    kind="human_decision",
                    priority=15,
                    scope=finding.scope,
                    title=finding.id,
                    message=finding.question or finding.message,
                    path=finding.path,
                    command=command,
                    action=_action("Inspect decision", command, "freshness") if command.startswith("devflow ") else None,
                )
            )

    return sorted(items, key=lambda item: (item.priority, item.id))


def _freshness_card(freshness: FreshnessReport | None) -> OperatingLayerFreshness | None:
    if not freshness:
        return None
    return OperatingLayerFreshness(
        status=freshness.status,
        snapshot_path=freshness.snapshot_path,
        stale_count=freshness.stale_count,
        needs_human_decision_count=freshness.needs_human_decision_count,
        next_action=freshness.next_action,
    )


def _goal_board(
    root: Path,
    freshness: FreshnessReport | None,
    *,
    project_id: str | None,
) -> list[OperatingLayerGoalBoardGoal]:
    if not freshness:
        return []
    goals: list[OperatingLayerGoalBoardGoal] = []
    for goal in freshness.goal_loop:
        lifecycle, lifecycle_reason = _goal_board_lifecycle(root, goal.goal_id, fallback=goal.goal_state)
        goals.append(
            OperatingLayerGoalBoardGoal(
                goal_id=goal.goal_id,
                title=goal.title,
                goal_state=goal.goal_state,
                lifecycle=lifecycle,
                lifecycle_reason=lifecycle_reason,
                loop_state=goal.loop_state,
                total_slices=goal.total_slices,
                completed_slice_count=goal.completed_slice_count,
                active_task_count=goal.active_task_count,
                blocked_lane_count=goal.blocked_lane_count,
                ready_parallel_lane_count=goal.ready_parallel_lane_count,
                ready_parallel_batch_count=goal.ready_parallel_batch_count,
                ready_worker_batch_count=goal.ready_worker_batch_count,
                ready_verification_batch_count=goal.ready_verification_batch_count,
                next_action=_safe_goal_command(root, goal.next_action, project_id),
                actions=_goal_actions(root, goal.goal_id, goal.next_action, project_id=project_id),
                lanes=[_goal_board_lane(root, lane, project_id=project_id) for lane in goal.lanes],
                blocked_lanes=[
                    _goal_board_lane(root, lane, project_id=project_id)
                    for lane in goal.lanes
                    if lane.lane_state in {"blocked", "needs_human_review"}
                ],
                ready_lanes=[
                    _goal_board_lane(root, lane, project_id=project_id)
                    for lane in goal.lanes
                    if lane.lane_state in {"ready_to_create_task", "ready_to_run_or_verify", "repair_or_verify", "ready_to_promote"}
                ],
                parallel_batches=[
                    _goal_board_batch(root, "parallel", batch, project_id=project_id)
                    for batch in goal.parallel_batches
                ],
                worker_batches=[
                    _goal_board_batch(root, "worker", batch, project_id=project_id)
                    for batch in goal.worker_batches
                ],
                verification_batches=[
                    _goal_board_batch(root, "verification", batch, project_id=project_id)
                    for batch in goal.verification_batches
                ],
            )
        )
    return goals


def _goal_board_lifecycle(root: Path, goal_id: str, *, fallback: str) -> tuple[str, str]:
    try:
        from devflow.control_room.goal_projection import build_goal_status_projection

        projection = build_goal_status_projection(root, goal_id)
        return projection.lifecycle, projection.lifecycle_reason
    except Exception:
        if fallback in {"active", "paused", "blocked", "complete", "archived", "missing_lifecycle"}:
            return ("missing" if fallback == "missing_lifecycle" else fallback), ""
        return "unknown", ""


def _goal_board_lane(root: Path, lane: Any, *, project_id: str | None) -> OperatingLayerGoalBoardLane:
    return OperatingLayerGoalBoardLane(
        slice_id=lane.slice_id,
        title=lane.title,
        lane_state=lane.lane_state,
        recommendation=lane.recommendation,
        command=_safe_goal_command(root, lane.command, project_id),
        actions=_lane_actions(root, lane, project_id=project_id),
        blockers=list(lane.blockers),
        shared_files=list(lane.shared_files),
        linked_task_ids=list(lane.linked_task_ids),
        parallel_safe=lane.parallel_safe,
        risk=lane.risk,
        execution_mode=lane.execution_mode,
    )


def _goal_board_batch(
    root: Path,
    kind: str,
    batch: Any,
    *,
    project_id: str | None,
) -> OperatingLayerGoalBoardBatch:
    commands = [_safe_goal_command(root, command, project_id) for command in getattr(batch, "commands", [])]
    return OperatingLayerGoalBoardBatch(
        batch_id=batch.batch_id,
        kind=kind,
        lane_ids=list(batch.lane_ids),
        task_ids=list(getattr(batch, "task_ids", [])),
        command_count=len(commands),
        commands=commands,
        actions=[
            _action(f"{kind.title()} command {index}", command, "goal")
            for index, command in enumerate(commands, start=1)
            if command
        ],
        shared_files=list(batch.shared_files),
        verification_scope=getattr(batch, "verification_scope", None),
        reason=batch.reason,
    )


def _goal_actions(root: Path, goal_id: str, next_action: str | None, *, project_id: str | None) -> list[OperatingLayerAction]:
    commands = [
        ("Goal status", _safe_goal_command(root, f"devflow goal status {goal_id}", project_id)),
    ]
    if next_action and next_action.startswith("devflow "):
        commands.insert(0, ("Next goal action", _safe_goal_command(root, next_action, project_id)))
    return _deduped_actions(commands, "goal")


def _lane_actions(root: Path, lane: Any, *, project_id: str | None) -> list[OperatingLayerAction]:
    commands: list[tuple[str, str | None]] = []
    if lane.command:
        commands.append(("Lane recommendation", _safe_goal_command(root, lane.command, project_id)))
    for task_id in lane.linked_task_ids:
        commands.append(("Show linked task", scope_task_command(f"devflow task show {task_id}", project_id)))
    return _deduped_actions(commands, "goal")


def _deduped_actions(commands: list[tuple[str, str | None]], scope: str) -> list[OperatingLayerAction]:
    seen: set[str] = set()
    actions: list[OperatingLayerAction] = []
    for label, command in commands:
        if not command or command in seen:
            continue
        seen.add(command)
        actions.append(_action(label, command, scope))
    return actions


def _safe_goal_command(root: Path, command: str | None, project_id: str | None) -> str | None:
    if not command:
        return None
    safe = _scrub_project_root(root, command)
    return scope_task_command(safe, project_id)


def _spec_board(root: Path, freshness: FreshnessReport | None) -> list[OperatingLayerSpecBoardGoal]:
    title_by_goal = {goal.goal_id: goal.title for goal in freshness.goal_loop} if freshness else {}
    state_by_goal = {goal.goal_id: goal.loop_state for goal in freshness.goal_loop} if freshness else {}
    board: list[OperatingLayerSpecBoardGoal] = []
    base = goals_dir(root)
    if not base.exists():
        return board
    for goal_path in sorted(path for path in base.iterdir() if path.is_dir()):
        goal_id = goal_path.name
        slices = _goal_slices(goal_path)
        board.append(
            OperatingLayerSpecBoardGoal(
                goal_id=goal_id,
                title=title_by_goal.get(goal_id) or _goal_title(goal_path, goal_id),
                state=state_by_goal.get(goal_id) or "unknown",
                spec_path=relative_path(root, goal_path),
                slice_count=len(slices),
                slices=slices,
                references=_spec_references(root, goal_path),
            )
        )
    return board


def _goal_title(goal_path: Path, fallback: str) -> str:
    goal_md = goal_path / "goal.md"
    if not goal_md.exists():
        return fallback
    for line in goal_md.read_text(encoding="utf-8").splitlines():
        stripped = line.strip("# ").strip()
        if stripped:
            return stripped[:120]
    return fallback


def _goal_slices(goal_path: Path) -> list[OperatingLayerSpecSlice]:
    data = _read_yaml(goal_path / "task-slices.yaml")
    raw_slices = data.get("task_slices") if isinstance(data, dict) else []
    if not isinstance(raw_slices, list):
        return []
    slices: list[OperatingLayerSpecSlice] = []
    for item in raw_slices:
        if not isinstance(item, dict):
            continue
        slice_id = str(item.get("task_id") or item.get("slice_id") or "unknown")
        linked = item.get("linked_task_ids") or item.get("linked_tasks") or []
        if isinstance(linked, str):
            linked = [linked]
        if not isinstance(linked, list):
            linked = []
        slices.append(
            OperatingLayerSpecSlice(
                slice_id=slice_id,
                title=str(item.get("title") or slice_id),
                state=_slice_state(item),
                risk=item.get("risk"),
                execution_mode=item.get("execution_mode"),
                parallel_safe=item.get("parallel_safe"),
                linked_task_ids=[str(value) for value in linked],
            )
        )
    return slices


def _spec_references(root: Path, goal_path: Path) -> list[OperatingLayerSpecReference]:
    references: list[OperatingLayerSpecReference] = []
    references.extend(_goal_context_references(root, goal_path))
    references.extend(_standards_index_references(root))
    references.extend(_architecture_contract_references(root))

    seen: set[str] = set()
    deduped: list[OperatingLayerSpecReference] = []
    for reference in references:
        key = f"{reference.kind}:{reference.path}"
        if key in seen:
            continue
        seen.add(key)
        deduped.append(reference)
    return deduped[:10]


def _goal_context_references(root: Path, goal_path: Path) -> list[OperatingLayerSpecReference]:
    path = goal_path / "context" / "relevant-files.md"
    if not path.exists():
        return []
    references: list[OperatingLayerSpecReference] = []
    for raw_target in _markdown_bullet_targets(path):
        target = _normalize_root_reference_path(root, raw_target)
        references.append(_spec_reference(root, target, "goal_reference", relative_path(root, path)))
    return references


def _standards_index_references(root: Path) -> list[OperatingLayerSpecReference]:
    path = root / ".devflow" / "standards" / "index.yml"
    if not path.exists():
        path = root / ".devflow" / "standards" / "index.yaml"
    if not path.exists():
        path = root / ".devflow" / "standards" / "index.json"
    if not path.exists():
        return []
    data = _read_yaml(path)
    raw_items: Any = data.get("standards") or data.get("references") or data.get("items") or data
    if isinstance(raw_items, dict):
        raw_items = list(raw_items.values())
    if not isinstance(raw_items, list):
        return []
    references: list[OperatingLayerSpecReference] = []
    for item in raw_items:
        if isinstance(item, str):
            target = _normalize_root_reference_path(root, item)
            references.append(_spec_reference(root, target, "standard", relative_path(root, path)))
            continue
        if not isinstance(item, dict):
            continue
        raw_target = item.get("path") or item.get("file") or item.get("href") or item.get("id")
        if not raw_target:
            continue
        target = _normalize_root_reference_path(root, str(raw_target))
        reference = _spec_reference(root, target, str(item.get("kind") or "standard"), relative_path(root, path))
        if item.get("title"):
            reference.title = str(item["title"])[:120]
        references.append(reference)
    return references


def _architecture_contract_references(root: Path) -> list[OperatingLayerSpecReference]:
    path = root / ".devflow" / "layers" / "architecture" / "contracts.md"
    if not path.exists():
        return []
    references: list[OperatingLayerSpecReference] = []
    for raw_target in _markdown_bullet_targets(path):
        target = _normalize_source_relative_reference_path(root, path.parent, raw_target)
        references.append(_spec_reference(root, target, "architecture_contract", relative_path(root, path)))
    return references


def _markdown_bullet_targets(path: Path) -> list[str]:
    targets: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped.startswith("- "):
            continue
        target = stripped[2:].strip()
        markdown_target = _markdown_link_target(target)
        if markdown_target:
            target = markdown_target
        target = target.strip().strip("`")
        if target:
            targets.append(target)
    return targets


def _markdown_link_target(value: str) -> str | None:
    start = value.find("](")
    if start == -1:
        return None
    end = value.find(")", start + 2)
    if end == -1:
        return None
    return value[start + 2 : end].strip()


def _normalize_root_reference_path(root: Path, value: str) -> str:
    if "://" in value:
        return value
    path = Path(value)
    if path.is_absolute():
        try:
            return relative_path(root, path)
        except ValueError:
            return _scrub_project_root(root, path.as_posix())
    return path.as_posix().removeprefix("./")


def _normalize_source_relative_reference_path(root: Path, source_dir: Path, value: str) -> str:
    if "://" in value:
        return value
    path = Path(value)
    if path.is_absolute():
        try:
            return relative_path(root, path)
        except ValueError:
            return _scrub_project_root(root, path.as_posix())
    return relative_path(root, (source_dir / path).resolve())


def _spec_reference(root: Path, path: str, kind: str, source: str) -> OperatingLayerSpecReference:
    return OperatingLayerSpecReference(
        path=path,
        kind=kind,
        title=_reference_title(root, path),
        source=source,
        status=_reference_status(root, path),
    )


def _reference_title(root: Path, path: str) -> str:
    if "://" in path:
        return path
    candidate = root / path
    if candidate.exists() and candidate.is_file() and candidate.suffix == ".md":
        for line in candidate.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                title = stripped.strip("# ").strip()
                if title:
                    return title[:120]
    return Path(path).name


def _reference_status(root: Path, path: str) -> str:
    if "://" in path:
        return "external"
    return "available" if (root / path).exists() else "missing"


def _slice_state(item: dict[str, Any]) -> str:
    if item.get("blocked_by"):
        return "blocked"
    if item.get("promotion_allowed") is True:
        return "ready_for_promotion"
    if item.get("parallel_safe") is True:
        return "parallel_candidate"
    return "planned"


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return loaded if isinstance(loaded, dict) else {}


def _multi_project_card(warnings: list[str]) -> OperatingLayerMultiProject | None:
    try:
        state = collect_multi_project_dashboard_state()
    except Exception as exc:  # pragma: no cover - defensive registry boundary
        warnings.append(f"multi-project registry unavailable: {exc}")
        return None

    return OperatingLayerMultiProject(
        registry_path=state.registry_path,
        projects_root=state.projects_root,
        total_projects=state.total_projects,
        active_projects=state.active_projects,
        missing_projects=state.missing_projects,
        total_tasks=state.total_tasks,
        active_tasks=state.active_tasks,
        needs_verification=state.needs_verification,
        ready_to_promote=state.ready_to_promote,
        projects=[
            OperatingLayerProjectSummary(
                project_id=project.project_id,
                name=project.name,
                path=project.path,
                status=project.status,
                path_status=project.path_status,
                source_control_mode=project.source_control_mode,
                branch=project.branch,
                working_tree=project.working_tree,
                total_tasks=project.total_tasks,
                active_tasks=project.active_tasks,
                needs_verification=project.needs_verification,
                ready_to_promote=project.ready_to_promote,
                detail=project.detail,
                next_action=_project_next_action(project),
            )
            for project in state.projects
        ],
    )


def _project_next_action(project: Any) -> str:
    if project.path_status == "missing":
        return f"devflow project doctor {project.project_id}"
    return f"devflow project status {project.project_id}"


def _project_actions(project_id: str | None) -> list[OperatingLayerAction]:
    commands = [
        ("Project status", f"devflow project status {project_id}" if project_id else "devflow git status", "project"),
        ("Task list", f"devflow task list --project {project_id}" if project_id else "devflow task list", "project"),
        ("Dashboard", "devflow dashboard", "project"),
        ("Status JSON", "devflow status --json", "project"),
    ]
    if project_id:
        commands.append(("Project doctor", f"devflow project doctor {project_id}", "project"))
    return [_action(label, command, scope) for label, command, scope in commands]


def _action(label: str, command: str, scope: str) -> OperatingLayerAction:
    capability = build_browser_task_capability(
        intent_for_command(command),
        label,
        command,
        scope=scope,
    )
    return OperatingLayerAction(
        label=capability.label,
        command=capability.command,
        scope=capability.scope,
        safety_class=capability.safety_class,
        requires_human_approval=capability.requires_human_approval,
        supervisor_may_auto_run=capability.supervisor_may_auto_run,
        intent=capability.intent,
        required_inputs=capability.required_inputs,
        reason=capability.reason,
    )
