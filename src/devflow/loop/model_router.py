"""Native V2 model router — single-flight gate for local large-model access.

This is the prerequisite for native DevFlow execution: it enforces "only one
large model resident at a time" across the whole machine by sharing one lock
path with any earlier runner still in flight.

The single-flight lock is copied verbatim from
the previous local-model runtime lock (the working code is
the intended design). The only deviation is that the two ``paths`` helpers it
depended on are inlined here so this module is self-contained and carries zero
legacy imports.

On top of the lock sits a thin V2-native role->slot table. The V2 spine's
fleet is a fixed set of known endpoints (from the project model-role direction),
so a small table replaces the earlier agent-registry scorer without pulling in
the worker-client tree. The execution engine that *calls* these slots is a
separate, later milestone.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Literal


# ---------------------------------------------------------------------------
# Inlined path helpers copied from the earlier implementation.
# ---------------------------------------------------------------------------
def _devflow_dir(root: Path) -> Path:
    # Preserve the previous path shape so older and V2 runners share one lock.
    # Do NOT add .resolve() here.
    return Path(root) / ".devflow"


def _relative_path(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


# ---------------------------------------------------------------------------
# Single-flight lock copied from the prior runtime implementation.
# ---------------------------------------------------------------------------
RuntimeLockState = Literal["free", "running", "stale"]
MAX_RESIDENT_LOCAL_CALLS = 3


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
    """Admit up to three calls to one resident model and reject model mixing."""

    lock_dir = _global_local_model_lock_dir(root)
    owner_id = uuid.uuid4().hex
    lock_dir.parent.mkdir(parents=True, exist_ok=True)
    lock_dir.mkdir(exist_ok=True)
    slot_dir = lock_dir / "slots" / owner_id
    with _admission_lock(lock_dir):
        statuses = _local_model_runtime_statuses(root)
        stale = next((status for status in statuses if status.state == "stale"), None)
        if stale is not None:
            raise LocalModelRuntimeLockError(_stale_lock_message(root, stale))
        if statuses and any(
            status.provider != provider or status.model != model
            for status in statuses
        ):
            raise LocalModelRuntimeLockError(
                _running_lock_message(
                    root,
                    statuses[0],
                    requested_provider=provider,
                    requested_model=model,
                )
            )
        if len(statuses) >= MAX_RESIDENT_LOCAL_CALLS:
            raise LocalModelRuntimeLockError(
                f"Resident local model '{provider}/{model}' is at capacity "
                f"({MAX_RESIDENT_LOCAL_CALLS} active calls)."
            )
        slot_dir.mkdir(parents=True, exist_ok=False)
        owner_payload = _owner_payload(
            root,
            slot_dir,
            provider=provider,
            model=model,
            task_id=task_id,
            worker_id=worker_id,
            operation=operation,
            owner_id=owner_id,
        )
        (slot_dir / "owner.json").write_text(
            json.dumps(owner_payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    owner = LocalModelRuntimeOwner(**owner_payload, state="running", elapsed_seconds=0)
    try:
        yield owner
    finally:
        _release_lock(root, lock_dir, owner_id)


@contextmanager
def _admission_lock(lock_dir: Path) -> Iterator[None]:
    """Serialize short owner-list mutations without serializing model calls."""

    gate = lock_dir / "admission.lock"
    deadline = time.monotonic() + 5.0
    while True:
        try:
            gate.mkdir(exist_ok=False)
            break
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise LocalModelRuntimeLockError(
                    f"Timed out acquiring local-model admission gate at {gate}."
                )
            time.sleep(0.01)
    try:
        yield
    finally:
        shutil.rmtree(gate, ignore_errors=True)


def _owner_paths(lock_dir: Path) -> list[Path]:
    """Return current slot owners plus the legacy single-owner path."""

    paths: list[Path] = []
    legacy = lock_dir / "owner.json"
    if legacy.exists():
        paths.append(legacy)
    slots = lock_dir / "slots"
    if slots.exists():
        paths.extend(sorted(slots.glob("*/owner.json")))
    return paths


def _local_model_runtime_statuses(root: Path) -> list[LocalModelRuntimeOwner]:
    lock_dir = _global_local_model_lock_dir(root)
    statuses: list[LocalModelRuntimeOwner] = []
    for owner_path in _owner_paths(lock_dir):
        payload = _read_owner_payload(owner_path)
        state: RuntimeLockState = (
            "running" if _owner_process_is_active(payload) else "stale"
        )
        statuses.append(LocalModelRuntimeOwner(
            owner_id=str(payload.get("owner_id") or "unknown"),
            provider=str(payload.get("provider") or "unknown"),
            model=str(payload.get("model") or "unknown"),
            task_id=_optional_str(payload.get("task_id")),
            worker_id=_optional_str(payload.get("worker_id")),
            operation=str(payload.get("operation") or "unknown"),
            pid=_safe_int(payload.get("pid")),
            host=str(payload.get("host") or "unknown"),
            acquired_at=str(payload.get("acquired_at") or "unknown"),
            lock_path=_relative_path(root, owner_path.parent),
            state=state,
            elapsed_seconds=_elapsed_seconds(payload.get("acquired_at")),
        ))
    return statuses


def local_model_runtime_status(root: Path, *, provider: str, model: str) -> LocalModelRuntimeOwner | None:
    return next(
        (
            status
            for status in _local_model_runtime_statuses(root)
            if status.provider == provider and status.model == model
        ),
        None,
    )


def _global_local_model_runtime_status(root: Path) -> LocalModelRuntimeOwner | None:
    statuses = _local_model_runtime_statuses(root)
    return statuses[0] if statuses else None


def list_local_model_runtime_status(root: Path) -> dict[str, dict[str, Any]]:
    return {
        f"{status.provider}/{status.model}/{status.owner_id}": status.model_dump()
        for status in _local_model_runtime_statuses(root)
    }


def reclaim_stale_local_model_runtime_lock(root: Path, *, provider: str, model: str) -> bool:
    """Explicitly remove matching stale owners; live owners are never removed."""

    lock_dir = _global_local_model_lock_dir(root)
    if not lock_dir.exists():
        return False
    with _admission_lock(lock_dir):
        matching = [
            status
            for status in _local_model_runtime_statuses(root)
            if status.provider == provider and status.model == model
        ]
        if not matching:
            return False
        running = next((status for status in matching if status.state == "running"), None)
        if running is not None:
            raise LocalModelRuntimeLockError(_running_lock_message(root, running))
        stale_ids = {status.owner_id for status in matching}
        for owner_path in _owner_paths(lock_dir):
            payload = _read_owner_payload(owner_path)
            if str(payload.get("owner_id")) in stale_ids:
                if owner_path == lock_dir / "owner.json":
                    owner_path.unlink(missing_ok=True)
                else:
                    shutil.rmtree(owner_path.parent, ignore_errors=True)
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


def _release_lock(root: Path, lock_dir: Path, owner_id: str) -> None:
    if not lock_dir.exists():
        return
    with _admission_lock(lock_dir):
        for owner_path in _owner_paths(lock_dir):
            payload = _read_owner_payload(owner_path)
            if payload.get("owner_id") != owner_id:
                continue
            if owner_path == lock_dir / "owner.json":
                owner_path.unlink(missing_ok=True)
            else:
                shutil.rmtree(owner_path.parent, ignore_errors=True)
            break
    _ = root


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
        f"{requested} DevFlow permits up to {MAX_RESIDENT_LOCAL_CALLS} concurrent "
        "calls only to the same resident model; wait or inspect runtime status."
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
# Role resolution (delegates to the routing layer)
# ---------------------------------------------------------------------------
# The hardcoded ROLE_SLOTS table has been replaced by a three-layer
# capability-driven architecture:
#
#   registry.py   — describes what models exist (models.yaml)
#   roles.py      — describes what each role requires (capabilities)
#   routing.py    — connects roles to models (profiles.yaml + auto routing)
#
# This module now ONLY owns the single-flight filesystem lock. Role
# resolution is delegated to routing.resolve_role_compatible(), which
# accepts canonical role names plus the active generic ``judge`` alias.

from devflow.loop.routing import (
    ResolvedSlot,
    resolve_local_fallback_compatible,
    resolve_role_compatible,
    known_roles as _routing_known_roles,
)


# Backward-compat: expose the same names callers expect.
KNOWN_ROLES = _routing_known_roles()

# Backward-compat shim: ModelSlot keeps the old shape (.role, .provider,
# .model, .endpoint) so existing attribute access in execution.py and
# server.py works unchanged. ResolvedSlot already provides all four
# attributes (.model is an alias for .model_name).
ModelSlot = ResolvedSlot


def _audition_override_for_role(role: str) -> str | None:
    """Read one explicit role->local-model audition override from the env."""
    raw = os.environ.get("DEVFLOW_AUDITION_OVERRIDES", "").strip()
    if not raw:
        return None
    try:
        mapping = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("DEVFLOW_AUDITION_OVERRIDES must be a JSON object.") from exc
    if not isinstance(mapping, dict):
        raise ValueError("DEVFLOW_AUDITION_OVERRIDES must be a JSON object.")
    target = mapping.get(role)
    if target is None and role == "judge":
        target = mapping.get("build_judge")
    if target is None:
        return None
    if not isinstance(target, str) or not target.strip():
        raise ValueError(
            f"DEVFLOW_AUDITION_OVERRIDES target for role '{role}' must be a model name."
        )
    return target.strip()


def resolve_role_slot(role: str) -> ModelSlot:
    """Return the (provider, model, endpoint) a role is routed to.

    Delegates to the routing layer, which evaluates capabilities,
    deployment profiles, and cost-class preferences.

    Accepts canonical role names (builder, verifier, planner, etc.) and the
    active generic ``judge`` alias for ``build_judge``.

    Raises ValueError for unknown roles so callers fail loud, not silent.
    """
    return resolve_role_compatible(
        role,
        audition_override_model=_audition_override_for_role(role),
    )


def resolve_local_role_slot(role: str) -> ModelSlot | None:
    """Resolve the one capable local fallback allowed after free-cloud exhaustion."""

    return resolve_local_fallback_compatible(role)


@contextmanager
def acquire_role_slot(
    root: Path,
    *,
    role: str,
    task_id: str | None = None,
    worker_id: str | None = None,
    operation: str = "v2-loop",
    slot: ModelSlot | None = None,
) -> Iterator[ModelSlot]:
    """Acquire the single-flight lock for a DevFlow role (planner/builder/judge/verifier).

    The V2 execution step that needs the model must do its work inside this
    ``with`` block. While held, no other role that maps to the same model (or
    any other live model on this machine, given the single-resident fleet) can
    acquire a slot.
    """
    slot = slot or resolve_role_slot(role)
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
    "KNOWN_ROLES",
    "ModelSlot",
    "resolve_role_slot",
    "resolve_local_role_slot",
    "acquire_role_slot",
]
