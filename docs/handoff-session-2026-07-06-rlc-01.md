# DevFlow Refactor — Session Handoff (Repo Loop Cockpit RLC-01)

## State

- Committed: `151e9a5d` (Ornith 35B parallel slots enabled, fleet docs aligned)
- Working tree: has unrelated docs/.context-map changes, no source changes
- Fleet: Ornith 35B (:8084, builder/scout, 3 parallel slots), Qwen 27B (:8083, judge). Ornith 9B, Qwopus, and Qwen3-Coder-Next are retired from active DevFlow use.
- `extract_module.py` proven and ready at `~/.hermes/skills/software-development/local-fleet-efficiency/scripts/extract_module.py`
- Architecture docs: `docs/adr/0002-repo-loop-cockpit-over-hermes-runtime.md` (accepted), `docs/architecture/repo-loop-cockpit-implementation-plan.md` (active ledger)
- RLC-00 (contract alignment) is in_progress per the ledger
- No pipeline run storage exists yet — `.devflow/pipeline-runs/` not created, `pipeline_run.py` not written

## Direction

Dev-Flow is narrowing from broad command center to **selected-repo loop cockpit**. The full direction is in:
- `docs/adr/0002-repo-loop-cockpit-over-hermes-runtime.md`
- `docs/architecture/repo-loop-cockpit-implementation-plan.md`
- The user's redesign brief (pasted into this session)

Key principles:
1. **Tool-first**: deterministic tools for mechanical work, models only when they add value
2. **Dev-Flow wraps Hermes**: does not rebuild Hermes internals
3. **Pipeline run artifacts** under `.devflow/pipeline-runs/<run_id>/`
4. **Four loop presets**: Spec/Planning, Builder-Judge, Verify-Fix, Refactor/Recovery
5. **Ornith 9B excluded** from Dev-Flow loop routing

## This Slice: RLC-01 — Pipeline Run Storage Model

Per the implementation plan:

> Add a small persistence module with typed helpers:
> - `pipeline_runs_dir(root)`
> - `new_pipeline_run_id()`
> - `create_pipeline_run(root, source)`
> - `load_pipeline_run(root, run_id)`
> - `update_pipeline_run_record(root, run_id, file_name, content)`
> - `append_pipeline_event(root, run_id, event)`
>
> Keep it filesystem-backed and boring. Do not add a database.

### Target files

- New: `src/devflow/control_room/pipeline_run.py`
- New: `tests/test_pipeline_run.py`

### Pipeline run filesystem contract

```text
.devflow/pipeline-runs/<run_id>/
  intent.md
  source.json
  brainstorm.md
  classification.json
  readiness-packet.md
  loop-packet.md
  validation.json
  run-log.jsonl
  artifacts.json
  review.md
```

### Implementation approach

This is a **new module with new tests** — no extraction, no refactoring of existing code. Use standard implementation:

1. Write `pipeline_run.py` with the typed helpers listed above
2. Each helper should be simple filesystem operations — `Path.mkdir`, `json.dumps`/`json.loads`, file append
3. `run_id` format: timestamp slug like `20260706-143022` (simple, sortable, no UUID complexity in V1)
4. `source` parameter for `create_pipeline_run` should accept: repo path, branch, Obsidian source links, handoff metadata
5. `update_pipeline_run_record` writes/overwrites a single file in the run directory
6. `append_pipeline_event` appends a JSON line to `run-log.jsonl`
7. All operations must stay within `.devflow/pipeline-runs/` — no mutation outside that path

### Verification

```bash
cd "/Users/jewelbait/Desktop/Local AI Dev Team"
PYTHONPATH=src .venv/bin/python -m pytest tests/test_pipeline_run.py -q --tb=short
.venv/bin/ruff check src/devflow/control_room/pipeline_run.py tests/test_pipeline_run.py
```

Test cases needed:
- `create_pipeline_run` creates the directory and all minimum files
- `load_pipeline_run` reads back the run correctly
- `update_pipeline_run_record` writes content to the named file
- `append_pipeline_event` appends JSON lines to run-log.jsonl
- All operations refuse to write outside `.devflow/pipeline-runs/`
- `new_pipeline_run_id` produces sortable unique IDs

### After RLC-01 passes

RLC-02 (snapshot projection) depends on RLC-01. The next session should add a `pipeline_run` field to `OperatingLayerSnapshot` that includes selected/current run id, stage, chosen preset, validation status, Hermes run status, next safe action, and key artifact paths.

## Fleet (corrected per this session's research)

| Port | Model | Role | Parallel | Notes |
|---|---|---|---|---|
| 8084 | Ornith 35B (MoE, Q4) | Builder/coder/scout | **3 slots** (`-np 3`) | 75.6 SWE-Bench, reasoning mode, self-scaffolding RL. Primary builder. |
| 8083 | Qwen 27B (Q5, MTP) | Judge | 1 | Thinking mode, genuine second opinion. |

Retired from active DevFlow use: Ornith 9B (:8085), Qwopus 35B (:8086), Qwen3-Coder-Next (:8087).

One heavy *process* at a time. **3 concurrent jobs can run within Ornith 35B's parallel slots.** Don't serialize work that could run in parallel. Router handles swaps. Fleet status is informational.

## Workflow for this slice

This is a **new module + new tests** — not an extraction or refactoring task. Use standard implementation:

1. Read the implementation plan section for RLC-01 (quoted above)
2. Write `pipeline_run.py` — simple filesystem-backed persistence
3. Write `test_pipeline_run.py` — test all helpers
4. Run `local_test_runner.py` for verification
5. Commit

No `extract_module.py` needed (nothing to extract). No builder-judge loop needed (simple filesystem code). This is a direct implementation slice — the kind of work where the supervisor writes the code because it's small and mechanical.

## Constraints

- Do NOT push without explicit user approval
- Use `local_test_runner.py` for verification
- Keep it filesystem-backed and boring — no database, no async, no caching
- All operations must stay within `.devflow/pipeline-runs/`
- Do not modify existing source modules in this slice
- Reference `docs/architecture/repo-loop-cockpit-implementation-plan.md` for the full contract
