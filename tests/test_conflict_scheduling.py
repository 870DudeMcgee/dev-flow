"""Tests for resource and semantic conflict scheduling (M3-S2)."""

from __future__ import annotations

import pytest

from devflow.loop.conflict_rules import (
    ConflictResult,
    ConflictType,
    ResourceBudget,
    apply_conflict_filters,
    check_file_conflicts,
    check_resource_conflict,
    check_semantic_conflicts,
)
from devflow.loop.dag_scheduler import SchedulerNode


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _n(node_id: str, target_files: tuple[str, ...] = ()) -> SchedulerNode:
    return SchedulerNode(node_id=node_id, target_files=target_files)


# ---------------------------------------------------------------------------
# File conflict tests
# ---------------------------------------------------------------------------

def test_file_conflict_detected() -> None:
    """Overlapping target_files → conflict."""
    candidate = _n("b", target_files=("src/main.py",))
    running = [_n("a", target_files=("src/main.py",))]

    result = check_file_conflicts(candidate, running)

    assert result.has_conflict is True
    assert result.conflict_type == ConflictType.file
    assert "a" in result.conflicting_with


def test_no_file_conflict_disjoint_paths() -> None:
    """Disjoint paths → no conflict."""
    candidate = _n("b", target_files=("src/main.py",))
    running = [_n("a", target_files=("src/utils.py",))]

    result = check_file_conflicts(candidate, running)

    assert result.has_conflict is False


def test_no_file_conflict_empty_targets() -> None:
    """No target_files → no conflict."""
    candidate = _n("b")
    running = [_n("a", target_files=("src/main.py",))]

    result = check_file_conflicts(candidate, running)

    assert result.has_conflict is False


def test_file_conflict_multiple_running() -> None:
    """Conflict with multiple running nodes."""
    candidate = _n("c", target_files=("src/shared.py",))
    running = [
        _n("a", target_files=("src/shared.py",)),
        _n("b", target_files=("src/shared.py", "src/other.py")),
    ]

    result = check_file_conflicts(candidate, running)

    assert result.has_conflict is True
    assert set(result.conflicting_with) == {"a", "b"}


def test_file_conflict_excludes_self() -> None:
    """Candidate doesn't conflict with itself."""
    candidate = _n("a", target_files=("src/main.py",))
    running = [candidate]

    result = check_file_conflicts(candidate, running)

    assert result.has_conflict is False


# ---------------------------------------------------------------------------
# Resource conflict tests
# ---------------------------------------------------------------------------

def test_resource_slot_respected() -> None:
    """Two heavy nodes, 1 slot, 1 in use → serialize."""
    budget = ResourceBudget(heavy_model_slots=1, heavy_model_in_use=1)

    result = check_resource_conflict("node-b", "bounded_coding", budget)

    assert result.has_conflict is True
    assert result.conflict_type == ConflictType.resource


def test_resource_slot_available() -> None:
    """1 heavy running, 2 slots → second allowed."""
    budget = ResourceBudget(heavy_model_slots=2, heavy_model_in_use=1)

    result = check_resource_conflict("node-b", "bounded_coding", budget)

    assert result.has_conflict is False


def test_resource_light_route_never_conflicts() -> None:
    """Light route (cheap_summary) doesn't consume heavy slots."""
    budget = ResourceBudget(heavy_model_slots=0, heavy_model_in_use=0)

    result = check_resource_conflict("node-a", "cheap_summary", budget)

    assert result.has_conflict is False


def test_resource_independent_review_no_conflict() -> None:
    """independent_review is not a heavy route."""
    budget = ResourceBudget(heavy_model_slots=0, heavy_model_in_use=0)

    result = check_resource_conflict("node-a", "independent_review", budget)

    assert result.has_conflict is False


def test_resource_deep_planning_is_heavy() -> None:
    """deep_planning is a heavy route."""
    budget = ResourceBudget(heavy_model_slots=1, heavy_model_in_use=1)

    result = check_resource_conflict("node-a", "deep_planning", budget)

    assert result.has_conflict is True


