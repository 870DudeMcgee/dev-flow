"""Factory Router — binds lane/sandbox/model/resource/concurrency (M5-S2).

A composition layer that takes a workflow template + resolved role slots and
produces a single :class:`BoundExecutionPlan` for the runtime. This is NOT
model resolution — it composes existing :func:`~devflow.loop.routing.resolve_role`
outputs with :class:`~devflow.loop.workflow_schema.BudgetPolicy` and
:class:`~devflow.loop.capability_routes.CapabilityRoute` mappings.

All bindings use functional role names. Model identity lives behind an
``inspection_control`` field — not in primary display fields (naming rule).
"""

from __future__ import annotations

from typing import Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field

from devflow.loop.capability_routes import CapabilityRoute, route_for_role
from devflow.loop.routing import ResolvedSlot
from devflow.loop.workflow_schema import (
    BudgetPolicy,
    PromotionPolicy,
    WorkflowSchemaV2,
)


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

class LaneProfile(BaseModel):
    """One execution lane's resource and concurrency profile."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    lane_id: str = Field(min_length=1)
    heavy_model_slots: int = Field(default=1, ge=0, le=4)
    max_concurrent_sandboxes: int = Field(default=1, ge=1, le=8)
    network_default: Literal["denied", "allowed"] = "denied"


class RoleBinding(BaseModel):
    """One role's resolved capability route + model behind inspection control.

    Primary fields use functional role and capability route names only.
    Model/provider details are in ``inspection_control`` for technical
    diagnostics, never for visible workflow language.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    role: str = Field(min_length=1)
    capability_route: str = Field(min_length=1)

    # Technical inspection details — not for visible workflow language.
    resolved_model: str = ""
    provider: str = ""
    cost_class: str = ""
    resolved_via: str = ""


class BoundExecutionPlan(BaseModel):
    """Complete binding of a workflow to execution resources."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ticket_id: str = Field(min_length=1)
    workflow_id: str = Field(min_length=1)
    lane: LaneProfile
    role_bindings: tuple[RoleBinding, ...] = ()
    budget: BudgetPolicy = Field(default_factory=BudgetPolicy)
    promotion: PromotionPolicy = Field(default_factory=PromotionPolicy)
    sandbox_profile: Literal["workspace_write"] = "workspace_write"
    capability_routes: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Binding
# ---------------------------------------------------------------------------

def bind_execution_plan(
    ticket_id: str,
    workflow: WorkflowSchemaV2,
    role_slots: Mapping[str, ResolvedSlot],
) -> BoundExecutionPlan:
    """Bind a workflow template to execution resources.

    Parameters
    ----------
    ticket_id
        The control-plane ticket this plan belongs to.
    workflow
        A validated workflow template from the library.
    role_slots
        Mapping from functional role name to resolved model slot (output of
        existing :func:`~devflow.loop.routing.resolve_role`).

    Returns a :class:`BoundExecutionPlan` with lane, role bindings,
    capability routes, budget, and promotion policy — all composed from
    the template and resolved slots. No autonomous promotion.
    """
    # Build lane profile from workflow budget
    lane = LaneProfile(
        lane_id=f"lane-{workflow.workflow_id}",
        heavy_model_slots=workflow.budget.heavy_model_slots,
        max_concurrent_sandboxes=max(1, workflow.budget.heavy_model_slots),
        network_default="denied",
    )

    # Build role bindings from resolved slots
    bindings: list[RoleBinding] = []
    routes: set[str] = set()

    for role, slot in role_slots.items():
        try:
            route = route_for_role(role)
        except ValueError:
            continue  # skip unknown roles
        routes.add(route.value)
        bindings.append(RoleBinding(
            role=role,
            capability_route=route.value,
            resolved_model=slot.model_name,
            provider=slot.provider,
            cost_class=slot.cost_class,
            resolved_via=slot.resolved_via,
        ))

    return BoundExecutionPlan(
        ticket_id=ticket_id,
        workflow_id=workflow.workflow_id,
        lane=lane,
        role_bindings=tuple(bindings),
        budget=workflow.budget,
        promotion=workflow.promotion,
        sandbox_profile="workspace_write",
        capability_routes=tuple(sorted(routes)),
    )


__all__ = [
    "BoundExecutionPlan",
    "LaneProfile",
    "RoleBinding",
    "bind_execution_plan",
]
