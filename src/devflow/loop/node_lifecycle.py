"""Per-node lifecycle state machine (M2-S2).

Provides a richer per-node lifecycle (planned→ready→running→verified/retrying/
blocked/awaiting_gate/failed/cancelled) alongside the existing ``NodeReceipt``,
which is never mutated. Legacy success/failure receipts replay byte-identically.

The lifecycle is recorded as append-only events in ``node-lifecycle-events.jsonl``
within the run directory — a separate file from the ledger's ``workflow-events.jsonl``.
The two coexist; neither touches the other's state.

Usage::

    from devflow.loop.node_lifecycle import NodeState, record_lifecycle_event

    record_lifecycle_event(root, run_id, receipt=NodeLifecycleReceipt(
        lifecycle_id="lc-1",
        node_id="spec",
        run_id=run_id,
        from_state=NodeState.running,
        to_state=NodeState.verified,
        timestamp="2026-07-15T20:00:00Z",
    ))
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from devflow.loop.pipeline_run import pipeline_runs_dir

# ---------------------------------------------------------------------------
# File layout
# ---------------------------------------------------------------------------

LIFECYCLE_EVENTS_FILE = "node-lifecycle-events.jsonl"
_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"


# ---------------------------------------------------------------------------
# State enums (blueprint §5.1)
# ---------------------------------------------------------------------------

class NodeState(str, Enum):
    """Per-node lifecycle states."""

    planned = "planned"
    ready = "ready"
    running = "running"
    verified = "verified"
    retrying = "retrying"
    blocked = "blocked"
    awaiting_gate = "awaiting_gate"
    failed = "failed"
    cancelled = "cancelled"


class WorkflowTerminalState(str, Enum):
    """Workflow-level terminal states."""

    completed = "completed"
    awaiting_promotion = "awaiting_promotion"
    needs_rework = "needs_rework"
    failed = "failed"
    cancelled = "cancelled"
    shipped = "shipped"


# ---------------------------------------------------------------------------
# Legal transitions
# ---------------------------------------------------------------------------

_VALID_TRANSITIONS: dict[NodeState, frozenset[NodeState]] = {
    NodeState.planned: frozenset({NodeState.ready, NodeState.cancelled}),
    NodeState.ready: frozenset({NodeState.running, NodeState.cancelled}),
    NodeState.running: frozenset({
        NodeState.verified,
        NodeState.retrying,
        NodeState.failed,
        NodeState.blocked,
        NodeState.awaiting_gate,
        NodeState.cancelled,
    }),
    NodeState.retrying: frozenset({
        NodeState.running,
        NodeState.failed,
        NodeState.cancelled,
    }),
    NodeState.blocked: frozenset({NodeState.ready, NodeState.cancelled}),
    NodeState.awaiting_gate: frozenset({
        NodeState.running,
        NodeState.failed,
        NodeState.cancelled,
    }),
    # Terminal states — no outgoing transitions
    NodeState.verified: frozenset(),
    NodeState.failed: frozenset(),
    NodeState.cancelled: frozenset(),
}

TERMINAL_STATES: frozenset[NodeState] = frozenset({
    NodeState.verified,
    NodeState.failed,
    NodeState.cancelled,
})


def is_valid_transition(from_state: NodeState, to_state: NodeState) -> bool:
    """Return True if a transition is legal."""
    return to_state in _VALID_TRANSITIONS.get(from_state, frozenset())


# ---------------------------------------------------------------------------
# Receipt model
# ---------------------------------------------------------------------------

class NodeLifecycleReceipt(BaseModel):
    """Versioned, additive lifecycle event.

    Never replaces :class:`~devflow.loop.workflow_ledger.NodeReceipt`. Recorded
    alongside it as a separate append-only event. ``schema_version`` enables
    future evolution without breaking replay.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    lifecycle_id: str = Field(pattern=_ID_PATTERN)
    node_id: str = Field(pattern=_ID_PATTERN)
    run_id: str = Field(pattern=_ID_PATTERN)
    from_state: NodeState
    to_state: NodeState
    timestamp: str = Field(min_length=1)  # ISO UTC
    evidence_ref: str | None = None  # optional link to NodeReceipt receipt_id
    schema_version: Literal[1] = 1


# ---------------------------------------------------------------------------
# Legacy receipt → lifecycle mapping (read-only, never mutates)
# ---------------------------------------------------------------------------

# Maps legacy NodeReceipt outcomes to NodeState terminal states.
LEGACY_OUTCOME_MAP: dict[str, NodeState] = {
    "success": NodeState.verified,
    "failure": NodeState.failed,
}


