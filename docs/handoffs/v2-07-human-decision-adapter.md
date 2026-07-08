# V2-07: Human Decision Adapter

## Goal
Create the v2 human decision adapter. After verification passes and the loop reaches `human_decision`, this adapter records the operator's decision and advances the loop to complete, blocked, or back to a prior stage for revision/continued work.

## Files to create
- `src/devflow/loop/human_decision.py`
- `tests/test_loop_human_decision.py`

## Do NOT modify
- Existing files

## Models

### `HumanDecision(str, Enum)`
Values:
- `accept`
- `continue_work`
- `revise_plan`
- `revise_spec`
- `block`
- `complete`

### `HumanDecisionRecord(BaseModel)`
Fields:
- `run_id: str`
- `decision_id: str`
- `decision: HumanDecision`
- `summary: str`
- `notes: str | None = None`
- `next_stage: LoopStage | None = None`
- `created_at: str`

## Functions

### `record_human_decision(root: Path | str, record: HumanDecisionRecord) -> tuple[DevFlowLoopState, HumanDecisionRecord]`
Record a human decision and update loop state.

Behavior:
1. Load loop state.
2. Require state is `human_decision`, unless decision is `block` and current stage is not complete. Raise ValueError otherwise.
3. Write record to pipeline run dir as `human-decision-<decision_id>.json`.
4. Set `state.next_human_decision` to the record summary.
5. Transition based on decision:
   - `accept` -> `complete`
   - `complete` -> `complete`
   - `continue_work` -> `assignment` unless record.next_stage is provided
   - `revise_plan` -> `planning`
   - `revise_spec` -> `spec`
   - `block` -> `blocked`
6. If record.next_stage is provided for `continue_work`, use it, but only allow `assignment`, `build_judge`, `verification`, or `planning_judge`.
7. Save loop state.
8. Return `(updated_state, record)`.

### `decision_completes_loop(record: HumanDecisionRecord) -> bool`
Return True when decision is `accept` or `complete`.

## Tests required
- HumanDecision enum has all six values.
- HumanDecisionRecord serializes/validates.
- record_human_decision rejects stages before human_decision for non-block decisions.
- accept transitions human_decision -> complete.
- complete transitions human_decision -> complete.
- continue_work transitions human_decision -> assignment by default.
- continue_work honors allowed next_stage override.
- continue_work rejects disallowed next_stage override.
- revise_plan transitions human_decision -> planning.
- revise_spec transitions human_decision -> spec.
- block transitions to blocked even from verification stage.
- record writes human-decision-<decision_id>.json.
- next_human_decision is set to record summary.
- decision_completes_loop works.

## Constraints
- Import from `devflow.loop.models`, `devflow.loop.adapter`
- Import from `devflow.control_room.pipeline_run` only for `update_pipeline_run_record`
- Keep human_decision.py under 200 lines
- Pydantic v2
- Use tmp_path for filesystem tests
- Deterministic only. No shell execution, no model calls.
