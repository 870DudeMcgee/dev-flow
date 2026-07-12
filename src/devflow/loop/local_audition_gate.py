"""Deterministic qualification gate for local-model auditions."""
from __future__ import annotations


def audition_gate(
    score: int,
    reliability_safe: bool,
    independent_review: bool,
) -> dict:
    """Qualify only valid high scores backed by safe independent review."""
    reasons: list[str] = []
    valid_score = type(score) is int and 0 <= score <= 100
    if not valid_score:
        reasons.append("score_out_of_range")
    elif score < 80:
        reasons.append("score_below_80")
    if reliability_safe is not True:
        reasons.append("reliability_safe_false")
    if independent_review is not True:
        reasons.append("independent_review_false")
    return {
        "decision": "hold" if reasons else "qualify",
        "reasons": reasons,
    }
