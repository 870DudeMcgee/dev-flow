"""Versioned workflow schema and generalized validator (M2-S1).

Separates composition strategy (how nodes are organized) from executable node
kind (what a node does), and adds budget/gate/loop/promotion policy validation.

Versioning:

- **v1** — ``canonical_product_build@1`` (legacy): no strategy field, validated
  by :func:`WorkflowDefinition.validate_references`.
- **v2** — generalized: strategy, budgets, gates, loops, promotion policy,
  optional phase grouping.

Both versions coexist. v1 is never broken; v2 is additive.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from devflow.loop.workflow_definition import (
    WorkflowDefinition,
    WorkflowEdge,
    WorkflowNode,
    canonical_product_build_v1,
)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class WorkflowVersion(str, Enum):
    """Schema version marker."""

    v1 = "v1"
    v2 = "v2"


class WorkflowStrategy(str, Enum):
    """How nodes within a phase or workflow are composed (blueprint §6.5).

    This is a *composition* attribute — it describes how nodes are scheduled
    relative to each other, not what each node executes. The distinction from
    :class:`NodeKind` (the executable type) is intentional (design decision D.13).
    """

    sequence = "sequence"
    parallel = "parallel"
    dag = "dag"
    loop = "loop"
    conditional = "conditional"


# ---------------------------------------------------------------------------
# Policy models
# ---------------------------------------------------------------------------

class LoopPolicy(BaseModel):
    """Bounds for a loop strategy — required when strategy=loop.

    A loop without bounds is the most dangerous workflow pattern: it can run
    forever, burn the entire budget, and never reach a terminal state. The
    validator rejects any loop that lacks this policy.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    max_rounds: int = Field(ge=1, le=20)
    stop_if_no_progress: int = Field(ge=1, le=10)


class BudgetPolicy(BaseModel):
    """Resource budgets for a workflow (blueprint §6.5 budgets)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    max_runtime_minutes: int = Field(default=180, ge=1, le=1440)
    max_agent_runs: int = Field(default=30, ge=1, le=200)
    max_repair_rounds: int = Field(default=4, ge=0, le=10)
    heavy_model_slots: int = Field(default=1, ge=0, le=4)


class PromotionPolicy(BaseModel):
    """Human authority over promotion (blueprint §9.4 AUTHORITY BOUNDARY).

    ``auto_promote`` is always ``False`` — the validator enforces this. No
    generated or parameterized workflow may grant itself autonomous promotion
    authority (blueprint §6.3, §9.4).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    human_required: bool = True
    auto_promote: bool = False


