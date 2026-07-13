"""Pure deterministic gates applied before local-model semantic judgments."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any


FINAL_JUDGE_NEXT_DECISION_BY_ACTION = {
    "none": "none",
    "repair_and_reverify": "Repair the failed gate and rerun verification.",
    "provide_missing_evidence": "Provide the missing required evidence.",
    "reconcile_conflicting_evidence": "Reconcile the conflicting authoritative evidence.",
    "human_choice_required": "Make the unresolved mandatory human choice.",
}


def derive_final_judge_next_human_decision(next_action: str) -> str:
    """Render safe human-facing text from a validated machine action."""
    try:
        return FINAL_JUDGE_NEXT_DECISION_BY_ACTION[next_action]
    except KeyError as exc:
        raise ValueError(f"Unsupported final-judge next action: {next_action!r}") from exc


_FINAL_JUDGE_ACTION_BY_STATE = {
    "qualify": ("qualify", "none"),
    "failed": ("block", "repair_and_reverify"),
    "missing": ("hold", "provide_missing_evidence"),
    "conflicting": ("hold", "reconcile_conflicting_evidence"),
    "mandatory_choice": ("block", "human_choice_required"),
}

FINAL_DECISION_REQUIRED_GATES = (
    "tests",
    "review",
    "reliability",
    "identity",
    "artifacts",
)


@dataclass(frozen=True)
class VerificationTestReceiptInput:
    evidence_id: str
    exit_code: int | None
    failed_count: int | None
    error_count: int | None
    status: str


@dataclass(frozen=True)
class ReviewResultInput:
    evidence_id: str
    status: str


@dataclass(frozen=True)
class ReliabilityResultInput:
    evidence_id: str
    status: str


@dataclass(frozen=True)
class IdentityEvidenceInput:
    evidence_id: str
    configured_identity: str | None
    served_identity: str | None
    matched: bool | None


@dataclass(frozen=True)
class AuthoritativeReceiptInput:
    evidence_id: str
    gate_id: str
    authority: str
    status: str


@dataclass(frozen=True)
class MandatoryChoiceInput:
    evidence_id: str
    status: str
    choice: str


@dataclass(frozen=True)
class FinalDecisionInputs:
    test_receipt: VerificationTestReceiptInput | None = None
    review_result: ReviewResultInput | None = None
    reliability_result: ReliabilityResultInput | None = None
    identity_evidence: IdentityEvidenceInput | None = None
    required_artifact_ids: tuple[str, ...] = ()
    present_artifact_ids: tuple[str, ...] = ()
    authoritative_receipts: tuple[AuthoritativeReceiptInput, ...] = ()
    mandatory_choices: tuple[MandatoryChoiceInput, ...] = ()
    required_gate_ids: tuple[str, ...] = field(
        default_factory=lambda: FINAL_DECISION_REQUIRED_GATES
    )


def _valid_identifier(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _source(
    sources: dict[str, list[dict[str, Any]]],
    gate_id: str,
    evidence_id: Any,
    state: str,
    reason: str | None = None,
) -> None:
    ref = str(evidence_id).strip() if _valid_identifier(evidence_id) else gate_id
    item: dict[str, Any] = {"evidence_id": ref, "state": state}
    if reason:
        item["reason"] = reason
    sources.setdefault(gate_id, []).append(item)


def _normalized_status(status: Any, mapping: Mapping[str, str]) -> str | None:
    return mapping.get(status) if isinstance(status, str) else None


def classify_final_decision(inputs: FinalDecisionInputs) -> dict[str, Any]:
    """Normalize typed facts and return the authoritative host decision receipt."""
    if not isinstance(inputs, FinalDecisionInputs):
        raise TypeError("final decision inputs must be FinalDecisionInputs")

    sources: dict[str, list[dict[str, Any]]] = {}
    test = inputs.test_receipt
    if test is not None:
        if not isinstance(test, VerificationTestReceiptInput) or not _valid_identifier(
            test.evidence_id
        ):
            _source(sources, "tests", "tests", "missing", "malformed_test_receipt")
        else:
            state = _normalized_status(
                test.status,
                {
                    "passed": "passed",
                    "failed": "failed",
                    "blocked": "failed",
                    "needs_review": "missing",
                    "missing": "missing",
                },
            )
            counters_valid = all(
                type(value) is int and value >= 0
                for value in (test.exit_code, test.failed_count, test.error_count)
            )
            passed_consistent = not (
                state == "passed"
                and counters_valid
                and (test.exit_code != 0 or test.failed_count != 0 or test.error_count != 0)
            )
            if state is None or not counters_valid:
                _source(sources, "tests", test.evidence_id, "missing", "malformed_test_receipt")
            elif not passed_consistent:
                _source(sources, "tests", test.evidence_id, "conflicting", "inconsistent_test_receipt")
            else:
                _source(sources, "tests", test.evidence_id, state)

    review = inputs.review_result
    if review is not None:
        if not isinstance(review, ReviewResultInput) or not _valid_identifier(review.evidence_id):
            _source(sources, "review", "review", "missing", "malformed_review_result")
        else:
            state = _normalized_status(
                review.status,
                {
                    "passed": "passed",
                    "failed": "failed",
                    "blocked": "failed",
                    "needs_review": "missing",
                    "missing": "missing",
                },
            )
            _source(
                sources,
                "review",
                review.evidence_id,
                state or "missing",
                None if state else "unknown_review_status",
            )

    reliability = inputs.reliability_result
    if reliability is not None:
        if not isinstance(reliability, ReliabilityResultInput) or not _valid_identifier(reliability.evidence_id):
            _source(sources, "reliability", "reliability", "missing", "malformed_reliability_result")
        else:
            state = _normalized_status(
                reliability.status,
                {"safe": "passed", "unsafe": "failed", "missing": "missing"},
            )
            _source(
                sources,
                "reliability",
                reliability.evidence_id,
                state or "missing",
                None if state else "unknown_reliability_status",
            )

    identity = inputs.identity_evidence
    if identity is not None:
        if not isinstance(identity, IdentityEvidenceInput) or not _valid_identifier(identity.evidence_id):
            _source(sources, "identity", "identity", "missing", "malformed_identity_evidence")
        else:
            configured = identity.configured_identity
            served = identity.served_identity
            present = _valid_identifier(configured) and _valid_identifier(served)
            if identity.matched is not None and type(identity.matched) is not bool:
                _source(sources, "identity", identity.evidence_id, "missing", "malformed_identity_match")
            elif not present or identity.matched is None:
                state = "conflicting" if identity.matched is True else "missing"
                _source(sources, "identity", identity.evidence_id, state, "incomplete_identity_evidence")
            elif (configured == served) != identity.matched:
                _source(sources, "identity", identity.evidence_id, "conflicting", "inconsistent_identity_evidence")
            else:
                _source(
                    sources,
                    "identity",
                    identity.evidence_id,
                    "passed" if identity.matched else "failed",
                )

    required_artifacts = inputs.required_artifact_ids
    present_artifacts = inputs.present_artifact_ids
    artifacts_valid = (
        isinstance(required_artifacts, tuple)
        and isinstance(present_artifacts, tuple)
        and all(_valid_identifier(item) for item in (*required_artifacts, *present_artifacts))
        and len(required_artifacts) == len(set(required_artifacts))
        and len(present_artifacts) == len(set(present_artifacts))
    )
    if not artifacts_valid:
        _source(sources, "artifacts", "artifacts", "missing", "malformed_artifact_ids")
    else:
        missing_artifacts = [item for item in required_artifacts if item not in set(present_artifacts)]
        refs = missing_artifacts or list(required_artifacts) or ["artifacts"]
        for ref in refs:
            _source(
                sources,
                "artifacts",
                f"artifact:{ref}" if ref != "artifacts" else ref,
                "missing" if missing_artifacts else "passed",
            )

    receipts = inputs.authoritative_receipts
    if not isinstance(receipts, tuple):
        _source(sources, "authoritative_receipts", "authoritative_receipts", "missing", "malformed_receipt_collection")
    else:
        for receipt in receipts:
            if (
                not isinstance(receipt, AuthoritativeReceiptInput)
                or not _valid_identifier(receipt.evidence_id)
                or not _valid_identifier(receipt.gate_id)
                or receipt.authority != "authoritative"
            ):
                gate_id = receipt.gate_id if isinstance(receipt, AuthoritativeReceiptInput) and _valid_identifier(receipt.gate_id) else "authoritative_receipts"
                evidence_id = receipt.evidence_id if isinstance(receipt, AuthoritativeReceiptInput) else gate_id
                _source(sources, gate_id, evidence_id, "missing", "malformed_authoritative_receipt")
                continue
            state = _normalized_status(
                receipt.status,
                {
                    "passed": "passed",
                    "failed": "failed",
                    "blocked": "failed",
                    "needs_review": "missing",
                    "missing": "missing",
                },
            )
            _source(
                sources,
                receipt.gate_id,
                receipt.evidence_id,
                state or "missing",
                None if state else "unknown_authoritative_status",
            )

    required_gates = inputs.required_gate_ids
    if (
        not isinstance(required_gates, tuple)
        or not required_gates
        or any(not _valid_identifier(gate) for gate in required_gates)
        or len(required_gates) != len(set(required_gates))
    ):
        required_gates = FINAL_DECISION_REQUIRED_GATES
        _source(sources, "required_gates", "required_gates", "missing", "malformed_required_gate_list")
    for gate_id in required_gates:
        if gate_id not in sources:
            _source(sources, gate_id, gate_id, "missing", "required_evidence_missing")

    findings: list[dict[str, Any]] = []
    for gate_id, gate_sources in sources.items():
        states = {item["state"] for item in gate_sources}
        state = "conflicting" if "conflicting" in states or len(states) > 1 else next(iter(states))
        finding: dict[str, Any] = {
            "gate_id": gate_id,
            "evidence_refs": list(dict.fromkeys(item["evidence_id"] for item in gate_sources)),
            "state": state,
        }
        reasons = list(dict.fromkeys(item["reason"] for item in gate_sources if item.get("reason")))
        if reasons:
            finding["reasons"] = reasons
        findings.append(finding)

    choices = inputs.mandatory_choices
    choice_refs: list[str] = []
    choice_state = "passed"
    choice_reasons: list[str] = []
    if not isinstance(choices, tuple):
        choice_state = "mandatory_choice"
        choice_refs = ["mandatory_choices"]
        choice_reasons = ["malformed_mandatory_choice_collection"]
    else:
        for choice in choices:
            if not isinstance(choice, MandatoryChoiceInput) or not _valid_identifier(
                choice.evidence_id
            ):
                choice_state = "mandatory_choice"
                choice_refs.append("mandatory_choice")
                choice_reasons.append("malformed_mandatory_choice")
                continue
            choice_refs.append(choice.evidence_id)
            if choice.status not in {"resolved", "unresolved"} or not _valid_identifier(
                choice.choice
            ):
                choice_state = "mandatory_choice"
                choice_reasons.append("incomplete_mandatory_choice")
            elif choice.status == "unresolved":
                choice_state = "mandatory_choice"
    if choice_refs:
        finding = {
            "gate_id": "mandatory_choices",
            "evidence_refs": list(dict.fromkeys(choice_refs)),
            "state": choice_state,
        }
        if choice_reasons:
            finding["reasons"] = list(dict.fromkeys(choice_reasons))
        findings.append(finding)

    precedence = ("mandatory_choice", "failed", "conflicting", "missing")
    winning_state = next(
        (state for state in precedence if any(item["state"] == state for item in findings)),
        "qualify",
    )
    state_key = "qualify" if winning_state == "qualify" else winning_state
    decision, next_action = _FINAL_JUDGE_ACTION_BY_STATE[state_key]
    decisive_refs = list(
        dict.fromkeys(
            ref
            for finding in findings
            if (
                finding["state"] == "passed"
                if winning_state == "qualify"
                else finding["state"] == winning_state
            )
            for ref in finding["evidence_refs"]
        )
    )
    return {
        "schema_version": 1,
        "evidence_state": winning_state,
        "decision": decision,
        "next_action": next_action,
        "decisive_evidence_refs": decisive_refs,
        "findings": findings,
        "next_human_decision": derive_final_judge_next_human_decision(next_action),
    }


def validate_final_decision_receipt(receipt: Any) -> dict[str, Any]:
    """Validate that a persisted receipt is entirely host-coherent."""
    if not isinstance(receipt, dict):
        raise ValueError("Final decision receipt must be an object.")
    expected_keys = {
        "schema_version",
        "evidence_state",
        "decision",
        "next_action",
        "decisive_evidence_refs",
        "findings",
        "next_human_decision",
    }
    if set(receipt) != expected_keys:
        raise ValueError("Final decision receipt keys are malformed.")
    state = receipt.get("evidence_state")
    expected = _FINAL_JUDGE_ACTION_BY_STATE.get(state)
    if receipt.get("schema_version") != 1 or expected is None:
        raise ValueError("Unsupported final decision receipt schema or state.")
    decision, action = expected
    if receipt.get("decision") != decision or receipt.get("next_action") != action:
        raise ValueError("Final decision receipt outcome/action mismatch.")
    if receipt.get("next_human_decision") != derive_final_judge_next_human_decision(
        action
    ):
        raise ValueError("Final decision receipt display text mismatch.")
    refs = receipt.get("decisive_evidence_refs")
    findings = receipt.get("findings")
    if (
        not isinstance(refs, list)
        or not refs
        or not all(_valid_identifier(ref) for ref in refs)
        or len(refs) != len(set(refs))
        or not isinstance(findings, list)
        or not findings
    ):
        raise ValueError("Final decision receipt evidence is malformed.")
    allowed_finding_states = {
        "passed",
        "failed",
        "missing",
        "conflicting",
        "mandatory_choice",
    }
    if any(
        not isinstance(finding, dict)
        or set(finding) not in (
            {"gate_id", "evidence_refs", "state"},
            {"gate_id", "evidence_refs", "state", "reasons"},
        )
        or not _valid_identifier(finding.get("gate_id"))
        or finding.get("state") not in allowed_finding_states
        or not isinstance(finding.get("evidence_refs"), list)
        or not finding["evidence_refs"]
        or not all(_valid_identifier(ref) for ref in finding["evidence_refs"])
        or len(finding["evidence_refs"]) != len(set(finding["evidence_refs"]))
        or (
            "reasons" in finding
            and (
                not isinstance(finding["reasons"], list)
                or not finding["reasons"]
                or not all(
                    _valid_identifier(reason) for reason in finding["reasons"]
                )
            )
        )
        for finding in findings
    ):
        raise ValueError("Final decision receipt findings are malformed.")
    findings_by_gate = {finding["gate_id"]: finding for finding in findings}
    if len(findings_by_gate) != len(findings):
        raise ValueError("Final decision receipt contains duplicate gate findings.")
    if state == "qualify":
        if any(finding["state"] != "passed" for finding in findings):
            raise ValueError("Qualifying receipt contains a nonpassing finding.")
        if not set(FINAL_DECISION_REQUIRED_GATES).issubset(findings_by_gate):
            raise ValueError("Qualifying receipt omits a mandatory gate.")
        decisive_state = "passed"
    else:
        decisive_state = state
    expected_refs = list(
        dict.fromkeys(
            ref
            for finding in findings
            if finding["state"] == decisive_state
            for ref in finding["evidence_refs"]
        )
    )
    if refs != expected_refs:
        raise ValueError("Final decision receipt decisive references mismatch.")
    return deepcopy(receipt)


def summarize_final_decision(
    receipt: Mapping[str, Any],
    summarizer: Any = None,
) -> str:
    """Return optional non-authoritative prose, falling back to host display text."""
    validated = validate_final_decision_receipt(dict(receipt))
    fallback = validated["next_human_decision"]
    if summarizer is None:
        return fallback
    try:
        summary = summarizer(deepcopy(validated))
    except Exception:
        return fallback
    return summary.strip() if isinstance(summary, str) and summary.strip() else fallback


def evaluate_final_judge_action(
    *,
    evidence_state: str,
    decision: Any,
    next_action: Any,
    next_human_decision: Any = None,
) -> dict[str, Any]:
    """Validate the verdict/action pair and derive the only safe display text."""
    expected = _FINAL_JUDGE_ACTION_BY_STATE.get(evidence_state)
    if expected is None:
        raise ValueError(f"Unsupported final-judge evidence state: {evidence_state!r}")
    expected_decision, expected_action = expected
    errors: list[str] = []
    if decision != expected_decision:
        errors.append("final_judge_decision_mismatch")
    if next_action != expected_action:
        errors.append("final_judge_next_action_mismatch")
    valid = not errors
    return {
        "valid": valid,
        "evidence_state": evidence_state,
        "expected_decision": expected_decision,
        "expected_next_action": expected_action,
        "derived_next_human_decision": (
            derive_final_judge_next_human_decision(next_action) if valid else None
        ),
        "errors": errors,
    }


def _normalize_verifier_scope_paths(paths: Any) -> tuple[str, ...] | None:
    """Return a stable validated scope set, or ``None`` when malformed."""
    if not isinstance(paths, list):
        return None

    normalized: list[str] = []
    for value in paths:
        if not isinstance(value, str) or not value.strip():
            return None
        posix_path = PurePosixPath(value)
        windows_path = PureWindowsPath(value)
        if (
            posix_path.is_absolute()
            or windows_path.is_absolute()
            or windows_path.drive
            or ".." in posix_path.parts
            or ".." in windows_path.parts
        ):
            return None
        normalized_value = posix_path.as_posix()
        if normalized_value in {"", "."}:
            return None
        normalized.append(normalized_value)

    if len(normalized) != len(set(normalized)):
        return None
    return tuple(sorted(normalized))


def evaluate_verifier_host_gates(
    *,
    test_result: Mapping[str, Any] | None,
    prior_review: Any,
    changed_files: Any,
    declared_target_files: Any,
) -> dict[str, Any]:
    """Classify verifier preflight facts before any model may be resolved."""
    counters = () if not isinstance(test_result, Mapping) else (
        test_result.get("exit_code"),
        test_result.get("failed"),
        test_result.get("errors"),
    )
    tests_passed = (
        len(counters) == 3
        and all(type(value) is int and value >= 0 for value in counters)
        and counters == (0, 0, 0)
    )
    test_outcome = "passed" if tests_passed else "failed"

    review_outcome = (
        {
            "passed": "passed",
            "failed": "failed",
            "blocked": "failed",
            "needs_review": "needs_review",
        }.get(prior_review, "needs_review")
        if isinstance(prior_review, str)
        else "needs_review"
    )

    normalized_changed = _normalize_verifier_scope_paths(changed_files)
    normalized_declared = _normalize_verifier_scope_paths(declared_target_files)
    if normalized_changed is None or normalized_declared is None:
        scope_outcome = "needs_review"
    elif normalized_changed != normalized_declared:
        scope_outcome = "failed"
    else:
        scope_outcome = "passed"

    outcomes = {
        "prior_review": review_outcome,
        "scope": scope_outcome,
        "tests": test_outcome,
    }
    if "failed" in outcomes.values():
        outcome = "failed"
    elif "needs_review" in outcomes.values():
        outcome = "needs_review"
    else:
        outcome = "model_may_decide"

    return {
        "outcome": outcome,
        "findings": [
            {"gate_id": gate_id, "outcome": gate_outcome}
            for gate_id, gate_outcome in outcomes.items()
        ],
        "changed_files": (
            list(normalized_changed) if normalized_changed is not None else None
        ),
        "declared_target_files": (
            list(normalized_declared) if normalized_declared is not None else None
        ),
    }


def evaluate_host_gates(
    *,
    test_result: Mapping[str, Any] | None = None,
    required_artifacts: Iterable[str] = (),
    present_artifacts: Iterable[str] = (),
    receipt_outcomes: Iterable[str] = (),
    required_evidence_ids: Iterable[str] = (),
    allowed_evidence_ids: Iterable[str] | None = None,
    cited_evidence_ids: Iterable[str] = (),
    required_regressions: Iterable[str] = (),
    observed_regressions: Iterable[str] = (),
    unresolved_mandatory_choices: Iterable[str] = (),
    allowed_scope: Iterable[str] = (),
    observed_scope: Iterable[str] = (),
) -> dict[str, Any]:
    """Return an ordered effective outcome that a model cannot override."""
    findings: list[dict[str, str]] = []

    if test_result is not None:
        exit_code = test_result.get("exit_code")
        failed = test_result.get("failed", 0)
        errors = test_result.get("errors", 0)
        if type(exit_code) is not int or exit_code != 0 or failed or errors:
            findings.append({"gate_id": "deterministic_tests", "outcome": "failed"})

    required_artifact_set = set(required_artifacts)
    if not required_artifact_set.issubset(set(present_artifacts)):
        findings.append({"gate_id": "required_artifacts", "outcome": "needs_review"})

    outcomes = set(receipt_outcomes)
    if "passed" in outcomes and outcomes.intersection({"failed", "blocked", "needs_review"}):
        findings.append({"gate_id": "receipt_conflict", "outcome": "needs_review"})

    required_ids = set(required_evidence_ids)
    allowed_ids = (
        set(allowed_evidence_ids)
        if allowed_evidence_ids is not None
        else required_ids
    )
    cited_ids = list(cited_evidence_ids)
    if (
        len(cited_ids) != len(set(cited_ids))
        or not required_ids.issubset(set(cited_ids))
        or not set(cited_ids).issubset(allowed_ids)
    ):
        findings.append({"gate_id": "evidence_references", "outcome": "needs_review"})

    if not set(required_regressions).issubset(set(observed_regressions)):
        findings.append({"gate_id": "required_regressions", "outcome": "failed"})

    allowed_scope_set = set(allowed_scope)
    observed_scope_set = set(observed_scope)
    if observed_scope_set and not observed_scope_set.issubset(allowed_scope_set):
        findings.append({"gate_id": "scope_boundary", "outcome": "failed"})

    if any(str(choice).strip() for choice in unresolved_mandatory_choices):
        findings.append({"gate_id": "mandatory_human_choice", "outcome": "block"})

    # A deterministic failure must not be softened to review by a simultaneous
    # missing/conflicting-evidence finding. Human blockers remain strongest.
    precedence = {"model_may_decide": 0, "needs_review": 1, "failed": 2, "block": 3}
    outcome = "model_may_decide"
    for finding in findings:
        if precedence[finding["outcome"]] > precedence[outcome]:
            outcome = finding["outcome"]
    return {"outcome": outcome, "findings": findings}


__all__ = [
    "AuthoritativeReceiptInput",
    "FINAL_DECISION_REQUIRED_GATES",
    "FINAL_JUDGE_NEXT_DECISION_BY_ACTION",
    "FinalDecisionInputs",
    "IdentityEvidenceInput",
    "MandatoryChoiceInput",
    "ReliabilityResultInput",
    "ReviewResultInput",
    "VerificationTestReceiptInput",
    "classify_final_decision",
    "derive_final_judge_next_human_decision",
    "evaluate_final_judge_action",
    "evaluate_host_gates",
    "evaluate_verifier_host_gates",
    "summarize_final_decision",
    "validate_final_decision_receipt",
]
