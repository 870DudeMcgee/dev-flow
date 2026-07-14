"""Public contract tests for the curated canonical workflow definition."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from devflow.loop.workflow_definition import (
    NodeKind,
    WorkflowDefinition,
    WorkflowEdge,
    WorkflowNode,
    canonical_product_build_v1,
)
from devflow.loop.models import LoopStage


def test_canonical_definition_is_typed_curated_and_serializable() -> None:
    definition = canonical_product_build_v1()

    assert definition.workflow_id == "canonical_product_build@1"
    assert {node.kind for node in definition.nodes} == {
        NodeKind.human,
        NodeKind.agent,
        NodeKind.code,
    }
    assert definition.nodes[0].stage.value == "idea"
    assert {node.stage.value for node in definition.nodes} == {
        "idea",
        "definition",
        "spec",
        "planning",
        "planning_judge",
        "assignment",
        "build_judge",
        "verification",
        "human_decision",
        "complete",
        "blocked",
    }

    terminal_ids = {"complete", "blocked"}
    for node in definition.nodes:
        outgoing = [edge for edge in definition.edges if edge.source == node.id]
        if node.id in terminal_ids:
            assert outgoing == []
            continue
        assert node.required_evidence
        assert {edge.outcome for edge in outgoing} == {"success", "failure"}

    serialized = definition.model_dump(mode="json")
    assert serialized["workflow_id"] == "canonical_product_build@1"
    assert serialized["nodes"][0]["kind"] == "human"


def test_definition_rejects_duplicate_edge_ids() -> None:
    definition = canonical_product_build_v1()

    with pytest.raises(ValidationError, match="workflow edge ids must be unique"):
        WorkflowDefinition(
            workflow_id=definition.workflow_id,
            nodes=definition.nodes,
            edges=definition.edges + (definition.edges[0],),
        )


def test_definition_rejects_cycles() -> None:
    definition = canonical_product_build_v1()
    cycle = WorkflowEdge(
        id="complete:restart",
        source="complete",
        target="idea",
        outcome="success",
    )

    with pytest.raises(ValidationError, match="workflow graph contains a cycle"):
        WorkflowDefinition(
            workflow_id=definition.workflow_id,
            nodes=definition.nodes,
            edges=definition.edges + (cycle,),
        )


def test_definition_is_deeply_immutable_and_serialization_is_deterministic() -> None:
    definition = canonical_product_build_v1()

    with pytest.raises(ValidationError, match="frozen"):
        definition.nodes[0].stage = LoopStage.complete

    assert definition.model_dump_json() == canonical_product_build_v1().model_dump_json()


def test_definition_rejects_duplicate_node_ids() -> None:
    definition = canonical_product_build_v1()
    with pytest.raises(ValidationError, match="workflow node ids must be unique"):
        WorkflowDefinition(
            workflow_id=definition.workflow_id,
            nodes=definition.nodes + (definition.nodes[0],),
            edges=definition.edges,
        )


def test_definition_rejects_unknown_references() -> None:
    definition = canonical_product_build_v1()
    with pytest.raises(ValidationError, match="references an unknown node"):
        WorkflowDefinition(
            workflow_id=definition.workflow_id,
            nodes=definition.nodes,
            edges=definition.edges
            + (
                WorkflowEdge(
                    id="idea:unknown",
                    source="idea",
                    target="missing",
                    outcome="success",
                ),
            ),
        )


def test_definition_rejects_invalid_kind_and_version() -> None:
    with pytest.raises(ValidationError):
        WorkflowNode(
            id="invalid",
            kind="model",
            stage=LoopStage.idea,
            required_evidence=("evidence",),
        )

    definition = canonical_product_build_v1()
    with pytest.raises(ValidationError):
        WorkflowDefinition(
            workflow_id="canonical_product_build@2",
            nodes=definition.nodes,
            edges=definition.edges,
        )


def test_definition_rejects_duplicate_routes() -> None:
    definition = canonical_product_build_v1()
    duplicate_route = WorkflowEdge(
        id="idea:success:duplicate",
        source="idea",
        target="definition",
        outcome="success",
    )
    with pytest.raises(ValidationError, match="duplicate 'success' routes"):
        WorkflowDefinition(
            workflow_id=definition.workflow_id,
            nodes=definition.nodes,
            edges=definition.edges + (duplicate_route,),
        )


def test_definition_rejects_an_empty_node_set() -> None:
    with pytest.raises(ValidationError):
        WorkflowDefinition(
            workflow_id="canonical_product_build@1",
            nodes=(),
            edges=(),
        )
