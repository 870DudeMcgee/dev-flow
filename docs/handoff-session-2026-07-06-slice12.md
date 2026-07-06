# DevFlow Refactor — Session Handoff (Slice 11 Complete + Slice 12 Plan)

## Goal

The operating layer server god class has been **fully decomposed**. All domain
handlers (8 mixins) and all HTTP infrastructure methods (1 mixin) now live in
separate modules. The server is at 153 lines — down 83% from the original 925.

The next refactoring target is **local_ai_fleet.py** (1470 lines): a god module
with 8 distinct functional areas crammed into one file.

## Current State (after 11 slices)

### Server Structure (153 lines — pure routing + static assets)

```
operating_layer_server.py (153 lines)
├── Imports (~35 lines, 9 mixin imports + re-exports)
├── OperatingLayerHTTPServer class (~5 lines)
├── OperatingLayerRequestHandler class
│   ├── Route dispatch tables (~50 lines)
│   ├── HTTP dispatchers: do_HEAD, do_GET, do_POST (~30 lines)
│   └── Static asset handlers: _send_index, _send_css, _send_js, _send_healthz (~30 lines)
└── Re-export comment (~3 lines)
```

### Extracted Mixin Modules (9 total, 743 lines)

| Module | Lines | Methods | Slice |
|:---|---:|---:|:---|
| operating_layer_brainstorm_handlers.py | 85 | 6 | 3 |
| operating_layer_obsidian_handlers.py | 72 | 5 | 4 |
| operating_layer_builder_judge_handlers.py | 64 | 4 | 5 |
| operating_layer_workbench_handlers.py | 114 | 2 | 6 |
| operating_layer_gates_local_model_handlers.py | 81 | 3 | 7 |
| operating_layer_refactor_handlers.py | 43 | 2 | 8 |
| operating_layer_browse_snapshot_repo_handlers.py | 64 | 3 | 9 |
| operating_layer_actions_agents_task_context_handlers.py | 101 | 3 | 10 |
| operating_layer_infrastructure_handlers.py | 119 | 10 | 11 |

### Metrics

- `operating_layer_server.py`: 925 → 153 lines (-83%)
- Tests: 108 passing across 10 test files
- Ruff: clean
- Builder-judge convergence: 1-2 rounds, zero GLM code generation since Slice 5
- Slice 11 builder-judge: 1-round approval, 6,537 local tokens

### Local Fleet Efficiency Toolkit (6 scripts + skill v2.0)

- `efficiency_gate.py` — preflight gate + budget check
- `scout_wiring_context.py` — deterministic AST-based scout
- `local_test_runner.py` — test/lint summary script
- `compress_tool_output.py` — context compression via 35B (rewritten)
- `extract_methods.py` — extract method bodies via 35B (new)
- `fleet_efficiency_report.py` — token metrics with subagent + delta mode

Key fleet changes since Slice 10:
- Ornith 35B bumped to `-np 3` (3 parallel slots, 43,776 ctx per slot)
- 9B retired as default compression lane — 35B is now default
- `compress_tool_output.py` handles `reasoning_content` fallback
- SKILL.md rewritten v2.0 — clean top-down structure for first-time agents

### Committed Work

| Commit | Description |
| --- | --- |
| `2cf04208` | Slices 8-10 + local-fleet-efficiency toolkit + doc cleanup |

**Uncommitted**: Slice 11 (infrastructure handlers extraction). Commit before starting Slice 12.

## Next Steps — Slice 12: local_ai_fleet.py Decomposition

### Target

Split `local_ai_fleet.py` (1470 lines) into focused modules along its natural
functional seams. The 35B survey identified 8 distinct functional groups.

### Why This Is the Next Target

- **Largest Python god module** in control_room/ (1470 lines, 40+ functions)
- **Clear functional seams** — 8 groups identified by 35B survey, each cohesive
- **Single importer** — only `local_ai_command.py` imports from it (plus tests)
- **Test coverage exists** — `test_local_ai_command.py` (1411 lines) exercises it
- **Not deferred by hotspot plan** — the hotspot plan defers this BUT it was
  written before the server refactor completed. With the server done, this is
  the next biggest god module.

### Functional Groups Identified (35B Survey)

| Group | Functions | ~Lines | Proposed Module |
|:---|:---|---:|:---|
| Scout capacity | `build_local_ai_scout_capacity_result`, `_resolve_concurrency`, `_capacity_report_dir`, `_latest_scout_capacity_*`, `_new_capacity_run_id`, `_loaded_model_state_ok`, `_p95`, `_count_output_quality_failures` | ~250 | `local_ai_scout_capacity.py` |
| Worker wave | `build_local_ai_scout_pack_result`, `build_local_ai_worker_wave_result`, `_run_wave_*`, `render_local_ai_scout_pack_json`, `render_local_ai_worker_wave_json` | ~200 | `local_ai_worker_wave.py` |
| Nightly dry run | `build_local_ai_nightly_dry_run_plan`, `render_local_ai_nightly_dry_run_json` | ~120 | `local_ai_nightly_plan.py` |
| Switch | `build_local_ai_switch`, `render_local_ai_switch_json`, `_stopped_targets` | ~165 | `local_ai_switch.py` |
| Snapshot/recommendation | `build_local_ai_snapshot`, `build_local_ai_recommendation`, `render_*_json/lines`, `_supervisor_target`, `_nightly_choose_qwen_profile` | ~280 | `local_ai_snapshot.py` |
| Ollama inspection | `inspect_ollama_loaded_models`, `inspect_ollama_installed_models`, `start_ollama_model` | ~110 | `local_ai_ollama.py` |
| Shared utilities | `_load_worker_wave_jobs`, `_load_task_packet_file`, `_load_structured_payload`, `_resolve_packet_path` | ~80 | `local_ai_payload_utils.py` |
| Constants/errors | `LocalAICommandError`, `DEFAULT_*` constants | ~10 | stays in `local_ai_fleet.py` as facade |

