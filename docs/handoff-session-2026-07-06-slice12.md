# DevFlow Refactor — Session Handoff (Slice 12: local_ai_fleet.py Decomposition)

## State

- Server: 153 lines (pure routing + static assets — decomposition complete)
- Tests: 108 passing across 10 operating-layer test files
- Ruff: clean
- Committed: `4202a16f` (Slice 11: infrastructure handlers)
- Working tree: clean
- Fleet toolkit: 8 scripts, SKILL.md v2.0

## Target

- File: `src/devflow/control_room/local_ai_fleet.py` (1470 lines, 47 functions, 1 class)
- What: Split into focused modules using facade re-export pattern
- Risk: MEDIUM — not a mixin extraction; module-level functions, not class methods
- Why: Largest Python god module in control_room/ after the server is done

## Why NOT the Hotspot Plan's Recommendation

The hotspot plan recommends "Client Action Kernel Extraction" from
`operating_layer_script.py`. That's a JS extraction from an embedded string
constant — different tooling, different workflow, and the local fleet scripts
(`scout_wiring_context.py`, `wire_mixin.py`, `builder-judge-loop.sh`) are all
designed for Python module extraction. `local_ai_fleet.py` is the next biggest
Python god module and fits the existing workflow naturally.

## Proposed Module Split

The 35B survey identified 6 functional groups. Each becomes its own module.
`local_ai_fleet.py` stays as a thin facade that re-exports everything.

| Module | Functions | ~Lines | Purpose |
|:---|:---|---:|:---|
| `local_ai_scout_capacity.py` | `build_local_ai_scout_capacity_result`, `render_local_ai_scout_capacity_json`, `scout_openai_base_url`, `_resolve_concurrency`, `_capacity_report_dir`, `_latest_scout_capacity_*`, `_new_capacity_run_id`, `_loaded_model_state_ok`, `_p95`, `_count_output_quality_failures` | ~250 | Measure safe concurrency for local models |
| `local_ai_worker_wave.py` | `build_local_ai_scout_pack_result`, `build_local_ai_worker_wave_result`, `_run_wave_*`, `render_local_ai_scout_pack_json`, `render_local_ai_worker_wave_json`, `_load_worker_wave_jobs`, `_load_task_packet_file`, `_load_structured_payload`, `_resolve_packet_path` | ~280 | Execute worker waves, build scout packs, load packets |
| `local_ai_nightly_plan.py` | `build_local_ai_nightly_dry_run_plan`, `render_local_ai_nightly_dry_run_json` | ~120 | Generate nightly dry-run plan |
| `local_ai_switch.py` | `build_local_ai_switch`, `render_local_ai_switch_json`, `_stopped_targets` | ~165 | Switch supervisor/scout roles, manage lifecycle |
| `local_ai_snapshot.py` | `build_local_ai_snapshot`, `build_local_ai_recommendation`, `render_*_json/lines` for snapshot+recommendation, `_supervisor_target`, `_nightly_choose_qwen_profile`, `_scout_target`, `_lane_payload`, `_runtime_lock_payload`, `_active_model_processes`, `_target_label`, `_mapping`, `_dict_rows`, `_string_rows` | ~350 | Fleet snapshots, recommendations, manifest target resolution |
| `local_ai_ollama.py` | `inspect_ollama_loaded_models`, `inspect_ollama_installed_models`, `start_ollama_model` | ~110 | Ollama runtime inspection and model start |
| `local_ai_fleet.py` (facade) | `LocalAICommandError`, `DEFAULT_*` constants, re-exports from all modules | ~50 | Backward-compat facade — `local_ai_command.py` won't need changes |

## Key Difference From Slices 3-11

Slices 3-11 extracted **class methods** from a god class into **mixin modules**.
This slice extracts **module-level functions** from a god module into **focused
modules**. The approach is different:

- **No mixin class** — functions move directly to new modules
- **No MRO wiring** — `wire_mixin.py` doesn't apply
- **Facade re-export** — `local_ai_fleet.py` keeps `from .local_ai_new_module import *`
  so `local_ai_command.py` (the only importer) doesn't need changes
- **Incremental** — extract one module at a time, test after each
- **scout_wiring_context.py won't work** — it's designed for class method
  extraction, not module-level function extraction. Use `codebase_survey.py`
  or manual AST inspection instead.

## Imports in local_ai_fleet.py

```
import json
import secrets
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
import yaml
from devflow.control_room import local_model_server
from devflow.control_room.local_model_readiness import (ExpectedLocalModelLane, LocalModelExpectedProfilesManifest, load_expected_local_model_manifest)
from devflow.control_room.local_model_runtime_lock import list_local_model_runtime_status
from devflow.control_room.paths import relative_path
from devflow.control_room.task_packet import TaskPacket, build_task_packet, render_task_packet_text
from devflow.control_room.task_packet_context import is_path_excluded
```

Each new module will need a subset of these imports. Shared imports (used by
multiple groups) include `json`, `Path`, `Any`, and `yaml`. The survey output
has the full analysis if needed.

## Constants (stay in facade)