class PhaseDefinition(BaseModel):
    """A named group of nodes with its own composition strategy."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1)
    strategy: WorkflowStrategy = WorkflowStrategy.sequence
    node_ids: tuple[str, ...] = Field(min_length=1)
    loop_policy: LoopPolicy | None = None


# ---------------------------------------------------------------------------
# Versioned generalized schema
# ---------------------------------------------------------------------------


def _detect_back_edges(graph: dict[str, list[str]]) -> set[tuple[str, str]]:
    """Return edges (source, target) that close a cycle (DFS back-edges)."""
    from enum import IntEnum

    class _Color(IntEnum):
        WHITE = 0
        GRAY = 1
        BLACK = 2

    color: dict[str, _Color] = {n: _Color.WHITE for n in graph}
    back: set[tuple[str, str]] = set()

    def dfs(node_id: str) -> None:
        color[node_id] = _Color.GRAY
        for nxt in graph.get(node_id, ()):
            if color.get(nxt, _Color.WHITE) == _Color.WHITE:
                dfs(nxt)
            elif color.get(nxt) == _Color.GRAY:
                back.add((node_id, nxt))
        color[node_id] = _Color.BLACK

    for n in graph:
        if color[n] == _Color.WHITE:
            dfs(n)
    return back


class WorkflowSchemaV2(BaseModel):
    """Versioned generalized workflow schema.

    Extends the v1 node/edge model with composition strategy, budgets,
    promotion policy, and optional phase grouping. The legacy
    :class:`WorkflowDefinition` (v1) remains valid and unchanged.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal["v2"] = "v2"
    workflow_id: str = Field(min_length=1)
    strategy: WorkflowStrategy = WorkflowStrategy.sequence
    loop_policy: LoopPolicy | None = None
    budget: BudgetPolicy = Field(default_factory=BudgetPolicy)
    promotion: PromotionPolicy = Field(default_factory=PromotionPolicy)
    nodes: tuple[WorkflowNode, ...] = Field(min_length=1)
    edges: tuple[WorkflowEdge, ...]
    phases: tuple[PhaseDefinition, ...] = ()

    @model_validator(mode="after")
    def validate_v2(self) -> "WorkflowSchemaV2":
        # Delegate structural checks to the v1 validator by constructing
        # a temporary v1 definition with the same nodes/edges.
        # This ensures v2 inherits all v1 cycle/ref/terminal checks.
        node_ids = {n.id for n in self.nodes}

        # --- Structural checks (same as v1 validate_references) ---
        if len(node_ids) != len(self.nodes):
            raise ValueError("workflow node ids must be unique")
        edge_ids = [e.id for e in self.edges]
        if len(edge_ids) != len(set(edge_ids)):
            raise ValueError("workflow edge ids must be unique")
        for edge in self.edges:
            if edge.source not in node_ids or edge.target not in node_ids:
                raise ValueError(
                    f"workflow edge {edge.id!r} references an unknown node"
                )
        routes: set[tuple[str, str]] = set()
        for edge in self.edges:
            route = (edge.source, edge.outcome)
            if route in routes:
                # Fan-out (multiple 'success' edges) is allowed for parallel/
                # dag/loop strategies. For sequence a node must have a single
                # success path; 'failure' is always single.
                if edge.outcome == "success" and self.strategy != WorkflowStrategy.sequence:
                    pass
                else:
                    raise ValueError(
                        f"workflow node {edge.source!r} has duplicate {edge.outcome!r} routes"
                    )
            routes.add(route)

        # v2-specific: a loop strategy (workflow- or phase-level) requires a
        # loop policy. This is checked BEFORE the structural back-edge rules so
        # a bare ``strategy=loop`` reports the missing policy rather than a
        # structural "missing back-edge" error (Slice 3).
        if self.strategy == WorkflowStrategy.loop and self.loop_policy is None:
            raise ValueError(
                "workflow with strategy=loop requires a loop_policy "
                "(max_rounds and stop_if_no_progress)"
            )
        for phase in self.phases:
            if phase.strategy == WorkflowStrategy.loop and phase.loop_policy is None:
                raise ValueError(
                    f"phase {phase.id!r} with strategy=loop requires a loop_policy"
                )

        # Cycle check — with loop-strategy exemption (Slice 3).
        #
        # A bounded intentional loop (strategy=loop) requires exactly ONE
        # back-edge that returns control to the loop head. That back-edge is a
        # legitimate cycle and must NOT be rejected; instead we validate the
        # loop bounds and that the forward graph (back-edge removed) is acyclic
        # and reaches a terminal. Non-loop workflows must remain acyclic.
        graph = {n.id: [] for n in self.nodes}
        for edge in self.edges:
            graph[edge.source].append(edge.target)

        is_loop = self.strategy == WorkflowStrategy.loop
        back_edges = _detect_back_edges(graph)
        if is_loop:
            # A bounded loop REQUIRES exactly one intentional back-edge that
            # returns control to the unique loop head (the in-degree-0 node in
            # the forward graph). A policy-valid but acyclic graph is
            # meaningless and must be rejected. The policy check above already
            # ran first, so an unbounded loop reports the policy error rather
            # than this missing back-edge error (Slice 3).
            if not back_edges:
                raise ValueError(
                    "workflow with strategy=loop requires a back-edge "
                    "targeting the loop head"
                )
            if len(back_edges) > 1:
                raise ValueError(
                    "workflow with strategy=loop must contain exactly one back-edge"
                )
            (_, back_tgt) = next(iter(back_edges))
            # The loop head is the unique node with in-degree 0 in the FORWARD
            # graph (back-edge removed), so the back-edge re-entering it does
            # not inflate its in-degree.
            forward_in_degree = {n.id: 0 for n in self.nodes}
            for src, targets in graph.items():
                for tgt in targets:
                    if (src, tgt) in back_edges:
                        continue
                    forward_in_degree[tgt] += 1
            heads = [nid for nid, d in forward_in_degree.items() if d == 0]
            if len(heads) != 1:
                raise ValueError(
                    "workflow with strategy=loop must have exactly one loop head"
                )
            head = heads[0]
            if back_tgt != head:
                raise ValueError(
                    "loop back-edge must target the loop head"
                )
        elif back_edges:
            raise ValueError("workflow graph contains a cycle")

        # Forward graph must be acyclic (remove loop back-edge if present).
        forward = {n: list(t) for n, t in graph.items()}
        for (bs, bt) in back_edges:
            if bt in forward.get(bs, []):
                forward[bs].remove(bt)
        visiting_f: set[str] = set()
        visited_f: set[str] = set()

        def visit_f(node_id: str) -> None:
            if node_id in visiting_f:
                raise ValueError("workflow forward graph contains a cycle")
            if node_id in visited_f:
                return
            visiting_f.add(node_id)
            for target in forward.get(node_id, ()):
                visit_f(target)
            visiting_f.remove(node_id)
            visited_f.add(node_id)

        for node in self.nodes:
            visit_f(node.id)

        # Terminal completeness
        from devflow.loop.models import LoopStage

        terminal_ids = {
            n.id for n in self.nodes
            if n.stage in {LoopStage.complete, LoopStage.blocked}
        }
        for node in self.nodes:
            outcomes = {e.outcome for e in self.edges if e.source == node.id}
            if node.id in terminal_ids:
                # Terminal nodes must have no outgoing edges.
                if outcomes:
                    raise ValueError(
                        f"workflow terminal node {node.id!r} must define no outcomes"
                    )
            else:
                # Non-terminal nodes must define a 'failure' edge (fan-out via
                # multiple 'success' edges is allowed for parallel/dag/loop).
                if "failure" not in outcomes:
                    raise ValueError(
                        f"workflow node {node.id!r} must define a 'failure' outcome"
                    )
            if len(node.required_evidence) != len(set(node.required_evidence)):
                raise ValueError(
                    f"workflow node {node.id!r} has duplicate evidence requirements"
                )

        # --- v2-specific checks ---

        # No autonomous promotion
        if self.promotion.auto_promote:
            raise ValueError(
                "auto_promote must be False — no autonomous promotion "
                "(blueprint §9.4 AUTHORITY BOUNDARY)"
            )

        # Phase coverage: every node must belong to exactly one phase
        if self.phases:
            all_phase_nodes: list[str] = []
            for phase in self.phases:
                for nid in phase.node_ids:
                    if nid not in node_ids:
                        raise ValueError(
                            f"phase {phase.id!r} references unknown node {nid!r}"
                        )
                    all_phase_nodes.append(nid)
            if sorted(all_phase_nodes) != sorted(node_ids):
                raise ValueError(
                    "phase coverage mismatch: every node must belong to "
                    "exactly one phase (got mismatches between phase node_ids "
                    "and workflow nodes)"
                )

        return self


