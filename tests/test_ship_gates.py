"""Tests for distinct merge/full-verification/ship gates (M4-S6)."""

from __future__ import annotations

from pathlib import Path

import pytest

from devflow.control_plane.gates import (
    GATE_EVENTS_FILE,
    GateConfig,
    GateDecision,
    GateStatus,
    GateType,
    can_merge,
    can_ship,
    gate_sequence_complete,
    gate_status,
    load_gate_decisions,
    record_gate_decision,
)
from devflow.loop.pipeline_run import create_pipeline_run


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _decision(
    gate_type: GateType = GateType.full_verification,
    run_id: str = "run-1",
    ticket_id: str = "t-1",
    status: GateStatus = GateStatus.approved,
    actor: str = "operator-alice",
    reason: str = "looks good",
) -> GateDecision:
    return GateDecision(
        gate_type=gate_type,
        run_id=run_id,
        ticket_id=ticket_id,
        status=status,
        actor=actor,
        decided_at="2026-01-01T00:00:00Z",
        reason=reason,
    )


# ---------------------------------------------------------------------------
# GateConfig tests
# ---------------------------------------------------------------------------

def test_ship_disabled_by_default() -> None:
    """ship_enabled=False in default config."""
    config = GateConfig()
    assert config.ship_enabled is False
    assert config.merge_enabled is True
    assert config.full_verification_enabled is True


def test_gate_config_frozen() -> None:
    """GateConfig is immutable."""
    config = GateConfig()
    with pytest.raises(Exception):
        config.ship_enabled = True  # type: ignore[misc]


def test_gate_config_ship_can_be_enabled() -> None:
    """Ship can be explicitly enabled (by a human configuring it)."""
    config = GateConfig(ship_enabled=True)
    assert config.ship_enabled is True


# ---------------------------------------------------------------------------
# GateDecision tests
# ---------------------------------------------------------------------------

def test_gate_decision_frozen() -> None:
    """GateDecision is immutable."""
    d = _decision()
    with pytest.raises(Exception):
        d.status = GateStatus.rejected  # type: ignore[misc]


def test_gate_decision_human_actor() -> None:
    """Actor is required and cannot be 'system'."""
    with pytest.raises(Exception, match="human operator"):
        GateDecision(
            gate_type=GateType.merge,
            run_id="run-1", ticket_id="t-1",
            status=GateStatus.approved,
            actor="system",
            decided_at="2026-01-01T00:00:00Z",
        )


def test_gate_decision_persisted(tmp_path: Path) -> None:
    """Decision saved to run dir."""
    run_id = create_pipeline_run(tmp_path, {"repo": "test"})
    decision = _decision(run_id=run_id)

    record_gate_decision(tmp_path, run_id, decision)

    run_dir = tmp_path / ".devflow" / "pipeline-runs" / run_id
    assert (run_dir / GATE_EVENTS_FILE).is_file()

    loaded = load_gate_decisions(tmp_path, run_id)
    assert len(loaded) == 1
    assert loaded[0].gate_type == GateType.full_verification


def test_gate_decision_idempotent(tmp_path: Path) -> None:
    """Same decision replayed → idempotent."""
    run_id = create_pipeline_run(tmp_path, {"repo": "test"})
    decision = _decision(run_id=run_id)

    record_gate_decision(tmp_path, run_id, decision)
    record_gate_decision(tmp_path, run_id, decision)

    assert len(load_gate_decisions(tmp_path, run_id)) == 1


def test_gate_decision_conflicting_rejected(tmp_path: Path) -> None:
    """Different decision for same gate → ValueError."""
    run_id = create_pipeline_run(tmp_path, {"repo": "test"})
    record_gate_decision(tmp_path, run_id, _decision(run_id=run_id, status=GateStatus.approved))

    with pytest.raises(ValueError, match="conflicting"):
        record_gate_decision(
            tmp_path, run_id,
            _decision(run_id=run_id, status=GateStatus.rejected, actor="operator-bob"),
        )


# ---------------------------------------------------------------------------
# gate_status tests
# ---------------------------------------------------------------------------

def test_gate_status_pending(tmp_path: Path) -> None:
    """Gate with no decision → None."""
    assert gate_status((), GateType.merge) is None


def test_gate_status_approved() -> None:
    """Approved decision → approved."""
    decisions = (_decision(gate_type=GateType.full_verification, status=GateStatus.approved),)
    assert gate_status(decisions, GateType.full_verification) == GateStatus.approved


def test_gate_status_latest_wins() -> None:
    """Latest decision for a gate wins."""
    decisions = (
        _decision(gate_type=GateType.merge, status=GateStatus.pending),
        _decision(gate_type=GateType.merge, status=GateStatus.approved, actor="op-2"),
    )
    assert gate_status(decisions, GateType.merge) == GateStatus.approved


