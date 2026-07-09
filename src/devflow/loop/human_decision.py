"""Human decision adapter: record operator decision and advance the loop.

Deterministic only — no shell execution, no model calls.

After verification passes and the loop reaches ``human_decision``, this
adapter records the operator's decision and advances the loop to complete,
blocked, or back to a prior stage for revision/continued work.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

from devflow.legacy.control_room.pipeline_run import update_pipeline_run_record
from devflow.loop.adapter import load_loop_state, save_loop_state
from devflow.loop.models import DevFlowLoopState, LoopStage


ALLOWED_CONTINUE_WORK_TARGETS = frozenset(
    {
        LoopStage.assignment,
        LoopStage.build_judge,
        LoopStage.verification,
        LoopStage.planning_judge,
    }
)


class HumanDecision(str, Enum):
    """Operator decision at the human_decision stage."""

    accept = "accept"
    continue_work = "continue_work"
    revise_plan = "revise_plan"
    revise_spec = "revise_spec"
    block = "block"
    complete = "complete"


class HumanDecisionRecord(BaseModel):
    """Record of an operator decision at the human_decision stage."""

    run_id: str
    decision_id: str
    decision: HumanDecision
    summary: str
    notes: Optional[str] = None
    next_stage: Optional[LoopStage] = None
    created_at: str


# Decision -> next stage mapping (used for all non-block decisions)
_DECISION_STAGE_MAP = {
    HumanDecision.accept: LoopStage.complete,
    HumanDecision.complete: LoopStage.complete,
    HumanDecision.revise_plan: LoopStage.planning,
    HumanDecision.revise_spec: LoopStage.spec,
    HumanDecision.block: LoopStage.blocked,
}


def decision_completes_loop(record: HumanDecisionRecord) -> bool:
    """Return True when the decision is accept or complete."""
    return record.decision in (
        HumanDecision.accept,
        HumanDecision.complete,
    )


def record_human_decision(
    root: Path | str, record: HumanDecisionRecord
) -> tuple[DevFlowLoopState, HumanDecisionRecord]:
    """Record a human decision and update loop state.

    Args:
        root: Pipeline root directory.
        record: The decision record to record.

    Returns:
        Tuple of (updated loop state, the record that was recorded).

    Raises:
        ValueError: If the current stage is not ``human_decision``
            (unless the decision is ``block`` and the current stage is
            not ``complete``).
    """
    state = load_loop_state(root, record.run_id)

    # Stage guard: require human_decision unless blocking from a non-complete stage
    if state.stage != LoopStage.human_decision:
        if record.decision != HumanDecision.block or state.stage == LoopStage.complete:
            raise ValueError(
                f"Expected stage human_decision, got "
                f"{state.stage.value}. Cannot record decision at current stage."
            )

    # Write record JSON into the pipeline run directory
    record_file_name = f"human-decision-{record.decision_id}.json"
    record_json = record.model_dump_json(indent=2, ensure_ascii=False)
    update_pipeline_run_record(
        root, record.run_id, record_file_name, record_json
    )

    # Set next_human_decision to the summary
    state = state.model_copy(
        update={"next_human_decision": record.summary}
    )

    # Transition based on decision — bypass advance_stage for reverse
    # transitions (revise_*), which the canonical transition map doesn't allow.
    if record.decision == HumanDecision.block:
        state = state.model_copy(
            update={"stage": LoopStage.blocked, "updated_at": datetime.now(timezone.utc).isoformat()}
        )
        state = state.model_copy(update={"next_human_decision": record.summary})
    elif record.decision == HumanDecision.continue_work:
        if record.next_stage is not None:
            if record.next_stage not in ALLOWED_CONTINUE_WORK_TARGETS:
                raise ValueError(
                    f"Invalid next_stage for continue_work: "
                    f"'{record.next_stage.value}'. Allowed: "
                    f"{sorted({s.value for s in ALLOWED_CONTINUE_WORK_TARGETS})}"
                )
            state = state.model_copy(
                update={
                    "stage": record.next_stage,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            )
        else:
            state = state.model_copy(
                update={
                    "stage": LoopStage.assignment,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            )
    elif record.decision in _DECISION_STAGE_MAP:
        target = _DECISION_STAGE_MAP[record.decision]
        state = state.model_copy(
            update={
                "stage": target,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        )

    save_loop_state(root, state)
    return (state, record)
