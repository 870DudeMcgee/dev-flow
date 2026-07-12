from copy import deepcopy

from devflow.loop.local_audition_gate import audition_gate
from devflow.loop.local_audition_qualification import qualification_record
from devflow.loop.local_audition_scorecard import role_score


def test_qualification_record_qualifies_with_three_cases_and_gate() -> None:
    assert qualification_record(
        "candidate-model",
        "build_judge",
        {
            "cases": 3,
            "distinct_cases": 3,
            "case_ids_unique": True,
            "passes": 3,
            "reliable_passes": 3,
            "score": 100,
        },
        {"decision": "qualify", "reasons": []},
    ) == {
        "model": "candidate-model",
        "role": "build_judge",
        "status": "qualified",
        "evidence": {
            "cases": 3,
            "distinct_cases": 3,
            "score": 100,
            "gate": "qualify",
            "consistent": True,
        },
    }


def test_qualification_record_remains_provisional_below_case_minimum() -> None:
    record = qualification_record(
        "model", "planner", {"cases": 2, "score": 100}, {"decision": "qualify"}
    )
    assert record["status"] == "provisional"


def test_qualification_record_remains_provisional_when_gate_holds() -> None:
    record = qualification_record(
        "model", "planner", {"cases": 3, "score": 90}, {"decision": "hold"}
    )
    assert record["status"] == "provisional"
    assert record["evidence"]["gate"] == "hold"


def test_qualification_record_uses_safe_defaults() -> None:
    assert qualification_record("model", "role", None, None) == {
        "model": "model",
        "role": "role",
        "status": "provisional",
        "evidence": {
            "cases": 0,
            "distinct_cases": 0,
            "score": 0,
            "gate": "hold",
            "consistent": False,
        },
    }
    record = qualification_record(
        "model", "role", {"cases": True, "score": 101}, {"decision": "unknown"}
    )
    assert record["evidence"] == {
        "cases": 0,
        "distinct_cases": 0,
        "score": 0,
        "gate": "hold",
        "consistent": False,
    }


def test_qualification_record_does_not_mutate_inputs() -> None:
    scorecard = {"cases": 3, "score": 90, "extra": []}
    gate = {"decision": "qualify", "reasons": []}
    before = (deepcopy(scorecard), deepcopy(gate))

    qualification_record("model", "role", scorecard, gate)

    assert (scorecard, gate) == before


def test_scorecard_gate_and_qualification_compose() -> None:
    scorecard = role_score([
        {"case_id": "one", "passed": True, "reliable": True},
        {"case_id": "two", "passed": True, "reliable": True},
        {"case_id": "three", "passed": True, "reliable": True},
    ])
    gate = audition_gate(
        scorecard["score"], reliability_safe=True, independent_review=True
    )

    record = qualification_record("model", "builder", scorecard, gate)

    assert record["status"] == "qualified"
    assert record["evidence"] == {
        "cases": 3,
        "distinct_cases": 3,
        "score": 100,
        "gate": "qualify",
        "consistent": True,
    }


def test_qualification_rejects_duplicate_cases_and_gate_score_mismatch() -> None:
    duplicate_scorecard = role_score([
        {"case_id": "same", "passed": True, "reliable": True},
        {"case_id": "same", "passed": True, "reliable": True},
        {"case_id": "same", "passed": True, "reliable": True},
    ])
    duplicate_record = qualification_record(
        "model", "planner", duplicate_scorecard, {"decision": "qualify", "reasons": []}
    )
    inconsistent_record = qualification_record(
        "model",
        "planner",
        {
            "cases": 3,
            "distinct_cases": 3,
            "case_ids_unique": True,
            "passes": 0,
            "reliable_passes": 0,
            "score": 0,
        },
        {"decision": "qualify", "reasons": []},
    )

    assert duplicate_record["status"] == "provisional"
    assert duplicate_record["evidence"]["consistent"] is False
    assert inconsistent_record["status"] == "provisional"
    assert inconsistent_record["evidence"]["consistent"] is False
