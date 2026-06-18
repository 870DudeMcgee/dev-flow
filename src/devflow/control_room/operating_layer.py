from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from devflow.control_room.dashboard import (
    DashboardHealth,
    DashboardNextAction,
    collect_dashboard_state,
    collect_multi_project_dashboard_state,
)
from devflow.control_room.agent_evidence import compact_agent_evidence_summary
from devflow.control_room.agent_onboarding import build_agent_catalog
from devflow.control_room.evidence_review_detail import EvidenceReviewDetail
from devflow.control_room.freshness import FreshnessReport, run_freshness_loop
from devflow.control_room.git_worktree import git_worker_lane_summary
from devflow.control_room.local_worker_lane import local_worker_lane_summary
from devflow.control_room.log_sanitizer import sanitize_log_line
from devflow.control_room.operator_readiness import OperatorReadinessSnapshot
from devflow.control_room.paths import absolute_path, goals_dir, relative_path, task_dir
from devflow.control_room.project_registry import ProjectRegistryError, load_project_metadata
from devflow.control_room.question_resume import QuestionSnapshot, build_question_snapshot
from devflow.control_room.review_readiness import build_review_readiness_projection
from devflow.control_room.scheduler_projection import SchedulerSnapshot, build_scheduler_snapshot
from devflow.control_room.status_projection import TaskStatusProjection
from devflow.control_room.supervisor_surface import classify_supervisor_command
from devflow.control_room.operating_layer_presentation import (
    FirstViewportPresentation,
    build_first_viewport_presentation,
)
from devflow.control_room.task_workbench import build_task_workbench


OPERATING_LAYER_SCHEMA_VERSION = 1


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
    reason: str | None = None


class OperatingLayerTaskControl(BaseModel):
    intent: str
    label: str
    command: str
    scope: str = "task"
    enabled: bool = True
    safety_class: str
    requires_human_approval: bool
    supervisor_may_auto_run: bool
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


class OperatingLayerLane(BaseModel):
    name: str
    label: str
    task_ids: list[str] = Field(default_factory=list)


class OperatingLayerTaskEvent(BaseModel):
    timestamp: str | None = None
    event: str
    summary: str = ""


class OperatingLayerTaskVerification(BaseModel):
    status: str
    task_status: str | None = None
    exit_code: int | None = None
    log_path: str | None = None


class OperatingLayerReviewItem(BaseModel):
    label: str
    value: str


class OperatingLayerTaskDetail(BaseModel):
    events_path: str
    verification_path: str
    recent_events: list[OperatingLayerTaskEvent] = Field(default_factory=list)
    verification: OperatingLayerTaskVerification | None = None
    evidence_paths: list[str] = Field(default_factory=list)
    review_summary: list[OperatingLayerReviewItem] = Field(default_factory=list)
    latest_worker_line: str | None = None
    latest_verification_line: str | None = None
    result_preview: str | None = None
    notes: list[str] = Field(default_factory=list)


class OperatingLayerWorkerLane(BaseModel):
    workspace_mode: str
    worker_id: str
    worker_branch: str
    worktree_path: str
    base_branch: str | None = None
    base_commit: str | None = None
    base_current_commit: str | None = None
    base_stale: bool = False
    origin_base_commit: str | None = None
    origin_base_stale: bool = False
    head_commit: str | None = None
    dirty: bool = False
    verification_status: str = "missing"
    verified_commit: str | None = None
    head_matches_verified: bool = False
    promotion_readiness: str = "unknown"
    conflict_prediction: str = "unknown"
    changed_files: list[str] = Field(default_factory=list)
    readiness_status: str
    readiness_errors: list[str] = Field(default_factory=list)
    readiness_warnings: list[str] = Field(default_factory=list)
    evidence_paths: list[str] = Field(default_factory=list)
    next_safe_action: str


class OperatingLayerLocalWorkerLane(BaseModel):
    lane_type: str
    worker_id: str
    profile_id: str | None = None
    model: str | None = None
    adapter: str | None = None
    permission_mode: str | None = None
    latest_run_id: str | None = None
    latest_status: str | None = None
    patch_candidate: bool = False
    readiness_status: str
    next_safe_action: str
    evidence_paths: list[str] = Field(default_factory=list)


