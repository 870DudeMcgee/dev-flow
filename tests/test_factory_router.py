"""Tests for the Factory Router (M5-S2)."""

from __future__ import annotations

import pytest

from devflow.control_plane.factory_router import (
    BoundExecutionPlan,
    LaneProfile,
    RoleBinding,
    bind_execution_plan,
)
from devflow.loop.routing import ResolvedSlot
from devflow.loop.workflow_library import hotfix_template, feature_template
from devflow.loop.workflow_schema import PromotionPolicy


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _slot(
    role: str = "builder",
    model: str = "test-model",
    provider: str = "test-provider",
    cost_class: str = "free",
    resolved_via: str = "auto",
) -> ResolvedSlot:
    return ResolvedSlot(
        role=role,
        model_name=model,
        provider=provider,
        endpoint="http://localhost:8080",
        transport="http",
        cost_class=cost_class,
        resolved_via=resolved_via,
    )


def _role_slots() -> dict[str, ResolvedSlot]:
    return {
        "planner": _slot(role="planner", model="plan-model"),
        "planning_judge": _slot(role="planning_judge", model="judge-model"),
        "builder": _slot(role="builder", model="build-model"),
        "verifier": _slot(role="verifier", model="verify-model"),
        "final_judge": _slot(role="final_judge", model="final-model"),
    }


# ---------------------------------------------------------------------------
# Bind execution plan tests
# ---------------------------------------------------------------------------

def test_binds_lane_and_sandbox() -> None:
    """BoundExecutionPlan has lane + sandbox_profile."""
    plan = bind_execution_plan("t-1", hotfix_template(), _role_slots())

    assert isinstance(plan, BoundExecutionPlan)
    assert isinstance(plan.lane, LaneProfile)
    assert plan.sandbox_profile == "workspace_write"


def test_role_bindings_functional_names() -> None:
    """RoleBinding uses role names, not model names."""
    plan = bind_execution_plan("t-1", hotfix_template(), _role_slots())

    for binding in plan.role_bindings:
        assert binding.role in ("planner", "planning_judge", "builder", "verifier", "final_judge")
        # capability_route is a functional name
        assert binding.capability_route in (
            "deep_planning", "independent_review", "bounded_coding", "frontier_judgment",
        )


def test_heavy_slots_from_budget() -> None:
    """lane.heavy_model_slots matches workflow budget."""
    plan = bind_execution_plan("t-1", hotfix_template(), _role_slots())

    assert plan.lane.heavy_model_slots == hotfix_template().budget.heavy_model_slots


def test_concurrent_sandboxes_from_budget() -> None:
    """max_concurrent_sandboxes derived from heavy_model_slots."""
    plan = bind_execution_plan("t-1", hotfix_template(), _role_slots())

    assert plan.lane.max_concurrent_sandboxes >= 1
    assert plan.lane.max_concurrent_sandboxes == hotfix_template().budget.heavy_model_slots


def test_capability_routes_recorded() -> None:
    """All routes present in the plan."""
    plan = bind_execution_plan("t-1", hotfix_template(), _role_slots())

    assert len(plan.capability_routes) > 0
    # Should include routes from the role slots
    assert "bounded_coding" in plan.capability_routes
    assert "deep_planning" in plan.capability_routes


def test_budget_inherited_from_workflow() -> None:
    """plan.budget == workflow.budget."""
    template = feature_template()
    plan = bind_execution_plan("t-1", template, _role_slots())

    assert plan.budget == template.budget


def test_no_auto_promote() -> None:
    """plan.promotion.auto_promote is False."""
    plan = bind_execution_plan("t-1", hotfix_template(), _role_slots())

    assert plan.promotion.auto_promote is False


def test_network_denied_by_default() -> None:
    """lane.network_default is 'denied'."""
    plan = bind_execution_plan("t-1", hotfix_template(), _role_slots())

    assert plan.lane.network_default == "denied"


def test_role_bindings_count() -> None:
    """All known roles get bindings."""
    plan = bind_execution_plan("t-1", hotfix_template(), _role_slots())

    assert len(plan.role_bindings) == 5  # planner, judge, builder, verifier, final


def test_unknown_roles_skipped() -> None:
    """Unknown roles are silently skipped (no crash)."""
    slots = _role_slots()
    slots["unknown_role"] = _slot(role="unknown_role", model="x")
    plan = bind_execution_plan("t-1", hotfix_template(), slots)

    assert len(plan.role_bindings) == 5  # only known roles


def test_model_details_behind_binding() -> None:
    """resolved_model is present but not in primary fields."""
    plan = bind_execution_plan("t-1", hotfix_template(), _role_slots())

    for binding in plan.role_bindings:
        if binding.role == "builder":
            assert binding.resolved_model == "build-model"
            assert binding.provider == "test-provider"


# ---------------------------------------------------------------------------
# Immutability tests
# ---------------------------------------------------------------------------

def test_bound_execution_plan_frozen() -> None:
    """BoundExecutionPlan is immutable."""
    plan = bind_execution_plan("t-1", hotfix_template(), _role_slots())
    with pytest.raises(Exception):
        plan.ticket_id = "modified"  # type: ignore[misc]


def test_lane_profile_frozen() -> None:
    """LaneProfile is immutable."""
    lane = LaneProfile(lane_id="test")
    with pytest.raises(Exception):
        lane.heavy_model_slots = 99  # type: ignore[misc]


def test_role_binding_frozen() -> None:
    """RoleBinding is immutable."""
    binding = RoleBinding(role="builder", capability_route="bounded_coding")
    with pytest.raises(Exception):
        binding.role = "modified"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Workflow_id and ticket_id tests
# ---------------------------------------------------------------------------

def test_workflow_id_recorded() -> None:
    """workflow_id matches template."""
    plan = bind_execution_plan("t-1", hotfix_template(), _role_slots())

    assert plan.workflow_id == "hotfix@1"


def test_ticket_id_recorded() -> None:
    """ticket_id from parameter."""
    plan = bind_execution_plan("t-special", hotfix_template(), _role_slots())

    assert plan.ticket_id == "t-special"
