# Operating Layer Handoff

## Status

complete

## Files Changed

- `src/devflow/control_room/operating_layer_script.py` (reworked the app script around current orchestrator data, including invalid timestamp guards and current next-action projection)
- `src/devflow/control_room/operating_layer_visual_qa.py` (updated visual checks for the current operating-layer structure)
- `src/devflow/control_room/operating_layer_html.py` and `src/devflow/control_room/operating_layer_styles.py` (aligned the operating-layer UI shell and styles)
- `src/devflow/control_room/brainstorm.py`, `env_loader.py`, and related tests (added Hermes env fallback and local/remote brainstorm profile handling)
- `src/devflow/control_room/agent_registry.py`, `agent_onboarding.py`, `local_agent_discovery.py`, `estimator.py`, `router.py`, and `model_runtime_profiles.py` (added model capability and runtime-profile routing inputs)
- `.devflow/agents/registry.yaml` and `docs/architecture/model-capability-taxonomy.md` (documented model capability dimensions)

## Verification

- `git diff --check`: pass
- `PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_env_loader.py tests/test_brainstorm_workbench.py tests/test_operating_layer.py -q`: pass, `52 passed in 33.78s`
- `PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_agent_registry.py tests/test_router.py tests/test_estimator.py tests/test_scorecard.py tests/test_routing_cli_roots.py tests/test_local_worker_loop.py -q`: pass, `60 passed in 3.05s`

## Risks

- The operating-layer script/style rewrite is large; targeted tests pass, but a live browser smoke is still useful before the next UI milestone.
- Model runtime profile updates are evidence-only and should stay advisory until broader routing policy promotes them.

## Next Safe Action

- Open the operating layer locally and run a live browser smoke across the orchestrator, brainstorm, review, and evidence views.
