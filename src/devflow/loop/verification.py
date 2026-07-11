"""Verification adapter: records receipts and advances the loop.

Deterministic only — no shell execution, no model calls.

After builder/judge passes and the loop enters ``verification``, this
adapter records verification receipts and advances the loop toward
``human_decision`` when evidence is passing.
"""
from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

from devflow.loop.pipeline_run import load_pipeline_run, update_pipeline_run_record
from devflow.loop.adapter import load_loop_state, save_loop_state
from devflow.loop.models import DevFlowLoopState, LoopStage, advance_stage
from devflow.loop.reliability import (
    attest_verification_receipt,
    verification_attestation_name,
)


class VerificationStatus(str, Enum):
    """Outcome of a single verification run."""

    passed = "passed"
    failed = "failed"
    blocked = "blocked"
    needs_review = "needs_review"


class VerificationReceipt(BaseModel):
    """Record of a single verification run."""

    run_id: str
    receipt_id: str
    status: VerificationStatus
    command: Optional[str] = None
    summary: str
    evidence_path: Optional[str] = None
    exit_code: Optional[int] = None
    created_at: str


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def record_verification_receipt(
    root: Path | str,
    receipt: VerificationReceipt,
) -> tuple[DevFlowLoopState, VerificationReceipt]:
    """Record a verification receipt and update loop state.

    Args:
        root: Pipeline root directory.
        receipt: The receipt to record.

    Returns:
        Tuple of (updated loop state, the receipt that was recorded).

    Raises:
        ValueError: If the current stage is not ``verification`` or
            ``human_decision``.
    """
    state = load_loop_state(root, receipt.run_id)

    if state.stage not in (
        LoopStage.verification,
        LoopStage.human_decision,
    ):
        raise ValueError(
            f"Expected stage verification or human_decision, got "
            f"{state.stage.value}. Cannot record receipt at current stage."
        )

    # Write receipt JSON into the pipeline run directory
    receipt_file_name = f"verification-receipt-{receipt.receipt_id}.json"
    receipt_json = receipt.model_dump_json(indent=2, ensure_ascii=False)
    run_data = load_pipeline_run(root, receipt.run_id)
    existing_receipt = run_data.get(receipt_file_name)
    expected_receipt = receipt.model_dump(mode="json")
    if existing_receipt is not None and existing_receipt != expected_receipt:
        raise ValueError(
            f"Conflicting verification receipt replay: {receipt.receipt_id}"
        )
    if (
        existing_receipt is not None
        and run_data.get(verification_attestation_name(receipt_file_name)) is None
    ):
        raise ValueError(
            "Legacy verification receipt requires explicit reliability migration."
        )
    update_pipeline_run_record(
        root, receipt.run_id, receipt_file_name, receipt_json
    )
    attest_verification_receipt(root, receipt.run_id, receipt_file_name)

    # Append receipt path to state if not already present (idempotent)
    receipt_path = receipt_file_name
    if receipt_path not in state.verification_receipts:
        state = state.model_copy(
            update={
                "verification_receipts": list(state.verification_receipts) + [receipt_path],
            }
        )

    # Stage transitions based on receipt status
    # GATE RULE: a verification receipt cannot promote a run to
    # human_decision as "passed" when the builder/judge gate did not pass.
    # If builder_judge_passed is False, record the receipt but stay at
    # verification so the operator sees the gate failure.
    if state.stage == LoopStage.verification:
        if receipt.status == VerificationStatus.passed and state.builder_judge_passed:
            state = advance_stage(state, LoopStage.human_decision)
        elif receipt.status == VerificationStatus.passed:
            state = state.model_copy(update={
                "next_human_decision": (
                    "Verification passed, but the builder/judge gate did not. "
                    "Review the failed build/judge rounds before continuing."
                ),
            })
        elif receipt.status in (
            VerificationStatus.failed,
            VerificationStatus.needs_review,
        ):
            prompt = (
                "Fix verification failures before continuing."
                if receipt.status == VerificationStatus.failed
                else "Review verification output before continuing."
            )
            state = state.model_copy(update={"next_human_decision": prompt})
        elif receipt.status == VerificationStatus.blocked:
            state = advance_stage(state, LoopStage.blocked)
            state = state.model_copy(
                update={"next_human_decision": receipt.summary}
            )
    # If already at human_decision, only append (idempotent above).

    save_loop_state(root, state)
    return (state, receipt)


def verification_ready_for_human(state: DevFlowLoopState) -> bool:
    """Return True when the loop is ready for human decision.

    A verification can be handed off to a human only when:
    1. The current stage is ``human_decision``, AND
    2. At least one verification receipt exists.
    """
    return (
        state.stage == LoopStage.human_decision
        and len(state.verification_receipts) > 0
    )
