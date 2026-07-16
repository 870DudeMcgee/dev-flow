"""Adversarial RED tests for independent reviewer trust-binding (M4-S4).

These tests assert that ``record_review`` does NOT blindly trust a
caller-supplied ``families_independent`` flag: it must recompute independence
from the builder and reviewer families and reject false independence claims.
``check_independence`` / ``select_independent_reviewer`` are also pinned by
pure unit tests so the recomputation logic has a clear contract.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from devflow.loop.independent_review import (
    ReviewResult,
    check_independence,
    record_review,
    select_independent_reviewer,
)
from devflow.loop.pipeline_run import create_pipeline_run
from devflow.loop.workflow_ledger import initialize_workflow_run


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _review(
    run_id: str,
    review_id: str = "rev-1",
    reviewer_family: str = "glm",
    builder_family: str = "qwen",
    verdict: str = "pass",
    families_independent: bool = True,
) -> ReviewResult:
    return ReviewResult(
        review_id=review_id,
        run_id=run_id,
        reviewer_family=reviewer_family,
        builder_family=builder_family,
        verdict=verdict,  # type: ignore[arg-type]
        findings=(),
        families_independent=families_independent,
        reviewed_at="2026-07-15T20:00:00Z",
    )


# ---------------------------------------------------------------------------
# Pure unit tests for the recomputation helpers
# ---------------------------------------------------------------------------

def test_check_independence_basic() -> None:
    """check_independence: same family → False; different → True."""
    assert check_independence(("qwen",), "qwen") is False
    assert check_independence(("qwen",), "glm") is True


def test_select_independent_reviewer_basic() -> None:
    """select_independent_reviewer: first non-overlapping, else None."""
    assert select_independent_reviewer(("qwen",), ("glm", "qwen")) == "glm"
    assert select_independent_reviewer(("qwen",), ("qwen",)) is None


# ---------------------------------------------------------------------------
# Adversarial trust-binding tests for record_review
# ---------------------------------------------------------------------------

def test_review_rejects_false_independence_claim(tmp_path: Path) -> None:
    """record_review must reject a false families_independent claim.

    When the reviewer family equals a builder family, the two are NOT
    independent. A caller must not be able to assert ``families_independent=True``
    to launder a non-independent review into the record. ``record_review`` must
    recompute and raise ValueError.
    """
    run_id = create_pipeline_run(tmp_path, {"repo": "test/repo"})
    initialize_workflow_run(tmp_path, run_id)

    # Reviewer family equals builder family → genuinely NOT independent.
    result = _review(
        run_id=run_id,
        review_id="rev-false",
        reviewer_family="qwen",
        builder_family="qwen",
        families_independent=True,  # false claim
    )

    with pytest.raises(ValueError):
        record_review(tmp_path, run_id, result)


def test_review_accepts_genuine_independence(tmp_path: Path) -> None:
    """record_review accepts and persists a genuinely independent review."""
    run_id = create_pipeline_run(tmp_path, {"repo": "test/repo"})
    initialize_workflow_run(tmp_path, run_id)

    # Reviewer family differs from builder family → genuinely independent.
    result = _review(
        run_id=run_id,
        review_id="rev-ok",
        reviewer_family="glm",
        builder_family="qwen",
        families_independent=True,  # true claim
    )

    returned = record_review(tmp_path, run_id, result)
    assert returned == result

    # Persisted: loadable from the run directory.
    from devflow.loop.independent_review import load_reviews

    reviews = load_reviews(tmp_path, run_id)
    assert len(reviews) == 1
    assert reviews[0].review_id == "rev-ok"
