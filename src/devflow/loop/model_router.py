"""Native V2 model router — single-flight gate for local large-model access.

This is the prerequisite for native DevFlow execution: it enforces "only one
large model resident at a time" across the whole machine, including any legacy
``devflow loop run`` still in flight, by sharing the exact same lock path.

The single-flight lock is copied verbatim from
``devflow.legacy.control_room.local_model_runtime_lock`` (the working code is
the intended design). The only deviation is that the two ``paths`` helpers it
depended on are inlined here so this module is self-contained and carries zero
legacy imports.

On top of the lock sits a thin V2-native role->slot table. The V2 spine's
fleet is a fixed set of known endpoints (from the project model-role direction),
so a small table replaces the legacy agent-registry scorer without pulling in
the worker-client tree. The execution engine that *calls* these slots is a
separate, later milestone.
"""

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


# ---------------------------------------------------------------------------
# Inlined path helpers (copied logic from devflow.legacy.control_room.paths)
# ---------------------------------------------------------------------------
def _devflow_dir(root: Path) -> Path:
    # Mirrors legacy devflow_dir EXACTLY so the V2 and legacy lock share the
    # same directory. Do NOT add .resolve() here — legacy does not.
    return Path(root) / ".devflow"


def _relative_path(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


# ---------------------------------------------------------------------------
# Single-flight lock (copied verbatim from local_model_runtime_lock.py)
# ---------------------------------------------------------------------------
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
    return _global_local_model_lock_dir(root)


def _global_local_model_lock_dir(root: Path) -> Path:
    return _devflow_dir(root) / "runtime" / "locks" / "local-model" / "global.lock"


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
    """Acquire the machine-wide single-flight lock for a local model call."""

    lock_dir = _global_local_model_lock_dir(root)
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
        status = _global_local_model_runtime_status(root)
        if status and status.state == "stale":
            raise LocalModelRuntimeLockError(
                _stale_lock_message(root, status)
            ) from exc
        if status:
            raise LocalModelRuntimeLockError(
                _running_lock_message(
                    root, status, requested_provider=provider, requested_model=model
                )
            ) from exc
        raise LocalModelRuntimeLockError(
            f"Local model '{provider}/{model}' is locked at {_relative_path(root, lock_dir)}."
        ) from exc

    owner = LocalModelRuntimeOwner(**owner_payload, state="running", elapsed_seconds=0)
    try:
        yield owner
    finally:
        _release_lock(lock_dir, owner_id)


def local_model_runtime_status(root: Path, *, provider: str, model: str) -> LocalModelRuntimeOwner | None:
    status = _global_local_model_runtime_status(root)
    if status is None:
        return None
    if status.provider != provider or status.model != model:
        return None
    return status


def _global_local_model_runtime_status(root: Path) -> LocalModelRuntimeOwner | None:
    lock_dir = _global_local_model_lock_dir(root)
    owner_path = lock_dir / "owner.json"
    if not owner_path.exists():
        return None
    payload = _read_owner_payload(owner_path)
    state: RuntimeLockState = "running" if _owner_process_is_active(payload) else "stale"
    elapsed = _elapsed_seconds(payload.get("acquired_at"))
    provider = str(payload.get("provider") or "unknown")
    model = str(payload.get("model") or "unknown")
    return LocalModelRuntimeOwner(
        owner_id=str(payload.get("owner_id") or "unknown"),
        provider=provider,
        model=model,
        task_id=_optional_str(payload.get("task_id")),
        worker_id=_optional_str(payload.get("worker_id")),
        operation=str(payload.get("operation") or "unknown"),
        pid=_safe_int(payload.get("pid")),
        host=str(payload.get("host") or "unknown"),
        acquired_at=str(payload.get("acquired_at") or "unknown"),
        lock_path=_relative_path(root, lock_dir),
        state=state,
        elapsed_seconds=elapsed,
    )


def list_local_model_runtime_status(root: Path) -> dict[str, dict[str, Any]]:
    status = _global_local_model_runtime_status(root)
    if status is None:
        return {}
    return {f"{status.provider}/{status.model}": status.model_dump()}


def reclaim_stale_local_model_runtime_lock(root: Path, *, provider: str, model: str) -> bool:
    """Explicitly remove a stale lock. Live locks are never removed here."""

    status = local_model_runtime_status(root, provider=provider, model=model)
    if status is None:
        return False
    if status.state != "stale":
        raise LocalModelRuntimeLockError(_running_lock_message(root, status))
    shutil.rmtree(_global_local_model_lock_dir(root), ignore_errors=True)
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
        "lock_path": _relative_path(root, lock_dir),
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


def _running_lock_message(
    root: Path,
    status: LocalModelRuntimeOwner,
    *,
    requested_provider: str | None = None,
    requested_model: str | None = None,
) -> str:
    requested = (
        f" Requested another local model '{requested_provider}/{requested_model}'."
        if requested_provider
        and requested_model
        and (requested_provider != status.provider or requested_model != status.model)
        else ""
    )
    return (
        f"Local model '{status.provider}/{status.model}' is already running "
        f"for task {status.task_id or 'unknown'} via {status.worker_id or status.operation} "
        f"(pid: {status.pid}, elapsed: {status.elapsed_seconds}s, lock: {status.lock_path})."
        f"{requested} DevFlow local model runs are single-flight; wait for it to finish or inspect runtime status."
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


# ---------------------------------------------------------------------------
# V2-native role -> slot table (replaces the legacy agent-registry scorer)
# ---------------------------------------------------------------------------
# Source of truth: project model-role direction.
#   planner -> Agents-A1 Q4        (http://localhost:8087)
#   builder -> Ornith 35B MoE      (http://localhost:8084)
#   planning_judge -> Qwen 27B Q5_K_M (http://localhost:8083) [live]
#   judge   -> Qwen 27B Q5_K_M     (http://localhost:8083)  [live]
#   verifier-> Qwen 27B Q5_K_M     (http://localhost:8083)  [live]
#
# The lock is keyed by (provider, model). judge and verifier share the same
# model, so they serialize against each other too. Because only one large
# model server is resident at a time in this fleet, the per-model lock yields
# machine-wide single-flight as required.
ROLE_SLOTS: dict[str, dict[str, str]] = {
    "planner": {"provider": "local", "model": "agents-a1-q4", "endpoint": "http://localhost:8087"},
    "builder": {"provider": "local", "model": "ornith-35b", "endpoint": "http://localhost:8084"},
    "planning_judge": {"provider": "local", "model": "qwen-27b-q5km", "endpoint": "http://localhost:8083"},
    "judge": {"provider": "local", "model": "qwen-27b-q5km", "endpoint": "http://localhost:8083"},
    "verifier": {"provider": "local", "model": "qwen-27b-q5km", "endpoint": "http://localhost:8083"},
    # GLM verifier: routes through the user's Hermes Z.AI subscription
    # (no per-token local API). Distinct (provider,model) so it does NOT
    # serialize against the local Qwen judge lane.
    "glm_verifier": {"provider": "zai", "model": "glm-5.2", "endpoint": "hermes://chat/zai/glm-5.2"},
}

KNOWN_ROLES = tuple(ROLE_SLOTS.keys())


@dataclass(frozen=True)
class ModelSlot:
    role: str
    provider: str
    model: str
    endpoint: str


def resolve_role_slot(role: str) -> ModelSlot:
    """Return the (provider, model, endpoint) a role is routed to.

    Raises ValueError for unknown roles so callers fail loud, not silent.
    """
    slot = ROLE_SLOTS.get(role)
    if slot is None:
        raise ValueError(
            f"Unknown model-router role '{role}'. Known roles: {', '.join(KNOWN_ROLES)}"
        )
    return ModelSlot(
        role=role,
        provider=slot["provider"],
        model=slot["model"],
        endpoint=slot["endpoint"],
    )


@contextmanager
def acquire_role_slot(
    root: Path,
    *,
    role: str,
    task_id: str | None = None,
    worker_id: str | None = None,
    operation: str = "v2-loop",
) -> Iterator[ModelSlot]:
    """Acquire the single-flight lock for a DevFlow role (planner/builder/judge/verifier).

    The V2 execution step that needs the model must do its work inside this
    ``with`` block. While held, no other role that maps to the same model (or
    any other live model on this machine, given the single-resident fleet) can
    acquire a slot.
    """
    slot = resolve_role_slot(role)
    with local_model_runtime_lock(
        root,
        provider=slot.provider,
        model=slot.model,
        task_id=task_id,
        worker_id=worker_id,
        operation=operation,
    ):
        yield slot


__all__ = [
    "LocalModelRuntimeLockError",
    "LocalModelRuntimeOwner",
    "local_model_runtime_lock",
    "local_model_runtime_status",
    "list_local_model_runtime_status",
    "reclaim_stale_local_model_runtime_lock",
    "ROLE_SLOTS",
    "KNOWN_ROLES",
    "ModelSlot",
    "resolve_role_slot",
    "acquire_role_slot",
]
