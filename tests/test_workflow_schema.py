"""Tests for the versioned workflow schema and generalized validator (M2-S1)."""

from __future__ import annotations

import pytest

from devflow.loop.models import LoopStage
from devflow.loop.workflow_definition import (
    NodeKind,
    WorkflowEdge,
    WorkflowNode,
    canonical_product_build_v1,
)
from devflow.loop.workflow_schema import (
    BudgetPolicy,
    LoopPolicy,
    PhaseDefinition,
    PromotionPolicy,
    WorkflowSchemaV2,
    WorkflowStrategy,
    WorkflowVersion,
    legacy_v1_validates,
    validate_workflow,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_node(
    node_id: str,
    kind: NodeKind = NodeKind.agent,
    stage: LoopStage = LoopStage.spec,
    evidence: tuple[str, ...] = ("output",),
) -> WorkflowNode:
    return WorkflowNode(id=node_id, kind=kind, stage=stage, required_evidence=evidence)


def _success_edge(source: str, target: str) -> WorkflowEdge:
    return WorkflowEdge(id=f"{source}:success", source=source, target=target, outcome="success")


def _failure_edge(source: str, target: str = "blocked") -> WorkflowEdge:
    return WorkflowEdge(id=f"{source}:failure", source=source, target=target, outcome="failure")


def _loop_back_edge(source: str, target: str) -> WorkflowEdge:
    # strategy=loop allows 'success' fan-out, so the intentional back-edge to
    # the loop head uses a 'success' outcome (a legitimate cycle, not duplicate
    # route rejection).
    return WorkflowEdge(id=f"{source}:loop_back", source=source, target=target, outcome="success")


def _terminal_nodes() -> tuple[WorkflowNode, ...]:
    return (
        WorkflowNode(id="complete", kind=NodeKind.code, stage=LoopStage.complete, required_evidence=()),
        WorkflowNode(id="blocked", kind=NodeKind.human, stage=LoopStage.blocked, required_evidence=()),
    )


def _simple_v2_sequence(
    strategy: WorkflowStrategy = WorkflowStrategy.sequence,
    loop_policy: LoopPolicy | None = None,
    promotion: PromotionPolicy | None = None,
    phases: tuple[PhaseDefinition, ...] = (),
    budget: BudgetPolicy | None = None,
) -> WorkflowSchemaV2:
    nodes = (
        _make_node("start", NodeKind.agent, LoopStage.spec),
        _make_node("middle", NodeKind.agent, LoopStage.planning),
        *_terminal_nodes(),
    )
    edges = (
        _success_edge("start", "middle"),
        _failure_edge("start"),
        _success_edge("middle", "complete"),
        _failure_edge("middle"),
    )
    if strategy == WorkflowStrategy.loop:
        # A bounded loop requires a real back-edge returning to the loop head
        # ('start'), which is the unique forward-graph root. Retain the
        # success/failure terminal routes; the loop_back edge is a legitimate
        # cycle (not duplicate-route rejection under strategy=loop).
        edges = (
            _success_edge("start", "middle"),
            _failure_edge("start"),
            _success_edge("middle", "complete"),
            _failure_edge("middle"),
            _loop_back_edge("middle", "start"),
        )
    kwargs: dict = dict(
        workflow_id="test-v2-workflow@1",
        strategy=strategy,
        nodes=nodes,
        edges=edges,
    )
    if loop_policy is not None:
        kwargs["loop_policy"] = loop_policy
    if promotion is not None:
        kwargs["promotion"] = promotion
    if phases:
        kwargs["phases"] = phases
    if budget is not None:
        kwargs["budget"] = budget
    return WorkflowSchemaV2(**kwargs)


# ---------------------------------------------------------------------------
# V1 legacy tests
# ---------------------------------------------------------------------------

def test_v1_legacy_validates_unchanged() -> None:
    """canonical_product_build@1 passes v1 validator without error."""
    assert legacy_v1_validates()
    # Also verify it constructs and validates directly
    defn = canonical_product_build_v1()
    validate_workflow(defn)


def test_workflow_version_enum() -> None:
    assert WorkflowVersion.v1.value == "v1"
    assert WorkflowVersion.v2.value == "v2"


# ---------------------------------------------------------------------------
# V2 basic validation tests
# ---------------------------------------------------------------------------

def test_v2_sequence_validates() -> None:
    """Simple v2 sequence graph validates."""
    schema = _simple_v2_sequence()
    validate_workflow(schema)
    assert schema.version == "v2"


def test_strategy_enum_values() -> None:
    """All five composition strategies exist."""
    strategies = {s.value for s in WorkflowStrategy}
    assert strategies == {"sequence", "parallel", "dag", "loop", "conditional"}


# ---------------------------------------------------------------------------
# Loop policy tests
# ---------------------------------------------------------------------------

def test_v2_rejects_unbounded_loop() -> None:
    """strategy=loop without loop_policy → ValueError."""
    with pytest.raises(ValueError, match="loop requires a loop_policy"):
        _simple_v2_sequence(strategy=WorkflowStrategy.loop)


def test_v2_loop_with_policy_validates() -> None:
    """strategy=loop + loop_policy → valid (real bounded loop)."""
    schema = _simple_v2_sequence(
        strategy=WorkflowStrategy.loop,
        loop_policy=LoopPolicy(max_rounds=3, stop_if_no_progress=2),
    )
    assert schema.strategy == WorkflowStrategy.loop
    assert schema.loop_policy is not None
    assert schema.loop_policy.max_rounds == 3


def test_v2_loop_with_policy_but_no_back_edge_rejected() -> None:
    """strategy=loop + loop_policy but NO back-edge → ValueError.

    A policy-valid but acyclic graph is meaningless; the strict Slice 3
    invariant requires exactly one intentional back-edge targeting the loop
    head.
    """
    nodes = (
        _make_node("start", NodeKind.agent, LoopStage.spec),
        _make_node("middle", NodeKind.agent, LoopStage.planning),
        *_terminal_nodes(),
    )
    # Acyclic graph: no back-edge from middle to start.
    edges = (
        _success_edge("start", "middle"),
        _failure_edge("start"),
        _success_edge("middle", "complete"),
        _failure_edge("middle"),
    )
    with pytest.raises(ValueError, match="requires a back-edge"):
        WorkflowSchemaV2(
            workflow_id="test-loop-no-backedge@1",
            strategy=WorkflowStrategy.loop,
            nodes=nodes,
            edges=edges,
            loop_policy=LoopPolicy(max_rounds=3, stop_if_no_progress=2),
        )


def test_loop_policy_field_bounds() -> None:
    """LoopPolicy enforces bounds."""
    with pytest.raises(Exception):
        LoopPolicy(max_rounds=0, stop_if_no_progress=1)
    with pytest.raises(Exception):
        LoopPolicy(max_rounds=21, stop_if_no_progress=1)


def test_phase_loop_requires_policy() -> None:
    """Phase with strategy=loop requires its own loop_policy."""
    nodes = (
        _make_node("a", NodeKind.agent, LoopStage.spec),
        _make_node("b", NodeKind.agent, LoopStage.planning),
        *_terminal_nodes(),
    )
    edges = (
        _success_edge("a", "b"),
        _failure_edge("a"),
        _success_edge("b", "complete"),
        _failure_edge("b"),
    )
    phases = (
        PhaseDefinition(id="p1", strategy=WorkflowStrategy.loop, node_ids=("a", "b")),
    )
    with pytest.raises(ValueError, match="phase.*loop.*loop_policy"):
        WorkflowSchemaV2(
            workflow_id="test-phase-loop@1",
            nodes=nodes,
            edges=edges,
            phases=phases,
        )


# ---------------------------------------------------------------------------
# Promotion policy tests
# ---------------------------------------------------------------------------

def test_v2_rejects_auto_promote() -> None:
    """auto_promote=True → ValueError."""
    with pytest.raises(ValueError, match="auto_promote must be False"):
        _simple_v2_sequence(promotion=PromotionPolicy(auto_promote=True))


def test_promotion_policy_defaults() -> None:
    """Default promotion policy requires human and no auto-promote."""
    p = PromotionPolicy()
    assert p.human_required is True
    assert p.auto_promote is False


# ---------------------------------------------------------------------------
# Budget tests
# ---------------------------------------------------------------------------

def test_v2_budget_range_enforced() -> None:
    """Budget fields enforce allowed ranges."""
    with pytest.raises(Exception):
        BudgetPolicy(max_runtime_minutes=0)
    with pytest.raises(Exception):
        BudgetPolicy(max_runtime_minutes=1441)


def test_budget_defaults() -> None:
    """BudgetPolicy has correct defaults."""
    b = BudgetPolicy()
    assert b.max_runtime_minutes == 180
    assert b.max_agent_runs == 30
    assert b.max_repair_rounds == 4
    assert b.heavy_model_slots == 1


# ---------------------------------------------------------------------------
# Phase tests
# ---------------------------------------------------------------------------

def test_v2_phase_node_coverage() -> None:
    """Phase coverage mismatch → ValueError."""
    nodes = (
        _make_node("a", NodeKind.agent, LoopStage.spec),
        _make_node("b", NodeKind.agent, LoopStage.planning),
        _make_node("c", NodeKind.agent, LoopStage.verification),
        *_terminal_nodes(),
    )
    edges = (
        _success_edge("a", "b"),
        _failure_edge("a"),
        _success_edge("b", "c"),
        _failure_edge("b"),
        _success_edge("c", "complete"),
        _failure_edge("c"),
    )
    # Phase only covers a,b — c, complete, blocked are uncovered
    phases = (PhaseDefinition(id="p1", node_ids=("a", "b")),)
    with pytest.raises(ValueError, match="phase coverage"):
        WorkflowSchemaV2(
            workflow_id="test-coverage@1",
            nodes=nodes,
            edges=edges,
            phases=phases,
        )


def test_v2_phase_unknown_node() -> None:
    """Phase references nonexistent node → ValueError."""
    nodes = (
        _make_node("a", NodeKind.agent, LoopStage.spec),
        *_terminal_nodes(),
    )
    edges = (
        _success_edge("a", "complete"),
        _failure_edge("a"),
    )
    phases = (PhaseDefinition(id="p1", node_ids=("a", "nonexistent")),)
    with pytest.raises(ValueError, match="unknown node"):
        WorkflowSchemaV2(
            workflow_id="test-unknown@1",
            nodes=nodes,
            edges=edges,
            phases=phases,
        )


def test_v2_phases_valid_full_coverage() -> None:
    """Phases covering all nodes validate."""
    schema = _simple_v2_sequence(
        phases=(
            PhaseDefinition(id="build", node_ids=("start",)),
            PhaseDefinition(id="verify", node_ids=("middle",)),
            PhaseDefinition(id="terminal", node_ids=("complete", "blocked")),
        )
    )
    assert len(schema.phases) == 3


# ---------------------------------------------------------------------------
# New node kinds tests
# ---------------------------------------------------------------------------

def test_v2_new_node_kinds_valid() -> None:
    """gate, human_gate, artifact_emit are accepted node kinds."""
    assert NodeKind.gate.value == "gate"
    assert NodeKind.human_gate.value == "human_gate"
    assert NodeKind.artifact_emit.value == "artifact_emit"


def test_v2_gate_node_validates() -> None:
    """A gate node with success/failure outcomes validates."""
    nodes = (
        WorkflowNode(id="my_gate", kind=NodeKind.gate, stage=LoopStage.verification, required_evidence=("gate-result",)),
        *_terminal_nodes(),
    )
    edges = (
        _success_edge("my_gate", "complete"),
        _failure_edge("my_gate"),
    )
    schema = WorkflowSchemaV2(
        workflow_id="test-gate@1",
        nodes=nodes,
        edges=edges,
    )
    validate_workflow(schema)


def test_v2_human_gate_node_validates() -> None:
    """A human_gate node validates."""
    nodes = (
        WorkflowNode(id="approval", kind=NodeKind.human_gate, stage=LoopStage.human_decision, required_evidence=("human-decision",)),
        *_terminal_nodes(),
    )
    edges = (
        _success_edge("approval", "complete"),
        _failure_edge("approval"),
    )
    schema = WorkflowSchemaV2(
        workflow_id="test-human-gate@1",
        nodes=nodes,
        edges=edges,
    )
    validate_workflow(schema)


def test_v2_artifact_emit_node_validates() -> None:
    """An artifact_emit node validates."""
    nodes = (
        WorkflowNode(id="emit", kind=NodeKind.artifact_emit, stage=LoopStage.complete, required_evidence=("artifact",)),
    )
    # artifact_emit at complete stage — terminal, no edges needed
    schema = WorkflowSchemaV2(
        workflow_id="test-emit@1",
        nodes=nodes,
        edges=(),
    )
    # complete stage nodes are terminal — no outcomes required
    validate_workflow(schema)


# ---------------------------------------------------------------------------
# Structural validation (v2 inherits v1 checks)
# ---------------------------------------------------------------------------

def test_v2_rejects_cycle() -> None:
    """v2 schema rejects cycles."""
    nodes = (
        _make_node("a", NodeKind.agent, LoopStage.spec),
        _make_node("b", NodeKind.agent, LoopStage.planning),
        *_terminal_nodes(),
    )
    edges = (
        _success_edge("a", "b"),
        _failure_edge("a"),
        _success_edge("b", "a"),  # cycle!
        _failure_edge("b"),
    )
    with pytest.raises(ValueError, match="cycle"):
        WorkflowSchemaV2(
            workflow_id="test-cycle@1",
            nodes=nodes,
            edges=edges,
        )


def test_v2_rejects_duplicate_node_ids() -> None:
    """Duplicate node IDs → ValueError."""
    nodes = (
        _make_node("dup", NodeKind.agent, LoopStage.spec),
        _make_node("dup", NodeKind.agent, LoopStage.planning),
        *_terminal_nodes(),
    )
    edges = (
        _success_edge("dup", "complete"),
        _failure_edge("dup"),
    )
    with pytest.raises(ValueError, match="unique"):
        WorkflowSchemaV2(
            workflow_id="test-dup@1",
            nodes=nodes,
            edges=edges,
        )


def test_v2_rejects_unknown_edge_node() -> None:
    """Edge referencing unknown node → ValueError."""
    nodes = (
        _make_node("a", NodeKind.agent, LoopStage.spec),
        *_terminal_nodes(),
    )
    edges = (
        WorkflowEdge(id="e1", source="a", target="nonexistent", outcome="success"),
        _failure_edge("a"),
    )
    with pytest.raises(ValueError, match="unknown node"):
        WorkflowSchemaV2(
            workflow_id="test-unknown-edge@1",
            nodes=nodes,
            edges=edges,
        )


# ---------------------------------------------------------------------------
# Coexistence tests
# ---------------------------------------------------------------------------

def test_v1_and_v2_coexist() -> None:
    """Both schema versions are importable and don't conflict."""
    v1 = canonical_product_build_v1()
    v2 = _simple_v2_sequence()

    validate_workflow(v1)
    validate_workflow(v2)

    assert v1.workflow_id == "canonical_product_build@1"
    assert v2.workflow_id == "test-v2-workflow@1"


def test_v2_model_is_frozen() -> None:
    """WorkflowSchemaV2 is immutable."""
    schema = _simple_v2_sequence()
    with pytest.raises(Exception):
        schema.workflow_id = "modified"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# validate_workflow dispatch tests
# ---------------------------------------------------------------------------

def test_validate_workflow_rejects_bad_type() -> None:
    """validate_workflow rejects unsupported types."""
    with pytest.raises(TypeError):
        validate_workflow("not a workflow")  # type: ignore[arg-type]


def test_v2_schema_round_trips_json() -> None:
    """v2 schema serializes and deserializes cleanly."""
    schema = _simple_v2_sequence(
        loop_policy=LoopPolicy(max_rounds=3, stop_if_no_progress=2),
    )
    data = schema.model_dump(mode="json")
    restored = WorkflowSchemaV2.model_validate(data)
    assert restored.workflow_id == schema.workflow_id
    assert restored.strategy == schema.strategy
    assert restored.loop_policy == schema.loop_policy
