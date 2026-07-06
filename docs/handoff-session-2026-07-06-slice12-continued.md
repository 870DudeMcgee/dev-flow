# DevFlow Refactor — Session Handoff (Slice 12 Continued)

## State

- Server: 153 lines (pure routing + static assets — decomposition complete)
- Tests: 60 passing across local model test files (full suite times out — targeted tests are source of truth)
- Ruff: clean
- Committed: `c7465b2a` (fleet reconfigure + 3 modules extracted)
- Working tree: has unrelated docs/.context-map changes, no source changes
- Fleet: Qwen3-Coder-Next (:8084, builder), Qwen 27B (:8083, judge), Ornith 35B (:8086, scout)

## What Was Done This Session

1. **Built `extract_module.py`** — deterministic AST-based module-level function extractor. No LLM needed. Handles imports, constants, helper references, monkeypatch preservation, facade re-exports, ruff auto-fix, and test/lint verification in one command.
2. **Extracted 3 of 6 modules** from `local_ai_fleet.py`:
   - `local_ai_ollama.py` (3 functions, 62 lines) ✅
   - `local_ai_nightly_plan.py` (2 functions, 33 lines) ✅
   - `local_ai_switch.py` (3 functions, 99 lines) ✅
3. **Reconfigured fleet** — retired Ornith 9B and Qwopus 35B, moved Qwen3-Coder-Next to port 8084, kept Ornith 35B as scout on 8086.
4. **Updated AGENTS.md** — fleet routing table in first 20 lines, tool routing table, corrected worker policy.
5. **Wrote fleet-routing-brief.md** — constraints for Codex sessions.

## Target (Remaining)

File: `src/devflow/control_room/local_ai_fleet.py` (1061 lines after 3 extractions, was 1470)

Extract 3 more modules using `extract_module.py`:

### Module 4: `local_ai_scout_capacity.py`
Functions:
- `build_local_ai_scout_capacity_result`
- `render_local_ai_scout_capacity_json`
- `scout_openai_base_url`
- `_resolve_concurrency`
- `_capacity_report_dir`
- `_latest_scout_capacity_concurrency`
- `_load_latest_scout_capacity`
- `_latest_scout_capacity_failed_at_one`
- `_new_capacity_run_id`
- `_loaded_model_state_ok`
- `_p95`
- `_count_output_quality_failures`

### Module 5: `local_ai_worker_wave.py`
Functions:
- `build_local_ai_scout_pack_result`
- `build_local_ai_worker_wave_result`
- `_run_wave_jobs`
- `_run_wave_packet`
- `_run_wave_attempt_for_capacity`
- `render_local_ai_scout_pack_json`
- `render_local_ai_worker_wave_json`
- `_load_worker_wave_jobs`
- `_load_task_packet_file`
- `_load_structured_payload`
- `_resolve_packet_path`

### Module 6: `local_ai_snapshot.py`
Functions:
- `build_local_ai_snapshot`
- `build_local_ai_recommendation`
- `render_local_ai_snapshot_json`
- `render_local_ai_snapshot_lines`
- `render_local_ai_recommendation_json`
- `render_local_ai_recommendation_lines`
- `_supervisor_target`
- `_nightly_choose_qwen_profile`
- `_scout_target`
- `_lane_payload`
- `_runtime_lock_payload`
- `_active_model_processes`
- `_target_label`
- `_mapping`
- `_dict_rows`
- `_string_rows`

## How to Extract (One Command Per Module)

