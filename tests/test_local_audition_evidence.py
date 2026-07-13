import json
from pathlib import Path

import pytest

from devflow.loop.local_audition_evidence import (
    FAILURE_CATEGORIES,
    attempt_evidence_path,
    build_attempt_evidence,
    persist_attempt_evidence,
)
from devflow.loop.local_audition_matrix import AtomicAttempt, MatrixReceipt


def _attempt(sequence: int = 1) -> AtomicAttempt:
    case = {"case_id": "case-one", "role": "planner", "payload": {"value": 1}}
    return AtomicAttempt(
        sequence=sequence,
        candidate_id="candidate-a",
        expected_model="model-a",
        role="planner",
        case_id="case-one",
        repeat=1,
        fingerprint="artifact-fingerprint-a",
        case_json=json.dumps(case, sort_keys=True, separators=(",", ":")),
    )


def _runner_receipt(status: str = "completed", sequence: int = 1) -> dict:
    return {
        "case_id": "case-one",
        "role": "planner",
        "requested_model": "model-a",
        "actual_model": "model-a",
        "status": status,
        "content": "raw output",
        "usage": {"total_tokens": 15},
        "finish_reason": "stop",
        "error_type": "" if status == "completed" else "RuntimeError",
        "error": "" if status == "completed" else "transport failed",
        "sequence": sequence,
        "request_evidence": {"schema_id": "devflow.planner.v1"},
        "parsed_packet": {"schema_version": 1},
        "protocol_validation": {"valid": status == "completed"},
        "deterministic_gates": {"outcome": "passed" if status == "completed" else "failed"},
    }


def _matrix_receipt(status: str = "completed", sequence: int = 1) -> MatrixReceipt:
    return MatrixReceipt(
        attempt=_attempt(sequence),
        runner_receipt=_runner_receipt(status, sequence),
        scheduled_at=95.0,
        started_at=100.0,
        finished_at=105.0,
        queue_duration_seconds=5.0,
        duration_seconds=5.0,
        total_duration_seconds=10.0,
    )


def test_failure_categories_are_exact_and_stable() -> None:
    assert FAILURE_CATEGORIES == (
        "model_capability",
        "prompt_context_packaging",
        "tool_runtime",
        "orchestration_guardrail",
        "ground_truth_scorer",
        "infrastructure",
    )


def test_completed_attempt_evidence_contains_full_defensive_record() -> None:
    receipt = _matrix_receipt()
    evidence = build_attempt_evidence(
        receipt,
        runtime_fingerprint="runtime-fingerprint-a",
        reliability_outcome={"eligible": True},
        quality_outcome={"score": 0.8},
    )

    assert evidence == {
        "schema_version": 1,
        "attempt": {
            "sequence": 1,
            "candidate_id": "candidate-a",
            "role": "planner",
            "case_id": "case-one",
            "repeat": 1,
        },
        "request": {
            "case_id": "case-one",
            "role": "planner",
            "payload": {"value": 1},
        },
        "expected_model": "model-a",
        "served_model": "model-a",
        "artifact_fingerprint": "artifact-fingerprint-a",
        "runtime_fingerprint": "runtime-fingerprint-a",
        "timing": {
            "scheduled_at": 95.0,
            "started_at": 100.0,
            "finished_at": 105.0,
            "queue_duration_seconds": 5.0,
            "duration_seconds": 5.0,
            "total_duration_seconds": 10.0,
        },
        "usage": {"total_tokens": 15},
        "raw_output": "raw output",
        "request_evidence": {"schema_id": "devflow.planner.v1"},
        "parsed_packet": {"schema_version": 1},
        "protocol_validation": {"valid": True},
        "deterministic_gates": {"outcome": "passed"},
        "reliability_outcome": {"eligible": True},
        "quality_outcome": {"score": 0.8},
        "failure_classification": None,
        "terminal_status": "completed",
        "runner_receipt": receipt.runner_receipt,
    }

    evidence["request"]["payload"]["value"] = 99
    evidence["runner_receipt"]["content"] = "mutated"
    assert receipt.attempt.case_data()["payload"]["value"] == 1
    assert receipt.runner_receipt["content"] == "raw output"


