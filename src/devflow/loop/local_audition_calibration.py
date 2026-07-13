"""Fail-closed validation for no-semantic candidate calibration receipts.

This module performs no process, network, router, or profile operations.  It
only turns already-observed, fully cleaned-up calibration evidence into
candidate lanes that may be used by the audition matrix after approval.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path

from .local_audition_matrix import CandidateLane


_REASON_ORDER = (
    "malformed_receipt",
    "duplicate_candidate",
    "duplicate_isolation_resource",
    "isolation_not_ephemeral",
    "identity_mismatch",
    "artifact_fingerprint_mismatch",
    "semantic_probe_violation",
    "runtime_settings_mismatch",
    "calibration_not_passed",
    "cleanup_incomplete",
)

_REQUIRED_FIELDS = {
    "schema_version",
    "candidate_id",
    "expected_model",
    "served_model",
    "artifact_fingerprint",
    "observed_artifact_fingerprint",
    "status",
    "probe_kind",
    "semantic_call_made",
    "semantic_tokens",
    "runtime_settings",
    "isolation",
    "cleanup",
}

_M1_RUNTIME_SETTINGS = {
    "bind_host": "127.0.0.1",
    "context_tokens": 8192,
    "max_in_flight": 1,
    "gpu_layers": 99,
    "cache_ram_mib": 512,
    "startup_timeout_seconds": 180,
    "speculation": False,
    "mtp": False,
}

_ISOLATION_FIELDS = (
    "lane_scope",
    "port_allocation",
    "loopback_port",
    "process_group_id",
    "runtime_dir",
    "output_dir",
)

_ISOLATION_RESOURCE_FIELDS = (
    "loopback_port",
    "process_group_id",
    "runtime_dir",
    "output_dir",
)


def _nonblank(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _well_formed(receipt: object) -> bool:
    if not isinstance(receipt, Mapping) or not _REQUIRED_FIELDS.issubset(receipt):
        return False
    if receipt.get("schema_version") != 1 or type(receipt.get("schema_version")) is not int:
        return False
    if any(
        not _nonblank(receipt.get(field))
        for field in (
            "candidate_id",
            "expected_model",
            "served_model",
            "artifact_fingerprint",
            "observed_artifact_fingerprint",
            "status",
            "probe_kind",
        )
    ):
        return False
    if type(receipt.get("semantic_call_made")) is not bool:
        return False
    if type(receipt.get("semantic_tokens")) is not int or receipt["semantic_tokens"] < 0:
        return False
    runtime = receipt.get("runtime_settings")
    isolation = receipt.get("isolation")
    cleanup = receipt.get("cleanup")
    if not isinstance(runtime, Mapping) or not isinstance(isolation, Mapping):
        return False
    if not isinstance(cleanup, Mapping):
        return False
    if set(isolation) != set(_ISOLATION_FIELDS):
        return False
    port = isolation.get("loopback_port")
    process_group = isolation.get("process_group_id")
    if (
        type(port) is not int
        or not 1 <= port <= 65535
        or type(process_group) is not int
        or process_group <= 0
        or not _nonblank(isolation.get("lane_scope"))
        or not _nonblank(isolation.get("port_allocation"))
        or not _nonblank(isolation.get("runtime_dir"))
        or not _nonblank(isolation.get("output_dir"))
    ):
        return False
    return True


def _ordered(reasons: set[str]) -> list[str]:
    order = {reason: index for index, reason in enumerate(_REASON_ORDER)}
    return sorted(
        reasons,
        key=lambda reason: (order.get(reason, len(_REASON_ORDER)), reason),
    )


def validate_calibration_receipts(receipts: Sequence[Mapping]) -> dict:
    """Return lanes only for exact, isolated, no-semantic calibration evidence."""
    if isinstance(receipts, (str, bytes)) or not isinstance(receipts, Sequence):
        raise ValueError("receipts must be a sequence")

    receipt_list = list(receipts)
    valid_indexes = [
        index for index, receipt in enumerate(receipt_list) if _well_formed(receipt)
    ]
    candidate_counts = Counter(
        receipt_list[index]["candidate_id"] for index in valid_indexes
    )
    resource_owners: dict[tuple[str, object], list[int]] = defaultdict(list)
    for index in valid_indexes:
        isolation = receipt_list[index]["isolation"]
        for field in _ISOLATION_RESOURCE_FIELDS:
            resource_owners[(field, isolation[field])].append(index)

    duplicate_resource_indexes = {
        index
        for owners in resource_owners.values()
        if len(owners) > 1
        for index in owners
    }
    for index in valid_indexes:
        isolation = receipt_list[index]["isolation"]
        if isolation["runtime_dir"] == isolation["output_dir"]:
            duplicate_resource_indexes.add(index)

    lanes: list[CandidateLane] = []
    evaluations: list[dict] = []
    for index, receipt in enumerate(receipt_list):
        if index not in valid_indexes:
            evaluations.append(
                {
                    "receipt_index": index,
                    "candidate_id": "<unknown>",
                    "eligible": False,
                    "reasons": ["malformed_receipt"],
                }
            )
            continue

        candidate_id = receipt["candidate_id"]
        reasons: set[str] = set()
        if candidate_counts[candidate_id] > 1:
            reasons.add("duplicate_candidate")
        if index in duplicate_resource_indexes:
            reasons.add("duplicate_isolation_resource")
        isolation = receipt["isolation"]
        if not (
            isolation["lane_scope"] == "test_only"
            and isolation["port_allocation"] == "os_ephemeral"
            and Path(isolation["runtime_dir"]).is_absolute()
            and Path(isolation["output_dir"]).is_absolute()
        ):
            reasons.add("isolation_not_ephemeral")
        if receipt["served_model"] != receipt["expected_model"]:
            reasons.add("identity_mismatch")
        if receipt["observed_artifact_fingerprint"] != receipt["artifact_fingerprint"]:
            reasons.add("artifact_fingerprint_mismatch")
        if (
            receipt["probe_kind"] != "identity_only"
            or receipt["semantic_call_made"] is not False
            or receipt["semantic_tokens"] != 0
        ):
            reasons.add("semantic_probe_violation")
        if dict(receipt["runtime_settings"]) != _M1_RUNTIME_SETTINGS:
            reasons.add("runtime_settings_mismatch")
        if receipt["status"] != "passed":
            reasons.add("calibration_not_passed")
        cleanup = receipt["cleanup"]
        if not (
            cleanup.get("status") == "completed"
            and cleanup.get("process_exited") is True
            and cleanup.get("port_released") is True
        ):
            reasons.add("cleanup_incomplete")

        ordered_reasons = _ordered(reasons)
        eligible = not ordered_reasons
        evaluations.append(
            {
                "receipt_index": index,
                "candidate_id": candidate_id,
                "eligible": eligible,
                "reasons": ordered_reasons,
            }
        )
        if eligible:
            lanes.append(
                CandidateLane(
                    candidate_id=candidate_id,
                    expected_model=receipt["expected_model"],
                    fingerprint=receipt["artifact_fingerprint"],
                )
            )

    return {
        "schema_version": 1,
        "lanes": tuple(lanes),
        "evaluations": tuple(evaluations),
    }


__all__ = ["validate_calibration_receipts"]
