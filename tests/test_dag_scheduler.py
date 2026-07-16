"""Tests for the per-run phase DAG scheduler (M3-S1)."""

from __future__ import annotations

import pytest

from devflow.loop.dag_scheduler import (
    SchedulerNode,
    can_advance,
    compute_ready_set,
    is_dag_complete,
    terminal_nodes,
    validate_dag,
)
from devflow.loop.node_lifecycle import NodeState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _n(node_id: str, depends_on: tuple[str, ...] = (), target_files: tuple[str, ...] = ()) -> SchedulerNode:
    return SchedulerNode(node_id=node_id, depends_on=depends_on, target_files=target_files)


def _states(**kwargs: NodeState) -> dict[str, NodeState]:
    return dict(kwargs)


# ---------------------------------------------------------------------------
# validate_dag tests
# ---------------------------------------------------------------------------

def test_validate_dag_rejects_cycle() -> None:
    """Cycle → ValueError."""
    nodes = (
        _n("a", depends_on=("c",)),
        _n("b", depends_on=("a",)),
        _n("c", depends_on=("b",)),
    )
    with pytest.raises(ValueError, match="cycle"):
        validate_dag(nodes)


def test_validate_dag_rejects_unknown_dep() -> None:
    """Unknown dependency → ValueError."""
    nodes = (_n("a", depends_on=("nonexistent",)),)
    with pytest.raises(ValueError, match="unknown dependencies"):
        validate_dag(nodes)


def test_validate_dag_rejects_duplicate_ids() -> None:
    """Duplicate node IDs → ValueError."""
    nodes = (_n("a"), _n("a"))
    with pytest.raises(ValueError, match="duplicate"):
        validate_dag(nodes)


def test_validate_dag_rejects_self_dependency() -> None:
    """Self-dependency → ValueError."""
    nodes = (_n("a", depends_on=("a",)),)
    with pytest.raises(ValueError, match="depends on itself"):
        validate_dag(nodes)


def test_validate_dag_returns_sorted() -> None:
    """validate_dag returns nodes in stable ID-sorted order."""
    nodes = (_n("c"), _n("a"), _n("b"))
    ordered = validate_dag(nodes)
    assert [n.node_id for n in ordered] == ["a", "b", "c"]


def test_validate_dag_empty() -> None:
    """Empty sequence → empty tuple."""
    assert validate_dag(()) == ()


# ---------------------------------------------------------------------------
# compute_ready_set tests
# ---------------------------------------------------------------------------

def test_ready_set_respects_edges() -> None:
    """A→B→C: only A ready initially."""
    nodes = (_n("a"), _n("b", depends_on=("a",)), _n("c", depends_on=("b",)))
    states = _states(a=NodeState.planned, b=NodeState.planned, c=NodeState.planned)

    ready = compute_ready_set(nodes, states)
    assert ready == ("a",)


def test_ready_set_after_a_verified() -> None:
    """A verified → B ready."""
    nodes = (_n("a"), _n("b", depends_on=("a",)), _n("c", depends_on=("b",)))
    states = _states(a=NodeState.verified, b=NodeState.planned, c=NodeState.planned)

    ready = compute_ready_set(nodes, states)
    assert ready == ("b",)


def test_ready_set_parallel_branches() -> None:
    """A→{B,C}: B and C both ready after A verified."""
    nodes = (
        _n("a"),
        _n("b", depends_on=("a",)),
        _n("c", depends_on=("a",)),
    )
    states = _states(a=NodeState.verified, b=NodeState.planned, c=NodeState.planned)

    ready = compute_ready_set(nodes, states)
    assert set(ready) == {"b", "c"}


def test_ready_set_empty_when_all_terminal() -> None:
    """All verified → empty ready set."""
    nodes = (_n("a"), _n("b", depends_on=("a",)))
    states = _states(a=NodeState.verified, b=NodeState.verified)

    ready = compute_ready_set(nodes, states)
    assert ready == ()


def test_ready_set_excludes_blocked() -> None:
    """Blocked node not in ready set."""
    nodes = (_n("a"), _n("b", depends_on=("a",)))
    states = _states(a=NodeState.verified, b=NodeState.blocked)

    ready = compute_ready_set(nodes, states)
    assert ready == ()


def test_ready_set_excludes_running() -> None:
    """Running node not in ready set."""
    nodes = (_n("a"),)
    states = _states(a=NodeState.running)

    ready = compute_ready_set(nodes, states)
    assert ready == ()


