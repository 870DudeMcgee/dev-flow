"""Deterministic durable Phase 4 packet advancement.

This is the *sole* mutating advancement entry point. Every durable transition
(dispatch, heartbeat, complete, fail, cancel, release, recover, retry) is driven
by an immutable, replayable :class:`AdvanceCommand` and recorded into an
append-only ``advancement-events.jsonl`` ledger. Authoritative records
(commands, outcomes, recovery receipts) are persisted immutably with ``O_EXCL``
+ ``fsync`` so identical replay returns the existing artifact and a conflicting
reuse fails closed.

Crash/restart recovery is purely reconstructive: the entire advancement state
for a run is rebuilt solely from the append-only event ledger plus the
immutable command / outcome / recovery records. No mutable side state is
required to reconstruct packet states, claims, attempts, or the ready set.

Contract highlights (Phase 4 packet B acceptance 6-18, 21-24, 26):
  - ``save_advancement_command`` persists a command by ``command_id``; identical
    replay returns the existing record, conflicting reuse fails closed.
  - ``advance_run`` loads the command and authoritative records under an
    ``fcntl`` run lock, replays the ledger, verifies the exact live Phase 3
    authorization / plan / snapshot / ref on dispatch and retry, writes an
    immutable outcome by ``command_id`` (same outcome for identical replay),
    and fails closed on conflicting command / outcome / corruption with no side
    effects.
  - Each outcome/snapshot persists the complete deterministic ready set derived
    from exact packet states, but dispatch creates at most one active packet
    globally. Initial states are ``pending``; success unlocks dependencies;
    ``failed``/``cancelled`` stay non-ready until owner-specific retry.
  - dispatch only fires when the packet is in the current ready set and no
    active claim exists. It calls :func:`create_sandbox` first with the
    deterministic ``packet-<packet_id>-attempt-<N>`` id, then appends the atomic
    claim + attempt-start events. Exact sandbox, claim, and attempt records
    exist before the outcome reports ``started``.
  - claims carry run/packet/owner/command/attempt/state/timestamps; attempts are
    append-only and uniquely bound. All timestamps are timezone-aware UTC.
  - owner-only transitions; stale/wrong-owner fails. Cancellation is durable and
    idempotent; a cancelled claim can never complete. complete/fail/cancel
    require a safe direct run-file ``evidence_reference`` that exists; events
    preserve it. LoopStage is never updated here.
  - recovery only after lease expiry at ``now``, with matching claim version /
    lease, and an immutable direct run evidence file. A :class:`RecoveryReceipt`
    is persisted BEFORE the release / recovered event. A live or heartbeat-
    extended claim cannot be recovered.
  - retry names the prior claim/packet only; derives owner_id and route exactly
    from the prior attempt (command may not override), requires a terminal
    prior failed/cancelled/recovered state and (when recovered) a recovery
    receipt, preserves all previous evidence, and creates the next numbered
    sandbox/claim/attempt only when the packet is current ready-after-retry and
    no active claim exists.
  - completion/failure may call the workflow ledger only when the command
    carries a fully typed ``NodeReceipt`` + ``WorkflowEvent`` and only through
    ``record_node_outcome``; otherwise packet state changes do not stage-
    advance. ``adapter.advance_loop_state`` is never called.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from devflow.loop.execution_authorization import (
    ExecutionAuthorizationReceipt,
    load_execution_authorization,
)
from devflow.loop.execution_plan import (
    ExecutionPlan,
    execution_plan_hash,
    load_execution_plan,
)
from devflow.loop.git_sandbox import SandboxKind, SandboxRequest, create_sandbox
from devflow.loop.packet_dag import (
    PacketState,
    ready_packet_ids,
    validate_packet_dag,
)
from devflow.loop.pipeline_run import pipeline_runs_dir
from devflow.loop.source_snapshot import (
    SnapshotError,
    load_source_snapshot_receipt,
)
from devflow.loop.workflow_ledger import (
    NodeReceipt,
    WorkflowEvent,
    record_node_outcome,
    replay_workflow_run,
)

__all__ = [
    "AdvanceAction",
    "AdvanceCommand",
    "AdvanceOutcome",
    "AdvancementSnapshot",
    "ClaimState",
    "PacketAttempt",
    "PacketClaim",
    "RecoveryReceipt",
    "advance_run",
    "load_advancement_command",
    "load_advancement_outcome",
    "load_advancement_snapshot",
    "save_advancement_command",
]


# ---------------------------------------------------------------------------
# Deterministic persistence constants
# ---------------------------------------------------------------------------
_COMMAND_DIR = "advancement-commands"
_OUTCOME_DIR = "advancement-outcomes"
_RECOVERY_DIR = "advancement-recoveries"
_EVENTS_FILE = "advancement-events.jsonl"
_SNAPSHOT_FILE = "advancement-snapshot.json"
_RUN_LOCK = ".advancement.lock"

_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"
# Safe direct run-file name used by evidence_reference.
_EVIDENCE_NAME_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]*$"
_DEFAULT_LEASE_SECONDS = 300
_MIN_LEASE_SECONDS = 30
_MAX_LEASE_SECONDS = 3600

_ADVANCE_ACTIONS = (
    "dispatch",
    "heartbeat",
    "complete",
    "fail",
    "cancel",
    "release",
    "recover",
    "retry",
)


# ---------------------------------------------------------------------------
# Frozen enums / models
# ---------------------------------------------------------------------------
class AdvanceAction(str, Enum):
    """Closed set of advancement transition actions."""

    dispatch = "dispatch"
    heartbeat = "heartbeat"
    complete = "complete"
    fail = "fail"
    cancel = "cancel"
    release = "release"
    recover = "recover"
    retry = "retry"


class ClaimState(str, Enum):
    """Closed lifecycle of a packet claim."""

    active = "active"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"
    released = "released"
    recovered = "recovered"


class AdvanceCommand(BaseModel):
    """Immutable, replayable instruction for exactly one advancement transition.

    The command is persisted once (by ``command_id``) and read back verbatim by
    ``advance_run``. Every field required to reproduce the transition is frozen
    here so replay is deterministic and conflict detection is exact.
    """

    model_config = ConfigDict(extra="forbid")

    command_id: str = Field(min_length=1, pattern=_ID_PATTERN)
    run_id: str = Field(min_length=1, pattern=_ID_PATTERN)
    action: AdvanceAction
    owner_id: str = Field(min_length=1, pattern=_ID_PATTERN)
    packet_id: str = Field(min_length=1, pattern=_ID_PATTERN)
    # claim_id this command targets (heartbeat/complete/fail/cancel/release/
    # recover). Required for owner-bound transitions.
    claim_id: Optional[str] = Field(default=None, pattern=_ID_PATTERN)
    # attempt_id this command targets (heartbeat/complete/fail/cancel for an
    # active attempt). Optional; derived from the live claim when omitted.
    attempt_id: Optional[str] = Field(default=None, pattern=_ID_PATTERN)
    # default lease (seconds) applied on dispatch; bounded.
    lease_seconds: int = Field(
        default=_DEFAULT_LEASE_SECONDS,
        ge=_MIN_LEASE_SECONDS,
        le=_MAX_LEASE_SECONDS,
    )
    # evidence_reference is a safe direct run-file name required for
    # complete/fail/cancel. It must exist as a direct file inside the run dir.
    evidence_reference: Optional[str] = Field(
        default=None, pattern=_EVIDENCE_NAME_PATTERN
    )
    # Optional fully typed workflow outcome; only when present may
    # advance_run record a node outcome through the workflow ledger.
    workflow_receipt: Optional[NodeReceipt] = None
    workflow_event: Optional[WorkflowEvent] = None
    # retry targets a prior claim/attempt explicitly.
    retry_claim_id: Optional[str] = Field(default=None, pattern=_ID_PATTERN)
    # Explicit bounded concurrent sandbox limit passed to create_sandbox on
    # dispatch/retry. Prior sandboxes/evidence remain preserved.
    max_sandboxes: int = Field(default=8, ge=1, le=64)
    # Phase 5 opt-in: a successful completion carrying the full worker identity
    # captures its sandbox as an immutable packet patch before its outcome is
    # published. Older Phase 4 commands omit these fields and remain readable.
    patch_provider: Optional[str] = Field(default=None, min_length=1)
    patch_model: Optional[str] = Field(default=None, min_length=1)
    patch_model_family: Optional[str] = Field(default=None, min_length=1)
    # monotonic sequence assigned at persistence time for stable ordering.
    sequence: int = Field(default=0, ge=0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="after")
    def _check_evidence_required(self) -> "AdvanceCommand":
        if self.action in (AdvanceAction.complete, AdvanceAction.fail, AdvanceAction.cancel):
            if not self.evidence_reference:
                raise ValueError(
                    f"{self.action.value} requires a nonblank evidence_reference"
                )
        if self.action == AdvanceAction.retry and not self.retry_claim_id:
            raise ValueError("retry requires retry_claim_id")
        if self.action in (AdvanceAction.heartbeat, AdvanceAction.release, AdvanceAction.recover):
            if not self.claim_id:
                raise ValueError(f"{self.action.value} requires claim_id")
        if (self.workflow_receipt is None) != (self.workflow_event is None):
            raise ValueError(
                "workflow_receipt and workflow_event must be provided together"
            )
        patch_identity = (
            self.patch_provider,
            self.patch_model,
            self.patch_model_family,
        )
        if any(value is not None for value in patch_identity) and not all(
            value is not None for value in patch_identity
        ):
            raise ValueError(
                "patch_provider, patch_model, and patch_model_family must be supplied together"
            )
        if all(value is not None for value in patch_identity) and self.action != AdvanceAction.complete:
            raise ValueError(
                "packet patch capture identity is valid only for complete commands"
            )
        return self

    @property
    def is_typed_workflow(self) -> bool:
        """True only when both workflow receipt and event are fully typed."""
        return self.workflow_receipt is not None and self.workflow_event is not None

    @property
    def captures_packet_patch(self) -> bool:
        """Whether this successful completion requires Phase 5 patch capture."""
        return self.patch_provider is not None


class PacketClaim(BaseModel):
    """Immutable claim record binding one owner to one packet attempt."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    claim_id: str = Field(pattern=_ID_PATTERN)
    run_id: str = Field(pattern=_ID_PATTERN)
    packet_id: str = Field(pattern=_ID_PATTERN)
    owner_id: str = Field(pattern=_ID_PATTERN)
    command_id: str = Field(pattern=_ID_PATTERN)
    attempt_id: str = Field(pattern=_ID_PATTERN)
    state: ClaimState
    claimed_at: datetime
    lease_expires_at: datetime
    last_heartbeat_at: datetime
    version: int = Field(ge=1)


