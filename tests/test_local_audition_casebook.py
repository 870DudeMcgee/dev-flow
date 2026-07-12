from devflow.loop.local_audition_casebook import build_local_audition_casebook


EXPECTED_ROLES = [
    "brainstorm",
    "planner",
    "planning_judge",
    "builder",
    "build_judge",
    "verifier",
    "final_judge",
]
EXPECTED_KEYS = {
    "case_id",
    "role",
    "system_prompt",
    "user_prompt",
    "max_tokens",
    "required_output",
    "checks",
}


def test_casebook_has_one_bounded_case_per_canonical_role() -> None:
    cases = build_local_audition_casebook()

    assert [case["role"] for case in cases] == EXPECTED_ROLES
    assert len({case["case_id"] for case in cases}) == len(EXPECTED_ROLES)
    assert all(set(case) == EXPECTED_KEYS for case in cases)
    assert all(case["system_prompt"].strip() for case in cases)
    assert all(case["user_prompt"].strip() for case in cases)
    assert all(0 < case["max_tokens"] <= 16384 for case in cases)


def test_casebook_contracts_and_checks_are_structured_data() -> None:
    for case in build_local_audition_casebook():
        assert isinstance(case["required_output"], dict)
        assert case["required_output"]
        assert isinstance(case["checks"], list)
        assert case["checks"]
        for check in case["checks"]:
            assert set(check) == {"name", "expectation"}
            assert isinstance(check["name"], str) and check["name"].strip()
            assert isinstance(check["expectation"], dict) and check["expectation"]
            assert not callable(check["expectation"])


def test_casebook_returns_fresh_nested_structures() -> None:
    first = build_local_audition_casebook()
    second = build_local_audition_casebook()

    first[0]["required_output"]["required_keys"].append("invented")
    first[0]["checks"][0]["expectation"]["unknowns_are_labeled"] = False
    first.append({"case_id": "invented"})

    assert "invented" not in second[0]["required_output"]["required_keys"]
    assert second[0]["checks"][0]["expectation"]["unknowns_are_labeled"] is True
    assert len(second) == len(EXPECTED_ROLES)
