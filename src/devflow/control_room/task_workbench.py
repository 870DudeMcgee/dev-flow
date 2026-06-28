from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from devflow.control_room.browser_task_capabilities import (
    build_task_action_capabilities,
    build_task_capability,
    build_task_control_capabilities,
    scope_task_command,
)
from devflow.control_room.dashboard import DashboardNextAction
from devflow.control_room.evidence_review_detail import EvidenceReviewDetail, build_evidence_review_detail
from devflow.control_room.git_worktree import git_worker_lane_summary
from devflow.control_room.local_worker_lane import local_worker_lane_summary
from devflow.control_room.review_readiness import build_review_readiness_projection
from devflow.control_room.status_projection import TaskStatusProjection, list_task_status_projections
from devflow.control_room.task_workbench_review import (
    TaskWorkbenchGateReceipt,
    TaskWorkbenchReviewLoop,
    TaskWorkbenchReviewQueueItem,
    TaskWorkbenchWorkerActivity,
    _gate_receipts,
    _review_loop_summary,
    _review_queue,
    _worker_activity,
    _worker_model_label,
)
from devflow.control_room.worker_options import build_worker_options


LANE_ORDER: tuple[tuple[str, str], ...] = (
    ("blocked", "Blocked"),
    ("failed", "Failed"),
    ("running", "Running"),
    ("ready_to_promote", "Ready for Review"),
    ("needs_review", "Needs Review"),
    ("needs_verification", "Needs Verification"),
    ("new", "New"),
    ("idle", "Idle"),
    ("closed", "Closed"),
)


class TaskWorkbenchAction(BaseModel):
    label: str
    command: str
    scope: str
    safety_class: str
    requires_human_approval: bool
    supervisor_may_auto_run: bool
    intent: str | None = None
    required_inputs: list[str] = Field(default_factory=list)
    reason: str | None = None


class TaskWorkbenchControl(BaseModel):
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


class TaskWorkbenchLane(BaseModel):
    name: str
    label: str
    task_ids: list[str] = Field(default_factory=list)


class TaskWorkbenchTaskEvent(BaseModel):
    timestamp: str | None = None
    event: str
    summary: str = ""


class TaskWorkbenchTaskVerification(BaseModel):
    status: str
    task_status: str | None = None
    exit_code: int | None = None
    log_path: str | None = None


class TaskWorkbenchReviewItem(BaseModel):
    label: str
    value: str


class TaskWorkbenchTaskDetail(BaseModel):
    events_path: str
    verification_path: str
    recent_events: list[TaskWorkbenchTaskEvent] = Field(default_factory=list)
    verification: TaskWorkbenchTaskVerification | None = None
    evidence_paths: list[str] = Field(default_factory=list)
    review_summary: list[TaskWorkbenchReviewItem] = Field(default_factory=list)
    latest_worker_line: str | None = None
    latest_verification_line: str | None = None
    result_preview: str | None = None
    notes: list[str] = Field(default_factory=list)


class TaskWorkbenchWorkerLane(BaseModel):
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


class TaskWorkbenchLocalWorkerLane(BaseModel):
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


class TaskWorkbenchTask(BaseModel):
    id: str
    title: str
    definition_of_done: str | None = None
    status: str
    display_status: str
    lane: str
    worker: str
    worker_model_label: str
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
    next_safe_action: str | None = None
    review_state: str = "not_ready"
    review_score: int = 0
    review_blockers: list[str] = Field(default_factory=list)
    review_next_command: str | None = None
    review_evidence: list[str] = Field(default_factory=list)
    agent_evidence_summary: dict[str, Any] = Field(default_factory=dict)
    worker_lane: TaskWorkbenchWorkerLane | None = None
    local_worker_lane: TaskWorkbenchLocalWorkerLane | None = None
    actions: list[TaskWorkbenchAction] = Field(default_factory=list)
    controls: list[TaskWorkbenchControl] = Field(default_factory=list)
    evidence_paths: list[str] = Field(default_factory=list)
    review_detail: EvidenceReviewDetail
    detail: TaskWorkbenchTaskDetail
    worker_options: list[dict[str, object]] = Field(default_factory=list)


class TaskWorkbenchPromotionCandidate(BaseModel):
    task_id: str
    title: str
    command: str
    merge_ready: bool | None
    blockers: list[str] = Field(default_factory=list)


class TaskWorkbenchEvidencePointer(BaseModel):
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


class TaskWorkbenchCounts(BaseModel):
    total_tasks: int
    active_task_count: int
    active_task_ids: list[str] = Field(default_factory=list)
    review_queue_count: int
    evidence_count: int
    lane_counts: dict[str, int] = Field(default_factory=dict)


