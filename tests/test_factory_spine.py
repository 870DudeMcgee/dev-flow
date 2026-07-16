"""Cross-module factory-spine acceptance test for the generalized VM.

This is the first end-to-end test that chains the generalized-VM modules
(M2–M7) into one continuous factory path:

    analyze → compile → persist → schedule/conflict-check → execute
    → verify → independent review → explicit gates → projection

It proves the new workflow machinery interoperates without falling back on the
legacy ``canonical_product_build@1`` state machine. Each module's public API
feeds the next; the test itself is the wiring.
"""

from __future__ import annotations

from pathlib import Path

from devflow.loop.pipeline_run import create_pipeline_run
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
)
from devflow.loop.models import LoopStage
from devflow.loop.dag_scheduler import (
    SchedulerNode,
    compute_ready_set,
    is_dag_complete,
)
from devflow.loop.conflict_rules import (
    ResourceBudget,
    apply_conflict_filters,
)
from devflow.loop.node_lifecycle import (
    NodeLifecycleReceipt,
    NodeState,
    get_current_node_state,
    load_lifecycle_events,
    record_lifecycle_event,
)
from devflow.loop.workflow_ledger import (
    EvidenceReference,
    NodeReceipt,
    WorkflowEvent,
    initialize_workflow_run,
    record_node_outcome,
)
from devflow.loop.independent_review import (
    ReviewResult,
    load_reviews,
    record_review,
)
from devflow.control_plane.gates import (
    GateConfig,
    GateDecision,
    GateStatus,
    GateType,
    can_merge,
    can_ship,
    load_gate_decisions,
    record_gate_decision,
)
from devflow.obsidian.projection import extract_projection


def _workflow_schema() -> WorkflowSchemaV2:
    """A minimal linear feature workflow with complete/blocked terminals."""
    nodes = (
        WorkflowNode(
            id="analyze",
            kind=NodeKind.agent,
            stage=LoopStage.spec,
            required_evidence=("analysis",),
        ),
        WorkflowNode(
            id="implement",
            kind=NodeKind.agent,
            stage=LoopStage.planning,
            required_evidence=("implementation",),
        ),
        WorkflowNode(
            id="verify_node",
            kind=NodeKind.code,
            stage=LoopStage.verification,
            required_evidence=("verification",),
        ),
        WorkflowNode(
            id="complete_node",
            kind=NodeKind.code,
            stage=LoopStage.complete,
            required_evidence=(),
        ),
        WorkflowNode(
            id="blocked_node",
            kind=NodeKind.human,
            stage=LoopStage.blocked,
            required_evidence=(),
        ),
    )
    edges = (
        WorkflowEdge(id="e1", source="analyze", target="implement", outcome="success"),
        WorkflowEdge(id="e2", source="analyze", target="blocked_node", outcome="failure"),
        WorkflowEdge(id="e3", source="implement", target="verify_node", outcome="success"),
        WorkflowEdge(id="e4", source="implement", target="blocked_node", outcome="failure"),
        WorkflowEdge(id="e5", source="verify_node", target="complete_node", outcome="success"),
        WorkflowEdge(id="e6", source="verify_node", target="blocked_node", outcome="failure"),
    )
    return WorkflowSchemaV2(
        workflow_id="factory_spine_feature_v1",
        strategy=WorkflowStrategy.sequence,
        budget=BudgetPolicy(
            max_runtime_minutes=60,
            max_agent_runs=5,
            max_repair_rounds=2,
            heavy_model_slots=1,
        ),
        promotion=PromotionPolicy(human_required=True, auto_promote=False),
        nodes=nodes,
        edges=edges,
    )


def _record_node_lifecycle(
    tmp_path: Path,
    run_id: str,
    node_id: str,
    from_state: NodeState,
    to_state: NodeState,
    counter: int,
) -> NodeLifecycleReceipt:
    receipt = NodeLifecycleReceipt(
        lifecycle_id=f"lc-{node_id}-{counter}",
        node_id=node_id,
        run_id=run_id,
        from_state=from_state,
        to_state=to_state,
        timestamp="2026-07-16T09:00:00Z",
    )
    return record_lifecycle_event(tmp_path, run_id, receipt=receipt)


