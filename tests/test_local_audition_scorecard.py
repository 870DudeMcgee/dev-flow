from devflow.loop.local_audition_scorecard import (
    CRITICAL_RELIABILITY_FLAGS,
    rank_role_candidates,
    role_score,
)


def _candidate_evidence(
    candidate_id,
    *,
    scores=(100.0, 100.0, 100.0),
    durations=(1.0, 1.0, 1.0),
    tokens=(10, 10, 10),
    reliability_updates=None,
    artifact_fingerprint=None,
    runtime_fingerprint=None,
    case_id="case-one",
):
    reliability = {flag: False for flag in CRITICAL_RELIABILITY_FLAGS}
    reliability.update(reliability_updates or {})
    artifact = artifact_fingerprint or f"artifact-{candidate_id}"
    runtime = runtime_fingerprint or f"runtime-{candidate_id}"
    return [
        {
            "schema_version": 1,
            "attempt": {
                "sequence": repeat,
                "candidate_id": candidate_id,
                "role": "planner",
                "case_id": case_id,
                "repeat": repeat,
            },
            "expected_model": f"model-{candidate_id}",
            "served_model": f"model-{candidate_id}",
            "artifact_fingerprint": artifact,
            "runtime_fingerprint": runtime,
            "timing": {"duration_seconds": duration},
            "usage": {"total_tokens": token_count},
            "quality_outcome": {"score": score},
            "reliability_outcome": dict(reliability),
            "failure_classification": None,
            "terminal_status": "completed",
        }
        for repeat, (score, duration, token_count) in enumerate(
            zip(scores, durations, tokens, strict=True), start=1
        )
    ]


def test_role_score_counts_only_reliable_passes() -> None:
    cases = [
        {"case_id": "one", "passed": True, "reliable": True},
        {"case_id": "two", "passed": True, "reliable": False},
        {"case_id": "three", "passed": False, "reliable": True},
        {"case_id": "four", "passed": True, "reliable": True},
    ]

    assert role_score(cases) == {
        "cases": 4,
        "distinct_cases": 4,
        "case_ids_unique": True,
        "passes": 2,
        "reliable_passes": 2,
        "score": 50,
    }


def test_role_score_ignores_non_dict_cases() -> None:
    assert role_score([None, "bad", {"case_id": "one", "passed": True, "reliable": True}]) == {
        "cases": 1,
        "distinct_cases": 1,
        "case_ids_unique": True,
        "passes": 1,
        "reliable_passes": 1,
        "score": 100,
    }


def test_role_score_requires_boolean_evidence() -> None:
    assert role_score([
        {"case_id": "one", "passed": 1, "reliable": True},
        {"case_id": "two", "passed": True, "reliable": "yes"},
        {"case_id": "three"},
    ]) == {
        "cases": 3,
        "distinct_cases": 3,
        "case_ids_unique": True,
        "passes": 0,
        "reliable_passes": 0,
        "score": 0,
    }


def test_role_score_handles_empty_or_invalid_input() -> None:
    expected = {
        "cases": 0,
        "distinct_cases": 0,
        "case_ids_unique": True,
        "passes": 0,
        "reliable_passes": 0,
        "score": 0,
    }
    assert role_score([]) == expected
    assert role_score(None) == expected


def test_role_score_exposes_duplicate_or_missing_case_ids() -> None:
    score = role_score([
        {"case_id": "same", "passed": True, "reliable": True},
        {"case_id": "same", "passed": True, "reliable": True},
        {"passed": True, "reliable": True},
    ])

    assert score["cases"] == 3
    assert score["distinct_cases"] == 1
    assert score["case_ids_unique"] is False


def test_reliability_is_a_hard_gate_before_quality_ranking() -> None:
    unsafe = _candidate_evidence(
        "unsafe",
        scores=(100.0, 100.0, 100.0),
        reliability_updates={"critical_false_accept": True},
    )
    safe = _candidate_evidence("safe", scores=(70.0, 70.0, 70.0))

    result = rank_role_candidates(
        unsafe + safe,
        role="planner",
        required_case_ids=("case-one",),
    )

    assert [item["candidate_id"] for item in result["ranked"]] == ["safe"]
    assert result["ineligible"] == [
        {
            "candidate_id": "unsafe",
            "artifact_fingerprint": "artifact-unsafe",
            "runtime_fingerprint": "runtime-unsafe",
            "reasons": ["critical_false_accept"],
        }
    ]


