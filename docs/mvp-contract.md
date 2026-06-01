# Current Control-Room Product Contract

Status: active, reconciled on 2026-05-30.

This is the stable contract for the current Dev-Flow control-room milestone. It freezes the shell-worker, manual proof-agent, local Ollama evidence wrapper, visibility, verification, and human-controlled promotion behavior that docs and tests should agree on. Implemented but experimental transition layers are allowed only as read-only/manual planning aids until promoted.

Post-MVP worker adapter boundaries are described in [docs/adapter-contract.md](adapter-contract.md). The opt-in Git-native worker isolation and promotion slice is described in [docs/architecture/git-native-worker-isolation-and-promotion.md](architecture/git-native-worker-isolation-and-promotion.md). The registry/provider/role architecture is described in [docs/architecture/agent-registry-and-adapter-runtime.md](architecture/agent-registry-and-adapter-runtime.md), with future task-fit/context routing design in [docs/architecture/agent-selection-and-context-routing.md](architecture/agent-selection-and-context-routing.md).

The stable runtime now includes an opt-in Git-native shell-worker slice through `devflow task create --git-worktree`. The default task path remains copy-workspace. It also includes `devflow task local` as a local Ollama evidence wrapper for Qwen/Gemma planning and review output; it is not a router, auto-editor, verification runner, or promotion path. The narrow registry-backed local patch runtime is `devflow task run <task-id> --worker qwopus-implementer`, which writes patch evidence for Dev-Flow to apply and verify.

## Stable Commands