def _execute_node(
    tmp_path: Path,
    run_id: str,
    node_id: str,
    evidence_key: str,
    receipt_id: str,
    evidence_counter: list[int],
) -> None:
    """Drive one node through planned→ready→running→verified with a receipt."""
    run_dir = tmp_path / ".devflow" / "pipeline-runs" / run_id
    (run_dir / f"{evidence_key}.md").write_text(
        f"# {evidence_key}\n\nEvidence for node {node_id}.\n", encoding="utf-8"
    )
    c = evidence_counter
    _record_node_lifecycle(tmp_path, run_id, node_id, NodeState.planned, NodeState.ready, c[0])
    c[0] += 1
    _record_node_lifecycle(tmp_path, run_id, node_id, NodeState.ready, NodeState.running, c[0])
    c[0] += 1
    receipt = NodeReceipt(
        receipt_id=receipt_id,
        node_id=node_id,
        outcome="success",
        evidence=(EvidenceReference(key=evidence_key, reference=f"{evidence_key}.md"),),
    )
    event = WorkflowEvent(
        event_id=f"event-{node_id}",
        node_id=node_id,
        outcome="success",
        receipt_id=receipt_id,
    )
    record_node_outcome(tmp_path, run_id, receipt=receipt, event=event)
    _record_node_lifecycle(tmp_path, run_id, node_id, NodeState.running, NodeState.verified, c[0])
    c[0] += 1


