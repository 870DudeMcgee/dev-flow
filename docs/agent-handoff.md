# Agent Handoff

Date: 2026-05-27

## Current Direction

Dev-Flow is being rebuilt as a local-first control room for parallel AI coding workers.

The previous Dev-Flow direction has been archived. It is no longer the process authority for this repository.

Active source of truth:

- [PRODUCT_NORTH_STAR.md](../PRODUCT_NORTH_STAR.md)
- [docs/control-room-mvp.md](control-room-mvp.md)
- [docs/roadmap.md](roadmap.md)
- [README.md](../README.md)

Archive index:

- [docs/archive/legacy-devflow-software-factory-2026-05-27/README.md](archive/legacy-devflow-software-factory-2026-05-27/README.md)

## Product Boundary

Dev-Flow is not the main coding brain. It coordinates replaceable workers and owns durable state, process isolation, status, logs, questions, result bundles, verification evidence, and merge readiness.

The first milestone is a non-AI control room with shell workers only.

Implemented so far:

- `devflow init`
- `devflow doctor`
- `devflow task create "title"`
- `devflow task list`
- `devflow task show <task_id>`
- `devflow task run <task_id> --worker shell -- <command>`
- `devflow task verify <task_id> -- <command>`
- `devflow dashboard`
- SQLite task state
- task-local logs, result, report, questions, context, and YAML artifacts
- git worktree creation for task workspaces when possible
- directory workspace fallback outside git repos
- verification command execution inside task workspaces
- merge-readiness status for completed and verified tasks

## Required MVP Commands

```bash
devflow init
devflow doctor
devflow task create "title"
devflow task list
devflow task show <task_id>
devflow task run <task_id> --worker shell -- <command>
devflow dashboard
```

## Implementation Posture

- Read the North Star before implementation decisions and use its Periodic Self-Check to catch product drift.
- Prefer direct implementation over ceremonial workflow.
- Do not create legacy task files for this rebuild.
- Do not route implementation through old agent, memory, context-pack, DAG, trace, eval, or unified-diff runner surfaces.
- Salvage useful code only when it supports the new control-room MVP.
- Keep unrelated dirty worktree changes intact.

## Useful Existing Code To Inspect Later

- `src/devflow/cli.py`: current CLI entry point, but likely too broad.
- `src/devflow/worktrees.py`: possible worktree isolation salvage.
- `src/devflow/runner.py`: possible shell and verification helper salvage.
- `src/devflow/failures.py`: possible simple failure taxonomy salvage.

## Acceptance Gauntlet

Create three shell tasks:

1. one succeeds
2. one fails
3. one times out

The CLI and dashboard must show all three accurately with status and logs.

Current verification covers this gauntlet, git-worktree isolation, verification logs, and merge readiness in `tests/test_control_room_shell.py`.

## Known Worktree State At Handoff

Before this documentation reset, the repository already had unrelated dirty files in public-site, agent, manager, script, test, and `.devflow` artifact/task/report areas. Future agents must not revert those unless explicitly asked.