def test_resource_frontier_judgment_is_heavy() -> None:
    """frontier_judgment is a heavy route."""
    budget = ResourceBudget(heavy_model_slots=1, heavy_model_in_use=1)

    result = check_resource_conflict("node-a", "frontier_judgment", budget)

    assert result.has_conflict is True


# ---------------------------------------------------------------------------
# Semantic conflict tests
# ---------------------------------------------------------------------------

def test_semantic_conflict_detected() -> None:
    """Shared semantic group → wait."""
    candidate = _n("b")
    running = [_n("a")]
    groups = {"api_contract": frozenset({"a", "b"})}

    result = check_semantic_conflicts(candidate, running, groups)

    assert result.has_conflict is True
    assert result.conflict_type == ConflictType.semantic
    assert "a" in result.conflicting_with


def test_semantic_conflict_none_when_group_empty() -> None:
    """No groups → no conflict."""
    candidate = _n("b")
    running = [_n("a")]

    result = check_semantic_conflicts(candidate, running, {})

    assert result.has_conflict is False


def test_semantic_conflict_different_groups() -> None:
    """Nodes in different groups → no conflict."""
    candidate = _n("b")
    running = [_n("a")]
    groups = {"group1": frozenset({"a"}), "group2": frozenset({"b"})}

    result = check_semantic_conflicts(candidate, running, groups)

    assert result.has_conflict is False


def test_semantic_conflict_no_running_in_group() -> None:
    """Candidate in a group but no running member → no conflict."""
    candidate = _n("b")
    running = [_n("c")]  # c is not in the group
    groups = {"api_contract": frozenset({"a", "b"})}

    result = check_semantic_conflicts(candidate, running, groups)

    assert result.has_conflict is False


def test_semantic_conflict_not_in_any_group() -> None:
    """Candidate not in any group → no conflict."""
    candidate = _n("c")
    running = [_n("a")]
    groups = {"api_contract": frozenset({"a", "b"})}

    result = check_semantic_conflicts(candidate, running, groups)

    assert result.has_conflict is False


# ---------------------------------------------------------------------------
# apply_conflict_filters tests
# ---------------------------------------------------------------------------

def test_apply_filters_all_clear() -> None:
    """No conflicts → all pass."""
    ready = ("a", "b")
    all_nodes = {"a": _n("a", ("f1",)), "b": _n("b", ("f2",))}
    budget = ResourceBudget(heavy_model_slots=2)
    routes = {"a": "bounded_coding", "b": "bounded_coding"}

    result = apply_conflict_filters(ready, all_nodes, [], budget, routes)

    assert set(result) == {"a", "b"}


def test_apply_filters_file_conflict() -> None:
    """File conflict removes node from schedulable set."""
    ready = ("a", "b")
    all_nodes = {"a": _n("a", ("shared.py",)), "b": _n("b", ("shared.py",))}
    running = [_n("a", ("shared.py",))]
    budget = ResourceBudget()
    routes = {"a": "bounded_coding", "b": "bounded_coding"}

    result = apply_conflict_filters(ready, all_nodes, running, budget, routes)

    assert "b" not in result  # b conflicts with running a


def test_apply_filters_resource_conflict() -> None:
    """Resource conflict removes node."""
    ready = ("a", "b")
    all_nodes = {"a": _n("a"), "b": _n("b")}
    budget = ResourceBudget(heavy_model_slots=1, heavy_model_in_use=1)
    routes = {"a": "cheap_summary", "b": "bounded_coding"}

    result = apply_conflict_filters(ready, all_nodes, [], budget, routes)

    assert "b" not in result  # heavy slot exhausted


