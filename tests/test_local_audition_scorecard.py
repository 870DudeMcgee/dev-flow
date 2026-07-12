from devflow.loop.local_audition_scorecard import role_score


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