class PacketAttempt(BaseModel):
    """Append-only attempt record bound to a packet claim."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    attempt_id: str = Field(pattern=_ID_PATTERN)
    run_id: str = Field(pattern=_ID_PATTERN)
    packet_id: str = Field(pattern=_ID_PATTERN)
    owner_id: str = Field(pattern=_ID_PATTERN)
    claim_id: str = Field(pattern=_ID_PATTERN)
    command_id: str = Field(pattern=_ID_PATTERN)
    attempt_number: int = Field(ge=1)
    sandbox_id: str = Field(pattern=_ID_PATTERN)
    started_at: datetime
    route: str = Field(pattern=_ID_PATTERN)


class RecoveryReceipt(BaseModel):
    """Immutable receipt proving a claim was recovered after lease expiry."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    recovery_id: str = Field(pattern=_ID_PATTERN)
    run_id: str = Field(pattern=_ID_PATTERN)
    packet_id: str = Field(pattern=_ID_PATTERN)
    claim_id: str = Field(pattern=_ID_PATTERN)
    attempt_id: str = Field(pattern=_ID_PATTERN)
    owner_id: str = Field(pattern=_ID_PATTERN)
    recovered_by: str = Field(pattern=_ID_PATTERN)
    expected_version: int = Field(ge=1)
    lease_expires_at: datetime
    evidence_reference: str = Field(pattern=_EVIDENCE_NAME_PATTERN)
    recovered_at: datetime


class AdvanceOutcome(BaseModel):
    """Immutable, replay-stable outcome of advancing one command."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    command_id: str = Field(pattern=_ID_PATTERN)
    run_id: str = Field(pattern=_ID_PATTERN)
    action: AdvanceAction
    packet_id: str = Field(pattern=_ID_PATTERN)
    owner_id: str = Field(pattern=_ID_PATTERN)
    status: Literal["ok", "no-op", "rejected"]
    claim_id: Optional[str] = None
    attempt_id: Optional[str] = None
    recovery_id: Optional[str] = None
    event_sequence: int = Field(ge=0)
    message: str = ""
    ready_packet_ids: tuple[str, ...] = ()
    packet_state: Optional[PacketState] = None
    recorded_workflow: bool = False
    packet_patch_receipt_id: Optional[str] = None
    decided_at: datetime


class AdvancementSnapshot(BaseModel):
    """Reconstructable projection of the entire advancement state for a run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str = Field(pattern=_ID_PATTERN)
    packet_state: dict[str, PacketState]
    ready_packet_ids: tuple[str, ...]
    active_claim_id: Optional[str] = None
    claims: tuple[PacketClaim, ...] = ()
    attempts: tuple[PacketAttempt, ...] = ()
    next_attempt_number: dict[str, int]
    event_sequence: int = Field(ge=0)
    updated_at: datetime


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------
def _run_dir(root: Path | str, run_id: str) -> Path:
    runs = pipeline_runs_dir(root).resolve()
    run_dir = (runs / run_id).resolve()
    try:
        run_dir.relative_to(runs)
    except ValueError as exc:
        raise ValueError("advancement run id escapes the pipeline run directory") from exc
    if not run_dir.is_dir():
        raise ValueError(f"Pipeline run not found: {run_dir}")
    return run_dir


def _command_path(root: Path | str, run_id: str, command_id: str) -> Path:
    if not command_id or any(
        c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
        for c in command_id
    ):
        raise ValueError("invalid advancement command id")
    run_dir = _run_dir(root, run_id)
    target = (run_dir / _COMMAND_DIR / f"{command_id}.json").resolve()
    if target.parent != (run_dir / _COMMAND_DIR).resolve():
        raise ValueError("advancement command path escapes its store")
    return target


def _outcome_path(root: Path | str, run_id: str, command_id: str) -> Path:
    if not command_id or any(
        c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
        for c in command_id
    ):
        raise ValueError("invalid advancement outcome id")
    run_dir = _run_dir(root, run_id)
    target = (run_dir / _OUTCOME_DIR / f"{command_id}.json").resolve()
    if target.parent != (run_dir / _OUTCOME_DIR).resolve():
        raise ValueError("advancement outcome path escapes its store")
    return target


def _recovery_path(root: Path | str, run_id: str, recovery_id: str) -> Path:
    if not recovery_id or any(
        c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
        for c in recovery_id
    ):
        raise ValueError("invalid advancement recovery id")
    run_dir = _run_dir(root, run_id)
    target = (run_dir / _RECOVERY_DIR / f"{recovery_id}.json").resolve()
    if target.parent != (run_dir / _RECOVERY_DIR).resolve():
        raise ValueError("advancement recovery path escapes its store")
    return target


def _events_path(root: Path | str, run_id: str) -> Path:
    return _run_dir(root, run_id) / _EVENTS_FILE


def _snapshot_path(root: Path | str, run_id: str) -> Path:
    return _run_dir(root, run_id) / _SNAPSHOT_FILE


def _lock_path(root: Path | str, run_id: str) -> Path:
    return _run_dir(root, run_id) / _RUN_LOCK


