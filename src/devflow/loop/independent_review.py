"""Independent reviewer selection (M4-S4, blueprint §9.2).

Selects a reviewer whose model family differs from the builder's model family,
ensuring independent judgment (blueprint §7.5 adversarial verification).

This is a *workflow-level* reviewer — distinct from the integration-layer
``IntegrationVerificationReceipt`` non-overlap rule in ``run_integration.py``.
Both enforce independence; this one operates at workflow scope.

All names are functional — model *family* is used for non-overlap checks,
never model names in primary UI.
"""

from __future__ import annotations

import json
import os

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from devflow.loop.pipeline_run import pipeline_runs_dir

_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"

REVIEW_EVENTS_FILE = "review-events.jsonl"


class ReviewResult(BaseModel):
    """Immutable result of one independent review."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    review_id: str = Field(pattern=_ID_PATTERN)
    run_id: str = Field(pattern=_ID_PATTERN)
    reviewer_family: str = Field(min_length=1)
    builder_family: str = Field(min_length=1)
    verdict: Literal["pass", "fail", "revise"]
    findings: tuple[str, ...] = ()
    families_independent: bool = True
    reviewed_at: str = Field(min_length=1)
    schema_version: Literal[1] = 1


def select_independent_reviewer(
    builder_families: tuple[str, ...],
    available_reviewers: tuple[str, ...],
) -> str | None:
    """Select a reviewer whose family differs from all builder families.

    Parameters
    ----------
    builder_families
        Model families used by builders in this run.
    available_reviewers
        Candidate reviewer families (functional names, not model names).

    Returns the first non-overlapping reviewer family, or ``None`` if no
    independent reviewer is available.
    """
    builder_set = set(builder_families)
    for reviewer in available_reviewers:
        if reviewer not in builder_set:
            return reviewer
    return None


def check_independence(
    builder_families: tuple[str, ...],
    reviewer_family: str,
) -> bool:
    """True if the reviewer family differs from all builder families."""
    return reviewer_family not in set(builder_families)


def record_review(
    root: Path | str,
    run_id: str,
    result: ReviewResult,
) -> ReviewResult:
    """Persist a review result to the run directory.

    Appends to ``review-events.jsonl``. Never touches the workflow ledger
    or decision receipts.
    """
    run_dir = pipeline_runs_dir(root) / run_id
    if not run_dir.is_dir():
        raise FileNotFoundError(f"Pipeline run not found: {run_id}")

    # Recompute independence — never trust caller-asserted bool
    expected = check_independence(
        (result.builder_family,), result.reviewer_family
    )
    if result.families_independent != expected:
        raise ValueError(
            f"review {result.review_id!r} claims families_independent="
            f"{result.families_independent} but check_independence "
            f"returned {expected}"
        )

    events_path = run_dir / REVIEW_EVENTS_FILE

    # Check for duplicate review_id
    if events_path.exists():
        for line in events_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                existing = ReviewResult.model_validate_json(line)
            except Exception:
                continue
            if existing.review_id == result.review_id:
                if existing == result:
                    return existing  # idempotent
                raise ValueError(
                    f"duplicate review id: {result.review_id}"
                )

    payload = json.dumps(result.model_dump(mode="json"), sort_keys=True) + "\n"
    with events_path.open("a", encoding="utf-8") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())

    return result


def load_reviews(
    root: Path | str,
    run_id: str,
) -> tuple[ReviewResult, ...]:
    """Load all reviews for a run in append order."""
    run_dir = pipeline_runs_dir(root) / run_id
    events_path = run_dir / REVIEW_EVENTS_FILE
    if not events_path.is_file():
        return ()

    reviews: list[ReviewResult] = []
    for line in events_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            reviews.append(ReviewResult.model_validate_json(line))
        except Exception:
            continue
    return tuple(reviews)


__all__ = [
    "REVIEW_EVENTS_FILE",
    "ReviewResult",
    "check_independence",
    "load_reviews",
    "record_review",
    "select_independent_reviewer",
]
