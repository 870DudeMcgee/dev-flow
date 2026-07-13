"""Deterministic role scorecard for local-model audition evidence."""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
import math

from .local_audition_evidence import FAILURE_CATEGORIES


CRITICAL_RELIABILITY_FLAGS = (
    "critical_false_accept",
    "identity_drift",
    "unsafe_deterministic_override",
    "scope_violation",
    "malformed_required_packet",
    "unreliable_failure_behavior",
)


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


_REASON_ORDER = (
    *CRITICAL_RELIABILITY_FLAGS,
    "malformed_reliability_evidence",
    "malformed_terminal_evidence",
    "malformed_metric_evidence",
    "incomplete_repeat_evidence",
    "role_mismatch",
    "malformed_group_identity",
)


def _ordered_reasons(reasons: set[str]) -> list[str]:
    order = {reason: index for index, reason in enumerate(_REASON_ORDER)}
    return sorted(reasons, key=lambda reason: (order.get(reason, len(order)), reason))


def _valid_metric(value: object, *, maximum: float | None = None) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    if not math.isfinite(value) or value < 0:
        return False
    return maximum is None or value <= maximum


def _valid_failure_classification(value: object) -> bool:
    if not isinstance(value, Mapping):
        return False
    reason = value.get("reason")
    refs = value.get("evidence_refs")
    return (
        value.get("category") in FAILURE_CATEGORIES
        and isinstance(reason, str)
        and bool(reason.strip())
        and isinstance(refs, list)
        and bool(refs)
        and all(isinstance(ref, str) and ref.strip() for ref in refs)
        and len(refs) == len(set(refs))
    )


