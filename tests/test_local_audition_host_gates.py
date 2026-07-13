import pytest

from devflow.loop.local_audition_host_gates import (
    AuthoritativeReceiptInput,
    FinalDecisionInputs,
    IdentityEvidenceInput,
    MandatoryChoiceInput,
    ReliabilityResultInput,
    ReviewResultInput,
    VerificationTestReceiptInput,
    classify_final_decision,
    derive_final_judge_next_human_decision,
    evaluate_final_judge_action,
    evaluate_host_gates,
    summarize_final_decision,
)


def _final_inputs(**updates) -> FinalDecisionInputs:
    values = {
        "test_receipt": VerificationTestReceiptInput("tests-r1", 0, 0, 0, "passed"),
        "review_result": ReviewResultInput("review-r1", "passed"),
        "reliability_result": ReliabilityResultInput("reliability-r1", "safe"),
        "identity_evidence": IdentityEvidenceInput(
            "identity-r1", "expected-model", "expected-model", True
        ),
        "required_artifact_ids": ("manifest", "diff"),
        "present_artifact_ids": ("manifest", "diff"),
    }
    values.update(updates)
    return FinalDecisionInputs(**values)


def test_clean_host_evidence_allows_model_decision() -> None:
    assert evaluate_host_gates(
        test_result={"exit_code": 0, "failed": 0, "errors": 0},
        required_artifacts=["manifest", "diff"],
        present_artifacts=["manifest", "diff"],
        receipt_outcomes=["passed"],
        required_evidence_ids=["pytest-r1"],
        cited_evidence_ids=["pytest-r1"],
        required_regressions=["duplicates"],
        observed_regressions=["duplicates"],
    ) == {"outcome": "model_may_decide", "findings": []}


def test_deterministic_failures_cannot_be_overridden() -> None:
    result = evaluate_host_gates(
        test_result={"exit_code": 1, "failed": 1, "errors": 0},
        required_artifacts=["manifest", "diff"],
        present_artifacts=["manifest"],
        receipt_outcomes=["passed", "failed"],
        required_evidence_ids=["pytest-r1"],
        cited_evidence_ids=["invented"],
        required_regressions=["bool-is-not-int"],
        observed_regressions=[],
        allowed_scope=["src/names.py", "tests/test_names.py"],
        observed_scope=[
            "src/names.py",
            "tests/test_names.py",
            "src/dashboard.py",
        ],
        unresolved_mandatory_choices=["Choose the release region."],
    )

    assert result["outcome"] == "block"
    assert [finding["gate_id"] for finding in result["findings"]] == [
        "deterministic_tests",
        "required_artifacts",
        "receipt_conflict",
        "evidence_references",
        "required_regressions",
        "scope_boundary",
        "mandatory_human_choice",
    ]


def test_scope_expansion_and_failed_tests_are_terminal_host_facts() -> None:
    result = evaluate_host_gates(
        test_result={"exit_code": 1, "failed": 1, "errors": 0},
        allowed_scope=["src/names.py", "tests/test_names.py"],
        observed_scope=[
            "src/names.py",
            "tests/test_names.py",
            "src/dashboard.py",
            "src/database.py",
            "deploy/prod.yaml",
        ],
    )

    assert result == {
        "outcome": "failed",
        "findings": [
            {"gate_id": "deterministic_tests", "outcome": "failed"},
            {"gate_id": "scope_boundary", "outcome": "failed"},
        ],
    }


def test_evidence_gate_allows_optional_valid_ids_but_requires_mandatory_ids() -> None:
    assert evaluate_host_gates(
        required_evidence_ids=["required"],
        allowed_evidence_ids=["required", "optional"],
        cited_evidence_ids=["required", "optional"],
    ) == {"outcome": "model_may_decide", "findings": []}

    result = evaluate_host_gates(
        required_evidence_ids=["required"],
        allowed_evidence_ids=["required", "optional"],
        cited_evidence_ids=["optional"],
    )
    assert result["outcome"] == "needs_review"


