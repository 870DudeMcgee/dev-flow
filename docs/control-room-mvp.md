# Dev-Flow Control-Room MVP

Date: 2026-05-27
Status: Active source of truth

## Product Compass

The long-term product North Star lives at [PRODUCT_NORTH_STAR.md](../PRODUCT_NORTH_STAR.md). Read it before implementation decisions and check proposed changes against its Periodic Self-Check section.

This document is the near-term MVP authority: it narrows the North Star into the first production-worthy control-room slice. The current frozen command, filesystem, and safety contract lives at [docs/mvp-contract.md](mvp-contract.md).

## Product Direction

Dev-Flow is being rebuilt as a local-first control room for parallel AI coding workers.

The product is not a coding agent, model provider, memory framework, IDE workflow, or software-factory ritual. Dev-Flow owns the boring but sacred control-plane pieces around replaceable workers:

- task state
- isolated workspaces
- locks and ownership
- worker process lifecycle
- status and logs
- result bundles
- verification evidence
- merge readiness

Workers can be shell commands today and Aider, Hermes, OpenCode, Codex, Claude Code, local models, or future tools later. The first milestone intentionally implements shell workers only.

## Non-Negotiable Principles

1. Agents are replaceable. State is sacred.
2. One task gets one isolated workspace and one owner.
3. Visibility is required through plain filesystem artifacts and CLI output before broader UI surfaces.
4. Context is durable artifacts, not hidden magic memory.
5. Autonomy is earned by reliable status, logs, recovery, and reviewable results.

## Frozen Shell-Worker MVP Contract

The current stable MVP is the shell-worker path only.

Stable commands:

```bash
devflow --help
devflow task --help
devflow task create "example task"
devflow task run <task_id> --shell "echo hello > result.txt"
devflow task verify <task_id> --shell "test -f result.txt"
devflow task list
devflow task show <task_id>
```

Existing helper commands may remain during the rebuild, but docs and focused MVP tests should treat only the list above as frozen.

Do not implement these in the first milestone:

- Aider
- Hermes
- OpenCode
- memory
- complex scheduling
- local model routing
- old task-packet workflow orchestration
- PR automation
- dashboard UI
- token-context routing helpers

## Runtime Structure

```text
.devflow/
  tasks/<task_id>/
    task.yaml
    events.jsonl
    verification.json
    logs/
      worker.log
      verify.log
  workspaces/<task_id>/
```

The filesystem is the source of truth. `task.yaml` is canonical current state. `events.jsonl` is append-only evidence. `verification.json` stores the latest verification result. Worker and verification logs are raw evidence. Worker and verification commands run only inside `.devflow/workspaces/<task_id>/`.

The frozen MVP does not create a SQLite database or `.devflow/worktrees/` directory. Shell-worker results stay in the task workspace unless a future explicit copy/promote feature is added.

## Files To Keep Or Salvage Later

These are useful ingredients, but they must be adapted to the new product shape instead of treated as process authority:

- `src/devflow/cli.py`: current CLI entry point; likely replace argparse with Typer or simplify heavily.
- `src/devflow/runner.py`: salvage small shell execution and verification helpers only; bypass unified-diff runner behavior for the MVP.
- `src/devflow/failures.py`: possible source for simple failure labels later.
- `tests/`: salvage patterns, but expect the first MVP tests to be new shell-worker/control-room tests.
- `pyproject.toml`: keep packaging entry point, but update dependencies when implementation begins.

## Files And Surfaces To Bypass

These belong to the old product direction and should not guide implementation:

- `.devflow/workflow/**`
- `.devflow/skills/devflow-software-factory/**`
- old `.github/instructions/devflow.instructions.md`
- old `.github/skills/devflow/references/**`
- `src/devflow/agents/**`
- `src/devflow/memory.py`
- `src/devflow/worktrees.py`
- `src/devflow/worktree_commands.py`
- `src/devflow/context.py`
- `src/devflow/dag.py`
- `src/devflow/evals.py`
- `src/devflow/traces.py`
- old task-file unified-diff runner
- old task claim/release/transition/status protocol

Bypass does not necessarily mean delete immediately. It means do not treat these files as source of truth for the rebuild.

## Files To Create For The MVP

Expected implementation files:

- `src/devflow/core/paths.py`
- `src/devflow/models/task.py`
- `src/devflow/models/worker.py`
- `src/devflow/services/task_service.py`
- `src/devflow/services/doctor_service.py`
- `src/devflow/services/workspace_service.py`
- `src/devflow/services/worker_service.py`
- `src/devflow/adapters/base.py`
- `src/devflow/adapters/shell.py`
- `tests/test_control_room_shell.py`

Existing files may be simplified instead of duplicated when that keeps the diff smaller.

## Smallest First Implementation Patch

The first code patch should prove a single vertical slice:

1. `devflow --help` and `devflow task --help` expose the CLI entry points.
2. `devflow task create "example task"` creates the stable task artifacts and isolated workspace directory.
3. `devflow task run <task_id> --shell "echo hello > result.txt"` runs in the task workspace, captures `logs/worker.log`, and marks the task complete.
4. `devflow task verify <task_id> --shell "test -f result.txt"` runs in the same task workspace, captures `logs/verify.log`, writes `verification.json`, and marks the task verified.
5. `devflow task list` and `devflow task show <task_id>` expose the current state from task files.

Only after that slice stays stable should new runtime behavior be promoted into the contract.

## Acceptance Gauntlet

Create one shell task, run `echo hello > result.txt`, verify `test -f result.txt`, list it, and show it. The command result must exist only under `.devflow/workspaces/<task_id>/`. No worker may mutate the main checkout directly. No AI worker adapters, dashboard UI, database, or worktree orchestration are part of this acceptance test.

## Current Implementation Status

Implemented:

- shell-worker control-room CLI
- filesystem task state with canonical `task.yaml`
- per-task artifact directories
- append-only task and system `events.jsonl`
- success, failure, and timeout statuses
- log/result/report artifact writing
- verification command execution inside the task workspace
- verification log writing
- `verification.json` latest-result evidence
- copied scratchpad workspaces under `.devflow/workspaces/<task_id>/`
- tampered workspace refusal before shell or verification commands execute
- symlink skipping during scratchpad copy

Outside the frozen MVP contract:

- dashboard UI
- token-context helper (Completed helper; acts purely as a visible planning helper that recommends context strategy. It does not execute token tools, route models, install hooks, or change shell-worker, merge, or verification behavior.)
- AI worker adapters
- SQLite or other databases
- `.devflow/worktrees/` orchestration

> [!IMPORTANT]
> **Next Priority**: Return all future effort back to the core control-room MVP: shell-worker task lifecycle, workspace isolation, status visibility, verification, and future merge readiness.
