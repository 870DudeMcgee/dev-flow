from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from devflow.control_room.log_sanitizer import sanitize_log_line
from devflow.control_room.models import TaskRecord
from devflow.control_room.paths import task_dir
from devflow.control_room.persistence import get_task, list_tasks
from devflow.control_room.qwopus_evidence import qwopus_suggested_next_action
from devflow.control_room.readiness import promotion_readiness_errors
from devflow.control_room.task_closure import closure_next_action, read_closure
from devflow.control_room.task_next_gate import (
    DashboardActionAdapter,
    resolve_task_next_gate,
)


class ProjectedNextAction(BaseModel):
    label: str
    task_id: str | None = None
    command: str | None = None
    reason: str


class ReviewCapsuleProjection(BaseModel):
    verification_text: str
    promotion_readiness_text: str
    promotion_preview_text: str
    decision: str
    safe_next_actions: list[str]


class TaskStatusProjection(BaseModel):
    task: TaskRecord
    task_path: Path
    verification_status: str
    verification_exit_code: int | None
    verification_log_path: str | None
    verification_command: str | None
    merge_ready: bool | None
    readiness_reasons: list[str]
    promotion_ready: bool = False
    promotion_blockers: list[str] = Field(default_factory=list)
    suggested_next_action: str
    manual_agent_state: str | None = None
    manual_agent_handoff_path: str | None = None
    manual_agent_result_path: str | None = None
    manual_agent_question: str | None = None
    manual_agent_failure: str | None = None
    closure_outcome: str | None = None

    model_config = {"arbitrary_types_allowed": True}

    @property
    def verify_token(self) -> str:
        return format_verify_token(self.verification_status, self.verification_exit_code)

    @property
    def latest(self) -> str:
        return sanitize_log_line(self.task.latest_log_line) or self.task.last_event or ""

    @property
    def display_status(self) -> str:
        if self.task.status == "closed":
            outcome = self.closure_outcome or self.task.close_outcome
            return f"closed/{outcome}" if outcome else "closed"
        if self.task.status == "blocked" and self.manual_agent_state:
            if self.manual_agent_state == "awaiting_human":
                return "awaiting_human"
            if self.manual_agent_state == "blocked":
                return "blocked_question"
            if self.manual_agent_state == "failed":
                return "worker_failed"
            if self.manual_agent_state == "result_present":
                return "result_present"
        return self.task.status

    @property
    def is_blocked(self) -> bool:
        if self.task.status == "closed":
            return False
        if self.manual_agent_state == "result_present":
            return False
        return (
            self.display_status in ("blocked", "blocked_question", "awaiting_human")
            or self.manual_agent_state == "blocked"
            or self.manual_agent_question is not None
            or self.task.status == "blocked"
        )

    @property
    def failed_verification(self) -> bool:
        if self.task.status == "closed":
            return False
        return self.task.status == "verification_failed" or self.verification_status == "failed"

    @property
    def needs_verification(self) -> bool:
        if not self.is_active:
            return False
        if self.failed_verification:
            return False
        if self.task.status == "complete":
            return True
        if self.manual_agent_state == "result_present" and self.verification_status != "passed":
            return True
        return self.verification_status in ("not_run", "pending") and self.task.status not in (
            "promoted",
            "verified",
            "created",
            "blocked",
        )

    @property
    def is_verified(self) -> bool:
        return self.task.status == "verified" or self.verification_status == "passed"

    @property
    def ready_to_promote(self) -> bool:
        if not self.is_active:
            return False
        return self.is_verified and self.promotion_ready

    @property
    def is_active(self) -> bool:
        return self.task.status not in ("closed", "promoted")

    @property
    def is_worker_failed(self) -> bool:
        if not self.is_active:
            return False
        return self.task.status == "worker_failed" or self.display_status == "worker_failed"

    @property
    def is_timeout(self) -> bool:
        if not self.is_active:
            return False
        return self.task.status == "timeout"

    @property
    def dashboard_action_priority(self) -> int:
        if not self.is_active:
            return 100
        if self.is_blocked:
            return 10
        if self.failed_verification:
            return 20
        if self.is_worker_failed:
            return 30
        if self.is_timeout:
            return 35
        if self.ready_to_promote:
            return 40
        if self.needs_verification:
            return 50
        if self.task.status == "created":
            return 70
        if self.task.status == "running":
            return 80
        if self.task.status != "promoted":
            return 90
        return 100

    @property
    def dashboard_next_action(self) -> ProjectedNextAction:
        task_id = self.task.id

        # Use canonical resolver for patch-gate states before falling through.
        _root = self.task_path.parents[2]  # .devflow/tasks/<task> → repo root
        try:
            _canonical = resolve_task_next_gate(_root, task_id)
        except Exception:
            _canonical = None

        gate_name = getattr(_canonical, "gate", "") if _canonical else ""
        if gate_name in ("review_patch", "patch_dry_run", "apply_patch"):
            adapter = DashboardActionAdapter.from_gate(_canonical)  # type: ignore[arg-type]
            return ProjectedNextAction(
                label=adapter["label"],
                task_id=task_id,
                command=adapter["command"],
                reason=adapter["reason"],
            )

        if self.is_blocked:
            return ProjectedNextAction(
                label="Resolve blocker",
                task_id=task_id,
                command=f"devflow task show {task_id}",
                reason="Manual worker blocked on a question.",
            )
        if self.failed_verification:
            return ProjectedNextAction(
                label="Inspect verification failure",
                task_id=task_id,
                command=f"devflow task log {task_id} --verify --tail 80",
                reason="Verification failed and needs inspection before rerun.",
            )
        if self.is_worker_failed:
            return ProjectedNextAction(
                label="Inspect worker failure",
                task_id=task_id,
                command=f"devflow task log {task_id} --tail 80",
                reason="Worker failed and logs should be inspected.",
            )
        if self.is_timeout:
            return ProjectedNextAction(
                label="Inspect timeout",
                task_id=task_id,
                command=f"devflow task log {task_id} --tail 80",
                reason="Worker timed out.",
            )
        if self.ready_to_promote:
            return ProjectedNextAction(
                label="Preview promotion",
                task_id=task_id,
                command=f"devflow task promote-preview {task_id}",
                reason="Verification passed; user should review promotion before promote.",
            )
        if self.needs_verification:
            return ProjectedNextAction(
                label="Run verification",
                task_id=task_id,
                command=f"devflow task verify {task_id} --shell \"<command>\"",
                reason="Worker completed but verification has not passed.",
            )
        if self.task.status == "created":
            return ProjectedNextAction(
                label="Run task",
                task_id=task_id,
                command=f"devflow task run {task_id} --worker shell -- <command>",
                reason="Task exists but no worker has run.",
            )
        if self.task.status == "running":
            return ProjectedNextAction(
                label="Inspect task",
                task_id=task_id,
                command=f"devflow task show {task_id}",
                reason="Task is running or in progress.",
            )
        return ProjectedNextAction(
            label="Inspect task",
            task_id=task_id,
            command=f"devflow task show {task_id}",
            reason="No safer automated action was inferred.",
        )