class TaskWorkbench(BaseModel):
    focus_task_id: str | None = None
    lanes: list[TaskWorkbenchLane] = Field(default_factory=list)
    tasks: list[TaskWorkbenchTask] = Field(default_factory=list)
    review_queue: list[TaskWorkbenchReviewQueueItem] = Field(default_factory=list)
    promotion_candidates: list[TaskWorkbenchPromotionCandidate] = Field(default_factory=list)
    evidence_stream: list[TaskWorkbenchEvidencePointer] = Field(default_factory=list)
    gate_receipts: list[TaskWorkbenchGateReceipt] = Field(default_factory=list)
    worker_activity: list[TaskWorkbenchWorkerActivity] = Field(default_factory=list)
    review_loop: TaskWorkbenchReviewLoop
    counts: TaskWorkbenchCounts
    warnings: list[str] = Field(default_factory=list)


def build_task_workbench(
    root: Path,
    *,
    project_id: str | None = None,
    projections: list[TaskStatusProjection] | None = None,
) -> TaskWorkbench:
    """Build the read-only task-centered operating-layer projection."""
    root = root.resolve()
    warnings: list[str] = []
    projections = projections if projections is not None else list_task_status_projections(root)
    tasks = [_task_card(root, projection, project_id=project_id) for projection in projections]
    lane_lookup = {name: [] for name, _label in LANE_ORDER}
    for task in tasks:
        lane_lookup.setdefault(task.lane, []).append(task.id)
    lanes = [
        TaskWorkbenchLane(name=name, label=label, task_ids=lane_lookup.get(name, []))
        for name, label in LANE_ORDER
    ]
    focus_task_id = _focus_task_id(tasks)
    promotion_candidates = _promotion_candidates(projections, project_id=project_id)
    evidence_stream = _evidence(tasks)
    gate_receipts = _gate_receipts(root, projections, project_id=project_id)
    review_queue = _review_queue(tasks)
    worker_activity = _worker_activity(tasks)
    review_loop = _review_loop_summary(
        tasks,
        review_queue=review_queue,
        promotion_candidates=promotion_candidates,
        next_action=_workbench_next_action(tasks, focus_task_id),
    )
    active_task_ids = [task.id for task in tasks if task.lane != "closed"]
    return TaskWorkbench(
        focus_task_id=focus_task_id,
        lanes=lanes,
        tasks=tasks,
        review_queue=review_queue,
        promotion_candidates=promotion_candidates,
        evidence_stream=evidence_stream,
        gate_receipts=gate_receipts,
        worker_activity=worker_activity,
        review_loop=review_loop,
        counts=TaskWorkbenchCounts(
            total_tasks=len(tasks),
            active_task_count=len(active_task_ids),
            active_task_ids=active_task_ids,
            review_queue_count=len(review_queue),
            evidence_count=len(evidence_stream),
            lane_counts={lane.name: len(lane.task_ids) for lane in lanes},
        ),
        warnings=warnings,
    )