```python
DEFAULT_LOCAL_AI_PACKET_MAX_CHARS = 200_000       # L26
DEFAULT_SCOUT_CAPACITY_BASE_URL = "http://..."    # L27
DEFAULT_SCOUT_CAPACITY_BASE_URL_WITH_V1 = ...     # L28
DEFAULT_SCOUT_CAPACITY_MODEL = "gemma4-e4b:latest" # L29
DEFAULT_SCOUT_CAPACITY_CANDIDATES = (1, 2, 3)     # L30
DEFAULT_SCOUT_CAPACITY_PASSES = 2                 # L31
DEFAULT_SCOUT_CAPACITY_WARMUP = 1                 # L32
DEFAULT_SCOUT_CAPACITY_TIMEOUT_SECONDS = 120.0    # L33
SCOUT_CAPACITY_REPORT_DIR = Path(...)             # L34
```

These are imported by `local_ai_command.py` and by the capacity module.
Either keep them in the facade and import from there, or move them to
the capacity module and re-export from the facade.

## Who Imports local_ai_fleet

Only one source file imports from it:

```
src/devflow/control_room/local_ai_command.py
  → imports 25+ symbols from local_ai_fleet
```

Test file that exercises it:

```
tests/test_local_ai_command.py (1411 lines, 30 test functions)
  → imports local_ai_fleet directly in 20+ test functions
```

The tests do `from devflow.control_room import local_ai_fleet` and then call
`local_ai_fleet.build_local_ai_*()` etc. The facade re-export pattern means
these test imports keep working without changes.

## Execution Plan (Using New Automated Workflow)

This slice does NOT use `scout_wiring_context.py` or `wire_mixin.py` (those
are for class method extraction). Instead, use a manual + builder-judge
approach with the fleet toolkit where applicable.

### Phase 1: Survey (local fleet)

```bash
# Start 35B
~/.hermes/scripts/model-router start ornith-35b

# Survey the target file (deterministic AST + 35B seam analysis)
python3 ~/.hermes/skills/software-development/local-fleet-efficiency/scripts/codebase_survey.py \
  --target-file src/devflow/control_room/local_ai_fleet.py \
  --write-json .devflow/evidence/survey-local-ai-fleet.json

# Also run compress_tool_output for a second-opinion analysis
python3 ~/.hermes/skills/software-development/local-fleet-efficiency/scripts/compress_tool_output.py \
  --input-file src/devflow/control_room/local_ai_fleet.py \
  --question "List all functions with their line ranges. Group them by functional area. For each group, list which imports it needs and which imports are shared across groups." \
  --max-output-chars 4000 \
  --write-json .devflow/evidence/compress-local-ai-fleet.json
```

### Phase 2: Gate

```bash
python3 ~/.hermes/skills/software-development/local-fleet-efficiency/scripts/efficiency_gate.py check \
  --task-id slice-12-local-ai-fleet \
  --planned-tool-calls 10 --files-to-inspect 3 \
  --will-edit --edit-areas 7 --will-run-tests \
  --needs-builder-judge \
  --user-requested-local-fleet \
  --delegation-planned scout,builder,judge,test-runner \
  --strict --write-json .devflow/evidence/efficiency-gate-slice12.json
```

### Phase 3: Extract One Module at a Time

For each of the 6 modules, use the builder-judge loop to generate the new
module file, then manually add the re-export to the facade.

Example for `local_ai_ollama.py` (simplest module, 3 functions):

```bash
# Builder-judge: generate the new module
bash ~/.hermes/skills/software-development/multi-model-fleet/scripts/builder-judge-loop.sh \
  --skip-baseline \
  "Extract these 3 functions from local_ai_fleet.py into a new module local_ai_ollama.py: inspect_ollama_loaded_models (L1164), inspect_ollama_installed_models (L1199), start_ollama_model (L1234). Imports needed: json, urllib.request, urllib.error, from typing import Any. Add from __future__ import annotations." \
  "/Users/jewelbait/Desktop/Local AI Dev Team/src/devflow/control_room/local_ai_ollama.py" \
  "/Users/jewelbait/Desktop/Local AI Dev Team" \
  "src/devflow/control_room/local_ai_fleet.py" \
  "inspect_ollama_loaded_models,inspect_ollama_installed_models,start_ollama_model"
```

After builder-judge produces the file:
1. Add re-export to `local_ai_fleet.py`: `from .local_ai_ollama import *`
2. Remove the 3 function bodies from `local_ai_fleet.py`
3. Run tests

Repeat for each module. Start with the simplest (ollama) and work toward
the most complex (snapshot/recommendation).

### Phase 4: Test After Each Extraction

```bash
python3 ~/.hermes/skills/software-development/local-fleet-efficiency/scripts/local_test_runner.py \
  --pytest "tests/test_local_ai_command.py" \
  --ruff "src/devflow/control_room/local_ai_fleet.py src/devflow/control_room/local_ai_ollama.py" \
  --project-root . --python .venv/bin/python --task-id slice-12-N \
  --write-json .devflow/evidence/test-results-slice12-N.json
```

### Phase 5: Receipt

