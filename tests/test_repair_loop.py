"""Tests for independent reviewer + bounded repair loop (M4-S4)."""

from __future__ import annotations

from pathlib import Path

import pytest

from devflow.loop.independent_review import (
    REVIEW_EVENTS_FILE,
    ReviewResult,
    check_independence,
    load_reviews,
    record_review,
    select_independent_reviewer,
)
from devflow.loop.pipeline_run import create_pipeline_run
from devflow.loop.repair_loop import (
    REPAIR_EVENTS_FILE,
    RepairRound,
    RepairState,
    compute_exhaustion,
    load_repair_state,
    record_repair_round,
    should_continue_repair,
)


# ---------------------------------------------------------------------------
# Independent reviewer tests
# ---------------------------------------------------------------------------

def test_select_independent_reviewer() -> None:
    """Different family selected."""
    result = select_independent_reviewer(
        builder_families=("family-a",),
        available_reviewers=("family-a", "family-b"),
    )
    assert result == "family-b"


def test_select_first_available_independent() -> None:
    """First non-overlapping reviewer wins."""
    result = select_independent_reviewer(
        builder_families=("family-a",),
        available_reviewers=("family-b", "family-c"),
    )
    assert result == "family-b"


def test_same_family_rejected() -> None:
    """Reviewer = builder family → None."""
    result = select_independent_reviewer(
        builder_families=("family-a",),
        available_reviewers=("family-a",),
    )
    assert result is None


def test_check_independence_true() -> None:
    assert check_independence(("family-a",), "family-b") is True


def test_check_independence_false() -> None:
    assert check_independence(("family-a",), "family-a") is False


def test_review_result_frozen() -> None:
    """ReviewResult is immutable."""
    r = ReviewResult(
        review_id="r1", run_id="run-1",
        reviewer_family="family-b", builder_family="family-a",
        verdict="pass", reviewed_at="2026-01-01T00:00:00Z",
    )
    with pytest.raises(Exception):
        r.verdict = "fail"  # type: ignore[misc]


def test_record_review_persists(tmp_path: Path) -> None:
    """Review saved to run dir."""
    run_id = create_pipeline_run(tmp_path, {"repo": "test"})
    review = ReviewResult(
        review_id="r1", run_id=run_id,
        reviewer_family="family-b", builder_family="family-a",
        verdict="pass", reviewed_at="2026-01-01T00:00:00Z",
    )

    record_review(tmp_path, run_id, review)

    run_dir = tmp_path / ".devflow" / "pipeline-runs" / run_id
    events_path = run_dir / REVIEW_EVENTS_FILE
    assert events_path.is_file()

    loaded = load_reviews(tmp_path, run_id)
    assert len(loaded) == 1
    assert loaded[0].review_id == "r1"


def test_record_review_idempotent(tmp_path: Path) -> None:
    """Same review replayed → idempotent."""
    run_id = create_pipeline_run(tmp_path, {"repo": "test"})
    review = ReviewResult(
        review_id="r1", run_id=run_id,
        reviewer_family="family-b", builder_family="family-a",
        verdict="pass", reviewed_at="2026-01-01T00:00:00Z",
    )

    record_review(tmp_path, run_id, review)
    record_review(tmp_path, run_id, review)

    loaded = load_reviews(tmp_path, run_id)
    assert len(loaded) == 1


def test_record_review_duplicate_id_rejected(tmp_path: Path) -> None:
    """Different review with same ID → ValueError."""
    run_id = create_pipeline_run(tmp_path, {"repo": "test"})
    r1 = ReviewResult(
        review_id="r1", run_id=run_id,
        reviewer_family="family-b", builder_family="family-a",
        verdict="pass", reviewed_at="2026-01-01T00:00:00Z",
    )
    r2 = ReviewResult(
        review_id="r1", run_id=run_id,
        reviewer_family="family-c", builder_family="family-a",
        verdict="fail", reviewed_at="2026-01-02T00:00:00Z",
    )

    record_review(tmp_path, run_id, r1)
    with pytest.raises(ValueError, match="duplicate review id"):
        record_review(tmp_path, run_id, r2)


def test_load_reviews_empty(tmp_path: Path) -> None:
    """No reviews → empty tuple."""
    run_id = create_pipeline_run(tmp_path, {"repo": "test"})
    assert load_reviews(tmp_path, run_id) == ()


# ---------------------------------------------------------------------------
# Repair loop tests
# ---------------------------------------------------------------------------

