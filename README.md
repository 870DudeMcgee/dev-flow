# devflow

Dev-Flow is being rebuilt as a local-first control room for parallel AI coding workers.

The current product direction is intentionally smaller than the previous software-factory design. Dev-Flow should coordinate replaceable workers, not become the worker itself.

## Active Source Of Truth

- [PRODUCT_NORTH_STAR.md](PRODUCT_NORTH_STAR.md) defines the product identity, end-state, and drift checks for implementation decisions.
- [docs/mvp-contract.md](docs/mvp-contract.md) freezes the current shell-worker MVP command, filesystem, and safety contract.
- [docs/control-room-mvp.md](docs/control-room-mvp.md) defines the new product direction, MVP scope, files to keep or bypass, runtime structure, and first implementation slice.
- [docs/roadmap.md](docs/roadmap.md) tracks the rebuild sequence.
- [docs/agent-handoff.md](docs/agent-handoff.md) summarizes the current repo state for future agents.
- [docs/archive/legacy-devflow-software-factory-2026-05-27/README.md](docs/archive/legacy-devflow-software-factory-2026-05-27/README.md) explains what was archived and why.

## Product Promise

Run multiple AI coding workers in parallel without them overwriting each other, losing context, hanging silently, or burning frontier-model credits unnecessarily.

## Local Development Install

Install the package into the repo virtual environment before using the documented `devflow` command:

```bash
.venv/bin/python -m pip install -e .
```

Then verify the console script:

```bash
.venv/bin/devflow --help
.venv/bin/devflow task --help
```

## Frozen Shell-Worker MVP

The current stable contract is intentionally smaller than the earlier first-milestone plan. It covers shell-worker task creation, execution, verification, listing, and inspection. See [docs/mvp-contract.md](docs/mvp-contract.md) for the full frozen contract.

Stable commands:

```bash
devflow --help
devflow task --help
devflow task create "example task"
devflow task run <task_id> --shell "echo hello > result.txt"
devflow task verify <task_id> --shell "test -f result.txt"
devflow task list
devflow task show <task_id>
devflow task packet <task_id>
```

Current implementation status: the shell-worker control-room slice uses filesystem task state, canonical `task.yaml`, append-only `events.jsonl`, task-local worker and verification logs, latest verification evidence, and copied scratchpad workspaces under `.devflow/workspaces/<task_id>/`. Shell-worker writes stay in the task workspace; no SQLite database or `.devflow/worktrees/` directory is part of the MVP contract.

Task packet note: `src/devflow/control_room/task_packet.py` contains a small read-only `TaskPacket` builder for future adapters. You can preview the built TaskPacket as deterministic JSON using the read-only `devflow task packet <task_id>` command, which projects canonical task artifacts into bounded context, tail-limits logs, discloses omissions, and applies robust secret redaction and path virtualization to reduce accidental local path or credential exposure. It is not wired into Codex or any worker adapter.

## Out Of The Frozen Contract

The runtime may still contain helper or experimental surfaces from in-progress work, but the frozen MVP docs and focused tests should not depend on them. Dashboard, token-context (completed purely as a visible planning helper that recommends context strategy without executing token tools, routing models, installing hooks, or changing core behavior), `devflow init`, `devflow doctor`, AI worker adapters, git worktree orchestration, database-backed state, copy-back, merge, and PR automation are outside this freeze unless a future contract explicitly promotes them.

> [!IMPORTANT]
> **Next Priority**: Future effort is redirected entirely back to the core control-room MVP: shell-worker task lifecycle, workspace isolation, status visibility, verification, and merge readiness.

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

Much of the existing implementation belongs to the previous direction. Treat it as salvage material, not authority. Useful pieces may be extracted only when they support the file-based shell-worker MVP.
