# Agent Handoff

Date: 2026-07-02

Status: Historical/resume reference, not startup authority.

For ordinary product or code work, start with `AGENTS.md`, `README.md`,
`docs/control-room-mvp.md`, `docs/operator-centered-mission.md`, and
`docs/roadmap.md`. Use this file only when a task explicitly needs old
milestone context.

Use `<repo-root>` for portable command examples. The old local checkout path
`/Users/jewelbait/Desktop/DevFlow` is quarantined and must not be restored into
active authority unless a useful part is intentionally rewritten as current
source.

## Current Authority

- `AGENTS.md`
- `README.md`
- `docs/control-room-mvp.md`
- `docs/operator-centered-mission.md`
- `docs/roadmap.md`
- `docs/devflow-operating-model.md`
- `docs/read-only-control-room-agent.md`
- `docs/devmode-devflow-boundary.md`
- `src/devflow/control_room/`

## Historical Context

The old per-milestone handoff archive under `docs/handoffs/` was deleted on
2026-07-02 as stale context. The cleanup classification and tombstone live in
`docs/architecture/repository-cleanup-ledger.md`.

The legacy runtime paths `src/devflow/_legacy/`, `src/devflow/agents/`, pure
top-level legacy shims, and `src/devflow/schemas/` were also deleted. Current
task and evidence state belongs to `.devflow/tasks/<task_id>/` artifacts and
active implementation under `src/devflow/control_room/`.

## Boundary

Do not route active work through removed legacy imports, deleted static
`public/` assets, or archived handoff/planning files. Preserve future roadmap
material only when it is clearly marked as roadmap/reference rather than
current runtime authority.
