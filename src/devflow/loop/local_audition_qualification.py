"""Pure qualification record construction for local-model auditions."""
from __future__ import annotations


def _nonblank(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _packet_identity(packet, model, role):
    if not isinstance(packet, dict):
        return None
    if packet.get("candidate_id") != model or packet.get("role") != role:
        return None
    artifact = packet.get("artifact_fingerprint")
    runtime = packet.get("runtime_fingerprint")
    if not _nonblank(artifact) or not _nonblank(runtime):
        return None
    return artifact, runtime


def qualification_record(
    model,
    role,
    scorecard,
    gate,
    *,
    reliability=None,
    repeat_evidence=None,
    independent_review=None,
) -> dict:
    """Build a provisional or qualified record without mutating inputs."""
    scorecard_data = scorecard if isinstance(scorecard, dict) else {}
    gate_data = gate if isinstance(gate, dict) else {}
    cases = scorecard_data.get("cases", 0)
    distinct_cases = scorecard_data.get("distinct_cases", 0)
    case_ids_unique = scorecard_data.get("case_ids_unique", False)
    reliable_passes = scorecard_data.get("reliable_passes", 0)
    passes = scorecard_data.get("passes", reliable_passes)
    score = scorecard_data.get("score", 0)
    safe_cases = cases if type(cases) is int and cases >= 0 else 0
    safe_distinct_cases = (
        distinct_cases
        if type(distinct_cases) is int and 0 <= distinct_cases <= safe_cases
        else 0
    )
    safe_score = score if type(score) is int and 0 <= score <= 100 else 0
    gate_decision = gate_data.get("decision", "hold")
    safe_gate = gate_decision if gate_decision in {"qualify", "hold"} else "hold"
    gate_reasons = gate_data.get("reasons", [])
    valid_counts = (
        type(reliable_passes) is int
        and type(passes) is int
        and 0 <= reliable_passes == passes <= safe_cases
    )
    expected_score = (
        int(reliable_passes * 100 / safe_cases)
        if valid_counts and safe_cases
        else 0
    )
    evidence_consistent = (
        valid_counts
        and safe_score == expected_score
        and case_ids_unique is True
        and safe_distinct_cases == safe_cases
        and isinstance(gate_reasons, list)
        and not gate_reasons
        and safe_score >= 80
    )
    scorecard_ok = (
        safe_cases >= 3 and safe_gate == "qualify" and evidence_consistent
    )
    repeat_identity = _packet_identity(repeat_evidence, model, role)
    reliability_identity = _packet_identity(reliability, model, role)
    review_identity = _packet_identity(independent_review, model, role)

    reliability_ok = (
        reliability_identity is not None
        and reliability_identity == repeat_identity
        and reliability.get("eligible") is True
        and reliability.get("critical_failures") == []
    )
    repeat_case_ids = (
        repeat_evidence.get("case_ids")
        if isinstance(repeat_evidence, dict)
        else None
    )
    repeat_ok = (
        repeat_identity is not None
        and type(repeat_evidence.get("required_repeats")) is int
        and repeat_evidence.get("required_repeats") == 3
        and repeat_evidence.get("complete") is True
        and isinstance(repeat_case_ids, list)
        and bool(repeat_case_ids)
        and all(_nonblank(case_id) for case_id in repeat_case_ids)
        and len(repeat_case_ids) == len(set(repeat_case_ids))
        and len(repeat_case_ids) == safe_cases == safe_distinct_cases
        and type(repeat_evidence.get("attempt_count")) is int
        and repeat_evidence.get("attempt_count") == len(repeat_case_ids) * 3
    )
    review_ok = (
        review_identity is not None
        and review_identity == repeat_identity
        and independent_review.get("passed") is True
        and _nonblank(independent_review.get("review_id"))
        and independent_review.get("independent_from_candidate") is True
    )
    qualification_gates = {
        "scorecard": scorecard_ok,
        "reliability": reliability_ok,
        "three_repeat_evidence": repeat_ok,
        "independent_review": review_ok,
    }
    blocking_reasons = []
    if not reliability_ok:
        blocking_reasons.append("reliability_not_passed")
    if not repeat_ok:
        blocking_reasons.append("three_repeat_evidence_incomplete")
    if not review_ok:
        blocking_reasons.append("independent_review_not_passed")
    if not scorecard_ok:
        blocking_reasons.append("scorecard_inconsistent")
    status = "qualified" if not blocking_reasons else "provisional"
    return {
        "model": model,
        "role": role,
        "status": status,
        "evidence": {
            "cases": safe_cases,
            "distinct_cases": safe_distinct_cases,
            "score": safe_score,
            "gate": safe_gate,
            "consistent": evidence_consistent,
        },
        "qualification_gates": qualification_gates,
        "blocking_reasons": blocking_reasons,
    }