# ---------------------------------------------------------------------------
# Immutable persistence helpers (O_EXCL + fsync)
# ---------------------------------------------------------------------------
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


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _load_advance_command_record(root: Path | str, run_id: str, command_id: str) -> AdvanceCommand:
    target = _command_path(root, run_id, command_id)
    try:
        cmd = AdvanceCommand.model_validate_json(target.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"advancement command {command_id!r} is missing or corrupt") from exc
    if cmd.command_id != command_id or cmd.run_id != run_id:
        raise ValueError("advancement command does not match its path")
    return cmd


def _load_outcome_record(root: Path | str, run_id: str, command_id: str) -> AdvanceOutcome:
    target = _outcome_path(root, run_id, command_id)
    try:
        outcome = AdvanceOutcome.model_validate_json(target.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"advancement outcome {command_id!r} is missing or corrupt") from exc
    if outcome.command_id != command_id or outcome.run_id != run_id:
        raise ValueError("advancement outcome does not match its path")
    return outcome


def _load_recovery_record(root: Path | str, run_id: str, recovery_id: str) -> RecoveryReceipt:
    target = _recovery_path(root, run_id, recovery_id)
    try:
        rec = RecoveryReceipt.model_validate_json(target.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"recovery receipt {recovery_id!r} is missing or corrupt") from exc
    if rec.recovery_id != recovery_id or rec.run_id != run_id:
        raise ValueError("recovery receipt does not match its path")
    return rec


# ---------------------------------------------------------------------------
# Public: persist command
# ---------------------------------------------------------------------------
def save_advancement_command(
    root: Path | str,
    run_id: str,
    command: AdvanceCommand,
) -> AdvanceCommand:
    """Immutably persist a command by ``command_id``.

    Identical replay (same fields) returns the existing record. A conflicting
    reuse of a command id with a different payload fails closed and preserves
    the original.
    """
    existing_path = _command_path(root, run_id, command.command_id)
    if existing_path.exists():
        existing = _load_advance_command_record(root, run_id, command.command_id)
        if existing == command:
            return existing
        raise ValueError(
            f"conflicting advancement command: {command.command_id!r} already "
            "exists with a different payload; original preserved"
        )
    if not _persist_immutable(existing_path, command.model_dump(mode="json")):
        existing = _load_advance_command_record(root, run_id, command.command_id)
        if existing == command:
            return existing
        raise ValueError(
            f"conflicting advancement command: {command.command_id!r} already "
            "exists with a different payload; original preserved"
        )
    return command


# ---------------------------------------------------------------------------
# Ledger replay (authoritative reconstruction)
# ---------------------------------------------------------------------------
def _parse_events(raw_text: str) -> list[dict]:
    events: list[dict] = []
    for line_number, line in enumerate(raw_text.splitlines(), start=1):
        if not line.strip():
            # An empty/blank line in the append-only ledger is corruption.
            raise ValueError(f"advancement event line {line_number} is empty")
        try:
            ev = json.loads(line)
        except ValueError as exc:
            raise ValueError(f"advancement event line {line_number} is corrupt") from exc
        events.append(ev)
    return events


def _validate_event_line(ev: dict, expected_event_id: str) -> None:
    if not isinstance(ev, dict):
        raise ValueError("advancement event must be an object")
    if ev.get("event_id") != expected_event_id:
        raise ValueError(
            f"advancement event id mismatch: expected {expected_event_id!r}, "
            f"got {ev.get('event_id')!r}"
        )


# Event type markers (kept as string literals for stable serialization).
_EV_CLAIM_START = "claim.start"
_EV_ATTEMPT_START = "attempt.start"
_EV_DISPATCH_START = "dispatch.start"
_EV_HEARTBEAT = "claim.heartbeat"
_EV_COMPLETE = "claim.complete"
_EV_FAIL = "claim.fail"
_EV_CANCEL = "claim.cancel"
_EV_RELEASE = "claim.release"
_EV_RECOVERED = "claim.recovered"
_EV_RETRY_CLAIM_START = "retry.claim.start"
_EV_RETRY_ATTEMPT_START = "retry.attempt.start"
_EV_RETRY_START = "retry.start"
_EV_STATE = "snapshot.state"


