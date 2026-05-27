# devflow

Dev-Flow is being rebuilt as a local-first control room for parallel AI coding workers.

The current product direction is intentionally smaller than the previous software-factory design. Dev-Flow should coordinate replaceable workers, not become the worker itself.

## Active Source Of Truth

- [PRODUCT_NORTH_STAR.md](PRODUCT_NORTH_STAR.md) defines the product identity, end-state, and drift checks for implementation decisions.
- [docs/control-room-mvp.md](docs/control-room-mvp.md) defines the new product direction, MVP scope, files to keep or bypass, runtime structure, and first implementation slice.
- [docs/roadmap.md](docs/roadmap.md) tracks the rebuild sequence.
- [docs/agent-handoff.md](docs/agent-handoff.md) summarizes the current repo state for future agents.
- [docs/archive/legacy-devflow-software-factory-2026-05-27/README.md](docs/archive/legacy-devflow-software-factory-2026-05-27/README.md) explains what was archived and why.

## Product Promise

Run multiple AI coding workers in parallel without them overwriting each other, losing context, hanging silently, or burning frontier-model credits unnecessarily.

## First Milestone

Build the non-AI control room with shell workers only.

Required commands:

```bash
devflow init
devflow doctor
devflow task create "title"
devflow task list
devflow task show <task_id>
devflow task run <task_id> --worker shell -- <command>
devflow task verify <task_id> -- <command>
devflow dashboard
```

The milestone is accepted when three shell tasks are visible through the CLI and dashboard:

1. one succeeds
2. one fails
3. one times out

Current implementation status: the shell-worker control-room slice is implemented, including SQLite task state, task-local artifacts, dashboard rendering, git worktree creation for task workspaces when the repo has a valid `HEAD`, verification logs, and merge-readiness status.

## Not In The First Milestone

- Aider
- Hermes
- OpenCode
- memory
- complex scheduling
- model routing
- old task-packet workflow orchestration
- old unified-diff software-factory rituals

## Current Repo Note

Much of the existing implementation belongs to the previous direction. Treat it as salvage material, not authority. Useful pieces may be extracted, especially worktree isolation and simple shell/verification helpers, but the new MVP should be a small, observable control room around shell workers.
