# Code Map

## What this repo does

Dev-Flow is a local-first control room for parallel AI coding workers. It owns task state, isolated workspaces, locks, logs, verification evidence, review readiness, and human-controlled promotion while keeping workers replaceable.

## Layout

- `src/devflow/control_room/` - active control-room implementation. New product behavior belongs here.
- `src/devflow/cli.py` - Typer CLI entry point and command wiring.
- `src/devflow/_legacy/` - quarantined legacy software-factory code. Do not add features here.
- `tests/` - pytest coverage for control-room commands, projections, dogfood, release gates, and safety behavior.
- `docs/` - active contracts, architecture notes, roadmap, and handoffs.
- `docs/superpowers/specs/` - approved design specs for larger slices.
- `docs/superpowers/plans/` - implementation plans for agent handoff.
- `.devflow/` - local runtime state and evidence. Do not edit manually unless a specific Dev-Flow command or handoff asks for it.

## Entry points

- CLI: `src/devflow/cli.py`
- Task lifecycle writes: `src/devflow/control_room/task_lifecycle.py`
- Core task service: `src/devflow/control_room/service.py`
- Task packets: `src/devflow/control_room/task_packet.py`
- Project code map: `src/devflow/control_room/code_map.py`
- Freshness loop: `src/devflow/control_room/freshness.py`
- Operating layer snapshot: `src/devflow/control_room/operating_layer.py`
- Release readiness gate: `src/devflow/control_room/release_readiness.py`

## What to read first (worker orientation)

1. `AGENTS.md` - mandatory repo operating rules.
2. `docs/devmode-contract.md` - DevMode discipline and handoff format.
3. `PRODUCT_NORTH_STAR.md` - product identity and periodic self-check.
4. `docs/control-room-mvp.md` - current MVP authority and stable command contract.
5. `docs/roadmap.md` - current sequencing and deferred work.
6. `docs/agent-handoff.md` - active handoff and architecture boundary notes.

## What to skip

- `src/devflow/_legacy/` - quarantined legacy code; do not modify or treat as authority.
- Archived workflow docs or stale plans that conflict with the control-room MVP.
- `.devflow/workspaces/`, `.devflow/worktrees/`, `.devflow/dogfood/`, and `.devflow/release-readiness/` unless the current task explicitly needs local evidence.
- Provider-backed adapters, autonomous route selection, memory, or dashboard expansion unless an approved active spec promotes that slice. Milestone 16 completed registry runtime hardening only; remote model execution and autonomous route selection remain excluded.

## Owners / contacts

- Primary: Josh

## Last reviewed

2026-06-13