def _replay_ledger(root: Path | str, run_id: str) -> AdvancementSnapshot:
    """Reconstruct the full advancement state solely from the event ledger.

    The ledger is the single source of truth. Commands/outcomes/recoveries are
    immutable references consulted during transitions, but the durable state
    (packet states, claims, attempts, ready set) is rebuilt entirely from the
    typed, monotonic event lines.
    """
    # Validate the run exists; the resolved dir is not otherwise needed here.
    _run_dir(root, run_id)
    plan = load_execution_plan(root, run_id)
    packets = validate_packet_dag(plan.packets)
    packet_ids = [p.id for p in packets]

    events_text = ""
    events_file = _events_path(root, run_id)
    if events_file.is_file():
        events_text = events_file.read_text(encoding="utf-8")
    events = _parse_events(events_text)

    # Exact, ordered packet state projection. Initial state is pending.
    packet_state: dict[str, PacketState] = {pid: PacketState.pending for pid in packet_ids}
    claims: dict[str, PacketClaim] = {}
    attempts: dict[str, PacketAttempt] = {}
    next_attempt_number: dict[str, int] = {pid: 1 for pid in packet_ids}
    active_claim_id: Optional[str] = None
    # Authoritative timestamps observed in the ledger drive an idempotent
    # updated_at so repeated replay reconstructs byte-identical snapshots.
    observed_ts: list[datetime] = []

    def _require_claim(claim_id: str, where: str) -> PacketClaim:
        claim = claims.get(claim_id)
        if claim is None:
            raise ValueError(f"advancement ledger references unknown claim {claim_id!r} ({where})")
        return claim

    def _require_attempt(attempt_id: str, where: str) -> PacketAttempt:
        attempt = attempts.get(attempt_id)
        if attempt is None:
            raise ValueError(f"advancement ledger references unknown attempt {attempt_id!r} ({where})")
        return attempt

    expected_counter = 0
    for ev in events:
        _validate_event_line(ev, f"adv-{expected_counter:06d}")
        expected_counter += 1
        kind = ev.get("kind")
        if kind in (_EV_DISPATCH_START, _EV_RETRY_START):
            claim = PacketClaim.model_validate(ev["claim"])
            attempt = PacketAttempt.model_validate(ev["attempt"])
            if claim.claim_id in claims:
                raise ValueError(f"duplicate claim id in ledger: {claim.claim_id!r}")
            if attempt.attempt_id in attempts:
                raise ValueError(f"duplicate attempt id in ledger: {attempt.attempt_id!r}")
            if (
                claim.attempt_id != attempt.attempt_id
                or attempt.claim_id != claim.claim_id
                or claim.packet_id != attempt.packet_id
                or claim.owner_id != attempt.owner_id
                or claim.command_id != attempt.command_id
            ):
                raise ValueError("atomic dispatch event has mismatched claim and attempt")
            claims[claim.claim_id] = claim
            attempts[attempt.attempt_id] = attempt
            active_claim_id = claim.claim_id
            next_attempt_number[attempt.packet_id] = max(
                next_attempt_number.get(attempt.packet_id, 1),
                attempt.attempt_number + 1,
            )
            observed_ts.extend((claim.claimed_at, attempt.started_at))
        elif kind == _EV_CLAIM_START:
            claim = PacketClaim.model_validate(ev["claim"])
            if claim.claim_id in claims:
                raise ValueError(f"duplicate claim id in ledger: {claim.claim_id!r}")
            claims[claim.claim_id] = claim
            active_claim_id = claim.claim_id
            observed_ts.append(claim.claimed_at)
        elif kind == _EV_ATTEMPT_START:
            attempt = PacketAttempt.model_validate(ev["attempt"])
            if attempt.attempt_id in attempts:
                raise ValueError(f"duplicate attempt id in ledger: {attempt.attempt_id!r}")
            attempts[attempt.attempt_id] = attempt
            nxt = attempt.attempt_number + 1
            if next_attempt_number.get(attempt.packet_id, 1) < nxt:
                next_attempt_number[attempt.packet_id] = nxt
            observed_ts.append(attempt.started_at)
        elif kind == _EV_HEARTBEAT:
            ts = _parse_ts(ev["at"])
            claim = _require_claim(ev["claim_id"], "heartbeat")
            claims[claim.claim_id] = claim.model_copy(
                update={
                    "last_heartbeat_at": ts,
                    "version": ev["version"],
                    "lease_expires_at": _parse_ts(ev.get("lease_expires_at", ev["at"])),
                }
            )
            observed_ts.append(ts)
        elif kind == _EV_COMPLETE:
            claim = _require_claim(ev["claim_id"], "complete")
            claims[claim.claim_id] = claim.model_copy(update={"state": ClaimState.completed})
            if active_claim_id == claim.claim_id:
                active_claim_id = None
            packet_state[claim.packet_id] = PacketState.succeeded
            observed_ts.append(_parse_ts(ev["at"]))
        elif kind == _EV_FAIL:
            claim = _require_claim(ev["claim_id"], "fail")
            claims[claim.claim_id] = claim.model_copy(update={"state": ClaimState.failed})
            if active_claim_id == claim.claim_id:
                active_claim_id = None
            packet_state[claim.packet_id] = PacketState.failed
            observed_ts.append(_parse_ts(ev["at"]))
        elif kind == _EV_CANCEL:
            claim = _require_claim(ev["claim_id"], "cancel")
            claims[claim.claim_id] = claim.model_copy(update={"state": ClaimState.cancelled})
            if active_claim_id == claim.claim_id:
                active_claim_id = None
            # cancelled stays non-ready: packet_state remains whatever it is
            # (typically pending) and is never promoted automatically.
            observed_ts.append(_parse_ts(ev["at"]))
        elif kind == _EV_RELEASE:
            claim = _require_claim(ev["claim_id"], "release")
            claims[claim.claim_id] = claim.model_copy(update={"state": ClaimState.released})
            if active_claim_id == claim.claim_id:
                active_claim_id = None
            observed_ts.append(_parse_ts(ev["at"]))
        elif kind == _EV_RECOVERED:
            claim = _require_claim(ev["claim_id"], "recovered")
            claims[claim.claim_id] = claim.model_copy(update={"state": ClaimState.recovered})
            if active_claim_id == claim.claim_id:
                active_claim_id = None
            observed_ts.append(_parse_ts(ev["at"]))
        elif kind == _EV_RETRY_CLAIM_START:
            claim = PacketClaim.model_validate(ev["claim"])
            if claim.claim_id in claims:
                raise ValueError(f"duplicate retry claim id in ledger: {claim.claim_id!r}")
            claims[claim.claim_id] = claim
            active_claim_id = claim.claim_id
            observed_ts.append(claim.claimed_at)
        elif kind == _EV_RETRY_ATTEMPT_START:
            attempt = PacketAttempt.model_validate(ev["attempt"])
            if attempt.attempt_id in attempts:
                raise ValueError(f"duplicate retry attempt id in ledger: {attempt.attempt_id!r}")
            attempts[attempt.attempt_id] = attempt
            nxt = attempt.attempt_number + 1
            if next_attempt_number.get(attempt.packet_id, 1) < nxt:
                next_attempt_number[attempt.packet_id] = nxt
        elif kind == _EV_STATE:
            pass  # audits only; packet_state already projected from transitions
        else:
            raise ValueError(f"unknown advancement event kind: {kind!r}")

    for claim in claims.values():
        attempt = attempts.get(claim.attempt_id)
        if attempt is None or attempt.claim_id != claim.claim_id:
            raise ValueError(
                f"advancement ledger claim {claim.claim_id!r} has no matching attempt"
            )

    ready = ready_packet_ids(
        packets, {pid: packet_state[pid].value for pid in packet_ids}
    )
    # Deterministic, replay-stable timestamp: derive from the authoritative
    # ledger timestamps (max observed) so identical replays compare equal.
    # Missing/unparseable entries fall back to the Unix epoch in UTC.
    updated_at = datetime(1970, 1, 1, tzinfo=timezone.utc)
    for ts in observed_ts:
        try:
            ts = _parse_ts(ts)
        except (ValueError, TypeError):
            continue
        if ts > updated_at:
            updated_at = ts
    return AdvancementSnapshot(
        run_id=run_id,
        packet_state=packet_state,
        ready_packet_ids=ready,
        active_claim_id=active_claim_id,
        claims=tuple(claims.values()),
        attempts=tuple(attempts.values()),
        next_attempt_number=next_attempt_number,
        event_sequence=expected_counter,
        updated_at=updated_at,
    )


def _parse_ts(value) -> datetime:
    if isinstance(value, datetime):
        ts = value
    else:
        ts = datetime.fromisoformat(value)
    if ts.tzinfo is None:
        raise ValueError("advancement timestamp must be timezone-aware UTC")
    return ts.astimezone(timezone.utc)


