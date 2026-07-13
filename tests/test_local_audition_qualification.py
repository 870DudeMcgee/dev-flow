from copy import deepcopy

import pytest

from devflow.loop.local_audition_gate import audition_gate
from devflow.loop.local_audition_qualification import qualification_record
from devflow.loop.local_audition_scorecard import role_score


def _qualification_packets(model="candidate-model", role="build_judge") -> dict:
    identity = {
        "candidate_id": model,
        "role": role,
        "artifact_fingerprint": "artifact-a",
        "runtime_fingerprint": "runtime-a",
    }
    return {
        "reliability": {
            **identity,
            "eligible": True,
            "critical_failures": [],
        },
        "repeat_evidence": {
            **identity,
            "required_repeats": 3,
            "complete": True,
            "case_ids": ["one", "two", "three"],
            "attempt_count": 9,
        },
        "independent_review": {
            **identity,
            "passed": True,
            "review_id": "review-1",
            "independent_from_candidate": True,
        },
    }


def test_qualification_record_qualifies_with_three_cases_and_gate() -> None:
    packets = _qualification_packets()
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
        **packets,
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
        "qualification_gates": {
            "scorecard": True,
            "reliability": True,
            "three_repeat_evidence": True,
            "independent_review": True,
        },
        "blocking_reasons": [],
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
        "qualification_gates": {
            "scorecard": False,
            "reliability": False,
            "three_repeat_evidence": False,
            "independent_review": False,
        },
        "blocking_reasons": [
            "reliability_not_passed",
            "three_repeat_evidence_incomplete",
            "independent_review_not_passed",
            "scorecard_inconsistent",
        ],
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
    packets = _qualification_packets("model", "role")
    before = (deepcopy(scorecard), deepcopy(gate), deepcopy(packets))

    qualification_record("model", "role", scorecard, gate, **packets)

    assert (scorecard, gate, packets) == before


def test_scorecard_gate_and_qualification_compose() -> None:
    scorecard = role_score([
        {"case_id": "one", "passed": True, "reliable": True},
        {"case_id": "two", "passed": True, "reliable": True},
        {"case_id": "three", "passed": True, "reliable": True},
    ])
    gate = audition_gate(
        scorecard["score"], reliability_safe=True, independent_review=True
    )

    record = qualification_record(
        "model", "builder", scorecard, gate, **_qualification_packets("model", "builder")
    )

    assert record["status"] == "qualified"
    assert record["evidence"] == {
        "cases": 3,
        "distinct_cases": 3,
        "score": 100,
        "gate": "qualify",
        "consistent": True,
    }


def test_legacy_qualify_inputs_remain_provisional_without_new_evidence() -> None:
    record = qualification_record(
        "model",
        "planner",
        {
            "cases": 3,
            "distinct_cases": 3,
            "case_ids_unique": True,
            "passes": 3,
            "reliable_passes": 3,
            "score": 100,
        },
        {"decision": "qualify", "reasons": []},
    )

    assert record["status"] == "provisional"
    assert record["blocking_reasons"] == [
        "reliability_not_passed",
        "three_repeat_evidence_incomplete",
        "independent_review_not_passed",
    ]


@pytest.mark.parametrize(
    ("packet_name", "replacement", "reason"),
    [
        (
            "reliability",
            {"eligible": 1, "critical_failures": []},
            "reliability_not_passed",
        ),
        (
            "repeat_evidence",
            {
                "required_repeats": 3,
                "complete": True,
                "case_ids": ["one", "two", "three"],
                "attempt_count": 8,
                "artifact_fingerprint": "artifact-a",
                "runtime_fingerprint": "runtime-a",
            },
            "three_repeat_evidence_incomplete",
        ),
        (
            "independent_review",
            {
                "passed": True,
                "review_id": "",
                "independent_from_candidate": True,
            },
            "independent_review_not_passed",
        ),
    ],
)
def test_each_new_qualification_gate_fails_closed(
    packet_name, replacement, reason
) -> None:
    packets = _qualification_packets("model", "planner")
    packets[packet_name].update(replacement)
    record = qualification_record(
        "model",
        "planner",
        {
            "cases": 3,
            "distinct_cases": 3,
            "case_ids_unique": True,
            "passes": 3,
            "reliable_passes": 3,
            "score": 100,
        },
        {"decision": "qualify", "reasons": []},
        **packets,
    )

    assert record["status"] == "provisional"
    assert record["blocking_reasons"] == [reason]


def test_evidence_for_another_candidate_cannot_qualify() -> None:
    packets = _qualification_packets("other-model", "planner")
    record = qualification_record(
        "model",
        "planner",
        {
            "cases": 3,
            "distinct_cases": 3,
            "case_ids_unique": True,
            "passes": 3,
            "reliable_passes": 3,
            "score": 100,
        },
        {"decision": "qualify", "reasons": []},
        **packets,
    )

    assert record["status"] == "provisional"
    assert record["blocking_reasons"] == [
        "reliability_not_passed",
        "three_repeat_evidence_incomplete",
        "independent_review_not_passed",
    ]


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
