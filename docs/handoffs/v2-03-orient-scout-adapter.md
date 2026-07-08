# V2-03: Orient/Scout Adapter

## Goal
Create an adapter that wraps the existing `scout_discovery.py` and `agent_workflow_receipts.py` surfaces into the v2 loop spine. This lets the canonical loop trigger orientation/scouting and record the evidence in a pipeline run.

## Files to create
- `src/devflow/loop/orient.py`
- `tests/test_loop_orient.py`

## Do NOT modify
- `src/devflow/control_room/scout_discovery.py`
- `src/devflow/control_room/agent_workflow_receipts.py`
- `src/devflow/control_room/agent_command.py`
- Any existing files

## Existing surfaces to import from

### From `devflow.control_room.scout_discovery`:
- `discover_agent_scout_context(root, task_id, *, handoff=None, files_to_touch=None, ...)` → `AgentScoutDiscovery`
- `AgentScoutDiscovery` dataclass with fields: `handoff_path`, `handoff_read`, `files_to_touch`, `files_to_read_next`, `tests`, `risks`, `recommended_lane`, `verification`, `map_freshness`, `evidence_paths`, `context_brief`

### From `devflow.loop.adapter`:
- `save_loop_state(root, state)`
- `load_loop_state(root, run_id)`

### From `devflow.loop.models`:
- `DevFlowLoopState`, `LoopStage`, `advance_stage`, `new_loop_state`

## Adapter functions

### `orient_packet(root: Path | str, run_id: str, *, handoff: str | None = None, files_to_touch: list[str] | None = None) -> OrientResult`
Run scout discovery for a pipeline run and return a compact result:
- Call `discover_agent_scout_context(root, run_id, handoff=handoff, files_to_touch=files_to_touch)`
- Build and return an `OrientResult` (pydantic model) containing:
  - `run_id: str`
  - `stage: str` — the current stage name
  - `lane: str` — recommended_lane from discovery
  - `files_to_touch: list[str]`
  - `files_to_read_next: list[dict[str, str]]`
  - `tests: list[str]`
  - `risks: list[str]`
  - `verification: str`
  - `map_confidence: str` — from map_freshness
  - `context_brief: list[dict]`
  - `ready: bool` — True if lane != "ask_user" and files_to_touch is non-empty

### `run_orient(root: Path | str, run_id: str, *, handoff: str | None = None, files_to_touch: list[str] | None = None) -> tuple[DevFlowLoopState, OrientResult]`
Full orient step:
- Load current loop state via `load_loop_state(root, run_id)`
- Call `orient_packet(root, run_id, handoff=handoff, files_to_touch=files_to_touch)`
- If state is at `idea` stage and orient is ready, advance to `definition`
- Save the updated loop state
- Write orient evidence to the pipeline run dir as `orient-result.json`
- Return (updated_state, orient_result)

### `OrientResult(BaseModel)`
Pydantic model with all fields listed above.

## Tests required
- `OrientResult` can be created from an `AgentScoutDiscovery`
- `orient_packet` returns correct fields from discovery
- `orient_packet` with no handoff and no files returns `ready=False`
- `orient_packet` with files_to_touch returns `ready=True` when lane != ask_user
- `run_orient` on a fresh pipeline run at stage=idea advances to definition when orient is ready
- `run_orient` does NOT advance stage when orient is not ready
- `run_orient` writes orient-result.json to the pipeline run directory
- Round-trip: create pipeline run, run orient, check loop state stage advanced

## Constraints
- Import ONLY from the three modules listed above
- Keep orient.py under 200 lines
- Use pydantic v2
- Use tmp_path for filesystem tests
- Create real pipeline runs with `create_pipeline_run` in tests
