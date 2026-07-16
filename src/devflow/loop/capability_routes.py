"""Six provider-independent capability routes (M2-S4, blueprint §7.4).

Workflow definitions request *capabilities* rather than hardcoding providers.
This module defines the six blueprint routes and maps each DevFlow role to
its primary route. The routing layer records which route was used as
provenance.

All names are functional — no model identity (per the user's naming rule).
"""

from __future__ import annotations

from enum import Enum


class CapabilityRoute(str, Enum):
    """Provider-independent capability routes (blueprint §7.4).

    A workflow requests a capability; the routing configuration resolves the
    current model or tool. This separation lets DevFlow switch providers,
    local models, or frontier models without changing orchestration logic.
    """

    repository_analysis = "repository_analysis"
    deep_planning = "deep_planning"
    bounded_coding = "bounded_coding"
    independent_review = "independent_review"
    frontier_judgment = "frontier_judgment"
    cheap_summary = "cheap_summary"


# ---------------------------------------------------------------------------
# Route descriptions (for documentation / UI tooltips — never model names)
# ---------------------------------------------------------------------------

_ROUTE_DESCRIPTIONS: dict[CapabilityRoute, str] = {
    CapabilityRoute.repository_analysis: (
        "Codebase inventory, symbol tracing, test discovery. "
        "Typically resolved to a small or medium local reasoning model "
        "plus deterministic search tools."
    ),
    CapabilityRoute.deep_planning: (
        "Specification synthesis, architecture, implementation DAG. "
        "Typically resolved to a strong planning model; local or frontier "
        "depending on risk and complexity."
    ),
    CapabilityRoute.bounded_coding: (
        "Implement one approved slice in an isolated workspace. "
        "Typically resolved to a coding-specialized local or cloud model."
    ),
    CapabilityRoute.independent_review: (
        "Review diff and evidence without the builder's narrative. "
        "Must resolve to a different model family or reviewer configuration."
    ),
    CapabilityRoute.frontier_judgment: (
        "Resolve difficult ambiguity, policy exception, or final high-risk "
        "verdict. Typically resolved to an explicitly authorized frontier "
        "model or human."
    ),
    CapabilityRoute.cheap_summary: (
        "Generate concise status and projection text. "
        "Typically resolved to a small local model or deterministic template."
    ),
}


# ---------------------------------------------------------------------------
# Role → route mapping
# ---------------------------------------------------------------------------

# Maps each DevFlow functional role to its primary capability route.
# All names are functional — no model identity.
ROLE_ROUTE_MAP: dict[str, CapabilityRoute] = {
    "brainstorm": CapabilityRoute.deep_planning,
    "planner": CapabilityRoute.deep_planning,
    "planning_judge": CapabilityRoute.independent_review,
    "builder": CapabilityRoute.bounded_coding,
    "build_judge": CapabilityRoute.independent_review,
    "verifier": CapabilityRoute.independent_review,
    "final_judge": CapabilityRoute.frontier_judgment,
}


def route_for_role(role_name: str) -> CapabilityRoute:
    """Return the capability route for a functional role.

    Raises ``ValueError`` for unknown roles.
    """
    if role_name not in ROLE_ROUTE_MAP:
        raise ValueError(
            f"no capability route mapped for role {role_name!r}. "
            f"Known roles: {', '.join(sorted(ROLE_ROUTE_MAP))}"
        )
    return ROLE_ROUTE_MAP[role_name]


def describe_route(route: CapabilityRoute) -> str:
    """Return a human-readable description of a capability route.

    This description uses only functional terms — no model names.
    """
    return _ROUTE_DESCRIPTIONS.get(
        route,
        f"Capability route: {route.value}",
    )


def all_routes() -> tuple[CapabilityRoute, ...]:
    """Return all six capability routes in canonical order."""
    return tuple(CapabilityRoute)


__all__ = [
    "CapabilityRoute",
    "ROLE_ROUTE_MAP",
    "all_routes",
    "describe_route",
    "route_for_role",
]