def test_missing_reliability_flag_and_incomplete_repeats_fail_closed() -> None:
    missing_flag = _candidate_evidence("missing-flag")
    del missing_flag[0]["reliability_outcome"]["scope_violation"]
    incomplete = _candidate_evidence("incomplete")[:2]

    result = rank_role_candidates(
        missing_flag + incomplete,
        role="planner",
        required_case_ids=("case-one",),
    )

    assert result["ranked"] == []
    assert {
        item["candidate_id"]: item["reasons"] for item in result["ineligible"]
    } == {
        "incomplete": ["incomplete_repeat_evidence"],
        "missing-flag": ["malformed_reliability_evidence"],
    }


def test_quality_then_repeat_consistency_determine_primary_order() -> None:
    high_quality = _candidate_evidence(
        "high-quality",
        scores=(91.0, 91.0, 91.0),
        durations=(9.0, 9.0, 9.0),
        tokens=(900, 900, 900),
    )
    stable = _candidate_evidence("stable", scores=(80.0, 80.0, 80.0))
    variable = _candidate_evidence("variable", scores=(70.0, 80.0, 90.0))

    result = rank_role_candidates(
        high_quality + variable + stable,
        role="planner",
        required_case_ids=("case-one",),
    )

    assert [item["candidate_id"] for item in result["ranked"]] == [
        "high-quality",
        "stable",
        "variable",
    ]
    assert result["ranked"][1]["quality"] == result["ranked"][2]["quality"]
    assert result["ranked"][1]["repeat_consistency"] == 100.0
    assert result["ranked"][2]["repeat_consistency"] == 80.0


def test_duration_then_token_use_break_remaining_ties() -> None:
    fast_expensive = _candidate_evidence(
        "fast-expensive",
        durations=(1.0, 1.0, 1.0),
        tokens=(100, 100, 100),
    )
    slow_cheap = _candidate_evidence(
        "slow-cheap",
        durations=(2.0, 2.0, 2.0),
        tokens=(1, 1, 1),
    )
    fast_cheap = _candidate_evidence(
        "fast-cheap",
        durations=(1.0, 1.0, 1.0),
        tokens=(10, 10, 10),
    )

    result = rank_role_candidates(
        slow_cheap + fast_expensive + fast_cheap,
        role="planner",
        required_case_ids=("case-one",),
    )

    assert [item["candidate_id"] for item in result["ranked"]] == [
        "fast-cheap",
        "fast-expensive",
        "slow-cheap",
    ]


def test_invalid_metrics_are_ineligible_instead_of_ranked() -> None:
    records = _candidate_evidence("invalid")
    records[1]["usage"]["total_tokens"] = None

    result = rank_role_candidates(
        records,
        role="planner",
        required_case_ids=("case-one",),
    )

    assert result["ranked"] == []
    assert result["ineligible"][0]["reasons"] == ["malformed_metric_evidence"]


def test_unreliable_failed_receipt_classification_is_a_hard_gate() -> None:
    records = _candidate_evidence("bad-failure")
    records[0]["terminal_status"] = "failed"
    records[0]["failure_classification"] = {"category": "infrastructure"}

    result = rank_role_candidates(
        records,
        role="planner",
        required_case_ids=("case-one",),
    )

    assert result["ranked"] == []
    assert result["ineligible"][0]["reasons"] == [
        "unreliable_failure_behavior"
    ]


def test_fingerprint_groups_remain_separate_and_ties_are_stable() -> None:
    first = _candidate_evidence(
        "same",
        artifact_fingerprint="artifact-a",
        runtime_fingerprint="runtime-a",
    )
    second = _candidate_evidence(
        "same",
        artifact_fingerprint="artifact-b",
        runtime_fingerprint="runtime-b",
    )

    result = rank_role_candidates(
        second + first,
        role="planner",
        required_case_ids=("case-one",),
    )

    assert [
        (item["rank"], item["artifact_fingerprint"], item["runtime_fingerprint"])
        for item in result["ranked"]
    ] == [(1, "artifact-a", "runtime-a"), (2, "artifact-b", "runtime-b")]
