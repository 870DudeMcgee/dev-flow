from __future__ import annotations

import json
import os
import shutil
import socket
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Literal

from devflow.control_room.paths import devflow_dir, relative_path


RuntimeLockState = Literal["free", "running", "stale"]


class LocalModelRuntimeLockError(ValueError):
    """Raised when a local model runtime lock blocks a new run."""


@dataclass(frozen=True)
class LocalModelRuntimeOwner:
    owner_id: str
    provider: str
    model: str
    task_id: str | None
    worker_id: str | None
    operation: str
    pid: int
    host: str
    acquired_at: str
    lock_path: str
    state: RuntimeLockState
    elapsed_seconds: int | None = None

    def model_dump(self) -> dict[str, Any]:
        return {
            "owner_id": self.owner_id,
            "provider": self.provider,
            "model": self.model,
            "task_id": self.task_id,
            "worker_id": self.worker_id,
            "operation": self.operation,
            "pid": self.pid,
            "host": self.host,
            "acquired_at": self.acquired_at,
            "lock_path": self.lock_path,
            "state": self.state,
            "elapsed_seconds": self.elapsed_seconds,
        }


def local_model_lock_dir(root: Path, provider: str, model: str) -> Path:
    return devflow_dir(root) / "runtime" / "locks" / "local-model" / _slug(provider) / f"{_slug(model)}.lock"


