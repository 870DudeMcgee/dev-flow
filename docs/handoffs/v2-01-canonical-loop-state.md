# V2-01: Canonical Loop State Model

## Goal
Create the canonical DevFlow loop state model. This is the first object in the new v2 product spine. No UI, no agent runtime, no dashboard, no model routing.

## Files to create
- `src/devflow/loop/__init__.py` (empty or minimal)
- `src/devflow/loop/models.py`
- `tests/test_loop_models.py`

## DevFlowLoopState spec

A Pydantic BaseModel (repo already uses pydantic) representing one pipeline run's canonical state.

Fields:
- `run_id: str`
- `stage: LoopStage` (enum)
- `idea_brief_path: Optional[str] = None`
- `spec_path: Optional[str] = None`
- `plan_path: Optional[str] = None`
- `planning_judge_path: Optional[str] = None`
- `assignments: list[str] = []` (task IDs)
- `builder_judge_runs: list[str] = []` (run IDs)
- `verification_receipts: list[str] = []` (receipt paths)
- `next_human_decision: Optional[str] = None`
- `created_at: str` (ISO timestamp)
- `updated_at: str` (ISO timestamp)

LoopStage enum values:
`idea`, `definition`, `spec`, `planning`, `planning_judge`, `assignment`, `build_judge`, `verification`, `human_decision`, `complete`, `blocked`

## Helper functions
- `new_loop_state(run_id: str) -> DevFlowLoopState` — factory that sets stage=idea and timestamps
- `advance_stage(state: DevFlowLoopState, new_stage: LoopStage) -> DevFlowLoopState` — returns updated copy with new stage + updated_at
- `is_terminal(state: DevFlowLoopState) -> bool` — True if stage is complete or blocked

## Stage ordering rule
Valid forward transitions:
```
idea -> definition -> spec -> planning -> planning_judge -> assignment -> build_judge -> verification -> human_decision -> complete
```
Any stage can transition to `blocked`. `blocked` can transition back to any non-terminal stage.

`advance_stage` must reject invalid transitions by raising ValueError with a clear message.

## Tests required
- Factory creates state at stage=idea with timestamps
- Valid forward transition works
- Invalid transition raises ValueError
- Transition to blocked from any stage works
- Transition from blocked back to a non-terminal stage works
- is_terminal returns True for complete/blocked, False otherwise
- Serialization round-trip (model_dump / model_validate)

## Constraints
- Use pydantic v2 (already in repo venv)
- Keep models.py under 150 lines
- No imports from control_room/ — this is a clean spine
- Follow repo's existing code style (check other src/devflow/ files)