def list_task_status_projections(root: Path) -> list[TaskStatusProjection]:
    return [build_task_status_projection(root, task.id, task=task) for task in list_tasks(root)]


def choose_task_focus_projection(projections: list[TaskStatusProjection]) -> TaskStatusProjection | None:
    if not projections:
        return None
    return sorted(projections, key=_dashboard_priority_sort_key)[0]


def choose_task_dashboard_action(
    projections: list[TaskStatusProjection],
    *,
    max_priority: int | None = None,
) -> ProjectedNextAction | None:
    candidates = [
        projection
        for projection in projections
        if projection.dashboard_action_priority < 100
        and (max_priority is None or projection.dashboard_action_priority <= max_priority)
    ]
    if not candidates:
        return None
    return sorted(candidates, key=_dashboard_priority_sort_key)[0].dashboard_next_action


def _dashboard_priority_sort_key(projection: TaskStatusProjection) -> tuple[int, float, str]:
    return (
        projection.dashboard_action_priority,
        -projection.task.updated_at.timestamp() if projection.task.updated_at else 0.0,
        projection.task.id,
    )


def format_verify_token(verification_status: str | None, verification_exit_code: int | None) -> str:
    status = verification_status or "not_run"
    if status == "passed":
        return "passed"
    if status == "failed":
        if verification_exit_code is not None:
            return f"failed(exit={verification_exit_code})"
        return "failed"
    return status