@contextmanager
def local_model_runtime_lock(
    root: Path,
    *,
    provider: str,
    model: str,
    task_id: str | None = None,
    worker_id: str | None = None,
    operation: str = "local-model-run",
) -> Iterator[LocalModelRuntimeOwner]:
    """Acquire a provider/model-scoped single-flight lock for a local model call."""

    lock_dir = local_model_lock_dir(root, provider, model)
    owner_id = uuid.uuid4().hex
    owner_payload = _owner_payload(
        root,
        lock_dir,
        provider=provider,
        model=model,
        task_id=task_id,
        worker_id=worker_id,
        operation=operation,
        owner_id=owner_id,
    )
    try:
        lock_dir.parent.mkdir(parents=True, exist_ok=True)
        lock_dir.mkdir(exist_ok=False)
        (lock_dir / "owner.json").write_text(
            json.dumps(owner_payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except FileExistsError as exc:
        status = local_model_runtime_status(root, provider=provider, model=model)
        if status and status.state == "stale":
            raise LocalModelRuntimeLockError(
                _stale_lock_message(root, status)
            ) from exc
        if status:
            raise LocalModelRuntimeLockError(_running_lock_message(root, status)) from exc
        raise LocalModelRuntimeLockError(
            f"Local model '{provider}/{model}' is locked at {relative_path(root, lock_dir)}."
        ) from exc

    owner = LocalModelRuntimeOwner(**owner_payload, state="running", elapsed_seconds=0)
    try:
        yield owner
    finally:
        _release_lock(lock_dir, owner_id)


def local_model_runtime_status(root: Path, *, provider: str, model: str) -> LocalModelRuntimeOwner | None:
    lock_dir = local_model_lock_dir(root, provider, model)
    owner_path = lock_dir / "owner.json"
    if not owner_path.exists():
        return None
    payload = _read_owner_payload(owner_path)
    state: RuntimeLockState = "running" if _owner_process_is_active(payload) else "stale"
    elapsed = _elapsed_seconds(payload.get("acquired_at"))
    return LocalModelRuntimeOwner(
        owner_id=str(payload.get("owner_id") or "unknown"),
        provider=str(payload.get("provider") or provider),
        model=str(payload.get("model") or model),
        task_id=_optional_str(payload.get("task_id")),
        worker_id=_optional_str(payload.get("worker_id")),
        operation=str(payload.get("operation") or "unknown"),
        pid=_safe_int(payload.get("pid")),
        host=str(payload.get("host") or "unknown"),
        acquired_at=str(payload.get("acquired_at") or "unknown"),
        lock_path=relative_path(root, lock_dir),
        state=state,
        elapsed_seconds=elapsed,
    )


def list_local_model_runtime_status(root: Path) -> dict[str, dict[str, Any]]:
    base = devflow_dir(root) / "runtime" / "locks" / "local-model"
    if not base.exists():
        return {}
    statuses: dict[str, dict[str, Any]] = {}
    for lock_dir in sorted(base.glob("*/*.lock")):
        owner_path = lock_dir / "owner.json"
        if not owner_path.exists():
            continue
        payload = _read_owner_payload(owner_path)
        provider = str(payload.get("provider") or lock_dir.parent.name)
        model = str(payload.get("model") or lock_dir.name.removesuffix(".lock"))
        status = local_model_runtime_status(root, provider=provider, model=model)
        if status:
            statuses[f"{provider}/{model}"] = status.model_dump()
    return statuses


def reclaim_stale_local_model_runtime_lock(root: Path, *, provider: str, model: str) -> bool:
    """Explicitly remove a stale lock. Live locks are never removed here."""

    status = local_model_runtime_status(root, provider=provider, model=model)
    if status is None:
        return False
    if status.state != "stale":
        raise LocalModelRuntimeLockError(_running_lock_message(root, status))
    shutil.rmtree(local_model_lock_dir(root, provider, model), ignore_errors=True)
    return True


def _owner_payload(
    root: Path,
    lock_dir: Path,
    *,
    provider: str,
    model: str,
    task_id: str | None,
    worker_id: str | None,
    operation: str,
    owner_id: str,
) -> dict[str, Any]:
    return {
        "owner_id": owner_id,
        "provider": provider,
        "model": model,
        "task_id": task_id,
        "worker_id": worker_id,
        "operation": operation,
        "pid": os.getpid(),
        "host": socket.gethostname(),
        "acquired_at": datetime.now(timezone.utc).isoformat(),
        "lock_path": relative_path(root, lock_dir),
    }


def _release_lock(lock_dir: Path, owner_id: str) -> None:
    owner_path = lock_dir / "owner.json"
    try:
        payload = _read_owner_payload(owner_path)
    except Exception:
        return
    if payload.get("owner_id") != owner_id:
        return
    shutil.rmtree(lock_dir, ignore_errors=True)


def _read_owner_payload(owner_path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(owner_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _owner_process_is_active(payload: dict[str, Any]) -> bool:
    if payload.get("host") != socket.gethostname():
        return False
    pid = _safe_int(payload.get("pid"))
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _elapsed_seconds(value: Any) -> int | None:
    try:
        acquired_at = datetime.fromisoformat(str(value))
    except Exception:
        return None
    if acquired_at.tzinfo is None:
        acquired_at = acquired_at.replace(tzinfo=timezone.utc)
    return max(0, int((datetime.now(timezone.utc) - acquired_at).total_seconds()))


def _running_lock_message(root: Path, status: LocalModelRuntimeOwner) -> str:
    return (
        f"Local model '{status.provider}/{status.model}' is already running "
        f"for task {status.task_id or 'unknown'} via {status.worker_id or status.operation} "
        f"(pid: {status.pid}, elapsed: {status.elapsed_seconds}s, lock: {status.lock_path}). "
        "DevFlow local model runs are single-flight; wait for it to finish or inspect runtime status."
    )


def _stale_lock_message(root: Path, status: LocalModelRuntimeOwner) -> str:
    return (
        f"Local model '{status.provider}/{status.model}' has a stale runtime lock "
        f"(pid: {status.pid}, lock: {status.lock_path}). "
        "The stale lock was not removed automatically; inspect it and call explicit reclaim before retrying."
    )


def _safe_int(value: Any) -> int:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return 0


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _slug(value: str) -> str:
    text = "".join(char if char.isalnum() or char in "_.-" else "-" for char in str(value)).strip("-._")
    return text or "unknown"


__all__ = [
    "LocalModelRuntimeLockError",
    "LocalModelRuntimeOwner",
    "local_model_lock_dir",
    "local_model_runtime_lock",
    "local_model_runtime_status",
    "list_local_model_runtime_status",
    "reclaim_stale_local_model_runtime_lock",
]
