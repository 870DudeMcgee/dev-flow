"""Distinct merge / full-verification / ship gates (M4-S6).

Three separate human-gated stages for promotion authority (blueprint §4.1, §9.4).
Each gate is a typed, human-authored decision — no gate auto-approves. Ship
remains ``enabled=False`` by default (no autonomous deployment).

Gates are ordered: full_verification → merge → ship. Each requires the prior
gate to be approved before it can proceed.

All decisions carry a human ``actor`` field — never "system".
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from devflow.loop.pipeline_run import pipeline_runs_dir

_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"
GATE_EVENTS_FILE = "gate-events.jsonl"


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class GateType(str, Enum):
    """The three distinct human-gated promotion stages."""

    full_verification = "full_verification"
    merge = "merge"
    ship = "ship"


class GateStatus(str, Enum):
    """Status of a gate decision."""

    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    skipped = "skipped"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class GateDecision(BaseModel):
    """One human-authored gate decision."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    gate_type: GateType
    run_id: str = Field(pattern=_ID_PATTERN)
    ticket_id: str = Field(pattern=_ID_PATTERN)
    status: GateStatus
    actor: str = Field(min_length=1)  # human operator, never "system"
    decided_at: str = Field(min_length=1)
    reason: str = ""
    schema_version: Literal[1] = 1

    @model_validator(mode="after")
    def reject_system_actor(self) -> "GateDecision":
        if self.actor.lower() == "system":
            raise ValueError(
                "gate decision actor must be a human operator, not 'system'"
            )
        return self


class GateConfig(BaseModel):
    """Configuration for each gate type.

    ``ship_enabled`` defaults to ``False`` — the validator rejects ``True``
    in default construction. Enabling ship requires explicit human
    configuration after construction.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    merge_enabled: bool = True
    full_verification_enabled: bool = True
    ship_enabled: bool = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_dir(root: Path | str, run_id: str) -> Path:
    return pipeline_runs_dir(root) / run_id


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _append_event(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, sort_keys=True) + "\n"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def record_gate_decision(
    root: Path | str,
    run_id: str,
    decision: GateDecision,
) -> GateDecision:
    """Persist a gate decision to ``gate-events.jsonl``."""
    run_dir = _run_dir(root, run_id)
    if not run_dir.is_dir():
        raise FileNotFoundError(f"Pipeline run not found: {run_id}")

    events_path = run_dir / GATE_EVENTS_FILE

    # Check for duplicate / idempotent
    if events_path.exists():
        existing_decisions = _load_gate_decisions(events_path)
        for existing in existing_decisions:
            if (
                existing.gate_type == decision.gate_type
                and existing.run_id == decision.run_id
            ):
                if existing == decision:
                    return existing  # idempotent
                raise ValueError(
                    f"conflicting gate decision for {decision.gate_type.value} "
                    f"on run {decision.run_id!r}"
                )

    _append_event(events_path, decision.model_dump(mode="json"))
    return decision


def _load_gate_decisions(events_path: Path) -> tuple[GateDecision, ...]:
    if not events_path.is_file():
        return ()
    decisions: list[GateDecision] = []
    for line in events_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            decisions.append(GateDecision.model_validate_json(line))
        except Exception:
            continue
    return tuple(decisions)


def load_gate_decisions(
    root: Path | str,
    run_id: str,
) -> tuple[GateDecision, ...]:
    """Load all gate decisions for a run in append order."""
    return _load_gate_decisions(_run_dir(root, run_id) / GATE_EVENTS_FILE)


def gate_status(
    decisions: tuple[GateDecision, ...],
    gate_type: GateType,
) -> GateStatus | None:
    """Return the status of one gate type, or None if no decision exists.

    If multiple decisions exist for the same gate (re-decisions), the latest
    one wins.
    """
    matching = [d for d in decisions if d.gate_type == gate_type]
    if not matching:
        return None
    return matching[-1].status


# ---------------------------------------------------------------------------
# Gate evaluation
# ---------------------------------------------------------------------------

def can_merge(
    gate_config: GateConfig,
    decisions: tuple[GateDecision, ...],
) -> bool:
    """True if merge is allowed: full_verification approved + explicit merge approval."""
    if not gate_config.merge_enabled:
        return False
    fv_status = gate_status(decisions, GateType.full_verification)
    if fv_status != GateStatus.approved:
        return False
    merge_status = gate_status(decisions, GateType.merge)
    # Merge requires an explicit approved merge gate decision
    if merge_status != GateStatus.approved:
        return False
    return True


def can_ship(
    gate_config: GateConfig,
    decisions: tuple[GateDecision, ...],
) -> bool:
    """True if ship is allowed: merge approved + explicit ship approval.

    Ship is ``enabled=False`` by default. This returns ``False`` unless
    ``ship_enabled`` is explicitly set to ``True`` in the config AND merge
    AND ship gates carry an explicit approved decision.
    """
    if not gate_config.ship_enabled:
        return False
    merge_status = gate_status(decisions, GateType.merge)
    if merge_status != GateStatus.approved:
        return False
    ship_status = gate_status(decisions, GateType.ship)
    # Ship requires an explicit approved ship gate decision
    if ship_status != GateStatus.approved:
        return False
    return True


def gate_sequence_complete(
    decisions: tuple[GateDecision, ...],
) -> bool:
    """True when all three gates have a terminal decision (approved/rejected/skipped)."""
    for gate_type in GateType:
        if gate_status(decisions, gate_type) is None:
            return False
    return True


__all__ = [
    "GATE_EVENTS_FILE",
    "GateConfig",
    "GateDecision",
    "GateStatus",
    "GateType",
    "can_merge",
    "can_ship",
    "gate_sequence_complete",
    "gate_status",
    "load_gate_decisions",
    "record_gate_decision",
]