def _round(n: int, progress: bool = True, triggered_by: str = "test_failure") -> RepairRound:
    return RepairRound(
        round_number=n,
        triggered_by=triggered_by,
        progress_detected=progress,
        completed=False,
        timestamp=f"2026-01-0{n}T00:00:00Z",
    )


def test_no_progress_stops() -> None:
    """N rounds with no progress → stop."""
    state = RepairState(
        run_id="run-1",
        rounds=(
            _round(1, progress=False),
            _round(2, progress=False),
        ),
        max_rounds=4,
        stop_if_no_progress=2,
    )

    assert should_continue_repair(state) is False


def test_max_rounds_stops() -> None:
    """max_rounds reached → exhausted."""
    state = RepairState(
        run_id="run-1",
        rounds=(_round(i) for i in range(1, 5)),  # type: ignore[arg-type]
        max_rounds=4,
        stop_if_no_progress=2,
    )
    # Can't use generator; build tuple
    state = RepairState(
        run_id="run-1",
        rounds=(_round(1), _round(2), _round(3), _round(4)),
        max_rounds=4,
        stop_if_no_progress=2,
    )

    assert should_continue_repair(state) is False


def test_progress_allows_continue() -> None:
    """Progress detected → continue."""
    state = RepairState(
        run_id="run-1",
        rounds=(_round(1, progress=True),),
        max_rounds=4,
        stop_if_no_progress=2,
    )

    assert should_continue_repair(state) is True


def test_repair_continues_after_one_no_progress() -> None:
    """One no-progress round doesn't stop if threshold is 2."""
    state = RepairState(
        run_id="run-1",
        rounds=(_round(1, progress=True), _round(2, progress=False)),
        max_rounds=4,
        stop_if_no_progress=2,
    )

    assert should_continue_repair(state) is True


def test_exhausted_when_max_reached() -> None:
    """exhausted=True at max_rounds."""
    state = RepairState(
        run_id="run-1",
        rounds=(_round(1), _round(2), _round(3), _round(4)),
        max_rounds=4,
    )
    result = compute_exhaustion(state)

    assert result.exhausted is True
    assert "max_rounds" in result.exhaustion_reason


def test_exhausted_when_no_progress() -> None:
    """exhausted=True after no_progress bound."""
    state = RepairState(
        run_id="run-1",
        rounds=(_round(1, progress=False), _round(2, progress=False)),
        max_rounds=4,
        stop_if_no_progress=2,
    )
    result = compute_exhaustion(state)

    assert result.exhausted is True
    assert "no-progress" in result.exhaustion_reason


def test_not_exhausted_when_progressing() -> None:
    """exhausted=False when making progress."""
    state = RepairState(
        run_id="run-1",
        rounds=(_round(1, progress=True), _round(2, progress=True)),
        max_rounds=4,
        stop_if_no_progress=2,
    )
    result = compute_exhaustion(state)

    assert result.exhausted is False


def test_repair_round_appended(tmp_path: Path) -> None:
    """Round persisted to repair-events.jsonl."""
    run_id = create_pipeline_run(tmp_path, {"repo": "test"})
    state = RepairState(run_id=run_id)
    round_data = _round(1)

    updated = record_repair_round(tmp_path, run_id, round_data, state)

    assert len(updated.rounds) == 1
    run_dir = tmp_path / ".devflow" / "pipeline-runs" / run_id
    assert (run_dir / REPAIR_EVENTS_FILE).is_file()


def test_repair_state_frozen() -> None:
    """RepairState is immutable."""
    state = RepairState(run_id="r")
    with pytest.raises(Exception):
        state.exhausted = True  # type: ignore[misc]


def test_repair_round_frozen() -> None:
    """RepairRound is immutable."""
    r = _round(1)
    with pytest.raises(Exception):
        r.progress_detected = False  # type: ignore[misc]


def test_load_repair_state_empty(tmp_path: Path) -> None:
    """No rounds → fresh state."""
    run_id = create_pipeline_run(tmp_path, {"repo": "test"})
    state = load_repair_state(tmp_path, run_id)

    assert state.rounds == ()
    assert state.exhausted is False


def test_load_repair_state_with_rounds(tmp_path: Path) -> None:
    """Loaded state includes persisted rounds."""
    run_id = create_pipeline_run(tmp_path, {"repo": "test"})
    state = RepairState(run_id=run_id)
    record_repair_round(tmp_path, run_id, _round(1, progress=True), state)
    record_repair_round(tmp_path, run_id, _round(2, progress=False), state)

    loaded = load_repair_state(tmp_path, run_id)

    assert len(loaded.rounds) == 2
    assert loaded.rounds[0].progress_detected is True
    assert loaded.rounds[1].progress_detected is False
