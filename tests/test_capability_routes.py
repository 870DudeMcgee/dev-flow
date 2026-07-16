"""Tests for the six capability routes (M2-S4)."""

from __future__ import annotations

import pytest

from devflow.loop.capability_routes import (
    CapabilityRoute,
    ROLE_ROUTE_MAP,
    all_routes,
    describe_route,
    route_for_role,
)
from devflow.loop.roles import known_roles
from devflow.loop.routing import ResolvedSlot


# ---------------------------------------------------------------------------
# Route enum tests
# ---------------------------------------------------------------------------

def test_six_routes_typed() -> None:
    """All 6 blueprint routes exist as enum values."""
    routes = {r.value for r in CapabilityRoute}
    assert routes == {
        "repository_analysis",
        "deep_planning",
        "bounded_coding",
        "independent_review",
        "frontier_judgment",
        "cheap_summary",
    }


def test_all_routes_count() -> None:
    """all_routes() returns exactly 6 routes."""
    assert len(all_routes()) == 6


def test_all_routes_in_canonical_order() -> None:
    """Routes returned in the enum definition order."""
    routes = all_routes()
    assert routes[0] == CapabilityRoute.repository_analysis
    assert routes[5] == CapabilityRoute.cheap_summary


# ---------------------------------------------------------------------------
# Role → route mapping tests
# ---------------------------------------------------------------------------

def test_route_for_each_role() -> None:
    """Every known role maps to a route."""
    for role_name in known_roles():
        route = route_for_role(role_name)
        assert isinstance(route, CapabilityRoute)


def test_route_for_unknown_role_raises() -> None:
    """Unknown role → ValueError."""
    with pytest.raises(ValueError, match="no capability route"):
        route_for_role("nonexistent_role")


def test_role_route_map_covers_all_roles() -> None:
    """ROLE_ROUTE_MAP covers every role in the registry."""
    for role_name in known_roles():
        assert role_name in ROLE_ROUTE_MAP


def test_role_route_map_uses_functional_names_only() -> None:
    """No model names appear in the route map (naming rule)."""
    for role_name in ROLE_ROUTE_MAP:
        # Role names must be functional, not model-derived
        assert role_name in known_roles()


# ---------------------------------------------------------------------------
# Route description tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("route", list(CapabilityRoute))
def test_route_has_description(route: CapabilityRoute) -> None:
    """Every route has a human-readable description."""
    desc = describe_route(route)
    assert isinstance(desc, str)
    assert len(desc) > 10


def test_repository_analysis_route() -> None:
    desc = describe_route(CapabilityRoute.repository_analysis)
    assert "Codebase" in desc or "inventory" in desc.lower()


def test_deep_planning_route() -> None:
    desc = describe_route(CapabilityRoute.deep_planning)
    assert "Specification" in desc or "architecture" in desc.lower()


def test_bounded_coding_route() -> None:
    desc = describe_route(CapabilityRoute.bounded_coding)
    assert "Implement" in desc or "slice" in desc.lower()


def test_independent_review_route() -> None:
    desc = describe_route(CapabilityRoute.independent_review)
    assert "Review" in desc or "different model family" in desc


def test_frontier_judgment_route() -> None:
    desc = describe_route(CapabilityRoute.frontier_judgment)
    assert "ambiguity" in desc.lower() or "frontier" in desc.lower()


def test_cheap_summary_route() -> None:
    desc = describe_route(CapabilityRoute.cheap_summary)
    assert "concise" in desc.lower() or "status" in desc.lower()


def test_descriptions_contain_no_model_names() -> None:
    """Route descriptions use functional terms only (naming rule)."""
    forbidden = {"qwen", "qwopus", "ornith", "glm", "gpt", "llama", "codex"}
    for route in CapabilityRoute:
        desc = describe_route(route).lower()
        for name in forbidden:
            assert name not in desc, f"Route {route.value} description contains {name!r}"


# ---------------------------------------------------------------------------
# ResolvedSlot integration tests
# ---------------------------------------------------------------------------

def test_route_in_resolved_slot() -> None:
    """resolve_role records capability_route when set."""
    slot = ResolvedSlot(
        role="builder",
        model_name="test-model",
        provider="test",
        endpoint="localhost",
        transport="http",
        cost_class="free_cloud",
        resolved_via="auto",
        capability_route=CapabilityRoute.bounded_coding,
    )
    assert slot.capability_route == CapabilityRoute.bounded_coding


def test_legacy_callers_unaffected() -> None:
    """Callers not setting capability_route get None (backward compatible)."""
    slot = ResolvedSlot(
        role="builder",
        model_name="test-model",
        provider="test",
        endpoint="localhost",
        transport="http",
        cost_class="free_cloud",
        resolved_via="auto",
    )
    assert slot.capability_route is None


def test_resolved_slot_frozen() -> None:
    """ResolvedSlot is still immutable."""
    slot = ResolvedSlot(
        role="builder",
        model_name="test",
        provider="test",
        endpoint="localhost",
        transport="http",
        cost_class="free_cloud",
        resolved_via="auto",
        capability_route=CapabilityRoute.bounded_coding,
    )
    with pytest.raises(Exception):
        slot.capability_route = None  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Mapping semantic tests
# ---------------------------------------------------------------------------

def test_builder_maps_to_bounded_coding() -> None:
    assert route_for_role("builder") == CapabilityRoute.bounded_coding


def test_judge_maps_to_independent_review() -> None:
    assert route_for_role("build_judge") == CapabilityRoute.independent_review
    assert route_for_role("planning_judge") == CapabilityRoute.independent_review


def test_verifier_maps_to_independent_review() -> None:
    assert route_for_role("verifier") == CapabilityRoute.independent_review


def test_planner_maps_to_deep_planning() -> None:
    assert route_for_role("planner") == CapabilityRoute.deep_planning


def test_final_judge_maps_to_frontier() -> None:
    assert route_for_role("final_judge") == CapabilityRoute.frontier_judgment
