from __future__ import annotations

import json
import os
import shutil
import socket
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

from devflow.control_room.paths import task_dir


TASK_LOCK_STALE_AFTER_SECONDS = 60 * 60


class TaskLockError(ValueError):
    """Raised when a task-local mutation lock cannot be acquired."""


@contextmanager
def task_mutation_lock(
    root: Path,
    task_id: str,
    operation: str,
    *,
    stale_after_seconds: int = TASK_LOCK_STALE_AFTER_SECONDS,
) -> Iterator[Path]:
    task_path = task_dir(root, task_id)
    if not task_path.is_dir():
        raise KeyError(f"Task not found: {task_id}")
    lock_dir = task_path / ".lock"
    owner_id = uuid.uuid4().hex
    while True:
        try:
            lock_dir.mkdir(exist_ok=False)
            owner_path = lock_dir / "owner.json"
            owner_path.write_text(
                json.dumps(_owner_payload(task_id, operation, owner_id), indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            break
        except FileExistsError as exc:
            if _remove_stale_lock(lock_dir, stale_after_seconds):
                continue
            raise TaskLockError(_locked_message(task_id, lock_dir)) from exc

    try:
        yield lock_dir
    finally:
        _release_lock(lock_dir, owner_id)


def _owner_payload(task_id: str, operation: str, owner_id: str) -> dict[str, object]:
    return {
        "owner_id": owner_id,
        "task_id": task_id,
        "operation": operation,
        "pid": os.getpid(),
        "host": socket.gethostname(),
        "acquired_at": datetime.now(timezone.utc).isoformat(),
    }


def _remove_stale_lock(lock_dir: Path, stale_after_seconds: int) -> bool:
    owner_path = lock_dir / "owner.json"
    try:
        payload = json.loads(owner_path.read_text(encoding="utf-8"))
        acquired_at = datetime.fromisoformat(str(payload.get("acquired_at")))
    except Exception:
        try:
            acquired_at = datetime.fromtimestamp(lock_dir.stat().st_mtime, tz=timezone.utc)
        except OSError:
            return False
    if _owner_process_is_active(payload):
        return False
    if acquired_at.tzinfo is None:
        acquired_at = acquired_at.replace(tzinfo=timezone.utc)
    age = datetime.now(timezone.utc) - acquired_at
    if age <= timedelta(seconds=stale_after_seconds):
        return False
    shutil.rmtree(lock_dir, ignore_errors=True)
    return True


def _release_lock(lock_dir: Path, owner_id: str) -> None:
    owner_path = lock_dir / "owner.json"
    try:
        payload = json.loads(owner_path.read_text(encoding="utf-8"))
    except Exception:
        return
    if payload.get("owner_id") != owner_id:
        return
    shutil.rmtree(lock_dir, ignore_errors=True)


def _owner_process_is_active(payload: dict[str, object]) -> bool:
    if payload.get("host") != socket.gethostname():
        return False
    try:
        pid = int(str(payload.get("pid")))
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _locked_message(task_id: str, lock_dir: Path) -> str:
    owner_path = lock_dir / "owner.json"
    try:
        payload = json.loads(owner_path.read_text(encoding="utf-8"))
    except Exception:
        payload = {}
    operation = payload.get("operation") or "unknown"
    pid = payload.get("pid") or "unknown"
    host = payload.get("host") or "unknown"
    acquired_at = payload.get("acquired_at") or "unknown"
    return (
        f"Task {task_id} is locked by operation '{operation}' "
        f"(pid: {pid}, host: {host}, acquired_at: {acquired_at})."
    )