def test_apply_filters_semantic_conflict() -> None:
    """Semantic conflict removes node."""
    ready = ("a", "b")
    all_nodes = {"a": _n("a"), "b": _n("b")}
    budget = ResourceBudget(heavy_model_slots=2)
    routes = {"a": "cheap_summary", "b": "cheap_summary"}
    running = [_n("a")]
    groups = {"api_contract": frozenset({"a", "b"})}

    result = apply_conflict_filters(ready, all_nodes, running, budget, routes, groups)

    assert "b" not in result  # semantic conflict with running a


def test_apply_filters_stable_order() -> None:
    """Results preserve the input ready-set order from the DAG scheduler."""
    ready = ("a", "b", "c")
    all_nodes = {nid: _n(nid) for nid in ("a", "b", "c")}
    budget = ResourceBudget(heavy_model_slots=4)
    routes = {nid: "cheap_summary" for nid in ("a", "b", "c")}

    result = apply_conflict_filters(ready, all_nodes, [], budget, routes)

    assert result == ("a", "b", "c")


def test_apply_filters_empty_ready() -> None:
    """Empty ready set → empty result."""
    result = apply_conflict_filters(
        [], {}, [], ResourceBudget(), {}
    )
    assert result == ()


def test_conflict_result_frozen() -> None:
    """ConflictResult is immutable."""
    result = ConflictResult(node_id="a", has_conflict=False)
    with pytest.raises(Exception):
        result.has_conflict = True  # type: ignore[misc]


def test_resource_budget_frozen() -> None:
    """ResourceBudget is immutable."""
    budget = ResourceBudget()
    with pytest.raises(Exception):
        budget.heavy_model_slots = 2  # type: ignore[misc]


def test_resource_budget_validates_range() -> None:
    """Budget fields enforce ranges."""
    with pytest.raises(Exception):
        ResourceBudget(heavy_model_slots=5)
    with pytest.raises(Exception):
        ResourceBudget(heavy_model_slots=-1)


# ---------------------------------------------------------------------------
# Adversarial RED tests: trust-binding vulnerabilities (M3-S2)
# ---------------------------------------------------------------------------

def test_apply_filters_resource_not_overbooked() -> None:
    """Two heavy ready nodes, 1 free slot → only one admitted, never both.

    Capacity is a *running total*, not a per-node independent check. With
    1 heavy slot and 0 in use, two heavy-route ready nodes must not both pass:
    admitting both would overbook the single slot. Exactly one (the first in
    stable order) must be admitted.
    """
    ready = ("a", "b")
    all_nodes = {"a": _n("a"), "b": _n("b")}
    budget = ResourceBudget(heavy_model_slots=1, heavy_model_in_use=0)
    routes = {"a": "bounded_coding", "b": "bounded_coding"}

    result = apply_conflict_filters(ready, all_nodes, [], budget, routes)

    assert len(result) == 1
    assert "a" in result


def test_apply_filters_heavy_slot_freed_after_semantic_reject() -> None:
    """Heavy node reserved a slot then semantically rejected → slot freed for next heavy node.

    With 1 heavy slot, node 'a' (heavy) is in a semantic group with a running
    node and gets rejected. The reserved slot must roll back so node 'b' (also
    heavy) can be admitted. This proves the rollback path in
    apply_conflict_filters is exercised, not just the forward reservation.
    """
    ready = ("a", "b")
    all_nodes = {"a": _n("a"), "b": _n("b")}
    running = [_n("c")]  # 'c' is running and in the same semantic group as 'a'
    budget = ResourceBudget(heavy_model_slots=1, heavy_model_in_use=0)
    routes = {"a": "bounded_coding", "b": "bounded_coding"}
    groups = {"shared": frozenset({"a", "c"})}

    result = apply_conflict_filters(ready, all_nodes, running, budget, routes, groups)

    # 'a' is rejected by semantic conflict (shares group with running 'c').
    # Its reserved heavy slot must roll back, allowing 'b' to be admitted.
    assert "a" not in result
    assert "b" in result
    assert len(result) == 1
