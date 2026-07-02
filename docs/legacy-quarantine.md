# Legacy Quarantine Index

The current Dev-Flow product is the local-first control room implemented under `src/devflow/control_room/`.

WARNING: stale context can be harmful when it looks like current authority. Legacy or archived direction may be useful history, but it must not steer new control-room, registry, adapter-runtime, or worker implementation unless it is intentionally rewritten into the current product contract.

The paths below are legacy or compatibility material. They may be useful for historical inspection, but they must not steer new supervisor-loop, registry, adapter-runtime, or worker implementation.

## Runtime Code

- `src/devflow/_legacy/`: deleted pre-control-room implementation.
- `src/devflow/agents/`: deleted compatibility shims for old agent imports.
- `src/devflow/schemas/`: deleted legacy workflow schemas.

## Archived Docs And Local Artifacts

- Legacy software-factory archives: quarantined outside the active repository tree.
- Local archived context and historical artifacts: quarantined outside the active repository tree.

## Current Authority

- `PRODUCT_NORTH_STAR.md`
- `docs/mvp-contract.md`
- `docs/control-room-mvp.md`
- `docs/roadmap.md`
- `src/devflow/control_room/`

Manual quarantine is complete for deleted paths when active imports, tests, and current docs no longer depend on them.

Use [architecture/graphify-architecture-baseline.md](architecture/graphify-architecture-baseline.md) and `graphify-out/graph.json` before pruning remaining legacy-labeled surfaces. Graphify should confirm that active control-room paths no longer depend on the target, but it is supporting evidence only; tests and focused source inspection remain required.

Do not restore quarantined material into the active repo unless it is intentionally rewritten as current, non-archived authority.