class OperatingLayerTask(BaseModel):
    id: str
    title: str
    definition_of_done: str | None = None
    status: str
    display_status: str
    lane: str
    worker: str
    workspace: str
    verification_status: str
    verification_exit_code: int | None = None
    merge_ready: bool | None = None
    promotion_ready: bool = False
    promotion_blockers: list[str] = Field(default_factory=list)
    latest: str = ""
    log_path: str | None = None
    result_path: str | None = None
    verification_log_path: str | None = None
    next_action: DashboardNextAction
    review_state: str = "not_ready"
    review_score: int = 0
    review_blockers: list[str] = Field(default_factory=list)
    review_next_command: str | None = None
    review_evidence: list[str] = Field(default_factory=list)
    agent_evidence_summary: dict[str, Any] = Field(default_factory=dict)
    worker_lane: OperatingLayerWorkerLane | None = None
    local_worker_lane: OperatingLayerLocalWorkerLane | None = None
    actions: list[OperatingLayerAction] = Field(default_factory=list)
    controls: list[OperatingLayerTaskControl] = Field(default_factory=list)
    review_detail: EvidenceReviewDetail | None = None
    detail: OperatingLayerTaskDetail


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


class OperatingLayerPromotionCandidate(BaseModel):
    task_id: str
    title: str
    command: str
    merge_ready: bool | None
    blockers: list[str] = Field(default_factory=list)


class OperatingLayerEvidencePointer(BaseModel):
    task_id: str
    log_path: str | None = None
    result_path: str | None = None
    verification_log_path: str | None = None
    verification_command: str | None = None
    kind: str = "evidence"
    text: str = ""
    path: str | None = None
    command: str | None = None
    timestamp: str | None = None


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


class OperatingLayerGateReceipt(BaseModel):
    task_id: str
    intake: bool
    worker_evidence: bool
    verification: bool
    promotion_readiness: bool
    human_decision: bool
    next_gate: str
    command: str | None = None


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


class OperatingLayerWorkerActivity(BaseModel):
    worker: str
    code: str
    name: str
    description: str
    state: str
    state_class: str
    tone: str
    task_count: int
    verified_percent: int
    recent_output_count: int
    latest: str
    first_task_id: str | None = None


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


class OperatingLayerReviewLoop(BaseModel):
    status: str
    headline: str
    next_safe_action: str
    browser_allowed_mutations: list[str] = Field(default_factory=list)
    browser_blocked_mutations: list[str] = Field(default_factory=list)
    needs_verification_count: int = 0
    ready_to_promote_count: int = 0
    blocked_decision_count: int = 0
    last_result_retention: str = "browser-session"
    evidence_summary: str = ""


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
    lanes: list[OperatingLayerLane] = Field(default_factory=list)
    tasks: list[OperatingLayerTask] = Field(default_factory=list)
    first_viewport: FirstViewportPresentation
    questions: list[OperatingLayerQuestion] = Field(default_factory=list)
    inbox: list[OperatingLayerInboxItem] = Field(default_factory=list)
    promotion_desk: list[OperatingLayerPromotionCandidate] = Field(default_factory=list)
    evidence: list[OperatingLayerEvidencePointer] = Field(default_factory=list)
    freshness: OperatingLayerFreshness | None = None
    goal_board: list[OperatingLayerGoalBoardGoal] = Field(default_factory=list)
    spec_board: list[OperatingLayerSpecBoardGoal] = Field(default_factory=list)
    gate_receipts: list[OperatingLayerGateReceipt] = Field(default_factory=list)
    multi_project: OperatingLayerMultiProject | None = None
    worker_activity: list[OperatingLayerWorkerActivity] = Field(default_factory=list)
    mission_feed: list[OperatingLayerMissionFeedItem] = Field(default_factory=list)
    review_loop: OperatingLayerReviewLoop
    scheduler: OperatingLayerScheduler | None = None
    operator_readiness: OperatorReadinessSnapshot | None = None
    agent_catalog: dict[str, Any] = Field(default_factory=dict)
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
    tasks = [_operating_task_from_workbench(task) for task in task_workbench.tasks]
    focus_goal_id = dashboard.goals.focus_goal.goal_id if dashboard.goals and dashboard.goals.focus_goal else None
    questions = _questions(question_snapshot, dashboard.tasks)
    inbox = _inbox_items(dashboard.tasks, freshness, question_snapshot=question_snapshot, project_id=project_id)
    promotion_desk = [
        OperatingLayerPromotionCandidate(**candidate.model_dump())
        for candidate in task_workbench.promotion_candidates
    ]
    evidence = [
        OperatingLayerEvidencePointer(**pointer.model_dump())
        for pointer in task_workbench.evidence_stream
    ]
    goal_board = _goal_board(root, freshness, project_id=project_id)
    gate_receipts = [
        OperatingLayerGateReceipt(**receipt.model_dump())
        for receipt in task_workbench.gate_receipts
    ]
    focus_task_id = task_workbench.focus_task_id

    dashboard_next_action = DashboardNextAction(**dashboard.next_action.model_dump())
    if dashboard_next_action.command:
        dashboard_next_action.command = _scope_task_command(dashboard_next_action.command, project_id)

    return OperatingLayerSnapshot(
        generated_at=datetime.now(timezone.utc).isoformat(),
        project=OperatingLayerProject(**dashboard.project.model_dump(), project_id=project_id),
        health=dashboard.health,
        next_action=dashboard_next_action,
        goals=_goal_cards(root, freshness),
        focus_goal_id=focus_goal_id,
        focus_task_id=focus_task_id,
        lanes=[
            OperatingLayerLane(**lane.model_dump())
            for lane in task_workbench.lanes
        ],
        tasks=tasks,
        first_viewport=build_first_viewport_presentation(task_workbench),
        questions=questions,
        inbox=inbox,
        promotion_desk=promotion_desk,
        evidence=evidence,
        freshness=_freshness_card(freshness),
        goal_board=goal_board,
        spec_board=_spec_board(root, freshness),
        gate_receipts=gate_receipts,
        multi_project=_multi_project_card(warnings),
        worker_activity=[
            OperatingLayerWorkerActivity(**activity.model_dump())
            for activity in task_workbench.worker_activity
        ],
        mission_feed=_mission_feed(
            tasks,
            inbox=inbox,
            questions=questions,
            promotion_desk=promotion_desk,
            gate_receipts=gate_receipts,
            evidence=evidence,
            goal_board=goal_board,
            focus_goal_id=focus_goal_id,
        ),
        review_loop=_review_loop_summary(
            tasks,
            inbox=inbox,
            gate_receipts=gate_receipts,
            promotion_desk=promotion_desk,
            next_action=dashboard_next_action,
        ),
        scheduler=_scheduler_card(scheduler),
        operator_readiness=dashboard.operator_readiness,
        agent_catalog=_agent_catalog_card(root, warnings),
        action_rail=_project_actions(project_id),
        warnings=warnings,
    )


