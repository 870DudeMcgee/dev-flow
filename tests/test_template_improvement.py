"""Tests for human-approved template refinements (M7-S2)."""

from __future__ import annotations

from pathlib import Path

import pytest

from devflow.control_plane.template_refinement import (
    REFINEMENT_APPROVALS_FILE,
    RefinementApproval,
    RefinementKind,
    TemplateRefinement,
    can_apply_refinement,
    format_refinement_for_display,
    load_refinement_approvals,
    propose_refinements,
    record_refinement_approval,
)
from devflow.loop.metrics_aggregator import WorkflowMetrics
from devflow.loop.workflow_library import get_template, list_templates


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _metrics(
    retries: int = 0,
    duration_seconds: float = 600.0,
    interventions: int = 0,
    repair_rounds: int = 0,
) -> WorkflowMetrics:
    return WorkflowMetrics(
        run_id="run-1",
        total_duration_seconds=duration_seconds,
        total_tokens=1000,
        retry_count=retries,
        repair_rounds=repair_rounds,
        human_interventions=interventions,
    )


def _approval(
    refinement_id: str = "ref-1",
    status: str = "pending",
    actor: str = "operator-alice",
) -> RefinementApproval:
    return RefinementApproval(
        refinement_id=refinement_id,
        template_id="hotfix@1",
        status=status,  # type: ignore[arg-type]
        actor=actor,
    )


# ---------------------------------------------------------------------------
# Approval tests
# ---------------------------------------------------------------------------

def test_refinement_requires_human() -> None:
    """can_apply False without approval."""
    approval = _approval(status="pending")
    assert can_apply_refinement(approval) is False


def test_refinement_approved() -> None:
    """approved → can_apply True."""
    approval = _approval(status="approved")
    assert can_apply_refinement(approval) is True


def test_refinement_rejected() -> None:
    """rejected → can_apply False."""
    approval = _approval(status="rejected")
    assert can_apply_refinement(approval) is False


def test_actor_cannot_be_system() -> None:
    """model_validator rejects 'system'."""
    with pytest.raises(Exception, match="human operator"):
        RefinementApproval(
            refinement_id="ref-1",
            template_id="hotfix@1",
            status="pending",
            actor="system",
        )


# ---------------------------------------------------------------------------
# Proposal heuristic tests
# ---------------------------------------------------------------------------

def test_propose_retry_heavy() -> None:
    """High retries → budget_adjustment."""
    history = (
        _metrics(retries=5),
        _metrics(retries=4),
        _metrics(retries=6),
    )
    refinements = propose_refinements("hotfix@1", history)

    assert len(refinements) >= 1
    assert any(r.kind == RefinementKind.budget_adjustment for r in refinements)
    assert any("repair" in r.description.lower() or "retry" in r.description.lower() for r in refinements)


def test_propose_slow_low_retries() -> None:
    """Slow with low retries → phase_reorder."""
    history = (
        _metrics(retries=1, duration_seconds=9000),  # 150 min
        _metrics(retries=0, duration_seconds=8400),  # 140 min
    )
    refinements = propose_refinements("feature@1", history)

    assert len(refinements) >= 1
    assert any(r.kind == RefinementKind.phase_reorder for r in refinements)


def test_propose_frequent_interventions() -> None:
    """Frequent interventions → node_addition."""
    history = (
        _metrics(interventions=3),
        _metrics(interventions=2),
    )
    refinements = propose_refinements("bug@1", history)

    assert len(refinements) >= 1
    assert any(r.kind == RefinementKind.node_addition for r in refinements)


def test_propose_no_refinements_normal() -> None:
    """Normal metrics → empty tuple."""
    history = (
        _metrics(retries=1, duration_seconds=600, interventions=0),
        _metrics(retries=0, duration_seconds=500, interventions=0),
    )
    refinements = propose_refinements("chore@1", history)

    assert refinements == ()


def test_propose_empty_history() -> None:
    """No metrics → empty tuple."""
    assert propose_refinements("hotfix@1", ()) == ()


# ---------------------------------------------------------------------------
# Persistence tests
# ---------------------------------------------------------------------------

def test_record_approval_persists(tmp_path: Path) -> None:
    """Saved to control-plane dir."""
    approval = _approval()
    record_refinement_approval(tmp_path, approval)

    events_path = tmp_path / ".devflow" / "control-plane" / REFINEMENT_APPROVALS_FILE
    assert events_path.is_file()

    loaded = load_refinement_approvals(tmp_path)
    assert len(loaded) == 1
    assert loaded[0].refinement_id == "ref-1"


def test_record_approval_idempotent(tmp_path: Path) -> None:
    """Replay → idempotent."""
    approval = _approval()
    record_refinement_approval(tmp_path, approval)
    record_refinement_approval(tmp_path, approval)

    assert len(load_refinement_approvals(tmp_path)) == 1


def test_record_approval_conflicting_rejected(tmp_path: Path) -> None:
    """Different approval for same refinement → ValueError."""
    record_refinement_approval(tmp_path, _approval(status="pending"))
    with pytest.raises(ValueError, match="conflicting"):
        record_refinement_approval(tmp_path, _approval(status="approved", actor="operator-bob"))


def test_load_approvals_empty(tmp_path: Path) -> None:
    """No approvals → empty tuple."""
    assert load_refinement_approvals(tmp_path) == ()


# ---------------------------------------------------------------------------
# Library safety tests
# ---------------------------------------------------------------------------

def test_proposal_does_not_modify_library() -> None:
    """Proposing doesn't change WORKFLOW_LIBRARY."""
    templates_before = list_templates()
    hotfix_before = get_template("hotfix@1")

    history = (_metrics(retries=10, interventions=5),)
    propose_refinements("hotfix@1", history)

    templates_after = list_templates()
    hotfix_after = get_template("hotfix@1")

    assert templates_before == templates_after
    assert hotfix_before == hotfix_after


# ---------------------------------------------------------------------------
# Immutability tests
# ---------------------------------------------------------------------------

def test_template_refinement_frozen() -> None:
    """TemplateRefinement is immutable."""
    r = TemplateRefinement(
        refinement_id="ref-1",
        template_id="hotfix@1",
        kind=RefinementKind.budget_adjustment,
        description="test",
        confidence=0.5,
    )
    with pytest.raises(Exception):
        r.description = "modified"  # type: ignore[misc]


def test_refinement_approval_frozen() -> None:
    """RefinementApproval is immutable."""
    approval = _approval()
    with pytest.raises(Exception):
        approval.status = "approved"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Display format test
# ---------------------------------------------------------------------------

def test_format_refinement_for_display() -> None:
    """Human-readable Markdown format."""
    refinement = TemplateRefinement(
        refinement_id="ref-1",
        template_id="hotfix@1",
        kind=RefinementKind.budget_adjustment,
        description="Increase max_repair_rounds",
        rationale="High retry count",
        confidence=0.8,
    )

    text = format_refinement_for_display(refinement)

    assert "### Proposed Refinement" in text
    assert "budget_adjustment" in text
    assert "80%" in text
    assert "requires explicit human approval" in text
