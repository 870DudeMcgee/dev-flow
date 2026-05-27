# Dev-Flow Control-Room MVP

Date: 2026-05-27
Status: Active source of truth

## Product Compass

The long-term product North Star lives at [PRODUCT_NORTH_STAR.md](../PRODUCT_NORTH_STAR.md). Read it before implementation decisions and check proposed changes against its Periodic Self-Check section.

This document is the near-term MVP authority: it narrows the North Star into the first production-worthy control-room slice.

## Product Direction

Dev-Flow is being rebuilt as a local-first control room for parallel AI coding workers.

The product is not a coding agent, model provider, memory framework, IDE workflow, or software-factory ritual. Dev-Flow owns the boring but sacred control-plane pieces around replaceable workers:

- task state
- isolated workspaces
- locks and ownership
- worker process lifecycle
- status and logs
- questions
- result bundles
- verification evidence
- merge readiness

Workers can be shell commands today and Aider, Hermes, OpenCode, Codex, Claude Code, local models, or future tools later. The first milestone intentionally implements shell workers only.

## Non-Negotiable Principles

1. Agents are replaceable. State is sacred.
2. One task gets one isolated workspace and one owner.
3. Visibility is required early; the dashboard is part of the MVP.
4. Context is durable artifacts, not hidden magic memory.
5. Autonomy is earned by reliable status, logs, recovery, and reviewable results.

## First Milestone

Build the non-AI control room.

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

Do not implement these in the first milestone:

- Aider
- Hermes
- OpenCode
- memory
- complex scheduling
- old task-packet workflow orchestration
- local model routing
- PR automation

## Runtime Structure

```text
.devflow/
  devflow.db
  config.yaml
  tasks/<task_id>/
    task.yaml
    task.md
    context.md
    questions.md
    result.md
    report.md
    logs/
      worker.log
      verify.log
  worktrees/
```

SQLite is the queryable state index. Markdown, YAML, logs, and patches remain the human-readable artifact layer.

## Files To Keep Or Salvage Later

These are useful ingredients, but they must be adapted to the new product shape instead of treated as process authority:

- `src/devflow/cli.py`: current CLI entry point; likely replace argparse with Typer or simplify heavily.
- `src/devflow/worktrees.py` and `src/devflow/worktree_commands.py`: salvage worktree creation ideas for isolated task workspaces.
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
- `src/devflow/context.py`
- `src/devflow/dag.py`
- `src/devflow/evals.py`
- `src/devflow/traces.py`
- old task-file unified-diff runner
- old task claim/release/transition/status protocol

Bypass does not necessarily mean delete immediately. It means do not treat these files as source of truth for the rebuild.

## Files To Create For The MVP

Expected implementation files:

- `src/devflow/core/db.py`
- `src/devflow/core/paths.py`
- `src/devflow/models/task.py`
- `src/devflow/models/worker.py`
- `src/devflow/services/task_service.py`
- `src/devflow/services/doctor_service.py`
- `src/devflow/services/workspace_service.py`
- `src/devflow/services/worker_service.py`
- `src/devflow/adapters/base.py`
- `src/devflow/adapters/shell.py`
- `src/devflow/dashboard/app.py`
- `tests/test_control_room_shell.py`

Existing files may be simplified instead of duplicated when that keeps the diff smaller.

## Smallest First Implementation Patch

The first code patch should prove a single vertical slice:

1. `devflow init` creates `.devflow/devflow.db`, `.devflow/config.yaml`, `.devflow/tasks/`, and `.devflow/worktrees/`.
2. `devflow task create "Smoke success"` creates a SQLite task row, task artifact directory, and isolated workspace. In a git repo with `HEAD`, the workspace is a git worktree; otherwise it falls back to a plain directory.
3. `devflow task run <task_id> --worker shell -- python -c "print('ok')"` runs in the task workspace, captures `logs/worker.log`, writes `result.md`, and marks the task `complete`.
4. `devflow task show <task_id>` prints status, title, worker, latest log line, and artifact paths.
5. A focused pytest verifies that one success task completes.

Only after that slice works should failure, timeout, dashboard, and three-task acceptance coverage be added.

## Acceptance Gauntlet

Create three shell tasks:

1. one succeeds
2. one fails
3. one times out

The CLI and dashboard must show all three accurately, including status and log paths. No worker may mutate the main checkout directly. No AI worker adapters are part of this acceptance test.

## Current Implementation Status

Implemented:

- shell-worker control-room CLI
- SQLite task state
- per-task artifact directories
- success, failure, and timeout statuses
- log/result/report artifact writing
- verification command execution inside the task workspace
- verification log writing
- merge-readiness status when a completed task passes verification
- simple auto-refreshing dashboard
- git worktree workspace creation when the repo has a valid `HEAD`
- directory workspace fallback for non-git runtimes