def render_operating_layer_snapshot_json(repo_root: Path | None = None, *, project_id: str | None = None) -> str:
    snapshot = build_operating_layer_snapshot(repo_root, project_id=project_id)
    return json.dumps(snapshot.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"


def _operating_task_from_workbench(task: Any) -> OperatingLayerTask:
    payload = task.model_dump()
    for internal_field in ("worker_model_label", "next_safe_action", "evidence_paths"):
        payload.pop(internal_field, None)
    return OperatingLayerTask(**payload)


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


def _focus_task_id(tasks: list[OperatingLayerTask]) -> str | None:
    for lane in ("blocked", "failed", "running", "ready_to_promote", "needs_review", "needs_verification", "new", "idle"):
        for task in tasks:
            if task.lane == lane:
                return task.id
    return None


def _worker_activity(tasks: list[OperatingLayerTask]) -> list[OperatingLayerWorkerActivity]:
    grouped: dict[str, list[OperatingLayerTask]] = {}
    for task in tasks:
        worker = _normalized_worker(task.worker)
        if not worker:
            continue
        grouped.setdefault(worker, []).append(task)

    rows: list[OperatingLayerWorkerActivity] = []
    for worker, worker_tasks in grouped.items():
        profile = _worker_profile(worker)
        open_tasks = [task for task in worker_tasks if task.lane != "closed"]
        verified = [task for task in worker_tasks if _worker_task_verified_or_ready(task)]
        latest_task = next((task for task in open_tasks if task.latest), None) or next(
            (task for task in worker_tasks if task.latest),
            worker_tasks[0],
        )
        state = _worker_state(open_tasks)
        rows.append(
            OperatingLayerWorkerActivity(
                worker=worker,
                code=profile["code"],
                name=profile["name"],
                description=profile["description"],
                state=state,
                state_class=_worker_state_class(state),
                tone=profile["tone"],
                task_count=len(worker_tasks),
                verified_percent=round((len(verified) / len(worker_tasks)) * 100) if worker_tasks else 0,
                recent_output_count=sum(len(task.detail.recent_events) for task in worker_tasks),
                latest=f"{latest_task.id}: {latest_task.latest or latest_task.display_status}",
                first_task_id=(open_tasks[0] if open_tasks else worker_tasks[0]).id if worker_tasks else None,
            )
        )

    return sorted(
        rows,
        key=lambda row: (
            0 if row.state == "Running" else 1 if row.state == "Needs attention" else 2 if row.state == "Waiting" else 3,
            -row.task_count,
            row.worker,
        ),
    )[:6]


def _review_loop_summary(
    tasks: list[OperatingLayerTask],
    *,
    inbox: list[OperatingLayerInboxItem],
    gate_receipts: list[OperatingLayerGateReceipt],
    promotion_desk: list[OperatingLayerPromotionCandidate],
    next_action: DashboardNextAction,
) -> OperatingLayerReviewLoop:
    needs_verification = [task for task in tasks if task.lane == "needs_verification"]
    ready_to_promote = [task for task in tasks if task.lane == "ready_to_promote"]
    blocked_decisions = [
        item for item in inbox if item.kind in {"question", "blocked_task", "task_attention", "human_decision"}
    ]
    verified_count = sum(1 for gate in gate_receipts if gate.verification)
    worker_output_count = sum(1 for gate in gate_receipts if gate.worker_evidence)

    if blocked_decisions:
        status = "needs_human_decision"
        decision_count = len(blocked_decisions)
        headline = (
            f"{decision_count} decision item{'s' if decision_count != 1 else ''} "
            f"{'need' if decision_count != 1 else 'needs'} attention"
        )
    elif ready_to_promote:
        status = "ready_to_promote"
        headline = f"{len(ready_to_promote)} task{'s' if len(ready_to_promote) != 1 else ''} ready for browser approval"
    elif needs_verification:
        status = "needs_verification"
        headline = f"{len(needs_verification)} task{'s' if len(needs_verification) != 1 else ''} need{'s' if len(needs_verification) == 1 else ''} verification"
    else:
        status = "watching"
        headline = "No browser approval items are waiting"

    promotion_command = promotion_desk[0].command if promotion_desk else None
    blocked_command = blocked_decisions[0].command if status == "needs_human_decision" and blocked_decisions else None
    ready_command = ready_to_promote[0].next_action.command if ready_to_promote else None
    verification_command = needs_verification[0].next_action.command if needs_verification else None
    command = blocked_command
    if not command and status == "ready_to_promote":
        command = promotion_command or ready_command
    if not command and status == "needs_verification":
        command = verification_command
    if not command:
        command = next_action.command or promotion_command or ready_command or verification_command or "devflow dashboard"

    return OperatingLayerReviewLoop(
        status=status,
        headline=headline,
        next_safe_action=command,
        browser_allowed_mutations=[
            "idea capture",
            "task creation",
            "shell worker execution",
            "task verification",
            "task promotion",
        ],
        browser_blocked_mutations=[
            "non-shell worker execution",
            "patch application",
            "git publication",
            "provider-backed model calls",
            "autonomous routing execution",
        ],
        needs_verification_count=len(needs_verification),
        ready_to_promote_count=len(ready_to_promote),
        blocked_decision_count=len(blocked_decisions),
        last_result_retention="browser-session",
        evidence_summary=(
            f"{worker_output_count} task{'s' if worker_output_count != 1 else ''} "
            f"{'have' if worker_output_count != 1 else 'has'} worker output; "
            f"{verified_count} task{'s' if verified_count != 1 else ''} "
            f"{'have' if verified_count != 1 else 'has'} passed verification; "
            f"{len(ready_to_promote)} task{'s' if len(ready_to_promote) != 1 else ''} "
            f"{'are' if len(ready_to_promote) != 1 else 'is'} ready for promotion."
        ),
    )


def _mission_feed(
    tasks: list[OperatingLayerTask],
    *,
    inbox: list[OperatingLayerInboxItem],
    questions: list[OperatingLayerQuestion],
    promotion_desk: list[OperatingLayerPromotionCandidate],
    gate_receipts: list[OperatingLayerGateReceipt],
    evidence: list[OperatingLayerEvidencePointer],
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
    return labels.get(kind, _plain_worker_name(kind))


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


def _normalized_worker(worker: str) -> str | None:
    value = str(worker or "").strip()
    if not value or value in {"unassigned", "unknown"}:
        return None
    return value


def _worker_profile(worker: str) -> dict[str, str]:
    profiles = {
        "shell": {
            "code": "SH",
            "name": "Shell worker",
            "description": "Runs the command DevFlow was given inside the task workspace.",
            "tone": "violet",
        },
        "devflow-manual-codex-worker": {
            "code": "CDX",
            "name": "Manual Codex worker",
            "description": "A human-launched Codex handoff that writes task evidence back to DevFlow.",
            "tone": "blue",
        },
        "qwopus-implementer": {
            "code": "QWO",
            "name": "Qwopus implementer",
            "description": "Local Ollama worker evidence for implementation proposals.",
            "tone": "mint",
        },
        "qwen-planner": {
            "code": "QWN",
            "name": "Local Qwen planner",
            "description": "Local Ollama planning output captured as evidence.",
            "tone": "gold",
        },
        "gemma-reviewer": {
            "code": "GEM",
            "name": "Gemma reviewer",
            "description": "Local Ollama review output captured as evidence.",
            "tone": "pink",
        },
    }
    return profiles.get(
        worker,
        {
            "code": _worker_code(worker),
            "name": _plain_worker_name(worker),
            "description": "DevFlow worker evidence grouped by the worker id recorded on tasks.",
            "tone": "blue",
        },
    )


def _worker_code(worker: str) -> str:
    parts = [part for part in "".join(char if char.isalnum() else " " for char in worker).split() if part]
    return "".join(part[0] for part in parts).upper()[:3] or "WRK"


def _plain_worker_name(worker: str) -> str:
    parts = [part for part in worker.replace("_", "-").split("-") if part]
    return " ".join(part[:1].upper() + part[1:] for part in parts) or "Worker"


def _worker_state(open_tasks: list[OperatingLayerTask]) -> str:
    if any(task.lane == "running" for task in open_tasks):
        return "Running"
    if any(task.lane in {"blocked", "failed"} or _worker_task_failed(task) for task in open_tasks):
        return "Needs attention"
    if any(task.lane in {"new", "needs_verification", "ready_to_promote", "idle"} for task in open_tasks):
        return "Waiting"
    return "Recorded"


def _worker_state_class(state: str) -> str:
    if state == "Running":
        return "active"
    if state == "Needs attention":
        return "blocked"
    if state == "Recorded":
        return "complete"
    return "idle"


def _worker_task_failed(task: OperatingLayerTask) -> bool:
    return "fail" in task.verification_status.lower() or "failed" in task.display_status.lower()


def _worker_task_verified_or_ready(task: OperatingLayerTask) -> bool:
    return (
        "pass" in task.verification_status.lower()
        or bool(task.promotion_ready or task.merge_ready)
        or task.lane == "closed"
    )


def _project_id(root: Path, warnings: list[str]) -> str | None:
    try:
        return load_project_metadata(root).project_id
    except ProjectRegistryError:
        return None
    except Exception as exc:  # pragma: no cover - defensive metadata boundary
        warnings.append(f"project metadata unavailable: {exc}")
        return None


def _task_card(root: Path, projection: TaskStatusProjection, *, project_id: str | None) -> OperatingLayerTask:
    task = projection.task
    next_action = DashboardNextAction(**projection.dashboard_next_action.model_dump())
    if next_action.command:
        next_action.command = _scope_task_command(next_action.command, project_id)
    worker_lane = git_worker_lane_summary(root, task)
    local_worker_lane = local_worker_lane_summary(root, task)
    review_readiness = build_review_readiness_projection(
        root,
        task.id,
        task=task,
        status_projection=projection,
        project_id=project_id,
    )
    if task.status == "verified" and not projection.ready_to_promote and review_readiness.next_command:
        next_action = DashboardNextAction(
            label="Resolve review blocker",
            task_id=task.id,
            command=review_readiness.next_command,
            reason="Verification passed but review readiness has blockers.",
        )
    return OperatingLayerTask(
        id=task.id,
        title=task.title,
        definition_of_done=task.definition_of_done,
        status=task.status,
        display_status=projection.display_status,
        lane=_lane_for(projection, review_state=review_readiness.review_state),
        worker=task.worker,
        workspace=task.workspace,
        verification_status=projection.verification_status,
        verification_exit_code=projection.verification_exit_code,
        merge_ready=projection.merge_ready,
        promotion_ready=projection.promotion_ready,
        promotion_blockers=projection.promotion_blockers,
        latest=_scrub_quarantined_checkout(projection.latest),
        log_path=task.log_path,
        result_path=task.result_path,
        verification_log_path=projection.verification_log_path,
        next_action=next_action,
        review_state=review_readiness.review_state,
        review_score=review_readiness.score,
        review_blockers=review_readiness.blockers,
        review_next_command=review_readiness.next_command,
        review_evidence=review_readiness.evidence,
        agent_evidence_summary=compact_agent_evidence_summary(root, task.id),
        worker_lane=OperatingLayerWorkerLane(**worker_lane) if worker_lane else None,
        local_worker_lane=OperatingLayerLocalWorkerLane(**local_worker_lane) if local_worker_lane else None,
        actions=_task_actions(task.id, next_action.command, project_id=project_id, ready_to_promote=projection.ready_to_promote),
        detail=_task_detail(root, projection),
    )


def _lane_for(projection: TaskStatusProjection, *, review_state: str | None = None) -> str:
    task = projection.task
    if not projection.is_active:
        return "closed"
    if projection.is_blocked:
        return "blocked"
    if projection.failed_verification or projection.is_worker_failed or projection.is_timeout:
        return "failed"
    if task.status == "running":
        return "running"
    if projection.ready_to_promote:
        return "ready_to_promote"
    if review_state == "needs_promotion_preview" and projection.is_verified:
        return "needs_review"
    if review_state == "needs_verification":
        return "needs_verification"
    if projection.needs_verification:
        return "needs_verification"
    if task.status == "created":
        return "new"
    return "idle"


def _scrub_quarantined_checkout(value: str) -> str:
    return value.replace("/Users/jewelbait/Desktop/DevFlow", "<quarantined-devflow>")


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
            command = _scope_task_command(f"devflow task show {task.id}", project_id)
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
            command = _scope_task_command(f"devflow task show {task.id}", project_id)
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
            command = _scope_task_command(command, project_id)
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


def _promotion_candidates(
    projections: list[TaskStatusProjection],
    *,
    project_id: str | None,
) -> list[OperatingLayerPromotionCandidate]:
    return [
        OperatingLayerPromotionCandidate(
            task_id=projection.task.id,
            title=projection.task.title,
            command=_scope_task_command(f"devflow task promote-preview {projection.task.id}", project_id),
            merge_ready=projection.merge_ready,
            blockers=projection.promotion_blockers,
        )
        for projection in projections
    ]


def _evidence(projections: list[TaskStatusProjection]) -> list[OperatingLayerEvidencePointer]:
    evidence: list[OperatingLayerEvidencePointer] = []
    for projection in projections:
        task = projection.task
        if not any([task.log_path, task.result_path, projection.verification_log_path, projection.verification_command]):
            continue
        evidence.append(
            OperatingLayerEvidencePointer(
                task_id=task.id,
                log_path=task.log_path,
                result_path=task.result_path,
                verification_log_path=projection.verification_log_path,
                verification_command=projection.verification_command,
            )
        )
    return evidence


def _task_detail(root: Path, projection: TaskStatusProjection) -> OperatingLayerTaskDetail:
    task = projection.task
    base = task_dir(root, task.id)
    notes: list[str] = []
    evidence_paths = [
        path
        for path in [
            _display_artifact_path(root, task.log_path),
            _display_artifact_path(root, task.result_path),
            _display_artifact_path(root, projection.verification_log_path),
            relative_path(root, base / "events.jsonl"),
        ]
        if path
    ]
    if (base / "verification.json").exists():
        evidence_paths.append(relative_path(root, base / "verification.json"))
    worker_lane = git_worker_lane_summary(root, task)
    if worker_lane:
        evidence_paths.extend(str(path) for path in worker_lane.get("evidence_paths") or [])
    local_worker_lane = local_worker_lane_summary(root, task)
    if local_worker_lane:
        evidence_paths.extend(str(path) for path in local_worker_lane.get("evidence_paths") or [])
    return OperatingLayerTaskDetail(
        events_path=relative_path(root, base / "events.jsonl"),
        verification_path=relative_path(root, base / "verification.json"),
        recent_events=_recent_events(root, base / "events.jsonl", notes),
        verification=_verification_detail(base / "verification.json", notes),
        evidence_paths=sorted(dict.fromkeys(evidence_paths)),
        review_summary=_task_review_summary(root, projection, notes),
        latest_worker_line=_artifact_preview(root, task.log_path, notes),
        latest_verification_line=_artifact_preview(root, projection.verification_log_path, notes),
        result_preview=_artifact_preview(root, task.result_path, notes),
        notes=notes,
    )


def _task_review_summary(
    root: Path,
    projection: TaskStatusProjection,
    notes: list[str],
) -> list[OperatingLayerReviewItem]:
    task = projection.task
    worker_lane = git_worker_lane_summary(root, task)
    local_worker_lane = local_worker_lane_summary(root, task)
    changed_files = _changed_workspace_files(root, task.workspace, notes)
    task_contents = _changed_file_contents(root, task.workspace, changed_files, notes)
    items = [
        OperatingLayerReviewItem(label="Task", value=f"{task.id} - {task.title}"),
        OperatingLayerReviewItem(label="Status", value=task.status),
        OperatingLayerReviewItem(label="Verification", value=projection.verification_status or "not_run"),
        OperatingLayerReviewItem(
            label="Changed files",
            value="\n".join(changed_files) if changed_files else "No file changes detected",
        ),
        OperatingLayerReviewItem(label="Task contents", value=task_contents or "No changed file preview available"),
        OperatingLayerReviewItem(
            label="Next action",
            value=projection.dashboard_next_action.command or f"devflow task show {task.id}",
        ),
    ]
    if worker_lane:
        items.insert(3, OperatingLayerReviewItem(label="Worker lane", value=str(worker_lane["workspace_mode"])))
        items.insert(4, OperatingLayerReviewItem(label="Lane readiness", value=str(worker_lane["readiness_status"])))
    if local_worker_lane:
        items.insert(3, OperatingLayerReviewItem(label="Local worker", value=str(local_worker_lane["worker_id"])))
        items.insert(
            4,
            OperatingLayerReviewItem(
                label="Local worker readiness",
                value=str(local_worker_lane["readiness_status"]),
            ),
        )
    return items


def _changed_workspace_files(root: Path, workspace_value: str, notes: list[str], *, limit: int = 20) -> list[str]:
    workspace = absolute_path(root, workspace_value).resolve()
    if not workspace.is_dir():
        notes.append(f"workspace unavailable for review summary: {workspace_value}")
        return []

    changed: list[str] = []
    for path in sorted(workspace.rglob("*")):
        if not path.is_file():
            continue
        try:
            name = path.relative_to(workspace).as_posix()
        except ValueError:
            continue
        if _is_ignored_review_name(name):
            continue
        target = root / name
        try:
            if not target.exists() or (target.is_file() and path.read_bytes() != target.read_bytes()):
                changed.append(name)
        except OSError:
            changed.append(name)
        if len(changed) >= limit:
            break
    return changed


def _changed_file_contents(
    root: Path,
    workspace_value: str,
    changed_files: list[str],
    notes: list[str],
    *,
    limit: int = 5,
) -> str:
    workspace = absolute_path(root, workspace_value).resolve()
    previews: list[str] = []
    for name in changed_files[:limit]:
        path = workspace / name
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            notes.append(f"{name} preview unavailable: {exc}")
            continue
        lines = []
        for line in raw.splitlines():
            preview = sanitize_log_line(line, max_chars=180)
            if preview:
                lines.append(preview)
        if lines:
            previews.append(f"{name}: " + "\n".join(lines[:4]))
    return "\n".join(previews)


def _is_ignored_review_name(name: str) -> bool:
    ignored = {".git", ".devflow", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".venv"}
    return any(part in ignored for part in Path(name).parts)


def _recent_events(root: Path, path: Path, notes: list[str], *, limit: int = 5) -> list[OperatingLayerTaskEvent]:
    if not path.exists():
        notes.append("events.jsonl is missing")
        return []
    events: list[OperatingLayerTaskEvent] = []
    malformed = 0
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        notes.append(f"events.jsonl unreadable: {exc}")
        return []
    for raw_line in lines:
        if not raw_line.strip():
            continue
        try:
            event = json.loads(raw_line)
        except json.JSONDecodeError:
            malformed += 1
            continue
        if not isinstance(event, dict):
            malformed += 1
            continue
        events.append(
            OperatingLayerTaskEvent(
                timestamp=str(event.get("timestamp")) if event.get("timestamp") else None,
                event=str(event.get("event") or "unknown"),
                summary=_event_summary(root, event),
            )
        )
    if malformed:
        notes.append(f"{malformed} malformed event line(s) omitted")
    return events[-limit:]


def _event_summary(root: Path, event: dict[str, Any]) -> str:
    safe_keys = ("status", "task_status", "exit_code", "log_path", "result_path", "cwd", "outcome", "reason")
    parts: list[str] = []
    for key in safe_keys:
        value = event.get(key)
        if value is None:
            continue
        parts.append(f"{key}={_safe_summary_value(root, value)}")
    return ", ".join(parts)


def _verification_detail(path: Path, notes: list[str]) -> OperatingLayerTaskVerification | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        notes.append(f"verification.json unreadable: {exc}")
        return None
    if not isinstance(payload, dict):
        notes.append("verification.json is not an object")
        return None
    return OperatingLayerTaskVerification(
        status=str(payload.get("status") or "unknown"),
        task_status=str(payload.get("task_status")) if payload.get("task_status") is not None else None,
        exit_code=payload.get("exit_code") if isinstance(payload.get("exit_code"), int) else None,
        log_path=str(payload.get("log_path")) if payload.get("log_path") is not None else None,
    )


def _artifact_preview(root: Path, relative_or_absolute_path: str | None, notes: list[str]) -> str | None:
    path = _artifact_path(root, relative_or_absolute_path)
    if path is None:
        return None
    if not path.exists():
        notes.append(f"{relative_or_absolute_path} is missing")
        return None
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        notes.append(f"{relative_or_absolute_path} unreadable: {exc}")
        return None
    for line in reversed(lines):
        preview = sanitize_log_line(line, max_chars=220)
        if preview.startswith("$ "):
            continue
        if preview:
            return _scrub_project_root(root, preview)
    return None


def _artifact_path(root: Path, relative_or_absolute_path: str | None) -> Path | None:
    if not relative_or_absolute_path:
        return None
    path = Path(relative_or_absolute_path)
    candidate = path if path.is_absolute() else root / path
    try:
        candidate.resolve().relative_to(root.resolve())
    except ValueError:
        return None
    return candidate


def _display_artifact_path(root: Path, relative_or_absolute_path: str | None) -> str | None:
    path = _artifact_path(root, relative_or_absolute_path)
    if path is None:
        return relative_or_absolute_path
    return relative_path(root, path)


def _safe_summary_value(root: Path, value: Any) -> str:
    if isinstance(value, (dict, list)):
        return "<structured>"
    return _scrub_project_root(root, sanitize_log_line(str(value), max_chars=120))


def _scrub_project_root(root: Path, value: str) -> str:
    scrubbed = _scrub_quarantined_checkout(value)
    candidates = {root.as_posix(), root.resolve().as_posix()}
    for candidate in sorted(candidates, key=len, reverse=True):
        scrubbed = scrubbed.replace(candidate, "<repo-root>")
    return scrubbed


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
        commands.append(("Show linked task", _scope_task_command(f"devflow task show {task_id}", project_id)))
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
    return _scope_task_command(safe, project_id)


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


def _gate_receipts(root: Path, projections: list[TaskStatusProjection]) -> list[OperatingLayerGateReceipt]:
    receipts: list[OperatingLayerGateReceipt] = []
    for projection in projections:
        task = projection.task
        worker_evidence = bool(task.log_path or task.result_path or task.status in {"complete", "verified", "promoted"})
        verification = projection.verification_status == "passed" or task.status in {"verified", "promoted"}
        promotion_readiness = bool(projection.ready_to_promote or projection.promotion_ready or _merge_readiness_exists(root, task.id))
        human_decision = task.status in {"promoted", "closed"}
        receipts.append(
            OperatingLayerGateReceipt(
                task_id=task.id,
                intake=True,
                worker_evidence=worker_evidence,
                verification=verification,
                promotion_readiness=promotion_readiness,
                human_decision=human_decision,
                next_gate=_next_gate(worker_evidence, verification, promotion_readiness, human_decision),
                command=projection.dashboard_next_action.command,
            )
        )
    return receipts


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


def _task_actions(
    task_id: str,
    next_action_command: str | None,
    *,
    project_id: str | None,
    ready_to_promote: bool,
) -> list[OperatingLayerAction]:
    commands: list[tuple[str, str, str]] = [
        ("Show task", _scope_task_command(f"devflow task show {task_id}", project_id), "task"),
        ("Review capsule", _scope_task_command(f"devflow task capsule {task_id}", project_id), "task"),
        ("Task log", _scope_task_command(f"devflow task log {task_id}", project_id), "task"),
        ("Task packet", _scope_task_command(f"devflow task packet {task_id}", project_id), "task"),
    ]
    if next_action_command:
        commands.insert(0, ("Next safe action", next_action_command, "task"))
    if ready_to_promote:
        commands.extend(
            [
                ("Review preview", _scope_task_command(f"devflow task promote-preview {task_id}", project_id), "task"),
                ("Approve promotion", _scope_task_command(f"devflow task promote {task_id}", project_id), "task"),
            ]
        )

    seen: set[str] = set()
    actions: list[OperatingLayerAction] = []
    for label, command, scope in commands:
        if command in seen:
            continue
        seen.add(command)
        actions.append(_action(label, command, scope))
    return actions


def _scope_task_command(command: str, project_id: str | None) -> str:
    if not project_id or "--project" in command or not command.startswith("devflow task "):
        return command
    before_separator, separator, after_separator = command.partition(" -- ")
    scoped = f"{before_separator} --project {project_id}"
    if separator:
        return f"{scoped}{separator}{after_separator}"
    return scoped


def _action(label: str, command: str, scope: str) -> OperatingLayerAction:
    classification = classify_supervisor_command(command)
    return OperatingLayerAction(
        label=label,
        command=command,
        scope=scope,
        safety_class=str(classification["safety_class"]),
        requires_human_approval=bool(classification["requires_human_approval"]),
        supervisor_may_auto_run=bool(classification["supervisor_may_auto_run"]),
        reason=classification.get("why_not_auto_runnable"),
    )


def _merge_readiness_exists(root: Path, task_id: str) -> bool:
    return (task_dir(root, task_id) / "merge-readiness.json").exists()


def _next_gate(
    worker_evidence: bool,
    verification: bool,
    promotion_readiness: bool,
    human_decision: bool,
) -> str:
    if human_decision:
        return "closed"
    if not worker_evidence:
        return "run_worker"
    if not verification:
        return "verify"
    if not promotion_readiness:
        return "promotion_preview"
    if not human_decision:
        return "human_decision"
    return "closed"