def test_deterministic_failure_is_not_softened_by_receipt_conflict() -> None:
    result = evaluate_host_gates(
        test_result={"exit_code": 1, "failed": 1, "errors": 0},
        receipt_outcomes=["passed", "failed"],
    )

    assert result["outcome"] == "failed"
    assert {item["gate_id"] for item in result["findings"]} == {
        "deterministic_tests",
        "receipt_conflict",
    }


def test_final_judge_action_gate_prohibits_override_after_failure() -> None:
    passed = evaluate_final_judge_action(
        evidence_state="failed",
        decision="block",
        next_action="repair_and_reverify",
    )
    assert passed["valid"] is True
    assert passed["derived_next_human_decision"] == "Repair the failed gate and rerun verification."

    result = evaluate_final_judge_action(
        evidence_state="failed",
        decision="block",
        next_action="none",
    )

    assert result["valid"] is False
    assert result["errors"] == ["final_judge_next_action_mismatch"]


def test_final_judge_action_gate_distinguishes_missing_conflicting_and_choice() -> None:
    cases = {
        "missing": ("hold", "provide_missing_evidence", "Provide the missing required evidence."),
        "conflicting": (
            "hold",
            "reconcile_conflicting_evidence",
            "Reconcile the conflicting authoritative evidence.",
        ),
        "mandatory_choice": (
            "block",
            "human_choice_required",
            "Make the unresolved mandatory human choice.",
        ),
        "qualify": ("qualify", "none", "none"),
    }

    for state, (decision, action, human_decision) in cases.items():
        result = evaluate_final_judge_action(
            evidence_state=state,
            decision=decision,
            next_action=action,
        )
        assert result["valid"] is True
        assert result["derived_next_human_decision"] == human_decision


def test_final_judge_display_text_is_host_derived_and_fail_closed() -> None:
    assert derive_final_judge_next_human_decision("provide_missing_evidence") == (
        "Provide the missing required evidence."
    )

    try:
        derive_final_judge_next_human_decision("override_and_qualify")
    except ValueError as exc:
        assert "Unsupported final-judge next action" in str(exc)
    else:
        raise AssertionError("unknown action unexpectedly received display text")


@pytest.mark.parametrize(
    ("updates", "expected"),
    [
        ({}, ("qualify", "none", "qualify")),
        (
            {"test_receipt": VerificationTestReceiptInput("tests-r1", 1, 1, 0, "failed")},
            ("block", "repair_and_reverify", "failed"),
        ),
        (
            {"mandatory_choices": (MandatoryChoiceInput("choice-r1", "unresolved", "Choose migration policy."),)},
            ("block", "human_choice_required", "mandatory_choice"),
        ),
        (
            {"identity_evidence": None},
            ("hold", "provide_missing_evidence", "missing"),
        ),
        (
            {"review_result": ReviewResultInput("review-r1", "failed")},
            ("block", "repair_and_reverify", "failed"),
        ),
        (
            {
                "test_receipt": None,
                "authoritative_receipts": (
                    AuthoritativeReceiptInput("tests-a", "tests", "authoritative", "passed"),
                    AuthoritativeReceiptInput("tests-b", "tests", "authoritative", "failed"),
                ),
            },
            ("hold", "reconcile_conflicting_evidence", "conflicting"),
        ),
    ],
)
def test_six_clean_room_states_are_host_decided(updates, expected) -> None:
    receipt = classify_final_decision(_final_inputs(**updates))
    assert (receipt["decision"], receipt["next_action"], receipt["evidence_state"]) == expected


def test_independent_failure_wins_over_conflict_and_retains_both_findings() -> None:
    receipt = classify_final_decision(
        _final_inputs(
            review_result=ReviewResultInput("review-failed", "failed"),
            test_receipt=None,
            authoritative_receipts=(
                AuthoritativeReceiptInput("tests-a", "tests", "authoritative", "passed"),
                AuthoritativeReceiptInput("tests-b", "tests", "authoritative", "failed"),
            ),
        )
    )

    assert receipt["decision"] == "block"
    assert receipt["next_action"] == "repair_and_reverify"
    assert receipt["decisive_evidence_refs"] == ["review-failed"]
    assert {item["gate_id"]: item["state"] for item in receipt["findings"]}[
        "tests"
    ] == "conflicting"


