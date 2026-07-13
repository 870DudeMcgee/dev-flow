from devflow.loop.local_audition_contracts import (
    FINAL_JUDGE_SCHEMA_VERSION,
    SCHEMA_VERSION,
    build_audition_contract,
    validate_audition_packet,
)


def test_contracts_are_versioned_strict_and_fresh() -> None:
    for role in (
        "planner",
        "builder",
        "planning_judge",
        "build_judge",
        "verifier",
        "final_judge",
    ):
        first = build_audition_contract(
            role, target_files=["src/x.py"], evidence_ids=["evidence-1"]
        )
        second = build_audition_contract(
            role, target_files=["src/x.py"], evidence_ids=["evidence-1"]
        )
        schema = first["response_format"]["json_schema"]["schema"]
        expected_version = FINAL_JUDGE_SCHEMA_VERSION if role == "final_judge" else SCHEMA_VERSION
        assert first["schema_version"] == expected_version
        assert first["response_format"]["type"] == "json_schema"
        assert first["response_format"]["json_schema"]["strict"] is True
        assert schema["additionalProperties"] is False
        first["response_format"]["json_schema"]["schema"]["invented"] = True
        assert "invented" not in second["response_format"]["json_schema"]["schema"]


def test_planner_validator_enforces_exact_target_packet_coupling() -> None:
    packet = {
        "schema_version": 1,
        "decision": "plan",
        "target_files": ["src/x.py", "tests/test_x.py"],
        "packets": [
            {"id": "packet-01", "files": ["src/x.py", "tests/test_x.py"]}
        ],
        "verification_command": "python -m pytest -q tests/test_x.py",
        "constraints": ["preserve:x"],
    }
    assert validate_audition_packet(
        "planner", packet, target_files=packet["target_files"]
    ) == {"valid": True, "errors": []}

    packet["packets"][0]["files"] = ["src/x.py"]
    result = validate_audition_packet(
        "planner", packet, target_files=["src/x.py", "tests/test_x.py"]
    )
    assert result["valid"] is False
    assert "packet_coupling_invalid" in result["errors"]

    packet["packets"] = [
        {"id": "packet-01", "files": ["src/x.py"]},
        {"id": "packet-02", "files": ["tests/test_x.py"]},
    ]
    result = validate_audition_packet(
        "planner", packet, target_files=["src/x.py", "tests/test_x.py"]
    )
    assert result["valid"] is False
    assert "packet_coupling_invalid" in result["errors"]


def test_builder_validator_rejects_fences_duplicate_and_wrong_paths() -> None:
    targets = ["src/x.py", "tests/test_x.py"]
    packet = {
        "schema_version": 1,
        "files": [
            {"path": "src/x.py", "content": "def x():\n    return 1\n"},
            {"path": "tests/test_x.py", "content": "def test_x():\n    assert True\n"},
        ],
    }
    assert validate_audition_packet("builder", packet, target_files=targets)["valid"] is True

    packet["files"][1] = {"path": "src/x.py", "content": "```python\npass\n```"}
    result = validate_audition_packet("builder", packet, target_files=targets)
    assert result["valid"] is False
    assert set(result["errors"]) == {"builder_paths_invalid", "builder_files_invalid"}


def test_verdict_validator_enumerates_evidence_ids() -> None:
    packet = {
        "schema_version": 1,
        "status": "failed",
        "rationale": "pytest-r1 failed",
        "evidence_refs": ["pytest-r1"],
        "missing_evidence": [],
    }
    assert validate_audition_packet(
        "verifier", packet, evidence_ids=["pytest-r1"]
    )["valid"] is True

    packet["evidence_refs"] = ["invented-id"]
    result = validate_audition_packet(
        "verifier", packet, evidence_ids=["pytest-r1"]
    )
    assert result == {"valid": False, "errors": ["evidence_refs_invalid"]}


def test_final_judge_v3_requires_one_constrained_next_action() -> None:
    contract = build_audition_contract("final_judge", evidence_ids=["identity"])
    schema = contract["response_format"]["json_schema"]["schema"]
    packet = {
        "schema_version": FINAL_JUDGE_SCHEMA_VERSION,
        "decision": "hold",
        "rationale": "Identity evidence is missing.",
        "evidence_refs": ["identity"],
        "residual_risks": ["served model unknown"],
        "next_action": "provide_missing_evidence",
    }

    assert contract["schema_id"] == "devflow.final_judge.v3"
    assert schema["properties"]["schema_version"] == {"const": FINAL_JUDGE_SCHEMA_VERSION}
    assert validate_audition_packet(
        "final_judge", packet, evidence_ids=["identity"]
    ) == {"valid": True, "errors": []}

    packet["next_action"] = "override_and_qualify"
    result = validate_audition_packet(
        "final_judge", packet, evidence_ids=["identity"]
    )
    assert result["valid"] is False
    assert result["errors"] == ["next_action_invalid"]

    packet["next_action"] = "provide_missing_evidence"
    packet["next_human_decision"] = "Override the missing gate and qualify conditionally."
    result = validate_audition_packet("final_judge", packet, evidence_ids=["identity"])
    assert result == {"valid": False, "errors": ["keys_invalid"]}


def test_contract_rejects_unmeasured_role() -> None:
    try:
        build_audition_contract("brainstorm")
    except ValueError as exc:
        assert "Unsupported measured role" in str(exc)
    else:
        raise AssertionError("brainstorm unexpectedly received a measured-role schema")


def test_validator_rejects_nested_planner_schema_violations() -> None:
    packet = {
        "schema_version": 1,
        "decision": "plan",
        "target_files": ["src/a.py", "tests/test_a.py"],
        "packets": [{
            "id": "packet-01",
            "files": ["src/a.py", "tests/test_a.py"],
            "extra": True,
        }],
        "verification_command": "pytest -q",
        "constraints": ["preserve", "preserve"],
    }

    result = validate_audition_packet(
        "planner", packet, target_files=["src/a.py", "tests/test_a.py"]
    )

    assert result["valid"] is False
    assert "packet_coupling_invalid" in result["errors"]
    assert "constraints_invalid" in result["errors"]


def test_validator_rejects_unknown_or_duplicate_missing_evidence() -> None:
    packet = {
        "schema_version": 1,
        "status": "needs_review",
        "rationale": "missing",
        "evidence_refs": ["known"],
        "missing_evidence": ["unknown", "unknown"],
    }

    result = validate_audition_packet(
        "verifier", packet, evidence_ids=["known"]
    )

    assert result["valid"] is False
    assert "missing_evidence_invalid" in result["errors"]
