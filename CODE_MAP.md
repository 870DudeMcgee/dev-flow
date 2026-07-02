# Code Map

## What this repo does

Dev-Flow is a local-first control room for parallel AI coding workers. It owns task state, isolated workspaces, locks, logs, verification evidence, review readiness, and human-controlled promotion while keeping workers replaceable.

## Layout

- `src/devflow/control_room/` - active control-room implementation. New product behavior belongs here.
- `src/devflow/cli.py` - Typer CLI entry point and command wiring.
- Legacy runtime note: `src/devflow/_legacy/` and pure top-level legacy shims were removed. Do not recreate them.
- `tests/` - pytest coverage for control-room commands, projections, dogfood, release gates, and safety behavior.
- `docs/` - active contracts, architecture notes, roadmap, and compact historical references.
- `docs/architecture/graphify-architecture-baseline.md` - lightweight Graphify cleanup baseline that records generated map metrics and update commands.
- `docs/superpowers/specs/` - preserved design-spec history for larger slices; not startup authority.
- `docs/superpowers/plans/` - preserved implementation-plan history; not startup authority.
- `.devflow/` - ignored local runtime materialization created by Dev-Flow commands. Seed/template authority lives in `src/devflow/control_room/seed.py`.
- `graphify-out/` - generated local architecture evidence. Use it for cleanup review, but do not treat it as canonical source or blindly commit the full directory.

## Entry points

- CLI: `src/devflow/cli.py`
- Task lifecycle writes: `src/devflow/control_room/task_lifecycle.py`
- Core task service: `src/devflow/control_room/service.py`
- Task packets: `src/devflow/control_room/task_packet.py`
- Project code map: `src/devflow/control_room/code_map.py`
- Freshness loop: `src/devflow/control_room/freshness.py`
- Operating layer snapshot: `src/devflow/control_room/operating_layer.py`
- Operating layer browser UI: `src/devflow/control_room/operating_layer_html.py`, `src/devflow/control_room/operating_layer_styles.py`, `src/devflow/control_room/operating_layer_script.py`, and `src/devflow/control_room/operating_layer_server.py`
- Release readiness gate: `src/devflow/control_room/release_readiness.py`

## What to read first (worker orientation)

1. `AGENTS.md` - mandatory repo operating rules.
2. `docs/devmode-contract.md` - DevMode discipline and handoff format.
3. `PRODUCT_NORTH_STAR.md` - product identity and periodic self-check.
4. `docs/control-room-mvp.md` - current MVP authority and stable command contract.
5. `docs/architecture/graphify-architecture-baseline.md` - current generated architecture baseline for cleanup milestones.
6. `docs/roadmap.md` - current sequencing and deferred work.
7. `docs/agent-handoff.md` - compact historical/resume reference when prior milestone context is explicitly needed.

## What to skip

- Deleted legacy runtime paths such as `src/devflow/_legacy/` and old top-level shims; do not restore them for current product work.
- Archived workflow docs or stale plans that conflict with the control-room MVP.
- `.devflow/` runtime evidence unless the current task explicitly needs local Dev-Flow state. Use `src/devflow/control_room/seed.py` for seed/template authority.
- The deleted root `public/` static surface for current UI work. It was older marketing/simulator content, not the active operating-layer browser surface.
- Task-fit/context routing commands are evidence-only. They write derived fit, scout, route, and scorecard artifacts; autonomous route selection and provider-backed execution remain excluded.
- Provider-backed adapters, autonomous route selection, memory, or unapproved dashboard expansion unless an approved active spec promotes that slice.

## Owners / contacts

- Primary: Josh

## Last reviewed

2026-06-17
