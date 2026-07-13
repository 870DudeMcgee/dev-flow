# DevFlow V2 Code Map

## Purpose

DevFlow turns a rough idea into a verified product change through the V2 stage
chain:

```text
Idea -> Brainstorm -> Spec -> Plan -> Judge -> Build -> Judge -> Verify -> Next human decision
```

The browser and Hermes are both brainstorm entry surfaces. DevFlow owns persisted
stage artifacts and evidence; Hermes also provides messaging, tools, and bounded
worker orchestration. The browser combines brainstorm chat with the live status
board.

Model and machine routing authority is split deliberately:

- `src/devflow/loop/roles.py` defines the seven stable role contracts;
- `src/devflow/loop/models.yaml` (or `DEVFLOW_MODELS_YAML`) defines eligible targets;
- `src/devflow/loop/profiles.yaml` (or `DEVFLOW_PROFILES_YAML`) defines environment preferences;
- `src/devflow/loop/routing.py` resolves roles by override, profile, capability, and cost;
- local endpoint probes establish resident identity; audition evidence establishes role fitness.

See `docs/DEVFLOW_SOURCE_OF_TRUTH.md` for the authoritative model-agnostic and
machine-agnostic contract, current profile meanings, and known implementation gaps.

## Active Layout

- `src/devflow/cli.py` — V2-only Typer entrypoint.
- `src/devflow/loop/` — loop models, state transitions, persistence, scout, and model-slot contracts.
- `src/devflow/control_room/` — V2 status board server, page, and support probes.
- `tests/test_v2_cli.py` — CLI isolation and deterministic fixture regression.
- `tests/test_loop_*.py` — V2 loop behavior.
- `tests/test_control_room_*.py` — status-board support behavior.
- `docs/DEVFLOW_SOURCE_OF_TRUTH.md` — canonical product direction.
- `AGENTS.md` — required agent workflow.

## Entry Points

```bash
PYTHONPATH=src .venv/bin/python -m devflow.cli status serve
PYTHONPATH=src .venv/bin/python -m devflow.cli loop spine-fixture --json
```

The status board defaults to `http://127.0.0.1:8770/`. The fixture command is
deterministic and makes no model calls.

## Orientation Order

1. `AGENTS.md`
2. `docs/DEVFLOW_SOURCE_OF_TRUTH.md`
3. This file
4. The exact `src/devflow/loop/` or `src/devflow/control_room/` module being changed
5. Its focused test file

## Do Not Reintroduce

- retired command surfaces or compatibility shims;
- former browser UI flows;
- unbounded worker orchestration or hidden model starts;
- broad historical plans as active instructions;
- any second chat interface in the status board.
