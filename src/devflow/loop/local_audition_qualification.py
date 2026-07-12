"""Pure qualification record construction for local-model auditions."""
from __future__ import annotations


def qualification_record(model, role, scorecard, gate) -> dict:
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
    status = (
        "qualified"
        if safe_cases >= 3 and safe_gate == "qualify" and evidence_consistent
        else "provisional"
    )
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
    }
