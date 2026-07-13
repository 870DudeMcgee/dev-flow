from dataclasses import FrozenInstanceError, replace
from threading import Barrier, Event, Lock

import pytest

import devflow.loop.local_audition_matrix as matrix
from devflow.loop.local_audition_matrix import (
    CandidateLane,
    MatrixReceipt,
    expand_audition_matrix,
    run_audition_matrix,
)


def _candidates() -> tuple[CandidateLane, ...]:
    return (
        CandidateLane("candidate-a", "model-a", "fingerprint-a"),
        CandidateLane("candidate-b", "model-b", "fingerprint-b"),
    )


def _cases() -> tuple[dict, ...]:
    return (
        {"case_id": "case-one", "role": "planner", "payload": {"value": 1}},
        {"case_id": "case-two", "role": "builder", "payload": {"value": 2}},
    )


def _runner_receipt(sequence: int = 1) -> dict:
    return {
        "case_id": "case-one",
        "role": "planner",
        "requested_model": "model-a",
        "actual_model": "model-a",
        "status": "completed",
        "content": "ok",
        "usage": {},
        "finish_reason": "stop",
        "error_type": "",
        "error": "",
        "sequence": sequence,
        "request_evidence": {},
        "parsed_packet": {},
        "protocol_validation": {},
        "deterministic_gates": {},
    }


def test_expand_audition_matrix_is_exact_candidate_case_repeat_product() -> None:
    attempts = expand_audition_matrix(_candidates(), _cases())

    assert len(attempts) == 12
    assert [
        (
            attempt.sequence,
            attempt.candidate_id,
            attempt.expected_model,
            attempt.fingerprint,
            attempt.case_id,
            attempt.repeat,
        )
        for attempt in attempts
    ] == [
        (1, "candidate-a", "model-a", "fingerprint-a", "case-one", 1),
        (2, "candidate-a", "model-a", "fingerprint-a", "case-one", 2),
        (3, "candidate-a", "model-a", "fingerprint-a", "case-one", 3),
        (4, "candidate-a", "model-a", "fingerprint-a", "case-two", 1),
        (5, "candidate-a", "model-a", "fingerprint-a", "case-two", 2),
        (6, "candidate-a", "model-a", "fingerprint-a", "case-two", 3),
        (7, "candidate-b", "model-b", "fingerprint-b", "case-one", 1),
        (8, "candidate-b", "model-b", "fingerprint-b", "case-one", 2),
        (9, "candidate-b", "model-b", "fingerprint-b", "case-one", 3),
        (10, "candidate-b", "model-b", "fingerprint-b", "case-two", 1),
        (11, "candidate-b", "model-b", "fingerprint-b", "case-two", 2),
        (12, "candidate-b", "model-b", "fingerprint-b", "case-two", 3),
    ]


def test_attempts_and_candidates_are_frozen_and_case_data_is_defensive() -> None:
    candidate = CandidateLane("candidate-a", "model-a", "fingerprint-a")
    attempt = expand_audition_matrix((candidate,), _cases(), repeats=1)[0]

    with pytest.raises(FrozenInstanceError):
        candidate.candidate_id = "changed"

    with pytest.raises(FrozenInstanceError):
        attempt.case_id = "changed"

    first = attempt.case_data()
    first["payload"]["value"] = 999
    first["new_key"] = "local mutation"

    second = attempt.case_data()
    assert second == {
        "case_id": "case-one",
        "role": "planner",
        "payload": {"value": 1},
    }
    assert second is not first


def test_matrix_rejects_invalid_expansion_and_duplicate_sequences() -> None:
    candidate = CandidateLane("candidate-a", "model-a", "fingerprint-a")

    with pytest.raises(ValueError):
        expand_audition_matrix((candidate, candidate), _cases())

    with pytest.raises(ValueError):
        expand_audition_matrix((candidate,), _cases(), repeats=0)

    with pytest.raises(ValueError):
        expand_audition_matrix((candidate,), _cases(), repeats=-1)

    attempts = expand_audition_matrix((candidate,), _cases(), repeats=2)
    duplicate_sequences = (
        attempts[0],
        replace(attempts[1], sequence=attempts[0].sequence),
    )

    with pytest.raises(ValueError):
        run_audition_matrix(duplicate_sequences, lambda *_args: {})


