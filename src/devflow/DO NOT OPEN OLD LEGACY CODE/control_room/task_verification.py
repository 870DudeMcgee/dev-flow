from __future__ import annotations

import json
import shlex
from pathlib import Path

from devflow.legacy.control_room.git_worktree import (
    is_git_worktree_task,
    refresh_git_worker_evidence,
    worker_id_for_task,
)
from devflow.legacy.control_room.locks import task_mutation_lock
from devflow.legacy.control_room.models import TASK_SCHEMA_VERSION, TaskRecord
from devflow.legacy.control_room.patch_evidence import read_patch_application_evidence
from devflow.legacy.control_room.paths import relative_path, task_dir, task_worker_dir
from devflow.legacy.control_room.persistence import atomic_write_text, get_task, utc_now
from devflow.legacy.control_room.promotion import current_main_head
from devflow.legacy.control_room.task_command_safety import looks_destructive_command
from devflow.legacy.control_room.task_lifecycle import (
    append_task_event,
    apply_lifecycle_metadata,
    record_task_update,
)
from devflow.legacy.control_room.task_workspace import validated_task_workspace
from devflow.legacy.control_room.verification import VerificationResult, run_verification_command


def verify_task_command(root: Path, task_id: str, command: list[str], timeout_seconds: int = 120) -> TaskRecord:
    if not command:
        raise ValueError("Verification requires a command after '--'.")
    if looks_destructive_command(command):
        with task_mutation_lock(root, task_id, "verify"):
            append_task_event(root, task_id, "verification_refused", {"command": command})
        raise ValueError("Refusing obviously destructive verification command.")

    with task_mutation_lock(root, task_id, "verify"):
        task = get_task(root, task_id)
        task_path = task_dir(root, task_id)
        workspace = validated_task_workspace(root, task)
        verify_log = task_path / "logs" / "verify.log"

        append_task_event(root, task_id, "verification_started", {"command": command, "cwd": task.workspace})
        result = run_verification_command(workspace, command, verify_log, timeout_seconds=timeout_seconds)

        task.verification_status = result.status
        task.verification_command = shlex.join(command)
        task.verification_exit_code = result.exit_code
        task.verification_log_path = relative_path(root, result.log_file)
        task.latest_log_line = result.latest_log_line
        if is_git_worktree_task(task):
            state = refresh_git_worker_evidence(root, task, worker_id=worker_id_for_task(task))
            task.workspace_dirty = bool(state["dirty"])
        apply_lifecycle_metadata(
            task,
            event_type="verification_finished",
            status="verified" if result.status == "passed" else "verification_failed",
            updated_at=utc_now(),
        )
        _write_verification_json(root, task_path, task, result)
        _write_verification_report(task_path, task, result)
        record_task_update(
            root,
            task,
            event_type="verification_finished",
            event_payload={"status": result.status, "exit_code": result.exit_code, "log_path": task.verification_log_path},
        )
        return task


def _write_verification_json(root: Path, task_path: Path, task: TaskRecord, result: VerificationResult) -> None:
    payload = {
        "schema_version": TASK_SCHEMA_VERSION,
        "task_id": task.id,
        "workspace": task.workspace,
        "command": result.command,
        "status": result.status,
        "task_status": task.status,
        "exit_code": result.exit_code,
        "latest_log_line": result.latest_log_line,
        "log_path": relative_path(root, result.log_file),
        "finished_at": utc_now().isoformat(),
    }
    latest_patch = read_patch_application_evidence(task_path)
    if latest_patch is not None and latest_patch.get("patch_hash"):
        payload.update(
            {
                "verified_patch_hash": latest_patch.get("patch_hash"),
                "verified_patch_application_path": relative_path(root, task_path / "patch-application.json"),
                "patch_applied_at": latest_patch.get("applied_at"),
            }
        )
    if is_git_worktree_task(task):
        state = refresh_git_worker_evidence(root, task, worker_id=worker_id_for_task(task))
        payload.update(
            {
                "worker_id": state["worker_id"],
                "branch": state["worker_branch"],
                "verified_commit": state["head_commit"],
                "base_commit": state["base_commit"],
                "main_head_at_verification": current_main_head(root),
                "dirty_at_verification": state["dirty"],
            }
        )
        worker_verification = task_worker_dir(root, task.id, state["worker_id"]) / "verification.json"
        atomic_write_text(worker_verification, json.dumps(payload, indent=2) + "\n")
    atomic_write_text(task_path / "verification.json", json.dumps(payload, indent=2) + "\n")


def _write_verification_report(task_path: Path, task: TaskRecord, result: VerificationResult) -> None:
    existing = (task_path / "result.md").read_text(encoding="utf-8") if (task_path / "result.md").exists() else ""
    if "\n## Verification\n" in existing:
        existing = existing.split("\n## Verification\n", 1)[0]
    verification = (
        "\n## Verification\n\n"
        f"Status: {result.status}\n\n"
        f"Task Status: {task.status}\n\n"
        f"Command:\n\n```bash\n{' '.join(result.command)}\n```\n\n"
        f"Exit Code: {result.exit_code if result.exit_code is not None else 'none'}\n\n"
        f"Log: {result.log_file}\n"
    )
    atomic_write_text(task_path / "result.md", existing.rstrip() + verification)
