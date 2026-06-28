from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from devflow.control_room.browser_task_capabilities import scope_task_command
from devflow.control_room.dashboard import DashboardNextAction
from devflow.control_room.paths import task_dir
from devflow.control_room.status_projection import TaskStatusProjection


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


def _review_queue(tasks: list[Any]) -> list[TaskWorkbenchReviewQueueItem]:
    review_lanes = {"blocked", "failed", "ready_to_promote", "needs_review", "needs_verification"}
    rows: list[TaskWorkbenchReviewQueueItem] = []
    for task in tasks:
        if task.lane not in review_lanes:
            continue
        detail = task.review_detail
        rows.append(
            TaskWorkbenchReviewQueueItem(
                task_id=task.id,
                title=task.title,
                lane=task.lane,
                priority=detail.review_priority,
                reason=detail.review_reason,
                command=detail.review_command,
                evidence_paths=detail.evidence_paths,
                review_state=detail.review_state,
                review_score=detail.review_score,
                operator_summary=detail.operator_summary,
                blockers=detail.blockers,
                changed_files=detail.changed_files,
                evidence_count=len(detail.evidence_paths),
            )
        )
    rank = {"blocked": 0, "failed": 1, "ready_to_promote": 2, "needs_review": 3, "needs_verification": 4}
    return sorted(rows, key=lambda row: (rank.get(row.lane, 9), row.task_id))


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
                command=scope_task_command(command, project_id) if command else None,
            )
        )
    return receipts


def _review_loop_summary(
    tasks: list[Any],
    *,
    review_queue: list[TaskWorkbenchReviewQueueItem],
    promotion_candidates: list[Any],
    next_action: DashboardNextAction,
) -> TaskWorkbenchReviewLoop:
    needs_verification = [task for task in tasks if task.lane == "needs_verification"]
    needs_review = [task for task in tasks if task.lane == "needs_review"]
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
    elif needs_review:
        status = "needs_review"
        headline = f"{len(needs_review)} task{'s' if len(needs_review) != 1 else ''} need{'s' if len(needs_review) == 1 else ''} review"
    elif needs_verification:
        status = "needs_verification"
        headline = f"{len(needs_verification)} task{'s' if len(needs_verification) != 1 else ''} need{'s' if len(needs_verification) == 1 else ''} verification"
    else:
        status = "watching"
        headline = "No browser approval items are waiting"

    promotion_command = promotion_candidates[0].command if promotion_candidates else None
    blocked_command = blocked_decisions[0].command if status == "needs_human_decision" and blocked_decisions else None
    ready_command = ready_to_promote[0].next_action.command if ready_to_promote else None
    review_command = needs_review[0].next_action.command if needs_review else None
    verification_command = needs_verification[0].next_action.command if needs_verification else None
    command = blocked_command
    if not command and status == "ready_to_promote":
        command = promotion_command or ready_command
    if not command and status == "needs_review":
        command = review_command
    if not command and status == "needs_verification":
        command = verification_command
    if not command:
        command = next_action.command or promotion_command or ready_command or review_command or verification_command or "devflow dashboard"

    from devflow.control_room.browser_action_policy import (
        get_browser_allowed_mutations,
        get_browser_blocked_mutations,
    )

    return TaskWorkbenchReviewLoop(
        status=status,
        headline=headline,
        next_safe_action=command,
        browser_allowed_mutations=get_browser_allowed_mutations(),
        browser_blocked_mutations=get_browser_blocked_mutations(),
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


def _worker_activity(tasks: list[Any]) -> list[TaskWorkbenchWorkerActivity]:
    grouped: dict[str, list[Any]] = {}
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


def _worker_state(open_tasks: list[Any]) -> str:
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


def _worker_task_failed(task: Any) -> bool:
    return "fail" in task.verification_status.lower() or "failed" in task.display_status.lower()


def _worker_task_verified_or_ready(task: Any) -> bool:
    return (
        "pass" in task.verification_status.lower()
        or bool(task.promotion_ready or task.merge_ready)
        or task.lane == "closed"
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
