# V2-02: Pipeline Run Adapter

## Goal
Create an adapter that bridges the existing `pipeline_run.py` filesystem storage to the new canonical `DevFlowLoopState` model. This lets the v2 spine read/write loop state without modifying existing code.

## Files to create
- `src/devflow/loop/adapter.py`
- `tests/test_loop_adapter.py`

## Do NOT modify
- `src/devflow/control_room/pipeline_run.py`
- `src/devflow/control_room/operating_layer.py`
- Any existing pipeline run files

## Existing pipeline run structure (from pipeline_run.py)

Pipeline runs live at `.devflow/pipeline-runs/<run_id>/` with files:
- `intent.md` — raw intent text
- `source.json` — repo/branch/metadata
- `brainstorm.md` — brainstorm content
- `classification.json` — rule-based classification
- `intent-summary.json` — IntentSummary fields
- `readiness-packet.md` — readiness gate text
- `loop-packet.md` — loop execution packet
- `validation.json` — validation results
- `run-log.jsonl` — event log
- `artifacts.json` — artifact paths
- `review.md` — review text

Key existing functions to USE (import from control_room.pipeline_run):
- `pipeline_runs_dir(root)` — get the runs directory
- `create_pipeline_run(root, source)` — create a new run, returns run_id
- `load_pipeline_run(root, run_id)` — load all files as dict
- `update_pipeline_run_record(root, run_id, file_name, content)` — write a file
- `append_pipeline_event(root, run_id, event)` — append to run-log.jsonl

## Adapter functions

### `infer_stage(run_data: dict) -> LoopStage`
Infer the current LoopStage from existing pipeline run files.

Mapping logic:
- If `validation.json` has results and no errors → `verification`
- If `loop-packet.md` is non-empty → `build_judge`
- If `readiness-packet.md` is non-empty → `assignment`
- If `classification.json` has content → `spec` or `planning`
- If `brainstorm.md` is non-empty → `definition`
- If `intent.md` exists → `idea`
- Default → `idea`

### `load_loop_state(root: Path | str, run_id: str) -> DevFlowLoopState`
Read the pipeline run directory and return a DevFlowLoopState:
- Use `load_pipeline_run()` to get all files
- Infer stage from file contents
- Map artifact paths from `artifacts.json` if present
- Return new DevFlowLoopState with fields populated

### `save_loop_state(root: Path | str, state: DevFlowLoopState) -> None`
Write the loop state back to the pipeline run directory:
- Write `loop-state.json` containing the serialized DevFlowLoopState
- Append a stage-change event to `run-log.jsonl` if stage changed
- Use `update_pipeline_run_record()` and `append_pipeline_event()`

### `create_run_with_state(root: Path | str, source: dict) -> tuple[str, DevFlowLoopState]`
Convenience: create a pipeline run AND return its initial loop state:
- Call `create_pipeline_run(root, source)` to get run_id
- Call `load_loop_state(root, run_id)` to get initial state
- Return (run_id, state)

## Tests required
- `infer_stage` correctly maps file contents to LoopStage values
- `infer_stage` with empty/default files returns `idea`
- `load_loop_state` returns valid DevFlowLoopState from a real pipeline run (use tmp_path)
- `save_loop_state` writes loop-state.json to the run directory
- `save_loop_state` appends event to run-log.jsonl
- `create_run_with_state` returns valid run_id and state at stage=idea
- Round-trip: save then load returns consistent stage
- No imports from control_room except pipeline_run functions listed above

## Constraints
- Import ONLY from `devflow.control_room.pipeline_run` (the specific functions listed)
- Import from `devflow.loop.models` for the state model
- Keep adapter.py under 200 lines
- Use pydantic v2
- Use tmp_path for filesystem tests
