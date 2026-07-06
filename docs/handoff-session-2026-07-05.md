# DevFlow Refactor — Session Handoff (Slice 5: Builder-Judge Handlers)

## Goal
Continue the DevFlow operating layer refactor using the multi-model fleet.
Slice 4 (obsidian handler extraction) is complete. The next extraction
target is the builder-judge handler group (4 methods), then workbench (2),
then refactor/gates/local-model/misc groups.

## Motivational Intent
DevFlow is a local-first control room for parallel AI coding workers. The
operating layer server started at 925 lines with 30+ handler methods in a
single god class. We're extracting handlers into per-domain mixin modules
using a builder-judge loop (Ornith 35B generates, Qwen 27B reviews). The
fleet toolchain is built, tested, and v2-patched — the next session should
use the v2 builder-judge-loop.sh directly.

## Current State (after 4 slices)

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

### Fleet v2 Improvements (applied this session)
- **`extract_methods.py`** — AST-based source code extractor for builder prompts
- **`strip_output.py`** — Markdown fence + META line stripper for model output
- **`run_metrics.py`** — Per-run metrics tracker (record/list/stats/trend)
- **`builder-judge-loop.sh` v2** — Complete rewrite with:
  - Source code fed to builder via `extract_methods.py`
  - Generated code fed to judge via file read
  - Markdown fence stripping via `strip_output.py`
  - Syntax validation gate (`ast.parse`) before judge
  - Pre-slice baseline test check
  - Full test suite (9 files) instead of 3-file subset
  - Metrics recording after every run
  - JSON payloads built with Python `json.dump()` (no bash heredoc)

### Metrics
| Metric | Value (4 runs) | Target |
|:---|:---|:---|
| Builder valid syntax | 25% | 100% |
| Builder source fed | 25% | 100% |
| Judge saw code | 25% | 100% |
| Judge false approvals | 75% | 0% |
| GLM takeover rate | 100% | 0% |

**Note:** Slices 1-2 didn't use the loop. Slice 3 was manual. Slice 4 v1 was
broken, v2 e2e test produced correct output. Slice 5 will be the first real
automated run with the v2 script.

### Codebase Metrics
- `operating_layer_server.py`: 925 → 676 lines (-27%)
- New modules: 5 (lifecycle, brainstorm_handlers, obsidian_handlers, static/, assets rewrite)
- Tests: 95 passing across 9 test files
- Ruff: clean
- Pattern database: 8 patterns from 4 slices
- Metrics database: 4 runs backfilled

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

## Next Steps — Slice 5: Builder-Judge Handler Extraction

### Target
Extract 4 builder-judge handler methods into `BuilderJudgeHandlerMixin`:
- `_handle_builder_judge_start` (L335) — starts a builder-judge loop
- `_handle_builder_judge_list` (L350) — lists builder-judge runs
- `_handle_builder_judge_status` (L358) — gets status of a specific run
- `_handle_builder_judge_quality_gate` (L369) — runs a quality gate check

### Risk Note
These methods use `_send_action_error` (not just `_send_json_error`) for some
error paths — check that the mixin has access to this method. They also use
several import groups:
- `BUILDER_JUDGE_START_VALIDATION_ERRORS`, `BUILDER_JUDGE_READ_BAD_REQUEST_ERRORS`,
  `BUILDER_JUDGE_QUALITY_GATE_BAD_REQUEST_ERRORS`, `BuilderJudgeRouteNotFound`,
  `build_builder_judge_list_payload`, `build_builder_judge_quality_gate_payload`,
  `build_builder_judge_start_payload`, `build_builder_judge_status_payload`
  — all from `devflow.control_room.operating_layer_builder_judge_routes`

### How to Execute

