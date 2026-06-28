from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from devflow.control_room.browser_task_capabilities import scope_task_command
from devflow.control_room.dashboard import (
    DashboardHealth,
    DashboardNextAction,
    collect_dashboard_state,
    collect_multi_project_dashboard_state,
)
from devflow.control_room.agent_catalog import build_agent_catalog
from devflow.control_room.freshness import FreshnessReport, run_freshness_loop
from devflow.control_room.goal_spec_projection import (
    OperatingLayerAction,
    OperatingLayerGoalBoardGoal,
    OperatingLayerSpecBoardGoal,
    build_operating_layer_action as _action,
    build_goal_board,
    build_spec_board,
)
from devflow.control_room.idea_greenhouse_projection import (
    OperatingLayerIdeaGreenhouse,
    build_idea_greenhouse,
)
from devflow.control_room.local_model_inventory import build_local_model_inventory
from devflow.control_room.local_model_runtime_lock import list_local_model_runtime_status
from devflow.control_room.operator_readiness import OperatorReadinessSnapshot
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
    goal_board = build_goal_board(root, freshness, project_id=project_id)
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
        goals=_goal_cards(freshness, goal_board),
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
        spec_board=build_spec_board(root, freshness),
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


def _goal_cards(
    freshness: FreshnessReport | None,
    goal_board: list[OperatingLayerGoalBoardGoal],
) -> list[OperatingLayerGoal]:
    if not freshness:
        return []
    lifecycle_by_goal = {goal.goal_id: goal for goal in goal_board}
    goals: list[OperatingLayerGoal] = []
    for goal in freshness.goal_loop:
        board_goal = lifecycle_by_goal.get(goal.goal_id)
        goals.append(
            OperatingLayerGoal(
                goal_id=goal.goal_id,
                title=goal.title,
                goal_state=goal.goal_state,
                lifecycle=board_goal.lifecycle if board_goal else goal.goal_state,
                lifecycle_reason=board_goal.lifecycle_reason if board_goal else "",
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
