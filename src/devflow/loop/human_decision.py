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
from typing import Any, Callable, Optional

from pydantic import BaseModel

from devflow.loop.pipeline_run import (
    append_worker_feed_entry,
    load_pipeline_run,
    update_pipeline_run_record,
)
from devflow.loop.adapter import advance_loop_state, load_loop_state, save_loop_state
from devflow.loop.local_audition_host_gates import (
    FinalDecisionInputs,
    classify_final_decision,
    summarize_final_decision,
    validate_final_decision_receipt,
)
from devflow.loop.models import DevFlowLoopState, LoopStage
from devflow.loop.model_routing_state import record_run_human_feedback
from devflow.loop.workflow_ledger import is_canonical_workflow_run


FINAL_DECISION_RECEIPT_FILE = "final-decision-receipt.json"
FINAL_DECISION_SUMMARY_FILE = "final-decision-summary.json"


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


def record_final_decision(
    root: Path | str,
    run_id: str,
    inputs: FinalDecisionInputs,
    *,
    summarizer: Callable[[dict[str, Any]], Any] | None = None,
) -> dict[str, Any]:
    """Commit the deterministic receipt before any optional model summary."""
    state = load_loop_state(root, run_id)
    if state.stage != LoopStage.human_decision:
        raise ValueError(
            "Final decision receipt can only be committed at human_decision, "
            f"got {state.stage.value}."
        )
    receipt = classify_final_decision(inputs)
    run_data = load_pipeline_run(root, run_id)
    existing = run_data.get(FINAL_DECISION_RECEIPT_FILE)
    if existing is not None and existing != receipt:
        raise ValueError("Conflicting final decision receipt replay.")
    update_pipeline_run_record(root, run_id, FINAL_DECISION_RECEIPT_FILE, receipt)

    if summarizer is not None:
        summary = summarize_final_decision(receipt, summarizer)
        update_pipeline_run_record(
            root,
            run_id,
            FINAL_DECISION_SUMMARY_FILE,
            {
                "authoritative": False,
                "receipt_file": FINAL_DECISION_RECEIPT_FILE,
                "summary": summary,
            },
        )
    return receipt


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

    if decision_completes_loop(record):
        run_data = load_pipeline_run(root, record.run_id)
        receipt = validate_final_decision_receipt(
            run_data.get(FINAL_DECISION_RECEIPT_FILE)
        )
        if receipt["decision"] != "qualify" or receipt["next_action"] != "none":
            raise ValueError(
                "Cannot complete loop because the deterministic final decision "
                f"is {receipt['decision']}/{receipt['next_action']}."
            )

    canonical = is_canonical_workflow_run(root, record.run_id)
    if canonical and record.decision not in {
        HumanDecision.accept,
        HumanDecision.complete,
        HumanDecision.block,
    }:
        raise ValueError(
            "canonical_product_build@1 does not permit reverse or retry "
            "transitions after human_decision"
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
        if canonical:
            state = advance_loop_state(
                root,
                state,
                LoopStage.blocked,
                evidence={"human-decision": record_file_name},
            )
        else:
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
        if canonical:
            state = advance_loop_state(
                root,
                state,
                target,
                evidence={"human-decision": record_file_name},
            )
        else:
            state = state.model_copy(
                update={
                    "stage": target,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            )

    save_loop_state(root, state)
    try:
        record_run_human_feedback(
            root,
            run_id=record.run_id,
            decision_id=record.decision_id,
            decision=record.decision.value,
        )
    except Exception as exc:
        append_worker_feed_entry(root, record.run_id, {
            "event": "score_persistence_failed",
            "role": "human_decision",
            "model": "",
            "error": str(exc),
        })
    return (state, record)
