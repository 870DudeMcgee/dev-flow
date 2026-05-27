# Roadmap

## Strategic Direction

Dev-Flow is a local-first control room for parallel AI coding workers.

The rebuild starts from a smaller foundation than the previous software-factory design:

- workers are replaceable
- state is sacred
- each task gets an isolated workspace
- dashboard visibility is required early
- context and results are durable artifacts
- autonomy is earned through reliability

Active specification: [docs/control-room-mvp.md](control-room-mvp.md)

North Star: [PRODUCT_NORTH_STAR.md](../PRODUCT_NORTH_STAR.md)

Legacy archive: [docs/archive/legacy-devflow-software-factory-2026-05-27/README.md](archive/legacy-devflow-software-factory-2026-05-27/README.md)

## Phase 0: Documentation Reset

Goal: stop the old workflow docs from steering future implementation.

Done when:

- legacy workflow docs are archived
- README, roadmap, handoff, AGENTS, and Copilot instructions point at the new MVP
- old active instruction hooks are removed or rewritten
- files to keep, bypass, create, and first patch are documented

## Phase 1: Core State And CLI

Goal: initialize Dev-Flow, create tasks, and show status.

Commands:

```bash
devflow init
devflow doctor
devflow task create "title"
devflow task list
devflow task show <task_id>
```

Acceptance:

- `.devflow/devflow.db` exists
- `.devflow/config.yaml` exists
- task artifact directories are created
- CLI shows task state from SQLite and task files

## Phase 2: Shell Worker Loop

Goal: prove orchestration without AI.

Command:

```bash
devflow task run <task_id> --worker shell -- <command>
```

Acceptance:

- command runs in the assigned workspace
- worker log is captured
- result artifact is written
- success, failure, and timeout statuses are accurate

## Phase 3: Dashboard

Goal: make the control room visible.

Command:

```bash
devflow dashboard
```

Acceptance:

- browser shows tasks, status, worker, latest log line, result path, and timestamps
- page auto-refreshes
- no frontend build tooling is required

## Phase 4: Workspace Isolation

Goal: ensure one task gets one safe workspace.

Status: first slice implemented. Task creation now creates a real git worktree when the repo has a valid `HEAD`, with a directory fallback for non-git runtimes.

Acceptance:

- each task has an isolated worktree or workspace path
- main checkout is untouched by workers
- conflicting edits are detected later at review or merge readiness, not during worker execution

## Phase 5: MVP Acceptance Gauntlet

Create three shell tasks:

1. one succeeds
2. one fails
3. one times out

Pass when the CLI and dashboard show all three accurately with logs and no manual detective work.

## Phase 6: Verification And Merge Readiness

Goal: make Dev-Flow own verification evidence before work can be considered merge-ready.

Status: first slice implemented with:

```bash
devflow task verify <task_id> -- <command>
```

Acceptance:

- verification runs inside the task workspace
- `logs/verify.log` is written
- CLI and dashboard show verification status
- only completed tasks with passing verification are marked merge-ready

## Later, Not Now

- Aider adapter
- Hermes supervisor
- OpenCode adapter
- dependency scheduler
- question resume flow
- protected path gates
- model routing
- memory
- PR automation
