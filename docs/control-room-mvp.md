# Dev-Flow Control-Room MVP

Date: 2026-05-27
Status: Active source of truth

## Product Compass

The long-term product North Star lives at [PRODUCT_NORTH_STAR.md](../PRODUCT_NORTH_STAR.md). Read it before implementation decisions and check proposed changes against its Periodic Self-Check section.

This document is the near-term MVP authority: it narrows the North Star into the first production-worthy control-room slice. The current command, filesystem, and safety contract lives at [docs/mvp-contract.md](mvp-contract.md).

For details on the project's design and boundaries:
- [docs/devflow-operating-model.md](devflow-operating-model.md) defines the role split between human, main chat/control-room agent, Dev-Flow kernel, worker agents, and DevMode.
- [docs/read-only-control-room-agent.md](read-only-control-room-agent.md) defines the main chat agent as read-only planner/spec/reviewer/coordinator.
- [docs/devmode-devflow-boundary.md](devmode-devflow-boundary.md) defines the boundary between DevMode discipline and Dev-Flow orchestration.


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

## Current Shell-Worker Control-Room Contract

The current stable milestone is the shell-worker control-room path. It includes task lifecycle commands, init/doctor structure checks, text-only terminal dashboard visibility, verification evidence, TaskPacket projection, logs, and human-controlled promotion from isolated workspaces.

Stable commands:

```bash
devflow --help
devflow init
devflow doctor
devflow dashboard
devflow task --help
devflow task create "example task"
devflow task run <task_id> --worker shell -- /bin/sh -c "echo hello > result.txt"
devflow task run <task_id> --shell "echo hello > result.txt"
devflow task verify <task_id> --shell "test -f result.txt"
devflow task list
devflow task show <task_id>
devflow task packet <task_id>
devflow task log <task_id>
devflow task promote-preview <task_id>
devflow task promote <task_id>
```

The preferred shell-worker form is `devflow task run <task_id> --worker shell -- <command>`. The `--shell "<command>"` form remains supported.

Do not implement these in the first milestone:

- Aider
- Hermes
- OpenCode
- memory
- complex scheduling
- local model routing
- old task-packet workflow orchestration
- PR automation
- browser or web dashboard UI
- token-context routing helpers
- automatic commit, push, merge, or pull request creation

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

The current control-room contract does not create a SQLite database or `.devflow/worktrees/` directory. Shell-worker results stay in the task workspace until a human explicitly previews and promotes verified changes.

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
5. `devflow task list`, `devflow task show <task_id>`, and `devflow dashboard` expose the current state from task files.
6. `devflow task promote-preview <task_id>` shows the isolated workspace changes that would be promoted.
7. `devflow task promote <task_id>` copies verified, human-approved changes back to the main checkout without staging, committing, pushing, or opening a pull request.

Only after that slice stays stable should new runtime behavior be promoted into the contract.

## Acceptance Gauntlet

Create one shell task, run `echo hello > result.txt`, verify `test -f result.txt`, list it, show it, inspect the dashboard, preview promotion, and promote only after explicit human approval. Before promotion, the command result must exist only under `.devflow/workspaces/<task_id>/`. No worker may mutate the main checkout directly. No AI worker adapters, browser/web dashboard UI, database, or worktree orchestration are part of this acceptance test.

## Current Implementation Status

Implemented:

- shell-worker control-room CLI
- init and doctor commands for the local control-room seed structure
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
- text-only terminal dashboard
- promotion preview from isolated workspace changes
- human-controlled promotion of verified changes to the main checkout

Outside the current product contract:

- browser or web dashboard UI
- token-context helper (Completed helper; acts purely as a visible planning helper that recommends context strategy. It does not execute token tools, route models, install hooks, or change shell-worker, merge, or verification behavior.)
- AI worker adapters
- SQLite or other databases
- `.devflow/worktrees/` orchestration

> [!IMPORTANT]
> **Next Priority**: Return all future effort back to the core control-room MVP: shell-worker task lifecycle, workspace isolation, status visibility, verification, and future merge readiness.


