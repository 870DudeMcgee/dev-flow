"""Deterministic git-worktree sandbox lifecycle for authorized packet builds.

A sandbox is a *linked* git worktree materialized from an already-authorized
source snapshot, bound to one packet of an approved execution plan. The path is
fully deterministic:

    <repo>/.devflow/sandboxes/<run_id>/<kind>-<sandbox_id>

Lifecycle guarantees (contract):
  - Creation revalidates the *entire* Phase 3 chain at request time: the
    approved plan (``load_execution_plan`` / ``execution_plan_hash``), the
    execution authorization (``load_execution_authorization``), the immutable
    source snapshot receipt (``load_source_snapshot_receipt``), and finally the
    live git ref ``git rev-parse <snapshot.ref>``. Every binding must match the
    recorded values exactly or creation fails closed.
  - Active capacity is ``max_sandboxes``; sandbox_ids that already carry a valid
    cleanup receipt do not count against capacity. Malformed stores fail closed.
  - A creation receipt is persisted immutably (O_EXCL + fsync) under the run
    directory at ``sandbox-receipts/<sandbox_id>.json``. An identical request is
    idempotent: the existing receipt is inspected *before* capacity accounting,
    and is returned only if the live worktree still matches this sandbox's
    registration, deterministic path, detached HEAD at the snapshot commit, and
    shared common dir. A conflicting reuse of a sandbox id is rejected and the
    original receipt is preserved.
  - If worktree creation succeeds but receipt persistence fails, the *just
    created* worktree is removed (and only that one) so partial state cannot
    masquerade as a usable sandbox.
  - ``git worktree list --porcelain`` is consulted before creation to ensure no
    existing unrelated worktree is already registered at the deterministic path,
    and before cleanup to confirm exact common-dir + HEAD ownership so an
    unrelated or foreign worktree is never removed.
  - Cleanup loads the creation receipt, validates positive ownership, then runs
    ``git worktree remove --force`` only for the exact worktree. A cleanup
    receipt is persisted immutably under ``sandbox-cleanups/<cleanup_id>.json``;
    it is idempotent by cleanup_id and conflicting reuse fails closed.
  - No ``shell=True``; typed argv subprocess only.
"""

from __future__ import annotations

import json
import os
import subprocess
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from devflow.loop.execution_authorization import load_execution_authorization
from devflow.loop.execution_plan import (
    ExecutionPlan,
    execution_plan_hash,
    load_execution_plan,
)
from devflow.loop.pipeline_run import pipeline_runs_dir
from devflow.loop.source_snapshot import (
    SnapshotError,
    load_source_snapshot_receipt,
)

__all__ = [
    "CleanupReceipt",
    "SandboxCapacityError",
    "SandboxCleanupReceipt",
    "SandboxConflictError",
    "SandboxError",
    "SandboxKind",
    "SandboxOwnershipError",
    "SandboxCleanupReceipt",
    "CleanupReceipt",
    "SandboxReceipt",
    "SandboxRequest",
    "SandboxValidationError",
    "cleanup_sandbox",
    "create_sandbox",
    "load_cleanup_receipt",
    "load_sandbox_receipt",
    "sandbox_path",
]

_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]*$"
_RECEIPT_DIR_NAME = "sandbox-receipts"
_CLEANUP_DIR_NAME = "sandbox-cleanups"


# ---------------------------------------------------------------------------
# Sandbox kind
# ---------------------------------------------------------------------------
class SandboxKind(str, Enum):
    """Discriminator for what a sandbox is bound to.

    ``packet`` sandboxes bind exactly one approved, ready packet and must carry
    a ``packet_id``. ``integration`` sandboxes are not packet-bound and must not
    carry a ``packet_id``.
    """

    packet = "packet"
    integration = "integration"


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------
class SandboxError(Exception):
    """Base class for sandbox lifecycle failures."""


class SandboxValidationError(SandboxError):
    """Raised when a request or referenced evidence violates the contract."""


class SandboxConflictError(SandboxError):
    """Raised when a sandbox/cleanup id is reused with a conflicting record."""


class SandboxCapacityError(SandboxError):
    """Raised when active sandboxes would exceed ``max_sandboxes``."""


