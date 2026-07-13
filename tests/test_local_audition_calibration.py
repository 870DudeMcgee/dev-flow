from copy import deepcopy

import pytest

from devflow.loop.local_audition_calibration import validate_calibration_receipts
from devflow.loop.local_audition_matrix import CandidateLane


def _receipt(candidate="candidate-a", port=18081, process_group=4101) -> dict:
    return {
        "schema_version": 1,
        "candidate_id": candidate,
        "expected_model": f"model-{candidate}",
        "served_model": f"model-{candidate}",
        "artifact_fingerprint": f"artifact-{candidate}",
        "observed_artifact_fingerprint": f"artifact-{candidate}",
        "status": "passed",
        "probe_kind": "identity_only",
        "semantic_call_made": False,
        "semantic_tokens": 0,
        "runtime_settings": {
            "bind_host": "127.0.0.1",
            "context_tokens": 8192,
            "max_in_flight": 1,
            "gpu_layers": 99,
            "cache_ram_mib": 512,
            "startup_timeout_seconds": 180,
            "speculation": False,
            "mtp": False,
        },
        "isolation": {
            "lane_scope": "test_only",
            "port_allocation": "os_ephemeral",
            "loopback_port": port,
            "process_group_id": process_group,
            "runtime_dir": f"/tmp/devflow/{candidate}/runtime",
            "output_dir": f"/tmp/devflow/{candidate}/output",
        },
        "cleanup": {
            "status": "completed",
            "process_exited": True,
            "port_released": True,
        },
    }


def test_valid_calibration_receipt_yields_candidate_lane() -> None:
    result = validate_calibration_receipts([_receipt()])

    assert result == {
        "schema_version": 1,
        "lanes": (
            CandidateLane(
                "candidate-a", "model-candidate-a", "artifact-candidate-a"
            ),
        ),
        "evaluations": (
            {
                "receipt_index": 0,
                "candidate_id": "candidate-a",
                "eligible": True,
                "reasons": [],
            },
        ),
    }


def test_identity_artifact_and_semantic_probe_fail_closed() -> None:
    receipt = _receipt()
    receipt["served_model"] = "wrong-model"
    receipt["observed_artifact_fingerprint"] = "wrong-artifact"
    receipt["semantic_call_made"] = True
    receipt["semantic_tokens"] = 4

    result = validate_calibration_receipts([receipt])

    assert result["lanes"] == ()
    assert result["evaluations"][0]["reasons"] == [
        "identity_mismatch",
        "artifact_fingerprint_mismatch",
        "semantic_probe_violation",
    ]


def test_m1_runtime_envelope_and_cleanup_are_exact() -> None:
    receipt = _receipt()
    receipt["runtime_settings"]["context_tokens"] = 4096
    receipt["runtime_settings"]["bind_host"] = "0.0.0.0"
    receipt["cleanup"]["port_released"] = False

    result = validate_calibration_receipts([receipt])

    assert result["evaluations"][0]["reasons"] == [
        "runtime_settings_mismatch",
        "cleanup_incomplete",
    ]


def test_lane_must_prove_ephemeral_test_only_isolation() -> None:
    receipt = _receipt()
    receipt["isolation"]["lane_scope"] = "production"
    receipt["isolation"]["port_allocation"] = "fixed"
    receipt["isolation"]["runtime_dir"] = "relative/runtime"

    result = validate_calibration_receipts([receipt])

    assert result["lanes"] == ()
    assert result["evaluations"][0]["reasons"] == [
        "isolation_not_ephemeral"
    ]


def test_failed_calibration_status_never_yields_a_lane() -> None:
    receipt = _receipt()
    receipt["status"] = "failed"

    result = validate_calibration_receipts([receipt])

    assert result["lanes"] == ()
    assert result["evaluations"][0]["reasons"] == [
        "calibration_not_passed"
    ]


@pytest.mark.parametrize("schema_version", [2, 1.0, True])
def test_schema_version_drift_is_malformed(schema_version) -> None:
    receipt = _receipt()
    receipt["schema_version"] = schema_version

    result = validate_calibration_receipts([receipt])

    assert result["evaluations"][0]["reasons"] == ["malformed_receipt"]


def test_runtime_and_output_directory_cannot_be_the_same() -> None:
    receipt = _receipt()
    receipt["isolation"]["output_dir"] = receipt["isolation"]["runtime_dir"]

    result = validate_calibration_receipts([receipt])

    assert result["evaluations"][0]["reasons"] == [
        "duplicate_isolation_resource"
    ]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("probe_kind", "semantic"),
        ("semantic_call_made", True),
        ("semantic_tokens", 1),
    ],
)
def test_each_semantic_probe_violation_fails_closed(field, value) -> None:
    receipt = _receipt()
    receipt[field] = value

    result = validate_calibration_receipts([receipt])

    assert result["evaluations"][0]["reasons"] == [
        "semantic_probe_violation"
    ]


def test_duplicate_isolation_resources_invalidate_every_owner() -> None:
    first = _receipt()
    second = _receipt("candidate-b", port=18081, process_group=4102)

    result = validate_calibration_receipts([first, second])

    assert result["lanes"] == ()
    assert [evaluation["reasons"] for evaluation in result["evaluations"]] == [
        ["duplicate_isolation_resource"],
        ["duplicate_isolation_resource"],
    ]


def test_distinct_valid_candidates_preserve_receipt_order() -> None:
    first = _receipt()
    second = _receipt("candidate-b", port=18082, process_group=4102)

    result = validate_calibration_receipts([second, first])

    assert [lane.candidate_id for lane in result["lanes"]] == [
        "candidate-b",
        "candidate-a",
    ]
    assert [evaluation["candidate_id"] for evaluation in result["evaluations"]] == [
        "candidate-b",
        "candidate-a",
    ]


def test_malformed_and_duplicate_candidate_receipts_do_not_raise() -> None:
    duplicate = deepcopy(_receipt())
    duplicate["isolation"]["loopback_port"] = 18082
    duplicate["isolation"]["process_group_id"] = 4102
    duplicate["isolation"]["runtime_dir"] += "-two"
    duplicate["isolation"]["output_dir"] += "-two"

    result = validate_calibration_receipts(["bad", _receipt(), duplicate])

    assert result["lanes"] == ()
    assert result["evaluations"] == (
        {
            "receipt_index": 0,
            "candidate_id": "<unknown>",
            "eligible": False,
            "reasons": ["malformed_receipt"],
        },
        {
            "receipt_index": 1,
            "candidate_id": "candidate-a",
            "eligible": False,
            "reasons": ["duplicate_candidate"],
        },
        {
            "receipt_index": 2,
            "candidate_id": "candidate-a",
            "eligible": False,
            "reasons": ["duplicate_candidate"],
        },
    )
