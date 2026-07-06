# DevFlow Refactor — Session Handoff (Slice 8: Refactor Handlers)

## Goal
Continue the DevFlow operating layer refactor using the multi-model fleet.
Slice 7 (gates/local model handler extraction) is complete — the v2 builder-judge
loop converged in 1 round with zero GLM code generation. The server is now at 433
lines (well under the 600 target). The next extraction target is the refactor
handler group (2 methods, ~30 lines), then misc (6 methods, ~120 lines).

## Motivational Intent
DevFlow is a local-first control room for parallel AI coding workers. The
operating layer server started at 925 lines with 30+ handler methods in a
single god class. We're extracting handlers into per-domain mixin modules
using a builder-judge loop (Ornith 35B generates, Qwen 27B reviews). The
fleet toolchain is built, tested, v2-patched, and proven — Slices 5, 6, and 7
all converged in 1 round with zero GLM intervention.

## Current State (after 7 slices)

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

**Slice 6 — Workbench Handler Extraction (COMPLETE)**
- `operating_layer_workbench_handlers.py` (114 lines) — `WorkbenchHandlerMixin` with 2 methods
- Class: `OperatingLayerRequestHandler(WorkbenchHandlerMixin, BuilderJudgeHandlerMixin, ...)`
- Workbench imports moved from server to mixin
- Converged in 1 round, zero GLM code generation
- 95/95 tests passing, ruff clean
- **New fleet scripts added**: `extract_wiring_context.py`, `compact_handoff.py`
- **Builder reasoning now fed to judge** (loop patch)
- Shared-import bug found: `WorkbenchError` needed by both extracted and remaining methods

**Slice 7 — Gates/Local Model Handler Extraction (COMPLETE)**
- `operating_layer_gates_local_model_handlers.py` (81 lines) — `GatesLocalModelHandlerMixin` with 3 methods
- Class: `OperatingLayerRequestHandler(GatesLocalModelHandlerMixin, WorkbenchHandlerMixin, ...)`
- 8 imports removed from server (architecture_evidence, agent_registry, local_model_ensure, local_model_server, unified_workbench)
- 6 monkeypatch targets updated in test_operating_layer_local_model_routes.py (3 single-line + 3 multi-line)
- Handoff doc noted 3 monkeypatch targets — actually 6 (3 were multi-line format not caught by grep)
- Converged in 1 round, zero GLM code generation
- 95/95 tests passing, ruff clean

### Metrics

| Metric | Slices 1-4 | Slice 5 | Slice 6 | Slice 7 | Target |
|:---|:---|:---|:---|:---|:---|
| Builder valid syntax | 25% | 100% | 100% | 100% | 100% |
| Builder source fed | 25% | 100% | 100% | 100% | 100% |
| Judge saw code | 25% | 100% | 100% | 100% | 100% |
| Judge false approvals | 75% | 0% | 0% | 0% | 0% |
| GLM takeover rate | 100% | 0% | 0% | 0% | 0% |
| Rounds to converge | 0.5 avg | 1 | 1 | 1 | ≤2 |
| GLM tokens per slice | ~25k | ~25k | ~25k | ~3.4k | <5k |

### Codebase Metrics
- `operating_layer_server.py`: 925 → 433 lines (-53%)
- New modules: 8 (lifecycle, brainstorm_handlers, obsidian_handlers, builder_judge_handlers, workbench_handlers, gates_local_model_handlers, static/, assets rewrite)
- Tests: 95 passing across 9 test files
- Ruff: clean
- Pattern database: 11 patterns from 7 slices
- Metrics database: 7 runs recorded

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

## Next Steps — Slice 8: Refactor Handler Extraction

### Target
Extract 2 handler methods into `RefactorHandlerMixin`:
- `_handle_refactor_start` (L272) — starts a refactor loop (~15 lines)
- `_handle_refactor_status` (L287) — queries refactor run status (~15 lines)

### Why This Is the Highest-Value Next Target
- **Cleanest extraction**: only 2 methods, self-contained domain
- **No monkeypatch targets**: no tests patch the refactor handler imports on the server module
- **Simple import surface**: 4 imports to move, only 1 shared (`ProjectRegistryError`)
- **Completes the "refactor" group** from the original remaining-hhandlers plan
- **Projected server**: 433 → ~403 lines
- After this, only the misc group (6 heterogeneous methods) remains