```bash
cd "/Users/jewelbait/Desktop/Local AI Dev Team"

# Module 4: scout_capacity
.venv/bin/python ~/.hermes/skills/software-development/local-fleet-efficiency/scripts/extract_module.py \
  --source src/devflow/control_room/local_ai_fleet.py \
  --new-module src/devflow/control_room/local_ai_scout_capacity.py \
  --functions "build_local_ai_scout_capacity_result,render_local_ai_scout_capacity_json,scout_openai_base_url,_resolve_concurrency,_capacity_report_dir,_latest_scout_capacity_concurrency,_load_latest_scout_capacity,_latest_scout_capacity_failed_at_one,_new_capacity_run_id,_loaded_model_state_ok,_p95,_count_output_quality_failures" \
  --pytest "tests/test_local_ai_command.py" \
  --python .venv/bin/python --ruff .venv/bin/ruff --project-root . \
  --write-json .devflow/evidence/extract-4-capacity.json

# Module 5: worker_wave
.venv/bin/python ~/.hermes/skills/software-development/local-fleet-efficiency/scripts/extract_module.py \
  --source src/devflow/control_room/local_ai_fleet.py \
  --new-module src/devflow/control_room/local_ai_worker_wave.py \
  --functions "build_local_ai_scout_pack_result,build_local_ai_worker_wave_result,_run_wave_jobs,_run_wave_packet,_run_wave_attempt_for_capacity,render_local_ai_scout_pack_json,render_local_ai_worker_wave_json,_load_worker_wave_jobs,_load_task_packet_file,_load_structured_payload,_resolve_packet_path" \
  --pytest "tests/test_local_ai_command.py" \
  --python .venv/bin/python --ruff .venv/bin/ruff --project-root . \
  --write-json .devflow/evidence/extract-5-worker-wave.json

# Module 6: snapshot
.venv/bin/python ~/.hermes/skills/software-development/local-fleet-efficiency/scripts/extract_module.py \
  --source src/devflow/control_room/local_ai_fleet.py \
  --new-module src/devflow/control_room/local_ai_snapshot.py \
  --functions "build_local_ai_snapshot,build_local_ai_recommendation,render_local_ai_snapshot_json,render_local_ai_snapshot_lines,render_local_ai_recommendation_json,render_local_ai_recommendation_lines,_supervisor_target,_nightly_choose_qwen_profile,_scout_target,_lane_payload,_runtime_lock_payload,_active_model_processes,_target_label,_mapping,_dict_rows,_string_rows" \
  --pytest "tests/test_local_ai_command.py" \
  --python .venv/bin/python --ruff .venv/bin/ruff --project-root . \
  --write-json .devflow/evidence/extract-6-snapshot.json
```

## Known Issues to Watch For

1. **Helper references between modules** — `local_ai_scout_capacity` calls `_load_worker_wave_jobs` and `_run_wave_attempt_for_capacity` which will be in `local_ai_worker_wave` (extracted next). The extractor handles this by importing from the facade with `_fleet.helper()` lazy import pattern. But if both modules try to import from each other through the facade, there may be circular import issues. Extract in order (capacity before worker_wave) to minimize this.

2. **`_dict_rows` is shared** — used by ollama (already extracted), switch (already extracted), and snapshot (to be extracted). Each extracted module gets its own copy of the constant/helper if it's a module-level function. If `_dict_rows` is still in the facade when snapshot is extracted, the extractor will import it via `_fleet._dict_rows()`. After snapshot extraction, `_dict_rows` should be gone from the facade — check if it needs to be a shared utility.

3. **Constants used as default parameter values** — `_LOCAL_AI_SCOUT_KEEP_ALIVE`, `_LOCAL_AI_SCOUT_START_TIMEOUT_SECONDS`, `DEFAULT_SCOUT_CAPACITY_*` constants. The extractor copies these into each module that references them. This is fine — they're small and self-contained.

4. **Monkeypatch targets** — tests patch `local_ai_fleet.urllib.request`, `local_ai_fleet.inspect_ollama_loaded_models`, `local_ai_fleet.load_expected_local_model_manifest`, `local_ai_fleet.local_model_server.*`, etc. The extractor scans test files and preserves imports in the facade with `# noqa: F401`.

5. **`local_ai_command.py` must NOT need import changes** — the facade re-export pattern preserves backward compatibility. If any extraction breaks this, the extractor's test verification will catch it.

## What "Done" Looks Like

- `local_ai_fleet.py` is ~50 lines (facade re-exports + constants + error class)
- 6 focused modules extracted (3 done, 3 remaining)
- `local_ai_command.py` has NO import changes
- `tests/test_local_ai_command.py` — all 30 tests passing
- Ruff clean
- Each extraction verified individually with `extract_module.py`
- Commit after all 6 modules are done

## Fleet

| Port | Model | Role |
|---|---|---|
| 8084 | Qwen3-Coder-Next (80B-A3B) | Builder/coder (non-thinking) |
| 8083 | Qwen 27B (Q5 MTP) | Judge (thinking mode) |
| 8086 | Ornith 35B (Q4) | Scout |

One heavy at a time. Router handles swaps. Fleet status is informational.

## Constraints

- Do NOT push without explicit user approval
- Use `extract_module.py` for all extractions — no manual patching
- Use `local_test_runner.py` for verification (but `extract_module.py` has built-in verification)
- Never read `local_ai_fleet.py` directly in frontier context — it's > 50 lines
- Never use `rm` with globs that match `local_ai_fleet.py` or `local_ai_command.py`
- If an extraction fails, read the JSON verdict's `repair_hints` — don't read raw pytest logs
