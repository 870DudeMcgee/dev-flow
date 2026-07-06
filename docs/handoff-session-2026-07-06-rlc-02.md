# DevFlow Refactor — Handoff (RLC-02: Snapshot Projection)

## State
- Committed: `70087cf4`
- Tests: 26 passing (test_pipeline_run.py), ruff clean
- Fleet: see AGENTS.md

## Task
Add a `pipeline_run` field to the operating layer snapshot so the cockpit UI can show the selected/current run id, stage, chosen preset, validation status, Hermes run status, next safe action, and key artifact paths. Do not copy large artifacts into `/api/snapshot` — only compact metadata.

## Target files
- `src/devflow/control_room/operating_layer.py` (modify — add pipeline_run to snapshot)
- `src/devflow/control_room/operating_layer_first_viewport.py` (modify — project pipeline_run into first viewport)
- `tests/test_operating_layer.py` or focused new test (add pipeline_run assertion)

## Commands

```bash
# Map
# Use mcp_context_map_orient on operating_layer.py and operating_layer_first_viewport.py

# Verify
python3 ~/.hermes/skills/software-development/local-fleet-efficiency/scripts/local_test_runner.py \
  --pytest "tests/test_pipeline_run.py tests/test_operating_layer.py" \
  --ruff "src/devflow/control_room/operating_layer.py src/devflow/control_room/operating_layer_first_viewport.py" \
  --project-root . --python .venv/bin/python --task-id rlc-02 \
  --write-json .devflow/evidence/test-results-rlc-02.json
```

## Constraints
- Follow AGENTS.md workflow
- Use local_test_runner.py for verification
- Do not push without approval
- Do not copy large artifacts into snapshot — compact metadata only
- Reference `docs/architecture/repo-loop-cockpit-implementation-plan.md` RLC-02 section for full contract
