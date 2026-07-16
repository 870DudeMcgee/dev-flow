"""Resource and semantic conflict scheduling rules (M3-S2).

Blueprint §7.5 conflict-aware parallelism. These rules are **additive filters**
on the ready set produced by :mod:`~devflow.loop.dag_scheduler`. They detect:

- **File conflicts**: nodes with overlapping ``target_files`` serialize or use
  separate worktrees.
- **Resource conflicts**: nodes needing the same ``heavy_model_slot`` serialize
  when slots are exhausted.
- **Semantic conflicts**: nodes sharing an unfrozen design decision/schema/API
  contract wait until the shared decision is frozen.

Dependency conflicts are handled by the DAG scheduler (M3-S1), not here.
"""

from __future__ import annotations

from enum import Enum
from typing import Mapping, Sequence

from pydantic import BaseModel, ConfigDict, Field

from devflow.loop.dag_scheduler import SchedulerNode


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

class ConflictType(str, Enum):
    """The four conflict types from blueprint §7.5."""

    dependency = "dependency"  # handled by dag_scheduler, not here
    file = "file"
    resource = "resource"
    semantic = "semantic"


# Routes that consume a heavy model slot when resident.
_HEAVY_ROUTES: frozenset[str] = frozenset({
    "deep_planning",
    "bounded_coding",
    "frontier_judgment",
})


class ConflictResult(BaseModel):
    """Result of checking conflicts for a candidate ready node."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    node_id: str
    has_conflict: bool
    conflict_type: ConflictType | None = None
    conflicting_with: tuple[str, ...] = ()
    reason: str = ""


class ResourceBudget(BaseModel):
    """Available resources for scheduling decisions."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    heavy_model_slots: int = Field(default=1, ge=0, le=4)
    heavy_model_in_use: int = Field(default=0, ge=0, le=4)


# ---------------------------------------------------------------------------
# Individual conflict checks
# ---------------------------------------------------------------------------

def check_file_conflicts(
    candidate: SchedulerNode,
    running_nodes: Sequence[SchedulerNode],
) -> ConflictResult:
    """Check if candidate's ``target_files`` overlap with any running node's.

    Two nodes writing the same file path must serialize or use separate
    worktrees. This check returns a conflict when overlapping paths are
    detected against currently-running nodes.
    """
    candidate_paths = set(candidate.target_files)
    if not candidate_paths:
        return ConflictResult(node_id=candidate.node_id, has_conflict=False)

    conflicting: list[str] = []
    for running in running_nodes:
        if running.node_id == candidate.node_id:
            continue
        overlap = candidate_paths & set(running.target_files)
        if overlap:
            conflicting.append(running.node_id)

    if conflicting:
        return ConflictResult(
            node_id=candidate.node_id,
            has_conflict=True,
            conflict_type=ConflictType.file,
            conflicting_with=tuple(conflicting),
            reason=f"target_files overlap with running node(s): {', '.join(conflicting)}",
        )
    return ConflictResult(node_id=candidate.node_id, has_conflict=False)


def check_resource_conflict(
    candidate_node_id: str,
    candidate_route: str,
    budget: ResourceBudget,
) -> ConflictResult:
    """Check if a heavy-route candidate exceeds available ``heavy_model_slots``.

    Light routes (repository_analysis, independent_review, cheap_summary) do
    not consume heavy slots and always pass.
    """
    if candidate_route not in _HEAVY_ROUTES:
        return ConflictResult(node_id=candidate_node_id, has_conflict=False)

    available = budget.heavy_model_slots - budget.heavy_model_in_use
    if available <= 0:
        return ConflictResult(
            node_id=candidate_node_id,
            has_conflict=True,
            conflict_type=ConflictType.resource,
            reason=(
                f"heavy model slot exhausted: {budget.heavy_model_in_use}/"
                f"{budget.heavy_model_slots} in use"
            ),
        )
    return ConflictResult(node_id=candidate_node_id, has_conflict=False)