class SandboxOwnershipError(SandboxError):
    """Raised when cleanup cannot confirm positive ownership of the worktree."""


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class SandboxRequest(BaseModel):
    """Typed, explicit request to materialize one packet sandbox worktree."""

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    repo: Path
    root: Path
    run_id: str = Field(min_length=1, pattern=_ID_PATTERN)
    sandbox_id: str = Field(min_length=1, pattern=_ID_PATTERN)
    kind: SandboxKind
    authorization_id: str = Field(min_length=1, pattern=_ID_PATTERN)
    packet_id: str | None = None
    max_sandboxes: int = Field(default=1, ge=1)


class SandboxReceipt(BaseModel):
    """Immutable receipt describing a materialized sandbox worktree."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    sandbox_id: str
    run_id: str
    kind: SandboxKind
    authorization_id: str
    packet_id: str | None
    path: str
    snapshot_ref: str
    snapshot_commit: str
    plan_hash: str
    execution_plan_hash: str


class SandboxCleanupReceipt(BaseModel):
    """Immutable receipt describing a completed sandbox cleanup."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    cleanup_id: str
    sandbox_id: str
    run_id: str
    kind: SandboxKind
    path: str
    snapshot_commit: str
    removed: bool = True


# Backwards-compatible alias.
CleanupReceipt = SandboxCleanupReceipt


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _git(repo: Path, *args: str, cwd: Path | None = None) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=str(cwd) if cwd is not None else str(repo),
        shell=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise SandboxError(f"git {' '.join(args[:2])} failed: {detail}")
    return result.stdout


def sandbox_path(repo: Path, run_id: str, kind: SandboxKind, sandbox_id: str) -> Path:
    """Deterministic absolute path for a sandbox worktree.

    Lays out under ``<repo>/.devflow/sandboxes/<run_id>/<kind>-<sandbox_id>``.
    """
    if not run_id or not kind or not sandbox_id:
        raise SandboxValidationError("run_id, kind, and sandbox_id are required")
    base = repo.resolve() / ".devflow" / "sandboxes" / run_id
    return base / f"{kind.value}-{sandbox_id}"


def _run_dir(root: Path | str, run_id: str) -> Path:
    runs = pipeline_runs_dir(root).resolve()
    run_dir = (runs / run_id).resolve()
    try:
        run_dir.relative_to(runs)
    except ValueError as exc:
        raise SandboxValidationError("sandbox run escapes pipeline runs") from exc
    if not run_dir.is_dir():
        raise SandboxValidationError(f"sandbox run {run_id!r} does not exist")
    return run_dir


def _receipt_path(
    root: Path | str, run_id: str, sandbox_id: str, *, cleanup: bool = False
) -> Path:
    if not sandbox_id or any(
        char
        not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
        for char in sandbox_id
    ):
        raise SandboxValidationError("invalid sandbox id")
    run_dir = _run_dir(root, run_id)
    subdir = _CLEANUP_DIR_NAME if cleanup else _RECEIPT_DIR_NAME
    target = (run_dir / subdir / f"{sandbox_id}.json").resolve()
    if target.parent != (run_dir / subdir).resolve():
        raise SandboxValidationError("sandbox receipt path escapes its store")
    return target