def test_one_in_flight_per_candidate_and_cross_candidate_overlap() -> None:
    attempts = expand_audition_matrix(
        _candidates(),
        ({"case_id": "only", "role": "planner"},),
        repeats=2,
    )
    barrier = Barrier(2)
    lock = Lock()
    active = {"candidate-a": 0, "candidate-b": 0}
    max_active = {"candidate-a": 0, "candidate-b": 0}
    calls: list[tuple[str, int]] = []

    def invoke(attempt, model, case):
        with lock:
            active[attempt.candidate_id] += 1
            max_active[attempt.candidate_id] = max(
                max_active[attempt.candidate_id],
                active[attempt.candidate_id],
            )
            calls.append((attempt.candidate_id, attempt.repeat))
        barrier.wait(timeout=2)
        with lock:
            active[attempt.candidate_id] -= 1
        return {
            "actual_model": model,
            "content": case["case_id"],
            "usage": {},
            "finish_reason": "stop",
        }

    receipts = run_audition_matrix(attempts, invoke, max_workers=2)

    assert len(calls) == 4
    assert max_active == {"candidate-a": 1, "candidate-b": 1}
    assert [receipt.attempt.sequence for receipt in receipts] == [1, 2, 3, 4]


def test_matrix_returns_sequence_order_when_later_attempt_finishes_first() -> None:
    attempts = expand_audition_matrix(
        _candidates(),
        ({"case_id": "only", "role": "planner"},),
        repeats=1,
    )
    candidate_b_finished = Event()
    release_candidate_a = Event()
    completion_order: list[int] = []

    def invoke(attempt, model, case):
        if attempt.candidate_id == "candidate-a":
            assert candidate_b_finished.wait(timeout=2)
            completion_order.append(attempt.sequence)
            release_candidate_a.set()
        else:
            completion_order.append(attempt.sequence)
            candidate_b_finished.set()
            assert release_candidate_a.wait(timeout=2)
        return {
            "actual_model": model,
            "content": case["case_id"],
            "usage": {},
            "finish_reason": "stop",
        }

    receipts = run_audition_matrix(attempts, invoke, max_workers=2)

    assert completion_order == [2, 1]
    assert [receipt.attempt.sequence for receipt in receipts] == [1, 2]


def test_each_atomic_call_uses_runner_and_preserves_runner_receipt(monkeypatch) -> None:
    attempts = expand_audition_matrix(
        (CandidateLane("candidate-a", "model-a", "fingerprint-a"),),
        ({"case_id": "case-one", "role": "planner"},),
        repeats=1,
    )
    expected_receipt = _runner_receipt(sequence=37)
    runner_calls: list[tuple[list[dict], dict]] = []
    invocation_calls: list[tuple[int, str, dict]] = []

    def invoke(attempt, model, case):
        invocation_calls.append((attempt.sequence, model, case))
        return {
            "actual_model": model,
            "content": "ok",
            "usage": {},
            "finish_reason": "stop",
        }

    def spy_run_local_audition(cases, assignments, runner_invoke):
        runner_calls.append((cases, assignments))
        case = cases[0]
        model = assignments[case["role"]]
        runner_invoke(model, case)
        return [expected_receipt]

    monkeypatch.setattr(matrix, "run_local_audition", spy_run_local_audition)

    receipts = run_audition_matrix(attempts, invoke)

    assert runner_calls == [
        ([{"case_id": "case-one", "role": "planner"}], {"planner": "model-a"})
    ]
    assert invocation_calls == [
        (1, "model-a", {"case_id": "case-one", "role": "planner"})
    ]
    assert isinstance(receipts[0], MatrixReceipt)
    assert receipts[0].runner_receipt == expected_receipt
    assert receipts[0].runner_receipt["sequence"] == 37


def test_matrix_records_each_attempt_timing_with_injected_clock(monkeypatch) -> None:
    attempts = expand_audition_matrix(
        (CandidateLane("candidate-a", "model-a", "fingerprint-a"),),
        ({"case_id": "case-one", "role": "planner"},),
        repeats=2,
    )
    clock_values = iter((1.0, 2.0, 10.0, 12.5, 20.0, 21.0))

    monkeypatch.setattr(
        matrix,
        "run_local_audition",
        lambda cases, assignments, runner_invoke: [
            _runner_receipt(sequence=1)
        ],
    )

    receipts = run_audition_matrix(
        attempts,
        lambda *_args: {},
        clock=lambda: next(clock_values),
    )

    assert [
        (
            receipt.scheduled_at,
            receipt.started_at,
            receipt.finished_at,
            receipt.queue_duration_seconds,
            receipt.duration_seconds,
            receipt.total_duration_seconds,
        )
        for receipt in receipts
    ] == [
        (1.0, 10.0, 12.5, 9.0, 2.5, 11.5),
        (2.0, 20.0, 21.0, 18.0, 1.0, 19.0),
    ]
