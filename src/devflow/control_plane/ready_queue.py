"""Multi-workflow Ready Queue (M4-S3).

Admits workflows to integration only when required gates pass and declared
ticket dependencies are satisfied. This is the bridge between single-run
execution (M3-S1 per-run ready set) and project-level workflow management.

Distinct from ``packet_dag.py`` per-run ready set: the Ready Queue operates
across multiple runs/tickets, not within one run's packet DAG.

No autonomous promotion — the queue tracks readiness; merge/ship remain
human-gated (M4-S6).
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

from pydantic import BaseModel, ConfigDict, Field

from devflow.control_plane.aggregate import DependencyState, TicketStatus
from devflow.loop.integration_candidates import CandidateSummary

_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

class QueueEntry(BaseModel):
    """One run's admission status in the Ready Queue."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str = Field(min_length=1)
    ticket_id: str = Field(min_length=1)
    admitted: bool = False
    gates_passed: tuple[str, ...] = ()
    dependencies_satisfied: bool = False
    admission_reason: str = ""
    admitted_at: str | None = None


class ReadyQueue(BaseModel):
    """Immutable snapshot of the Ready Queue."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    entries: tuple[QueueEntry, ...] = ()


# ---------------------------------------------------------------------------
# Admission evaluation
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def evaluate_admission(
    run_id: str,
    ticket_id: str,
    candidate_summary: CandidateSummary,
    dependency_state: DependencyState | None,
) -> QueueEntry:
    """Evaluate whether a run qualifies for the Ready Queue.

    Admission rules:
    1. ``candidate_summary.all_verified`` must be True
    2. ``candidate_summary.ready_for_integration`` must be True
    3. All ticket dependencies must be satisfied (no unresolved ``blocked_by``)

    Returns a :class:`QueueEntry` with ``admitted`` reflecting the result.
    """
    gates: list[str] = []
    reasons: list[str] = []

    # Gate 1: all slices verified
    if candidate_summary.all_verified:
        gates.append("verification")
    else:
        reasons.append("not all slices verified")

    # Gate 2: ready for integration
    if candidate_summary.ready_for_integration:
        gates.append("integration_ready")
    else:
        reasons.append("integration not ready")

    # Gate 3: dependencies satisfied
    deps_satisfied = True
    if dependency_state is not None and dependency_state.blocked_by:
        deps_satisfied = False
        reasons.append(
            f"blocked by unresolved dependencies: {', '.join(dependency_state.blocked_by)}"
        )

    admitted = len(reasons) == 0

    return QueueEntry(
        run_id=run_id,
        ticket_id=ticket_id,
        admitted=admitted,
        gates_passed=tuple(gates),
        dependencies_satisfied=deps_satisfied,
        admission_reason="; ".join(reasons) if reasons else "all gates passed",
        admitted_at=_now_iso() if admitted else None,
    )


# ---------------------------------------------------------------------------
# Queue operations
# ---------------------------------------------------------------------------

def admit_to_queue(queue: ReadyQueue, entry: QueueEntry) -> ReadyQueue:
    """Return a new ReadyQueue with the entry added (if admitted).

    Non-admitted entries are not added. Existing entries for the same run_id
    are replaced (the queue keeps only the latest evaluation per run).
    """
    if not entry.admitted:
        return queue

    # Remove any existing entry for the same run_id (replace with latest)
    filtered = tuple(
        e for e in queue.entries if e.run_id != entry.run_id
    )
    return ReadyQueue(entries=filtered + (entry,))


def reject_from_queue(queue: ReadyQueue, run_id: str) -> ReadyQueue:
    """Remove a run from the queue (e.g., after cancellation)."""
    return ReadyQueue(
        entries=tuple(e for e in queue.entries if e.run_id != run_id)
    )


def queue_order(queue: ReadyQueue) -> tuple[str, ...]:
    """Return run_ids in admission order (oldest first).

    This respects dependency order implicitly: dependencies must be satisfied
    before admission, so admitted runs are already in a valid order.
    """
    return tuple(e.run_id for e in queue.entries)


def is_in_queue(queue: ReadyQueue, run_id: str) -> bool:
    """Check if a run_id is currently in the queue."""
    return any(e.run_id == run_id for e in queue.entries)


def queue_size(queue: ReadyQueue) -> int:
    """Number of admitted entries."""
    return len(queue.entries)


__all__ = [
    "QueueEntry",
    "ReadyQueue",
    "admit_to_queue",
    "evaluate_admission",
    "is_in_queue",
    "queue_order",
    "queue_size",
    "reject_from_queue",
]
