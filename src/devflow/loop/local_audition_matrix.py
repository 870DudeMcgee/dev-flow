"""Immutable atomic matrix expansion and per-candidate audition scheduling."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
import json
import time
from typing import Callable, Mapping, Sequence

from .local_audition_runner import run_local_audition


def _require_nonblank(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a nonblank string")


def _require_positive_integer(name: str, value: object) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")


@dataclass(frozen=True, slots=True)
class CandidateLane:
    """One frozen candidate identity and artifact fingerprint."""

    candidate_id: str
    expected_model: str
    fingerprint: str

    def __post_init__(self) -> None:
        _require_nonblank("candidate_id", self.candidate_id)
        _require_nonblank("expected_model", self.expected_model)
        _require_nonblank("fingerprint", self.fingerprint)


@dataclass(frozen=True, slots=True)
class AtomicAttempt:
    """One immutable model x role x case x repeat x fingerprint attempt."""

    sequence: int
    candidate_id: str
    expected_model: str
    role: str
    case_id: str
    repeat: int
    fingerprint: str
    case_json: str = field(repr=False)

    def __post_init__(self) -> None:
        _require_positive_integer("sequence", self.sequence)
        _require_positive_integer("repeat", self.repeat)
        _require_nonblank("candidate_id", self.candidate_id)
        _require_nonblank("expected_model", self.expected_model)
        _require_nonblank("role", self.role)
        _require_nonblank("case_id", self.case_id)
        _require_nonblank("fingerprint", self.fingerprint)
        _require_nonblank("case_json", self.case_json)
        try:
            case = json.loads(self.case_json)
        except (TypeError, ValueError) as exc:
            raise ValueError("case_json must contain valid JSON") from exc
        if not isinstance(case, dict):
            raise ValueError("case_json must encode an object")
        if case.get("case_id") != self.case_id or case.get("role") != self.role:
            raise ValueError("case_json identity must match the atomic attempt")

    def case_data(self) -> dict:
        """Return a fresh mutable copy of the canonical case payload."""
        return json.loads(self.case_json)


@dataclass(frozen=True, slots=True)
class MatrixReceipt:
    """Matrix metadata wrapped around an unchanged serial-runner receipt."""

    attempt: AtomicAttempt
    runner_receipt: dict
    scheduled_at: float
    started_at: float
    finished_at: float
    queue_duration_seconds: float
    duration_seconds: float
    total_duration_seconds: float


def _canonical_case(case: Mapping) -> tuple[str, str, str]:
    if not isinstance(case, Mapping):
        raise ValueError("cases must contain mappings")
    case_copy = dict(case)
    case_id = case_copy.get("case_id")
    role = case_copy.get("role")
    _require_nonblank("case_id", case_id)
    _require_nonblank("role", role)
    try:
        encoded = json.dumps(
            case_copy,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("case data must be JSON serializable") from exc
    return encoded, case_id, role


def expand_audition_matrix(
    candidates: Sequence[CandidateLane],
    cases: Sequence[Mapping],
    repeats: int = 3,
) -> tuple[AtomicAttempt, ...]:
    """Expand candidates and cases in stable candidate/case/repeat order."""
    _require_positive_integer("repeats", repeats)
    candidate_list = tuple(candidates)
    case_list = tuple(_canonical_case(case) for case in cases)
    seen_candidates: set[str] = set()

    for candidate in candidate_list:
        if not isinstance(candidate, CandidateLane):
            raise ValueError("candidates must contain CandidateLane values")
        if candidate.candidate_id in seen_candidates:
            raise ValueError(f"duplicate candidate: {candidate.candidate_id}")
        seen_candidates.add(candidate.candidate_id)

    attempts: list[AtomicAttempt] = []
    sequence = 1
    for candidate in candidate_list:
        for case_json, case_id, role in case_list:
            for repeat in range(1, repeats + 1):
                attempts.append(
                    AtomicAttempt(
                        sequence=sequence,
                        candidate_id=candidate.candidate_id,
                        expected_model=candidate.expected_model,
                        role=role,
                        case_id=case_id,
                        repeat=repeat,
                        fingerprint=candidate.fingerprint,
                        case_json=case_json,
                    )
                )
                sequence += 1
    return tuple(attempts)


def run_audition_matrix(
    attempts: Sequence[AtomicAttempt],
    invoke: Callable[[AtomicAttempt, str, dict], Mapping],
    max_workers: int | None = None,
    clock: Callable[[], float] = time.time,
) -> tuple[MatrixReceipt, ...]:
    """Run candidates concurrently while serializing attempts within each lane."""
    attempt_list = tuple(attempts)
    if any(not isinstance(attempt, AtomicAttempt) for attempt in attempt_list):
        raise ValueError("attempts must contain AtomicAttempt values")
    sequences = [attempt.sequence for attempt in attempt_list]
    if len(sequences) != len(set(sequences)):
        raise ValueError("attempt sequences must be unique")
    if max_workers is not None:
        _require_positive_integer("max_workers", max_workers)
    if not attempt_list:
        return ()
    scheduled_at = {attempt.sequence: clock() for attempt in attempt_list}

    grouped: dict[str, list[AtomicAttempt]] = {}
    lane_identities: dict[str, tuple[str, str]] = {}
    for attempt in attempt_list:
        identity = (attempt.expected_model, attempt.fingerprint)
        previous = lane_identities.setdefault(attempt.candidate_id, identity)
        if previous != identity:
            raise ValueError("candidate attempts must share model and fingerprint")
        grouped.setdefault(attempt.candidate_id, []).append(attempt)

    def run_candidate(candidate_attempts: list[AtomicAttempt]) -> list[MatrixReceipt]:
        candidate_receipts: list[MatrixReceipt] = []
        for attempt in candidate_attempts:
            case = attempt.case_data()

            def invoke_attempt(model: str, runner_case: dict) -> Mapping:
                return invoke(attempt, model, runner_case)

            started_at = clock()
            runner_receipt = run_local_audition(
                [case],
                {attempt.role: attempt.expected_model},
                invoke_attempt,
            )[0]
            finished_at = clock()
            candidate_receipts.append(
                MatrixReceipt(
                    attempt=attempt,
                    runner_receipt=runner_receipt,
                    scheduled_at=scheduled_at[attempt.sequence],
                    started_at=started_at,
                    finished_at=finished_at,
                    queue_duration_seconds=max(
                        0.0, started_at - scheduled_at[attempt.sequence]
                    ),
                    duration_seconds=max(0.0, finished_at - started_at),
                    total_duration_seconds=max(
                        0.0, finished_at - scheduled_at[attempt.sequence]
                    ),
                )
            )
        return candidate_receipts

    worker_count = max_workers if max_workers is not None else len(grouped)
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = [
            executor.submit(run_candidate, candidate_attempts)
            for candidate_attempts in grouped.values()
        ]
        receipts = [receipt for future in futures for receipt in future.result()]
    return tuple(sorted(receipts, key=lambda receipt: receipt.attempt.sequence))


__all__ = [
    "AtomicAttempt",
    "CandidateLane",
    "MatrixReceipt",
    "expand_audition_matrix",
    "run_audition_matrix",
]