```bash
devflow --help
devflow init
devflow doctor
devflow reconcile
devflow dashboard
devflow task --help
devflow task create "example task"
devflow task create --git-worktree "example git task"
devflow task run <task-id> --worker shell -- /bin/sh -c "echo hello > result.txt"
devflow task run <task-id> --shell "echo hello > result.txt"
devflow task run <task-id> --worker qwopus-implementer
devflow task apply-patch <task-id> --agent qwopus-implementer
devflow task verify <task-id> --shell "test -f result.txt"
devflow task local <task-id> --worker qwen-planner
devflow task local <task-id> --worker gemma-reviewer --input-worker qwen-planner
devflow task list
devflow task show <task-id>
devflow task packet <task-id>
devflow task log <task-id>
devflow task promote-preview <task-id>
devflow task promote <task-id>
devflow task cleanup <task-id> --dry-run
devflow worktree list
devflow worktree prune --dry-run
devflow branch list
devflow branch archive <branch> --dry-run
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

- **Stable**: Authorized local control-room commands (e.g., `init`, `doctor`, `reconcile`, `dashboard`, `task create`, `task list`, `task show`, `task run`, `task verify`, `task local`, `task packet`, `task log`, `task promote-preview`, `task promote`, `task cleanup`, `worktree list`, `worktree prune`, `branch list`, `branch archive`, `agent show devflow-manual-codex-worker`, `agent packet <task-id> devflow-manual-codex-worker`).
- **Experimental-ReadOnly**: Read-only diagnostic and context-assembly aids (e.g., `context`, `task fit`, `task pack`, `task scout`, `task route`, `task scorecard`, non-proof-agent registry inspection).
- **Experimental-Manual**: Manual coordination and polling harnesses (e.g., `supervise`).
- **Forbidden-Runtime**: Any command or background process that bypasses human review, routes models automatically, or mutates the main checkout autonomously. No such commands are allowed in the control room.

Agent adapters also carry runtime maturity: `stable_runtime`, `local_patch_runtime`, `experimental_readonly`, or `planned_not_executable`. Only `shell` and `manual` are `stable_runtime` executable adapters in this milestone. `ollama_chat` is executable only as a safe `local_patch_runtime` agent such as `qwopus-implementer`: provider `ollama`, loopback base URL, `workspace_write`, no shell, no network permission, and `can_promote: false`. Remote provider adapters may appear in registries or docs, but task execution must fail clearly if they are invoked.

Experimental task-fit, scout, route, scorecard, context, and supervisor commands are hidden from `--help` by default and refuse execution unless the environment variable `DEVFLOW_EXPERIMENTAL=1` is explicitly set. The proof-agent registry commands are visible because they are part of this stable milestone.

`devflow init` creates or repairs the local control-room seed structure. `devflow doctor` checks that structure. `devflow reconcile` reports crash/interruption evidence without mutating files, including partial task/system event writes, task/system event divergence, interrupted promotion evidence, and inconsistent task artifacts. `devflow dashboard` renders the current text-only terminal dashboard from task artifacts.

`devflow task create` creates the task artifacts and task workspace needed by the later commands. Shell worker commands and verification commands run from the task workspace. The preferred shell-worker invocation is `devflow task run <task-id> --worker shell -- <command>`; `--shell "<command>"` remains supported.

`devflow task local <task-id> --worker qwen-planner` and `devflow task local <task-id> --worker gemma-reviewer --input-worker qwen-planner` compose prompts from `task.yaml`, Dev-Flow rules, workspace/context listings, and selected prior local-worker output, then call `ollama run <model>` through a local subprocess with a 600-second default timeout. Raw output is captured as evidence only; Dev-Flow does not parse it as truth, apply it, verify it, commit it, merge it, route automatically, or call remote provider APIs.

`devflow task run <task-id> --worker qwopus-implementer` builds a bounded agent packet, calls local Ollama through `/api/generate` with `qwopus:latest`, preserves raw output under `.devflow/tasks/<task-id>/agents/qwopus-implementer/raw_output.md`, and writes `.devflow/tasks/<task-id>/agents/qwopus-implementer/proposal.patch`. The model does not edit main, promote, or verify. The human-controlled path is `devflow task apply-patch <task-id> --agent qwopus-implementer`, then `devflow task verify`, `devflow task promote-preview`, and `devflow task promote`.

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
.devflow/tasks/<task-id>/patch-application.json
.devflow/tasks/<task-id>/patches/<patch-hash>.json
.devflow/tasks/<task-id>/agents/devflow-manual-codex-worker/handoff.md
.devflow/tasks/<task-id>/agents/devflow-manual-codex-worker/result.md
.devflow/tasks/<task-id>/agents/devflow-manual-codex-worker/questions.jsonl
.devflow/tasks/<task-id>/agents/devflow-manual-codex-worker/worker_failed.json
.devflow/tasks/<task-id>/agents/qwopus-implementer/packet.json
.devflow/tasks/<task-id>/agents/qwopus-implementer/raw_output.md
.devflow/tasks/<task-id>/agents/qwopus-implementer/proposal.patch
.devflow/tasks/<task-id>/agents/qwopus-implementer/result.md
.devflow/tasks/<task-id>/agents/qwopus-implementer/run.json
.devflow/tasks/<task-id>/agents/qwopus-implementer/logs/worker.log
.devflow/workspaces/<task-id>/
.devflow/workspaces/<task-id>/local-workers/<worker-name>/prompt.md
.devflow/workspaces/<task-id>/local-workers/<worker-name>/response.raw.md
.devflow/workspaces/<task-id>/local-workers/<worker-name>/response.md
.devflow/workspaces/<task-id>/local-workers/<worker-name>/run.json
.devflow/workspaces/<task-id>/local-workers/<worker-name>/stderr.log
.devflow/worktrees/<task-id>/shell/                          # only for --git-worktree tasks
.devflow/tasks/<task-id>/workers/shell/git.json              # only for --git-worktree tasks
.devflow/tasks/<task-id>/workers/shell/diff.patch            # only for --git-worktree tasks
.devflow/tasks/<task-id>/workers/shell/diff-summary.json     # only for --git-worktree tasks
.devflow/tasks/<task-id>/workers/shell/verification.json     # only for --git-worktree tasks
.devflow/tasks/<task-id>/workers/shell/promotion-preview.json # only for --git-worktree tasks
```

`task.yaml` is the canonical current task state. `events.jsonl` is append-only evidence. `verification.json` stores the latest verification result. Logs are raw command evidence. Patch application writes a SHA-256-addressed evidence artifact under `patches/` and updates latest `patch-application.json`; `patch_applied` events point at that evidence. The workspace is the only current place where shell-worker results and local Ollama worker artifacts are written. Versioned state artifacts include `schema_version: 1`; unversioned historical task files are treated as version 1, and unknown task schema versions are refused.

Mutating task operations use a task-local `.lock/` directory with `owner.json` metadata. `run`, `local`, `verify`, `apply-patch`, and `promote` refuse concurrent mutations for the same task, report the current lock owner, and recover locks that are stale beyond the lock TTL.

## Optional Derived State

`.devflow/tasks/<task-id>/summary.json` may exist as a derived cache for visibility and token efficiency. It is not canonical state. It may be deleted and regenerated without losing information. If it is missing, stale, malformed, or disagrees with `task.yaml`, `events.jsonl`, `verification.json`, or logs, the canonical files win.