@pytest.mark.parametrize(
    "updates",
    [
        {},
        {"failure_category": "unknown", "failure_reason": "x", "classification_evidence": ("e1",)},
        {"failure_category": "infrastructure", "classification_evidence": ("e1",)},
        {"failure_category": "infrastructure", "failure_reason": "x"},
    ],
)
def test_failed_attempt_requires_explicit_supported_classification(updates) -> None:
    with pytest.raises(ValueError):
        build_attempt_evidence(
            _matrix_receipt("failed"),
            runtime_fingerprint="runtime-fingerprint-a",
            reliability_outcome={"eligible": False},
            quality_outcome={},
            **updates,
        )


def test_failed_attempt_persists_grounded_classification() -> None:
    evidence = build_attempt_evidence(
        _matrix_receipt("failed"),
        runtime_fingerprint="runtime-fingerprint-a",
        reliability_outcome={"eligible": False},
        quality_outcome={},
        failure_category="infrastructure",
        failure_reason="transport exception before a usable completion",
        classification_evidence=("runner:error_type:RuntimeError",),
    )

    assert evidence["failure_classification"] == {
        "category": "infrastructure",
        "reason": "transport exception before a usable completion",
        "evidence_refs": ["runner:error_type:RuntimeError"],
    }
    assert evidence["terminal_status"] == "failed"


def test_completed_attempt_rejects_failure_classification() -> None:
    with pytest.raises(ValueError):
        build_attempt_evidence(
            _matrix_receipt(),
            runtime_fingerprint="runtime-fingerprint-a",
            reliability_outcome={"eligible": True},
            quality_outcome={"score": 0.8},
            failure_category="infrastructure",
            failure_reason="invented",
            classification_evidence=("invented",),
        )


def test_completed_attempt_requires_served_model_identity() -> None:
    receipt = _matrix_receipt()
    receipt.runner_receipt.pop("actual_model")

    with pytest.raises(ValueError):
        build_attempt_evidence(
            receipt,
            runtime_fingerprint="runtime-fingerprint-a",
            reliability_outcome={"eligible": True},
            quality_outcome={"score": 0.8},
        )


def test_attempt_evidence_path_is_sequence_ordered() -> None:
    assert attempt_evidence_path(Path("/run"), 1) == Path("/run/attempts/000001.json")
    assert attempt_evidence_path(Path("/run"), 123456) == Path(
        "/run/attempts/123456.json"
    )


def test_persist_attempt_evidence_is_atomic_and_write_once(tmp_path: Path) -> None:
    evidence = build_attempt_evidence(
        _matrix_receipt(sequence=7),
        runtime_fingerprint="runtime-fingerprint-a",
        reliability_outcome={"eligible": True},
        quality_outcome={"score": 0.8},
    )

    path = persist_attempt_evidence(tmp_path, evidence)

    assert path == tmp_path / "attempts" / "000007.json"
    assert json.loads(path.read_text()) == evidence
    assert list(path.parent.glob("*.tmp")) == []
    with pytest.raises(FileExistsError):
        persist_attempt_evidence(tmp_path, evidence)
    assert list(path.parent.glob("*.tmp")) == []


def test_persist_attempt_evidence_cleans_temp_after_commit_failure(tmp_path: Path) -> None:
    evidence = build_attempt_evidence(
        _matrix_receipt(sequence=7),
        runtime_fingerprint="runtime-fingerprint-a",
        reliability_outcome={"eligible": True},
        quality_outcome={},
    )

    def fail_commit(_source, _target) -> None:
        raise OSError("commit failed")

    with pytest.raises(OSError):
        persist_attempt_evidence(tmp_path, evidence, commit=fail_commit)
    assert list((tmp_path / "attempts").glob("*.tmp")) == []
    assert not attempt_evidence_path(tmp_path, 7).exists()
