"""Curated immutable workflow definition for new canonical product builds."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from devflow.loop.models import LoopStage


WORKFLOW_ID = "canonical_product_build@1"


class NodeKind(str, Enum):
    """Closed set of node executors supported by the canonical workflow."""

    human = "human"
    agent = "agent"
    code = "code"


class WorkflowNode(BaseModel):
    """One immutable node in the curated workflow."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1)
    kind: NodeKind
    stage: LoopStage
    required_evidence: tuple[str, ...]


class WorkflowEdge(BaseModel):
    """One explicit success or failure route between workflow nodes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    target: str = Field(min_length=1)
    outcome: Literal["success", "failure"]


class WorkflowDefinition(BaseModel):
    """The immutable, serializable canonical product-build contract."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    workflow_id: Literal["canonical_product_build@1"]
    nodes: tuple[WorkflowNode, ...] = Field(min_length=1)
    edges: tuple[WorkflowEdge, ...]

    @model_validator(mode="after")
    def validate_references(self) -> "WorkflowDefinition":
        node_ids = [node.id for node in self.nodes]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("workflow node ids must be unique")
        edge_ids = [edge.id for edge in self.edges]
        if len(edge_ids) != len(set(edge_ids)):
            raise ValueError("workflow edge ids must be unique")
        known_nodes = set(node_ids)
        routes: set[tuple[str, str]] = set()
        for edge in self.edges:
            if edge.source not in known_nodes or edge.target not in known_nodes:
                raise ValueError(
                    f"workflow edge {edge.id!r} references an unknown node"
                )
            route = (edge.source, edge.outcome)
            if route in routes:
                raise ValueError(
                    f"workflow node {edge.source!r} has duplicate {edge.outcome!r} routes"
                )
            routes.add(route)

        graph = {node_id: [] for node_id in node_ids}
        for edge in self.edges:
            graph[edge.source].append(edge.target)
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node_id: str) -> None:
            if node_id in visiting:
                raise ValueError("workflow graph contains a cycle")
            if node_id in visited:
                return
            visiting.add(node_id)
            for target in graph[node_id]:
                visit(target)
            visiting.remove(node_id)
            visited.add(node_id)

        for node_id in node_ids:
            visit(node_id)

        terminal_ids = {
            node.id
            for node in self.nodes
            if node.stage in {LoopStage.complete, LoopStage.blocked}
        }
        for node in self.nodes:
            outcomes = {edge.outcome for edge in self.edges if edge.source == node.id}
            expected = set() if node.id in terminal_ids else {"success", "failure"}
            if outcomes != expected:
                raise ValueError(
                    f"workflow node {node.id!r} must define outcomes {sorted(expected)}"
                )
            if len(node.required_evidence) != len(set(node.required_evidence)):
                raise ValueError(
                    f"workflow node {node.id!r} has duplicate evidence requirements"
                )
        return self


_NODES = (
    WorkflowNode(
        id="idea",
        kind=NodeKind.human,
        stage=LoopStage.idea,
        required_evidence=("idea-brief",),
    ),
    WorkflowNode(
        id="definition",
        kind=NodeKind.human,
        stage=LoopStage.definition,
        required_evidence=("orientation-receipt",),
    ),
    WorkflowNode(
        id="spec",
        kind=NodeKind.agent,
        stage=LoopStage.spec,
        required_evidence=("spec",),
    ),
    WorkflowNode(
        id="planning",
        kind=NodeKind.agent,
        stage=LoopStage.planning,
        required_evidence=("execution-plan",),
    ),
    WorkflowNode(
        id="planning_judge",
        kind=NodeKind.agent,
        stage=LoopStage.planning_judge,
        required_evidence=("planning-judge-report",),
    ),
    WorkflowNode(
        id="assignment",
        kind=NodeKind.agent,
        stage=LoopStage.assignment,
        required_evidence=("approved-execution-plan",),
    ),
    WorkflowNode(
        id="build_judge",
        kind=NodeKind.agent,
        stage=LoopStage.build_judge,
        required_evidence=("build-judge-report",),
    ),
    WorkflowNode(
        id="verification",
        kind=NodeKind.code,
        stage=LoopStage.verification,
        required_evidence=("verification-receipt",),
    ),
    WorkflowNode(
        id="human_decision",
        kind=NodeKind.human,
        stage=LoopStage.human_decision,
        required_evidence=("human-decision",),
    ),
    WorkflowNode(
        id="complete",
        kind=NodeKind.code,
        stage=LoopStage.complete,
        required_evidence=(),
    ),
    WorkflowNode(
        id="blocked",
        kind=NodeKind.human,
        stage=LoopStage.blocked,
        required_evidence=(),
    ),
)

_SUCCESS_CHAIN = tuple(
    zip(
        (
            "idea",
            "definition",
            "spec",
            "planning",
            "planning_judge",
            "assignment",
            "build_judge",
            "verification",
            "human_decision",
        ),
        (
            "definition",
            "spec",
            "planning",
            "planning_judge",
            "assignment",
            "build_judge",
            "verification",
            "human_decision",
            "complete",
        ),
        strict=True,
    )
)

_EDGES = tuple(
    edge
    for source, target in _SUCCESS_CHAIN
    for edge in (
        WorkflowEdge(
            id=f"{source}:success",
            source=source,
            target=target,
            outcome="success",
        ),
        WorkflowEdge(
            id=f"{source}:failure",
            source=source,
            target="blocked",
            outcome="failure",
        ),
    )
)

CANONICAL_PRODUCT_BUILD_V1 = WorkflowDefinition(
    workflow_id=WORKFLOW_ID,
    nodes=_NODES,
    edges=_EDGES,
)


def canonical_product_build_v1() -> WorkflowDefinition:
    """Return the single curated canonical workflow definition."""

    return CANONICAL_PRODUCT_BUILD_V1


__all__ = [
    "CANONICAL_PRODUCT_BUILD_V1",
    "NodeKind",
    "WORKFLOW_ID",
    "WorkflowDefinition",
    "WorkflowEdge",
    "WorkflowNode",
    "canonical_product_build_v1",
]