def test_mandatory_choice_wins_over_failure_and_resolved_choice_does_not_block() -> None:
    blocked = classify_final_decision(
        _final_inputs(
            review_result=ReviewResultInput("review-failed", "failed"),
            mandatory_choices=(
                MandatoryChoiceInput("choice-r1", "unresolved", "Choose region."),
            ),
        )
    )
    assert blocked["next_action"] == "human_choice_required"

    qualified = classify_final_decision(
        _final_inputs(
            mandatory_choices=(
                MandatoryChoiceInput("choice-r1", "resolved", "Use us-central."),
            )
        )
    )
    assert qualified["decision"] == "qualify"


def test_failure_wins_over_missing_and_reliability_failure_is_explicit() -> None:
    receipt = classify_final_decision(
        _final_inputs(
            review_result=None,
            reliability_result=ReliabilityResultInput("reliability-r1", "unsafe"),
        )
    )
    assert receipt["evidence_state"] == "failed"
    assert receipt["decisive_evidence_refs"] == ["reliability-r1"]


def test_blocked_and_needs_review_statuses_normalize_before_precedence() -> None:
    blocked = classify_final_decision(
        _final_inputs(review_result=ReviewResultInput("review-r1", "blocked"))
    )
    assert blocked["decision"] == "block"

    missing = classify_final_decision(
        _final_inputs(review_result=ReviewResultInput("review-r1", "needs_review"))
    )
    assert missing["decision"] == "hold"
    assert missing["next_action"] == "provide_missing_evidence"

    receipt_states = classify_final_decision(
        _final_inputs(
            authoritative_receipts=(
                AuthoritativeReceiptInput("deploy-a", "deploy", "authoritative", "blocked"),
                AuthoritativeReceiptInput("docs-a", "docs", "authoritative", "needs_review"),
            ),
            required_gate_ids=("tests", "review", "reliability", "identity", "artifacts", "deploy", "docs"),
        )
    )
    states = {item["gate_id"]: item["state"] for item in receipt_states["findings"]}
    assert states["deploy"] == "failed"
    assert states["docs"] == "missing"


@pytest.mark.parametrize(
    "updates",
    [
        {"test_receipt": VerificationTestReceiptInput("tests-r1", 1, 1, 0, "passed")},
        {"identity_evidence": IdentityEvidenceInput("identity-r1", "a", "b", True)},
        {"mandatory_choices": (MandatoryChoiceInput("choice-r1", "resolved", ""),)},
        {"review_result": ReviewResultInput("review-r1", "surprising")},
    ],
)
def test_malformed_unknown_and_inconsistent_inputs_cannot_qualify(updates) -> None:
    receipt = classify_final_decision(_final_inputs(**updates))
    assert receipt["decision"] != "qualify"


def test_required_identity_and_artifacts_must_be_explicitly_present() -> None:
    missing_identity = classify_final_decision(_final_inputs(identity_evidence=None))
    assert "identity" in missing_identity["decisive_evidence_refs"]

    missing_artifact = classify_final_decision(
        _final_inputs(present_artifact_ids=("manifest",))
    )
    assert missing_artifact["decision"] == "hold"
    assert "artifact:diff" in missing_artifact["decisive_evidence_refs"]


def test_product_required_gate_must_be_explicitly_passing() -> None:
    missing = classify_final_decision(
        _final_inputs(
            required_gate_ids=("tests", "review", "reliability", "identity", "artifacts", "release"),
        )
    )
    assert missing["decision"] == "hold"
    assert "release" in missing["decisive_evidence_refs"]

    passing = classify_final_decision(
        _final_inputs(
            required_gate_ids=("tests", "review", "reliability", "identity", "artifacts", "release"),
            authoritative_receipts=(
                AuthoritativeReceiptInput("release-r1", "release", "authoritative", "passed"),
            ),
        )
    )
    assert passing["decision"] == "qualify"


def test_optional_summary_failure_falls_back_without_mutating_receipt() -> None:
    receipt = classify_final_decision(_final_inputs())
    before = dict(receipt)

    def broken(_receipt):
        raise RuntimeError("summary unavailable")

    assert summarize_final_decision(receipt, broken) == "none"
    assert receipt == before
