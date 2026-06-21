from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from devflow.control_room.dashboard import DashboardNextAction
from devflow.control_room.evidence_review_detail import EvidenceReviewDetail, build_evidence_review_detail
from devflow.control_room.git_worktree import git_worker_lane_summary
from devflow.control_room.local_worker_lane import local_worker_lane_summary
from devflow.control_room.log_sanitizer import sanitize_log_line
from devflow.control_room.paths import absolute_path, relative_path, task_dir
from devflow.control_room.review_readiness import build_review_readiness_projection
from devflow.control_room.status_projection import TaskStatusProjection, list_task_status_projections
from devflow.control_room.supervisor_surface import classify_supervisor_command
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


class TaskWorkbenchGateReceipt(BaseModel):
    task_id: str
    intake: bool
    worker_evidence: bool
    verification: bool
    promotion_readiness: bool
    human_decision: bool
    next_gate: str
    command: str | None = None


class TaskWorkbenchWorkerActivity(BaseModel):
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


class TaskWorkbenchReviewQueueItem(BaseModel):
    task_id: str
    title: str
    lane: str
    priority: str
    reason: str
    command: str | None = None
    evidence_paths: list[str] = Field(default_factory=list)
    review_state: str = "not_ready"
    review_score: int = 0
    operator_summary: str = ""
    blockers: list[str] = Field(default_factory=list)
    changed_files: list[str] = Field(default_factory=list)
    evidence_count: int = 0


class TaskWorkbenchReviewLoop(BaseModel):
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


def _review_queue(tasks: list[TaskWorkbenchTask]) -> list[TaskWorkbenchReviewQueueItem]:
    review_lanes = {"blocked", "failed", "ready_to_promote", "needs_review", "needs_verification"}
    rows: list[TaskWorkbenchReviewQueueItem] = []
    for task in tasks:
        if task.lane not in review_lanes:
            continue
        rows.append(
            TaskWorkbenchReviewQueueItem(
                task_id=task.id,
                title=task.title,
                lane=task.lane,
                priority=task.review_detail.review_priority,
                reason=task.review_detail.review_reason or _review_queue_reason(task),
                command=task.review_detail.review_command or task.next_action.command or task.review_next_command,
                evidence_paths=task.evidence_paths,
                review_state=task.review_detail.review_state,
                review_score=task.review_detail.review_score,
                operator_summary=task.review_detail.operator_summary,
                blockers=task.review_detail.blockers,
                changed_files=task.review_detail.changed_files,
                evidence_count=len(task.review_detail.evidence_paths),
            )
        )
    rank = {"blocked": 0, "failed": 1, "ready_to_promote": 2, "needs_review": 3, "needs_verification": 4}
    return sorted(rows, key=lambda row: (rank.get(row.lane, 9), row.task_id))


def _review_queue_reason(task: TaskWorkbenchTask) -> str:
    if task.review_blockers:
        return "; ".join(task.review_blockers)
    if task.promotion_blockers:
        return "; ".join(task.promotion_blockers)
    if task.next_action.reason:
        return task.next_action.reason
    return task.display_status


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
            command=_scope_task_command(f"devflow task promote-preview {projection.task.id}", project_id),
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
        if not any([task.log_path, task.result_path, task.verification_log_path, detail.verification_command, artifact]):
            continue
        evidence.append(
            TaskWorkbenchEvidencePointer(
                task_id=task.id,
                log_path=task.log_path,
                result_path=task.result_path,
                verification_log_path=task.verification_log_path,
                verification_command=detail.verification_command,
                kind=artifact.kind if artifact else _legacy_evidence_kind(task),
                text=artifact.text if artifact else detail.verification_command or task.result_path or task.log_path or "",
                path=artifact.path if artifact else task.verification_log_path or task.result_path or task.log_path,
                command=artifact.command if artifact else detail.verification_command,
                timestamp=artifact.timestamp if artifact else (
                    detail.recent_events[-1].timestamp if detail.recent_events else None
                ),
            )
        )
    return evidence


def _legacy_evidence_kind(task: TaskWorkbenchTask) -> str:
    if task.verification_log_path:
        return "verification"
    if task.result_path:
        return "result"
    if task.log_path:
        return "worker log"
    return "evidence"


def _gate_receipts(
    root: Path,
    projections: list[TaskStatusProjection],
    *,
    project_id: str | None,
) -> list[TaskWorkbenchGateReceipt]:
    receipts: list[TaskWorkbenchGateReceipt] = []
    for projection in projections:
        task = projection.task
        worker_evidence = bool(task.log_path or task.result_path or task.status in {"complete", "verified", "promoted"})
        verification = projection.verification_status == "passed" or task.status in {"verified", "promoted"}
        promotion_readiness = bool(projection.ready_to_promote or projection.promotion_ready or _merge_readiness_exists(root, task.id))
        human_decision = task.status in {"promoted", "closed"}
        command = projection.dashboard_next_action.command
        receipts.append(
            TaskWorkbenchGateReceipt(
                task_id=task.id,
                intake=True,
                worker_evidence=worker_evidence,
                verification=verification,
                promotion_readiness=promotion_readiness,
                human_decision=human_decision,
                next_gate=_next_gate(worker_evidence, verification, promotion_readiness, human_decision),
                command=_scope_task_command(command, project_id) if command else None,
            )
        )
    return receipts


