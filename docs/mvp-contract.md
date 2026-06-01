# Current Control-Room Product Contract

Status: active, reconciled on 2026-05-30.

This is the stable contract for the current Dev-Flow control-room milestone. It freezes the shell-worker, manual proof-agent, visibility, verification, and human-controlled promotion behavior that docs and tests should agree on. Implemented but experimental transition layers are allowed only as read-only/manual planning aids until promoted.

Post-MVP worker adapter boundaries are described in [docs/adapter-contract.md](adapter-contract.md). The next registry/provider/role architecture is described in [docs/architecture/agent-registry-and-adapter-runtime.md](architecture/agent-registry-and-adapter-runtime.md), with future task-fit/context routing design in [docs/architecture/agent-selection-and-context-routing.md](architecture/agent-selection-and-context-routing.md). These design documents do not change this current product contract.

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
devflow agent show devflow-manual-codex-worker
devflow agent packet <task-id> devflow-manual-codex-worker
devflow task run <task-id> --worker devflow-manual-codex-worker
```

## Implemented But Experimental Transition Commands
The following CLI commands represent the transition layer. They are fully implemented but are classified as experimental and restricted to read-only/manual planning/auditing aids, except for the stable proof-agent forms listed above:

```bash
devflow agent list
devflow agent show <non-proof-agent-id>
devflow agent packet <task-id> <non-proof-agent-id>
devflow task fit <task-id>
devflow task pack <task-id> <role>
devflow task scout <task-id> <role>
devflow task route <task-id>
devflow task scorecard <task-id>
```

### Command Maturity Classifications

To guarantee execution safety and prevent automated agents from operating on unstable transition layers, all CLI commands are classified under a strict maturity hierarchy:

- **Stable**: Authorized local control-room commands (e.g., `init`, `doctor`, `dashboard`, `task create`, `task list`, `task show`, `task run`, `task verify`, `task packet`, `task log`, `task promote-preview`, `task promote`, `agent show devflow-manual-codex-worker`, `agent packet <task-id> devflow-manual-codex-worker`).
- **Experimental-ReadOnly**: Read-only diagnostic and context-assembly aids (e.g., `context`, `task fit`, `task pack`, `task scout`, `task route`, `task scorecard`, non-proof-agent registry inspection).
- **Experimental-Manual**: Manual coordination and polling harnesses (e.g., `supervise`).
- **Forbidden-Runtime**: Any command or background process that bypasses human review, routes models automatically, or mutates the main checkout autonomously. No such commands are allowed in the control room.

Agent adapters also carry runtime maturity: `stable_runtime`, `experimental_readonly`, or `planned_not_executable`. Only `shell` and `manual` are `stable_runtime` executable adapters in this milestone. Planned provider adapters may appear in registries or docs, but task execution must fail clearly if they are invoked.

Experimental task-fit, scout, route, scorecard, context, and supervisor commands are hidden from `--help` by default and refuse execution unless the environment variable `DEVFLOW_EXPERIMENTAL=1` is explicitly set. The proof-agent registry commands are visible because they are part of this stable milestone.

`devflow init` creates or repairs the local control-room seed structure. `devflow doctor` checks that structure. `devflow dashboard` renders the current text-only terminal dashboard from task artifacts.

`devflow task create` creates the task artifacts and task workspace needed by the later commands. Shell worker commands and verification commands run from the task workspace. The preferred shell-worker invocation is `devflow task run <task-id> --worker shell -- <command>`; `--shell "<command>"` remains supported.

`devflow task promote-preview` and `devflow task promote` are explicit, human-controlled promotion surfaces. Promotion preview reports the task baseline commit, the current main checkout HEAD, and whether the baseline is unchanged, changed, or unavailable. Promotion is not automatic and does not stage, commit, push, open a pull request, bypass verification readiness checks, or promote work from a stale task baseline unless the human explicitly passes `--force-stale-baseline` after reviewing the risk.

`devflow agent show devflow-manual-codex-worker` displays the stable proof-agent contract:

- Agent ID: `devflow-manual-codex-worker`
- Role: `implementation_worker`
- Adapter: `manual`
- Execution mode: `human_launched_agent`
- Purpose: consume a bounded task packet, edit only the assigned isolated workspace, produce structured result, question, or failure evidence, then stop.

`devflow agent packet <task-id> devflow-manual-codex-worker` prints a bounded packet with role, allowed reads, allowed writes, forbidden writes, required outputs, completion rules, and Codex-ready manual instructions.

`devflow task run <task-id> --worker devflow-manual-codex-worker` creates `.devflow/tasks/<task-id>/agents/devflow-manual-codex-worker/handoff.md` and packet evidence for a human-launched Codex or IDE agent, then leaves the task blocked with `manual_agent_state: awaiting_human`. It does not call a provider API, choose a model, schedule another agent, verify work, promote work, or mutate the main checkout. Pressing Enter in an interactive terminal is not completion evidence.

## Stable Filesystem Artifacts

For a created task, the MVP contract is:

```text
.devflow/tasks/<task-id>/task.yaml
.devflow/tasks/<task-id>/.lock/owner.json   # live only during task-local mutations
.devflow/tasks/<task-id>/events.jsonl
.devflow/tasks/<task-id>/verification.json
.devflow/tasks/<task-id>/logs/worker.log
.devflow/tasks/<task-id>/logs/verify.log
.devflow/tasks/<task-id>/agents/devflow-manual-codex-worker/handoff.md
.devflow/tasks/<task-id>/agents/devflow-manual-codex-worker/result.md
.devflow/tasks/<task-id>/agents/devflow-manual-codex-worker/questions.jsonl
.devflow/tasks/<task-id>/agents/devflow-manual-codex-worker/worker_failed.json
.devflow/workspaces/<task-id>/
```

`task.yaml` is the canonical current task state. `events.jsonl` is append-only evidence. `verification.json` stores the latest verification result. Logs are raw command evidence. The workspace is the only current place where shell-worker results are written. Versioned state artifacts include `schema_version: 1`; unversioned historical task files are treated as version 1, and unknown task schema versions are refused.

Mutating task operations use a task-local `.lock/` directory with `owner.json` metadata. `run`, `verify`, `apply-patch`, and `promote` refuse concurrent mutations for the same task, report the current lock owner, and recover locks that are stale beyond the lock TTL.

## Optional Derived State

`.devflow/tasks/<task-id>/summary.json` may exist as a derived cache for visibility and token efficiency. It is not canonical state. It may be deleted and regenerated without losing information. If it is missing, stale, malformed, or disagrees with `task.yaml`, `events.jsonl`, `verification.json`, or logs, the canonical files win.

`.devflow/tasks/<task-id>/packet.json` may exist as a generated TaskPacket dump. It is derived state and is written immediately before a worker execution when needed. Dynamic TaskPacket projections are also derived state.

`.devflow/tasks/<task-id>/result.md` may exist as a human-readable result summary. It is not canonical state.

Manual proof-agent evidence under `.devflow/tasks/<task-id>/agents/devflow-manual-codex-worker/` is worker-produced evidence, not canonical task state. Dev-Flow may display `awaiting_human`, `blocked`, `failed`, and `result_present` in `task show` and `dashboard`, but only Dev-Flow updates `task.yaml`, `events.jsonl`, `verification.json`, merge-readiness, and promotion state.

## Stable Safety Rules

- Shell workers execute only in `.devflow/workspaces/<task-id>/`.
- Verification commands execute only in `.devflow/workspaces/<task-id>/`.
- Tampered task workspace paths are refused before command execution.
- Symlinks are skipped during scratchpad copy.
- Shell-worker results do not write into the main checkout.
- Promotion to the main checkout is explicit, human-confirmed, and gated on verification readiness.
- Promotion refuses unsafe workspace paths and blocks dirty main-checkout changes unless explicitly forced.
- New task events are hash-chained with monotonic indexes, previous-event hashes, and current-event hashes; `doctor` reports malformed or edited task event logs.
- No SQLite database is created.
- No `.devflow/worktrees/` directory is created.
- Legacy agent, memory, DAG, trace, worktree, database, and software-factory systems remain bypassed for this MVP path.
- Manual proof-agent workers may write only to the assigned isolated workspace and their agent evidence directory.
- Manual proof-agent completion does not imply verification or promotion readiness.

## Sandbox & Security Boundaries

Destructive command filtering is intentionally shallow (detecting obvious fragments like `rm -rf /`, `mkfs`, `dd if=`). The Dev-Flow shell worker operates with trusted local credentials in the task workspace; it is path-isolated, not sandboxed.

The current safety model is trusted local single-user execution:

- shell and verification commands run as subprocesses in `.devflow/workspaces/<task-id>/`
- worker environment variables are filtered to an allowlist plus explicit task environment
- POSIX subprocesses are started in their own session so timeout and log-limit cleanup can terminate child processes in the same process group
- canonical task artifacts are written with same-directory temporary files followed by atomic replacement

This does not stop a command from using the local user's filesystem permissions, network access, CPU, memory, or other OS capabilities before Dev-Flow terminates it. It is not suitable for untrusted worker code, hostile repositories, shared multi-user hosts, or tenant isolation.

Current MVP implementation limits:

- workspaces are copy-based scratchpads, not git worktrees
- promotion copies verified workspace changes into the main checkout instead of performing a git-native three-way merge
- patch application supports validated text patches only and rejects binary diffs, renames, copies, mode changes, and similarity metadata
- event logs are append-only evidence, but task and system event writes are still separate writes and may require future reconciliation tooling after a crash

Future security hardening items:
- Per-task temporary `HOME` and temp directories.
- Network-off runner policies.
- Resource limits for CPU, memory, file descriptors, and process counts.
- Allowlisted command profiles and absolute path inspections.
- Container, firejail, macOS sandbox, or other OS-level isolation.
- Git worktree or branch-backed workspaces.
- Git-native promotion and conflict handling.
- Event-log reconciliation and repair checks.

## Out Of The Current Contract

- Browser or web dashboards.
- Token-context helper as runtime authority. The helper may exist as visible planning guidance, but it does not execute token tools, route models, install hooks, or change shell-worker, verification, or promotion behavior.
- Task-fit/context routing runtime.
- Provider-backed worker adapters. The only stable non-shell worker path is the manual proof-agent handoff; it does not execute model APIs or own canonical task state.
- Git worktree orchestration.
- SQLite or any other database.
- Automatic merge, automatic copy-back, commit, push, or PR automation.
- Legacy task-packet and unified-diff workflow rituals.

> [!IMPORTANT]
> **Next Priority**: Keep the shell-worker control-room loop stable while adding the next layer only in order: registry loading, agent list/show/packet commands, manual adapter, shell alignment, deterministic task-fit/context estimation, context pack building, local adapter, provider adapters, then routing.
