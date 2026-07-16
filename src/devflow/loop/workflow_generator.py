"""Workflow generator — proposes candidate graphs (M6-S1, blueprint §6.4/§12.5).

A deterministic graph composer that takes a task description + capability
requirements and produces a candidate :class:`~devflow.loop.workflow_schema.WorkflowSchemaV2`.

The generator is deterministic — it does not call any model. A model *proposes*
by calling this API; the schema *validates*; the human *approves* (M6-S2).

All generated workflows have ``auto_promote=False`` and ``human_required=True``.
Node count is bounded by ``max_nodes`` (3–30).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from devflow.loop.models import LoopStage
from devflow.loop.workflow_definition import (
    NodeKind,
    WorkflowEdge,
    WorkflowNode,
)
from devflow.loop.workflow_schema import (
    BudgetPolicy,
    PromotionPolicy,
    WorkflowSchemaV2,
    WorkflowStrategy,
    validate_workflow,
)

_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"

# Capability → (node_id_prefix, node_kind) mapping
_CAPABILITY_NODES: dict[str, tuple[str, NodeKind]] = {
    "repository_analysis": ("grounding", NodeKind.agent),
    "deep_planning": ("planning", NodeKind.agent),
    "bounded_coding": ("implementation", NodeKind.agent),
    "independent_review": ("review", NodeKind.agent),
    "frontier_judgment": ("judgment", NodeKind.agent),
    "cheap_summary": ("summary", NodeKind.agent),
}


import itertools

_gen_counter = itertools.count(1)


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

class GenerationRequest(BaseModel):
    """Request for a generated workflow graph."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    task_description: str = Field(min_length=1)
    ticket_id: str = Field(pattern=_ID_PATTERN)
    required_capabilities: tuple[str, ...] = ()
    max_nodes: int = Field(default=15, ge=3, le=30)
    strategy_hint: WorkflowStrategy = WorkflowStrategy.sequence


class GenerationResult(BaseModel):
    """Result of a generation attempt."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    request: GenerationRequest
    workflow: WorkflowSchemaV2 | None = None
    validation_errors: tuple[str, ...] = ()
    generation_id: str = Field(pattern=_ID_PATTERN)
    generated_at: str = Field(min_length=1)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def _gen_id() -> str:
    return f"gen-{_now_iso()}-{next(_gen_counter):04d}"


def _success(source: str, target: str) -> WorkflowEdge:
    return WorkflowEdge(
        id=f"{source}:success", source=source, target=target, outcome="success",
    )


def _failure(source: str, target: str) -> WorkflowEdge:
    return WorkflowEdge(
        id=f"{source}:failure", source=source, target=target, outcome="failure",
    )


# ---------------------------------------------------------------------------
# Graph composition
# ---------------------------------------------------------------------------

def _compose_nodes(
    capabilities: tuple[str, ...],
    max_nodes: int,
) -> tuple[WorkflowNode, ...]:
    """Compose body nodes from required capabilities.

    Always starts with ``grounding`` (repository_analysis). If capabilities
    don't include it, it's prepended. Ends with ``human_gate`` → ``complete``
    and ``blocked`` terminals.
    """
    nodes: list[WorkflowNode] = []

    # Ensure grounding is first
    cap_list = list(capabilities)
    if not cap_list or cap_list[0] != "repository_analysis":
        cap_list.insert(0, "repository_analysis")

    for cap in cap_list:
        if len(nodes) >= max_nodes - 3:  # leave room for gate + 2 terminals
            break
        prefix, kind = _CAPABILITY_NODES.get(cap, (cap.replace("-", "_"), NodeKind.agent))
        nodes.append(WorkflowNode(
            id=f"gen-{prefix}",
            kind=kind,
            stage=LoopStage.spec,
            required_evidence=(f"{prefix}-output",),
        ))

    # Human gate before terminals
    nodes.append(WorkflowNode(
        id="gen-approval",
        kind=NodeKind.human_gate,
        stage=LoopStage.human_decision,
        required_evidence=("approval",),
    ))

    # Terminals
    nodes.append(WorkflowNode(
        id="gen-complete",
        kind=NodeKind.code,
        stage=LoopStage.complete,
        required_evidence=(),
    ))
    nodes.append(WorkflowNode(
        id="gen-blocked",
        kind=NodeKind.human,
        stage=LoopStage.blocked,
        required_evidence=(),
    ))

    return tuple(nodes)


def _compose_edges(nodes: tuple[WorkflowNode, ...]) -> tuple[WorkflowEdge, ...]:
    """Build success-chain + failure→blocked edges for a linear node sequence."""
    edges: list[WorkflowEdge] = []
    body_ids = [n.id for n in nodes if n.id not in ("gen-complete", "gen-blocked")]

    for i in range(len(body_ids) - 1):
        edges.append(_success(body_ids[i], body_ids[i + 1]))
        edges.append(_failure(body_ids[i], "gen-blocked"))

    # Last body node → complete (success) + blocked (failure)
    if body_ids:
        last = body_ids[-1]
        edges.append(_success(last, "gen-complete"))
        edges.append(_failure(last, "gen-blocked"))

    return tuple(edges)


def _derive_budget(node_count: int) -> BudgetPolicy:
    """Derive budget from node count."""
    return BudgetPolicy(
        max_runtime_minutes=min(30 * node_count, 480),
        max_agent_runs=min(3 * node_count, 60),
        max_repair_rounds=min(node_count, 5),
        heavy_model_slots=1,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_workflow(request: GenerationRequest) -> GenerationResult:
    """Generate a candidate workflow graph from a task description.

    1. Compose nodes/edges from the request's required capabilities
    2. Assign budget based on node count
    3. Validate against the M2 schema
    4. Return result with workflow (if valid) or validation_errors
    """
    generation_id = _gen_id()

    nodes = _compose_nodes(request.required_capabilities, request.max_nodes)
    edges = _compose_edges(nodes)
    budget = _derive_budget(len(nodes))

    try:
        workflow = WorkflowSchemaV2(
            version="v2",
            workflow_id=f"generated:{generation_id}",
            strategy=request.strategy_hint,
            budget=budget,
            promotion=PromotionPolicy(human_required=True, auto_promote=False),
            nodes=nodes,
            edges=edges,
        )
        validate_workflow(workflow)
    except Exception as exc:
        return GenerationResult(
            request=request,
            workflow=None,
            validation_errors=(str(exc),),
            generation_id=generation_id,
            generated_at=_now_iso(),
        )

    return GenerationResult(
        request=request,
        workflow=workflow,
        validation_errors=(),
        generation_id=generation_id,
        generated_at=_now_iso(),
    )


__all__ = [
    "GenerationRequest",
    "GenerationResult",
    "generate_workflow",
]
