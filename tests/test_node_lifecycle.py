"""Tests for the per-node lifecycle state machine (M2-S2)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from devflow.loop.node_lifecycle import (
    LIFECYCLE_EVENTS_FILE,
    NodeLifecycleReceipt,
    NodeState,
    TERMINAL_STATES,
    WorkflowTerminalState,
    get_current_node_state,
    is_valid_transition,
    legacy_outcome_to_state,
    load_lifecycle_events,
    record_lifecycle_event,
)
from devflow.loop.pipeline_run import create_pipeline_run
from devflow.loop.workflow_ledger import (
    EvidenceReference,
    NodeReceipt,
    WorkflowEvent,
    initialize_workflow_run,
    record_node_outcome,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_receipt(
    lifecycle_id: str = "lc-1",
    node_id: str = "spec",
    *,
    run_id: str,
    from_state: NodeState = NodeState.running,
    to_state: NodeState = NodeState.verified,
    evidence_ref: str | None = None,
) -> NodeLifecycleReceipt:
    return NodeLifecycleReceipt(
        lifecycle_id=lifecycle_id,
        node_id=node_id,
        run_id=run_id,
        from_state=from_state,
        to_state=to_state,
        timestamp="2026-07-15T20:00:00Z",
        evidence_ref=evidence_ref,
    )


def _record_success(root: Path, run_id: str, node_id: str, evidence_key: str, idx: int) -> None:
    evidence_file = f"{evidence_key}.md"
    run_dir = root / ".devflow" / "pipeline-runs" / run_id
    if not (run_dir / evidence_file).exists():
        (run_dir / evidence_file).write_text(f"# {evidence_key}\n", encoding="utf-8")
    record_node_outcome(
        root,
        run_id,
        receipt=NodeReceipt(
            receipt_id=f"receipt-{idx}",
            node_id=node_id,
            outcome="success",
            evidence=(EvidenceReference(key=evidence_key, reference=evidence_file),),
        ),
        event=WorkflowEvent(
            event_id=f"event-{idx}",
            node_id=node_id,
            outcome="success",
            receipt_id=f"receipt-{idx}",
        ),
    )


# ---------------------------------------------------------------------------
# Legacy replay tests (non-negotiable)
# ---------------------------------------------------------------------------

def test_legacy_success_replays_unchanged(tmp_path: Path) -> None:
    """NodeReceipt bytes identical after lifecycle module exists."""
    run_id = create_pipeline_run(tmp_path, {"repo": "test/repo"})
    initialize_workflow_run(tmp_path, run_id)

    _record_success(tmp_path, run_id, "idea", "idea-brief", 1)

    # Read the persisted NodeReceipt from disk
    run_dir = tmp_path / ".devflow" / "pipeline-runs" / run_id
    receipt_path = run_dir / "workflow-receipts" / "receipt-1.json"
    receipt_bytes = receipt_path.read_bytes()

    # Establish node was running via proper chain
    record_lifecycle_event(
        tmp_path,
        run_id,
        receipt=_make_receipt(
            lifecycle_id="lc-prep-a",
            run_id=run_id,
            node_id="idea",
            from_state=NodeState.planned,
            to_state=NodeState.ready,
        ),
    )
    record_lifecycle_event(
        tmp_path,
        run_id,
        receipt=_make_receipt(
            lifecycle_id="lc-prep-b",
            run_id=run_id,
            node_id="idea",
            from_state=NodeState.ready,
            to_state=NodeState.running,
        ),
    )

    # Now record a lifecycle event (shouldn't touch NodeReceipt)
    record_lifecycle_event(
        tmp_path,
        run_id,
        receipt=_make_receipt(
            run_id=run_id,
            node_id="idea",
            from_state=NodeState.running,
            to_state=NodeState.verified,
            evidence_ref="receipt-1",
        ),
    )

    # NodeReceipt must be byte-identical
    assert receipt_path.read_bytes() == receipt_bytes


def test_legacy_failure_replays_unchanged(tmp_path: Path) -> None:
    """Failure NodeReceipt bytes identical after lifecycle module."""
    run_id = create_pipeline_run(tmp_path, {"repo": "test/repo"})
    initialize_workflow_run(tmp_path, run_id)

    run_dir = tmp_path / ".devflow" / "pipeline-runs" / run_id
    (run_dir / "idea-brief.md").write_text("# idea\n", encoding="utf-8")
    record_node_outcome(
        tmp_path,
        run_id,
        receipt=NodeReceipt(
            receipt_id="receipt-fail",
            node_id="idea",
            outcome="failure",
            evidence=(EvidenceReference(key="idea-brief", reference="idea-brief.md"),),
        ),
        event=WorkflowEvent(
            event_id="event-fail",
            node_id="idea",
            outcome="failure",
            receipt_id="receipt-fail",
        ),
    )

    receipt_path = run_dir / "workflow-receipts" / "receipt-fail.json"
    bytes_before = receipt_path.read_bytes()

    # Establish node was running via proper chain
    record_lifecycle_event(
        tmp_path,
        run_id,
        receipt=_make_receipt(
            lifecycle_id="lc-prep-a",
            run_id=run_id,
            node_id="idea",
            from_state=NodeState.planned,
            to_state=NodeState.ready,
        ),
    )
    record_lifecycle_event(
        tmp_path,
        run_id,
        receipt=_make_receipt(
            lifecycle_id="lc-prep-b",
            run_id=run_id,
            node_id="idea",
            from_state=NodeState.ready,
            to_state=NodeState.running,
        ),
    )

    record_lifecycle_event(
        tmp_path,
        run_id,
        receipt=_make_receipt(
            run_id=run_id,
            node_id="idea",
            from_state=NodeState.running,
            to_state=NodeState.failed,
            evidence_ref="receipt-fail",
        ),
    )

    assert receipt_path.read_bytes() == bytes_before


def test_legacy_success_maps_to_verified() -> None:
    """Read-only mapping: success → verified."""
    assert legacy_outcome_to_state("success") == NodeState.verified


def test_legacy_failure_maps_to_failed() -> None:
    """Read-only mapping: failure → failed."""
    assert legacy_outcome_to_state("failure") == NodeState.failed


def test_legacy_unknown_outcome_raises() -> None:
    with pytest.raises(ValueError, match="unknown legacy outcome"):
        legacy_outcome_to_state("unknown")


def test_lifecycle_does_not_mutate_ledger(tmp_path: Path) -> None:
    """workflow-events.jsonl unchanged after lifecycle recording."""
    run_id = create_pipeline_run(tmp_path, {"repo": "test/repo"})
    initialize_workflow_run(tmp_path, run_id)

    run_dir = tmp_path / ".devflow" / "pipeline-runs" / run_id
    events_path = run_dir / "workflow-events.jsonl"

    _record_success(tmp_path, run_id, "idea", "idea-brief", 1)
    ledger_bytes_before = events_path.read_bytes()

    # Establish node was running via proper chain
    record_lifecycle_event(
        tmp_path,
        run_id,
        receipt=_make_receipt(
            lifecycle_id="lc-prep-a",
            run_id=run_id,
            node_id="idea",
            from_state=NodeState.planned,
            to_state=NodeState.ready,
        ),
    )
    record_lifecycle_event(
        tmp_path,
        run_id,
        receipt=_make_receipt(
            lifecycle_id="lc-prep-b",
            run_id=run_id,
            node_id="idea",
            from_state=NodeState.ready,
            to_state=NodeState.running,
        ),
    )

    record_lifecycle_event(
        tmp_path,
        run_id,
        receipt=_make_receipt(run_id=run_id, node_id="idea", to_state=NodeState.verified),
    )

    assert events_path.read_bytes() == ledger_bytes_before


# ---------------------------------------------------------------------------
# Lifecycle transition tests
# ---------------------------------------------------------------------------

def test_lifecycle_planned_to_ready(tmp_path: Path) -> None:
    """Legal transition: planned → ready."""
    run_id = create_pipeline_run(tmp_path, {"repo": "test/repo"})
    initialize_workflow_run(tmp_path, run_id)

    record_lifecycle_event(
        tmp_path,
        run_id,
        receipt=_make_receipt(
            lifecycle_id="lc-1",
            run_id=run_id,
            from_state=NodeState.planned,
            to_state=NodeState.ready,
        ),
    )

    events = load_lifecycle_events(tmp_path, run_id)
    assert len(events) == 1
    assert events[0].to_state == NodeState.ready


def test_lifecycle_running_to_verified(tmp_path: Path) -> None:
    """Legal transition: running → verified."""
    run_id = create_pipeline_run(tmp_path, {"repo": "test/repo"})
    initialize_workflow_run(tmp_path, run_id)

    # Establish node was running via proper chain
    record_lifecycle_event(
        tmp_path,
        run_id,
        receipt=_make_receipt(
            lifecycle_id="lc-prep-a",
            run_id=run_id,
            from_state=NodeState.planned,
            to_state=NodeState.ready,
        ),
    )
    record_lifecycle_event(
        tmp_path,
        run_id,
        receipt=_make_receipt(
            lifecycle_id="lc-prep-b",
            run_id=run_id,
            from_state=NodeState.ready,
            to_state=NodeState.running,
        ),
    )

    record_lifecycle_event(
        tmp_path,
        run_id,
        receipt=_make_receipt(
            lifecycle_id="lc-1",
            run_id=run_id,
            from_state=NodeState.running,
            to_state=NodeState.verified,
        ),
    )

    events = load_lifecycle_events(tmp_path, run_id)
    assert len(events) == 3
    assert events[-1].to_state == NodeState.verified


def test_lifecycle_running_to_retrying(tmp_path: Path) -> None:
    """Legal transition: running → retrying."""
    run_id = create_pipeline_run(tmp_path, {"repo": "test/repo"})
    initialize_workflow_run(tmp_path, run_id)

    # Establish node was running via proper chain
    record_lifecycle_event(
        tmp_path,
        run_id,
        receipt=_make_receipt(
            lifecycle_id="lc-prep-a",
            run_id=run_id,
            from_state=NodeState.planned,
            to_state=NodeState.ready,
        ),
    )
    record_lifecycle_event(
        tmp_path,
        run_id,
        receipt=_make_receipt(
            lifecycle_id="lc-prep-b",
            run_id=run_id,
            from_state=NodeState.ready,
            to_state=NodeState.running,
        ),
    )

    record_lifecycle_event(
        tmp_path,
        run_id,
        receipt=_make_receipt(
            lifecycle_id="lc-1",
            run_id=run_id,
            from_state=NodeState.running,
            to_state=NodeState.retrying,
        ),
    )

    events = load_lifecycle_events(tmp_path, run_id)
    assert events[-1].to_state == NodeState.retrying


def test_lifecycle_illegal_transition(tmp_path: Path) -> None:
    """Illegal transition: planned → verified → ValueError."""
    run_id = create_pipeline_run(tmp_path, {"repo": "test/repo"})
    initialize_workflow_run(tmp_path, run_id)

    with pytest.raises(ValueError, match="illegal lifecycle transition"):
        record_lifecycle_event(
            tmp_path,
            run_id,
            receipt=_make_receipt(
                lifecycle_id="lc-1",
                run_id=run_id,
                from_state=NodeState.planned,
                to_state=NodeState.verified,
            ),
        )


def test_lifecycle_terminal_no_outgoing(tmp_path: Path) -> None:
    """Terminal states have no outgoing transitions."""
    assert is_valid_transition(NodeState.verified, NodeState.running) is False
    assert is_valid_transition(NodeState.failed, NodeState.running) is False
    assert is_valid_transition(NodeState.cancelled, NodeState.running) is False


def test_is_valid_transition_matrix() -> None:
    """Spot-check key transitions."""
    assert is_valid_transition(NodeState.planned, NodeState.ready)
    assert is_valid_transition(NodeState.ready, NodeState.running)
    assert is_valid_transition(NodeState.running, NodeState.verified)
    assert is_valid_transition(NodeState.running, NodeState.failed)
    assert is_valid_transition(NodeState.running, NodeState.blocked)
    assert is_valid_transition(NodeState.running, NodeState.awaiting_gate)
    assert is_valid_transition(NodeState.retrying, NodeState.running)
    assert is_valid_transition(NodeState.blocked, NodeState.ready)
    assert is_valid_transition(NodeState.awaiting_gate, NodeState.running)
    # Illegal
    assert not is_valid_transition(NodeState.planned, NodeState.verified)
    assert not is_valid_transition(NodeState.ready, NodeState.verified)
    assert not is_valid_transition(NodeState.verified, NodeState.running)


# ---------------------------------------------------------------------------
# Persistence tests
# ---------------------------------------------------------------------------

def test_lifecycle_receipt_appended(tmp_path: Path) -> None:
    """Lifecycle event in jsonl, NodeReceipt untouched."""
    run_id = create_pipeline_run(tmp_path, {"repo": "test/repo"})
    initialize_workflow_run(tmp_path, run_id)

    record_lifecycle_event(
        tmp_path,
        run_id,
        receipt=_make_receipt(
            lifecycle_id="lc-1",
            run_id=run_id,
            from_state=NodeState.planned,
            to_state=NodeState.ready,
        ),
    )
    record_lifecycle_event(
        tmp_path,
        run_id,
        receipt=_make_receipt(
            lifecycle_id="lc-2",
            run_id=run_id,
            from_state=NodeState.ready,
            to_state=NodeState.running,
        ),
    )

    run_dir = tmp_path / ".devflow" / "pipeline-runs" / run_id
    lifecycle_path = run_dir / LIFECYCLE_EVENTS_FILE
    assert lifecycle_path.is_file()

    events = load_lifecycle_events(tmp_path, run_id)
    assert len(events) == 2
    assert events[0].lifecycle_id == "lc-1"
    assert events[1].lifecycle_id == "lc-2"

    # No workflow-receipts should exist (we never called record_node_outcome)
    receipts_dir = run_dir / "workflow-receipts"
    assert not receipts_dir.exists() or not any(receipts_dir.iterdir())


def test_lifecycle_duplicate_id_rejected(tmp_path: Path) -> None:
    """Duplicate lifecycle_id → ValueError."""
    run_id = create_pipeline_run(tmp_path, {"repo": "test/repo"})
    initialize_workflow_run(tmp_path, run_id)

    record_lifecycle_event(
        tmp_path,
        run_id,
        receipt=_make_receipt(
            lifecycle_id="lc-dup",
            run_id=run_id,
            from_state=NodeState.planned,
            to_state=NodeState.ready,
        ),
    )

    with pytest.raises(ValueError, match="duplicate lifecycle event id"):
        record_lifecycle_event(
            tmp_path,
            run_id,
            receipt=_make_receipt(
                lifecycle_id="lc-dup",
                run_id=run_id,
                from_state=NodeState.ready,
                to_state=NodeState.running,
            ),
        )


def test_lifecycle_receipt_frozen() -> None:
    """NodeLifecycleReceipt is immutable."""
    receipt = _make_receipt(run_id="run-x")
    with pytest.raises(Exception):
        receipt.to_state = NodeState.failed  # type: ignore[misc]


def test_lifecycle_idempotent_replay(tmp_path: Path) -> None:
    """Recording the same transition twice is idempotent."""
    run_id = create_pipeline_run(tmp_path, {"repo": "test/repo"})
    initialize_workflow_run(tmp_path, run_id)

    receipt = _make_receipt(
        lifecycle_id="lc-1",
        run_id=run_id,
        from_state=NodeState.planned,
        to_state=NodeState.ready,
    )
    record_lifecycle_event(tmp_path, run_id, receipt=receipt)
    record_lifecycle_event(tmp_path, run_id, receipt=receipt)

    events = load_lifecycle_events(tmp_path, run_id)
    assert len(events) == 1  # only one event, not two


def test_get_current_node_state(tmp_path: Path) -> None:
    """get_current_node_state returns most recent to_state."""
    run_id = create_pipeline_run(tmp_path, {"repo": "test/repo"})
    initialize_workflow_run(tmp_path, run_id)

    record_lifecycle_event(
        tmp_path,
        run_id,
        receipt=_make_receipt(
            lifecycle_id="lc-1",
            run_id=run_id,
            from_state=NodeState.planned,
            to_state=NodeState.ready,
        ),
    )
    record_lifecycle_event(
        tmp_path,
        run_id,
        receipt=_make_receipt(
            lifecycle_id="lc-2",
            run_id=run_id,
            from_state=NodeState.ready,
            to_state=NodeState.running,
        ),
    )

    state = get_current_node_state(tmp_path, run_id, "spec")
    assert state == NodeState.running


def test_get_current_node_state_none_for_legacy(tmp_path: Path) -> None:
    """Returns None when no lifecycle events exist (legacy run)."""
    run_id = create_pipeline_run(tmp_path, {"repo": "test/repo"})
    initialize_workflow_run(tmp_path, run_id)

    state = get_current_node_state(tmp_path, run_id, "idea")
    assert state is None


def test_load_lifecycle_events_empty(tmp_path: Path) -> None:
    """Empty tuple for runs with no lifecycle file."""
    run_id = create_pipeline_run(tmp_path, {"repo": "test/repo"})
    initialize_workflow_run(tmp_path, run_id)

    events = load_lifecycle_events(tmp_path, run_id)
    assert events == ()


# ---------------------------------------------------------------------------
# Workflow terminal states
# ---------------------------------------------------------------------------

def test_workflow_terminal_states() -> None:
    """All terminal state values exist."""
    states = {s.value for s in WorkflowTerminalState}
    assert states == {
        "completed", "awaiting_promotion", "needs_rework",
        "failed", "cancelled", "shipped",
    }


def test_terminal_states_set() -> None:
    """TERMINAL_STATES frozenset is correct."""
    assert NodeState.verified in TERMINAL_STATES
    assert NodeState.failed in TERMINAL_STATES
    assert NodeState.cancelled in TERMINAL_STATES
    assert NodeState.running not in TERMINAL_STATES


# ---------------------------------------------------------------------------
# Schema version
# ---------------------------------------------------------------------------

def test_lifecycle_receipt_schema_version() -> None:
    """Receipts carry schema_version=1."""
    receipt = _make_receipt(run_id="run-x")
    assert receipt.schema_version == 1


def test_lifecycle_receipt_round_trips_json() -> None:
    """Receipt serializes and deserializes cleanly."""
    receipt = _make_receipt(run_id="run-x", evidence_ref="receipt-1")
    data = json.loads(receipt.model_dump_json())
    restored = NodeLifecycleReceipt.model_validate(data)
    assert restored == receipt
    assert restored.evidence_ref == "receipt-1"


# ---------------------------------------------------------------------------
# Adversarial RED tests: trust-binding vulnerabilities (M2-S2)
# ---------------------------------------------------------------------------

def test_lifecycle_rejects_mismatched_run_id(tmp_path: Path) -> None:
    """A receipt stamped for a different run must be rejected (run_id binding).

    The path ``run_id`` is the authority for which run the event belongs to.
    A receipt whose own ``run_id`` differs from the path parameter is a
    trust-binding violation: it must not be written into this run's append-only
    lifecycle history. No events file should be created for the run.
    """
    run_id = create_pipeline_run(tmp_path, {"repo": "test/repo"})
    initialize_workflow_run(tmp_path, run_id)

    receipt = _make_receipt(
        lifecycle_id="lc-bad",
        node_id="spec",
        run_id="different-run",  # mismatched: not the path run_id
        from_state=NodeState.running,
        to_state=NodeState.verified,
    )

    with pytest.raises(ValueError, match="run_id"):
        record_lifecycle_event(tmp_path, run_id, receipt=receipt)

    # No event file should have been written for this run.
    run_dir = tmp_path / ".devflow" / "pipeline-runs" / run_id
    assert not (run_dir / LIFECYCLE_EVENTS_FILE).exists()


def test_lifecycle_rejects_discontinuous_first_event(tmp_path: Path) -> None:
    """The first lifecycle event for a node must come from a known prior state.

    A node's first event cannot be ``from_state=running``: that implies a prior
    running state that was never recorded, producing a discontinuous / missing
    prior state. The lifecycle history must be contiguous starting from
    ``planned`` (planned → ready → running ...).
    """
    run_id = create_pipeline_run(tmp_path, {"repo": "test/repo"})
    initialize_workflow_run(tmp_path, run_id)

    receipt = _make_receipt(
        lifecycle_id="lc-first",
        run_id=run_id,
        node_id="spec",
        from_state=NodeState.running,  # first event claims a prior running state
        to_state=NodeState.verified,
    )

    with pytest.raises(ValueError, match="discontinu|prior state"):
        record_lifecycle_event(tmp_path, run_id, receipt=receipt)
