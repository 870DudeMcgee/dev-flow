from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from devflow.legacy.control_room.freshness import FreshnessReport, run_freshness_loop
from devflow.legacy.control_room.models import TaskRecord
from devflow.legacy.control_room.operator_readiness import (
    OperatorReadinessSnapshot,
    OperatorTaskProjection,
    build_operator_readiness_snapshot,
)
from devflow.legacy.control_room.paths import relative_path, task_dir
from devflow.legacy.control_room.persistence import atomic_write_text, get_task, list_tasks, utc_now
from devflow.legacy.control_room.question_resume import QuestionRecord, build_question_snapshot
from devflow.legacy.control_room.status_projection import build_task_status_projection
from devflow.legacy.control_room.task_lifecycle import append_task_event


SchedulerTaskState = Literal[
    "ready",
    "running",
    "stale",
    "blocked",
    "needs_retry",
    "needs_review",
    "ready_to_verify",
    "ready_to_promote",
    "closed",
]


class SchedulerTask(BaseModel):
    task_id: str
    title: str
    status: str
    verification_status: str
    scheduler_state: SchedulerTaskState
    stale: bool = False
    stale_reason: str | None = None
    blockers: list[str] = Field(default_factory=list)
    evidence_paths: list[str] = Field(default_factory=list)
    next_safe_action: str


class SchedulerBatch(BaseModel):
    batch_type: Literal["task_creation", "worker", "verification"]
    goal_id: str
    batch_id: str
    lane_ids: list[str] = Field(default_factory=list)
    task_ids: list[str] = Field(default_factory=list)
    commands: list[str] = Field(default_factory=list)
    shared_files: list[str] = Field(default_factory=list)
    next_safe_action: str


class SchedulerDependencyBlocker(BaseModel):
    goal_id: str
    lane_id: str
    blocked_by: list[str] = Field(default_factory=list)
    title: str
    next_safe_action: str


class SchedulerRetryRequest(BaseModel):
    schema_version: int = 1
    task_id: str
    requested_at: str
    reason: str
    previous_status: str
    previous_verification_status: str
    recommended_next_command: str
    retry_request_path: str


class SchedulerSnapshot(BaseModel):
    schema_version: int = 1
    generated_at: str
    status: Literal["ready", "blocked", "stale", "idle"]
    counts: dict[str, int]
    max_parallel_recommendation: int
    tasks: list[SchedulerTask] = Field(default_factory=list)
    batches: list[SchedulerBatch] = Field(default_factory=list)
    blocked_dependencies: list[SchedulerDependencyBlocker] = Field(default_factory=list)
    stale_tasks: list[str] = Field(default_factory=list)
    retry_candidates: list[str] = Field(default_factory=list)
    next_safe_action: str
    evidence_paths: list[str] = Field(default_factory=list)
    operator_readiness: OperatorReadinessSnapshot | None = None


STATE_ORDER: list[SchedulerTaskState] = [
    "stale",
    "blocked",
    "needs_retry",
    "running",
    "ready_to_promote",
    "ready_to_verify",
    "needs_review",
    "ready",
    "closed",
]

RETRY_STATUSES = {"worker_failed", "timeout", "failed", "verification_failed"}
CLOSED_STATUSES = {"closed", "promoted"}


def build_scheduler_snapshot(root: Path) -> SchedulerSnapshot:
    root = root.resolve()
    freshness = _try_freshness(root)
    question_snapshot = build_question_snapshot(root)
    operator_readiness = build_operator_readiness_snapshot(root)
    operator_tasks = {task.task_id: task for task in operator_readiness.tasks}
    questions_by_task: dict[str, list[QuestionRecord]] = {}
    for question in question_snapshot.questions:
        questions_by_task.setdefault(question.task_id, []).append(question)
    tasks = [
        _scheduler_task(root, task, questions_by_task.get(task.id, []), operator_tasks.get(task.id))
        for task in list_tasks(root)
    ]
    batches = _scheduler_batches(freshness)
    blocked_dependencies = _blocked_dependencies(freshness)

    counts = {state: 0 for state in STATE_ORDER}
    for task in tasks:
        counts[task.scheduler_state] = counts.get(task.scheduler_state, 0) + 1
    counts["blocked"] = counts.get("blocked", 0) + len(blocked_dependencies)
    counts["ready"] = counts.get("ready", 0) + sum(len(batch.lane_ids) for batch in batches)

    sorted_tasks = sorted(tasks, key=lambda item: (STATE_ORDER.index(item.scheduler_state), item.task_id))
    stale_tasks = [task.task_id for task in sorted_tasks if task.scheduler_state == "stale"]
    retry_candidates = [task.task_id for task in sorted_tasks if task.scheduler_state == "needs_retry"]
    evidence_paths = _dedupe(
        [
            ".devflow/freshness/latest.json",
            *[path for task in sorted_tasks for path in task.evidence_paths],
        ]
    )
    return SchedulerSnapshot(
        generated_at=datetime.now(timezone.utc).isoformat(),
        status=_snapshot_status(counts),
        counts=counts,
        max_parallel_recommendation=_max_parallel_recommendation(batches),
        tasks=sorted_tasks,
        batches=batches,
        blocked_dependencies=blocked_dependencies,
        stale_tasks=stale_tasks,
        retry_candidates=retry_candidates,
        next_safe_action=_next_safe_action(operator_readiness, batches, sorted_tasks, blocked_dependencies),
        evidence_paths=evidence_paths,
        operator_readiness=operator_readiness,
    )