### Proposed Approach

Unlike the server mixin extractions (Slices 3-11), this is a **module split**
not a **mixin extraction**. The functions are module-level, not class methods.
The approach:

1. Extract each group into its own module
2. Keep `local_ai_fleet.py` as a thin facade that re-exports everything
   (backward compat — `local_ai_command.py` won't need changes)
3. Test with `test_local_ai_command.py` after each extraction

This can be done incrementally — one group at a time — with tests after each.

### Risk Assessment

- **Risk**: LOW-MEDIUM
- `local_ai_command.py` is the only importer (verify with grep before starting)
- Tests in `test_local_ai_command.py` import `local_ai_fleet` directly — if
  functions move, test imports may need updating
- The facade pattern (re-export from `local_ai_fleet.py`) eliminates import changes
- No monkeypatch targets expected — functions are called directly, not patched

### How to Execute

This is NOT a mixin extraction, so the builder-judge loop and scout_wiring_context
don't directly apply. Instead:

1. **Survey** (NEW — use `codebase_survey.py` or manual 35B compression):
   - Verify import graph (who imports what from local_ai_fleet)
   - Identify exact line ranges for each function group
   - Check for shared private helpers across groups

2. **Extract** (one group at a time):
   - Create the new module file with the group's functions + imports
   - Add re-export in `local_ai_fleet.py`: `from .local_ai_new_module import *`
   - Run tests after each extraction

3. **Test**: `local_test_runner.py` with `test_local_ai_command.py`

4. **Receipt**: `fleet_efficiency_report.py`

### Expected Outcome

```
local_ai_fleet.py (~50 lines — facade re-exports)
local_ai_scout_capacity.py (~250 lines)
local_ai_worker_wave.py (~200 lines)
local_ai_nightly_plan.py (~120 lines)
local_ai_switch.py (~165 lines)
local_ai_snapshot.py (~280 lines)
local_ai_ollama.py (~110 lines)
local_ai_payload_utils.py (~80 lines)
```

## Local Fleet Opportunity: codebase_survey.py

### Problem

Planning slices currently requires the frontier model to:
- Read multiple large files (> 50 lines each)
- Identify functional seams and dependencies
- Check import graphs
- Produce structured plans

This consumes significant frontier tokens just for planning.

### Solution

Build a `codebase_survey.py` script that uses the 35B to:
1. Take a directory or file path as input
2. Identify all Python files and their sizes
3. For each file > 500 lines, use the 35B to analyze:
   - Function/class structure
   - Natural seams for splitting
   - Import dependencies
   - Shared vs movable imports
4. Produce a structured JSON plan with extraction candidates

This replaces the manual survey work done in this session (which consumed
~20K frontier tokens reading files and running greps).

### What "Done" Looks Like

- `local_ai_fleet.py` is a thin facade (~50 lines) re-exporting from 6-7 modules
- 108+ tests passing
- Ruff clean
- `codebase_survey.py` script built and tested
- Efficiency receipt produced

## Test Command

```bash
cd "/Users/jewelbait/Desktop/Local AI Dev Team"
PYTHONPATH=src .venv/bin/python -m pytest \
  tests/test_local_ai_command.py \
  -v --tb=short
```

## Lint Command

```bash
cd "/Users/jewelbait/Desktop/Local AI Dev Team"
.venv/bin/ruff check src/devflow/control_room/local_ai_fleet.py src/devflow/control_room/local_ai_*.py
```

## Constraints

- Do NOT edit files without running tests after
- Do NOT push without explicit user approval
- Use the local-fleet-efficiency toolkit where applicable
- Never read files > 50 lines directly in frontier context — use `compress_tool_output.py`
- Never run pytest/ruff directly — use `local_test_runner.py`
- All local models: `ctx=131072`, reasoning ON, `max_tokens=2048+`
- Heavy models (Ornith 35B, Qwen 27B) — only ONE at a time, use `model-router start`
- 35B now runs `-np 3` (3 parallel slots)

## What "Done" Looks Like

- `local_ai_fleet.py` is ~50 lines (facade re-exports only)
- 6-7 focused modules extracted
- 108+ tests passing
- Ruff clean
- `codebase_survey.py` script built and tested
- Efficiency receipt produced
- Local-fleet-efficiency toolkit updated with survey script
