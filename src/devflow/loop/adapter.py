"""Adapter: bridge pipeline_run filesystem storage to DevFlowLoopState.

Reads/writes loop state through the existing pipeline run directory without
modifying pipeline_run.py itself.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from devflow.loop.pipeline_run import (
    append_pipeline_event,
    create_pipeline_run,
    load_pipeline_run,
    update_pipeline_run_record,
)
from devflow.loop.models import DevFlowLoopState, LoopStage, new_loop_state


def infer_stage(run_data: dict) -> LoopStage:
    """Infer the current LoopStage from existing pipeline run files."""
    # verification — validation.json has results with no errors
    val = run_data.get("validation.json") or {}
    if val and isinstance(val, dict):
        results = val.get("results")
        has_results = results is not None and results != {} and results != ""
        has_no_errors = not val.get("errors") and val.get("status") != "error"
        if has_results and has_no_errors:
            return LoopStage.verification

    # build_judge — loop-packet.md is non-empty
    loop_packet = run_data.get("loop-packet.md", "")
    if isinstance(loop_packet, str) and loop_packet.strip():
        return LoopStage.build_judge

    # assignment — readiness-packet.md is non-empty
    readiness = run_data.get("readiness-packet.md", "")
    if isinstance(readiness, str) and readiness.strip():
        return LoopStage.assignment

    # spec or planning — classification.json has content
    classification = run_data.get("classification.json") or {}
    if isinstance(classification, dict) and classification:
        # Heuristic: if it contains planning-related keys, it's planning
        planning_keys = {"subtasks", "task_breakdown", "plan", "phases"}
        if planning_keys & set(classification.keys()):
            return LoopStage.planning
        return LoopStage.spec

    # definition — brainstorm.md is non-empty
    brainstorm = run_data.get("brainstorm.md", "")
    if isinstance(brainstorm, str) and brainstorm.strip():
        return LoopStage.definition

    # idea — intent.md exists (it always does from MINIMUM_RUN_FILES,
    # so check that source.json has meaningful content beyond defaults)
    source = run_data.get("source.json") or {}
    if isinstance(source, dict) and source:
        return LoopStage.idea

    return LoopStage.idea


def load_loop_state(root: Path | str, run_id: str) -> DevFlowLoopState:
    """Read the pipeline run directory and return a DevFlowLoopState."""
    data = load_pipeline_run(root, run_id)

    # Try to load saved state from loop-state.json first
    saved_state = data.get("loop-state.json")
    if isinstance(saved_state, dict):
        try:
            state = DevFlowLoopState.model_validate(saved_state)
            # Refresh updated_at timestamp
            state = state.model_copy(update={"updated_at": datetime.now(timezone.utc).isoformat()})
            return state
        except Exception:
            pass  # Fall through to inference if parsing fails

    # Fall back to inferring stage from file contents
    stage = infer_stage(data)

    now = datetime.now(timezone.utc).isoformat()
    state = new_loop_state(run_id)
    state = state.model_copy(update={"stage": stage, "updated_at": now})

    # Map artifact paths from artifacts.json
    artifacts = data.get("artifacts.json") or {}
    if isinstance(artifacts, dict):
        if artifacts.get("idea_brief_path"):
            state = state.model_copy(update={"idea_brief_path": artifacts["idea_brief_path"]})
        if artifacts.get("spec_path"):
            state = state.model_copy(update={"spec_path": artifacts["spec_path"]})
        if artifacts.get("plan_path"):
            state = state.model_copy(update={"plan_path": artifacts["plan_path"]})
        if artifacts.get("planning_judge_path"):
            state = state.model_copy(update={"planning_judge_path": artifacts["planning_judge_path"]})
        if artifacts.get("assignments"):
            state = state.model_copy(update={"assignments": artifacts["assignments"]})
        if artifacts.get("builder_judge_runs"):
            state = state.model_copy(update={"builder_judge_runs": artifacts["builder_judge_runs"]})
        if artifacts.get("verification_receipts"):
            state = state.model_copy(update={"verification_receipts": artifacts["verification_receipts"]})

    return state


def _load_old_stage(root: Path | str, run_id: str) -> LoopStage:
    """Read the previously saved loop-state.json to find the old stage."""
    try:
        existing = load_pipeline_run(root, run_id)
        old_json = existing.get("loop-state.json")
        if isinstance(old_json, str) and old_json.strip():
            old_state = DevFlowLoopState.model_validate_json(old_json)
            return old_state.stage
    except Exception:
        pass
    # No previous loop-state.json — assume starting from idea
    return LoopStage.idea


def save_loop_state(root: Path | str, state: DevFlowLoopState) -> None:
    """Write the loop state back to the pipeline run directory."""
    old_stage = _load_old_stage(root, state.run_id)

    # Serialize and write loop-state.json
    state_json = state.model_dump_json(indent=2, ensure_ascii=False)
    update_pipeline_run_record(root, state.run_id, "loop-state.json", state_json)

    # Also persist artifacts to artifacts.json so load_loop_state can read them
    artifact_data: dict = {}
    if state.idea_brief_path:
        artifact_data["idea_brief_path"] = state.idea_brief_path
    if state.spec_path:
        artifact_data["spec_path"] = state.spec_path
    if state.plan_path:
        artifact_data["plan_path"] = state.plan_path
    if state.planning_judge_path:
        artifact_data["planning_judge_path"] = state.planning_judge_path
    if state.assignments:
        artifact_data["assignments"] = state.assignments
    if state.builder_judge_runs:
        artifact_data["builder_judge_runs"] = state.builder_judge_runs
    if state.verification_receipts:
        artifact_data["verification_receipts"] = state.verification_receipts
    if artifact_data:
        update_pipeline_run_record(root, state.run_id, "artifacts.json", artifact_data)

    # Append stage-change event if the stage actually changed
    if old_stage != state.stage:
        event = {
            "event": "stage_changed",
            "from": old_stage.value,
            "to": state.stage.value,
        }
        append_pipeline_event(root, state.run_id, event)


def create_run_with_state(
    root: Path | str, source: dict
) -> tuple[str, DevFlowLoopState]:
    """Convenience: create a pipeline run AND return its initial loop state."""
    run_id = create_pipeline_run(root, source)
    state = load_loop_state(root, run_id)
    return (run_id, state)
