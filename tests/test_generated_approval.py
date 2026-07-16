"""Tests for resource estimation + visible approval gate (M6-S2)."""

from __future__ import annotations

from pathlib import Path

import pytest

from devflow.control_plane.generated_approval import (
    APPROVAL_EVENTS_FILE,
    GeneratedApproval,
    ResourceEstimate,
    approval_required,
    can_execute,
    estimate_resources,
    format_estimate_for_display,
    load_approvals,
    record_approval,
)
from devflow.loop.workflow_definition import NodeKind
from devflow.loop.workflow_generator import generate_workflow
from devflow.loop.workflow_generator import GenerationRequest
from devflow.loop.workflow_schema import (
    BudgetPolicy,
    PromotionPolicy,
    WorkflowSchemaV2,
    WorkflowStrategy,
)
from devflow.loop.workflow_definition import (
    WorkflowEdge,
    WorkflowNode,
)
from devflow.loop.models import LoopStage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _workflow(
    node_count: int = 5,
    include_gate: bool = False,
    strategy: WorkflowStrategy = WorkflowStrategy.sequence,
) -> WorkflowSchemaV2:
    """Build a minimal valid WorkflowSchemaV2 for estimation tests."""
    nodes: list[WorkflowNode] = []
    for i in range(node_count):
        kind = NodeKind.human_gate if (include_gate and i == node_count - 1) else NodeKind.agent
        nodes.append(WorkflowNode(
            id=f"gen-node-{i}",
            kind=kind,
            stage=LoopStage.spec,
            required_evidence=(f"output-{i}",),
        ))
    nodes.append(WorkflowNode(id="gen-complete", kind=NodeKind.code, stage=LoopStage.complete, required_evidence=()))
    nodes.append(WorkflowNode(id="gen-blocked", kind=NodeKind.human, stage=LoopStage.blocked, required_evidence=()))

    edges: list[WorkflowEdge] = []
    body_ids = [n.id for n in nodes if n.id not in ("gen-complete", "gen-blocked")]
    for i in range(len(body_ids) - 1):
        edges.append(WorkflowEdge(id=f"{body_ids[i]}:success", source=body_ids[i], target=body_ids[i + 1], outcome="success"))
        edges.append(WorkflowEdge(id=f"{body_ids[i]}:failure", source=body_ids[i], target="gen-blocked", outcome="failure"))
    if body_ids:
        edges.append(WorkflowEdge(id=f"{body_ids[-1]}:success", source=body_ids[-1], target="gen-complete", outcome="success"))
        edges.append(WorkflowEdge(id=f"{body_ids[-1]}:failure", source=body_ids[-1], target="gen-blocked", outcome="failure"))

    return WorkflowSchemaV2(
        version="v2",
        workflow_id="generated:gen-test-0001",
        strategy=strategy,
        budget=BudgetPolicy(max_runtime_minutes=120, max_agent_runs=20, max_repair_rounds=3, heavy_model_slots=1),
        promotion=PromotionPolicy(human_required=True, auto_promote=False),
        nodes=tuple(nodes),
        edges=tuple(edges),
    )


def _approval(
    generation_id: str = "gen-test-0001",
    status: str = "pending",
    actor: str = "operator-alice",
) -> GeneratedApproval:
    return GeneratedApproval(
        generation_id=generation_id,
        ticket_id="t-1",
        workflow_id="generated:gen-test-0001",
        status=status,  # type: ignore[arg-type]
        actor=actor,
    )


# ---------------------------------------------------------------------------
# Resource estimation tests
# ---------------------------------------------------------------------------

def test_estimate_resources_basic() -> None:
    """Estimate from node count."""
    wf = _workflow(node_count=5)
    estimate = estimate_resources(wf, "gen-test-0001")

    assert estimate.estimated_duration_minutes >= 1
    assert estimate.estimated_agent_runs >= 1
    assert estimate.estimated_heavy_model_hours >= 0.0