`.devflow/tasks/<task-id>/packet.json` may exist as a generated TaskPacket dump. It is derived state and is written immediately before a worker execution when needed. Dynamic TaskPacket projections are also derived state.

`.devflow/tasks/<task-id>/result.md` may exist as a human-readable result summary. It is not canonical state.

Manual proof-agent evidence under `.devflow/tasks/<task-id>/agents/devflow-manual-codex-worker/` is worker-produced evidence, not canonical task state. Dev-Flow may display `awaiting_human`, `blocked`, `failed`, and `result_present` in `task show` and `dashboard`, but only Dev-Flow updates `task.yaml`, `events.jsonl`, `verification.json`, merge-readiness, and promotion state.

## Stable Safety Rules

- Shell workers execute only in `.devflow/workspaces/<task-id>/`.
- Local Ollama workers write evidence only under `.devflow/workspaces/<task-id>/local-workers/<worker-name>/`.
- Verification commands execute only in `.devflow/workspaces/<task-id>/`.
- Tampered task workspace paths are refused before command execution.
- Symlinks are skipped during scratchpad copy.
- Shell-worker results do not write into the main checkout.
- Local Ollama worker success is based only on subprocess exit code `0`; nonempty model output with a nonzero exit remains failed evidence.
- Local Ollama workers do not auto-edit files, auto-verify, auto-commit, auto-merge, or auto-promote.
- Promotion to the main checkout is explicit, human-confirmed, and gated on verification readiness.
- Promotion refuses unsafe workspace paths and blocks dirty main-checkout changes unless explicitly forced.
- New task events are hash-chained with monotonic indexes, previous-event hashes, and current-event hashes; `doctor` reports malformed or edited task event logs.
- `doctor --strict` is read-only and reports stale task locks, unsafe workspace paths, malformed or inconsistent JSON artifacts, missing worker/verification logs, malformed manual-agent evidence, missing patch evidence, promoted-task consistency, and Git-native worker branch sharing across tasks.
- `devflow reconcile` is read-only and reports partial task/system event writes, task/system event divergence, interrupted promotion evidence, and inconsistent task artifacts.
- No SQLite database is created.
- Default copy-workspace tasks do not create `.devflow/worktrees/`; `--git-worktree` tasks do.
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

- default workspaces are copy-based scratchpads
- opt-in `--git-worktree` tasks create branch-backed worktrees and promote with Git-aware merge mechanics
- copy-workspace promotion copies verified workspace changes into the main checkout instead of performing a git-native three-way merge
- patch application supports validated text patches only, records SHA-256 patch evidence, and rejects binary diffs, renames, copies, mode changes, and similarity metadata
- event logs are append-only evidence, but task and system event writes are still separate writes and may require human-reviewed reconciliation after a crash

Future production hardening items:
- Multi-worker Git worktree attempts per task beyond the initial shell worker lane.
- Richer Git-native conflict handling and resolver-task UX.
- Multi-worker branch-sharing cleanup beyond the initial shell worker lane.
- Per-task temporary `HOME` and temp directories.
- Network-off runner policies.
- Ollama keep-alive and model-stop controls for local resource pressure.
- Resource limits for CPU, memory, file descriptors, and process counts.
- Allowlisted command profiles and absolute path inspections.
- Container, firejail, macOS sandbox, or other OS-level isolation.
- Cautious `devflow repair --dry-run` design after read-only reconciliation reporting stays stable.

## Out Of The Current Contract

- Browser or web dashboards.
- Token-context helper as runtime authority. The helper may exist as visible planning guidance, but it does not execute token tools, route models, install hooks, or change shell-worker, verification, or promotion behavior.
- Task-fit/context routing runtime.
- Provider-backed worker adapters. The stable non-shell model path is limited to local `ollama run` evidence capture through `devflow task local`; it does not use remote provider APIs, own canonical task state, or apply model output.
- Provider-backed Git worktree orchestration beyond the opt-in shell-worker lane.
- SQLite or any other database.
- Automatic merge, automatic copy-back, commit, push, or PR automation.
- Legacy task-packet and unified-diff workflow rituals.

> [!IMPORTANT]
> **Next Priority**: Harden the opt-in Git-native shell-worker isolation and promotion slice while keeping the current shell-worker/manual proof-agent loop stable. Provider-backed adapters, autonomous routing, and PR automation remain later layers.