### Risk Notes
- **Shared imports** (run `extract_wiring_context.py` for full report):
  - `ProjectRegistryError` — used in 1 remaining method (`_handle_snapshot` at L165)
  - `resolve_project_root` — used in remaining utility methods (`_payload_project_root`, `_query_project_root`)
  - `HTTPStatus` — used everywhere (stdlib, keep in server)
  - `Path` — used in remaining methods (stdlib, keep in server)
- **No monkeypatch targets** — no tests patch `refactor_loop` functions on the server module
- Imports needed in the mixin (all from existing modules, no new deps):
  - From `devflow.control_room.refactor_loop`: `RefactorLoopError`, `load_refactor_run_status`, `require_refactor_approval`, `start_refactor_loop`
  - From `devflow.control_room.project_registry`: `ProjectRegistryError`
  - From `http`: `HTTPStatus`
- `_handle_refactor_status` is a GET handler (takes `query: dict[str, list[str]]`) — different signature from the POST handler
- Both methods use `self._send_json`, `self._send_json_error`, `self._read_json_body`, `self._payload_project_root`, `self._query_project_root` — all host class methods

### How to Execute (Optimized Flow — ~3.4k GLM tokens)

1. **Load the fleet skill**: `/skills load multi-model-fleet devflow-analysis`
2. **Check fleet status**: `~/.hermes/scripts/model-router status`
3. **Run compact handoff** (instead of reading this full doc):
   ```bash
   ~/.hermes/hermes-agent/venv/bin/python3 ~/.hermes/skills/software-development/multi-model-fleet/scripts/compact_handoff.py docs/handoff-session-2026-07-06-slice8.md --slice 8
   ```
4. **Run the v2 builder-judge loop** (5 parameters):
   ```bash
   bash ~/.hermes/skills/software-development/multi-model-fleet/scripts/builder-judge-loop.sh \
     "Extract the refactor handler methods from OperatingLayerRequestHandler into a RefactorHandlerMixin class in operating_layer_refactor_handlers.py. Follow the GatesLocalModelHandlerMixin pattern: module docstring, from __future__ import annotations, imports from devflow.control_room.refactor_loop (RefactorLoopError, load_refactor_run_status, require_refactor_approval, start_refactor_loop), from devflow.control_room.project_registry (ProjectRegistryError), from http (HTTPStatus), then the mixin class with both methods. The host class provides self._send_json, self._send_json_error, self._read_json_body, self._payload_project_root, self._query_project_root." \
     "/Users/jewelbait/Desktop/Local AI Dev Team/src/devflow/control_room/operating_layer_refactor_handlers.py" \
     "/Users/jewelbait/Desktop/Local AI Dev Team" \
     "src/devflow/control_room/operating_layer_server.py" \
     "_handle_refactor_start,_handle_refactor_status"
   ```
5. **Run wiring context** (replaces full server file read):
   ```bash
   ~/.hermes/hermes-agent/venv/bin/python3 ~/.hermes/skills/software-development/multi-model-fleet/scripts/extract_wiring_context.py \
     "src/devflow/control_room/operating_layer_server.py" \
     "_handle_refactor_start,_handle_refactor_status" \
     "src/devflow/control_room/operating_layer_refactor_handlers.py"
   ```
   This tells you exactly which imports to remove and which are shared.
6. **Wire the mixin into `operating_layer_server.py`**:
   - Add `from devflow.control_room.operating_layer_refactor_handlers import RefactorHandlerMixin`
   - Change class to `class OperatingLayerRequestHandler(RefactorHandlerMixin, GatesLocalModelHandlerMixin, WorkbenchHandlerMixin, BuilderJudgeHandlerMixin, ObsidianHandlerMixin, BrainstormHandlerMixin, BaseHTTPRequestHandler)`
   - Remove the 2 handler methods from the class body
   - Remove imports that are ONLY used by these methods (per wiring context report)
   - **Keep shared imports** (`ProjectRegistryError`, `resolve_project_root`, `HTTPStatus`, `Path`) — they're used by remaining methods
   - Run `ruff check` (full, not just F401) to verify
