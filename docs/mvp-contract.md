# Current Control-Room Product Contract

Status: active, reconciled on 2026-05-30.

This is the stable contract for the current Dev-Flow control-room milestone. It freezes the shell-worker, visibility, verification, and human-controlled promotion behavior that docs and tests should agree on. Runtime surfaces outside this document may exist as helper or experimental code, but they are not part of this current product contract.

Post-MVP worker adapter boundaries are described in [docs/adapter-contract.md](adapter-contract.md). The next registry/provider/role architecture is described in [docs/architecture/agent-registry-and-adapter-runtime.md](architecture/agent-registry-and-adapter-runtime.md). These design documents do not change this current product contract.

## Stable Commands

```bash
devflow --help
devflow init
devflow doctor
devflow dashboard
devflow task --help
devflow task create "example task"
devflow task run <task-id> --worker shell -- /bin/sh -c "echo hello > result.txt"
devflow task run <task-id> --shell "echo hello > result.txt"
devflow task verify <task-id> --shell "test -f result.txt"
devflow task list
devflow task show <task-id>
devflow task packet <task-id>
devflow task log <task-id>
devflow task promote-preview <task-id>
devflow task promote <task-id>
```

`devflow init` creates or repairs the local control-room seed structure. `devflow doctor` checks that structure. `devflow dashboard` renders the current text-only terminal dashboard from task artifacts.

`devflow task create` creates the task artifacts and task workspace needed by the later commands. Shell worker commands and verification commands run from the task workspace. The preferred shell-worker invocation is `devflow task run <task-id> --worker shell -- <command>`; `--shell "<command>"` remains supported.

`devflow task promote-preview` and `devflow task promote` are explicit, human-controlled promotion surfaces. Promotion is not automatic and does not stage, commit, push, open a pull request, or bypass verification readiness checks.

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

## Optional Derived State

`.devflow/tasks/<task-id>/summary.json` may exist as a derived cache for visibility and token efficiency. It is not canonical state. It may be deleted and regenerated without losing information. If it is missing, stale, malformed, or disagrees with `task.yaml`, `events.jsonl`, `verification.json`, or logs, the canonical files win.

`.devflow/tasks/<task-id>/packet.json` may exist as a generated TaskPacket dump. It is derived state and is written immediately before a worker execution when needed. Dynamic TaskPacket projections are also derived state.

`.devflow/tasks/<task-id>/result.md` may exist as a human-readable result summary. It is not canonical state.

## Stable Safety Rules

- Shell workers execute only in `.devflow/workspaces/<task-id>/`.
- Verification commands execute only in `.devflow/workspaces/<task-id>/`.
- Tampered task workspace paths are refused before command execution.
- Symlinks are skipped during scratchpad copy.
- Shell-worker results do not write into the main checkout.
- Promotion to the main checkout is explicit, human-confirmed, and gated on verification readiness.
- Promotion refuses unsafe workspace paths and blocks dirty main-checkout changes unless explicitly forced.
- No SQLite database is created.
- No `.devflow/worktrees/` directory is created.
- Legacy agent, memory, DAG, trace, worktree, database, and software-factory systems remain bypassed for this MVP path.

## Out Of The Current Contract

- Browser or web dashboards.
- Token-context helper as runtime authority. The helper may exist as visible planning guidance, but it does not execute token tools, route models, install hooks, or change shell-worker, verification, or promotion behavior.
- Enabled non-shell worker adapters. Registry and adapter-runtime documents may exist as planning artifacts, but no provider-backed adapter is active in this contract.
- Git worktree orchestration.
- SQLite or any other database.
- Automatic merge, automatic copy-back, commit, push, or PR automation.
- Legacy task-packet and unified-diff workflow rituals.

> [!IMPORTANT]
> **Next Priority**: Keep the shell-worker control-room loop stable while adding the next layer only in order: registry loading, agent list/show/packet commands, manual adapter, shell alignment, local adapter, then provider adapters and routing.
