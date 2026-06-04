from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from devflow.control_room.models import TASK_SCHEMA_VERSION, TaskRecord
from devflow.control_room.paths import relative_path, task_dir, tasks_dir
from devflow.control_room.persistence import atomic_write_text, list_tasks, utc_now
from devflow.control_room.task_closure import read_closure


class TaskPruneError(ValueError):
    pass


@dataclass(frozen=True)
class _PruneDecision:
    task_id: str
    status: str
    path: str | None = None
    reason: str | None = None


_DURATION_PATTERN = re.compile(r"^(?P<value>\d+)(?P<unit>[smhdw])$")
_DURATION_SECONDS = {
    "s": 1,
    "m": 60,
    "h": 60 * 60,
    "d": 24 * 60 * 60,
    "w": 7 * 24 * 60 * 60,
}


def prune_closed_tasks(root: Path, *, older_than: str, apply: bool) -> dict[str, Any]:
    older_than_seconds = parse_duration_seconds(older_than)
    now = utc_now()
    cutoff = now - timedelta(seconds=older_than_seconds)

    would_prune: list[str] = []
    pruned: list[str] = []
    skipped: list[dict[str, str]] = []
    refused: list[dict[str, str]] = []

    for task in list_tasks(root):
        decision = _prune_decision(root, task, cutoff)
        if decision.status == "eligible":
            if decision.path is None:
                raise TaskPruneError(f"Internal prune decision missing path for {task.id}.")
            if apply:
                shutil.rmtree(task_dir(root, task.id))
                pruned.append(decision.path)
            else:
                would_prune.append(decision.path)
        elif decision.status == "skipped":
            skipped.append({"task_id": decision.task_id, "reason": decision.reason or "skipped"})
        elif decision.status == "refused":
            refused.append({"task_id": decision.task_id, "reason": decision.reason or "refused"})

    generated_at = now.isoformat()
    run_id = _run_id(now)
    audit_path = root / ".devflow" / "prune-runs" / f"{run_id}.json"
    result = {
        "schema_version": TASK_SCHEMA_VERSION,
        "run_id": run_id,
        "generated_at": generated_at,
        "older_than": older_than,
        "older_than_seconds": older_than_seconds,
        "applied": apply,
        "mode": "apply" if apply else "preview",
        "would_prune": would_prune,
        "pruned": pruned,
        "skipped": skipped,
        "refused": refused,
        "audit_path": relative_path(root, audit_path),
    }
    atomic_write_text(audit_path, json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def parse_duration_seconds(value: str) -> int:
    match = _DURATION_PATTERN.match(value.strip())
    if match is None:
        raise TaskPruneError("Invalid --older-than duration. Use a value like 30d, 12h, 45m, or 0s.")
    amount = int(match.group("value"))
    return amount * _DURATION_SECONDS[match.group("unit")]


def _prune_decision(root: Path, task: TaskRecord, cutoff: datetime) -> _PruneDecision:
    if task.status != "closed":
        return _PruneDecision(task.id, "refused", reason="active task")

    task_path = task_dir(root, task.id)
    if not _is_safe_task_evidence_path(root, task_path):
        return _PruneDecision(task.id, "refused", reason="unsafe task evidence path")

    closure = read_closure(root, task.id)
    closed_at = _closure_closed_at(closure, task.id)
    if closed_at is None:
        return _PruneDecision(task.id, "refused", reason="missing closure metadata")

    if closed_at > cutoff:
        return _PruneDecision(task.id, "skipped", reason="recently closed")

    return _PruneDecision(task.id, "eligible", path=relative_path(root, task_path))


def _closure_closed_at(closure: dict[str, Any] | None, task_id: str) -> datetime | None:
    if not closure or closure.get("task_id") != task_id:
        return None
    raw_closed_at = closure.get("closed_at")
    if not isinstance(raw_closed_at, str) or not raw_closed_at:
        return None
    try:
        closed_at = datetime.fromisoformat(raw_closed_at)
    except ValueError:
        return None
    return closed_at if closed_at.tzinfo is not None else None


def _is_safe_task_evidence_path(root: Path, path: Path) -> bool:
    tasks_root = tasks_dir(root).resolve()
    if path.is_symlink():
        return False
    try:
        resolved = path.resolve(strict=True)
    except FileNotFoundError:
        return False
    try:
        resolved.relative_to(tasks_root)
    except ValueError:
        return False
    return resolved.parent == tasks_root and path.parent.resolve() == tasks_root


def _run_id(now: datetime) -> str:
    return f"prune-{now.strftime('%Y%m%d-%H%M%S-%fZ')}"