def test_ready_set_excludes_failed() -> None:
    """Failed node not in ready set."""
    nodes = (_n("a"),)
    states = _states(a=NodeState.failed)

    ready = compute_ready_set(nodes, states)
    assert ready == ()


def test_ready_set_includes_ready_state() -> None:
    """Nodes in 'ready' state are schedulable (same as 'planned')."""
    nodes = (_n("a"),)
    states = _states(a=NodeState.ready)

    ready = compute_ready_set(nodes, states)
    assert ready == ("a",)


def test_ready_set_stable_order() -> None:
    """Multiple ready nodes returned in sorted order."""
    nodes = (_n("c"), _n("b"), _n("a"))
    states = _states(a=NodeState.planned, b=NodeState.planned, c=NodeState.planned)

    ready = compute_ready_set(nodes, states)
    assert ready == ("a", "b", "c")


def test_diamond_dependency() -> None:
    """A→B,C→D: D ready only after B AND C verified."""
    nodes = (
        _n("a"),
        _n("b", depends_on=("a",)),
        _n("c", depends_on=("a",)),
        _n("d", depends_on=("b", "c")),
    )
    # After A verified, B and C are ready
    states = _states(
        a=NodeState.verified, b=NodeState.planned,
        c=NodeState.planned, d=NodeState.planned,
    )
    ready = compute_ready_set(nodes, states)
    assert set(ready) == {"b", "c"}

    # After B verified but C still planned, D not ready yet
    states2 = _states(
        a=NodeState.verified, b=NodeState.verified,
        c=NodeState.planned, d=NodeState.planned,
    )
    ready2 = compute_ready_set(nodes, states2)
    assert ready2 == ("c",)

    # After both B and C verified, D is ready
    states3 = _states(
        a=NodeState.verified, b=NodeState.verified,
        c=NodeState.verified, d=NodeState.planned,
    )
    ready3 = compute_ready_set(nodes, states3)
    assert ready3 == ("d",)


def test_ready_set_missing_states_raises() -> None:
    """Missing state for a node → ValueError."""
    nodes = (_n("a"), _n("b", depends_on=("a",)))
    states = _states(a=NodeState.planned)  # missing b

    with pytest.raises(ValueError, match="missing for nodes"):
        compute_ready_set(nodes, states)


# ---------------------------------------------------------------------------
# can_advance tests
# ---------------------------------------------------------------------------

def test_can_advance_single_node() -> None:
    """can_advance true when deps met."""
    nodes = (_n("a"), _n("b", depends_on=("a",)))
    states = _states(a=NodeState.verified, b=NodeState.planned)

    assert can_advance("b", nodes, states) is True


def test_can_advance_false_when_dep_pending() -> None:
    """can_advance false when dep not verified."""
    nodes = (_n("a"), _n("b", depends_on=("a",)))
    states = _states(a=NodeState.planned, b=NodeState.planned)

    assert can_advance("b", nodes, states) is False


def test_can_advance_false_when_terminal() -> None:
    """Terminal node → can't advance."""
    nodes = (_n("a"),)
    states = _states(a=NodeState.verified)

    assert can_advance("a", nodes, states) is False


def test_can_advance_false_when_running() -> None:
    """Running node → can't advance."""
    nodes = (_n("a"),)
    states = _states(a=NodeState.running)

    assert can_advance("a", nodes, states) is False


# ---------------------------------------------------------------------------
# terminal_nodes / is_dag_complete tests
# ---------------------------------------------------------------------------

def test_terminal_nodes() -> None:
    """terminal_nodes returns verified/failed/cancelled."""
    states = _states(
        a=NodeState.verified,
        b=NodeState.failed,
        c=NodeState.cancelled,
        d=NodeState.running,
        e=NodeState.planned,
    )
    terminals = terminal_nodes(states)
    assert set(terminals) == {"a", "b", "c"}


def test_is_dag_complete_true() -> None:
    """All nodes terminal → complete."""
    nodes = (_n("a"), _n("b", depends_on=("a",)))
    states = _states(a=NodeState.verified, b=NodeState.verified)

    assert is_dag_complete(nodes, states) is True


def test_is_dag_complete_false() -> None:
    """Some nodes not terminal → not complete."""
    nodes = (_n("a"), _n("b", depends_on=("a",)))
    states = _states(a=NodeState.verified, b=NodeState.planned)

    assert is_dag_complete(nodes, states) is False