## Milestone 1 Checkpoint: Shell-Worker Control Room Completed

The first production-ready milestone of the Dev-Flow control plane is officially complete and checkpointed.

* **Checkpoint Commit**: `0dffab6 feat: add task log command`
* **Test Status**: 184 tests passing cleanly (6 skipped)

### Compact Checklist of Accepted Capabilities

- [x] **Task Creation**: `devflow task create` scaffolds task folders under `.devflow/tasks/` and handles dirty-git state copying safely.
- [x] **Isolated Workspaces**: Commands run strictly inside isolated workspaces under `.devflow/workspaces/<task_id>/` without mutating the main checkout.
- [x] **Shell Task Execution**: `devflow task run <task_id> --worker shell -- <command>` executes and captures command outcomes.
- [x] **Worker Command Persistence**: Stores exact run command strings (`worker_command`) shell-safely.
- [x] **Exit-Code & Timeout Propagation**: Propagates subprocess outcomes and respects customizable task execution timeouts.
- [x] **Verification Command Persistence**: Captures and persists the shell command string used for task verification.
- [x] **Verification Exit-Code Propagation**: Tracks and persists verification outcomes (`passed` / `failed`) and exit codes.
- [x] **Lifecycle Visibility**:
  - `devflow task list` provides status, updates, and compact verification states.
  - `devflow task show <task_id>` exposes comprehensive lifecycle details, events, readiness, and next-action hints.
- [x] **TaskPacket Projections**: `devflow task packet <task_id>` generates a deterministic JSON task context packet with virtualized paths (e.g. `<workspace>`, `<task>`) and secret redaction.
- [x] **Read-Only Log Viewing**: `devflow task log <task_id> [--verify] [--tail N]` prints raw worker or verification logs directly to stdout without mutating task state.

---

### Data Surface Architecture

To ensure strict engineering discipline, the data surface is stratified as follows:

#### 1. Canonical State (Source of Truth)
- `task.yaml`: Canonical current state and metadata.
- `events.jsonl`: Append-only, timeline-exact sequence of events.
- `questions.jsonl`: Formatted user-worker questions (when present).
- `verification.json`: Authoritative verification summary output.
- `logs/worker.log` & `logs/verify.log`: Raw terminal outputs representing absolute evidence of execution.

#### 2. Derived State (Non-Canonical/Cache-Only)
- `result.md`: Human-readable summary formatted by the worker or verification commands.
- `summary.json`: Local cache of parsed data derived entirely from canonical state.
- `packet.json`: Generated TaskPacket dump written instantly before worker executions.
- *TaskPacket projections*: Any dynamic context structure derived from canonical properties.

---

### Non-MVP Boundaries (Strictly Excluded)

The following areas are out-of-scope for the completed MVP and deferred:
* **Replaceable AI Adapters**: No Codex, Aider, or Hermes adapters.
* **Model Routing**: No dynamic LLM gateway routing or scheduling.
* **Dashboard / Web Server**: No database-driven dashboard (text-only terminal dashboard remains static).
* **Databases**: Relies strictly on plain filesystem architecture; no SQL/NoSQL databases.
* **Automated Merging**: No automatic pull request creation or branch merging.

### Dogfooding Requirement

Future implementation slices should use Dev-Flow shell tasks or local worker commands where practical. This is required dogfooding for task isolation, logs, verification evidence, dashboard visibility, promotion previews, and handoff quality. It must not be used as justification to add AI adapters, local model routing, autonomous scheduling, or old workflow machinery before the shell-worker control room remains stable.

---

### Next Phase Outlook

Future adapter development or advanced scheduling may only begin using this stable checkpoint as a solid boundary. The next phase must strictly preserve:
1. **Local-First State**: Rely on plain-file source of truth before any database storage.
2. **Workspace Isolation**: Ensure replaceable workers operate strictly within copied sandboxes.
3. **Verification Ownership**: Control-plane holds authoritative ownership of verification execution.
4. **Human-Controlled Promotion**: Keep humans at the helm of promotion and merge-readiness approvals.