def test_estimate_risk_low() -> None:
    """Few nodes → low risk."""
    wf = _workflow(node_count=3)
    estimate = estimate_resources(wf, "gen-test-0001")

    assert estimate.risk_level == "low"


def test_estimate_risk_medium() -> None:
    """Gates or moderate size → medium risk."""
    wf = _workflow(node_count=5, include_gate=True)
    estimate = estimate_resources(wf, "gen-test-0001")

    assert estimate.risk_level == "medium"


def test_estimate_risk_high() -> None:
    """Large node count → high risk."""
    wf = _workflow(node_count=14)
    estimate = estimate_resources(wf, "gen-test-0001")

    assert estimate.risk_level == "high"
    assert "large node count" in estimate.risk_factors


def test_estimate_risk_high_dag() -> None:
    """DAG with moderate complexity → high risk."""
    wf = _workflow(node_count=8, strategy=WorkflowStrategy.dag)
    estimate = estimate_resources(wf, "gen-test-0001")

    assert estimate.risk_level == "high"


def test_authority_always_capped() -> None:
    """authority_capped is always True."""
    wf = _workflow()
    estimate = estimate_resources(wf, "gen-test-0001")

    assert estimate.authority_capped is True


# ---------------------------------------------------------------------------
# approval_required tests
# ---------------------------------------------------------------------------

def test_approval_required_for_generated() -> None:
    """Generated class → True."""
    assert approval_required("generated:gen-test-0001") is True


def test_approval_not_required_for_fixed() -> None:
    """Fixed/parameterized → False."""
    assert approval_required("canonical_product_build@1") is False
    assert approval_required("hotfix@1") is False
    assert approval_required("feature@1") is False


# ---------------------------------------------------------------------------
# can_execute tests
# ---------------------------------------------------------------------------

def test_can_execute_requires_approved() -> None:
    """Pending → False."""
    approval = _approval(status="pending")
    estimate = ResourceEstimate(
        generation_id="gen-test-0001",
        estimated_duration_minutes=30,
        estimated_agent_runs=5,
        estimated_heavy_model_hours=0.5,
        risk_level="low",
    )

    assert can_execute(approval, estimate) is False


def test_can_execute_approved() -> None:
    """Approved + capped → True."""
    approval = _approval(status="approved")
    estimate = ResourceEstimate(
        generation_id="gen-test-0001",
        estimated_duration_minutes=30,
        estimated_agent_runs=5,
        estimated_heavy_model_hours=0.5,
        risk_level="low",
    )

    assert can_execute(approval, estimate) is True


def test_cannot_execute_rejected() -> None:
    """Rejected → False."""
    approval = _approval(status="rejected")
    estimate = ResourceEstimate(
        generation_id="gen-test-0001",
        estimated_duration_minutes=30,
        estimated_agent_runs=5,
        estimated_heavy_model_hours=0.5,
        risk_level="low",
    )

    assert can_execute(approval, estimate) is False


# ---------------------------------------------------------------------------
# Actor validation
# ---------------------------------------------------------------------------

def test_actor_cannot_be_system() -> None:
    """model_validator rejects 'system'."""
    with pytest.raises(Exception, match="human operator"):
        GeneratedApproval(
            generation_id="gen-1",
            ticket_id="t-1",
            workflow_id="generated:gen-1",
            status="pending",
            actor="system",
        )


# ---------------------------------------------------------------------------
# Persistence tests
# ---------------------------------------------------------------------------

def test_record_approval_persists(tmp_path: Path) -> None:
    """Saved to control-plane dir."""
    approval = _approval()
    record_approval(tmp_path, approval)

    events_path = tmp_path / ".devflow" / "control-plane" / "generated-approvals" / APPROVAL_EVENTS_FILE
    assert events_path.is_file()

    loaded = load_approvals(tmp_path)
    assert len(loaded) == 1
    assert loaded[0].generation_id == "gen-test-0001"