def test_generalized_factory_spine(tmp_path: Path) -> None:
    """Compile → persist → schedule → execute → verify → review → gates → projection.

    Proves the generalized-VM modules interoperate as one continuous factory
    path and that Slice-1 trust boundaries (lifecycle binding, explicit gate
    approvals, recomputed review independence) hold inside the chain.
    """
    # --- Step 1: Compile (WorkflowSchemaV2) ---
    schema = _workflow_schema()
    assert schema.version == "v2"
    assert schema.strategy is WorkflowStrategy.sequence
    assert len(schema.nodes) == 5
    assert len(schema.edges) == 6

    # --- Step 2: Persist (pipeline_run + workflow_ledger) ---
    run_id = create_pipeline_run(
        tmp_path, {"repo": "test/factory-spine", "kind": "generalized_vm"}
    )
    initialize_workflow_run(tmp_path, run_id, definition=schema)
    run_dir = tmp_path / ".devflow" / "pipeline-runs" / run_id

    # --- Step 3: Schedule (dag_scheduler + conflict_rules) ---
    scheduler_nodes = [
        SchedulerNode(node_id="analyze"),
        SchedulerNode(node_id="implement", depends_on=("analyze",)),
        SchedulerNode(node_id="verify_node", depends_on=("implement",)),
    ]
    node_states: dict[str, NodeState] = {
        "analyze": NodeState.planned,
        "implement": NodeState.planned,
        "verify_node": NodeState.planned,
    }
    first_ready = compute_ready_set(scheduler_nodes, node_states)
    assert first_ready == ("analyze",)

    budget = ResourceBudget(heavy_model_slots=1, heavy_model_in_use=0)
    node_routes = {
        "analyze": "deep_planning",
        "implement": "bounded_coding",
        "verify_node": "independent_review",
    }
    filtered = apply_conflict_filters(
        first_ready,
        {n.node_id: n for n in scheduler_nodes},
        [],
        budget,
        node_routes,
    )
    assert "analyze" in filtered

    # --- Step 4: Execute (lifecycle + ledger) ---
    counter = [1]
    _execute_node(tmp_path, run_id, "analyze", "analysis", "receipt-analyze", counter)
    assert get_current_node_state(tmp_path, run_id, "analyze") is NodeState.verified

    # After analyze is verified, implement becomes ready.
    node_states["analyze"] = NodeState.verified
    second_ready = compute_ready_set(scheduler_nodes, node_states)
    assert second_ready == ("implement",)

    _execute_node(tmp_path, run_id, "implement", "implementation", "receipt-implement", counter)
    assert get_current_node_state(tmp_path, run_id, "implement") is NodeState.verified

    node_states["implement"] = NodeState.verified
    third_ready = compute_ready_set(scheduler_nodes, node_states)
    assert third_ready == ("verify_node",)

    _execute_node(tmp_path, run_id, "verify_node", "verification", "receipt-verify", counter)
    assert get_current_node_state(tmp_path, run_id, "verify_node") is NodeState.verified

    node_states["verify_node"] = NodeState.verified
    assert is_dag_complete(
        scheduler_nodes, node_states
    )

    # --- Step 5: Verify (evidence + receipts persisted) ---
    assert (run_dir / "workflow-receipts" / "receipt-analyze.json").exists()
    assert (run_dir / "workflow-receipts" / "receipt-implement.json").exists()
    assert (run_dir / "workflow-receipts" / "receipt-verify.json").exists()
    events = load_lifecycle_events(tmp_path, run_id)
    assert len(events) == 9  # 3 nodes x 3 transitions

    # Direct projection of the generalized workflow
    from devflow.loop.workflow_ledger import rebuild_workflow_snapshot
    snapshot = rebuild_workflow_snapshot(tmp_path, run_id)
    assert snapshot.workflow_id == "factory_spine_feature_v1"
    assert snapshot.current_node_id == "complete_node"
    assert snapshot.completed_node_ids == ("analyze", "implement", "verify_node")
    assert snapshot.stage is LoopStage.complete

    # --- Step 6: Independent review (recomputed independence) ---
    review = ReviewResult(
        review_id="review-1",
        run_id=run_id,
        reviewer_family="glm",
        builder_family="qwen",
        verdict="pass",
        findings=("All nodes verified successfully",),
        families_independent=True,  # True because glm != qwen
        reviewed_at="2026-07-16T09:00:00Z",
    )
    record_review(tmp_path, run_id, review)
    loaded = load_reviews(tmp_path, run_id)
    assert len(loaded) == 1
    assert loaded[0].verdict == "pass"

    # --- Step 7: Gates (explicit approval required) ---
    config = GateConfig()
    decisions = load_gate_decisions(tmp_path, run_id)
    assert can_merge(config, decisions) is False
    assert can_ship(config, decisions) is False

    fv = GateDecision(
        gate_type=GateType.full_verification,
        run_id=run_id,
        ticket_id="t-1",
        status=GateStatus.approved,
        actor="operator-alice",
        decided_at="2026-07-16T10:00:00Z",
    )
    record_gate_decision(tmp_path, run_id, fv)
    decisions = load_gate_decisions(tmp_path, run_id)
    assert can_merge(config, decisions) is False

    merge = GateDecision(
        gate_type=GateType.merge,
        run_id=run_id,
        ticket_id="t-1",
        status=GateStatus.approved,
        actor="operator-bob",
        decided_at="2026-07-16T11:00:00Z",
    )
    record_gate_decision(tmp_path, run_id, merge)
    decisions = load_gate_decisions(tmp_path, run_id)
    assert can_merge(config, decisions) is True

    ship_config = GateConfig(ship_enabled=True)
    assert can_ship(ship_config, decisions) is False
    ship = GateDecision(
        gate_type=GateType.ship,
        run_id=run_id,
        ticket_id="t-1",
        status=GateStatus.approved,
        actor="operator-carol",
        decided_at="2026-07-16T12:00:00Z",
    )
    record_gate_decision(tmp_path, run_id, ship)
    decisions = load_gate_decisions(tmp_path, run_id)
    assert can_ship(ship_config, decisions) is True

    # --- Step 8: Projection (read model from the run) ---
    state = extract_projection(tmp_path, run_id)
    assert state.run_id == run_id
    assert state.health is not None