def _persist_immutable(target: Path, payload: dict) -> bool:
    """Write immutably with O_EXCL + fsync. Return True if newly written."""
    target.parent.mkdir(mode=0o755, exist_ok=True)
    text = (
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")
    try:
        fd = os.open(str(target), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
    except FileExistsError:
        return False
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
    except Exception:
        target.unlink(missing_ok=True)
        raise
    return True


def _parse_worktree_list(repo: Path) -> list[dict]:
    """Parse ``git worktree list --porcelain`` into a list of entries."""
    out = _git(repo, "worktree", "list", "--porcelain")
    worktrees: list[dict] = []
    current: dict | None = None
    for line in out.splitlines():
        if line.startswith("worktree "):
            if current is not None:
                worktrees.append(current)
            current = {"worktree": line[len("worktree ") :]}
        elif current is not None:
            if line.startswith("HEAD "):
                current["HEAD"] = line[len("HEAD ") :]
            elif line == "detached":
                current["detached"] = True
            elif line.startswith("branch "):
                current["branch"] = line[len("branch ") :]
            elif line == "locked":
                current["locked"] = True
    if current is not None:
        worktrees.append(current)
    return worktrees


def _worktree_entry_for_path(repo: Path, path: Path) -> dict | None:
    resolved = path.resolve()
    for entry in _parse_worktree_list(repo):
        try:
            if Path(entry["worktree"]).resolve() == resolved:
                return entry
        except (KeyError, OSError):
            continue
    return None


def _common_dir(repo: Path) -> Path:
    return Path(_git(repo, "rev-parse", "--absolute-git-dir").strip()).resolve()


def _verify_owned_worktree(repo: Path, target: Path, snapshot_commit: str) -> bool:
    """Return True only if *target* is exactly the worktree we would own.

    The worktree must be registered at *target*, detached at the snapshot
    commit, and share this repo's common dir (never a foreign repo).
    """
    entry = _worktree_entry_for_path(repo, target)
    if entry is None:
        return False
    if entry.get("HEAD") != snapshot_commit:
        return False
    if not entry.get("detached"):
        return False
    try:
        common = Path(
            _git(Path(target), "rev-parse", "--git-common-dir").strip()
        ).resolve()
    except SandboxError:
        return False
    return common == _common_dir(repo)


def load_sandbox_receipt(
    root: Path | str, run_id: str, sandbox_id: str
) -> SandboxReceipt:
    """Load one immutable sandbox creation receipt (malformed fails closed)."""
    target = _receipt_path(root, run_id, sandbox_id)
    try:
        receipt = SandboxReceipt.model_validate_json(
            target.read_text(encoding="utf-8")
        )
    except (OSError, ValueError) as exc:
        raise SandboxValidationError(
            f"sandbox receipt {sandbox_id!r} is missing or corrupt"
        ) from exc
    if receipt.sandbox_id != sandbox_id or receipt.run_id != run_id:
        raise SandboxValidationError("sandbox receipt does not match its path")
    return receipt


def load_cleanup_receipt(
    root: Path | str, run_id: str, cleanup_id: str
) -> SandboxCleanupReceipt:
    """Load one immutable cleanup receipt (malformed fails closed)."""
    target = _receipt_path(root, run_id, cleanup_id, cleanup=True)
    try:
        receipt = SandboxCleanupReceipt.model_validate_json(
            target.read_text(encoding="utf-8")
        )
    except (OSError, ValueError) as exc:
        raise SandboxValidationError(
            f"cleanup receipt {cleanup_id!r} is missing or corrupt"
        ) from exc
    if receipt.cleanup_id != cleanup_id or receipt.run_id != run_id:
        raise SandboxValidationError("cleanup receipt does not match its path")
    return receipt


def _active_sandbox_ids(root: Path | str, run_id: str) -> set[str]:
    """Set of sandbox_ids with a creation receipt but no valid cleanup receipt.

    Every cleanup JSON is parsed; the filename stem must equal the recorded
    cleanup id and the run id must match. A malformed or unexpected cleanup
    file fails closed.
    """
    run_dir = _run_dir(root, run_id)
    receipt_dir = run_dir / _RECEIPT_DIR_NAME
    cleanup_dir = run_dir / _CLEANUP_DIR_NAME
    if not receipt_dir.is_dir():
        return set()
    cleaned: set[str] = set()
    if cleanup_dir.is_dir():
        for child in cleanup_dir.iterdir():
            if not (child.is_file() and child.suffix == ".json"):
                continue
            try:
                receipt = SandboxCleanupReceipt.model_validate_json(
                    child.read_text(encoding="utf-8")
                )
            except (OSError, ValueError) as exc:
                raise SandboxValidationError(
                    f"cleanup receipt {child.name!r} is missing or corrupt"
                ) from exc
            if receipt.cleanup_id != child.stem:
                raise SandboxValidationError(
                    f"cleanup receipt {child.name!r} path does not match its id"
                )
            if receipt.run_id != run_id:
                raise SandboxValidationError(
                    f"cleanup receipt {child.name!r} run does not match"
                )
            cleaned.add(receipt.sandbox_id)
    active: set[str] = set()
    for child in receipt_dir.iterdir():
        if not child.is_file() or child.suffix != ".json":
            continue
        try:
            receipt = SandboxReceipt.model_validate_json(
                child.read_text(encoding="utf-8")
            )
        except (OSError, ValueError) as exc:
            raise SandboxValidationError(
                f"sandbox receipt {child.stem!r} is corrupt"
            ) from exc
        if receipt.sandbox_id not in cleaned:
            active.add(receipt.sandbox_id)
    return active


def _validate_packet_binding(
    plan: ExecutionPlan,
    authorized_packet_ids: tuple[str, ...],
    snapshot_selected: list[str],
    packet_id: str | None,
) -> None:
    if packet_id is None:
        return
    packet = next((p for p in plan.packets if p.id == packet_id), None)
    if packet is None:
        raise SandboxValidationError(
            f"packet {packet_id!r} is not part of the approved plan"
        )
    if packet_id not in authorized_packet_ids:
        raise SandboxValidationError(
            f"packet {packet_id!r} is not covered by the authorization"
        )
    selected = set(snapshot_selected)
    extra = set(packet.target_files) - selected
    if extra:
        raise SandboxValidationError(
            f"packet {packet_id!r} targets files outside the source snapshot: "
            f"{sorted(extra)!r}"
        )


# ---------------------------------------------------------------------------
# Creation
# ---------------------------------------------------------------------------
def create_sandbox(request: SandboxRequest) -> SandboxReceipt:
    """Materialize a linked git worktree for one authorized packet.

    Revalidates the full Phase 3 chain (plan, authorization, snapshot, live
    ref), enforces capacity, and persists an immutable creation receipt.
    Idempotent for identical requests.
    """
    repo = request.repo.resolve()
    if not (repo / ".git").exists():
        raise SandboxValidationError(f"not a git repository: {repo}")

    # --- revalidate the full Phase 3 chain at request time ------------------
    try:
        plan = load_execution_plan(request.root, request.run_id)
    except ValueError as exc:
        raise SandboxValidationError(f"execution plan is missing or corrupt: {exc}") from exc
    plan_hash = execution_plan_hash(plan)

    try:
        auth = load_execution_authorization(
            request.root, request.run_id, request.authorization_id
        )
    except ValueError as exc:
        raise SandboxValidationError(
            f"execution authorization is missing or corrupt: {exc}"
        ) from exc

    if auth.execution_plan_hash != plan_hash:
        raise SandboxValidationError(
            "authorization plan hash does not match the approved plan"
        )

    try:
        snapshot = load_source_snapshot_receipt(
            request.root, request.run_id, auth.snapshot_id
        )
    except SnapshotError as exc:
        raise SandboxValidationError(
            f"source snapshot is missing or corrupt: {exc}"
        ) from exc

    if snapshot.fingerprint != auth.snapshot_fingerprint:
        raise SandboxValidationError(
            "snapshot fingerprint does not match the authorization"
        )
    if snapshot.commit != auth.snapshot_commit:
        raise SandboxValidationError(
            "snapshot commit does not match the authorization"
        )
    if snapshot.selected_paths != plan.target_files:
        raise SandboxValidationError(
            "snapshot selected paths do not match the approved plan targets"
        )

    # Live ref must still resolve to the recorded snapshot commit.
    live_ref = _git(repo, "rev-parse", snapshot.ref).strip()
    if live_ref != snapshot.commit:
        raise SandboxValidationError(
            f"snapshot ref {snapshot.ref!r} resolves to {live_ref!r}, "
            f"expected {snapshot.commit!r}"
        )
    _git(repo, "rev-parse", snapshot.commit).strip()

    # --- kind / packet binding ---------------------------------------------
    if request.kind == SandboxKind.integration:
        if request.packet_id is not None:
            raise SandboxValidationError(
                "integration sandbox must not bind a packet (packet_id=None)"
            )
    else:  # packet
        if request.packet_id is None:
            raise SandboxValidationError(
                "packet sandbox requires a packet_id"
            )
        _validate_packet_binding(
            plan, auth.packet_ids, snapshot.selected_paths, request.packet_id
        )

    target = sandbox_path(repo, request.run_id, request.kind, request.sandbox_id)

    # --- existing receipt checked BEFORE capacity --------------------------
    receipt_path = _receipt_path(request.root, request.run_id, request.sandbox_id)
    existing: SandboxReceipt | None = None
    if receipt_path.exists():
        try:
            existing = load_sandbox_receipt(
                request.root, request.run_id, request.sandbox_id
            )
        except SandboxValidationError:
            existing = None

    if existing is not None:
        expected = SandboxReceipt(
            sandbox_id=request.sandbox_id,
            run_id=request.run_id,
            kind=request.kind,
            authorization_id=request.authorization_id,
            packet_id=request.packet_id,
            path=str(target),
            snapshot_ref=snapshot.ref,
            snapshot_commit=snapshot.commit,
            plan_hash=plan_hash,
            execution_plan_hash=auth.execution_plan_hash,
        )
        if expected.model_dump() == existing.model_dump():
            # Identical request returns the existing receipt only if the live
            # worktree still matches exactly (path/HEAD/detached/common-dir).
            if _verify_owned_worktree(repo, target, snapshot.commit):
                return existing
            # Otherwise the recorded worktree is gone or mismatched: fail closed
            # so a stale receipt cannot masquerade as a usable sandbox.
            raise SandboxConflictError(
                f"sandbox id {request.sandbox_id!r} has a stale receipt whose "
                "worktree no longer matches; original receipt preserved"
            )
        # Conflicting reuse of a sandbox id: reject, keep the original.
        raise SandboxConflictError(
            f"sandbox id {request.sandbox_id!r} already exists with a "
            "conflicting request; original receipt preserved"
        )

    # --- capacity & conflict ------------------------------------------------
    active = _active_sandbox_ids(request.root, request.run_id)
    if request.sandbox_id in active:
        raise SandboxConflictError(
            f"sandbox id {request.sandbox_id!r} is already active"
        )
    if len(active) >= request.max_sandboxes:
        raise SandboxCapacityError(
            f"active sandboxes {len(active)} would exceed max_sandboxes "
            f"{request.max_sandboxes}"
        )

    if target.exists():
        raise SandboxConflictError(
            f"deterministic sandbox path already exists: {target}"
        )

    # Ensure no unrelated worktree is already registered at the exact path.
    if _worktree_entry_for_path(repo, target) is not None:
        raise SandboxConflictError(
            f"a worktree is already registered at {target}"
        )

    # --- create the worktree ------------------------------------------------
    receipt = SandboxReceipt(
        sandbox_id=request.sandbox_id,
        run_id=request.run_id,
        kind=request.kind,
        authorization_id=request.authorization_id,
        packet_id=request.packet_id,
        path=str(target),
        snapshot_ref=snapshot.ref,
        snapshot_commit=snapshot.commit,
        plan_hash=plan_hash,
        execution_plan_hash=auth.execution_plan_hash,
    )

    created = False
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        # --detach so no branch is created; the worktree is pinned to the
        # immutable snapshot commit via the run-scoped ref.
        _git(repo, "worktree", "add", "--detach", str(target), snapshot.ref)
        created = True
        # Defensive: confirm the worktree HEAD matches the snapshot commit.
        head = _git(Path(target), "rev-parse", "HEAD").strip()
        if head != snapshot.commit:
            raise SandboxError(
                f"sandbox worktree HEAD {head!r} != snapshot commit "
                f"{snapshot.commit!r}"
            )
    except Exception:
        if created:
            # Remove only the just-created exact worktree on any failure.
            _remove_worktree(repo, target)
        raise

    # Persist immutably; O_EXCL detects an existing sandbox id.
    target_receipt = _receipt_path(request.root, request.run_id, request.sandbox_id)
    if not _persist_immutable(
        target_receipt, receipt.model_dump(mode="json")
    ):
        existing = load_sandbox_receipt(
            request.root, request.run_id, request.sandbox_id
        )
        if existing.model_dump() != receipt.model_dump():
            # Roll back the orphaned worktree so it cannot masquerade as usable.
            _remove_worktree(repo, target)
            raise SandboxConflictError(
                f"sandbox id {request.sandbox_id!r} already exists with a "
                "conflicting request; original receipt preserved"
            )
        # Identical replay: receipt already matches; remove the redundant
        # freshly-created worktree to keep a single source of truth.
        _remove_worktree(repo, target)
        return existing

    return receipt


def _remove_worktree(repo: Path, target: Path) -> None:
    """Remove exactly the worktree at *target* only if it is registered.

    An unregistered path is never touched (it is not ours to remove).
    """
    entry = _worktree_entry_for_path(repo, target)
    if entry is None:
        return
    _git(repo, "worktree", "remove", "--force", str(target))


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------
def cleanup_sandbox(
    root: Path | str,
    repo: Path | str,
    run_id: str,
    sandbox_id: str,
    cleanup_id: str,
) -> SandboxCleanupReceipt:
    """Remove an authorized sandbox worktree after positive-ownership checks.

    Loads the creation receipt, validates that the live worktree is exactly the
    one we created (same deterministic path, detached HEAD at the snapshot
    commit, and sharing the repo's common dir), then runs
    ``git worktree remove --force`` only for that worktree. A cleanup receipt is
    persisted immutably; it is idempotent by cleanup_id and conflicting reuse
    fails closed.
    """
    if not cleanup_id or any(
        char
        not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
        for char in cleanup_id
    ):
        raise SandboxValidationError("invalid cleanup id")

    repo_path = Path(repo).resolve()
    if not (repo_path / ".git").exists():
        raise SandboxValidationError(f"not a git repository: {repo_path}")

    # Idempotency first: a valid cleanup receipt for this id wins.
    cleanup_target = _receipt_path(root, run_id, cleanup_id, cleanup=True)
    if cleanup_target.exists():
        existing = load_cleanup_receipt(root, run_id, cleanup_id)
        if existing.sandbox_id != sandbox_id:
            raise SandboxConflictError(
                f"cleanup id {cleanup_id!r} already used for a different sandbox"
            )
        return existing

    receipt = load_sandbox_receipt(root, run_id, sandbox_id)
    if receipt.run_id != run_id:
        raise SandboxValidationError("sandbox receipt run does not match request")

    target = Path(receipt.path).resolve()
    repo_resolved = repo_path.resolve()

    # Refuse to touch the operator checkout or any .git location.
    if target == repo_resolved or (
        repo_resolved / ".git"
    ) in target.parents or str(target).endswith("/.git"):
        raise SandboxValidationError(
            f"refusing to touch operator checkout or .git at {target}"
        )

    # The receipt path must equal the deterministic path for this sandbox.
    deterministic = sandbox_path(
        repo_path, run_id, receipt.kind, sandbox_id
    ).resolve()
    if target != deterministic:
        raise SandboxValidationError(
            "sandbox receipt path is not the deterministic path"
        )

    # Positive ownership: the worktree must be registered, detached at the
    # snapshot commit, and share this repo's common dir (never a foreign repo).
    entry = _worktree_entry_for_path(repo_path, target)
    if entry is None:
        raise SandboxOwnershipError(
            f"sandbox worktree {target} is not a registered worktree of {repo_path}"
        )
    if entry.get("HEAD") != receipt.snapshot_commit:
        raise SandboxOwnershipError(
            f"sandbox worktree HEAD {entry.get('HEAD')!r} does not match the "
            f"creation receipt commit {receipt.snapshot_commit!r}"
        )
    if not entry.get("detached"):
        raise SandboxOwnershipError(
            "sandbox worktree is not in the expected detached state"
        )
    common = Path(
        _git(Path(target), "rev-parse", "--git-common-dir").strip()
    ).resolve()
    repo_common = _common_dir(repo_path)
    if common != repo_common:
        raise SandboxOwnershipError(
            f"sandbox worktree common dir {common} does not match repo common "
            f"dir {repo_common}; refusing to touch a foreign worktree"
        )

    _git(repo_path, "worktree", "remove", "--force", str(target))

    cleanup_receipt = SandboxCleanupReceipt(
        cleanup_id=cleanup_id,
        sandbox_id=sandbox_id,
        run_id=run_id,
        kind=receipt.kind,
        path=str(target),
        snapshot_commit=receipt.snapshot_commit,
        removed=True,
    )
    if not _persist_immutable(
        cleanup_target, cleanup_receipt.model_dump(mode="json")
    ):
        # Concurrent writer won; return the already-persisted record (detect a
        # conflicting sandbox ownership).
        concurrent = load_cleanup_receipt(root, run_id, cleanup_id)
        if concurrent.sandbox_id != sandbox_id:
            raise SandboxConflictError(
                f"cleanup id {cleanup_id!r} already used for a different sandbox"
            )
        return concurrent
    return cleanup_receipt
