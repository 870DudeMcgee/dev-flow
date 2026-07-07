# Code Map

## What this repo does

DevFlow is the local operating layer that turns a user's rough idea into a verified product implementation through brainstorm, specification, planning, planning review, bounded worker delegation, builder/judge execution, and evidence-backed verification.

## Layout

- `src/devflow/control_room/` - active control-room implementation. New product behavior belongs here.
- `src/devflow/cli.py` - Typer CLI entry point and command wiring.
- Legacy runtime note: `src/devflow/_legacy/` and pure top-level legacy shims were removed. Do not recreate them.
- `tests/` - pytest coverage for control-room commands, projections, dogfood, release gates, and safety behavior.
- `docs/` - intentionally sparse active docs. The active source of truth is `docs/DEVFLOW_SOURCE_OF_TRUTH.md`.
- `docs/_quarantine_2026-07-07/` - non-authoritative historical recovery material. Do not load as active context unless explicitly requested.
- `.devflow/` - ignored local runtime materialization created by DevFlow commands. Seed/template authority lives in `src/devflow/control_room/seed.py`.
- `graphify-out/` - generated local architecture evidence. Use it for cleanup review only when requested; do not treat it as canonical source or blindly commit the full directory.

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
2. `docs/DEVFLOW_SOURCE_OF_TRUTH.md` - canonical product and architecture direction.
3. `docs/README.md` - active docs index.
4. `docs/local-worker-policy.md` - compact local worker boundary when local model work is explicitly needed.
5. `docs/verification-ledger.md` - factual evidence history when rerunning expensive verification.

## What to skip

- Quarantined historical docs under `docs/_quarantine_2026-07-07/` unless the user explicitly asks for recovery or comparison.
- Deleted legacy runtime paths such as `src/devflow/_legacy/` and old top-level shims; do not restore them for current product work.
- Archived workflow docs or stale plans that conflict with the source-of-truth loop.
- `.devflow/` runtime evidence unless the current task explicitly needs local DevFlow state. Use `src/devflow/control_room/seed.py` for seed/template authority.
- The deleted root `public/` static surface for current UI work. It was older marketing/simulator content, not the active operating-layer browser surface.
- Non-local adapters, autonomous route selection, memory, or unapproved dashboard expansion unless an approved active spec promotes that slice.

## Owners / contacts

- Primary: Josh

## Last reviewed

2026-07-07
