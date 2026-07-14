"""Safe real result-branch promotion (Phase 6B).

A *real* git branch under ``refs/heads/devflow/results/<run_id>`` is created
for an accepted, promotion-eligible :class:`~devflow.loop.workflow_ledger.DecisionReceipt`.
The branch is keyed **only** by ``run_id`` (no per-decision id component in the
ref path). Creation is create-only and uses the host-owned argv vector::

    git update-ref refs/heads/devflow/results/<run_id> <exact_verified_integration_head> ''

``shell=False`` is used for every git invocation. No checkout, rebuild,
squash, cherry-pick, regenerate, force-move, merge, PR, push, deploy, or
``main``/unrelated-ref mutation is ever performed.

Authority and immutability follow the strict frozen-model conventions of the
surrounding Phase 5/6 code:

* ``run_id`` is validated with the ref-safe pattern
  ``^[A-Za-z0-9][A-Za-z0-9._-]*$``;
* the full branch shorthand ``devflow/results/<run_id>`` is additionally
  validated by the host-owned ``git check-ref-format --branch ...``
  (``shell=False``) before any ref mutation;
* a strict immutable :class:`PromotionCommand` is persisted (O_EXCL + 0o444)
  **before** the side effect and a strict immutable :class:`PromotionReceipt`
  **after** the side effect, outside the generic artifact API
  (``promotion-<id>.json``);
* a promotion lock (``.promotion.lock``, ``fcntl.LOCK_EX``) serializes the
  side effect.

Reuse of Phase 5 / P6-A authority (never weakened):

* promotion requires the live :class:`DecisionReceipt` to be explicit
  ``accept`` / ``promotion_eligible`` and bound to a currently valid passing
  independent verification and an exact clean/non-stale integration
  head/tree/fingerprint — exactly the checks performed by
  :func:`devflow.loop.workflow_ledger.record_decision`.
* ``reject`` / ``request_changes`` create or move **no** branch.

Recovery / replay:

* exact replay is idempotent (missing receipt persisted without moving the ref
  when the exact branch + head + immutable command already bind);
* an existing branch pointing at another commit fails closed (no force move);
* a conflicting command / id replay fails closed.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from devflow.loop.pipeline_run import pipeline_runs_dir
from devflow.loop.run_integration import (
    IntegrationVerificationReceipt,
    _status_paths,
    _current_git_state,
    load_integration_snapshot,
    load_sandbox_receipt,
)
from devflow.loop.workflow_ledger import (
    DecisionReceipt,
    DecisionType,
)


# ---------------------------------------------------------------------------
# Constants (mirror surrounding Phase 5/6 conventions)
# ---------------------------------------------------------------------------
_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]*$"
_GIT_SHA = r"^[0-9a-f]{40,64}$"
_SHA256 = r"^[0-9a-f]{64}$"

RESULT_REF_NAMESPACE = "devflow/results"
PROMOTION_COMMAND_FILE_PREFIX = "promotion-command-"
PROMOTION_RECEIPT_FILE_PREFIX = "promotion-"
PROMOTION_LOCK_FILE = ".promotion.lock"

PromotionState = Literal["pending", "committed", "conflicting", "replayed", "colliding"]


class PromotionError(ValueError):
    """Fail-closed Phase 6B promotion error."""


class PromotionOutcome(str, Enum):
    """Why a promotion attempt resolved the way it did."""

    committed = "committed"
    replayed = "replayed"
    colliding = "colliding"
    conflicting = "conflicting"


# ---------------------------------------------------------------------------
# Frozen authoritative models
# ---------------------------------------------------------------------------
class PromotionCommand(BaseModel):
    """Immutable intent persisted before the branch side effect.

    Keyed only by ``run_id``. The exact ``integration_head`` is the single
    verified commit the branch will point at (no rebuild/squash/cherry-pick).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    promotion_id: str = Field(pattern=_ID_PATTERN)
    run_id: str = Field(pattern=_ID_PATTERN)
    decision_id: str = Field(pattern=_ID_PATTERN)
    integration_id: str = Field(pattern=_ID_PATTERN)
    integration_head: str = Field(pattern=_GIT_SHA)
    integration_tree: str = Field(pattern=_GIT_SHA)
    integration_fingerprint: str = Field(pattern=_SHA256)
    verification_receipt_id: str = Field(pattern=_ID_PATTERN)
    verification_receipt_hash: str = Field(pattern=_SHA256)
    created_at: datetime