def request_scheduler_retry(root: Path, task_id: str, *, reason: str) -> SchedulerRetryRequest:
    clean_reason = reason.strip()
    if not clean_reason:
        raise ValueError("Retry reason is required.")

    root = root.resolve()
    task = get_task(root, task_id)
    path = task_dir(root, task_id) / "retry-request.json"
    request = SchedulerRetryRequest(
        task_id=task_id,
        requested_at=datetime.now(timezone.utc).isoformat(),
        reason=clean_reason,
        previous_status=task.status,
        previous_verification_status=task.verification_status,
        recommended_next_command=f"devflow task next-action {task_id}",
        retry_request_path=relative_path(root, path),
    )
    atomic_write_text(path, request.model_dump_json(indent=2) + "\n")
    append_task_event(root, task_id, "retry_requested", {"reason": request.reason})
    return request


def render_scheduler_snapshot(snapshot: SchedulerSnapshot) -> str:
    lines = [
        f"scheduler_status: {snapshot.status}",
        f"next_safe_action: {snapshot.next_safe_action}",
        f"max_parallel_recommendation: {snapshot.max_parallel_recommendation}",
        "counts:",
    ]
    for state in STATE_ORDER:
        lines.append(f"  {state}: {snapshot.counts.get(state, 0)}")
    if snapshot.batches:
        lines.append("batches:")
        for batch in snapshot.batches[:8]:
            lines.append(f"  - {batch.batch_type} {batch.batch_id}: {batch.next_safe_action}")
    if snapshot.tasks:
        lines.append("tasks:")
        for task in snapshot.tasks[:12]:
            lines.append(f"  - {task.task_id}: {task.scheduler_state} -> {task.next_safe_action}")
    return "\n".join(lines) + "\n"


def _try_freshness(root: Path) -> FreshnessReport | None:
    try:
        return run_freshness_loop(root, write_snapshot=False)
    except Exception:
        return None


def _scheduler_task(
    root: Path,
    task: TaskRecord,
    questions: list[QuestionRecord],
    operator_task: OperatorTaskProjection | None = None,
) -> SchedulerTask:
    current_task_dir = task_dir(root, task.id)
    stale, stale_reason, stale_evidence = _is_stale(root, task, current_task_dir)
    blockers, blocker_evidence, question_next_action, has_answered_question = _question_blockers(questions)
    projection = build_task_status_projection(root, task.id, task=task)
    retry_request = current_task_dir / "retry-request.json"
    evidence_paths = [
        relative_path(root, current_task_dir / "task.yaml"),
        relative_path(root, current_task_dir / "events.jsonl"),
        *blocker_evidence,
        *stale_evidence,
    ]
    if retry_request.exists():
        evidence_paths.append(relative_path(root, retry_request))

    operator_blocked = operator_task is not None and operator_task.readiness.state == "blocked"
    if operator_blocked:
        blockers.extend(blocker.message for blocker in operator_task.readiness.blocked_by)

    if task.status in CLOSED_STATUSES:
        state: SchedulerTaskState = "closed"
    elif operator_blocked:
        state = "blocked"
    elif stale:
        state: SchedulerTaskState = "stale"
    elif blockers or (task.status == "blocked" and not has_answered_question):
        state = "blocked"
    elif retry_request.exists() or task.status in RETRY_STATUSES:
        state = "needs_retry"
    elif task.status == "running":
        state = "running"
    elif projection.ready_to_promote:
        state = "ready_to_promote"
    elif projection.is_verified:
        state = "needs_review"
    elif projection.needs_verification:
        state = "ready_to_verify"
    else:
        state = "ready"

    return SchedulerTask(
        task_id=task.id,
        title=task.title,
        status=task.status,
        verification_status=task.verification_status,
        scheduler_state=state,
        stale=stale,
        stale_reason=stale_reason,
        blockers=blockers,
        evidence_paths=_dedupe(evidence_paths),
        next_safe_action=question_next_action or _task_next_action(task.id, state),
    )


