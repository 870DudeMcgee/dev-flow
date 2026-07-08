# V2-05: Builder/Judge Adapter

## Goal
Create a clean v2 adapter between the canonical loop spine and the existing builder/judge implementation. This adapter should let a pipeline run at `assignment` stage start/record builder-judge work and advance the loop to `build_judge` / `verification` based on evidence.

## Files to create
- `src/devflow/loop/builder_judge.py`
- `tests/test_loop_builder_judge.py`

## Do NOT modify
- `src/devflow/control_room/builder_judge_loop.py`
- `src/devflow/control_room/builder_judge_command.py`
- Existing builder/judge files

## Existing surfaces to inspect/use

### From `devflow.control_room.builder_judge_loop`
Use only stable public surfaces already present there. Inspect before importing exact names. Known candidates from audit:
- `BuilderJudgeRun`
- `BuilderJudgeRound`
- `BuilderJudgeConfig`
- `run_builder_judge_loop`
- `get_builder_judge_run`
- `project_builder_judge_run`
- `builder_judge_run_path`

If a candidate import is awkward or requires external model execution, do NOT call it in tests. The adapter may record/link existing run ids without executing live models.

### From `devflow.loop.adapter`
- `load_loop_state(root, run_id)`
- `save_loop_state(root, state)`

### From `devflow.loop.models`
- `DevFlowLoopState`
- `LoopStage`
- `advance_stage`

### From `devflow.control_room.pipeline_run`
- `update_pipeline_run_record(root, run_id, file_name, content)`

## New models

### `BuilderJudgeAssignment(BaseModel)`
Fields:
- `run_id: str`
- `assignment_id: str`
- `definition_of_done: str`
- `target_files: list[str] = []`
- `verification_command: str | None = None`
- `builder_judge_run_id: str | None = None`

### `BuilderJudgeLink(BaseModel)`
A lightweight record linking canonical loop state to a builder/judge run.
Fields:
- `run_id: str`
- `assignment_id: str`
- `builder_judge_run_id: str`
- `status: str` — `pending`, `running`, `passed`, `failed`, `needs_review`
- `evidence_path: str | None = None`
- `created_at: str`

## Functions

### `prepare_builder_judge_assignment(root: Path | str, assignment: BuilderJudgeAssignment) -> tuple[DevFlowLoopState, BuilderJudgeLink]`
Deterministic prep/link step. No model execution.

Behavior:
1. Load loop state.
2. Require current state is `assignment` or `build_judge`; otherwise raise ValueError.
3. Create a `BuilderJudgeLink` with:
   - `builder_judge_run_id` = assignment.builder_judge_run_id if provided else `assignment.assignment_id`
   - `status="pending"`
   - `evidence_path="builder-judge-link.json"`
4. Write `builder-judge-link.json` to the pipeline run directory with `update_pipeline_run_record`.
5. If state is `assignment`, advance to `build_judge`.
6. Add the builder_judge_run_id to `state.builder_judge_runs` if absent.
7. Save loop state.
8. Return `(updated_state, link)`.

### `record_builder_judge_result(root: Path | str, run_id: str, *, builder_judge_run_id: str, status: str, evidence_path: str | None = None) -> tuple[DevFlowLoopState, BuilderJudgeLink]`
Record result of a builder/judge run.

Behavior:
1. Load loop state.
2. Require current state is `build_judge`; otherwise raise ValueError.
3. Require status is one of `passed`, `failed`, `needs_review`.
4. Write/update `builder-judge-link.json` with the new status/evidence.
5. If status == `passed`, advance to `verification`.
6. If status == `failed` or `needs_review`, stay at `build_judge`.
7. Add builder_judge_run_id to state.builder_judge_runs if absent.
8. Save loop state.
9. Return `(updated_state, link)`.

## Tests required

- `BuilderJudgeAssignment` serializes/validates.
- `BuilderJudgeLink` serializes/validates.
- `prepare_builder_judge_assignment` rejects state before assignment.
- `prepare_builder_judge_assignment` advances `assignment -> build_judge`.
- `prepare_builder_judge_assignment` keeps stage as `build_judge` if already there.
- `prepare_builder_judge_assignment` writes `builder-judge-link.json`.
- `prepare_builder_judge_assignment` records builder_judge_run_id exactly once.
- `record_builder_judge_result` rejects invalid status.
- `record_builder_judge_result` rejects wrong loop stage.
- `record_builder_judge_result(status="passed")` advances `build_judge -> verification`.
- `record_builder_judge_result(status="failed")` stays at `build_judge`.
- `record_builder_judge_result(status="needs_review")` stays at `build_judge`.
- Result write is visible in `builder-judge-link.json`.

## Constraints
- Adapter is deterministic; no model calls in tests.
- Keep `builder_judge.py` under 220 lines.
- Use pydantic v2.
- Use tmp_path for filesystem tests.
- Use real pipeline runs via existing `create_pipeline_run`.
- Do not import broad control_room modules. If importing from `builder_judge_loop`, import only specific public classes/functions needed; if none needed, do not import it.