class PromotionReceipt(BaseModel):
    """Immutable outcome persisted after the branch side effect.

    ``state`` distinguishes pending (command saved, side effect not yet proven),
    committed (branch created/confirmed at the exact head), conflicting
    (a conflicting command replay), and replayed (already-promoted idempotent
    replay). ``outcome`` mirrors :class:`PromotionOutcome`.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    promotion_id: str = Field(pattern=_ID_PATTERN)
    run_id: str = Field(pattern=_ID_PATTERN)
    decision_id: str = Field(pattern=_ID_PATTERN)
    integration_id: str = Field(pattern=_ID_PATTERN)
    integration_head: str = Field(pattern=_GIT_SHA)
    integration_tree: str = Field(pattern=_GIT_SHA)
    integration_fingerprint: str = Field(pattern=_SHA256)
    verification_receipt_id: str = Field(pattern=_ID_PATTERN)
    verification_receipt_hash: str = Field(pattern=_SHA256)
    branch: str
    commit: str = Field(pattern=_GIT_SHA)
    state: PromotionState
    outcome: PromotionOutcome
    created_at: datetime


# ---------------------------------------------------------------------------
# Filesystem / git helpers
# ---------------------------------------------------------------------------
def _run_dir(root: Path | str, run_id: str) -> Path:
    """Resolve and validate the run directory (guards path escapes)."""
    runs_dir = pipeline_runs_dir(root).resolve()
    run_dir = (runs_dir / run_id).resolve()
    try:
        run_dir.relative_to(runs_dir)
    except ValueError as exc:
        raise PromotionError("promotion run id escapes the pipeline run directory") from exc
    if not run_dir.is_dir():
        raise PromotionError(f"pipeline run {run_id!r} does not exist")
    return run_dir


def _safe_id(value: str) -> str:
    if not value or any(
        char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
        for char in value
    ):
        raise PromotionError("unsafe record id")
    return value


def _result_branch_ref(run_id: str) -> str:
    return f"refs/heads/{RESULT_REF_NAMESPACE}/{run_id}"


def _result_branch_shorthand(run_id: str) -> str:
    return f"{RESULT_REF_NAMESPACE}/{run_id}"


def _validate_run_id_ref_safe(run_id: str) -> None:
    """Validate ``run_id`` before any ref mutation.

    The full branch shorthand is validated by the host-owned
    ``git check-ref-format --branch`` (shell=False). A colon, ``..``,
    leading dot, double slash, or other ref hazard fails closed.
    """
    import re

    if not re.match(_ID_PATTERN, run_id):
        raise PromotionError(
            f"run id {run_id!r} is not ref-safe (expect {_ID_PATTERN})"
        )
    shorthand = _result_branch_shorthand(run_id)
    proc = subprocess.run(
        ["git", "check-ref-format", "--branch", shorthand],
        shell=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise PromotionError(
            f"branch name {shorthand!r} failed host-owned git check-ref-format: "
            f"{(proc.stderr or proc.stdout).strip()}"
        )


def _git(repo: Path, *args: str, timeout: int = 120, check: bool = True) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=repo,
            shell=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PromotionError(f"git {args[0] if args else ''} could not complete: {exc}") from exc
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout)[-4000:].strip()
        raise PromotionError(f"git {' '.join(args[:2])} failed: {detail}")
    return result


def _git_text(repo: Path, *args: str, **kwargs) -> str:
    return _git(repo, *args, **kwargs).stdout.strip()


def _sha256_canonical(model: BaseModel) -> str:
    payload = (
        json.dumps(model.model_dump(mode="json"), indent=2, sort_keys=True).encode()
        + b"\n"
    )
    return hashlib.sha256(payload).hexdigest()


def _persist_exclusive(path: Path, data: bytes, *, mode: int = 0o444) -> bool:
    """Write immutably (O_EXCL + mode). Return False if it already exists."""
    path.parent.mkdir(mode=0o755, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    except FileExistsError:
        return False
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return True


def _promotion_command_path(run_dir: Path, promotion_id: str) -> Path:
    _safe_id(promotion_id)
    path = (run_dir / f"{PROMOTION_COMMAND_FILE_PREFIX}{promotion_id}.json").resolve()
    if path.parent != run_dir:
        raise PromotionError("promotion command path escapes the run directory")
    return path


def _promotion_receipt_path(run_dir: Path, promotion_id: str) -> Path:
    _safe_id(promotion_id)
    path = (run_dir / f"{PROMOTION_RECEIPT_FILE_PREFIX}{promotion_id}.json").resolve()
    if path.parent != run_dir:
        raise PromotionError("promotion receipt path escapes the run directory")
    return path


def _promotion_lock(run_dir: Path):
    return (run_dir / PROMOTION_LOCK_FILE).open("a+b")


def load_promotion_receipt(root: Path | str, run_id: str, promotion_id: str) -> PromotionReceipt:
    """Load one immutable promotion receipt (malformed fails closed)."""
    path = _promotion_receipt_path(_run_dir(root, run_id), promotion_id)
    try:
        receipt = PromotionReceipt.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PromotionError(f"promotion receipt {promotion_id!r} is missing or corrupt") from exc
    if receipt.promotion_id != promotion_id or receipt.run_id != run_id:
        raise PromotionError("promotion receipt does not match its path")
    return receipt


def load_promotion_command(root: Path | str, run_id: str, promotion_id: str) -> PromotionCommand:
    """Load one immutable promotion command (malformed fails closed)."""
    path = _promotion_command_path(_run_dir(root, run_id), promotion_id)
    try:
        command = PromotionCommand.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PromotionError(f"promotion command {promotion_id!r} is missing or corrupt") from exc
    if command.promotion_id != promotion_id or command.run_id != run_id:
        raise PromotionError("promotion command does not match its path")
    return command


# ---------------------------------------------------------------------------
# Phase 5 / P6-A authority reuse (never weakened)
# ---------------------------------------------------------------------------
def _validate_promotion_authority(
    root: Path, run_dir: Path, receipt: DecisionReceipt
) -> tuple[str, str, Optional[str]]:
    """Reuse the Phase 5 / P6-A checks; return (head, tree, fingerprint).

    Mirrors the gating inside
    :func:`devflow.loop.workflow_ledger.record_decision`: the integration
    worktree must be clean and its live head/tree/fingerprint must match the
    receipt, and the bound independent verification receipt must be present,
    non-corrupt, passing, and of the ``integration_verification`` family with a
    canonical sha256 matching ``receipt.verification_receipt_hash``.
    """
    from devflow.loop.run_integration import load_integration_snapshot as _lis  # noqa: F401

    if receipt.decision_type != DecisionType.accept or not receipt.promotion_eligible:
        raise PromotionError(
            "promotion requires an explicit accept + promotion_eligible decision"
        )

    state = load_integration_snapshot(root, receipt.run_id)
    if state.integration_id != receipt.integration_id:
        raise PromotionError("decision is bound to a different integration id than the run")
    if state.sandbox_id is None:
        raise PromotionError("integration worktree has not been created")

    sandbox = load_sandbox_receipt(root, receipt.run_id, state.sandbox_id)
    worktree = Path(sandbox.path).resolve()
    if not worktree.is_dir():
        raise PromotionError("integration worktree is missing")

    if _status_paths(worktree):
        raise PromotionError("integration worktree is dirty")
    live_head, live_tree = _current_git_state(worktree)
    if (live_head, live_tree) != (receipt.integration_head, receipt.integration_tree):
        raise PromotionError(
            "integration worktree head/tree does not match the decision receipt"
        )
    if state.fingerprint != receipt.integration_fingerprint:
        raise PromotionError("integration fingerprint does not match the decision receipt")

    # --- Phase 5 independent verification receipt checks (reused) ---
    verification_path = (
        run_dir / "integration-verification-receipts" / f"{receipt.verification_receipt_id}.json"
    )
    try:
        verification = IntegrationVerificationReceipt.model_validate_json(
            verification_path.read_text(encoding="utf-8")
        )
    except (OSError, ValueError) as exc:
        raise PromotionError("bound integration verification receipt is missing or corrupt") from exc
    if verification.receipt_id != receipt.verification_receipt_id:
        raise PromotionError("integration verification receipt filename does not match its id")
    if verification.run_id != receipt.run_id:
        raise PromotionError("integration verification receipt is bound to a different run")
    if verification.integration_id != receipt.integration_id:
        raise PromotionError("integration verification receipt is bound to a different integration")
    if verification.verdict != "pass":
        raise PromotionError("decision cannot bind a non-passing integration verification receipt")

    try:
        verification_sha256 = _sha256_canonical(verification)
    except Exception as exc:  # pragma: no cover - defensive
        raise PromotionError("bound integration verification receipt is corrupt") from exc
    if verification_sha256 != receipt.verification_receipt_hash:
        raise PromotionError(
            "integration verification receipt hash does not match the decision receipt"
        )

    return live_head, live_tree, state.fingerprint


# ---------------------------------------------------------------------------
# Promotion
# ---------------------------------------------------------------------------
def create_result_ref(
    root: Path | str,
    repo: Path | str,
    receipt: DecisionReceipt,
    *,
    promotion_id: str,
    actor: str,
) -> PromotionReceipt:
    """Promote a real result branch for an accepted, promotion-eligible receipt.

    The branch ``refs/heads/devflow/results/<run_id>`` is created create-only
    (``git update-ref ... <exact_verified_integration_head> ''``) and points
    only at the exact verified integration head. ``reject`` /
    ``request_changes`` are rejected. Requires the live :class:`DecisionReceipt`
    to be explicit accept + promotion_eligible and bound to a currently valid
    passing independent verification and an exact clean/non-stale integration
    head/tree/fingerprint.

    Idempotent exact replay:

    * if the command already exists and is identical, and the branch already
      points at the exact verified head, the missing receipt (if any) is
      persisted *without moving the ref* and the result is reported as
      ``replayed``;
    * if the command conflicts (different intent for the same id), the replay
      fails closed with a ``conflicting`` receipt;
    * if the branch already points elsewhere, the attempt fails closed (no
      force move).

    The branch creation is serialized by a promotion lock. The immutable
    :class:`PromotionCommand` is persisted **before** the side effect; the
    :class:`PromotionReceipt` is persisted **after** it. Never checks out,
    rebuilds, squashes, cherry-picks, regenerates, force-moves, merges, PRs,
    pushes, deploys, or mutates ``main``/unrelated refs.
    """
    repo_path = Path(repo).resolve()
    if (repo_path / ".git").exists() is False:
        raise PromotionError(f"not a git repository: {repo_path}")
    _safe_id(promotion_id)
    if not actor:
        raise PromotionError("promotion actor must be set")

    _validate_run_id_ref_safe(receipt.run_id)
    run_dir = _run_dir(root, receipt.run_id)

    if receipt.decision_type != DecisionType.accept or not receipt.promotion_eligible:
        raise PromotionError(
            "only an explicit accept + promotion_eligible decision may promote a "
            "result branch; reject/request_changes create or move no branch"
        )

    command = PromotionCommand(
        promotion_id=promotion_id,
        run_id=receipt.run_id,
        decision_id=receipt.decision_id,
        integration_id=receipt.integration_id,
        integration_head=receipt.integration_head,
        integration_tree=receipt.integration_tree,
        integration_fingerprint=receipt.integration_fingerprint,
        verification_receipt_id=receipt.verification_receipt_id,
        verification_receipt_hash=receipt.verification_receipt_hash,
        created_at=datetime.now(timezone.utc),
    )
    command_payload = (
        json.dumps(command.model_dump(mode="json"), indent=2, sort_keys=True).encode() + b"\n"
    )
    command_path = _promotion_command_path(run_dir, promotion_id)
    receipt_path = _promotion_receipt_path(run_dir, promotion_id)
    branch_ref = _result_branch_ref(receipt.run_id)

    with _promotion_lock(run_dir) as lock_handle:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
        try:
            # --- Fail-closed conflict detection (BEFORE re-validating authority) ---
            # An identical promotion id bound to a DIFFERENT immutable command is a
            # conflicting replay: it must fail closed as ``conflicting`` regardless of
            # whether the new payload would otherwise pass authority. This keeps the
            # original command/branch authoritative and prevents a stale or forged
            # intent from mutating the ref.
            existing_command: Optional[PromotionCommand] = None
            if command_path.exists():
                existing_command = load_promotion_command(root, receipt.run_id, promotion_id)
                # Reuse the canonical stored timestamp so an identical semantic replay
                # is not mistaken for a conflict due to wall-clock drift in created_at.
                command = command.model_copy(update={"created_at": existing_command.created_at})
                if existing_command != command:
                    raise PromotionError(
                        f"conflicting promotion command for {promotion_id!r}; "
                        "original command preserved"
                    )

            head, tree, fingerprint = _validate_promotion_authority(
                Path(root).resolve(), run_dir, receipt
            )

            # Persist the immutable command BEFORE the side effect.
            if not _persist_exclusive(command_path, command_payload):
                # A concurrent writer won the race; re-check the persisted command.
                existing_command = load_promotion_command(root, receipt.run_id, promotion_id)
                command = command.model_copy(update={"created_at": existing_command.created_at})
                if existing_command != command:
                    raise PromotionError(
                        f"conflicting promotion command for {promotion_id!r}; "
                        "original command preserved"
                    )

            # Determine current branch state under the lock.
            branch_exists = (
                _git(repo_path, "rev-parse", "--verify", "--quiet", branch_ref, check=False).returncode == 0
            )
            if branch_exists:
                current_commit = _git_text(repo_path, "rev-parse", branch_ref)
                if current_commit != head:
                    # Pre-existing branch pointing elsewhere: fail closed, no force move.
                    _persist_receipt(
                        receipt_path,
                        command,
                        branch_ref,
                        current_commit,
                        state="colliding",
                        outcome=PromotionOutcome.colliding,
                    )
                    raise PromotionError(
                        f"result branch {branch_ref} already exists at a different "
                        f"commit {current_commit}; refusing to force-move"
                    )
                # Branch already points at the exact verified head: idempotent replay.
                # The canonical receipt is immutable; return an in-memory replayed
                # view derived from it. The committed file is never touched.
                return _persist_receipt(
                    receipt_path,
                    command,
                    branch_ref,
                    head,
                    state="replayed",
                    outcome=PromotionOutcome.replayed,
                )

            # Create-only side effect. No checkout/merge/squash/cherry-pick/push.
            _git(repo_path, "update-ref", branch_ref, head, "", timeout=120)

            return _persist_receipt(
                receipt_path,
                command,
                branch_ref,
                head,
                state="committed",
                outcome=PromotionOutcome.committed,
            )
        finally:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)


def _persist_receipt(
    receipt_path: Path,
    command: PromotionCommand,
    branch_ref: str,
    commit: str,
    *,
    state: PromotionState,
    outcome: PromotionOutcome,
) -> PromotionReceipt:
    """Persist the immutable canonical promotion receipt *exactly once*.

    The canonical ``promotion-<id>.json`` receipt is create-only: it is written
    a single time via ``O_EXCL`` + ``0o444`` and is thereafter byte-immutable
    authority. This function NEVER chmods, rewrites, replaces, or refreshes an
    existing receipt -- doing so would mutate committed authority and break the
    O_EXCL invariant.

    * If the canonical receipt is missing, it is O_EXCL-created once and the
      newly created receipt (carrying the requested ``state``/``outcome``) is
      returned.
    * If the canonical receipt already exists it is validated strictly for
      consistency with this exact command/branch/commit intent. A genuine
      conflict (different branch/commit for the same id) raises fail-closed.
      An idempotent exact replay (identical intent) returns an *in-memory*
      ``PromotionReceipt`` derived from the immutable committed receipt with the
      requested ``state``/``outcome`` (e.g. ``replayed``). The canonical file is
      never touched: same bytes, same SHA256, same mode, same timestamps.
    """
    receipt = PromotionReceipt(
        promotion_id=command.promotion_id,
        run_id=command.run_id,
        decision_id=command.decision_id,
        integration_id=command.integration_id,
        integration_head=command.integration_head,
        integration_tree=command.integration_tree,
        integration_fingerprint=command.integration_fingerprint,
        verification_receipt_id=command.verification_receipt_id,
        verification_receipt_hash=command.verification_receipt_hash,
        branch=branch_ref,
        commit=commit,
        state=state,
        outcome=outcome,
        created_at=command.created_at,
    )
    data = (
        json.dumps(receipt.model_dump(mode="json"), indent=2, sort_keys=True).encode() + b"\n"
    )
    # Create-only authority: write the canonical receipt exactly once via
    # O_EXCL + 0o444. A concurrent writer that already created it wins; we then
    # validate (never rewrite) below.
    if _persist_exclusive(receipt_path, data):
        return PromotionReceipt.model_validate_json(receipt_path.read_text(encoding="utf-8"))

    # Canonical receipt already exists: it is immutable authority. Never
    # chmod/rewrite/replace it. Strictly validate it binds to this exact
    # command/branch/commit intent; a mismatch for the same id is a genuine
    # conflict and must fail closed (the caller raises on collision).
    existing = PromotionReceipt.model_validate_json(receipt_path.read_text(encoding="utf-8"))
    if (
        existing.promotion_id != receipt.promotion_id
        or existing.run_id != receipt.run_id
        or existing.branch != receipt.branch
        or existing.commit != receipt.commit
    ):
        raise PromotionError(
            f"conflicting promotion receipt for {command.promotion_id!r}; "
            "original receipt preserved"
        )

    # Idempotent exact replay: the existing canonical receipt is consistent and
    # must be left byte-identical. Return an in-memory view carrying the
    # requested replay state (e.g. replayed) derived from the immutable
    # committed receipt. The canonical file is untouched.
    return existing.model_copy(update={"state": state, "outcome": outcome})


def result_branch_commit(root: Path | str, run_id: str) -> Optional[str]:
    """Return the commit the result branch points at, or None if absent."""
    _validate_run_id_ref_safe(run_id)
    repo_path = Path(root).resolve()
    branch_ref = _result_branch_ref(run_id)
    proc = _git(repo_path, "rev-parse", "--verify", "--quiet", branch_ref, check=False)
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()


def has_result_branch(root: Path | str, run_id: str) -> bool:
    """Return whether a real result branch exists for *run_id*."""
    return result_branch_commit(root, run_id) is not None


__all__ = [
    "PromotionCommand",
    "PromotionReceipt",
    "PromotionError",
    "PromotionOutcome",
    "create_result_ref",
    "load_promotion_receipt",
    "load_promotion_command",
    "has_result_branch",
    "result_branch_commit",
]
