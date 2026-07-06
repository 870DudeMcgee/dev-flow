# DevFlow Refactor — Session Handoff (Slice 6: Workbench Handlers)

## Goal
Continue the DevFlow operating layer refactor using the multi-model fleet.
Slice 5 (builder-judge handler extraction) is complete — the v2 builder-judge
loop produced perfect output in 1 round with no GLM takeover. The next
extraction target is the workbench handler group (2 methods, ~77 lines),
then gates/local-model (3), refactor (2), misc (5).

## Motivational Intent
DevFlow is a local-first control room for parallel AI coding workers. The
operating layer server started at 925 lines with 30+ handler methods in a
single god class. We're extracting handlers into per-domain mixin modules
using a builder-judge loop (Ornith 35B generates, Qwen 27B reviews). The
fleet toolchain is built, tested, v2-patched, and proven — Slice 5 was the
first fully automated run that converged without GLM intervention.

## Current State (after 5 slices)

### What's Done

**Slice 1 — Lifecycle + Dispatch Table (COMPLETE)**
- `operating_layer_lifecycle.py` (158 lines) — extracted lifecycle methods
- `operating_layer_server.py` — dispatch dicts replacing if/elif routing
- Re-exports from lifecycle module with `# noqa: F401`

**Slice 2 — Frontend Assets to Static Files (COMPLETE)**
- `static/index.html`, `static/app.css`, `static/app.js` — extracted from inline strings
- `operating_layer_assets.py` rewritten to read from static files with fallback
- `pyproject.toml` has `[tool.setuptools.package-data]` for static files

**Slice 3 — Brainstorm Handler Extraction (COMPLETE)**
- `operating_layer_brainstorm_handlers.py` (85 lines) — `BrainstormHandlerMixin` with 6 methods
- Manual builder-judge loop: operator fed source to builder and code to judge
- Qwen found 4 issues → GLM fixed → Qwen approved

**Slice 4 — Obsidian Handler Extraction (COMPLETE)**
- `operating_layer_obsidian_handlers.py` (72 lines) — `ObsidianHandlerMixin` with 5 methods
- Class: `OperatingLayerRequestHandler(ObsidianHandlerMixin, BrainstormHandlerMixin, ...)`
- Obsidian imports moved from server to mixin
- Test: monkeypatch target updated to patch mixin module
- Fleet v2 script tested end-to-end — builder produced correct output with source-in-prompt

**Slice 5 — Builder-Judge Handler Extraction (COMPLETE)**
- `operating_layer_builder_judge_handlers.py` (64 lines) — `BuilderJudgeHandlerMixin` with 4 methods
- Class: `OperatingLayerRequestHandler(BuilderJudgeHandlerMixin, ObsidianHandlerMixin, ...)`
- Builder-judge route imports moved from server to mixin
- **First fully automated v2 run**: converged in 1 round, no GLM takeover, exact source match
- 95/95 tests passing, ruff clean

### Metrics
| Metric | Slices 1-4 | Slice 5 | Target |
|:---|:---|:---|:---|
| Builder valid syntax | 25% | 100% | 100% |
| Builder source fed | 25% | 100% | 100% |
| Judge saw code | 25% | 100% | 100% |
| Judge false approvals | 75% | 0% | 0% |
| GLM takeover rate | 100% | 0% | 0% |
| Rounds to converge | 0.5 avg | 1 | ≤2 |

### Codebase Metrics
- `operating_layer_server.py`: 925 → 620 lines (-33%)
- New modules: 6 (lifecycle, brainstorm_handlers, obsidian_handlers, builder_judge_handlers, static/, assets rewrite)
- Tests: 95 passing across 9 test files
- Ruff: clean
- Pattern database: 8 patterns from 4 slices
- Metrics database: 5 runs recorded

### Test Command
```bash
cd "/Users/jewelbait/Desktop/Local AI Dev Team"
PYTHONPATH=src .venv/bin/python -m pytest tests/test_operating_layer.py tests/test_operating_layer_lifecycle.py tests/test_operating_layer_browse_routes.py tests/test_operating_layer_brainstorm_routes.py tests/test_browser_action_routes.py tests/test_operating_layer_obsidian_routes.py tests/test_operating_layer_builder_judge_routes.py tests/test_operating_layer_static_project_routes.py tests/test_operating_layer_local_model_routes.py -v --tb=short
```

### Lint Command
```bash
cd "/Users/jewelbait/Desktop/Local AI Dev Team"
PYTHONPATH=src .venv/bin/ruff check src/devflow/control_room/operating_layer_server.py
```

