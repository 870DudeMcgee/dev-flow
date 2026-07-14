"""Planning Judge: gate between planning and assignment.

This is a deterministic, rule-based judge that evaluates planning evidence
and decides whether a plan is ready to be broken into bounded tasks.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field

from devflow.loop.pipeline_run import update_pipeline_run_record
from devflow.loop.adapter import advance_loop_state, load_loop_state, save_loop_state
from devflow.loop.models import (
    DevFlowLoopState,
    LoopStage,
)


class JudgeDecision(str, Enum):
    """Decision outcomes from the planning judge."""
    approve = "approve"
    revise = "revise"
    block = "block"
    escalate_to_user = "escalate_to_user"


class PlanningEvidence(BaseModel):
    """Evidence that the planning judge evaluates."""
    run_id: str
    plan_path: Optional[str] = None
    spec_path: Optional[str] = None
    target_files: List[str] = Field(default_factory=list)
    verification_command: Optional[str] = None
    validators: List[dict] = Field(default_factory=list)
    constraints: List[str] = Field(default_factory=list)
    files_exist: bool = False
    has_verification: bool = False


class PlanningJudgeReport(BaseModel):
    """Report from the planning judge evaluation."""
    run_id: str
    decision: JudgeDecision
    repo_grounding: str
    task_boundaries: str
    verification_reality: str
    overbuild_risk: str
    simpler_path: str
    required_changes: List[str] = Field(default_factory=list)
    next_safe_action: str
    created_at: str


def _build_report(
    evidence: PlanningEvidence,
    decision: JudgeDecision,
    required_changes: List[str],
    next_safe_action: str,
) -> PlanningJudgeReport:
    """Construct a planning judge report with human-readable assessments."""
    return PlanningJudgeReport(
        run_id=evidence.run_id,
        decision=decision,
        repo_grounding=(
            "Plan is grounded in real repo constraints."
            if evidence.files_exist
            else "Plan references files that don't exist in the repo."
        ),
        task_boundaries=(
            "Tasks are properly bounded."
            if len(evidence.target_files) <= 8
            else f"Too many target files ({len(evidence.target_files)}), likely overbuilt scope."
        ),
        verification_reality=(
            "Typed validator declarations are present."
            if evidence.validators
            else "Legacy verification command is present."
            if evidence.has_verification
            else "No real verification evidence provided."
        ),
        overbuild_risk=(
            "Low overbuild risk."
            if len(evidence.target_files) <= 8
            else "High overbuild risk: plan touches more than 8 files."
        ),
        simpler_path=(
            "A simpler approach exists: consolidate target files or split into sub-plans."
            if len(evidence.target_files) > 8
            else "No obvious simpler path detected."
        ),
        required_changes=required_changes,
        next_safe_action=next_safe_action,
        created_at=datetime.now(timezone.utc).isoformat(),
    )


def judge_plan(evidence: PlanningEvidence) -> PlanningJudgeReport:
    """Evaluate planning evidence and produce a judge report.

    Decision logic (deterministic, rule-based):
    1. BLOCK if target_files is empty, spec_path is None/empty, or plan_path is None/empty
    2. REVISE if files_exist is False, has_verification is False, or >8 target_files
    3. ESCALATE_TO_USER if files exist AND has verification AND constraints say escalate
    4. APPROVE if all evidence is valid
    """
    # BLOCK conditions
    if not evidence.target_files:
        return _build_report(
            evidence,
            JudgeDecision.block,
            ["Provide at least one target file in target_files."],
            "Define the files the plan will create or modify.",
        )

    if not evidence.spec_path:
        return _build_report(
            evidence,
            JudgeDecision.block,
            ["Provide a spec_path to the specification artifact."],
            "Create a specification artifact before planning.",
        )

    if not evidence.plan_path:
        return _build_report(
            evidence,
            JudgeDecision.block,
            ["Provide a plan_path to the planning artifact."],
            "Create a planning artifact before submission.",
        )

    # ESCALATE_TO_USER conditions (check before REVISE to give priority)
    if (
        evidence.files_exist
        and evidence.has_verification
        and any("escalate" in c.lower() or "user_decision" in c.lower() for c in evidence.constraints)
    ):
        return _build_report(
            evidence,
            JudgeDecision.escalate_to_user,
            [
                "Review the escalation constraints and make a user decision.",
                "Update the constraints to remove escalation markers if not needed.",
            ],
            "Make a human decision on the escalation constraints before proceeding.",
        )

    # REVISE conditions
    if not evidence.files_exist:
        return _build_report(
            evidence,
            JudgeDecision.revise,
            ["Verify that all target files exist in the repository before planning."],
            "Check that the target files actually exist in the repo.",
        )

    if not evidence.has_verification:
        return _build_report(
            evidence,
            JudgeDecision.revise,
            ["Provide typed validator declarations for the planned changes."],
            "Add typed validators before assignment.",
        )

    if len(evidence.target_files) > 8:
        return _build_report(
            evidence,
            JudgeDecision.revise,
            [f"Reduce target_files to 8 or fewer (currently {len(evidence.target_files)})."],
            "Consolidate target files or split into multiple smaller plans.",
        )

    # APPROVE - all conditions met
    return _build_report(
        evidence,
        JudgeDecision.approve,
        [],
        "Proceed to assignment stage: break plan into bounded tasks.",
    )


def run_planning_judge(
    root: Path | str,
    run_id: str,
    evidence: PlanningEvidence,
) -> tuple[DevFlowLoopState, PlanningJudgeReport]:
    """Full planning judge step: load state, judge, update, save.

    Returns (updated_state, report).
    """
    # Load current loop state
    state = load_loop_state(root, run_id)

    # Run the judge
    report = judge_plan(evidence)

    # Write the report to the pipeline run dir as planning-judge.json
    report_json = report.model_dump_json(indent=2, ensure_ascii=False)
    update_pipeline_run_record(root, run_id, "planning-judge.json", report_json)

    # Also write to worker-feed.jsonl so the status board shows the judge's decision
    from devflow.loop.pipeline_run import append_worker_feed_entry
    append_worker_feed_entry(root, run_id, {
        "event": "completed",
        "role": "planning_judge",
        "model": "deterministic-rules-engine",
        "content": json.dumps({
            "decision": report.decision.value,
            "required_changes": report.required_changes,
            "next_safe_action": report.next_safe_action,
            "repo_grounding": report.repo_grounding,
            "task_boundaries": report.task_boundaries,
            "overbuild_risk": report.overbuild_risk,
            "simpler_path": report.simpler_path,
        }, indent=2),
        "usage": {},
    })

    # Update state based on decision
    if report.decision == JudgeDecision.approve and state.stage == LoopStage.planning_judge:
        state = advance_loop_state(
            root,
            state,
            LoopStage.assignment,
            evidence={"planning-judge-report": "planning-judge.json"},
        )
    elif report.decision == JudgeDecision.block:
        state = advance_loop_state(
            root,
            state,
            LoopStage.blocked,
            evidence={"planning-judge-report": "planning-judge.json"},
        )
    elif report.decision == JudgeDecision.escalate_to_user:
        state = advance_loop_state(
            root,
            state,
            LoopStage.blocked,
            evidence={"planning-judge-report": "planning-judge.json"},
        ).model_copy(
            update={
                "next_human_decision": "Make a human decision on the escalation constraints."
            }
        )
    # REVISE stays at planning_judge, no state change needed

    # Save updated state
    save_loop_state(root, state)

    return state, report