def check_semantic_conflicts(
    candidate: SchedulerNode,
    running_nodes: Sequence[SchedulerNode],
    semantic_groups: Mapping[str, frozenset[str]],
) -> ConflictResult:
    """Check if candidate shares an unfrozen semantic group with running nodes.

    ``semantic_groups`` maps group name → set of node IDs that share a design
    decision, schema, or API contract. When two nodes in the same group are
    running concurrently, the second must wait — they depend on a shared
    decision that is not yet frozen (blueprint §7.5 semantic conflict).
    """
    if not semantic_groups:
        return ConflictResult(node_id=candidate.node_id, has_conflict=False)

    # Find which groups the candidate belongs to
    candidate_groups = {
        group_name
        for group_name, members in semantic_groups.items()
        if candidate.node_id in members
    }
    if not candidate_groups:
        return ConflictResult(node_id=candidate.node_id, has_conflict=False)

    # Check if any running node shares a group
    running_ids = {n.node_id for n in running_nodes}
    conflicting: list[str] = []
    for group_name in candidate_groups:
        members = semantic_groups[group_name]
        overlap = (members & running_ids) - {candidate.node_id}
        conflicting.extend(sorted(overlap))

    if conflicting:
        return ConflictResult(
            node_id=candidate.node_id,
            has_conflict=True,
            conflict_type=ConflictType.semantic,
            conflicting_with=tuple(conflicting),
            reason=f"shares unfrozen semantic group with: {', '.join(conflicting)}",
        )
    return ConflictResult(node_id=candidate.node_id, has_conflict=False)


# ---------------------------------------------------------------------------
# Combined filter
# ---------------------------------------------------------------------------

def apply_conflict_filters(
    ready_nodes: Sequence[str],
    all_nodes: Mapping[str, SchedulerNode],
    running_nodes: Sequence[SchedulerNode],
    budget: ResourceBudget,
    node_routes: Mapping[str, str],
    semantic_groups: Mapping[str, frozenset[str]] | None = None,
) -> tuple[str, ...]:
    """Filter a ready set through file, resource, and semantic conflict rules.

    Parameters
    ----------
    ready_nodes
        Node IDs from :func:`~devflow.loop.dag_scheduler.compute_ready_set`.
    all_nodes
        All scheduler nodes keyed by node_id.
    running_nodes
        Currently running scheduler nodes (for file/semantic checks).
    budget
        Resource budget for heavy-model-slot checking.
    node_routes
        Mapping of node_id → capability route string.
    semantic_groups
        Optional mapping of group name → member node_ids.

    Returns the subset of ``ready_nodes`` with no conflicts, in stable order.
    """
    running_list = list(running_nodes)
    groups = semantic_groups or {}

    # Track consumed heavy slots within this batch
    consumed_heavy = budget.heavy_model_in_use
    schedulable: list[str] = []
    for node_id in ready_nodes:
        node = all_nodes.get(node_id)
        if node is None:
            continue

        # File conflict
        fc = check_file_conflicts(node, running_list)
        if fc.has_conflict:
            continue

        # Resource conflict — use adjusted budget
        route = node_routes.get(node_id, "")
        if route in _HEAVY_ROUTES:
            available = budget.heavy_model_slots - consumed_heavy
            if available <= 0:
                continue
            # Reserve the slot for this node
            consumed_heavy += 1

        # Semantic conflict
        sc = check_semantic_conflicts(node, running_list, groups)
        if sc.has_conflict:
            # Roll back the reservation if this node is rejected by a later check
            if route in _HEAVY_ROUTES:
                consumed_heavy -= 1
            continue

        schedulable.append(node_id)

    return tuple(schedulable)


__all__ = [
    "ConflictResult",
    "ConflictType",
    "ResourceBudget",
    "apply_conflict_filters",
    "check_file_conflicts",
    "check_resource_conflict",
    "check_semantic_conflicts",
]