def build_task_status_projection(root: Path, task_id: str, task: TaskRecord | None = None) -> TaskStatusProjection:
    record = task or get_task(root, task_id)
    path = task_dir(root, record.id)
    verification = _read_verification(path / "verification.json", record)
    merge_ready, readiness_reasons = _read_merge_readiness(path / "merge-readiness.json")
    promotion_errors = promotion_readiness_errors(record, path)
    if merge_ready is None:
        readiness_reasons = []

    verification_status = _string_or_default(verification.get("status"), record.verification_status) or "not_run"
    verification_exit_code = _int_or_none(verification.get("exit_code"), record.verification_exit_code)
    verification_log_path = _string_or_default(verification.get("log_path"), record.verification_log_path)
    verification_command = _string_or_default(verification.get("command"), record.verification_command)
    manual_evidence = _manual_evidence(root, record)
    closure = read_closure(root, record.id) if record.status == "closed" else None
    qwopus_next_action = None
    if record.status != "closed":
        qwopus_next_action = qwopus_suggested_next_action(
            root,
            record.id,
            task_status=record.status,
            verification_status=verification_status,
        )

    return TaskStatusProjection(
        task=record,
        task_path=path,
        verification_status=verification_status,
        verification_exit_code=verification_exit_code,
        verification_log_path=verification_log_path,
        verification_command=verification_command,
        merge_ready=merge_ready,
        readiness_reasons=readiness_reasons,
        promotion_ready=not promotion_errors,
        promotion_blockers=promotion_errors,
        suggested_next_action=qwopus_next_action or _suggest_next_action(
            record.status,
            verification_status,
            record.id,
            closed_next_action=closure_next_action(root, record) if closure else None,
            promotion_ready=not promotion_errors,
            manual_agent_state=manual_evidence.state if manual_evidence is not None else None,
        ),
        manual_agent_state=manual_evidence.state if manual_evidence is not None else None,
        manual_agent_handoff_path=manual_evidence.handoff_path if manual_evidence is not None else None,
        manual_agent_result_path=manual_evidence.result_path if manual_evidence is not None else None,
        manual_agent_question=manual_evidence.question if manual_evidence is not None else None,
        manual_agent_failure=manual_evidence.failure if manual_evidence is not None else None,
        closure_outcome=str(closure.get("outcome")) if closure and closure.get("outcome") else record.close_outcome,
    )


def _manual_evidence(root: Path, record: TaskRecord):
    if record.worker != "devflow-manual-codex-worker":
        return None
    from devflow.control_room.manual_worker import read_manual_agent_evidence

    return read_manual_agent_evidence(root, record.id, record.worker)


def _read_verification(path: Path, task: TaskRecord) -> dict[str, Any]:
    fallback = {
        "task_id": task.id,
        "status": task.verification_status,
        "exit_code": task.verification_exit_code,
        "log_path": task.verification_log_path,
        "command": task.verification_command,
    }
    if not path.exists():
        return fallback
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return fallback
    if not isinstance(data, dict):
        return fallback
    if data.get("task_id") not in (None, task.id):
        return fallback
    return {**fallback, **data}


def _read_merge_readiness(path: Path) -> tuple[bool | None, list[str]]:
    if not path.exists():
        return None, []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None, []
    if not isinstance(data, dict):
        return None, []
    ready = data.get("ready")
    if not isinstance(ready, bool):
        return None, []
    reasons = data.get("reasons", [])
    if not isinstance(reasons, list):
        reasons = []
    return ready, [str(reason) for reason in reasons]


def _string_or_default(value: Any, default: str | None) -> str | None:
    return value if isinstance(value, str) else default


def _int_or_none(value: Any, default: int | None) -> int | None:
    return value if isinstance(value, int) else default


def _suggest_next_action(
    status: str,
    verification_status: str,
    task_id: str,
    closed_next_action: str | None = None,
    promotion_ready: bool = False,
    manual_agent_state: str | None = None,
) -> str:
    if manual_agent_state is not None:
        if manual_agent_state == "awaiting_human":
            return "Manual handoff generated. Awaiting human workspace changes and result.md."
        if manual_agent_state == "blocked":
            return "Manual worker blocked on a question. Resolve the question in questions.jsonl."
        if manual_agent_state == "failed":
            return "Manual worker failed. Inspect worker_failed.json."
        if manual_agent_state == "result_present":
            if verification_status == "passed" and promotion_ready:
                return f"Task is verified. Review promotion preview, then run 'devflow task promote {task_id}' when ready."
            if verification_status == "passed":
                return "Task is verified, but promotion readiness evidence is incomplete. Re-run verification before promotion."
            if verification_status == "failed":
                return f"Fix the failure and re-run verification using 'devflow task verify {task_id} -- <command>'"
            return f"Verify the task using 'devflow task verify {task_id} -- <command>'"

    if status == "closed":
        return closed_next_action or "none"
    if status == "created":
        return f"Run the task using 'devflow task run {task_id} --worker shell -- <command>'"
    if status == "running":
        return "Monitor the execution or wait for the task to complete."
    if status == "complete":
        return f"Verify the task using 'devflow task verify {task_id} -- <command>'"
    if status == "promoted":
        return "Task has been promoted. Review main checkout changes, then commit manually if appropriate."
    if status == "verified" and promotion_ready:
        return f"Task is verified. Review promotion preview, then run 'devflow task promote {task_id}' when ready."
    if status == "verified" or verification_status == "passed":
        return "Task is verified, but promotion readiness evidence is incomplete. Re-run verification before promotion."
    if status == "verification_failed" or verification_status == "failed":
        return f"Fix the failure and re-run verification using 'devflow task verify {task_id} -- <command>'"
    if status == "worker_failed":
        return f"Inspect the logs, fix the failure, and re-run using 'devflow task run {task_id} --worker shell -- <command>'"
    if status == "timeout":
        return f"Re-run the task with an increased timeout using 'devflow task run {task_id} --timeout-seconds <seconds> --worker shell -- <command>'"
    if status == "blocked":
        return "Resolve the workspace or safety block before running again."
    return "Check task status and logs for the next logical step."