7. **Check for monkeypatch targets** (likely none, but verify):
   ```bash
   grep -rn "monkeypatch.setattr.*operating_layer_server.*refactor" tests/
   grep -rn "monkeypatch.setattr.*operating_layer_server.*start_refactor\|load_refactor" tests/
   ```
8. **Run the full test suite** (9 files, not a subset)
9. **If new patterns found**: add them with `pattern_inject.py add ...`
10. **Record metrics**: the script does this automatically, but verify with `run_metrics.py list`
11. **Commit** (with user approval — commit ≠ push)

### Remaining Handler Groups (after refactor)

| Group | Methods | Est. Lines | Notes |
|:---|:---|:---|:---|
| Misc (snapshot, browse, repo_set, agents, actions_run, task_write_context) | 6 | ~120 | Heterogeneous — consider splitting into 2 mixins: (1) browse+snapshot+repo_set, (2) agents+actions_run+task_write_context. Complex import surface with inline imports in `_handle_agents_list`. |

### Server Structure After Slice 8 (Projected ~403 lines)

```
operating_layer_server.py (~403 lines)
├── Imports (~45 lines)
├── Constants (~5 lines)
├── OperatingLayerHTTPServer class (~10 lines)
├── OperatingLayerRequestHandler class
│   ├── Route dispatch tables (~80 lines)
│   ├── Misc handlers (6 methods, ~120 lines) ← next extraction target
│   │   ├── _handle_snapshot
│   │   ├── _handle_actions_run
│   │   ├── _handle_browse
│   │   ├── _handle_repo_set
│   │   ├── _handle_agents_list
│   │   └── _handle_task_write_context
│   ├── Infrastructure methods (~110 lines) ← stays in server
│   │   ├── _payload_project_root
│   │   ├── _query_project_root
│   │   ├── _read_json_body
│   │   ├── _send_text / _send_text_headers
│   │   ├── _send_artifact
│   │   ├── _send_json / _send_json_error
│   │   ├── _send_action_error
│   │   └── log_message
│   └── do_GET / do_POST dispatchers (~30 lines)
└── Re-export comment
```

## Constraints

- Do NOT edit files without running tests after
- Do NOT push without explicit user approval
- Use the fleet skill's v2 tools: `extract_methods.py`, `strip_output.py`, `run_metrics.py`, `builder-judge-loop.sh`
- **Use `extract_wiring_context.py` BEFORE removing imports** — it catches shared-import bugs
- **Use `compact_handoff.py`** instead of reading the full handoff doc — saves ~10k tokens
- All local models: `ctx=131072`, reasoning ON, `max_tokens=4096`
- Only Ornith 9B (light group) runs in parallel with heavy models
- Heavy models (Ornith 35B, Qwen 27B, Qwopus 35B) — only ONE at a time, use `model-router start`
- The v2 builder-judge-loop.sh takes 5 params: task, output_file, project_root, source_file, method_names
- The script needs `bash` prefix (not directly executable): `bash ~/.hermes/skills/.../builder-judge-loop.sh`
- Builder reasoning is now fed to the judge automatically (Slice 6 patch)

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

# Wiring context for post-extraction GLM wiring (replaces full file reads)
~/.hermes/hermes-agent/venv/bin/python3 ~/.hermes/skills/software-development/multi-model-fleet/scripts/extract_wiring_context.py <source_file> <method1,method2,...> [new_module_path]

# Compact handoff extraction (replaces full doc reads)
~/.hermes/hermes-agent/venv/bin/python3 ~/.hermes/skills/software-development/multi-model-fleet/scripts/compact_handoff.py <handoff_doc.md> [--slice N]

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

- `operating_layer_server.py` is well under 600 lines (currently 433, refactor extraction removes ~30 → ~403)
- All domain handlers live in `operating_layer_<domain>_handlers.py` mixin modules
- 95+ tests passing
- Ruff clean
- Pattern database has 11+ patterns
- Metrics show builder_valid_syntax ≥ 80% and glm_takeover ≤ 50% for automated runs
- Builder-judge loop converges in 1 round for most extractions
- GLM token consumption under 5k per slice (using compact_handoff + wiring_context)
