from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from devflow.legacy.control_room.models import TASK_SCHEMA_VERSION, TaskRecord
from devflow.legacy.control_room.persistence import atomic_write_text, utc_now
from devflow.legacy.control_room.readiness import readiness_state


BASELINE_TASK_ARTIFACTS: tuple[str, ...] = (
    "task.yaml",
    "events.jsonl",
    "questions.jsonl",
    "result.md",
    "verification.json",
    "logs/worker.log",
    "logs/verify.log",
    "merge-readiness.json",
)


def missing_task_baseline_artifacts(task_path: Path) -> list[str]:
    return [name for name in BASELINE_TASK_ARTIFACTS if not (task_path / name).exists()]


def ensure_task_baseline_artifacts(
    task_path: Path,
    *,
    task_id: str,
    workspace_rel: str,
    task: TaskRecord | None = None,
) -> list[str]:
    """Create missing baseline task artifacts without truncating existing evidence."""
    task_path.mkdir(parents=True, exist_ok=True)
    (task_path / "logs").mkdir(parents=True, exist_ok=True)

    created: list[str] = []

    for name in ("events.jsonl", "questions.jsonl", "logs/worker.log", "logs/verify.log"):
        path = task_path / name
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()
            created.append(name)

    result_path = task_path / "result.md"
    if not result_path.exists():
        atomic_write_text(result_path, f"# Result: {task_id}\n\nNot run yet.\n")
        created.append("result.md")

    verification_path = task_path / "verification.json"
    if not verification_path.exists():
        atomic_write_text(
            verification_path,
            json.dumps(_default_verification(task_id, workspace_rel, task), indent=2) + "\n",
        )
        created.append("verification.json")

    readiness_path = task_path / "merge-readiness.json"
    if not readiness_path.exists():
        atomic_write_text(
            readiness_path,
            json.dumps(_default_merge_readiness(task_path, task_id, task), indent=2) + "\n",
        )
        created.append("merge-readiness.json")

    return created


def _default_verification(task_id: str, workspace_rel: str, task: TaskRecord | None) -> dict[str, Any]:
    return {
        "schema_version": TASK_SCHEMA_VERSION,
        "task_id": task_id,
        "workspace": workspace_rel,
        "command": task.verification_command if task else None,
        "status": task.verification_status if task else "not_run",
        "task_status": task.status if task else "created",
        "exit_code": task.verification_exit_code if task else None,
        "latest_log_line": task.latest_log_line if task else None,
        "log_path": f".devflow/tasks/{task_id}/logs/verify.log",
        "finished_at": task.finished_at.isoformat() if task and task.finished_at else None,
    }


def _default_merge_readiness(task_path: Path, task_id: str, task: TaskRecord | None) -> dict[str, Any]:
    ready = False
    reasons = ["verification has not passed"]
    if task is not None:
        ready, reasons = readiness_state(task, task_path)
    return {
        "schema_version": TASK_SCHEMA_VERSION,
        "task_id": task_id,
        "ready": ready,
        "reasons": reasons,
        "verification_status": task.verification_status if task else "not_run",
        "verification_exit_code": task.verification_exit_code if task else None,
        "verification_finished_at": None,
        "verification_log_path": task.verification_log_path if task else None,
        "workspace_dirty": task.workspace_dirty if task else None,
        "workspace_branch": task.branch_name if task else None,
        "workspace_commit": task.workspace_commit if task else None,
        "generated_at": utc_now().isoformat(),
    }