## Next Steps — Slice 6: Workbench Handler Extraction

### Target
Extract 2 workbench handler methods into `WorkbenchHandlerMixin`:
- `_handle_workbench_project` (L326) — creates a workbench project (~13 lines)
- `_handle_workbench_implement` (L338) — starts implementation, has async branching (~64 lines)

### Risk Notes
- `_handle_workbench_implement` is the largest remaining method (~64 lines) with:
  - Extensive payload validation (6 fields with type checks)
  - Async/sync branching (`async_mode` flag)
  - Two different code paths: `run_workbench_implementation` (sync) vs `start_workbench_implementation_async` (async)
  - Multiple exception groups: `WorkbenchError`, `BuilderJudgeConfigError`, `BuilderJudgeRunError`, `ProjectRegistryError`, `ValueError`, `OSError`
- Uses `_send_action_error` (not just `_send_json_error`) for some error paths — mixin needs host class access
- Imports needed in the mixin (all from existing modules, no new deps):
  - From `devflow.control_room.builder_judge_loop`: `DEFAULT_BUILDER_PROFILE`, `DEFAULT_JUDGE_PROFILE`, `DEFAULT_PASS_THRESHOLD`, `BuilderJudgeConfigError`, `BuilderJudgeRunError`, `run_builder_judge_loop`
  - From `devflow.control_room.builder_judge_async_runtime`: `start_workbench_implementation_async`
  - From `devflow.control_room.workbench`: `WorkbenchError`, `create_workbench_project`, `implementation_config_from_package`, `new_workbench_loop_id`, `prepare_implementation_package`, `run_workbench_implementation`
  - From `devflow.control_room.project_registry`: `ProjectRegistryError`
- No test monkeypatch targets on the server module for these symbols (verified)
- All 12 imports are used ONLY in these 2 methods (verified) — safe to move all

### How to Execute

1. **Load the fleet skill**: `/skills load multi-model-fleet devflow-analysis handoff-adapter`
2. **Check fleet status**: `~/.hermes/scripts/model-router status`
3. **Run the v2 builder-judge loop** (5 parameters):
   ```bash
   bash ~/.hermes/skills/software-development/multi-model-fleet/scripts/builder-judge-loop.sh \
     "Extract the workbench handler methods from OperatingLayerRequestHandler into a WorkbenchHandlerMixin class in operating_layer_workbench_handlers.py. Follow the BuilderJudgeHandlerMixin pattern: module docstring, from __future__ import annotations, imports from devflow.control_room.builder_judge_loop (DEFAULT_BUILDER_PROFILE, DEFAULT_JUDGE_PROFILE, DEFAULT_PASS_THRESHOLD, BuilderJudgeConfigError, BuilderJudgeRunError, run_builder_judge_loop), from devflow.control_room.builder_judge_async_runtime (start_workbench_implementation_async), from devflow.control_room.workbench (WorkbenchError, create_workbench_project, implementation_config_from_package, new_workbench_loop_id, prepare_implementation_package, run_workbench_implementation), from devflow.control_room.project_registry (ProjectRegistryError), then the mixin class with both methods. The host class provides self._send_json, self._send_json_error, self._send_action_error, self._read_json_body, self._payload_project_root, self.server.repo_root." \
     "/Users/jewelbait/Desktop/Local AI Dev Team/src/devflow/control_room/operating_layer_workbench_handlers.py" \
     "/Users/jewelbait/Desktop/Local AI Dev Team" \
     "src/devflow/control_room/operating_layer_server.py" \
     "_handle_workbench_project,_handle_workbench_implement"
   ```
4. **After the loop**: wire the mixin into `operating_layer_server.py`:
   - Add `from devflow.control_room.operating_layer_workbench_handlers import WorkbenchHandlerMixin`
   - Change class to `class OperatingLayerRequestHandler(WorkbenchHandlerMixin, BuilderJudgeHandlerMixin, ObsidianHandlerMixin, BrainstormHandlerMixin, BaseHTTPRequestHandler)`
   - Remove the 2 workbench handler methods from the class body
   - Remove workbench imports from the server (now in mixin):
     - `DEFAULT_BUILDER_PROFILE`, `DEFAULT_JUDGE_PROFILE`, `DEFAULT_PASS_THRESHOLD`, `BuilderJudgeConfigError`, `BuilderJudgeRunError`, `run_builder_judge_loop` (from builder_judge_loop)
     - `start_workbench_implementation_async` (from builder_judge_async_runtime)
     - `WorkbenchError`, `create_workbench_project`, `implementation_config_from_package`, `new_workbench_loop_id`, `prepare_implementation_package`, `run_workbench_implementation` (from workbench)
   - Run `ruff --select F401` to find any remaining unused imports
   - Search tests for `monkeypatch.setattr(operating_layer_server,` and update any that patch moved functions
   - Run the test command above