1. **Load the fleet skill**: `/skills load multi-model-fleet devflow-analysis handoff-adapter`
2. **Check fleet status**: `~/.hermes/scripts/model-router status`
3. **Run the v2 builder-judge loop** (NOTE: 5 parameters now — source file + methods):
   ```bash
   ~/.hermes/skills/software-development/multi-model-fleet/scripts/builder-judge-loop.sh \
     "Extract the builder-judge handler methods from OperatingLayerRequestHandler into a BuilderJudgeHandlerMixin class in operating_layer_builder_judge_handlers.py. Follow the ObsidianHandlerMixin pattern: module docstring, from __future__ import annotations, imports from devflow.control_room.operating_layer_builder_judge_routes, then the mixin class with all 4 methods. The host class provides self._send_json, self._send_json_error, self._send_action_error, self._read_json_body, self.server.repo_root." \
     "/Users/jewelbait/Desktop/Local AI Dev Team/src/devflow/control_room/operating_layer_builder_judge_handlers.py" \
     "/Users/jewelbait/Desktop/Local AI Dev Team" \
     "src/devflow/control_room/operating_layer_server.py" \
     "_handle_builder_judge_start,_handle_builder_judge_list,_handle_builder_judge_status,_handle_builder_judge_quality_gate"
   ```
4. **After the loop**: wire the mixin into `operating_layer_server.py`:
   - Add `from devflow.control_room.operating_layer_builder_judge_handlers import BuilderJudgeHandlerMixin`
   - Change class to `class OperatingLayerRequestHandler(BuilderJudgeHandlerMixin, ObsidianHandlerMixin, BrainstormHandlerMixin, BaseHTTPRequestHandler)`
   - Remove the 4 builder-judge handler methods from the class body
   - Remove builder-judge imports from the server (now in mixin)
   - Run `ruff --select F401` to find unused imports
   - Search tests for `monkeypatch.setattr(operating_layer_server,` and update any that patch moved functions
   - Run the test command above
5. **If new patterns found**: add them with `pattern_inject.py add ...`
6. **Record metrics**: the script does this automatically, but verify with `run_metrics.py list`
7. **Commit** (with user approval — commit ≠ push)

### Remaining Handler Groups (after builder-judge)

| Group | Methods | Est. Lines | Notes |
|:---|:---|:---|:---|
| Workbench | 2 | ~80 | `_handle_workbench_implement` is 76 lines with async branching |
| Gates/Local Model | 3 | ~40 | Straightforward |
| Refactor | 2 | ~30 | Straightforward |
| Misc (browse, repo_set, agents, architecture_artifact, task_write_context) | 5 | ~80 | Core infrastructure — extract last |

## Constraints

- Do NOT edit files without running tests after
- Do NOT push without explicit user approval
- Use the fleet skill's v2 tools: `extract_methods.py`, `strip_output.py`, `run_metrics.py`, `builder-judge-loop.sh`
- All local models: `ctx=131072`, reasoning ON, `max_tokens=4096`
- Only Ornith 9B (light group) runs in parallel with heavy models
- Heavy models (Ornith 35B, Qwen 27B, Qwopus 35B) — only ONE at a time, use `model-router start`
- The v2 builder-judge-loop.sh takes 5 params: task, output_file, project_root, source_file, method_names

## Fleet Quick Reference

```bash
# Check what's running
~/.hermes/scripts/model-router status

# Start a model (stops heavy-group siblings first)
~/.hermes/scripts/model-router start ornith-35b   # builder
~/.hermes/scripts/model-router start 8083          # Qwen 27B (judge)

# V2 builder-judge loop (5 params — includes source file + methods)
~/.hermes/skills/software-development/multi-model-fleet/scripts/builder-judge-loop.sh \
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

- `operating_layer_server.py` is under 600 lines
- All domain handlers live in `operating_layer_<domain>_handlers.py` mixin modules
- 95+ tests passing
- Ruff clean
- Pattern database has 10+ patterns
- Metrics show builder_valid_syntax ≥ 80% and glm_takeover ≤ 50% for automated runs
- Builder-judge loop converges in 1 round for most extractions
