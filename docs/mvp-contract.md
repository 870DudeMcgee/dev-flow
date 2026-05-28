# Shell-Worker MVP Contract

Status: frozen on 2026-05-28.

This is the smallest stable contract for the current Dev-Flow MVP. It freezes the shell-worker control-room behavior that docs and tests should agree on. Runtime surfaces outside this document may exist as helper or experimental code, but they are not part of the frozen MVP contract.

## Stable Commands

```bash
devflow --help
devflow task --help
devflow task create "example task"
devflow task run <task-id> --shell "echo hello > result.txt"
devflow task verify <task-id> --shell "test -f result.txt"
devflow task list
devflow task show <task-id>
```

`devflow task create` creates the task artifacts and task workspace needed by the later commands. Shell worker commands and verification commands run from the task workspace.

## Stable Filesystem Artifacts

For a created task, the MVP contract is:

```text
.devflow/tasks/<task-id>/task.yaml
.devflow/tasks/<task-id>/events.jsonl
.devflow/tasks/<task-id>/verification.json
.devflow/tasks/<task-id>/logs/worker.log
.devflow/tasks/<task-id>/logs/verify.log
.devflow/workspaces/<task-id>/
```

`task.yaml` is the canonical current task state. `events.jsonl` is append-only evidence. `verification.json` stores the latest verification result. Logs are raw command evidence. The workspace is the only current place where shell-worker results are written.

## Stable Safety Rules

- Shell workers execute only in `.devflow/workspaces/<task-id>/`.
- Verification commands execute only in `.devflow/workspaces/<task-id>/`.
- Tampered task workspace paths are refused before command execution.
- Symlinks are skipped during scratchpad copy.
- Shell-worker results do not write into the main checkout unless a future explicit copy/promote feature is added.
- No SQLite database is created.
- No `.devflow/worktrees/` directory is created.
- Legacy agent, memory, DAG, trace, worktree, database, and software-factory systems remain bypassed for this MVP path.

## Out Of The Frozen Contract

- Browser or terminal dashboards.
- Token-context helper (purely a completed visible planning helper that recommends context strategy; does not execute token tools, route models, install hooks, or change shell-worker/verification/merge behavior).
- AI worker adapters.
- Git worktree orchestration.
- SQLite or any other database.
- Automatic merge, copy-back, or PR automation.
- Legacy task-packet and unified-diff workflow rituals.

> [!IMPORTANT]
> **Next Priority**: Future work must focus on the core control-room MVP: shell-worker task lifecycle, workspace isolation, status visibility, verification, and merge readiness.