def _review_loop_summary(
    tasks: list[TaskWorkbenchTask],
    *,
    review_queue: list[TaskWorkbenchReviewQueueItem],
    promotion_candidates: list[TaskWorkbenchPromotionCandidate],
    next_action: DashboardNextAction,
) -> TaskWorkbenchReviewLoop:
    needs_verification = [task for task in tasks if task.lane == "needs_verification"]
    ready_to_promote = [task for task in tasks if task.lane == "ready_to_promote"]
    blocked_decisions = [item for item in review_queue if item.lane in {"blocked", "failed"}]
    verified_count = sum(1 for task in tasks if _worker_task_verified_or_ready(task))
    worker_output_count = sum(1 for task in tasks if task.log_path or task.result_path)

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

    promotion_command = promotion_candidates[0].command if promotion_candidates else None
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

    return TaskWorkbenchReviewLoop(
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


def _task_review_summary(
    root: Path,
    projection: TaskStatusProjection,
    notes: list[str],
) -> list[TaskWorkbenchReviewItem]:
    task = projection.task
    worker_lane = git_worker_lane_summary(root, task)
    local_worker_lane = local_worker_lane_summary(root, task)
    changed_files = _changed_workspace_files(root, task.workspace, notes)
    task_contents = _changed_file_contents(root, task.workspace, changed_files, notes)
    items = [
        TaskWorkbenchReviewItem(label="Task", value=f"{task.id} - {task.title}"),
        TaskWorkbenchReviewItem(label="Status", value=task.status),
        TaskWorkbenchReviewItem(label="Verification", value=projection.verification_status or "not_run"),
        TaskWorkbenchReviewItem(
            label="Changed files",
            value="\n".join(changed_files) if changed_files else "No file changes detected",
        ),
        TaskWorkbenchReviewItem(label="Task contents", value=task_contents or "No changed file preview available"),
        TaskWorkbenchReviewItem(
            label="Next action",
            value=projection.dashboard_next_action.command or f"devflow task show {task.id}",
        ),
    ]
    if worker_lane:
        items.insert(3, TaskWorkbenchReviewItem(label="Worker lane", value=str(worker_lane["workspace_mode"])))
        items.insert(4, TaskWorkbenchReviewItem(label="Lane readiness", value=str(worker_lane["readiness_status"])))
    if local_worker_lane:
        items.insert(3, TaskWorkbenchReviewItem(label="Local worker", value=str(local_worker_lane["worker_id"])))
        items.insert(
            4,
            TaskWorkbenchReviewItem(
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


def _recent_events(root: Path, path: Path, notes: list[str], *, limit: int = 5) -> list[TaskWorkbenchTaskEvent]:
    if not path.exists():
        notes.append("events.jsonl is missing")
        return []
    events: list[TaskWorkbenchTaskEvent] = []
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
            TaskWorkbenchTaskEvent(
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


def _verification_detail(path: Path, notes: list[str]) -> TaskWorkbenchTaskVerification | None:
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
    return TaskWorkbenchTaskVerification(
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


def _scrub_quarantined_checkout(value: str) -> str:
    return value.replace("/Users/jewelbait/Desktop/DevFlow", "<quarantined-devflow>")


def _worker_activity(tasks: list[TaskWorkbenchTask]) -> list[TaskWorkbenchWorkerActivity]:
    grouped: dict[str, list[TaskWorkbenchTask]] = {}
    for task in tasks:
        worker = _normalized_worker(task.worker)
        if not worker:
            continue
        grouped.setdefault(worker, []).append(task)

    rows: list[TaskWorkbenchWorkerActivity] = []
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
            TaskWorkbenchWorkerActivity(
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


def _worker_model_label(worker: str, local_worker_lane: dict[str, Any] | None) -> str:
    if local_worker_lane:
        identity = str(
            local_worker_lane.get("profile_id")
            or local_worker_lane.get("worker_id")
            or "local model"
        )
        model = local_worker_lane.get("model")
        return f"{identity} - {model}" if model else identity
    return worker or "unassigned"


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


def _worker_state(open_tasks: list[TaskWorkbenchTask]) -> str:
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


def _worker_task_failed(task: TaskWorkbenchTask) -> bool:
    return "fail" in task.verification_status.lower() or "failed" in task.display_status.lower()


def _worker_task_verified_or_ready(task: TaskWorkbenchTask) -> bool:
    return (
        "pass" in task.verification_status.lower()
        or bool(task.promotion_ready or task.merge_ready)
        or task.lane == "closed"
    )


def _task_actions(
    task_id: str,
    next_action_command: str | None,
    *,
    project_id: str | None,
    ready_to_promote: bool,
) -> list[TaskWorkbenchAction]:
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
    actions: list[TaskWorkbenchAction] = []
    for label, command, scope in commands:
        if command in seen:
            continue
        seen.add(command)
        actions.append(_action(label, command, scope))
    return actions


def _task_controls(
    projection: TaskStatusProjection,
    next_action_command: str | None,
    *,
    project_id: str | None,
    ready_to_promote: bool,
) -> list[TaskWorkbenchControl]:
    task_id = projection.task.id
    commands: list[tuple[str, str, str]] = [
        ("inspect", "Inspect", _scope_task_command(f"devflow task show {task_id}", project_id)),
    ]
    if projection.task.status == "closed":
        cleanup = next_action_command if next_action_command and " task cleanup " in next_action_command else None
        if not cleanup and projection.suggested_next_action.startswith("devflow task cleanup "):
            cleanup = _scope_task_command(projection.suggested_next_action, project_id)
        if cleanup and cleanup != "none":
            commands.append(("cleanup_preview", "Cleanup preview", cleanup))
    else:
        if next_action_command:
            commands.append((_intent_for_command(next_action_command), _label_for_command(next_action_command), next_action_command))
        if projection.task.status == "created":
            commands.append(
                (
                    "start_shell",
                    "Start shell",
                    _scope_task_command(f"devflow task run {task_id} --worker shell -- <command>", project_id),
                )
            )
        if projection.failed_verification:
            commands.append(
                (
                    "verify",
                    "Verify",
                    _scope_task_command(f'devflow task verify {task_id} --shell "<command>"', project_id),
                )
            )
        if projection.is_worker_failed or projection.is_timeout:
            commands.append(
                (
                    "retry",
                    "Retry",
                    _scope_task_command(f"devflow task run {task_id} --worker shell -- <command>", project_id),
                )
            )
        if ready_to_promote:
            commands.extend(
                [
                    (
                        "review_preview",
                        "Review preview",
                        _scope_task_command(f"devflow task promote-preview {task_id}", project_id),
                    ),
                    ("promote", "Promote", _scope_task_command(f"devflow task promote {task_id}", project_id)),
                ]
            )
        commands.append(
            (
                "close",
                "Close",
                _scope_task_command(
                    f'devflow task close {task_id} --outcome evidence-only --reason "<reason>"',
                    project_id,
                ),
            )
        )

    seen: set[tuple[str, str]] = set()
    controls: list[TaskWorkbenchControl] = []
    for intent, label, command in commands:
        key = (intent, command)
        if key in seen:
            continue
        seen.add(key)
        controls.append(_control(intent, label, command))
    return controls


def _intent_for_command(command: str) -> str:
    if " task run " in command and "--worker shell" in command:
        return "start_shell"
    if " task verify " in command:
        return "verify"
    if " task promote-preview " in command:
        return "review_preview"
    if " task promote " in command:
        return "promote"
    if " task cleanup " in command and "--preview" in command:
        return "cleanup_preview"
    if " task log " in command:
        return "inspect_log"
    return "next_safe_action"


def _label_for_command(command: str) -> str:
    labels = {
        "start_shell": "Start shell",
        "verify": "Verify",
        "review_preview": "Review preview",
        "promote": "Promote",
        "cleanup_preview": "Cleanup preview",
        "inspect_log": "Inspect log",
    }
    return labels.get(_intent_for_command(command), "Next safe action")


def _action(label: str, command: str, scope: str) -> TaskWorkbenchAction:
    classification = classify_supervisor_command(command)
    return TaskWorkbenchAction(
        label=label,
        command=command,
        scope=scope,
        safety_class=str(classification["safety_class"]),
        requires_human_approval=bool(classification["requires_human_approval"]),
        supervisor_may_auto_run=bool(classification["supervisor_may_auto_run"]),
        reason=classification.get("why_not_auto_runnable"),
    )


def _control(intent: str, label: str, command: str) -> TaskWorkbenchControl:
    classification = classify_supervisor_command(command)
    return TaskWorkbenchControl(
        intent=intent,
        label=label,
        command=command,
        safety_class=str(classification["safety_class"]),
        requires_human_approval=bool(classification["requires_human_approval"]),
        supervisor_may_auto_run=bool(classification["supervisor_may_auto_run"]),
        required_inputs=_required_inputs_for_control(intent, command),
        reason=classification.get("why_not_auto_runnable"),
    )


def _required_inputs_for_control(intent: str, command: str) -> list[str]:
    if intent in {"start_shell", "retry"} or command.endswith(" -- <command>"):
        return ["shell_command"]
    if intent == "verify" or ' --shell "<command>"' in command:
        return ["verification_command"]
    if intent == "close":
        return ["close_outcome", "close_reason"]
    return []


def _scope_task_command(command: str, project_id: str | None) -> str:
    if not project_id or "--project" in command or not command.startswith("devflow task "):
        return command
    before_separator, separator, after_separator = command.partition(" -- ")
    scoped = f"{before_separator} --project {project_id}"
    if separator:
        return f"{scoped}{separator}{after_separator}"
    return scoped


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
