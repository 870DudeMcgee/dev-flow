"""Bounded repair loop (M4-S4, blueprint §9.3).

A workflow-level repair loop with no-progress detection and retry bounds.
Failed nodes return to their own repair loop rather than restarting the
entire workflow. The loop stops when maximum rounds or no-progress
threshold is reached (blueprint §9.3).

This is distinct from the integration-repair in ``run_integration.py``
(which is per-packet, 3-attempt, conflict-driven). This is a workflow-level
repair policy with configurable bounds.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from devflow.loop.pipeline_run import pipeline_runs_dir

_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"
REPAIR_EVENTS_FILE = "repair-events.jsonl"


class RepairRound(BaseModel):
    """One round in a bounded repair loop."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    round_number: int = Field(ge=1)
    triggered_by: str = Field(min_length=1)  # what failed
    progress_detected: bool = False
    completed: bool = False
    timestamp: str = Field(min_length=1)
    schema_version: Literal[1] = 1


class RepairState(BaseModel):
    """Immutable snapshot of the repair loop state for one run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str = Field(pattern=_ID_PATTERN)
    rounds: tuple[RepairRound, ...] = ()
    max_rounds: int = Field(default=4, ge=1, le=10)
    stop_if_no_progress: int = Field(default=2, ge=1, le=5)
    exhausted: bool = False
    exhaustion_reason: str = ""


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def should_continue_repair(state: RepairState) -> bool:
    """True if repair can continue (not exhausted, making progress).

    The loop stops when:
    - ``exhausted`` is True
    - Round count >= ``max_rounds``
    - Consecutive no-progress rounds >= ``stop_if_no_progress``
    """
    if state.exhausted:
        return False

    if len(state.rounds) >= state.max_rounds:
        return False

    # Check consecutive no-progress streak
    consecutive_no_progress = 0
    for round_data in reversed(state.rounds):
        if not round_data.progress_detected:
            consecutive_no_progress += 1
        else:
            break

    if consecutive_no_progress >= state.stop_if_no_progress:
        return False

    return True


def compute_exhaustion(state: RepairState) -> RepairState:
    """Return a new RepairState with exhaustion status evaluated.

    Sets ``exhausted=True`` and records the reason when a bound is reached.
    """
    if state.exhausted:
        return state

    if len(state.rounds) >= state.max_rounds:
        return state.model_copy(update={
            "exhausted": True,
            "exhaustion_reason": f"max_rounds ({state.max_rounds}) reached",
        })

    consecutive_no_progress = 0
    for round_data in reversed(state.rounds):
        if not round_data.progress_detected:
            consecutive_no_progress += 1
        else:
            break

    if consecutive_no_progress >= state.stop_if_no_progress:
        return state.model_copy(update={
            "exhausted": True,
            "exhaustion_reason": (
                f"no-progress threshold ({state.stop_if_no_progress}) reached"
            ),
        })

    return state


def record_repair_round(
    root: Path | str,
    run_id: str,
    round_data: RepairRound,
    state: RepairState,
) -> RepairState:
    """Append a repair round and return updated state.

    Persists the round to ``repair-events.jsonl`` and returns a new
    :class:`RepairState` with the round added and exhaustion recomputed.
    """
    run_dir = pipeline_runs_dir(root) / run_id
    if not run_dir.is_dir():
        raise FileNotFoundError(f"Pipeline run not found: {run_id}")

    events_path = run_dir / REPAIR_EVENTS_FILE

    # Append the round event
    payload = json.dumps(round_data.model_dump(mode="json"), sort_keys=True) + "\n"
    with events_path.open("a", encoding="utf-8") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())

    # Update state
    new_rounds = state.rounds + (round_data,)
    updated = state.model_copy(update={"rounds": new_rounds})

    return compute_exhaustion(updated)


def load_repair_state(
    root: Path | str,
    run_id: str,
    max_rounds: int = 4,
    stop_if_no_progress: int = 2,
) -> RepairState:
    """Load repair state from persisted events."""
    run_dir = pipeline_runs_dir(root) / run_id
    events_path = run_dir / REPAIR_EVENTS_FILE
    if not events_path.is_file():
        return RepairState(
            run_id=run_id,
            max_rounds=max_rounds,
            stop_if_no_progress=stop_if_no_progress,
        )

    rounds: list[RepairRound] = []
    for line in events_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rounds.append(RepairRound.model_validate_json(line))
        except Exception:
            continue

    state = RepairState(
        run_id=run_id,
        rounds=tuple(rounds),
        max_rounds=max_rounds,
        stop_if_no_progress=stop_if_no_progress,
    )
    return compute_exhaustion(state)


__all__ = [
    "REPAIR_EVENTS_FILE",
    "RepairRound",
    "RepairState",
    "compute_exhaustion",
    "load_repair_state",
    "record_repair_round",
    "should_continue_repair",
]
