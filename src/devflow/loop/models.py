"""Canonical DevFlow loop state model (V2-01).

One pipeline run's canonical state. Pure data — no filesystem I/O, no agent
runtime, no model routing.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Stage enum
# ---------------------------------------------------------------------------
class LoopStage(str, Enum):
    """All pipeline stages in canonical order.

    Compatibility/UI projection. The canonical workflow read model
    (:mod:`devflow.loop.read_model`) derives a richer public view from the
    ledger's :class:`~devflow.loop.workflow_ledger.WorkflowSnapshot` for
    canonical-marked runs; this enum is retained for noncanonical/historical
    compatibility and is not deleted.
    """

    idea = "idea"
    definition = "definition"
    spec = "spec"
    planning = "planning"
    planning_judge = "planning_judge"
    assignment = "assignment"
    build_judge = "build_judge"
    verification = "verification"
    human_decision = "human_decision"
    complete = "complete"
    blocked = "blocked"


# ---------------------------------------------------------------------------
# Forward-transition map (stage -> set of allowed next stages)
# ---------------------------------------------------------------------------
_VALID_TRANSITIONS: dict[LoopStage, set[LoopStage]] = {
    LoopStage.idea: {LoopStage.definition, LoopStage.blocked},
    LoopStage.definition: {LoopStage.spec, LoopStage.blocked},
    LoopStage.spec: {LoopStage.planning, LoopStage.blocked},
    LoopStage.planning: {LoopStage.planning_judge, LoopStage.blocked},
    LoopStage.planning_judge: {LoopStage.assignment, LoopStage.blocked},
    LoopStage.assignment: {LoopStage.build_judge, LoopStage.blocked},
    LoopStage.build_judge: {LoopStage.verification, LoopStage.blocked},
    LoopStage.verification: {LoopStage.human_decision, LoopStage.blocked},
    LoopStage.human_decision: {LoopStage.complete, LoopStage.blocked},
    LoopStage.complete: set(),
    LoopStage.blocked: {
        LoopStage.idea,
        LoopStage.definition,
        LoopStage.spec,
        LoopStage.planning,
        LoopStage.planning_judge,
        LoopStage.assignment,
        LoopStage.build_judge,
        LoopStage.verification,
        LoopStage.human_decision,
    },
}


class DevFlowLoopState(BaseModel):
    """Canonical state for one DevFlow pipeline run."""

    run_id: str
    stage: LoopStage
    idea_brief_path: Optional[str] = None
    spec_path: Optional[str] = None
    plan_path: Optional[str] = None
    planning_judge_path: Optional[str] = None
    assignments: list[str] = Field(default_factory=list)
    builder_judge_runs: list[str] = Field(default_factory=list)
    verification_receipts: list[str] = Field(default_factory=list)
    next_human_decision: Optional[str] = None
    # True only when the builder/judge gate recorded a "passed" decision.
    # Verification receipts cannot promote a run to human_decision as "passed"
    # when this is False — they are recorded but the gate failure is surfaced.
    builder_judge_passed: bool = False
    # Autonomous mode: when auto_verify is True, the verification stage is
    # driven by the model assigned to the canonical verifier role instead of
    # parking for a human. loop_cap bounds autonomous build/judge/verify
    # cycles may run before the loop must stop and await a human.
    auto_verify: bool = False
    loop_cap: int = 3
    loop_iteration: int = 0
    created_at: str
    updated_at: str


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------
def new_loop_state(run_id: str) -> DevFlowLoopState:
    """Factory: create a brand-new loop state at stage=idea."""
    now = datetime.now(timezone.utc).isoformat()
    return DevFlowLoopState(
        run_id=run_id,
        stage=LoopStage.idea,
        created_at=now,
        updated_at=now,
    )


def advance_stage(
    state: DevFlowLoopState, new_stage: LoopStage
) -> DevFlowLoopState:
    """Return a copy with *new_stage* set and *updated_at* refreshed.

    Raises ValueError if the transition is not allowed.
    """
    current = state.stage
    allowed = _VALID_TRANSITIONS.get(current)
    if allowed is None or len(allowed) == 0:
        msg = (
            f"No transitions allowed from '{current.value}' stage. "
            "This state is terminal."
        )
        raise ValueError(msg)
    if new_stage not in allowed:
        msg = (
            f"Invalid transition: '{current.value}' -> '{new_stage.value}'. "
            f"Allowed next stages: {sorted({s.value for s in allowed})}"
        )
        raise ValueError(msg)

    now = datetime.now(timezone.utc).isoformat()
    return state.model_copy(update={"stage": new_stage, "updated_at": now})


def is_terminal(state: DevFlowLoopState) -> bool:
    """True if the loop is in a terminal stage (complete or blocked)."""
    return state.stage in (LoopStage.complete, LoopStage.blocked)
