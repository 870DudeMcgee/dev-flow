from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from devflow.legacy.control_room.models import TASK_SCHEMA_VERSION, TaskRecord, TaskStatus
from devflow.legacy.control_room.paths import relative_path, task_dir
from devflow.legacy.control_room.persistence import append_event, atomic_write_text, save_task, utc_now
from devflow.legacy.control_room.readiness import readiness_state


EventPosition = Literal["before_save", "after_save"]


def append_task_event(root: Path, task_id: str, event_type: str, event_payload: dict[str, Any]) -> None:
    append_event(root, task_id, event_type, event_payload)


def write_task_state(root: Path, task: TaskRecord, *, write_readiness: bool = True) -> None:
    task_path = task_dir(root, task.id)
    save_task(task_path, task)
    if write_readiness:
        write_merge_readiness(root, task_path, task)


def apply_lifecycle_metadata(
    task: TaskRecord,
    *,
    event_type: str | None = None,
    status: TaskStatus | None = None,
    updated_at: datetime | None = None,
) -> TaskRecord:
    if status is not None:
        task.status = status
    if updated_at is not None:
        task.updated_at = updated_at
    if event_type is not None:
        task.last_event = event_type
    return task


def record_task_update(
    root: Path,
    task: TaskRecord,
    *,
    event_type: str,
    event_payload: dict[str, Any],
    status: TaskStatus | None = None,
    updated_at: datetime | None = None,
    write_readiness: bool = True,
    event_position: EventPosition = "after_save",
) -> TaskRecord:
    apply_lifecycle_metadata(task, event_type=event_type, status=status, updated_at=updated_at)
    if event_position == "before_save":
        append_task_event(root, task.id, event_type, event_payload)
    write_task_state(root, task, write_readiness=write_readiness)
    if event_position == "after_save":
        append_task_event(root, task.id, event_type, event_payload)
    return task


def invalidate_verification_after_workspace_mutation(
    root: Path,
    task: TaskRecord,
    *,
    patch_application: dict[str, Any],
) -> TaskRecord:
    task_path = task_dir(root, task.id)
    status = "closed" if task.status == "closed" else "complete"
    task.verification_status = "not_run"
    task.verification_exit_code = None
    task.verification_log_path = None
    apply_lifecycle_metadata(task, event_type="patch_applied", status=status, updated_at=utc_now())
    write_pending_verification_after_patch(root, task_path, task, patch_application)
    write_task_state(root, task)
    return task


def write_pending_verification_after_patch(
    root: Path,
    task_path: Path,
    task: TaskRecord,
    patch_application: dict[str, Any],
) -> None:
    payload = {
        "schema_version": TASK_SCHEMA_VERSION,
        "task_id": task.id,
        "workspace": task.workspace,
        "command": task.verification_command,
        "status": "not_run",
        "task_status": task.status,
        "exit_code": None,
        "latest_log_line": None,
        "log_path": f".devflow/tasks/{task.id}/logs/verify.log",
        "finished_at": None,
        "invalidated_by_patch_hash": patch_application.get("patch_hash"),
        "invalidated_by_patch_application_path": relative_path(root, task_path / "patch-application.json"),
        "invalidated_at": patch_application.get("applied_at"),
    }
    atomic_write_text(task_path / "verification.json", json.dumps(payload, indent=2) + "\n")


def write_merge_readiness(root: Path, task_path: Path, task: TaskRecord) -> None:
    finished_at = None
    verification_json_path = task_path / "verification.json"
    if verification_json_path.exists():
        try:
            v_data = json.loads(verification_json_path.read_text(encoding="utf-8"))
            finished_at = v_data.get("finished_at")
        except Exception:
            pass

    ready, reasons = readiness_state(task, task_path)

    payload = {
        "schema_version": TASK_SCHEMA_VERSION,
        "task_id": task.id,
        "ready": ready,
        "reasons": reasons,
        "verification_status": task.verification_status,
        "verification_exit_code": task.verification_exit_code,
        "verification_finished_at": finished_at,
        "verification_log_path": task.verification_log_path,
        "workspace_dirty": task.workspace_dirty,
        "workspace_branch": task.branch_name,
        "workspace_commit": task.workspace_commit,
        "generated_at": utc_now().isoformat(),
    }
    atomic_write_text(task_path / "merge-readiness.json", json.dumps(payload, indent=2) + "\n")