def rank_role_candidates(
    records: Sequence[Mapping],
    *,
    role: str,
    required_case_ids: Sequence[str],
    required_repeats: int = 3,
) -> dict:
    """Reliability-gate and rank candidate fingerprints for one role."""
    if not isinstance(role, str) or not role.strip():
        raise ValueError("role must be a nonblank string")
    if (
        not isinstance(required_repeats, int)
        or isinstance(required_repeats, bool)
        or required_repeats <= 0
    ):
        raise ValueError("required_repeats must be a positive integer")
    if isinstance(required_case_ids, (str, bytes)):
        raise ValueError("required_case_ids must be a sequence of identifiers")
    required_cases = tuple(required_case_ids)
    if (
        not required_cases
        or any(not isinstance(case_id, str) or not case_id.strip() for case_id in required_cases)
        or len(required_cases) != len(set(required_cases))
    ):
        raise ValueError("required_case_ids must be unique nonblank strings")
    if isinstance(records, (str, bytes)) or not isinstance(records, Sequence):
        raise ValueError("records must be a sequence")

    buckets: dict[tuple[object, object, object], list[Mapping]] = defaultdict(list)
    for record in records:
        if not isinstance(record, Mapping):
            raise ValueError("records must contain mappings")
        attempt = record.get("attempt")
        if not isinstance(attempt, Mapping):
            raise ValueError("each record must contain attempt metadata")
        if attempt.get("role") != role:
            continue
        key = (
            attempt.get("candidate_id"),
            record.get("artifact_fingerprint"),
            record.get("runtime_fingerprint"),
        )
        buckets[key].append(record)

    ranked: list[dict] = []
    ineligible: list[dict] = []
    expected_repeats = set(range(1, required_repeats + 1))
    required_case_set = set(required_cases)

    for key, group in buckets.items():
        candidate_id, artifact_fingerprint, runtime_fingerprint = key
        reasons: set[str] = set()
        for identity in key:
            if not isinstance(identity, str) or not identity.strip():
                reasons.add("malformed_group_identity")

        cases: dict[str, dict[int, Mapping]] = defaultdict(dict)
        quality_scores: list[float] = []
        durations: list[float] = []
        token_counts: list[float] = []

        for record in group:
            attempt = record["attempt"]
            case_id = attempt.get("case_id")
            repeat = attempt.get("repeat")
            if (
                not isinstance(case_id, str)
                or not case_id.strip()
                or not isinstance(repeat, int)
                or isinstance(repeat, bool)
                or repeat <= 0
                or repeat in cases[case_id]
            ):
                reasons.add("incomplete_repeat_evidence")
            else:
                cases[case_id][repeat] = record

            reliability = record.get("reliability_outcome")
            if not isinstance(reliability, Mapping) or any(
                flag not in reliability or type(reliability[flag]) is not bool
                for flag in CRITICAL_RELIABILITY_FLAGS
            ):
                reasons.add("malformed_reliability_evidence")
            else:
                reasons.update(
                    flag for flag in CRITICAL_RELIABILITY_FLAGS if reliability[flag]
                )

            expected_model = record.get("expected_model")
            served_model = record.get("served_model")
            if (
                not isinstance(expected_model, str)
                or not expected_model.strip()
                or not isinstance(served_model, str)
                or not served_model.strip()
                or expected_model != served_model
            ):
                reasons.add("identity_drift")

            status = record.get("terminal_status")
            classification = record.get("failure_classification")
            if status == "failed" and not _valid_failure_classification(classification):
                reasons.add("unreliable_failure_behavior")
            elif not (
                status == "failed"
                or (status == "completed" and classification is None)
            ):
                reasons.add("malformed_terminal_evidence")

            quality = record.get("quality_outcome")
            timing = record.get("timing")
            usage = record.get("usage")
            score = quality.get("score") if isinstance(quality, Mapping) else None
            duration = (
                timing.get("duration_seconds") if isinstance(timing, Mapping) else None
            )
            tokens = usage.get("total_tokens") if isinstance(usage, Mapping) else None
            if (
                not _valid_metric(score, maximum=100)
                or not _valid_metric(duration)
                or not _valid_metric(tokens)
            ):
                reasons.add("malformed_metric_evidence")
            else:
                quality_scores.append(float(score))
                durations.append(float(duration))
                token_counts.append(float(tokens))

        if set(cases) != required_case_set or any(
            set(cases[case_id]) != expected_repeats for case_id in required_case_set
        ):
            reasons.add("incomplete_repeat_evidence")

        if reasons:
            ineligible.append(
                {
                    "candidate_id": candidate_id,
                    "artifact_fingerprint": artifact_fingerprint,
                    "runtime_fingerprint": runtime_fingerprint,
                    "reasons": _ordered_reasons(reasons),
                }
            )
            continue

        case_consistency = []
        for case_id in required_cases:
            scores = [
                float(cases[case_id][repeat]["quality_outcome"]["score"])
                for repeat in range(1, required_repeats + 1)
            ]
            case_consistency.append(100.0 - (max(scores) - min(scores)))
        ranked.append(
            {
                "candidate_id": candidate_id,
                "artifact_fingerprint": artifact_fingerprint,
                "runtime_fingerprint": runtime_fingerprint,
                "attempts": len(group),
                "quality": sum(quality_scores) / len(quality_scores),
                "repeat_consistency": sum(case_consistency) / len(case_consistency),
                "mean_duration_seconds": sum(durations) / len(durations),
                "mean_total_tokens": sum(token_counts) / len(token_counts),
            }
        )

    ranked.sort(
        key=lambda item: (
            -item["quality"],
            -item["repeat_consistency"],
            item["mean_duration_seconds"],
            item["mean_total_tokens"],
            item["candidate_id"],
            item["artifact_fingerprint"],
            item["runtime_fingerprint"],
        )
    )
    for rank, item in enumerate(ranked, start=1):
        item["rank"] = rank
    ineligible.sort(
        key=lambda item: (
            str(item["candidate_id"]),
            str(item["artifact_fingerprint"]),
            str(item["runtime_fingerprint"]),
        )
    )
    return {
        "schema_version": 1,
        "role": role,
        "required_case_ids": list(required_cases),
        "required_repeats": required_repeats,
        "ranked": ranked,
        "ineligible": ineligible,
    }


__all__ = ["CRITICAL_RELIABILITY_FLAGS", "rank_role_candidates", "role_score"]