def _fmt_ts(ts: datetime) -> str:
    return ts.astimezone(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Event append (atomic, fsync)
# ---------------------------------------------------------------------------
def _append_event(root: Path | str, run_id: str, *, sequence: int, kind: str, **fields: object) -> None:
    # Validate the run directory exists; the resolved path is not otherwise used.
    _run_dir(root, run_id)
    payload = {
        "event_id": f"adv-{sequence:06d}",
        "kind": kind,
        "sequence": sequence,
        **fields,
    }
    target = _events_path(root, run_id)
    target.parent.mkdir(mode=0o755, exist_ok=True)
    with open(str(target), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def _write_snapshot(root: Path | str, run_id: str, snapshot: AdvancementSnapshot) -> None:
    run_dir = _run_dir(root, run_id)
    path = _snapshot_path(root, run_id)
    temp = run_dir / f".{_SNAPSHOT_FILE}.tmp"
    temp.write_text(
        json.dumps(snapshot.model_dump(mode="json"), indent=2, sort_keys=True, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )
    os.replace(str(temp), str(path))


# ---------------------------------------------------------------------------
# Authoritative Phase 3 verification
# ---------------------------------------------------------------------------
def _verify_phase3(
    root: Path | str,
    run_id: str,
    authorization_id: str,
    now: datetime,
) -> tuple[ExecutionPlan, ExecutionAuthorizationReceipt, str]:
    """Verify the exact live Phase 3 chain at request time.

    Returns (plan, authorization, snapshot_commit). Raises on any mismatch so
    dispatch/retry fail closed before any side effect.
    """
    plan = load_execution_plan(root, run_id)
    plan_hash = execution_plan_hash(plan)

    auth = load_execution_authorization(root, run_id, authorization_id)
    if auth.execution_plan_hash != plan_hash:
        raise ValueError("authorization plan hash does not match the approved plan")

    try:
        snapshot = load_source_snapshot_receipt(root, run_id, auth.snapshot_id)
    except SnapshotError as exc:
        raise ValueError(f"source snapshot is missing or corrupt: {exc}") from exc
    if snapshot.fingerprint != auth.snapshot_fingerprint:
        raise ValueError("snapshot fingerprint does not match the authorization")
    if snapshot.commit != auth.snapshot_commit:
        raise ValueError("snapshot commit does not match the authorization")
    if snapshot.selected_paths != plan.target_files:
        raise ValueError("snapshot selected paths do not match the approved plan targets")

    repo = Path(root).resolve()
    if not (repo / ".git").exists():
        raise ValueError(f"not a git repository: {repo}")
    import subprocess

    result = subprocess.run(
        ["git", "rev-parse", snapshot.ref],
        cwd=str(repo),
        shell=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ValueError(f"snapshot ref {snapshot.ref!r} does not resolve")
    live_ref = result.stdout.strip()
    if live_ref != snapshot.commit:
        raise ValueError(
            f"snapshot ref {snapshot.ref!r} resolves to {live_ref!r}, "
            f"expected {snapshot.commit!r}"
        )
    return plan, auth, snapshot.commit


# ---------------------------------------------------------------------------
# Evidence reference validation
# ---------------------------------------------------------------------------
def _validate_evidence_reference(root: Path | str, run_id: str, reference: str) -> str | None:
    ref = Path(reference)
    if ref.is_absolute() or ref.name != reference:
        return f"evidence_reference {reference!r} is not a safe direct run-file name"
    run_dir = _run_dir(root, run_id)
    target = (run_dir / reference).resolve()
    try:
        target.relative_to(run_dir)
    except ValueError:
        return f"evidence_reference {reference!r} escapes the run directory"
    if not target.is_file():
        return f"evidence_reference {reference!r} does not exist as a run file"
    return None


# ---------------------------------------------------------------------------
# Public: load snapshot (reconstructive)
# ---------------------------------------------------------------------------
def load_advancement_snapshot(root: Path | str, run_id: str) -> AdvancementSnapshot:
    """Reconstruct the advancement state solely from the append-only ledger."""
    return _replay_ledger(root, run_id)


def load_advancement_command(
    root: Path | str, run_id: str, command_id: str
) -> AdvanceCommand:
    """Public: load and validate an immutable :class:`AdvanceCommand` record.

    Raises :class:`ValueError` if the record is missing, corrupt, or does not
    match its path (so a supervisor can fail closed on malformed commands).
    """
    return _load_advance_command_record(root, run_id, command_id)


def load_advancement_outcome(
    root: Path | str, run_id: str, command_id: str
) -> AdvanceOutcome:
    """Public: load and validate an immutable :class:`AdvanceOutcome` record.

    Raises :class:`ValueError` if the record is missing, corrupt, or does not
    match its path (so a supervisor can fail closed on malformed outcomes).
    """
    return _load_outcome_record(root, run_id, command_id)


def _recover_committed_outcome(
    root: Path | str,
    repo: Path | str,
    run_id: str,
    command: AdvanceCommand,
    snapshot: AdvancementSnapshot,
) -> Optional[AdvanceOutcome]:
    """Finish an outcome after its authoritative event survived a crash."""
    events_path = _events_path(root, run_id)
    if not events_path.is_file():
        return None
    committed: Optional[dict] = None
    for event in _parse_events(events_path.read_text(encoding="utf-8")):
        event_command_id = event.get("command_id")
        if event.get("kind") in (_EV_DISPATCH_START, _EV_RETRY_START):
            event_command_id = event.get("claim", {}).get("command_id")
        if event_command_id == command.command_id:
            if committed is not None:
                raise ValueError(
                    f"command {command.command_id!r} appears more than once in the advancement ledger"
                )
            committed = event
    if committed is None:
        return None

    claim_id = committed.get("claim_id")
    attempt_id = committed.get("attempt_id")
    if "claim" in committed:
        claim_id = committed["claim"]["claim_id"]
    if "attempt" in committed:
        attempt_id = committed["attempt"]["attempt_id"]
    decided_at = _parse_ts(
        committed.get("at") or committed.get("claim", {}).get("claimed_at")
    )
    message = {
        AdvanceAction.dispatch: "dispatched; sandbox, claim, and attempt established",
        AdvanceAction.heartbeat: "heartbeat accepted; lease extended",
        AdvanceAction.complete: "complete accepted",
        AdvanceAction.fail: "fail accepted",
        AdvanceAction.cancel: "cancel accepted; claim cancelled and never completable",
        AdvanceAction.release: "release accepted",
        AdvanceAction.recover: "recover accepted; claim released and marked recovered",
        AdvanceAction.retry: "retry dispatched with derived owner/route and preserved evidence",
    }[command.action]
    packet_state = None
    if command.action == AdvanceAction.dispatch:
        packet_state = PacketState.pending
    elif command.action == AdvanceAction.complete:
        packet_state = PacketState.succeeded
    elif command.action == AdvanceAction.fail:
        packet_state = PacketState.failed
    recorded_workflow = False
    if (
        command.action in (AdvanceAction.complete, AdvanceAction.fail)
        and command.is_typed_workflow
    ):
        recorded_workflow = _maybe_record_workflow(root, run_id, command, snapshot)
    packet_patch_receipt_id = _capture_completed_patch(
        root, Path(repo), run_id, command, snapshot, decided_at
    )
    _write_snapshot(root, run_id, snapshot)
    return _ok(
        root,
        run_id,
        command,
        snapshot,
        decided_at,
        claim_id=claim_id,
        attempt_id=attempt_id,
        recovery_id=committed.get("recovery_id"),
        packet_state=packet_state,
        recorded_workflow=recorded_workflow,
        packet_patch_receipt_id=packet_patch_receipt_id,
        message=message,
    )


# ---------------------------------------------------------------------------
# Public: advance_run (sole mutating entry point)
# ---------------------------------------------------------------------------
def advance_run(
    root: Path | str,
    repo: Path | str,
    run_id: str,
    command_id: str,
    *,
    now: Optional[datetime] = None,
) -> AdvanceOutcome:
    """Apply exactly one advancement transition for ``command_id``.

    This is the sole mutating entry point. It loads the immutable command and
    authoritative records under an ``fcntl`` run lock, replays the append-only
    ledger, verifies the exact live Phase 3 chain on dispatch/retry, writes an
    immutable outcome by ``command_id`` (identical replay returns the existing
    outcome), and fails closed on conflicting command / outcome / corruption
    with no side effects.
    """
    if now is None:
        now = _utcnow()
    now = _parse_ts(now)

    _run_dir(root, run_id)

    # Identical replay: an existing outcome wins immediately (no side effects).
    outcome_path = _outcome_path(root, run_id, command_id)
    if outcome_path.exists():
        return _load_outcome_record(root, run_id, command_id)

    # Load and validate the immutable command.
    try:
        command = _load_advance_command_record(root, run_id, command_id)
    except ValueError as exc:
        raise ValueError(f"advancement command {command_id!r} missing or corrupt") from exc

    # Serialize the whole transition under an exclusive run lock so no two
    # advancement transitions for a run interleave.
    import fcntl

    lock_path = _lock_path(root, run_id)
    with lock_path.open("a+b") as lock_fh:
        fcntl.flock(lock_fh.fileno(), fcntl.LOCK_EX)
        try:
            snapshot = _replay_ledger(root, run_id)
            committed_outcome = _recover_committed_outcome(
                root, repo, run_id, command, snapshot
            )
            if committed_outcome is not None:
                return committed_outcome

            if command.action == AdvanceAction.dispatch:
                return _do_dispatch(root, repo, run_id, command, snapshot, now)
            if command.action == AdvanceAction.heartbeat:
                return _do_heartbeat(root, run_id, command, snapshot, now)
            if command.action == AdvanceAction.complete:
                return _do_terminal(root, repo, run_id, command, snapshot, now, _EV_COMPLETE, ClaimState.completed, PacketState.succeeded)
            if command.action == AdvanceAction.fail:
                return _do_terminal(root, repo, run_id, command, snapshot, now, _EV_FAIL, ClaimState.failed, PacketState.failed)
            if command.action == AdvanceAction.cancel:
                return _do_cancel(root, run_id, command, snapshot, now)
            if command.action == AdvanceAction.release:
                return _do_release(root, run_id, command, snapshot, now)
            if command.action == AdvanceAction.recover:
                return _do_recover(root, run_id, command, snapshot, now)
            if command.action == AdvanceAction.retry:
                return _do_retry(root, repo, run_id, command, snapshot, now)
            raise ValueError(f"unknown advancement action: {command.action!r}")
        finally:
            fcntl.flock(lock_fh.fileno(), fcntl.LOCK_UN)


# ---------------------------------------------------------------------------
# Transition handlers (assume lock held + snapshot replayed)
# ---------------------------------------------------------------------------
def _authorization_id_for(root, run_id, snapshot) -> str:
    # Reuse the one authorization recorded for the run (the run was authorized
    # exactly once via authorize_execution with the plan's ready set).
    from devflow.loop.pipeline_run import pipeline_runs_dir

    auth_dir = pipeline_runs_dir(root).resolve() / run_id / "execution-authorizations"
    if not auth_dir.is_dir():
        raise ValueError("no execution authorization exists for the run")
    auths = [p for p in auth_dir.iterdir() if p.is_file() and p.suffix == ".json"]
    if len(auths) != 1:
        raise ValueError("expected exactly one execution authorization for the run")
    return auths[0].stem


def _do_dispatch(root, repo, run_id, command, snapshot, now) -> AdvanceOutcome:
    # One active packet globally.
    if snapshot.active_claim_id is not None:
        return _reject(root, run_id, command, snapshot, now,
                       "a packet is already active; dispatch refused until it settles")
    if any(claim.packet_id == command.packet_id for claim in snapshot.claims):
        return _reject(
            root,
            run_id,
            command,
            snapshot,
            now,
            "packet already has a claim; only owner-specific retry may create another attempt",
        )
    # Packet must be in the current ready set.
    if command.packet_id not in snapshot.ready_packet_ids:
        return _reject(root, run_id, command, snapshot, now,
                       f"packet {command.packet_id!r} is not ready")
    authorization_id = _authorization_id_for(root, run_id, snapshot)
    plan, auth, snapshot_commit = _verify_phase3(root, run_id, authorization_id, now)

    attempt_number = snapshot.next_attempt_number[command.packet_id]
    sandbox_id = f"{command.packet_id}-attempt-{attempt_number}"
    claim_id = f"claim-{command.packet_id}-{attempt_number}"
    attempt_id = f"attempt-{command.packet_id}-{attempt_number}"
    lease_expires_at = now + timedelta(seconds=command.lease_seconds)

    # Exact sandbox/claim/attempt records must exist BEFORE the outcome says
    # started. create_sandbox revalidates the full Phase 3 chain at request
    # time and is idempotent for identical requests.
    create_sandbox(
        SandboxRequest(
            repo=Path(repo).resolve(),
            root=Path(root).resolve(),
            run_id=run_id,
            sandbox_id=sandbox_id,
            kind=SandboxKind.packet,
            authorization_id=authorization_id,
            packet_id=command.packet_id,
            max_sandboxes=command.max_sandboxes,
        )
    )

    claim = PacketClaim(
        claim_id=claim_id,
        run_id=run_id,
        packet_id=command.packet_id,
        owner_id=command.owner_id,
        command_id=command.command_id,
        attempt_id=attempt_id,
        state=ClaimState.active,
        claimed_at=now,
        lease_expires_at=lease_expires_at,
        last_heartbeat_at=now,
        version=1,
    )
    attempt = PacketAttempt(
        attempt_id=attempt_id,
        run_id=run_id,
        packet_id=command.packet_id,
        owner_id=command.owner_id,
        claim_id=claim_id,
        command_id=command.command_id,
        attempt_number=attempt_number,
        sandbox_id=sandbox_id,
        started_at=now,
        route=command.owner_id,
    )

    # Claim and attempt are one atomic journal record: replay can never observe
    # one without the other after a crash.
    _append_event(
        root, run_id,
        sequence=snapshot.event_sequence,
        kind=_EV_DISPATCH_START,
        claim=claim.model_dump(mode="json"),
        attempt=attempt.model_dump(mode="json"),
        snapshot_commit=snapshot_commit,
        sandbox_id=sandbox_id,
    )
    new_snapshot = _replay_ledger(root, run_id)
    _write_snapshot(root, run_id, new_snapshot)
    return _ok(
        root, run_id, command, new_snapshot, now,
        claim_id=claim_id, attempt_id=attempt_id,
        packet_state=PacketState.pending,
        message="dispatched; sandbox, claim, and attempt established",
    )


def _claim_for_command(snapshot, command) -> PacketClaim:
    if command.claim_id:
        claim = next((c for c in snapshot.claims if c.claim_id == command.claim_id), None)
        if claim is None:
            raise ValueError(f"claim {command.claim_id!r} not found")
        return claim
    if snapshot.active_claim_id is not None:
        return next(c for c in snapshot.claims if c.claim_id == snapshot.active_claim_id)
    raise ValueError("no active claim for owner-bound command")


def _do_heartbeat(root, run_id, command, snapshot, now) -> AdvanceOutcome:
    claim = _claim_for_command(snapshot, command)
    if claim.state != ClaimState.active:
        return _reject(root, run_id, command, snapshot, now,
                       f"claim {claim.claim_id!r} is not active (state={claim.state.value})")
    if claim.owner_id != command.owner_id:
        return _reject(root, run_id, command, snapshot, now,
                       "heartbeat rejected: wrong owner")
    if command.claim_id and claim.claim_id != command.claim_id:
        return _reject(root, run_id, command, snapshot, now, "heartbeat claim id mismatch")
    if now > claim.lease_expires_at:
        return _reject(root, run_id, command, snapshot, now,
                       "heartbeat rejected: lease already expired (recover instead)")

    new_version = claim.version + 1
    new_lease = now + (claim.lease_expires_at - claim.last_heartbeat_at)
    claim.model_copy(
        update={"last_heartbeat_at": now, "version": new_version,
                "lease_expires_at": new_lease}
    )
    _append_event(
        root, run_id,
        sequence=snapshot.event_sequence,
        kind=_EV_HEARTBEAT,
        command_id=command.command_id,
        claim_id=claim.claim_id,
        at=_fmt_ts(now),
        version=new_version,
        lease_expires_at=_fmt_ts(new_lease),
    )
    new_snapshot = _replay_ledger(root, run_id)
    _write_snapshot(root, run_id, new_snapshot)
    return _ok(
        root, run_id, command, new_snapshot, now,
        claim_id=claim.claim_id,
        message="heartbeat accepted; lease extended",
    )


def _do_terminal(root, repo, run_id, command, snapshot, now, event_kind, claim_state, packet_state) -> AdvanceOutcome:
    claim = _claim_for_command(snapshot, command)
    if claim.state != ClaimState.active:
        return _reject(root, run_id, command, snapshot, now,
                       f"claim {claim.claim_id!r} is not active (state={claim.state.value})")
    if claim.owner_id != command.owner_id:
        return _reject(root, run_id, command, snapshot, now, "rejected: wrong owner")
    if not command.evidence_reference:
        return _reject(root, run_id, command, snapshot, now, "rejected: missing evidence_reference")
    evidence_err = _validate_evidence_reference(root, run_id, command.evidence_reference)
    if evidence_err is not None:
        return _reject(root, run_id, command, snapshot, now, f"rejected: {evidence_err}")

    # Typed-workflow precheck: a complete NodeReceipt/WorkflowEvent must agree
    # exactly with the authoritative replayed workflow state before this event
    # is allowed to land. Any position/outcome/receipt mismatch is rejected
    # without appending an event (no side effects).
    if command.is_typed_workflow:
        receipt = command.workflow_receipt
        event = command.workflow_event
        wf = replay_workflow_run(root, run_id)
        if wf.current_node_id != event.node_id:
            return _reject(
                root, run_id, command, snapshot, now,
                f"rejected: typed workflow event targets node {event.node_id!r} "
                f"but the workflow is at {wf.current_node_id!r}",
            )
        if wf.current_node_id != receipt.node_id:
            return _reject(
                root, run_id, command, snapshot, now,
                f"rejected: typed workflow receipt targets node {receipt.node_id!r} "
                f"but the workflow is at {wf.current_node_id!r}",
            )
        if (receipt.receipt_id != event.receipt_id
                or receipt.outcome != event.outcome
                or receipt.node_id != event.node_id):
            return _reject(
                root, run_id, command, snapshot, now,
                "rejected: typed workflow receipt/event receipt_id, outcome, "
                "or node_id mismatch",
            )

    _append_event(
        root, run_id,
        sequence=snapshot.event_sequence,
        kind=event_kind,
        command_id=command.command_id,
        claim_id=claim.claim_id,
        attempt_id=claim.attempt_id,
        evidence_reference=command.evidence_reference,
        at=_fmt_ts(now),
        packet_state=packet_state.value,
    )
    new_snapshot = _replay_ledger(root, run_id)
    recorded_workflow = False
    if command.is_typed_workflow:
        recorded_workflow = _maybe_record_workflow(root, run_id, command, new_snapshot)
    packet_patch_receipt_id = _capture_completed_patch(
        root, Path(repo), run_id, command, new_snapshot, now
    )
    _write_snapshot(root, run_id, new_snapshot)
    return _ok(
        root, run_id, command, new_snapshot, now,
        claim_id=claim.claim_id, attempt_id=claim.attempt_id,
        packet_state=packet_state,
        recorded_workflow=recorded_workflow,
        packet_patch_receipt_id=packet_patch_receipt_id,
        message=f"{command.action.value} accepted",
    )


def _do_cancel(root, run_id, command, snapshot, now) -> AdvanceOutcome:
    claim = _claim_for_command(snapshot, command)
    # Cancellation is durable/idempotent; a cancelled claim stays cancelled.
    if claim.state == ClaimState.cancelled:
        new_snapshot = _replay_ledger(root, run_id)
        return _ok(
            root, run_id, command, new_snapshot, now,
            claim_id=claim.claim_id,
            message="cancel is idempotent; claim already cancelled",
            status="no-op",
        )
    if claim.state != ClaimState.active:
        return _reject(root, run_id, command, snapshot, now,
                       f"cannot cancel claim {claim.claim_id!r} in state {claim.state.value}")
    if claim.owner_id != command.owner_id:
        return _reject(root, run_id, command, snapshot, now, "rejected: wrong owner")
    if not command.evidence_reference:
        return _reject(root, run_id, command, snapshot, now, "rejected: missing evidence_reference")
    evidence_err = _validate_evidence_reference(root, run_id, command.evidence_reference)
    if evidence_err is not None:
        return _reject(root, run_id, command, snapshot, now, f"rejected: {evidence_err}")

    _append_event(
        root, run_id,
        sequence=snapshot.event_sequence,
        kind=_EV_CANCEL,
        command_id=command.command_id,
        claim_id=claim.claim_id,
        attempt_id=claim.attempt_id,
        evidence_reference=command.evidence_reference,
        at=_fmt_ts(now),
    )
    new_snapshot = _replay_ledger(root, run_id)
    _write_snapshot(root, run_id, new_snapshot)
    return _ok(
        root, run_id, command, new_snapshot, now,
        claim_id=claim.claim_id, attempt_id=claim.attempt_id,
        message="cancel accepted; claim cancelled and never completable",
    )


def _do_release(root, run_id, command, snapshot, now) -> AdvanceOutcome:
    claim = _claim_for_command(snapshot, command)
    if claim.owner_id != command.owner_id:
        return _reject(root, run_id, command, snapshot, now, "rejected: wrong owner")
    if claim.state not in (ClaimState.active, ClaimState.recovered):
        return _reject(root, run_id, command, snapshot, now,
                       f"cannot release claim {claim.claim_id!r} in state {claim.state.value}")
    _append_event(
        root, run_id,
        sequence=snapshot.event_sequence,
        kind=_EV_RELEASE,
        command_id=command.command_id,
        claim_id=claim.claim_id,
        at=_fmt_ts(now),
    )
    new_snapshot = _replay_ledger(root, run_id)
    _write_snapshot(root, run_id, new_snapshot)
    return _ok(
        root, run_id, command, new_snapshot, now,
        claim_id=claim.claim_id,
        message="release accepted",
    )


def _do_recover(root, run_id, command, snapshot, now) -> AdvanceOutcome:
    claim = _claim_for_command(snapshot, command)
    if claim.owner_id != command.owner_id:
        return _reject(root, run_id, command, snapshot, now, "rejected: wrong owner")
    if claim.state != ClaimState.active:
        return _reject(root, run_id, command, snapshot, now,
                       f"cannot recover claim {claim.claim_id!r} in state {claim.state.value}")
    if now <= claim.lease_expires_at:
        return _reject(root, run_id, command, snapshot, now,
                       "rejected: lease not yet expired; heartbeat to extend instead")
    if command.claim_id and claim.claim_id != command.claim_id:
        return _reject(root, run_id, command, snapshot, now, "recover claim id mismatch")
    if not command.evidence_reference:
        return _reject(root, run_id, command, snapshot, now, "rejected: missing evidence_reference")
    evidence_err = _validate_evidence_reference(root, run_id, command.evidence_reference)
    if evidence_err is not None:
        return _reject(root, run_id, command, snapshot, now, f"rejected: {evidence_err}")

    recovery_id = f"recovery-{claim.claim_id}-{claim.version}"
    recovery = RecoveryReceipt(
        recovery_id=recovery_id,
        run_id=run_id,
        packet_id=claim.packet_id,
        claim_id=claim.claim_id,
        attempt_id=claim.attempt_id,
        owner_id=claim.owner_id,
        recovered_by=command.owner_id,
        expected_version=claim.version,
        lease_expires_at=claim.lease_expires_at,
        evidence_reference=command.evidence_reference,
        recovered_at=now,
    )
    # Persist RecoveryReceipt immutably BEFORE the release/recovered event.
    recovery_path = _recovery_path(root, run_id, recovery_id)
    if not _persist_immutable(recovery_path, recovery.model_dump(mode="json")):
        existing = _load_recovery_record(root, run_id, recovery_id)
        if existing != recovery:
            return _reject(root, run_id, command, snapshot, now,
                           "conflicting recovery receipt; original preserved")

    _append_event(
        root, run_id,
        sequence=snapshot.event_sequence,
        kind=_EV_RECOVERED,
        command_id=command.command_id,
        claim_id=claim.claim_id,
        recovery_id=recovery_id,
        at=_fmt_ts(now),
    )
    new_snapshot = _replay_ledger(root, run_id)
    _write_snapshot(root, run_id, new_snapshot)
    return _ok(
        root, run_id, command, new_snapshot, now,
        claim_id=claim.claim_id, recovery_id=recovery_id,
        message="recover accepted; claim released and marked recovered",
    )


def _do_retry(root, repo, run_id, command, snapshot, now) -> AdvanceOutcome:
    prior_claim = next(
        (c for c in snapshot.claims if c.claim_id == command.retry_claim_id), None
    )
    if prior_claim is None:
        return _reject(root, run_id, command, snapshot, now,
                       f"retry targets unknown claim {command.retry_claim_id!r}")
    # Terminal state required for retry.
    if prior_claim.state not in (ClaimState.failed, ClaimState.cancelled, ClaimState.recovered):
        return _reject(root, run_id, command, snapshot, now,
                       f"retry requires a terminal prior claim state; got {prior_claim.state.value}")
    if prior_claim.state == ClaimState.recovered:
        recovery = next(
            (r for r in _load_recoveries(root, run_id) if r.claim_id == prior_claim.claim_id),
            None,
        )
        if recovery is None:
            return _reject(root, run_id, command, snapshot, now,
                           "retry after recovery requires a recovery receipt")
    # Derive owner_id and route EXACTLY from the prior attempt.
    prior_attempt = next(
        (a for a in snapshot.attempts if a.attempt_id == prior_claim.attempt_id), None
    )
    if prior_attempt is None:
        return _reject(root, run_id, command, snapshot, now,
                       "retry targets a claim with no bound attempt")
    derived_owner = prior_attempt.owner_id
    derived_route = prior_attempt.route
    if command.owner_id != derived_owner:
        return _reject(root, run_id, command, snapshot, now,
                       "retry owner_id must derive exactly from the prior attempt")

    # One active packet globally.
    if snapshot.active_claim_id is not None:
        return _reject(root, run_id, command, snapshot, now,
                       "a packet is already active; retry refused until it settles")
    # Packet must be current ready-after-retry. A terminal prior claim leaves
    # the packet non-ready in the live snapshot, so recompute the ready set as
    # if this packet were reset to pending (the exact retry readiness rule).
    plan = load_execution_plan(root, run_id)
    retry_states = dict(snapshot.packet_state)
    retry_states[command.packet_id] = PacketState.pending
    retry_ready = ready_packet_ids(validate_packet_dag(plan.packets), retry_states)
    if command.packet_id not in retry_ready:
        return _reject(root, run_id, command, snapshot, now,
                       f"packet {command.packet_id!r} is not ready for retry")

    authorization_id = _authorization_id_for(root, run_id, snapshot)
    plan, auth, snapshot_commit = _verify_phase3(root, run_id, authorization_id, now)

    attempt_number = snapshot.next_attempt_number[command.packet_id]
    sandbox_id = f"{command.packet_id}-attempt-{attempt_number}"
    claim_id = f"claim-{command.packet_id}-{attempt_number}"
    attempt_id = f"attempt-{command.packet_id}-{attempt_number}"
    lease_expires_at = now + timedelta(seconds=command.lease_seconds)

    # Preserve all previous evidence: validate each prior evidence reference
    # exists and carry it forward implicitly via replay (events preserve them).
    _assert_prior_evidence_present(root, run_id, snapshot, prior_claim.claim_id)

    create_sandbox(
        SandboxRequest(
            repo=Path(repo).resolve(),
            root=Path(root).resolve(),
            run_id=run_id,
            sandbox_id=sandbox_id,
            kind=SandboxKind.packet,
            authorization_id=authorization_id,
            packet_id=command.packet_id,
            max_sandboxes=command.max_sandboxes,
        )
    )

    claim = PacketClaim(
        claim_id=claim_id,
        run_id=run_id,
        packet_id=command.packet_id,
        owner_id=derived_owner,
        command_id=command.command_id,
        attempt_id=attempt_id,
        state=ClaimState.active,
        claimed_at=now,
        lease_expires_at=lease_expires_at,
        last_heartbeat_at=now,
        version=1,
    )
    attempt = PacketAttempt(
        attempt_id=attempt_id,
        run_id=run_id,
        packet_id=command.packet_id,
        owner_id=derived_owner,
        claim_id=claim_id,
        command_id=command.command_id,
        attempt_number=attempt_number,
        sandbox_id=sandbox_id,
        started_at=now,
        route=derived_route,
    )
    _append_event(
        root, run_id,
        sequence=snapshot.event_sequence,
        kind=_EV_RETRY_START,
        claim=claim.model_dump(mode="json"),
        attempt=attempt.model_dump(mode="json"),
        prior_claim_id=prior_claim.claim_id,
        snapshot_commit=snapshot_commit,
        sandbox_id=sandbox_id,
    )
    new_snapshot = _replay_ledger(root, run_id)
    _write_snapshot(root, run_id, new_snapshot)
    return _ok(
        root, run_id, command, new_snapshot, now,
        claim_id=claim_id, attempt_id=attempt_id,
        message="retry dispatched with derived owner/route and preserved evidence",
    )


# ---------------------------------------------------------------------------
# Workflow ledger (optional typed path only)
# ---------------------------------------------------------------------------
def _maybe_record_workflow(root, run_id, command, snapshot) -> bool:
    if not command.is_typed_workflow:
        return False
    record_node_outcome(
        root, run_id,
        receipt=command.workflow_receipt,
        event=command.workflow_event,
    )
    return True


def _capture_completed_patch(root, repo, run_id, command, snapshot, captured_at):
    """Capture an opted-in completed packet before publishing its outcome.

    This runs on both the normal completion path and event-to-outcome recovery,
    so a crash after the completion event cannot strand a successful packet
    without its immutable Phase 5 patch receipt.
    """
    if command.action != AdvanceAction.complete or not command.captures_packet_patch:
        return None
    claim = next(
        (item for item in snapshot.claims if item.claim_id == command.claim_id),
        None,
    )
    if claim is None or claim.state != ClaimState.completed:
        raise ValueError("packet patch capture requires the committed completed claim")
    attempt = next(
        (item for item in snapshot.attempts if item.attempt_id == claim.attempt_id),
        None,
    )
    if attempt is None:
        raise ValueError("packet patch capture requires the completed attempt")
    from devflow.loop.run_integration import (
        PatchCaptureCommand,
        capture_packet_patch,
        save_patch_capture_command,
    )

    capture_command = PatchCaptureCommand(
        command_id=f"capture-{command.command_id}",
        run_id=run_id,
        packet_id=command.packet_id,
        claim_id=claim.claim_id,
        attempt_id=attempt.attempt_id,
        owner_id=attempt.owner_id,
        route=attempt.route,
        provider=command.patch_provider,
        model=command.patch_model,
        model_family=command.patch_model_family,
        created_at=captured_at,
    )
    save_patch_capture_command(root, capture_command)
    return capture_packet_patch(
        root, repo, run_id, capture_command.command_id
    ).receipt_id


def _load_recoveries(root, run_id) -> list[RecoveryReceipt]:
    run_dir = _run_dir(root, run_id)
    recovery_dir = run_dir / _RECOVERY_DIR
    if not recovery_dir.is_dir():
        return []
    out: list[RecoveryReceipt] = []
    for child in sorted(recovery_dir.iterdir()):
        if not (child.is_file() and child.suffix == ".json"):
            continue
        out.append(RecoveryReceipt.model_validate_json(child.read_text(encoding="utf-8")))
    return out


def _assert_prior_evidence_present(root, run_id, snapshot, prior_claim_id) -> None:
    """Ensure every evidence reference emitted under the prior claim exists."""
    run_dir = _run_dir(root, run_id)
    events_text = _events_path(root, run_id).read_text(encoding="utf-8")
    for line in events_text.splitlines():
        if not line.strip():
            continue
        ev = json.loads(line)
        if ev.get("claim_id") == prior_claim_id and "evidence_reference" in ev:
            ref = ev["evidence_reference"]
            if not (run_dir / ref).is_file():
                raise ValueError(
                    f"prior evidence_reference {ref!r} is missing; retry must preserve it"
                )


# ---------------------------------------------------------------------------
# Outcome writers
# ---------------------------------------------------------------------------
def _ok(
    root,
    run_id,
    command,
    snapshot,
    now,
    *,
    claim_id=None,
    attempt_id=None,
    recovery_id=None,
    packet_state=None,
    recorded_workflow=False,
    packet_patch_receipt_id=None,
    message="",
    status: Literal["ok", "no-op", "rejected"] = "ok",
) -> AdvanceOutcome:
    outcome = AdvanceOutcome(
        command_id=command.command_id,
        run_id=run_id,
        action=command.action,
        packet_id=command.packet_id,
        owner_id=command.owner_id,
        status=status,
        claim_id=claim_id,
        attempt_id=attempt_id,
        recovery_id=recovery_id,
        event_sequence=snapshot.event_sequence,
        message=message,
        ready_packet_ids=snapshot.ready_packet_ids,
        packet_state=packet_state,
        recorded_workflow=recorded_workflow,
        packet_patch_receipt_id=packet_patch_receipt_id,
        decided_at=now,
    )
    outcome_path = _outcome_path(root, run_id, command.command_id)
    if not _persist_immutable(outcome_path, outcome.model_dump(mode="json")):
        # Concurrent identical replay persisted first; return that record.
        outcome = _load_outcome_record(root, run_id, command.command_id)
    return outcome


def _reject(root, run_id, command, snapshot, now, message) -> AdvanceOutcome:
    outcome = AdvanceOutcome(
        command_id=command.command_id,
        run_id=run_id,
        action=command.action,
        packet_id=command.packet_id,
        owner_id=command.owner_id,
        status="rejected",
        event_sequence=snapshot.event_sequence,
        message=message,
        ready_packet_ids=snapshot.ready_packet_ids,
        decided_at=now,
    )
    outcome_path = _outcome_path(root, run_id, command.command_id)
    if not _persist_immutable(outcome_path, outcome.model_dump(mode="json")):
        outcome = _load_outcome_record(root, run_id, command.command_id)
    return outcome
