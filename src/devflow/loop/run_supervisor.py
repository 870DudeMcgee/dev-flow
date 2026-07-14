"""Optional, repeat-only Phase 4 supervisor (r0).

The supervisor never creates or writes any Phase 4 durable record. It only
*discovers* already-immutable :class:`AdvanceCommand` JSONs in a run's
``advancement-commands`` directory, excludes those that already have a valid
immutable :class:`AdvanceOutcome`, and calls the single authoritative mutating
entry point :func:`~devflow.loop.run_advancement.advance_run` for the pending
ones.

It is deliberately a thin, stateless, side-effect-free orchestration layer:

* It performs exactly one ``advance_run`` call per pending command it selects;
  it does not invent a loop, sleep, retry, daemon, process, thread, or network.
* An optional host may call :func:`run_supervisor_cycle` repeatedly to drive
  the run to completion (restart/repeat semantics: a completed outcome excludes
  the command next cycle, so reruns make progress deterministically).
* It fails closed on malformed or unexpected command/outcome files.
* It never hides an advancement error: exceptions from ``advance_run``
  propagate to the caller.

Contract (cpb4-supervisor-build-r0):

* ``pending_command_ids`` returns the stable, sorted set of command ids that
  have no valid immutable outcome yet, validating every command filename and
  record. Malformed/unexpected files raise.
* ``run_supervisor_cycle`` accepts ``max_commands`` in ``1..64`` (explicit
  validation otherwise). It checks ``stop_requested`` before each call and
  invokes at most ``max_commands`` existing pending ids. Passing ``now``
  forwards the same host time only when supplied.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Callable, Optional

from pydantic import BaseModel, ConfigDict, Field

from devflow.loop.adapter import load_loop_state
from devflow.loop.models import LoopStage
from devflow.loop.run_advancement import (
    AdvanceAction,
    AdvanceOutcome,
    _outcome_path,
    advance_run,
    load_advancement_command,
    load_advancement_outcome,
    load_advancement_snapshot,
)
from devflow.loop.run_integration import (
    IntegrationCommand,
    IntegrationOutcome,
    integrate_run,
)

# Reserved authority prefixes owned solely by P6-A/P6-B (workflow_ledger.record_decision
# via the 'decision-' owned prefix, and result_branch via the 'promotion-command-' /
# 'promotion-' owned prefixes). The supervisor MUST never author, accept, redispatch,
# or synthesize a command that targets these reserved namespaces. A repeat-only
# supervisor is permitted to act ONLY on already-immutable advancement-command and
# integration-command records it discovers.
_RESERVED_DECISION_PREFIX = "decision-"
_RESERVED_PROMOTION_PREFIX = "promotion-"

__all__ = [
    "SupervisorCycleResult",
    "pending_command_ids",
    "run_supervisor_cycle",
    "IntegrationSupervisorCycleResult",
    "pending_integration_command_ids",
    "run_integration_supervisor_cycle",
    "phase6_reached_human_decision",
    "PushPrepareAuthorization",
    "DeployAuthorization",
    "PushPrepareCommand",
    "DeployAuthorizeCommand",
]

_MAX_COMMANDS_MIN = 1
_MAX_COMMANDS_MAX = 64
_COMMAND_DIR = "advancement-commands"

# The authoritative final node the supervisor must never cross automatically.
# After independent verification passes, the run parks at ``human_decision``;
# acceptance, rejection, request_changes, and result promotion are explicit
# external human-command actions that the supervisor may only *discover and
# redispatch* as already-immutable commands — it never synthesizes them.
_HUMAN_DECISION_STAGE = LoopStage.human_decision

_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"


def phase6_reached_human_decision(root: Path | str, run_id: str) -> bool:
    """Return True once the run has parked at the explicit ``human_decision`` stage.

    The supervisor uses this to enforce the hard human boundary: no redispatch,
    repeat, or restart path may cross ``human_decision`` automatically. Once the
    loop reaches ``human_decision`` the only legal progress is an explicit
    external human command (accept / reject / request_changes / promotion), which
    the supervisor never authors or simulates.
    """
    try:
        state = load_loop_state(root, run_id)
    except FileNotFoundError:
        return False
    return state.stage == _HUMAN_DECISION_STAGE


# ---------------------------------------------------------------------------
# Strict typed, disabled-by-default human-authorization boundaries (P6-C)
# ---------------------------------------------------------------------------
class PushPrepareAuthorization(str, Enum):
    """Closed set of explicit push/PR-preparation authorizations.

    Distinct from acceptance and promotion. The supervisor never performs any
    push/PR side effect; this is a reserved command/boundary that is disabled by
    default and only ever actioned by an explicit external human command.
    """

    prepare_push = "prepare_push"
    prepare_pr = "prepare_pr"


class DeployAuthorization(str, Enum):
    """Closed set of explicit deployment authorizations.

    Distinct from acceptance, promotion, and push/PR preparation. The supervisor
    never performs any deployment side effect; this is a reserved command/boundary
    that is disabled by default and only ever actioned by an explicit external
    human command.
    """

    deploy = "deploy"


class PushPrepareCommand(BaseModel):
    """Immutable, disabled-by-default push/PR-preparation authorization command.

    Strict typed frozen model following the live strict-model conventions used by
    the surrounding Phase 5/6 code (extra="forbid", frozen=True, ref-safe id
    patterns). It carries NO side-effect implementation: preparation of a push or
    PR is a separate, distinct human-authorization boundary that the supervisor
    must never execute or synthesize on its own. ``enabled`` is False by default
    so the boundary is inert unless an explicit external human command enables it.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    command_id: str = Field(pattern=_ID_PATTERN)
    run_id: str = Field(pattern=_ID_PATTERN)
    authorization: PushPrepareAuthorization
    enabled: bool = False
    actor: str = Field(default="", min_length=0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DeployAuthorizeCommand(BaseModel):
    """Immutable, disabled-by-default deployment-authorization command.

    Strict typed frozen model, distinct from acceptance, promotion, and
    push/PR preparation. It carries NO deployment side effect: deployment
    authorization is a separate human-authorization boundary that the supervisor
    must never execute or synthesize on its own. ``enabled`` is False by default.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    command_id: str = Field(pattern=_ID_PATTERN)
    run_id: str = Field(pattern=_ID_PATTERN)
    authorization: DeployAuthorization
    enabled: bool = False
    actor: str = Field(default="", min_length=0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SupervisorCycleResult(BaseModel):
    """Frozen result of exactly one supervisor cycle.

    ``considered_command_ids`` are the pending ids the cycle evaluated.
    ``advanced_command_ids`` are those for which ``advance_run`` was invoked.
    ``outcomes`` maps each advanced command id to its returned outcome.
    ``stopped`` is True when a stop was requested before a call was made.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    considered_command_ids: tuple[str, ...]
    advanced_command_ids: tuple[str, ...]
    outcomes: dict[str, AdvanceOutcome]
    stopped: bool


class IntegrationSupervisorCycleResult(BaseModel):
    """Frozen result of one repeat-only Phase 5 integration cycle."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    considered_command_ids: tuple[str, ...]
    advanced_command_ids: tuple[str, ...]
    outcomes: dict[str, IntegrationOutcome]
    stopped: bool


def _command_store(root: Path | str, run_id: str) -> Optional[Path]:
    """Locate the run's advancement-commands directory (resolving the run).

    Returns ``None`` when the run itself does not exist (so ``pending`` is
    trivially empty); otherwise the resolved ``advancement-commands`` path.
    """
    from devflow.loop.pipeline_run import pipeline_runs_dir

    runs = pipeline_runs_dir(root).resolve()
    run_dir = (runs / run_id).resolve()
    try:
        run_dir.relative_to(runs)
    except ValueError as exc:
        raise ValueError("supervisor run id escapes the pipeline run directory") from exc
    if not run_dir.is_dir():
        return None
    return run_dir / _COMMAND_DIR


def _command_is_reserved(command_id: str) -> Optional[str]:
    """Return the reserved authority prefix a command id targets, or None.

    The supervisor is strictly repeat-only: it may act ONLY on already-immutable
    advancement-command and integration-command records it discovers. Any command
    id whose filename targets a reserved P6-A/P6-B namespace (``decision-`` /
    ``promotion-``) is a reserved-authority command the supervisor is forbidden
    from authoring, accepting, redispatching, or synthesizing. Such ids must never
    appear in the advancement-commands store the supervisor drives; if one does,
    discovery fails closed.
    """
    if command_id.startswith(_RESERVED_DECISION_PREFIX):
        return _RESERVED_DECISION_PREFIX
    if command_id.startswith(_RESERVED_PROMOTION_PREFIX):
        return _RESERVED_PROMOTION_PREFIX
    return None


def pending_command_ids(root: Path | str, run_id: str) -> list[str]:
    """Stable sorted pending command ids with no valid immutable outcome.

    Every file in the run's ``advancement-commands`` directory is validated:

    * Only ``<command_id>.json`` files are expected (no stray files).
    * Each command record is loaded and validated via
      :func:`load_advancement_command`; malformed/missing/corrupt records
      raise :class:`ValueError` (fail closed).
    * A command that already has a valid immutable outcome (loaded and
      validated via :func:`load_advancement_outcome`, matching ``command_id``
      and ``run_id``) is excluded.

    Returns the command ids in stable sorted order.
    """
    store = _command_store(root, run_id)
    if store is None or not store.is_dir():
        return []

    pending: list[str] = []
    # Sorted iteration gives deterministic, stable ordering for both
    # discovery and the resulting list.
    for child in sorted(store.iterdir()):
        if not child.is_file():
            # Unexpected entry (subdirectory, symlink dir, etc.) fails closed.
            raise ValueError(
                f"unexpected entry in advancement-commands store: {child.name!r}"
            )
        if child.suffix != ".json":
            raise ValueError(
                f"unexpected non-JSON file in advancement-commands store: {child.name!r}"
            )
        command_id = child.stem
        # Reserved P6-A/P6-B authority commands (decision-*/promotion-*) are
        # forbidden inside the repeat-only supervisor store: the supervisor may
        # never author, accept, redispatch, or synthesize such commands. If one
        # appears, fail closed rather than treat it as a dispatchable command.
        reserved = _command_is_reserved(command_id)
        if reserved is not None:
            raise ValueError(
                f"supervisor command {command_id!r} targets reserved authority "
                f"prefix {reserved!r}; the repeat-only supervisor may not act on "
                f"reserved human-decision or result-branch authority"
            )
        # Hard human boundary: once the run has parked at human_decision, no
        # redispatch/repeat path may cross it automatically. Discovery stops.
        if phase6_reached_human_decision(root, run_id):
            break
        # Validates the command filename/id and the full record; raises on
        # malformed/missing/corrupt or path-mismatch.
        load_advancement_command(root, run_id, command_id)
        # Already decided (valid immutable outcome present)? Exclude it. A
        # missing outcome is exactly what marks a command pending; only a
        # corrupt/mismatched outcome fails closed.
        outcome_path = _outcome_path(root, run_id, command_id)
        if outcome_path.is_file():
            outcome = load_advancement_outcome(root, run_id, command_id)
            if outcome.status == "rejected":
                raise ValueError(
                    f"rejected supervisor command {command_id!r} is immutable; "
                    "persist a new command after correcting its preconditions"
                )
            continue
        pending.append(command_id)

    pending.sort()
    return pending


def _command_is_actionable(root: Path | str, run_id: str, command_id: str) -> bool:
    command = load_advancement_command(root, run_id, command_id)
    if command.action != AdvanceAction.dispatch:
        return True
    snapshot = load_advancement_snapshot(root, run_id)
    if snapshot.active_claim_id is not None:
        return False
    if command.packet_id not in snapshot.ready_packet_ids:
        return False
    return not any(
        claim.packet_id == command.packet_id for claim in snapshot.claims
    )


def run_supervisor_cycle(
    root: Path | str,
    repo: Path | str,
    run_id: str,
    *,
    max_commands: int = 1,
    stop_requested: Optional[Callable[[], bool]] = None,
    now: Optional[datetime] = None,
) -> SupervisorCycleResult:
    """Advance at most ``max_commands`` pending commands via ``advance_run``.

    The supervisor discovers pending commands, then for each one (in stable
    sorted order) checks ``stop_requested`` *before* invoking ``advance_run``.
    At most ``max_commands`` existing pending ids are advanced per cycle. If a
    stop is requested before a call, the cycle makes no further change and
    reports ``stopped=True``.

    ``max_commands`` must be in ``1..64``; other values raise
    :class:`ValueError`. Advancement errors are not caught or hidden: any
    exception from ``advance_run`` propagates to the caller.

    The supervisor is strictly repeat-only. It calls exactly ``advance_run``
    for already-immutable commands it discovers; it NEVER calls
    ``record_decision`` or ``create_result_ref`` and never synthesizes human
    acceptance. Once the run has parked at ``human_decision`` (the hard human
    boundary) discovery returns nothing, so no redispatch/repeat path crosses
    the boundary automatically. Acceptance, rejection, request_changes, and
    result promotion remain explicit external human-command actions.
    """
    if max_commands < _MAX_COMMANDS_MIN or max_commands > _MAX_COMMANDS_MAX:
        raise ValueError(
            f"max_commands must be in {_MAX_COMMANDS_MIN}..{_MAX_COMMANDS_MAX}, "
            f"got {max_commands!r}"
        )

    # Hard human boundary: the supervisor must not redispatch/repeat past the
    # explicit human_decision gate. Reserved-authority commands are rejected by
    # pending_command_ids, so this short-circuits any crossing attempt.
    if phase6_reached_human_decision(root, run_id):
        return SupervisorCycleResult(
            considered_command_ids=(),
            advanced_command_ids=(),
            outcomes={},
            stopped=False,
        )

    considered: list[str] = []
    advanced: list[str] = []
    outcomes: dict[str, AdvanceOutcome] = {}
    stopped = False

    pending = pending_command_ids(root, run_id)
    for command_id in pending:
        if len(advanced) >= max_commands:
            break
        if stop_requested is not None and stop_requested():
            # Stop before issuing the call: no change for this command.
            stopped = True
            break
        if not _command_is_actionable(root, run_id, command_id):
            continue
        considered.append(command_id)
        if now is None:
            outcome = advance_run(root, repo, run_id, command_id)
        else:
            outcome = advance_run(root, repo, run_id, command_id, now=now)
        advanced.append(command_id)
        outcomes[command_id] = outcome

    return SupervisorCycleResult(
        considered_command_ids=tuple(considered),
        advanced_command_ids=tuple(advanced),
        outcomes=outcomes,
        stopped=stopped,
    )


def pending_integration_command_ids(root: Path | str, run_id: str) -> list[str]:
    """Discover valid immutable integration commands without outcomes.

    The repeat-only supervisor may only rediscover already-persisted Phase 5
    integration commands. Reserved P6-A/P6-B authority commands
    (``decision-``/``promotion-``) are forbidden, and once the run parks at
    ``human_decision`` no further repeat/redispatch is permitted across that
    boundary — so discovery returns nothing.
    """
    from devflow.loop.pipeline_run import pipeline_runs_dir

    run_dir = (pipeline_runs_dir(root).resolve() / run_id).resolve()
    if not run_dir.is_dir():
        return []
    store = run_dir / "integration-commands"
    if not store.is_dir():
        return []
    # The hard human boundary is a whole-run property captured once before
    # iterating. Crucially, the reserved-authority check below MUST run before
    # any boundary short-circuit: a tampered ``decision-*``/``promotion-*`` file
    # in the integration-commands store must never be silently skipped by the
    # human_decision early return (fail-closed). This mirrors the correct
    # ordering in pending_command_ids (reserved check precedes the break).
    reached_human_decision = phase6_reached_human_decision(root, run_id)
    pending: list[str] = []
    for child in sorted(store.iterdir()):
        if not child.is_file() or child.suffix != ".json":
            raise ValueError(
                f"unexpected entry in integration-commands store: {child.name!r}"
            )
        # Reserved P6-A/P6-B authority commands are never integration commands
        # the supervisor may redispatch; fail closed if one appears here. This
        # check runs BEFORE the human_decision break so a reserved tamper is
        # always rejected, even after the run has parked at human_decision.
        reserved = _command_is_reserved(child.stem)
        if reserved is not None:
            raise ValueError(
                f"integration command {child.stem!r} targets reserved authority "
                f"prefix {reserved!r}; the repeat-only supervisor may not act on "
                f"reserved human-decision or result-branch authority"
            )
        # Hard human boundary: no redispatch/repeat path may cross
        # human_decision. Once reached, no further integration command is
        # considered pending (but any reserved file above was still rejected).
        if reached_human_decision:
            break
        try:
            command = IntegrationCommand.model_validate_json(
                child.read_text(encoding="utf-8")
            )
        except (OSError, ValueError) as exc:
            raise ValueError(
                f"integration command {child.stem!r} is corrupt"
            ) from exc
        if command.command_id != child.stem or command.run_id != run_id:
            raise ValueError("integration command does not match its path")
        outcome_path = (
            run_dir / "integration-outcomes" / f"{command.command_id}.json"
        )
        if outcome_path.exists():
            try:
                outcome = IntegrationOutcome.model_validate_json(
                    outcome_path.read_text(encoding="utf-8")
                )
            except (OSError, ValueError) as exc:
                raise ValueError(
                    f"integration outcome {command.command_id!r} is corrupt"
                ) from exc
            if outcome.command_id != command.command_id or outcome.run_id != run_id:
                raise ValueError("integration outcome does not match its path")
            continue
        pending.append(command.command_id)
    return pending


def run_integration_supervisor_cycle(
    root: Path | str,
    repo: Path | str,
    run_id: str,
    *,
    max_commands: int = 1,
    stop_requested: Optional[Callable[[], bool]] = None,
) -> IntegrationSupervisorCycleResult:
    """Repeat only already-persisted Phase 5 integration commands."""
    if max_commands < _MAX_COMMANDS_MIN or max_commands > _MAX_COMMANDS_MAX:
        raise ValueError(
            f"max_commands must be in {_MAX_COMMANDS_MIN}..{_MAX_COMMANDS_MAX}, "
            f"got {max_commands!r}"
        )
    # Hard human boundary: the supervisor must not redispatch/repeat past the
    # explicit human_decision gate. Reserved-authority commands are rejected by
    # pending_integration_command_ids, so this short-circuits any crossing
    # attempt before discovery even runs. Both guards are independent and must
    # agree: neither must silently skip a reserved tamper at the boundary.
    if phase6_reached_human_decision(root, run_id):
        return IntegrationSupervisorCycleResult(
            considered_command_ids=(),
            advanced_command_ids=(),
            outcomes={},
            stopped=False,
        )
    considered: list[str] = []
    advanced: list[str] = []
    outcomes: dict[str, IntegrationOutcome] = {}
    stopped = False
    for command_id in pending_integration_command_ids(root, run_id):
        if len(advanced) >= max_commands:
            break
        if stop_requested is not None and stop_requested():
            stopped = True
            break
        considered.append(command_id)
        outcome = integrate_run(root, repo, run_id, command_id)
        advanced.append(command_id)
        outcomes[command_id] = outcome
    return IntegrationSupervisorCycleResult(
        considered_command_ids=tuple(considered),
        advanced_command_ids=tuple(advanced),
        outcomes=outcomes,
        stopped=stopped,
    )