# ---------------------------------------------------------------------------
# can_merge tests
# ---------------------------------------------------------------------------

def test_merge_requires_full_verification() -> None:
    """can_merge False without full_verify approved."""
    config = GateConfig()
    decisions = ()

    assert can_merge(config, decisions) is False


def test_merge_requires_explicit_merge_approval() -> None:
    """can_merge requires an explicit approved merge gate, not just full_verification."""
    config = GateConfig()
    decisions_fv_only = (
        _decision(gate_type=GateType.full_verification, status=GateStatus.approved),
    )
    # Full verification alone is NOT sufficient — merge needs its own approval
    assert can_merge(config, decisions_fv_only) is False

    # With explicit merge approval, merge is allowed
    decisions_with_merge = decisions_fv_only + (
        _decision(gate_type=GateType.merge, status=GateStatus.approved, actor="op-2"),
    )
    assert can_merge(config, decisions_with_merge) is True


def test_merge_blocked_when_disabled() -> None:
    """can_merge False when merge_enabled=False."""
    config = GateConfig(merge_enabled=False)
    decisions = (_decision(gate_type=GateType.full_verification, status=GateStatus.approved),)

    assert can_merge(config, decisions) is False


def test_merge_blocked_when_rejected() -> None:
    """can_merge False when merge was rejected."""
    config = GateConfig()
    decisions = (
        _decision(gate_type=GateType.full_verification, status=GateStatus.approved),
        _decision(gate_type=GateType.merge, status=GateStatus.rejected),
    )

    assert can_merge(config, decisions) is False


# ---------------------------------------------------------------------------
# can_ship tests
# ---------------------------------------------------------------------------

def test_ship_requires_merge() -> None:
    """can_ship False without merge approved."""
    config = GateConfig(ship_enabled=True)
    decisions = ()

    assert can_ship(config, decisions) is False


def test_ship_requires_enabled() -> None:
    """can_ship False when ship_enabled=False (default)."""
    config = GateConfig()  # ship_enabled=False
    decisions = (
        _decision(gate_type=GateType.full_verification, status=GateStatus.approved),
        _decision(gate_type=GateType.merge, status=GateStatus.approved),
    )

    assert can_ship(config, decisions) is False


def test_ship_requires_explicit_ship_approval() -> None:
    """can_ship requires an explicit approved ship gate, not just merge approved."""
    config = GateConfig(ship_enabled=True)
    decisions_no_ship = (
        _decision(gate_type=GateType.full_verification, status=GateStatus.approved),
        _decision(gate_type=GateType.merge, status=GateStatus.approved, actor="op-2"),
    )
    # Merge approved alone is NOT sufficient — ship needs its own approval
    assert can_ship(config, decisions_no_ship) is False

    # With explicit ship approval, ship is allowed
    decisions_with_ship = decisions_no_ship + (
        _decision(gate_type=GateType.ship, status=GateStatus.approved, actor="op-3"),
    )
    assert can_ship(config, decisions_with_ship) is True


def test_ship_blocked_when_rejected() -> None:
    """can_ship False when ship was rejected."""
    config = GateConfig(ship_enabled=True)
    decisions = (
        _decision(gate_type=GateType.full_verification, status=GateStatus.approved),
        _decision(gate_type=GateType.merge, status=GateStatus.approved),
        _decision(gate_type=GateType.ship, status=GateStatus.rejected),
    )

    assert can_ship(config, decisions) is False


# ---------------------------------------------------------------------------
# Gate ordering / completeness tests
# ---------------------------------------------------------------------------

def test_full_verification_independent() -> None:
    """Full verify gate is separate from merge gate."""
    decisions = (_decision(gate_type=GateType.full_verification, status=GateStatus.approved),)

    assert gate_status(decisions, GateType.full_verification) == GateStatus.approved
    assert gate_status(decisions, GateType.merge) is None  # not yet decided


def test_gate_sequence_complete() -> None:
    """All three gates decided → complete."""
    decisions = (
        _decision(gate_type=GateType.full_verification, status=GateStatus.approved),
        _decision(gate_type=GateType.merge, status=GateStatus.approved, actor="op-2"),
        _decision(gate_type=GateType.ship, status=GateStatus.skipped, actor="op-3"),
    )

    assert gate_sequence_complete(decisions) is True


def test_gate_sequence_incomplete() -> None:
    """Missing ship decision → incomplete."""
    decisions = (
        _decision(gate_type=GateType.full_verification, status=GateStatus.approved),
        _decision(gate_type=GateType.merge, status=GateStatus.approved, actor="op-2"),
    )

    assert gate_sequence_complete(decisions) is False
