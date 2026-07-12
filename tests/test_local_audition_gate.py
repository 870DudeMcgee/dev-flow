import pytest

from devflow.loop.local_audition_gate import audition_gate


@pytest.mark.parametrize("score", [80, 100])
def test_audition_gate_qualifies_at_valid_boundaries(score: int) -> None:
    assert audition_gate(score, True, True) == {
        "decision": "qualify",
        "reasons": [],
    }


@pytest.mark.parametrize("score", [-1, 101, True, False, 80.0, "80"])
def test_audition_gate_rejects_invalid_scores(score) -> None:
    assert audition_gate(score, True, True) == {
        "decision": "hold",
        "reasons": ["score_out_of_range"],
    }


def test_audition_gate_reports_below_threshold() -> None:
    assert audition_gate(79, True, True) == {
        "decision": "hold",
        "reasons": ["score_below_80"],
    }


def test_audition_gate_reports_all_failed_conditions_in_order() -> None:
    assert audition_gate(79, False, False) == {
        "decision": "hold",
        "reasons": [
            "score_below_80",
            "reliability_safe_false",
            "independent_review_false",
        ],
    }


def test_audition_gate_requires_literal_true_booleans() -> None:
    assert audition_gate(90, 1, "yes") == {
        "decision": "hold",
        "reasons": ["reliability_safe_false", "independent_review_false"],
    }