def legacy_outcome_to_state(outcome: str) -> NodeState:
    """Map a legacy NodeReceipt outcome to a NodeState (read-only).

    This mapping is advisory — it lets new lifecycle consumers interpret
    old receipts without mutating them. The legacy receipt is never touched.

    Raises ValueError for unknown outcomes.
    """
    if outcome not in LEGACY_OUTCOME_MAP:
        raise ValueError(f"unknown legacy outcome {outcome!r}")
    return LEGACY_OUTCOME_MAP[outcome]


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def _run_dir(root: Path | str, run_id: str) -> Path:
    return pipeline_runs_dir(root) / run_id


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def record_lifecycle_event(
    root: Path | str,
    run_id: str,
    *,
    receipt: NodeLifecycleReceipt,
) -> NodeLifecycleReceipt:
    """Append one lifecycle event to the run directory.

    Validates the transition is legal, then appends to
    ``node-lifecycle-events.jsonl``. Never touches ``NodeReceipt``,
    ``WorkflowEvent``, or ``workflow-events.jsonl``.

    Raises ValueError for illegal transitions or duplicate lifecycle IDs.
    """
    run_dir = _run_dir(root, run_id)
    if not run_dir.is_dir():
        raise FileNotFoundError(f"Pipeline run not found: {run_id}")

    # Validate transition
    if not is_valid_transition(receipt.from_state, receipt.to_state):
        raise ValueError(
            f"illegal lifecycle transition: {receipt.from_state.value} → "
            f"{receipt.to_state.value} for node {receipt.node_id!r}"
        )

    # Bind the lifecycle event to its run.
    #
    # The path ``run_id`` is the authority for which run the event belongs to.
    # A receipt stamped for a genuinely different run is a trust-binding
    # violation and must be rejected.
    if receipt.run_id != run_id:
        raise ValueError(
            f"lifecycle event run_id {receipt.run_id!r} does not match "
            f"path run_id {run_id!r}"
        )

    events_path = run_dir / LIFECYCLE_EVENTS_FILE

    # Check for duplicate / idempotent replay
    if events_path.exists():
        for line in events_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                existing = NodeLifecycleReceipt.model_validate_json(line)
            except Exception:
                continue
            if existing.lifecycle_id == receipt.lifecycle_id:
                if (
                    existing.node_id == receipt.node_id
                    and existing.from_state == receipt.from_state
                    and existing.to_state == receipt.to_state
                ):
                    # Idempotent replay — exact same receipt already recorded
                    return existing
                raise ValueError(
                    f"duplicate lifecycle event id: {receipt.lifecycle_id}"
                )

    # Validate history continuity: the from_state must match the node's
    # current state (most recent to_state), or if no prior events exist
    # for this node, from_state must be 'planned' (the initial state).
    node_prior: list[NodeLifecycleReceipt] = []
    if events_path.exists():
        prior_events = [
            NodeLifecycleReceipt.model_validate_json(line)
            for line in events_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        node_prior = [e for e in prior_events if e.node_id == receipt.node_id]
    if node_prior:
        expected_from = node_prior[-1].to_state
        if receipt.from_state != expected_from:
            raise ValueError(
                f"discontinuous lifecycle: node {receipt.node_id!r} "
                f"expected from_state={expected_from.value}, "
                f"got {receipt.from_state.value}"
            )
    else:
        # First event for this node must start from planned
        if receipt.from_state != NodeState.planned:
            raise ValueError(
                f"discontinuous lifecycle: first event for node "
                f"{receipt.node_id!r} must have from_state=planned, "
                f"got {receipt.from_state.value}"
            )

    # Append the event
    payload = json.dumps(receipt.model_dump(mode="json"), sort_keys=True) + "\n"
    with events_path.open("a", encoding="utf-8") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())

    return receipt


def load_lifecycle_events(
    root: Path | str,
    run_id: str,
) -> tuple[NodeLifecycleReceipt, ...]:
    """Load all lifecycle events for a run, in append order.

    Returns an empty tuple if no lifecycle events exist (legacy run).
    """
    run_dir = _run_dir(root, run_id)
    events_path = run_dir / LIFECYCLE_EVENTS_FILE
    if not events_path.is_file():
        return ()

    events: list[NodeLifecycleReceipt] = []
    for line in events_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            receipt = NodeLifecycleReceipt.model_validate_json(line)
        except Exception:
            continue
        events.append(receipt)
    return tuple(events)


def get_current_node_state(
    root: Path | str,
    run_id: str,
    node_id: str,
) -> NodeState | None:
    """Get the current lifecycle state for one node.

    Returns the ``to_state`` of the most recent lifecycle event for that node,
    or ``None`` if no lifecycle events exist for it (legacy run).
    """
    events = load_lifecycle_events(root, run_id)
    node_events = [e for e in events if e.node_id == node_id]
    if not node_events:
        return None
    return node_events[-1].to_state


__all__ = [
    "LEGACY_OUTCOME_MAP",
    "LIFECYCLE_EVENTS_FILE",
    "NodeLifecycleReceipt",
    "NodeState",
    "TERMINAL_STATES",
    "WorkflowTerminalState",
    "get_current_node_state",
    "is_valid_transition",
    "legacy_outcome_to_state",
    "load_lifecycle_events",
    "record_lifecycle_event",
]
