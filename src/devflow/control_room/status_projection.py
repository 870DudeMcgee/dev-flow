from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from devflow.control_room.log_sanitizer import sanitize_log_line
from devflow.control_room.models import TaskRecord
from devflow.control_room.paths import task_dir
from devflow.control_room.persistence import get_task, list_tasks
from devflow.control_room.qwopus_evidence import qwopus_suggested_next_action
from devflow.control_room.readiness import promotion_readiness_errors


class TaskStatusProjection(BaseModel):
    task: TaskRecord
    task_path: Path
    verification_status: str
    verification_exit_code: int | None
    verification_log_path: str | None
    verification_command: str | None
    merge_ready: bool | None
    readiness_reasons: list[str]
    suggested_next_action: str
    manual_agent_state: str | None = None
    manual_agent_handoff_path: str | None = None
    manual_agent_result_path: str | None = None
    manual_agent_question: str | None = None
    manual_agent_failure: str | None = None

    model_config = {"arbitrary_types_allowed": True}

    @property
    def verify_token(self) -> str:
        return format_verify_token(self.verification_status, self.verification_exit_code)

    @property
    def latest(self) -> str:
        return sanitize_log_line(self.task.latest_log_line) or self.task.last_event or ""

    @property
    def display_status(self) -> str:
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


def list_task_status_projections(root: Path) -> list[TaskStatusProjection]:
    return [build_task_status_projection(root, task.id, task=task) for task in list_tasks(root)]


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
        suggested_next_action=qwopus_next_action or _suggest_next_action(
            record.status,
            verification_status,
            record.id,
            promotion_ready=not promotion_errors,
            manual_agent_state=manual_evidence.state if manual_evidence is not None else None,
        ),
        manual_agent_state=manual_evidence.state if manual_evidence is not None else None,
        manual_agent_handoff_path=manual_evidence.handoff_path if manual_evidence is not None else None,
        manual_agent_result_path=manual_evidence.result_path if manual_evidence is not None else None,
        manual_agent_question=manual_evidence.question if manual_evidence is not None else None,
        manual_agent_failure=manual_evidence.failure if manual_evidence is not None else None,
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
