"""Deterministic role scorecard for local-model audition evidence."""
from __future__ import annotations


def role_score(cases: list[dict]) -> dict:
    """Count reliable passes without treating duplicate evidence as new cases."""
    valid_cases = [case for case in cases if isinstance(case, dict)] if isinstance(cases, list) else []
    case_ids = [
        case.get("case_id").strip()
        for case in valid_cases
        if isinstance(case.get("case_id"), str) and case.get("case_id").strip()
    ]
    distinct_case_ids = set(case_ids)
    reliable_passes = sum(
        case.get("passed") is True and case.get("reliable") is True
        for case in valid_cases
    )
    count = len(valid_cases)
    return {
        "cases": count,
        "distinct_cases": len(distinct_case_ids),
        "case_ids_unique": len(case_ids) == count == len(distinct_case_ids),
        "passes": reliable_passes,
        "reliable_passes": reliable_passes,
        "score": int(reliable_passes * 100 / count) if count else 0,
    }
