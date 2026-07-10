"""Canonical DevFlow role definitions.

Roles are the stable, permanent concepts in the pipeline. They define
responsibilities and the capabilities required to perform them. They do
NOT define implementation — that is the job of the routing layer.

A role definition specifies:
  - required_capabilities: a model MUST have all of these to be eligible
  - preferred_cost_classes: routing preference order (cheapest first)
  - preferred_transports: routing preference order
  - output_size: "small" or "large" — informs token budgeting
  - reasoning: whether this role benefits from chain-of-thought
  - fallbacks: roles that can substitute in a pinch (capability subset)

Adding a new role: add a RoleDefinition here. No pipeline code changes.
Changing a role's requirements: edit here. No pipeline code changes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional




@dataclass(frozen=True)
class RoleDefinition:
    """What a role requires and prefers (not what model runs it)."""

    name: str
    description: str
    required_capabilities: tuple[str, ...]
    preferred_cost_classes: tuple[str, ...]
    preferred_transports: tuple[str, ...] = ()
    output_size: str = "small"  # "small" (reasoning) or "large" (generation)
    reasoning: bool = False
    fallbacks: tuple[str, ...] = field(default_factory=tuple)


# ---------------------------------------------------------------------------
# Cost-class preference shortcuts
# ---------------------------------------------------------------------------
# Builder / generation roles: prefer local first, then free cloud, then
# subscription. Avoid metered frontier for bulk generation.
_GENERATION_PREFS = (
    "local",
    "free_cloud",
    "included_subscription",
    "metered_low",
    "metered_high",
)

# Reasoning / judgment roles: prefer subscription (already paid), then local.
# These are small-output, high-value tasks.
_REASONING_PREFS = (
    "included_subscription",
    "local",
    "free_cloud",
    "metered_low",
    "metered_high",
)


# ---------------------------------------------------------------------------
# Canonical roles
# ---------------------------------------------------------------------------
BRAINSTORM = RoleDefinition(
    name="brainstorm",
    description="Initial idea refinement and ambiguity resolution.",
    required_capabilities=(
        "high_level_reasoning",
        "ambiguity_resolution",
    ),
    preferred_cost_classes=_REASONING_PREFS,
    preferred_transports=("hermes-chat",),
    output_size="small",
    reasoning=True,
)

PLANNER = RoleDefinition(
    name="planner",
    description="Architecture, specification writing, and task decomposition.",
    required_capabilities=(
        "architecture",
        "specification_writing",
        "structured_planning",
        "decomposition",
    ),
    preferred_cost_classes=_GENERATION_PREFS,
    preferred_transports=("openai-http", "hermes-chat"),
    output_size="large",
    reasoning=False,
    fallbacks=("brainstorm",),
)

PLANNING_JUDGE = RoleDefinition(
    name="planning_judge",
    description="Specification review, gap detection, and structured reasoning.",
    required_capabilities=(
        "spec_review",
        "gap_detection",
        "structured_reasoning",
    ),
    preferred_cost_classes=_REASONING_PREFS,
    preferred_transports=("openai-http", "hermes-chat"),
    output_size="small",
    reasoning=True,
)

BUILDER = RoleDefinition(
    name="builder",
    description="Code generation, repository-aware implementation, edit planning.",
    required_capabilities=(
        "code_generation",
        "structured_output",
        "edit_planning",
    ),
    preferred_cost_classes=_GENERATION_PREFS,
    preferred_transports=("openai-http",),
    output_size="large",
    reasoning=False,
)

BUILD_JUDGE = RoleDefinition(
    name="build_judge",
    description="Implementation review, repository reasoning, correctness evaluation.",
    required_capabilities=(
        "implementation_review",
        "repository_reasoning",
        "correctness_evaluation",
    ),
    preferred_cost_classes=_REASONING_PREFS,
    preferred_transports=("openai-http", "hermes-chat"),
    output_size="small",
    reasoning=True,
)

VERIFIER = RoleDefinition(
    name="verifier",
    description="Evidence review, deterministic verification, structured output.",
    required_capabilities=(
        "evidence_review",
        "structured_output",
    ),
    preferred_cost_classes=_REASONING_PREFS,
    preferred_transports=("hermes-chat", "openai-http"),
    output_size="small",
    reasoning=True,
)

FINAL_JUDGE = RoleDefinition(
    name="final_judge",
    description="High-level reasoning, evidence synthesis, and decision making.",
    required_capabilities=(
        "high_level_reasoning",
        "evidence_synthesis",
        "decision_making",
    ),
    preferred_cost_classes=_REASONING_PREFS,
    preferred_transports=("hermes-chat",),
    output_size="small",
    reasoning=True,
)


# ---------------------------------------------------------------------------
# Registry of all canonical roles
# ---------------------------------------------------------------------------
ROLES: dict[str, RoleDefinition] = {
    r.name: r
    for r in (
        BRAINSTORM,
        PLANNER,
        PLANNING_JUDGE,
        BUILDER,
        BUILD_JUDGE,
        VERIFIER,
        FINAL_JUDGE,
    )
}


def get_role(name: str) -> Optional[RoleDefinition]:
    """Look up a role by canonical name."""
    return ROLES.get(name)


def known_roles() -> tuple[str, ...]:
    """All canonical role names."""
    return tuple(ROLES.keys())


def role_requires(role_name: str) -> tuple[str, ...]:
    """Return the capabilities a role requires. Raises ValueError if unknown."""
    role = ROLES.get(role_name)
    if role is None:
        raise ValueError(
            f"Unknown DevFlow role '{role_name}'. Known roles: {', '.join(known_roles())}"
        )
    return role.required_capabilities


__all__ = [
    "RoleDefinition",
    "ROLES",
    "get_role",
    "known_roles",
    "role_requires",
]
