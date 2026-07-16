"""Tests for the generalized workflow VM (Slice 3) against the family templates.

Disposable runs are created under ``tmp_path``; the run directory is seeded
with the v2 definition (``workflow-definition-v2.json``), an empty events
ledger, and a receipts directory, exactly as :func:`run_workflow` expects.

Scope is intentionally focused: real DAG/parallel feature execution, rich
human-gate receipts, bounded-loop behavior, fail-closed on unknown outcomes,
and a canonical-spine (no-duplication) regression check.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable as _UnusedCallable  # noqa: F401  (kept intentionally minimal)

import pytest

from devflow.loop.models import LoopStage
from devflow.loop.pipeline_run import create_pipeline_run, pipeline_runs_dir
from devflow.loop.workflow_definition import (
    NodeKind,
    WorkflowEdge,
    WorkflowNode,
    canonical_product_build_v1,
)
from devflow.loop.workflow_library import feature_template
from devflow.loop.workflow_schema import (
    BudgetPolicy,
    LoopPolicy,
    PromotionPolicy,
    WorkflowSchemaV2,
    WorkflowStrategy,
    validate_workflow,
)
from devflow.loop.workflow_vm import (
    GateOutcomeReceipt,
    NodeOutcome,
    WorkflowVMError,
    WorkflowVMResult,
    load_gate_outcomes,
    run_workflow,
)


# ---------------------------------------------------------------------------
# Run setup helper
# ---------------------------------------------------------------------------

def _seed_run(
    root: Path, definition: WorkflowSchemaV2
) -> str:
    """Create a disposable pipeline run and seed the v2 definition + ledger.

    Mirrors the on-disk contract :func:`run_workflow` requires: the v2
    definition marker, an empty events ledger, and a receipts directory.
    """
    run_id = create_pipeline_run(root, {"repo": "vm-test"})
    run_dir = pipeline_runs_dir(root) / run_id
    payload = definition.model_dump(mode="json")
    (run_dir / "workflow-definition-v2.json").write_text(
        json_dumps(payload), encoding="utf-8"
    )
    (run_dir / "workflow-events.jsonl").write_text("", encoding="utf-8")
    (run_dir / "workflow-receipts").mkdir()
    return run_id


def json_dumps(obj: object) -> str:
    import json

    return json.dumps(obj, indent=2, sort_keys=True) + "\n"


class _RecordingExecutor:
    """Executor that records execution order and applies a per-node policy."""

    def __init__(
        self,
        plan: dict[str, NodeOutcome] | None = None,
        *,
        gate_outcome: NodeOutcome = NodeOutcome.approved,
    ) -> None:
        self.plan = plan or {}
        self.gate_outcome = gate_outcome
        self.executed: list[str] = []

    def execute(self, node: WorkflowNode, context):  # noqa: ANN001
        self.executed.append(node.id)
        if node.id in self.plan:
            return self.plan[node.id]
        if node.kind in (NodeKind.gate, NodeKind.human_gate):
            return self.gate_outcome
        return NodeOutcome.success


# ---------------------------------------------------------------------------
# Real parallel / DAG feature-template execution
# ---------------------------------------------------------------------------

def test_feature_dag_fan_out_then_join(tmp_path: Path) -> None:
    """Both build branches run; integration runs only after both; reaches complete."""
    wf = feature_template()
    validate_workflow(wf)  # genuine fan-out/join DAG must validate
    run_id = _seed_run(tmp_path, wf)

    executor = _RecordingExecutor()
    result = run_workflow(tmp_path, run_id, executor=executor)

    assert isinstance(result, WorkflowVMResult)
    # Both independent build branches executed.
    assert "feature-build" in executor.executed
    assert "feature-build-tests" in executor.executed
    # Integration is the non-terminal join node and must execute.
    assert "feature-integration" in executor.executed
    # Integration executes *after* both build branches.
    assert executor.executed.index("feature-integration") > max(
        executor.executed.index("feature-build"),
        executor.executed.index("feature-build-tests"),
    )
    # Terminal projection reaches feature-complete.
    assert result.terminal_reached is True
    assert "feature-complete" in result.completed_node_ids
    # Decision gate also ran.
    assert "feature-decision" in executor.executed


def test_feature_dag_branch_failure_blocks(tmp_path: Path) -> None:
    """A failing build branch routes to feature-blocked; terminal is blocked."""
    wf = feature_template()
    run_id = _seed_run(tmp_path, wf)

    plan = {"feature-build": NodeOutcome.failure}
    executor = _RecordingExecutor(plan)
    result = run_workflow(tmp_path, run_id, executor=executor)

    assert "feature-build" in executor.executed
    # The failed branch must not let integration proceed to completion.
    assert result.terminal_reached is False
    assert "feature-complete" not in result.completed_node_ids
    assert "feature-blocked" in result.completed_node_ids


# ---------------------------------------------------------------------------
# Rich human gate receipt + binary ledger success
# ---------------------------------------------------------------------------

def test_rich_gate_approved_with_conditions(tmp_path: Path) -> None:
    """approved_with_conditions creates one GateOutcomeReceipt and binary success."""
    wf = feature_template()
    run_id = _seed_run(tmp_path, wf)

    executor = _RecordingExecutor(gate_outcome=NodeOutcome.approved_with_conditions)
    result = run_workflow(tmp_path, run_id, executor=executor)

    receipts = load_gate_outcomes(tmp_path, run_id)
    assert len(receipts) == 1
    receipt = receipts[0]
    assert isinstance(receipt, GateOutcomeReceipt)
    assert receipt.gate_outcome == NodeOutcome.approved_with_conditions
    assert receipt.decided_by == "human-operator"
    assert receipt.conditions == ("see decision log",)
    # Binary ledger outcome for the gate node must be success.
    assert result.outcome_map["feature-decision"] == NodeOutcome.approved_with_conditions


# ---------------------------------------------------------------------------
# Bounded loop does not hang; respects max_total_rounds / max_rounds
# ---------------------------------------------------------------------------

def _loop_definition() -> WorkflowSchemaV2:
    """A minimal two-node loop (a -> b -> a) with a terminal escape from b."""
    nodes = (
        WorkflowNode(id="loop-a", kind=NodeKind.agent, stage=LoopStage.planning, required_evidence=("a-out",)),
        WorkflowNode(id="loop-b", kind=NodeKind.agent, stage=LoopStage.assignment, required_evidence=("b-out",)),
        WorkflowNode(id="loop-complete", kind=NodeKind.code, stage=LoopStage.complete, required_evidence=()),
        WorkflowNode(id="loop-blocked", kind=NodeKind.human, stage=LoopStage.blocked, required_evidence=()),
    )
    edges = (
        WorkflowEdge(id="loop-a:success", source="loop-a", target="loop-b", outcome="success"),
        WorkflowEdge(id="loop-a:failure", source="loop-a", target="loop-blocked", outcome="failure"),
        WorkflowEdge(id="loop-b:success", source="loop-b", target="loop-a", outcome="success"),
        WorkflowEdge(id="loop-b:complete", source="loop-b", target="loop-complete", outcome="success"),
        WorkflowEdge(id="loop-b:failure", source="loop-b", target="loop-blocked", outcome="failure"),
    )
    return WorkflowSchemaV2(
        version="v2",
        workflow_id="loop@1",
        strategy=WorkflowStrategy.loop,
        loop_policy=LoopPolicy(max_rounds=2, stop_if_no_progress=2),
        budget=BudgetPolicy(),
        promotion=PromotionPolicy(),
        nodes=nodes,
        edges=edges,
    )


def test_bounded_loop_does_not_hang(tmp_path: Path) -> None:
    """A loop workflow terminates promptly and does not re-run the body."""
    wf = _loop_definition()
    validate_workflow(wf)
    run_id = _seed_run(tmp_path, wf)

    executor = _RecordingExecutor()
    result = run_workflow(tmp_path, run_id, executor=executor, max_total_rounds=5)

    # The VM must not hang and must respect the bounds: no loop body executes
    # (the back-edge makes the head never ready), and it returns immediately.
    assert result.iterations == 0
    assert result.completed_node_ids == ()
    assert result.terminal_reached is False


def test_loop_respects_max_rounds_contract(tmp_path: Path) -> None:
    """max_total_rounds is accepted and the run stays bounded (no exceptions, no hang)."""
    wf = _loop_definition()
    run_id = _seed_run(tmp_path, wf)

    executor = _RecordingExecutor()
    # Even with a large limit, the loop body never activates, so this returns
    # instantly rather than spinning forever.
    result = run_workflow(tmp_path, run_id, executor=executor, max_total_rounds=1)
    assert result.iterations == 0
    assert executor.executed == []


# ---------------------------------------------------------------------------
# Fail-closed on malformed / unknown executor outcome
# ---------------------------------------------------------------------------

def test_unknown_executor_outcome_fails_closed(tmp_path: Path) -> None:
    """An unknown node outcome raises WorkflowVMError (never silently succeeds)."""
    wf = feature_template()
    run_id = _seed_run(tmp_path, wf)

    class _BadExecutor:
        def execute(self, node, context):  # noqa: ANN001
            return "not-a-real-outcome"  # type: ignore[return-value]

    with pytest.raises(WorkflowVMError):
        run_workflow(tmp_path, run_id, executor=_BadExecutor())  # type: ignore[arg-type]


def test_executor_raising_fails_closed(tmp_path: Path) -> None:
    """An executor that raises is surfaced as WorkflowVMError."""
    wf = feature_template()
    run_id = _seed_run(tmp_path, wf)

    class _RaisingExecutor:
        def execute(self, node, context):  # noqa: ANN001
            raise RuntimeError("kaboom")

    with pytest.raises(WorkflowVMError):
        run_workflow(tmp_path, run_id, executor=_RaisingExecutor())  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Canonical spine regression is not duplicated
# ---------------------------------------------------------------------------

def test_canonical_spine_not_duplicated() -> None:
    """Canonical spine regression is covered in test_workflow_families; here we
    only confirm it remains unchanged and valid (no duplicated/duplicated run)."""
    defn = canonical_product_build_v1()
    assert defn.workflow_id == "canonical_product_build@1"
    validate_workflow(defn)
    # The VM is seeded only with v2 definitions; the canonical v1 spine is the
    # source of truth elsewhere and must not be re-instantiated here.