5. **If new patterns found**: add them with `pattern_inject.py add ...`
6. **Record metrics**: the script does this automatically, but verify with `run_metrics.py list`
7. **Commit** (with user approval — commit ≠ push)

### Remaining Handler Groups (after workbench)

| Group | Methods | Est. Lines | Notes |
|:---|:---|:---|:---|
| Gates/Local Model | 3 | ~45 | `_handle_gates_setup`, `_handle_local_model_ensure`, `_handle_architecture_artifact` |
| Refactor | 2 | ~30 | `_handle_refactor_start`, `_handle_refactor_status` |
| Misc (browse, repo_set, agents, task_write_context) | 4 | ~60 | Core infrastructure — extract last |

## Constraints

- Do NOT edit files without running tests after
- Do NOT push without explicit user approval
- Use the fleet skill's v2 tools: `extract_methods.py`, `strip_output.py`, `run_metrics.py`, `builder-judge-loop.sh`
- All local models: `ctx=131072`, reasoning ON, `max_tokens=4096`
- Only Ornith 9B (light group) runs in parallel with heavy models
- Heavy models (Ornith 35B, Qwen 27B, Qwopus 35B) — only ONE at a time, use `model-router start`
- The v2 builder-judge-loop.sh takes 5 params: task, output_file, project_root, source_file, method_names
- The script needs `bash` prefix (not directly executable): `bash ~/.hermes/skills/.../builder-judge-loop.sh`

## Fleet Quick Reference

```bash
# Check what's running
~/.hermes/scripts/model-router status

# Start a model (stops heavy-group siblings first)
~/.hermes/scripts/model-router start ornith-35b   # builder
~/.hermes/scripts/model-router start 8083          # Qwen 27B (judge)

# V2 builder-judge loop (5 params — includes source file + methods)
bash ~/.hermes/skills/software-development/multi-model-fleet/scripts/builder-judge-loop.sh \
  "<task>" "<output_file>" "<project_root>" "<source_file>" "<method1,method2,...>"

# Parse a response (handles Qwen inline thinking)
~/.hermes/hermes-agent/venv/bin/python3 ~/.hermes/skills/software-development/multi-model-fleet/scripts/parse_response.py /tmp/response.json

# Auto-verify curl (truncation detection + auto-rerun)
~/.hermes/hermes-agent/venv/bin/python3 ~/.hermes/skills/software-development/multi-model-fleet/scripts/curl_verify.py <port> <payload.json> <output.json>

# Extract method bodies from a source file (for builder prompts)
~/.hermes/hermes-agent/venv/bin/python3 ~/.hermes/skills/software-development/multi-model-fleet/scripts/extract_methods.py <source_file> <method1> [method2 ...]

# Strip markdown fences from model output
~/.hermes/hermes-agent/venv/bin/python3 ~/.hermes/skills/software-development/multi-model-fleet/scripts/strip_output.py <input_file> [output_file]

# Pattern database
~/.hermes/hermes-agent/venv/bin/python3 ~/.hermes/skills/software-development/multi-model-fleet/scripts/pattern_inject.py list
~/.hermes/hermes-agent/venv/bin/python3 ~/.hermes/skills/software-development/multi-model-fleet/scripts/pattern_inject.py builder  # get builder context
~/.hermes/hermes-agent/venv/bin/python3 ~/.hermes/skills/software-development/multi-model-fleet/scripts/pattern_inject.py judge   # get judge context

# Metrics
~/.hermes/hermes-agent/venv/bin/python3 ~/.hermes/skills/software-development/multi-model-fleet/scripts/run_metrics.py list
~/.hermes/hermes-agent/venv/bin/python3 ~/.hermes/skills/software-development/multi-model-fleet/scripts/run_metrics.py stats
~/.hermes/hermes-agent/venv/bin/python3 ~/.hermes/skills/software-development/multi-model-fleet/scripts/run_metrics.py trend
```

## What "Done" Looks Like

- `operating_layer_server.py` is under 600 lines (currently 620, workbench extraction removes ~77 → ~543)
- All domain handlers live in `operating_layer_<domain>_handlers.py` mixin modules
- 95+ tests passing
- Ruff clean
- Pattern database has 10+ patterns
- Metrics show builder_valid_syntax ≥ 80% and glm_takeover ≤ 50% for automated runs
- Builder-judge loop converges in 1 round for most extractions
