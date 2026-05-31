# Agent Registry Runtime Handoff - 2026-05-31

## Status

in-progress

## Files Changed

- `docs/architecture/agent-registry-and-adapter-runtime.md` defines the next provider/agent/role registry and adapter-runtime direction.
- `README.md`, `AGENTS.md`, `PRODUCT_NORTH_STAR.md`, `.codex`, `.github`, `.devflow`, and active docs now point at the shell-worker control room plus registry/manual/shell-alignment sequence.
- Quarantined archive material, stale root notes, and stale top-level plans were removed from the active repo.

## Verification

- `.venv/bin/python -m pytest -q`: pass, `262 passed, 6 skipped`
- `.venv/bin/devflow doctor`: pass, all checks reported `ok`
- stale-context scan for active docs/control-room/test/example surfaces: pass, no archive or old model-routing references found
- final git checkpoint before this handoff: `9b35929 docs: align agent registry runtime direction`, merged to `main` and pushed to `origin/main`

## Risks

- Do not restore archived legacy workflow material unless it is intentionally promoted back as active, non-archived source.
- Do not jump to provider-backed adapters, autonomous routing, Aider, Hermes, OpenCode, memory, scheduling, or web dashboards before registry loading, manual packets, and shell alignment exist.
- Runtime changes must stay under `src/devflow/control_room/`; top-level modules and `src/devflow/_legacy/` are compatibility or legacy surfaces only.

## Next Safe Action

- Implement registry loading for agents/providers/roles under `src/devflow/control_room/`, with focused tests proving valid registry load, disabled/default seed behavior, and clear validation errors.