# ---------------------------------------------------------------------------
# Validator entry points
# ---------------------------------------------------------------------------

def validate_workflow(
    definition: WorkflowDefinition | WorkflowSchemaV2,
) -> None:
    """Validate a workflow definition of any version.

    Raises ``ValueError`` on any structural or policy violation.
    Does nothing if the workflow is valid.
    """
    if isinstance(definition, WorkflowSchemaV2):
        # V2 validator runs on construction; re-run explicitly for clarity.
        WorkflowSchemaV2.model_validate(definition.model_dump(mode="json"))
        return

    if isinstance(definition, WorkflowDefinition):
        # V1 validator runs on construction; re-validate explicitly.
        WorkflowDefinition.model_validate(definition.model_dump(mode="json"))
        return

    raise TypeError(
        f"unsupported workflow definition type: {type(definition).__name__}"
    )


def legacy_v1_validates() -> bool:
    """Confirm the legacy canonical_product_build@1 definition still validates.

    Utility for regression tests — confirms the v1 definition is not broken
    by any v2 additions.
    """
    try:
        canonical_product_build_v1()
        return True
    except Exception:
        return False


__all__ = [
    "BudgetPolicy",
    "LoopPolicy",
    "PhaseDefinition",
    "PromotionPolicy",
    "WorkflowSchemaV2",
    "WorkflowStrategy",
    "WorkflowVersion",
    "legacy_v1_validates",
    "validate_workflow",
]