def build_review_capsule_projection(
    task: TaskRecord,
    verification: dict[str, Any] | None,
    verification_note: str,
    preview: dict[str, Any] | None,
    preview_note: str,
) -> ReviewCapsuleProjection:
    decision, actions = _review_capsule_decision_and_actions(
        task,
        verification,
        preview,
        preview_note,
    )
    return ReviewCapsuleProjection(
        verification_text=_review_capsule_verification_text(task, verification, verification_note),
        promotion_readiness_text=_review_capsule_promotion_readiness_text(preview, preview_note),
        promotion_preview_text=_review_capsule_promotion_preview_text(preview, preview_note),
        decision=decision,
        safe_next_actions=actions,
    )


def _review_capsule_verification_text(task: TaskRecord, payload: dict[str, Any] | None, note: str) -> str:
    if payload is None:
        return "missing (no verification.json)" if note.startswith("missing") else note
    status = payload.get("status") or task.verification_status
    exit_code = payload.get("exit_code")
    if status == "passed":
        return "PASS"
    if status == "failed":
        return f"FAIL (exit code {exit_code})" if exit_code is not None else "FAIL"
    if status == "not_run":
        return "NOT RUN"
    return str(status or "unknown")


def _review_capsule_promotion_readiness_text(payload: dict[str, Any] | None, note: str) -> str:
    if payload is None:
        return note
    readiness = payload.get("promotion_readiness")
    if isinstance(readiness, str) and readiness:
        if readiness == "ready" and payload.get("human_approval_required") is True:
            return "ready (human approval required)"
        return readiness
    return "available"


def _review_capsule_promotion_preview_text(payload: dict[str, Any] | None, note: str) -> str:
    if payload is None:
        return note
    readiness = payload.get("promotion_readiness")
    if readiness == "ready" and payload.get("human_approval_required") is True:
        return "PASS (human approval required)"
    if readiness == "ready":
        return "PASS"
    if isinstance(readiness, str) and readiness:
        return f"not ready ({readiness})"
    return "available"


def _review_capsule_decision_and_actions(
    task: TaskRecord,
    verification: dict[str, Any] | None,
    preview: dict[str, Any] | None,
    preview_note: str,
) -> tuple[str, list[str]]:
    verification_status = (verification or {}).get("status") or task.verification_status
    if verification is None or verification_status == "not_run":
        return (
            "Run verification for this task.",
            [f"run verification {task.id}", f"reject/close {task.id}"],
        )
    if verification_status != "passed":
        return (
            "Needs changes before promotion.",
            [f"needs changes {task.id}", f"reject/close {task.id}"],
        )
    if preview is None:
        return (
            "Run promotion preview before promoting.",
            [f"run promotion preview {task.id}", f"reject/close {task.id}"],
        )
    if preview.get("promotion_readiness") == "ready" and preview.get("human_approval_required") is True:
        return (
            "Human approval required before promotion.",
            [f"review preview and approve {task.id}", f"reject/close {task.id}"],
        )
    if preview.get("promotion_readiness") == "ready":
        return (
            "Promote or reject this task.",
            [f"promote {task.id}", f"reject/close {task.id}"],
        )
    if preview_note == "current command output":
        return (
            "Review promotion preview and decide whether this needs changes.",
            [f"needs changes {task.id}", f"reject/close {task.id}"],
        )
    return (
        "Needs changes before promotion.",
        [f"needs changes {task.id}", f"reject/close {task.id}"],
    )
