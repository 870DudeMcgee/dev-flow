# DevFlow Refactor — Handoff (RLC-03: Curated Handoff Intake)

## State
- Committed: `e4e897aa`
- Tests: 64 passing (test_pipeline_run + test_operating_layer), ruff clean
- Fleet: see AGENTS.md

## Task
Convert the Obsidian integration from broad card browsing to narrow curated packet intake. Add a new POST route `/api/pipeline/intake` that accepts a curated handoff packet with structured fields (source, repo, intent, constraints, acceptance_criteria, suggested_preset, known_docs_files). This route should validate the packet, optionally create a pipeline run via `create_pipeline_run()`, and return the run_id — but must NOT launch Hermes. Keep existing obsidian card routes untouched.

## Target files
- `src/devflow/control_room/obsidian_task_bridge.py` (modify — add `build_curated_packet_preview` and `create_pipeline_run_from_curated_packet`)
- `src/devflow/control_room/operating_layer_obsidian_handlers.py` (modify — add `_handle_pipeline_intake` handler)
- `src/devflow/control_room/operating_layer_server.py` (modify — register `/api/pipeline/intake` in `_POST_ROUTES`)
- `tests/test_obsidian_task_bridge.py` (modify — add tests for new functions)

## Commands

```bash
# Map
# Use mcp_context_map_orient on obsidian_task_bridge.py and operating_layer_obsidian_handlers.py

# Verify
python3 ~/.hermes/skills/software-development/local-fleet-efficiency/scripts/local_test_runner.py \
  --pytest "tests/test_obsidian_task_bridge.py tests/test_pipeline_run.py tests/test_operating_layer.py" \
  --ruff "src/devflow/control_room/obsidian_task_bridge.py src/devflow/control_room/operating_layer_obsidian_handlers.py src/devflow/control_room/operating_layer_server.py" \
  --project-root . --python .venv/bin/python --task-id rlc-03 \
  --write-json .devflow/evidence/test-results-rlc-03.json
```

## Constraints
- Follow AGENTS.md workflow
- Use local_test_runner.py for verification
- Do not push without approval
- Do NOT modify existing obsidian card routes — additive only
- Do NOT launch Hermes from the intake route
- Use `create_pipeline_run()` from `pipeline_run.py` for run creation
- Accepted packet fields: source, repo, operator_intent, constraints, acceptance_criteria, suggested_preset, known_docs_files (list of paths)