```bash
python3 ~/.hermes/skills/software-development/local-fleet-efficiency/scripts/fleet_efficiency_report.py \
  --session-id <SESSION_ID> --task-id slice-12-local-ai-fleet \
  --local-response-dir /tmp/builder-judge \
  --baseline-json .devflow/evidence/token-efficiency-slice11.json \
  --write-json .devflow/evidence/token-efficiency-slice12.json
```

## Recommended Extraction Order

| Order | Module | Functions | ~Lines | Risk |
|---:|:---|---:|---:|:---|
| 1 | `local_ai_ollama.py` | 3 | ~110 | LOW — self-contained, no shared helpers |
| 2 | `local_ai_nightly_plan.py` | 2 | ~120 | LOW — self-contained |
| 3 | `local_ai_switch.py` | 3 | ~165 | LOW-MED — uses `_stopped_targets` |
| 4 | `local_ai_scout_capacity.py` | 11 | ~250 | MED — many private helpers |
| 5 | `local_ai_worker_wave.py` | 9 | ~280 | MED — shares packet loaders with capacity |
| 6 | `local_ai_snapshot.py` | 15 | ~350 | MED-HIGH — most complex, many private helpers |

Extract 1-2 modules per session, test after each. If any extraction breaks
tests, the facade re-export pattern makes it easy to revert — just remove
the `from .new_module import *` line and the old functions are still there.

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
.venv/bin/ruff check \
  src/devflow/control_room/local_ai_fleet.py \
  src/devflow/control_room/local_ai_*.py
```

## Constraints

- Do NOT edit files without running tests after
- Do NOT push without explicit user approval
- Use the local-fleet-efficiency toolkit where applicable
- Never read files > 50 lines directly in frontier context — use `compress_tool_output.py` or `codebase_survey.py`
- Never run pytest/ruff directly — use `local_test_runner.py`
- All local models: `ctx=131072`, reasoning ON, `max_tokens=2048+`
- Heavy models (Ornith 35B, Qwen 27B) — only ONE at a time, use `model-router start`
- 35B runs `-np 3` (3 parallel slots)
- `scout_wiring_context.py` and `wire_mixin.py` do NOT apply to this slice (they're for class method extraction, not module-level function extraction)
- Use `codebase_survey.py` for structure analysis instead
- Use builder-judge loop with `--skip-baseline` for code generation

## What "Done" Looks Like

- `local_ai_fleet.py` is ~50 lines (facade re-exports + constants + error class)
- 6 focused modules extracted
- `local_ai_command.py` has NO import changes (facade handles backward compat)
- `tests/test_local_ai_command.py` — all 30 tests passing
- Ruff clean
- Efficiency receipt produced with delta vs Slice 11
- Compact handoff written for next slice

## Fleet Toolkit State (8 scripts)

| Script | Version | Status |
|:---|:---|:---|
| `efficiency_gate.py` | 1.0 | Ready |
| `scout_wiring_context.py` | 1.0 | Ready (not used this slice — class-method only) |
| `local_test_runner.py` | 1.0 | Ready |
| `compress_tool_output.py` | 2.0 | Ready (35B default, `## ANSWER:` marker extraction) |
| `extract_methods.py` | 1.0 | Ready |
| `codebase_survey.py` | 1.0 | Ready (deterministic AST + 35B seam analysis) |
| `wire_mixin.py` | 1.0 | Ready (not used this slice — class-method only) |
| `fleet_efficiency_report.py` | 1.0 | Ready |

## Compact Handoff

```
# Slice 12: local_ai_fleet.py decomposition

## State
- Server: 153 lines (done). Tests: 108 passing. Ruff: clean.
- Committed: 4202a16f (slice 11). Working tree: clean.

## Target
- File: local_ai_fleet.py (1470 lines, 47 functions, 1 class)
- Split into 6 modules + facade re-export. Risk: MEDIUM.
- NOT a mixin extraction — module-level functions, not class methods.
- scout_wiring_context.py + wire_mixin.py do NOT apply.

## Modules (extract in order)
1. local_ai_ollama.py (3 funcs, ~110 lines) — LOW
2. local_ai_nightly_plan.py (2 funcs, ~120 lines) — LOW
3. local_ai_switch.py (3 funcs, ~165 lines) — LOW-MED
4. local_ai_scout_capacity.py (11 funcs, ~250 lines) — MED
5. local_ai_worker_wave.py (9 funcs, ~280 lines) — MED
6. local_ai_snapshot.py (15 funcs, ~350 lines) — MED-HIGH

## Commands
- Survey: codebase_survey.py --target-file ...local_ai_fleet.py
- Gate: efficiency_gate.py check --task-id slice-12 ...
- Build: builder-judge-loop.sh --skip-baseline "..." ...
- Test: local_test_runner.py --pytest tests/test_local_ai_command.py ...
- Receipt: fleet_efficiency_report.py --baseline-json ...slice11.json ...

## Constraints
- Facade re-export: from .new_module import * in local_ai_fleet.py
- local_ai_command.py must NOT need import changes
- Test after each extraction
```