def _task_card(root: Path, projection: TaskStatusProjection, *, project_id: str | None) -> TaskWorkbenchTask:
    task = projection.task
    next_action = DashboardNextAction(**projection.dashboard_next_action.model_dump())
    if next_action.command:
        next_action.command = scope_task_command(next_action.command, project_id)
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
    lane = _lane_for(projection, review_state=review_readiness.review_state)
    evidence_review_detail = build_evidence_review_detail(
        root,
        projection,
        review_readiness=review_readiness,
        worker_lane=worker_lane,
        local_worker_lane=local_worker_lane,
        project_id=project_id,
    )
    detail = _task_detail(evidence_review_detail)
    actions = _task_actions(
        task.id,
        next_action.command,
        project_id=project_id,
        ready_to_promote=projection.ready_to_promote,
    )
    controls = _task_controls(
        projection,
        next_action.command,
        project_id=project_id,
        ready_to_promote=projection.ready_to_promote,
    )
    local_lane = TaskWorkbenchLocalWorkerLane(**local_worker_lane) if local_worker_lane else None
    worker_opts_raw = build_worker_options(root, task.id, project_id=project_id)
    # Flatten to serializable dicts: ai workers + blocked details.
    wo_dicts: list[dict[str, object]] = []
    for w in worker_opts_raw.get("ai_workers", []):
        if isinstance(w, dict):
            wo_dicts.append(w)
        else:
            wo_dicts.append({k: v for k, v in w.model_dump().items() if not k.startswith("_")})
    for wid, w in worker_opts_raw.get("blocked_details", {}).items():
        if isinstance(w, dict):
            wo_dicts.append({"worker_id": wid, "is_blocked_reason": True, **w})
        else:
            wo_dicts.append({"worker_id": wid, "is_blocked_reason": True, **{k: v for k, v in w.model_dump().items() if not k.startswith("_")}})
    # Always append the shell fallback last.
    fo = worker_opts_raw.get("fallback_shell")
    if fo:
        wo_dicts.append({k: v for k, v in fo.model_dump().items() if not k.startswith("_")})

    return TaskWorkbenchTask(
        id=task.id,
        title=task.title,
        definition_of_done=task.definition_of_done,
        status=task.status,
        display_status=projection.display_status,
        lane=lane,
        worker=task.worker,
        worker_model_label=_worker_model_label(task.worker, local_worker_lane),
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
        next_safe_action=next_action.command,
        review_state=review_readiness.review_state,
        review_score=review_readiness.score,
        review_blockers=review_readiness.blockers,
        review_next_command=evidence_review_detail.review_command,
        review_evidence=evidence_review_detail.evidence_paths,
        agent_evidence_summary=evidence_review_detail.agent_evidence_summary,
        worker_lane=TaskWorkbenchWorkerLane(**worker_lane) if worker_lane else None,
        local_worker_lane=local_lane,
        actions=actions,
        controls=controls,
        evidence_paths=evidence_review_detail.evidence_paths,
        review_detail=evidence_review_detail,
        detail=detail,
        worker_options=wo_dicts,
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
    if review_state in {"review_patch", "patch_dry_run", "apply_patch"}:
        return "needs_review"
    if review_state == "needs_promotion_preview" and projection.is_verified:
        return "needs_review"
    if review_state == "needs_verification":
        return "needs_verification"
    if projection.needs_verification:
        return "needs_verification"
    if task.status == "created":
        return "new"
    return "idle"


def _focus_task_id(tasks: list[TaskWorkbenchTask]) -> str | None:
    for lane in ("blocked", "failed", "running", "ready_to_promote", "needs_review", "needs_verification", "new", "idle"):
        for task in tasks:
            if task.lane == lane:
                return task.id
    return None


def _workbench_next_action(tasks: list[TaskWorkbenchTask], focus_task_id: str | None) -> DashboardNextAction:
    focus_task = next((task for task in tasks if task.id == focus_task_id), None)
    if focus_task:
        return focus_task.next_action
    return DashboardNextAction(label="Inspect dashboard", command="devflow dashboard", reason="No task is waiting.")


def _promotion_candidates(
    projections: list[TaskStatusProjection],
    *,
    project_id: str | None,
) -> list[TaskWorkbenchPromotionCandidate]:
    return [
        TaskWorkbenchPromotionCandidate(
            task_id=projection.task.id,
            title=projection.task.title,
            command=build_task_capability(
                "review_preview",
                projection.task.id,
                project_id=project_id,
            ).command,
            merge_ready=projection.merge_ready,
            blockers=projection.promotion_blockers,
        )
        for projection in projections
        if projection.ready_to_promote
    ]


def _evidence(tasks: list[TaskWorkbenchTask]) -> list[TaskWorkbenchEvidencePointer]:
    evidence: list[TaskWorkbenchEvidencePointer] = []
    for task in tasks:
        detail = task.review_detail
        artifact = detail.artifacts[0] if detail.artifacts else None
        if not artifact:
            continue
        evidence.append(
            TaskWorkbenchEvidencePointer(
                task_id=task.id,
                log_path=task.log_path,
                result_path=task.result_path,
                verification_log_path=task.verification_log_path,
                verification_command=detail.verification_command,
                kind=artifact.kind,
                text=artifact.text,
                path=artifact.path,
                command=artifact.command,
                timestamp=artifact.timestamp,
            )
        )
    return evidence


def _task_detail(review_detail: EvidenceReviewDetail) -> TaskWorkbenchTaskDetail:
    return TaskWorkbenchTaskDetail(
        events_path=review_detail.events_path,
        verification_path=review_detail.verification_path,
        recent_events=[
            TaskWorkbenchTaskEvent(**event.model_dump())
            for event in review_detail.recent_events
        ],
        verification=(
            TaskWorkbenchTaskVerification(**review_detail.verification.model_dump())
            if review_detail.verification
            else None
        ),
        evidence_paths=review_detail.evidence_paths,
        review_summary=[
            TaskWorkbenchReviewItem(**item.model_dump())
            for item in review_detail.review_summary
        ],
        latest_worker_line=review_detail.latest_worker_line,
        latest_verification_line=review_detail.latest_verification_line,
        result_preview=review_detail.result_preview,
        notes=review_detail.notes,
    )


def _scrub_quarantined_checkout(value: str) -> str:
    return value.replace("/Users/jewelbait/Desktop/DevFlow", "<quarantined-devflow>")


def _task_actions(
    task_id: str,
    next_action_command: str | None,
    *,
    project_id: str | None,
    ready_to_promote: bool,
) -> list[TaskWorkbenchAction]:
    return [
        TaskWorkbenchAction(**capability.model_dump())
        for capability in build_task_action_capabilities(
            task_id,
            project_id=project_id,
            next_action_command=next_action_command,
            ready_to_promote=ready_to_promote,
        )
    ]


def _task_controls(
    projection: TaskStatusProjection,
    next_action_command: str | None,
    *,
    project_id: str | None,
    ready_to_promote: bool,
) -> list[TaskWorkbenchControl]:
    return [
        TaskWorkbenchControl(**capability.model_dump())
        for capability in build_task_control_capabilities(
            projection.task.id,
            project_id=project_id,
            task_status=projection.task.status,
            next_action_command=next_action_command,
            suggested_next_action=projection.suggested_next_action,
            failed_verification=projection.failed_verification,
            worker_failed=projection.is_worker_failed,
            timed_out=projection.is_timeout,
            ready_to_promote=ready_to_promote,
        )
    ]
