# Agent Handoff

Date: 2026-05-27

## Current Direction

Dev-Flow is being rebuilt as a local-first control room for parallel AI coding workers.

The previous Dev-Flow direction has been archived. It is no longer the process authority for this repository.

Active source of truth:

- [PRODUCT_NORTH_STAR.md](../PRODUCT_NORTH_STAR.md)
- [docs/mvp-contract.md](mvp-contract.md)
- [docs/control-room-mvp.md](control-room-mvp.md)
- [docs/roadmap.md](roadmap.md)
- [README.md](../README.md)

Archive index:

- [docs/archive/legacy-devflow-software-factory-2026-05-27/README.md](archive/legacy-devflow-software-factory-2026-05-27/README.md)

## Product Boundary

Dev-Flow is not the main coding brain. It coordinates replaceable workers and owns durable state, process isolation, status, logs, questions, result bundles, verification evidence, and merge readiness.

The frozen MVP is a non-AI shell-worker contract with task creation, shell execution, verification, listing, and inspection.

Normal local development install:

```bash
.venv/bin/python -m pip install -e .
```

That editable install exposes the console script declared in `pyproject.toml` as `devflow = "devflow.cli:main"`.

Stable MVP contract:

- `devflow --help`
- `devflow task --help`
- `devflow task create "title"`
- `devflow task list`
- `devflow task show <task_id>`
- `devflow task run <task_id> --shell "echo hello > result.txt"`
- `devflow task verify <task_id> --shell "test -f result.txt"`
- filesystem task state with canonical `task.yaml`
- task append-only `events.jsonl`
- task-local worker logs, verification logs, verification JSON, and YAML artifacts
- copied scratchpad workspaces under `.devflow/workspaces/<task_id>/`
- verification command execution inside task workspaces
- `verified` and `verification_failed` task statuses from verification
- no SQLite database or `.devflow/worktrees/` directory in the MVP path

## Required MVP Commands

```bash
devflow --help
devflow task --help
devflow task create "example task"
devflow task run <task_id> --shell "echo hello > result.txt"
devflow task verify <task_id> --shell "test -f result.txt"
devflow task show <task_id>
devflow task list
```

## Implementation Posture

- Read the North Star before implementation decisions and use its Periodic Self-Check to catch product drift.
- Prefer direct implementation over ceremonial workflow.
- Do not create legacy task files for this rebuild.
- Do not route implementation through old agent, memory, context-pack, DAG, trace, eval, or unified-diff runner surfaces.
- Treat dashboard, token-context, init/doctor helpers, worktree orchestration, databases, and AI worker adapters as outside the frozen MVP contract unless a future doc explicitly promotes them.
- Salvage useful code only when it supports the new control-room MVP.
- Keep unrelated dirty worktree changes intact.

## Useful Existing Code To Inspect Later

- `src/devflow/cli.py`: current CLI entry point, but likely too broad.
- `src/devflow/runner.py`: possible shell and verification helper salvage.
- `src/devflow/failures.py`: possible simple failure taxonomy salvage.

## Acceptance Check

Create one shell task, run `echo hello > result.txt`, verify `test -f result.txt`, list it, and show it. Confirm `result.txt` exists only in `.devflow/workspaces/<task_id>/`, the task artifacts exist, no SQLite database is created, and no `.devflow/worktrees/` directory is created.

Current verification covers the frozen command/filesystem/safety contract, copied workspace isolation, append-only events, verification logs, tampered workspace refusal, and symlink skipping in `tests/test_control_room_shell.py`.

## Known Worktree State At Handoff

Before this documentation reset, the repository already had unrelated dirty files in public-site, agent, manager, script, test, and `.devflow` artifact/task/report areas. Future agents must not revert those unless explicitly asked.
