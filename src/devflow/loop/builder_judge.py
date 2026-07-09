"""Builder/Judge adapter: canonical loop spine ↔ existing builder-judge implementation.

Deterministic adapter. No model calls. Bridges the canonical DevFlow loop
state to the existing builder-judge loop engine via pipeline-run records.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from devflow.legacy.control_room.pipeline_run import update_pipeline_run_record
from devflow.loop.adapter import load_loop_state, save_loop_state
from devflow.loop.models import (
    DevFlowLoopState,
    LoopStage,
    advance_stage,
)


class BuilderJudgeAssignment(BaseModel):
    """An assignment to run a builder-judge quality-control loop."""

    run_id: str
    assignment_id: str
    definition_of_done: str
    target_files: list[str] = Field(default_factory=list)
    verification_command: Optional[str] = None
    builder_judge_run_id: Optional[str] = None


class BuilderJudgeLink(BaseModel):
    """Lightweight record linking canonical loop state to a builder/judge run."""

    run_id: str
    assignment_id: str
    builder_judge_run_id: str
    status: str  # pending, running, passed, failed, needs_review
    evidence_path: Optional[str] = None
    created_at: str


_VALID_RESULT_STATUSES = {"passed", "failed", "needs_review"}


def _ensure_unique(builder_judge_runs: list[str], run_id: str) -> list[str]:
    """Add run_id to the list if not already present."""
    if run_id not in builder_judge_runs:
        builder_judge_runs = list(builder_judge_runs) + [run_id]
    return builder_judge_runs


def prepare_builder_judge_assignment(
    root: Path | str, assignment: BuilderJudgeAssignment
) -> tuple[DevFlowLoopState, BuilderJudgeLink]:
    """Deterministic prep/link step. No model execution.

    Transitions the loop from ``assignment`` to ``build_judge`` (or stays
    at ``build_judge`` if already there) and writes a link record.

    Args:
        root: Pipeline root directory.
        assignment: The assignment to prepare.

    Returns:
        Tuple of (updated loop state, link record).

    Raises:
        ValueError: If the current stage is not ``assignment`` or ``build_judge``.
    """
    state = load_loop_state(root, assignment.run_id)

    if state.stage not in (LoopStage.assignment, LoopStage.build_judge):
        raise ValueError(
            f"Expected stage assignment or build_judge, got {state.stage.value}. "
            f"Cannot prepare builder/judge assignment."
        )

    builder_judge_run_id = (
        assignment.builder_judge_run_id or assignment.assignment_id
    )

    now = datetime.now(timezone.utc).isoformat()
    link = BuilderJudgeLink(
        run_id=assignment.run_id,
        assignment_id=assignment.assignment_id,
        builder_judge_run_id=builder_judge_run_id,
        status="pending",
        evidence_path="builder-judge-link.json",
        created_at=now,
    )

    link_json = link.model_dump_json(indent=2, ensure_ascii=False)
    update_pipeline_run_record(
        root, assignment.run_id, "builder-judge-link.json", link_json
    )

    # Advance stage if needed
    if state.stage == LoopStage.assignment:
        state = advance_stage(state, LoopStage.build_judge)

    # Ensure builder_judge_runs is unique
    state = state.model_copy(
        update={"builder_judge_runs": _ensure_unique(state.builder_judge_runs, builder_judge_run_id)}
    )

    save_loop_state(root, state)
    return state, link


def record_builder_judge_result(
    root: Path | str,
    run_id: str,
    *,
    builder_judge_run_id: str,
    status: str,
    evidence_path: Optional[str] = None,
) -> tuple[DevFlowLoopState, BuilderJudgeLink]:
    """Record the result of a builder/judge run.

    Updates the loop state based on the result:
    - ``passed`` → advance to ``verification``
    - ``failed`` or ``needs_review`` → stay at ``build_judge``

    Args:
        root: Pipeline root directory.
        run_id: The pipeline run id.
        builder_judge_run_id: The builder-judge run id to link.
        status: Result status (passed, failed, needs_review).
        evidence_path: Optional path to evidence file.

    Returns:
        Tuple of (updated loop state, link record).

    Raises:
        ValueError: If status is invalid or stage is not ``build_judge``.
    """
    if status not in _VALID_RESULT_STATUSES:
        raise ValueError(
            f"Invalid status: {status}. Must be one of {sorted(_VALID_RESULT_STATUSES)}."
        )

    state = load_loop_state(root, run_id)

    if state.stage != LoopStage.build_judge:
        raise ValueError(
            f"Expected stage build_judge, got {state.stage.value}. "
            f"Cannot record result at current stage."
        )

    # Load existing link or create new one
    link_status = status
    link_evidence = evidence_path or "builder-judge-link.json"

    link = BuilderJudgeLink(
        run_id=run_id,
        assignment_id=builder_judge_run_id,  # Use run_id as assignment_id fallback
        builder_judge_run_id=builder_judge_run_id,
        status=link_status,
        evidence_path=link_evidence,
        created_at=datetime.now(timezone.utc).isoformat(),
    )

    link_json = link.model_dump_json(indent=2, ensure_ascii=False)
    update_pipeline_run_record(
        root, run_id, "builder-judge-link.json", link_json
    )

    # Advance or stay based on status
    if status == "passed":
        state = advance_stage(state, LoopStage.verification)

    # Add builder_judge_run_id to state if not present
    state = state.model_copy(
        update={"builder_judge_runs": _ensure_unique(state.builder_judge_runs, builder_judge_run_id)}
    )

    save_loop_state(root, state)
    return state, link
