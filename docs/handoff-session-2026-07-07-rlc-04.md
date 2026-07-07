# DevFlow Refactor — Handoff (RLC-04)

## State
- Committed: f871f576
- Tests: 71 passing
- Fleet: see AGENTS.md

## Task
Add a brainstorm-to-classification gate. The brainstorm pipeline should produce a `classification.json` artifact that outputs: work type, rationale, deterministic-tool eligibility, eligible presets, recommended preset, and why alternatives were not recommended. This gate is rule-based (no LLM needed) and writes into the existing pipeline run storage. The classification is visible and editable via a new server route.

## Target files
- Modify: `src/devflow/control_room/brainstorm_pipeline.py` — add classification builder functions
- Modify: `src/devflow/control_room/operating_layer_brainstorm_handlers.py` — add classification route handler
- Modify: `src/devflow/control_room/operating_layer_brainstorm_routes.py` — add route payload builder
- Modify: `src/devflow/control_room/operating_layer_server.py` — register new routes
- New: `tests/test_brainstorm_classification.py` — focused classification tests

## Commands
- `env PYTHONPATH=src:. python -m pytest tests/test_brainstorm_classification.py -v`
- `env PYTHONPATH=src:. python -m ruff check src/devflow/control_room/brainstorm_pipeline.py src/devflow/control_room/operating_layer_brainstorm_handlers.py src/devflow/control_room/operating_layer_brainstorm_routes.py src/devflow/control_room/operating_layer_server.py tests/test_brainstorm_classification.py`

## Constraints
- Follow AGENTS.md workflow
- Classification is rule-based — keyword/pattern matching, no LLM calls
- Must not launch Hermes or create pipeline runs — classification is a read-only gate that produces a preview artifact
- Classification output must be serializable to `classification.json` in a pipeline run directory
- Existing brainstorm tests must continue to pass
- Do not push without approval
