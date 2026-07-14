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

from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from pydantic import BaseModel, ConfigDict

from devflow.loop.run_advancement import (
    AdvanceAction,
    AdvanceOutcome,
    _outcome_path,
    advance_run,
    load_advancement_command,
    load_advancement_outcome,
    load_advancement_snapshot,
)

__all__ = [
    "SupervisorCycleResult",
    "pending_command_ids",
    "run_supervisor_cycle",
]

_MAX_COMMANDS_MIN = 1
_MAX_COMMANDS_MAX = 64
_COMMAND_DIR = "advancement-commands"


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

    Passing ``now`` forwards the same host time to ``advance_run`` only when
    supplied (otherwise each call uses its own ``advance_run`` default).
    """
    if max_commands < _MAX_COMMANDS_MIN or max_commands > _MAX_COMMANDS_MAX:
        raise ValueError(
            f"max_commands must be in {_MAX_COMMANDS_MIN}..{_MAX_COMMANDS_MAX}, "
            f"got {max_commands!r}"
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
