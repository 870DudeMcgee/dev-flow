"""Tests for the multi-workflow Ready Queue (M4-S3)."""

from __future__ import annotations

import pytest

from devflow.control_plane.aggregate import DependencyState
from devflow.control_plane.ready_queue import (
    QueueEntry,
    ReadyQueue,
    admit_to_queue,
    evaluate_admission,
    is_in_queue,
    queue_order,
    queue_size,
    reject_from_queue,
)
from devflow.loop.integration_candidates import CandidateSummary


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _candidate_summary(
    all_verified: bool = True,
    ready: bool = True,
) -> CandidateSummary:
    return CandidateSummary(
        run_id="run-1",
        all_verified=all_verified,
        ready_for_integration=ready,
    )


def _deps(blocked_by: tuple[str, ...] = ()) -> DependencyState:
    return DependencyState(
        ticket_id="t-1",
        depends_on=("t-dep",) if blocked_by else (),
        blocked_by=blocked_by,
    )


# ---------------------------------------------------------------------------
# evaluate_admission tests
# ---------------------------------------------------------------------------

def test_admits_only_gate_passed() -> None:
    """Verified + deps satisfied → admitted."""
    entry = evaluate_admission(
        run_id="run-1",
        ticket_id="t-1",
        candidate_summary=_candidate_summary(all_verified=True, ready=True),
        dependency_state=_deps(blocked_by=()),
    )

    assert entry.admitted is True
    assert "verification" in entry.gates_passed
    assert "integration_ready" in entry.gates_passed
    assert entry.dependencies_satisfied is True
    assert entry.admitted_at is not None


def test_rejects_unverified() -> None:
    """Unverified → not admitted."""
    entry = evaluate_admission(
        run_id="run-1",
        ticket_id="t-1",
        candidate_summary=_candidate_summary(all_verified=False, ready=False),
        dependency_state=_deps(blocked_by=()),
    )

    assert entry.admitted is False
    assert "verification" not in entry.gates_passed
    assert "not all slices verified" in entry.admission_reason


def test_rejects_unsatisfied_deps() -> None:
    """Open dependency → not admitted."""
    entry = evaluate_admission(
        run_id="run-1",
        ticket_id="t-1",
        candidate_summary=_candidate_summary(all_verified=True, ready=True),
        dependency_state=_deps(blocked_by=("t-dep-open",)),
    )

    assert entry.admitted is False
    assert entry.dependencies_satisfied is False
    assert "t-dep-open" in entry.admission_reason


def test_admits_with_no_dependency_state() -> None:
    """No dependency state (None) → admitted if gates pass."""
    entry = evaluate_admission(
        run_id="run-1",
        ticket_id="t-1",
        candidate_summary=_candidate_summary(all_verified=True, ready=True),
        dependency_state=None,
    )

    assert entry.admitted is True


def test_gates_passed_recorded() -> None:
    """Which gates passed is recorded."""
    entry = evaluate_admission(
        run_id="run-1",
        ticket_id="t-1",
        candidate_summary=_candidate_summary(all_verified=True, ready=True),
        dependency_state=_deps(blocked_by=()),
    )

    assert "verification" in entry.gates_passed
    assert "integration_ready" in entry.gates_passed


# ---------------------------------------------------------------------------
# admit_to_queue tests
# ---------------------------------------------------------------------------

def test_admit_returns_new_queue() -> None:
    """Immutable — new queue returned."""
    queue = ReadyQueue()
    entry = QueueEntry(
        run_id="run-1", ticket_id="t-1", admitted=True,
        gates_passed=("verification",), dependencies_satisfied=True,
        admitted_at="2026-01-01T00:00:00Z",
    )

    new_queue = admit_to_queue(queue, entry)

    assert len(queue.entries) == 0  # original unchanged
    assert len(new_queue.entries) == 1


def test_admit_rejects_non_admitted() -> None:
    """Non-admitted entry not added."""
    queue = ReadyQueue()
    entry = QueueEntry(
        run_id="run-1", ticket_id="t-1", admitted=False,
    )

    new_queue = admit_to_queue(queue, entry)

    assert len(new_queue.entries) == 0


def test_admit_replaces_existing() -> None:
    """Existing entry for same run_id is replaced."""
    entry1 = QueueEntry(
        run_id="run-1", ticket_id="t-1", admitted=True,
        gates_passed=("verification",), dependencies_satisfied=True,
        admitted_at="2026-01-01T00:00:00Z",
    )
    queue = ReadyQueue(entries=(entry1,))

    entry2 = QueueEntry(
        run_id="run-1", ticket_id="t-1", admitted=True,
        gates_passed=("verification", "integration_ready"),
        dependencies_satisfied=True,
        admitted_at="2026-01-02T00:00:00Z",
    )
    new_queue = admit_to_queue(queue, entry2)

    assert len(new_queue.entries) == 1
    assert "integration_ready" in new_queue.entries[0].gates_passed


# ---------------------------------------------------------------------------
# queue_order / is_in_queue / queue_size tests
# ---------------------------------------------------------------------------

def test_queue_order_respects_admission() -> None:
    """Admission order preserved."""
    e1 = QueueEntry(run_id="run-1", ticket_id="t-1", admitted=True, admitted_at="2026-01-01")
    e2 = QueueEntry(run_id="run-2", ticket_id="t-2", admitted=True, admitted_at="2026-01-02")
    queue = ReadyQueue(entries=(e1, e2))

    order = queue_order(queue)
    assert order == ("run-1", "run-2")


def test_queue_empty() -> None:
    """Empty queue → empty order."""
    queue = ReadyQueue()
    assert queue_order(queue) == ()
    assert queue_size(queue) == 0


def test_multiple_entries() -> None:
    """Multiple runs queued correctly."""
    entries = (
        QueueEntry(run_id=f"run-{i}", ticket_id=f"t-{i}", admitted=True, admitted_at=f"2026-01-0{i}")
        for i in range(1, 4)
    )
    queue = ReadyQueue(entries=tuple(entries))

    assert queue_size(queue) == 3
    assert len(queue_order(queue)) == 3


def test_is_in_queue() -> None:
    """Check membership."""
    entry = QueueEntry(run_id="run-1", ticket_id="t-1", admitted=True, admitted_at="2026-01-01")
    queue = ReadyQueue(entries=(entry,))

    assert is_in_queue(queue, "run-1") is True
    assert is_in_queue(queue, "run-999") is False


def test_reject_from_queue() -> None:
    """Remove a run from the queue."""
    e1 = QueueEntry(run_id="run-1", ticket_id="t-1", admitted=True, admitted_at="2026-01-01")
    e2 = QueueEntry(run_id="run-2", ticket_id="t-2", admitted=True, admitted_at="2026-01-02")
    queue = ReadyQueue(entries=(e1, e2))

    new_queue = reject_from_queue(queue, "run-1")

    assert queue_size(new_queue) == 1
    assert is_in_queue(new_queue, "run-1") is False
    assert is_in_queue(new_queue, "run-2") is True


# ---------------------------------------------------------------------------
# Immutability tests
# ---------------------------------------------------------------------------

def test_queue_entry_frozen() -> None:
    """QueueEntry is immutable."""
    entry = QueueEntry(run_id="r", ticket_id="t", admitted=False)
    with pytest.raises(Exception):
        entry.admitted = True  # type: ignore[misc]


def test_ready_queue_frozen() -> None:
    """ReadyQueue is immutable."""
    queue = ReadyQueue()
    with pytest.raises(Exception):
        queue.entries = ()  # type: ignore[misc]
