"""Per-run phase DAG scheduler (M3-S1).

Computes ready sets from workflow-node dependency edges and per-node lifecycle
states. This is the generalized scheduler that works on any DAG of workflow
nodes using :class:`~devflow.loop.node_lifecycle.NodeState` — it is distinct
from :mod:`~devflow.loop.packet_dag`, which operates on file-producing build
packets using :class:`~devflow.loop.packet_dag.PacketState`.

The two coexist: ``packet_dag`` remains the packet-level ready-set authority;
``dag_scheduler`` is the workflow-node-level scheduler.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field
from typing import Mapping, Sequence

from devflow.loop.node_lifecycle import NodeState

# States that block a node from being scheduled (not ready to advance).
_NON_SCHEDULABLE: frozenset[NodeState] = frozenset({
    NodeState.running,
    NodeState.verified,
    NodeState.failed,
    NodeState.cancelled,
    NodeState.awaiting_gate,
    NodeState.blocked,
})


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

class SchedulerNode(BaseModel):
    """One node in the scheduler's view of a workflow DAG."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    node_id: str = Field(min_length=1)
    depends_on: tuple[str, ...] = ()
    target_files: tuple[str, ...] = ()  # for file-conflict detection (M3-S2)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_dag(nodes: Sequence[SchedulerNode]) -> tuple[SchedulerNode, ...]:
    """Validate unique IDs, known deps, no cycles. Return stable ID-sorted order.

    Raises ``ValueError`` on:
    - Duplicate node IDs
    - Dependencies referencing unknown nodes
    - Self-dependencies
    - Cycles
    """
    by_id: dict[str, SchedulerNode] = {}
    for node in nodes:
        if node.node_id in by_id:
            raise ValueError(f"duplicate scheduler node id: {node.node_id!r}")
        by_id[node.node_id] = node

    known = set(by_id)
    for node in nodes:
        if node.node_id in node.depends_on:
            raise ValueError(f"node {node.node_id!r} depends on itself")
        unknown = set(node.depends_on) - known
        if unknown:
            raise ValueError(
                f"node {node.node_id!r} has unknown dependencies: {sorted(unknown)!r}"
            )

    # Cycle detection (topological sort)
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node_id: str) -> None:
        if node_id in visiting:
            raise ValueError("scheduler DAG contains a cycle")
        if node_id in visited:
            return
        visiting.add(node_id)
        for dep in by_id[node_id].depends_on:
            visit(dep)
        visiting.remove(node_id)
        visited.add(node_id)

    for node_id in sorted(by_id):
        visit(node_id)

    return tuple(by_id[node_id] for node_id in sorted(by_id))


# ---------------------------------------------------------------------------
# Ready-set computation
# ---------------------------------------------------------------------------

def compute_ready_set(
    nodes: Sequence[SchedulerNode],
    states: Mapping[str, NodeState],
) -> tuple[str, ...]:
    """Return node_ids whose dependencies are all verified and that are schedulable.

    A node is *schedulable* when its state is ``planned`` or ``ready`` (not
    running/terminal/blocked). A node is *ready* when all of its
    ``depends_on`` nodes are in ``verified`` state.

    Returns node IDs in stable (sorted) order.
    """
    ordered = validate_dag(nodes)

    # Validate state coverage
    expected_ids = {n.node_id for n in ordered}
    missing = expected_ids - set(states)
    if missing:
        raise ValueError(
            f"scheduler states missing for nodes: {sorted(missing)!r}"
        )

    result: list[str] = []
    for node in ordered:
        state = states.get(node.node_id)
        if state is None:
            continue
        # Must be in a schedulable state
        if state in _NON_SCHEDULABLE:
            continue
        # Only planned/ready states can be scheduled
        if state not in (NodeState.planned, NodeState.ready):
            continue
        # All dependencies must be verified
        deps_satisfied = all(
            states.get(dep) == NodeState.verified
            for dep in node.depends_on
        )
        if deps_satisfied:
            result.append(node.node_id)

    return tuple(result)


def can_advance(
    node_id: str,
    nodes: Sequence[SchedulerNode],
    states: Mapping[str, NodeState],
) -> bool:
    """True if a single node's dependencies are satisfied and it's schedulable.

    Convenience wrapper around :func:`compute_ready_set` for a single node.
    """
    ready = compute_ready_set(nodes, states)
    return node_id in ready


def terminal_nodes(
    states: Mapping[str, NodeState],
) -> tuple[str, ...]:
    """Return node_ids that are in a terminal state (verified/failed/cancelled)."""
    return tuple(
        node_id
        for node_id, state in sorted(states.items())
        if state in (NodeState.verified, NodeState.failed, NodeState.cancelled)
    )


def is_dag_complete(
    nodes: Sequence[SchedulerNode],
    states: Mapping[str, NodeState],
) -> bool:
    """True when every node is in a terminal state."""
    for node in nodes:
        state = states.get(node.node_id)
        if state not in (NodeState.verified, NodeState.failed, NodeState.cancelled):
            return False
    return True


__all__ = [
    "SchedulerNode",
    "can_advance",
    "compute_ready_set",
    "is_dag_complete",
    "terminal_nodes",
    "validate_dag",
]
