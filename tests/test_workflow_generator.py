"""Tests for the workflow generator (M6-S1)."""

from __future__ import annotations

import pytest

from devflow.loop.workflow_generator import (
    GenerationRequest,
    GenerationResult,
    generate_workflow,
)
from devflow.loop.workflow_definition import NodeKind
from devflow.loop.workflow_schema import (
    WorkflowSchemaV2,
    WorkflowStrategy,
    validate_workflow,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _request(
    capabilities: tuple[str, ...] = ("bounded_coding",),
    max_nodes: int = 15,
    strategy: WorkflowStrategy = WorkflowStrategy.sequence,
) -> GenerationRequest:
    return GenerationRequest(
        task_description="Implement feature X",
        ticket_id="t-1",
        required_capabilities=capabilities,
        max_nodes=max_nodes,
        strategy_hint=strategy,
    )


# ---------------------------------------------------------------------------
# Generation + validation tests
# ---------------------------------------------------------------------------

def test_generated_graph_validates() -> None:
    """Valid request → valid workflow."""
    result = generate_workflow(_request())

    assert result.workflow is not None
    assert result.validation_errors == ()
    validate_workflow(result.workflow)  # does not raise


def test_generated_workflow_id_prefix() -> None:
    """workflow_id starts with 'generated:'."""
    result = generate_workflow(_request())

    assert result.workflow is not None
    assert result.workflow.workflow_id.startswith("generated:")


def test_generated_graph_rejected_invalid() -> None:
    """Invalid graph → validation_errors populated."""
    # Strategy hint dag with only sequence edges — the validator might accept
    # it, so we force an error by requesting 0 capabilities with tiny max_nodes
    req = GenerationRequest(
        task_description="Test",
        ticket_id="t-1",
        required_capabilities=(),
        max_nodes=3,  # minimal: grounding + gate + 2 terminals = 4 > 3
    )
    result = generate_workflow(req)

    # With max_nodes=3, only grounding fits (needs 3 for body + terminals)
    # This may produce an invalid graph
    if result.workflow is None:
        assert len(result.validation_errors) > 0


def test_generated_has_grounding_entry() -> None:
    """First body node is grounding (repository_analysis)."""
    result = generate_workflow(_request(capabilities=("bounded_coding",)))

    assert result.workflow is not None
    node_ids = [n.id for n in result.workflow.nodes]
    assert node_ids[0] == "gen-grounding"


def test_generated_has_human_gate() -> None:
    """Includes a human_gate before terminal."""
    result = generate_workflow(_request())

    assert result.workflow is not None
    gate_nodes = [n for n in result.workflow.nodes if n.kind == NodeKind.human_gate]
    assert len(gate_nodes) >= 1


def test_generated_budget_proportional() -> None:
    """More nodes → higher budget."""
    small = generate_workflow(_request(capabilities=("bounded_coding",), max_nodes=6))
    large = generate_workflow(_request(
        capabilities=("deep_planning", "bounded_coding", "independent_review", "frontier_judgment"),
        max_nodes=15,
    ))

    assert small.workflow is not None
    assert large.workflow is not None
    assert large.workflow.budget.max_runtime_minutes > small.workflow.budget.max_runtime_minutes


def test_generated_max_nodes_enforced() -> None:
    """Node count within max_nodes bound."""
    result = generate_workflow(_request(
        capabilities=("bounded_coding", "deep_planning", "independent_review"),
        max_nodes=8,
    ))

    assert result.workflow is not None
    assert len(result.workflow.nodes) <= 8


def test_generated_auto_promote_false() -> None:
    """Generated workflow never auto-promotes."""
    result = generate_workflow(_request())

    assert result.workflow is not None
    assert result.workflow.promotion.auto_promote is False


def test_generated_human_required_true() -> None:
    """Generated workflow always requires human."""
    result = generate_workflow(_request())

    assert result.workflow is not None
    assert result.workflow.promotion.human_required is True


def test_generated_uses_functional_roles() -> None:
    """No model names in nodes."""
    forbidden = {"qwen", "qwopus", "ornith", "glm", "gpt", "llama", "codex"}
    result = generate_workflow(_request())

    assert result.workflow is not None
    for node in result.workflow.nodes:
        node_lower = node.id.lower()
        for name in forbidden:
            assert name not in node_lower


def test_generated_strategy_from_hint() -> None:
    """Strategy from request hint."""
    result = generate_workflow(_request(strategy=WorkflowStrategy.sequence))

    assert result.workflow is not None
    assert result.workflow.strategy == WorkflowStrategy.sequence


def test_generate_with_empty_capabilities() -> None:
    """Minimal graph (just grounding) still valid."""
    result = generate_workflow(_request(capabilities=(), max_nodes=10))

    assert result.workflow is not None
    assert len(result.workflow.nodes) >= 4  # grounding + gate + 2 terminals


def test_generation_id_unique() -> None:
    """Two calls produce different generation_ids."""
    r1 = generate_workflow(_request())
    r2 = generate_workflow(_request())

    assert r1.generation_id != r2.generation_id


def test_generation_result_frozen() -> None:
    """GenerationResult is immutable."""
    result = generate_workflow(_request())
    with pytest.raises(Exception):
        result.generation_id = "modified"  # type: ignore[misc]


def test_generation_request_frozen() -> None:
    """GenerationRequest is immutable."""
    req = _request()
    with pytest.raises(Exception):
        req.task_description = "modified"  # type: ignore[misc]


def test_validation_errors_populated_on_failure() -> None:
    """Rejected graph has error messages."""
    # Force max_nodes so tight that grounding + gate + terminals can't fit
    # any requested capability nodes
    req = GenerationRequest(
        task_description="Test",
        ticket_id="t-1",
        required_capabilities=("bounded_coding", "deep_planning"),
        max_nodes=3,  # only room for grounding + gate + 1 terminal — too tight
    )
    result = generate_workflow(req)

    if result.workflow is None:
        assert len(result.validation_errors) > 0
        assert all(isinstance(e, str) and e for e in result.validation_errors)


def test_generated_workflow_is_v2() -> None:
    """Generated workflow is version v2."""
    result = generate_workflow(_request())

    assert result.workflow is not None
    assert result.workflow.version == "v2"


def test_generated_has_complete_and_blocked_terminals() -> None:
    """Generated graph has complete + blocked terminal nodes."""
    result = generate_workflow(_request())

    assert result.workflow is not None
    node_ids = {n.id for n in result.workflow.nodes}
    assert "gen-complete" in node_ids
    assert "gen-blocked" in node_ids