def test_record_approval_idempotent(tmp_path: Path) -> None:
    """Replay → idempotent."""
    approval = _approval()
    record_approval(tmp_path, approval)
    record_approval(tmp_path, approval)

    assert len(load_approvals(tmp_path)) == 1


def test_record_approval_conflicting_rejected(tmp_path: Path) -> None:
    """Different approval for same generation → ValueError."""
    record_approval(tmp_path, _approval(status="pending"))
    with pytest.raises(ValueError, match="conflicting"):
        record_approval(tmp_path, _approval(status="approved", actor="operator-bob"))


def test_load_approvals_empty(tmp_path: Path) -> None:
    """No approvals → empty tuple."""
    assert load_approvals(tmp_path) == ()


# ---------------------------------------------------------------------------
# Authority cap tests
# ---------------------------------------------------------------------------

def test_generated_cannot_self_promote() -> None:
    """Generated workflow's promotion policy enforces auto_promote=False."""
    req = GenerationRequest(
        task_description="Test",
        ticket_id="t-1",
        required_capabilities=("bounded_coding",),
    )
    result = generate_workflow(req)

    assert result.workflow is not None
    assert result.workflow.promotion.auto_promote is False


def test_generated_budget_within_policy() -> None:
    """Budget ≤ policy maximums (enforced by M2 validator bounds)."""
    req = GenerationRequest(
        task_description="Test",
        ticket_id="t-1",
        required_capabilities=("bounded_coding", "deep_planning", "independent_review"),
    )
    result = generate_workflow(req)

    assert result.workflow is not None
    assert result.workflow.budget.max_runtime_minutes <= 480
    assert result.workflow.budget.max_agent_runs <= 60
    assert result.workflow.budget.max_repair_rounds <= 5


# ---------------------------------------------------------------------------
# Immutability tests
# ---------------------------------------------------------------------------

def test_resource_estimate_frozen() -> None:
    """ResourceEstimate is immutable."""
    estimate = ResourceEstimate(
        generation_id="gen-1",
        estimated_duration_minutes=30,
        estimated_agent_runs=5,
        estimated_heavy_model_hours=0.5,
        risk_level="low",
    )
    with pytest.raises(Exception):
        estimate.risk_level = "high"  # type: ignore[misc]


def test_generated_approval_frozen() -> None:
    """GeneratedApproval is immutable."""
    approval = _approval()
    with pytest.raises(Exception):
        approval.status = "approved"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Display format test
# ---------------------------------------------------------------------------

def test_format_estimate_for_display() -> None:
    """Human-readable Markdown format."""
    estimate = ResourceEstimate(
        generation_id="gen-1",
        estimated_duration_minutes=45,
        estimated_agent_runs=8,
        estimated_heavy_model_hours=0.75,
        risk_level="medium",
        risk_factors=("includes gates",),
    )

    text = format_estimate_for_display(estimate)

    assert "### Resource Estimate" in text
    assert "45 minutes" in text
    assert "**medium**" in text
    assert "Authority capped" in text


# ---------------------------------------------------------------------------
# Adversarial RED tests: trust-binding vulnerabilities (M6-S2)
# ---------------------------------------------------------------------------

def test_can_execute_rejects_generation_mismatch() -> None:
    """can_execute must reject an approval whose generation_id != estimate's.

    Approval and estimate are bound to the same generation. Approving
    generation A but executing generation B's estimate is a trust-binding
    violation: the approval does not authorize that estimate. Even when both
    are approved and authority-capped, a generation_id mismatch must force
    can_execute to return False.
    """
    approval = _approval(generation_id="gen-A", status="approved")
    estimate = ResourceEstimate(
        generation_id="gen-B",
        estimated_duration_minutes=30,
        estimated_agent_runs=5,
        estimated_heavy_model_hours=0.5,
        risk_level="low",
    )

    assert can_execute(approval, estimate) is False
