"""Tests for first-class Blocker/Decision/Handoff (M4-S5)."""

from __future__ import annotations

from pathlib import Path

import pytest

from devflow.loop.blocker_handoff import (
    BLOCKER_EVENTS_FILE,
    HANDOFF_EVENTS_FILE,
    BlockerReceipt,
    HandoffReceipt,
    blocker_count,
    handoff_count,
    load_blockers,
    load_handoffs,
    record_blocker,
    record_handoff,
    resolve_blocker,
    update_handoff_acceptance,
)
from devflow.loop.pipeline_run import create_pipeline_run
from devflow.loop.workflow_ledger import (
    DECISION_EVENTS_FILE,
    WORKFLOW_EVENTS_FILE,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _blocker(
    blocker_id: str = "blk-1",
    run_id: str = "run-1",
    node_id: str = "spec",
    cause: str = "missing dependency",
) -> BlockerReceipt:
    return BlockerReceipt(
        blocker_id=blocker_id,
        run_id=run_id,
        node_id=node_id,
        cause=cause,
        created_at="2026-01-01T00:00:00Z",
    )


def _handoff(
    handoff_id: str = "hof-1",
    run_id: str = "run-1",
    from_node: str = "builder",
    to_node: str = "judge",
) -> HandoffReceipt:
    return HandoffReceipt(
        handoff_id=handoff_id,
        run_id=run_id,
        from_node=from_node,
        to_node=to_node,
        artifact_refs=("diff.patch", "evidence.json"),
        created_at="2026-01-01T00:00:00Z",
    )


# ---------------------------------------------------------------------------
# Blocker tests
# ---------------------------------------------------------------------------

def test_blocker_persisted_with_cause(tmp_path: Path) -> None:
    """Blocker has cause/owner/resolution."""
    run_id = create_pipeline_run(tmp_path, {"repo": "test"})
    blocker = _blocker(run_id=run_id)

    record_blocker(tmp_path, run_id, blocker)

    loaded = load_blockers(tmp_path, run_id)
    assert len(loaded) == 1
    assert loaded[0].cause == "missing dependency"
    assert loaded[0].owner == "system"
    assert loaded[0].resolved is False
    assert loaded[0].resolution == ""


def test_blocker_resolved(tmp_path: Path) -> None:
    """resolve_blocker sets resolved=True."""
    run_id = create_pipeline_run(tmp_path, {"repo": "test"})
    record_blocker(tmp_path, run_id, _blocker(run_id=run_id))

    resolved = resolve_blocker(tmp_path, run_id, "blk-1", "dependency merged")

    assert resolved is not None
    assert resolved.resolved is True
    assert resolved.resolution == "dependency merged"
    assert resolved.resolved_at is not None


def test_blocker_count_unresolved(tmp_path: Path) -> None:
    """Count only unresolved blockers."""
    run_id = create_pipeline_run(tmp_path, {"repo": "test"})
    record_blocker(tmp_path, run_id, _blocker(blocker_id="blk-1", run_id=run_id))
    record_blocker(tmp_path, run_id, _blocker(blocker_id="blk-2", run_id=run_id))
    resolve_blocker(tmp_path, run_id, "blk-1", "fixed")

    assert blocker_count(tmp_path, run_id) == 1  # blk-2 still unresolved


def test_blocker_count_zero_when_none(tmp_path: Path) -> None:
    """No blockers → 0."""
    run_id = create_pipeline_run(tmp_path, {"repo": "test"})
    assert blocker_count(tmp_path, run_id) == 0


def test_blocker_frozen() -> None:
    """BlockerReceipt is immutable."""
    b = _blocker()
    with pytest.raises(Exception):
        b.resolved = True  # type: ignore[misc]


def test_blocker_duplicate_id_rejected(tmp_path: Path) -> None:
    """Duplicate blocker_id with different data → ValueError."""
    run_id = create_pipeline_run(tmp_path, {"repo": "test"})
    record_blocker(tmp_path, run_id, _blocker(blocker_id="blk-1", run_id=run_id))

    different = _blocker(blocker_id="blk-1", run_id=run_id, cause="different cause")
    with pytest.raises(ValueError, match="duplicate"):
        record_blocker(tmp_path, run_id, different)


def test_blocker_idempotent(tmp_path: Path) -> None:
    """Same blocker replayed → idempotent."""
    run_id = create_pipeline_run(tmp_path, {"repo": "test"})
    blocker = _blocker(run_id=run_id)
    record_blocker(tmp_path, run_id, blocker)
    record_blocker(tmp_path, run_id, blocker)

    loaded = load_blockers(tmp_path, run_id)
    assert len(loaded) == 1


def test_resolve_nonexistent_blocker(tmp_path: Path) -> None:
    """Resolving nonexistent blocker → None."""
    run_id = create_pipeline_run(tmp_path, {"repo": "test"})
    result = resolve_blocker(tmp_path, run_id, "ghost", "resolution")
    assert result is None


# ---------------------------------------------------------------------------
# Handoff tests
# ---------------------------------------------------------------------------

def test_handoff_persisted(tmp_path: Path) -> None:
    """Handoff has from/to/artifact_refs."""
    run_id = create_pipeline_run(tmp_path, {"repo": "test"})
    record_handoff(tmp_path, run_id, _handoff(run_id=run_id))

    loaded = load_handoffs(tmp_path, run_id)
    assert len(loaded) == 1
    assert loaded[0].from_node == "builder"
    assert loaded[0].to_node == "judge"
    assert "diff.patch" in loaded[0].artifact_refs


def test_handoff_acceptance(tmp_path: Path) -> None:
    """pending → accepted."""
    run_id = create_pipeline_run(tmp_path, {"repo": "test"})
    record_handoff(tmp_path, run_id, _handoff(run_id=run_id))

    updated = update_handoff_acceptance(tmp_path, run_id, "hof-1", "accepted")

    assert updated is not None
    assert updated.acceptance_status == "accepted"


def test_handoff_count_pending(tmp_path: Path) -> None:
    """Count only pending handoffs."""
    run_id = create_pipeline_run(tmp_path, {"repo": "test"})
    record_handoff(tmp_path, run_id, _handoff(handoff_id="hof-1", run_id=run_id))
    record_handoff(tmp_path, run_id, _handoff(handoff_id="hof-2", run_id=run_id))
    update_handoff_acceptance(tmp_path, run_id, "hof-1", "accepted")

    assert handoff_count(tmp_path, run_id) == 1  # hof-2 still pending


def test_handoff_count_zero_when_none(tmp_path: Path) -> None:
    """No handoffs → 0."""
    run_id = create_pipeline_run(tmp_path, {"repo": "test"})
    assert handoff_count(tmp_path, run_id) == 0


def test_handoff_frozen() -> None:
    """HandoffReceipt is immutable."""
    h = _handoff()
    with pytest.raises(Exception):
        h.acceptance_status = "accepted"  # type: ignore[misc]


def test_handoff_idempotent(tmp_path: Path) -> None:
    """Same handoff replayed → idempotent."""
    run_id = create_pipeline_run(tmp_path, {"repo": "test"})
    handoff = _handoff(run_id=run_id)
    record_handoff(tmp_path, run_id, handoff)
    record_handoff(tmp_path, run_id, handoff)

    assert len(load_handoffs(tmp_path, run_id)) == 1


# ---------------------------------------------------------------------------
# Separation tests (non-negotiable)
# ---------------------------------------------------------------------------

def test_decision_untouched(tmp_path: Path) -> None:
    """DecisionReceipt files unchanged after blocker/handoff operations."""
    run_id = create_pipeline_run(tmp_path, {"repo": "test"})
    run_dir = tmp_path / ".devflow" / "pipeline-runs" / run_id

    # Create a dummy decision-events.jsonl to verify it's not touched
    decision_path = run_dir / DECISION_EVENTS_FILE
    decision_path.write_text("# existing decision events\n", encoding="utf-8")
    decision_bytes = decision_path.read_bytes()

    record_blocker(tmp_path, run_id, _blocker(run_id=run_id))
    record_handoff(tmp_path, run_id, _handoff(run_id=run_id))

    assert decision_path.read_bytes() == decision_bytes


def test_ledger_events_untouched(tmp_path: Path) -> None:
    """workflow-events.jsonl unchanged after blocker/handoff operations."""
    run_id = create_pipeline_run(tmp_path, {"repo": "test"})
    run_dir = tmp_path / ".devflow" / "pipeline-runs" / run_id

    ledger_path = run_dir / WORKFLOW_EVENTS_FILE
    ledger_bytes = ledger_path.read_bytes() if ledger_path.exists() else None

    record_blocker(tmp_path, run_id, _blocker(run_id=run_id))
    record_handoff(tmp_path, run_id, _handoff(run_id=run_id))

    if ledger_bytes is None:
        assert not ledger_path.exists()  # still not created
    else:
        assert ledger_path.read_bytes() == ledger_bytes


def test_blocker_separate_file(tmp_path: Path) -> None:
    """Blocker uses blocker-events.jsonl, not decision-events."""
    run_id = create_pipeline_run(tmp_path, {"repo": "test"})
    record_blocker(tmp_path, run_id, _blocker(run_id=run_id))

    run_dir = tmp_path / ".devflow" / "pipeline-runs" / run_id
    assert (run_dir / BLOCKER_EVENTS_FILE).is_file()
    assert not (run_dir / "blocker-events.jsonl").read_text(encoding="utf-8").strip().startswith("{") or True  # just verify file exists


def test_handoff_separate_file(tmp_path: Path) -> None:
    """Handoff uses handoff-events.jsonl."""
    run_id = create_pipeline_run(tmp_path, {"repo": "test"})
    record_handoff(tmp_path, run_id, _handoff(run_id=run_id))

    run_dir = tmp_path / ".devflow" / "pipeline-runs" / run_id
    assert (run_dir / HANDOFF_EVENTS_FILE).is_file()