def _is_stale(root: Path, task: TaskRecord, current_task_dir: Path) -> tuple[bool, str | None, list[str]]:
    evidence: list[str] = []
    if task.status != "running":
        return False, None, evidence

    started = task.started_at or task.updated_at
    age = (utc_now() - started).total_seconds()
    threshold = max(int(task.timeout_seconds or 120), 300)
    if age > threshold:
        return True, f"running for {int(age)}s, threshold {threshold}s", evidence

    owner = current_task_dir / ".lock" / "owner.json"
    if owner.exists():
        evidence.append(relative_path(root, owner))
        try:
            json.loads(owner.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            return True, f"lock owner evidence is unreadable or malformed: {exc}", evidence
    return False, None, evidence


def _question_blockers(questions: list[QuestionRecord]) -> tuple[list[str], list[str], str | None, bool]:
    blockers: list[str] = []
    evidence: list[str] = []
    next_action: str | None = None
    has_answered_question = False
    for question in questions:
        evidence.extend(question.evidence_paths)
        if question.status == "answered":
            has_answered_question = True
            if next_action is None:
                next_action = question.recommended_resume_command
            continue
        if question.status != "open":
            continue
        blockers.append(question.question)
        if next_action is None:
            next_action = f'devflow question answer {question.question_id} --answer "<answer>"'
    return blockers, _dedupe(evidence), next_action, has_answered_question


def _task_next_action(task_id: str, state: SchedulerTaskState) -> str:
    if state == "needs_retry":
        return f'devflow scheduler retry {task_id} --reason "<reason>"'
    if state == "ready_to_promote":
        return f"devflow task promote-preview {task_id}"
    if state == "ready_to_verify":
        return f'devflow task verify {task_id} --shell "<command>"'
    if state == "needs_review":
        return f"devflow task review-ready {task_id} --json"
    return f"devflow task show {task_id}"


def _scheduler_batches(freshness: FreshnessReport | None) -> list[SchedulerBatch]:
    if freshness is None:
        return []

    batches: list[SchedulerBatch] = []
    for goal in freshness.goal_loop:
        for batch in goal.parallel_batches:
            batches.append(
                SchedulerBatch(
                    batch_type="task_creation",
                    goal_id=goal.goal_id,
                    batch_id=batch.batch_id,
                    lane_ids=batch.lane_ids,
                    commands=batch.commands,
                    shared_files=batch.shared_files,
                    next_safe_action=f"devflow freshness create-batch {goal.goal_id} {batch.batch_id}",
                )
            )
        for batch in goal.worker_batches:
            batches.append(
                SchedulerBatch(
                    batch_type="worker",
                    goal_id=goal.goal_id,
                    batch_id=batch.batch_id,
                    lane_ids=batch.lane_ids,
                    task_ids=batch.task_ids,
                    commands=batch.commands,
                    shared_files=batch.shared_files,
                    next_safe_action=f"devflow freshness worker-batch {goal.goal_id} {batch.batch_id}",
                )
            )
        for batch in goal.verification_batches:
            batches.append(
                SchedulerBatch(
                    batch_type="verification",
                    goal_id=goal.goal_id,
                    batch_id=batch.batch_id,
                    lane_ids=batch.lane_ids,
                    task_ids=batch.task_ids,
                    commands=batch.commands,
                    shared_files=batch.shared_files,
                    next_safe_action=f"devflow freshness verify-batch {goal.goal_id} {batch.batch_id}",
                )
            )
    return batches


def _blocked_dependencies(freshness: FreshnessReport | None) -> list[SchedulerDependencyBlocker]:
    if freshness is None:
        return []

    blockers: list[SchedulerDependencyBlocker] = []
    for goal in freshness.goal_loop:
        for lane in goal.lanes:
            if lane.blockers:
                blockers.append(
                    SchedulerDependencyBlocker(
                        goal_id=goal.goal_id,
                        lane_id=lane.slice_id,
                        blocked_by=lane.blockers,
                        title=lane.title,
                        next_safe_action=f"devflow goal status {goal.goal_id}",
                    )
                )
    return blockers


def _snapshot_status(counts: dict[str, int]) -> Literal["ready", "blocked", "stale", "idle"]:
    if counts.get("stale", 0):
        return "stale"
    if counts.get("ready", 0):
        return "ready"
    if counts.get("blocked", 0) or counts.get("needs_retry", 0):
        return "blocked"
    return "idle"


def _next_safe_action(
    operator_readiness: OperatorReadinessSnapshot,
    batches: list[SchedulerBatch],
    tasks: list[SchedulerTask],
    blocked_dependencies: list[SchedulerDependencyBlocker],
) -> str:
    if (
        operator_readiness.next_safe_action.kind in {"repair_goal_lifecycle", "inspect_stale_directive"}
        and operator_readiness.next_safe_action.command
    ):
        return operator_readiness.next_safe_action.command
    if batches:
        return batches[0].next_safe_action
    for state in ("stale", "needs_retry", "blocked", "ready_to_promote", "ready_to_verify"):
        for task in tasks:
            if task.scheduler_state == state:
                return task.next_safe_action
    if blocked_dependencies:
        return blocked_dependencies[0].next_safe_action
    return "devflow task list"


def _max_parallel_recommendation(batches: list[SchedulerBatch]) -> int:
    if not batches:
        return 4
    return max(1, min(4, max(len(batch.task_ids or batch.lane_ids) for batch in batches)))


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result
