# Dev-Flow

Dev-Flow is a local-first control room for parallel AI coding workers.

It is not the coding intelligence itself. It is the operational layer around coding intelligence: task state, isolated workspaces, locks and ownership, status, logs, verification evidence, and human-controlled promotion.

Workers are replaceable. The stable executable runtime supports shell workers and the manual proof-agent handoff only. Provider-backed adapters, autonomous routing, and broader orchestration remain non-stable until explicitly promoted through the registry and adapter-runtime sequence.

## Current Product Contract

The active runtime contract is [docs/mvp-contract.md](docs/mvp-contract.md). The near-term product direction is [docs/control-room-mvp.md](docs/control-room-mvp.md), grounded by [PRODUCT_NORTH_STAR.md](PRODUCT_NORTH_STAR.md).

### Stable Commands
- **Initialization & Diagnostics**: `devflow init`, `devflow doctor`, `devflow reconcile`
- **Dashboard**: `devflow dashboard`
- **Task Lifecycle**: `devflow task create`, `devflow task run --worker shell`, `devflow task verify`, `devflow task list`, `devflow task show`, `devflow task log`
- **Git-Native Task Lane**: `devflow task create --git-worktree`
- **Promotion & Merging**: `devflow task promote-preview`, `devflow task promote`
- **Git Cleanup & Repair**: `devflow worktree list`, `devflow worktree prune`, `devflow branch list`, `devflow branch archive`, `devflow task cleanup`

### Planning And Manual Transition Commands
- **Agent Registry**: `devflow agent list`, `devflow agent show`, `devflow agent packet`
- **Task Estimation**: `devflow task fit`, `devflow task pack`
- **Scouting & Routing**: `devflow task scout`, `devflow task route`, `devflow task scorecard`

These transition commands are allowed only as read-only or manual planning aids until promoted into the stable contract. Experimental ones remain gated outside the default help surface, and none of them execute provider APIs or make autonomous routing decisions in the stable runtime.

The current control-room MVP intentionally excludes enabled remote provider adapters, browser or web dashboards, database state, autonomous scheduling/routing, and provider-backed worktree orchestration. An opt-in Git-native shell-worker isolation and promotion slice is available through `devflow task create --git-worktree`, documented in [docs/architecture/git-native-worker-isolation-and-promotion.md](docs/architecture/git-native-worker-isolation-and-promotion.md). The future registries and adapter-runtime designs are documented in [docs/architecture/agent-registry-and-adapter-runtime.md](docs/architecture/agent-registry-and-adapter-runtime.md) and [docs/architecture/agent-selection-and-context-routing.md](docs/architecture/agent-selection-and-context-routing.md).

## Runtime Shape

Dev-Flow stores durable task state as local filesystem artifacts:

```text
.devflow/
  tasks/<task-id>/
    task.yaml
    events.jsonl
    verification.json
    logs/
      worker.log
      verify.log
    patch-application.json
    patches/<patch-hash>.json
  workspaces/<task-id>/
  worktrees/<task-id>/shell/                    # only for --git-worktree tasks
  tasks/<task-id>/workers/shell/git.json        # only for --git-worktree tasks
  tasks/<task-id>/workers/shell/diff.patch      # only for --git-worktree tasks
  tasks/<task-id>/workers/shell/diff-summary.json
  tasks/<task-id>/workers/shell/verification.json
  tasks/<task-id>/workers/shell/promotion-preview.json
```

`task.yaml` is canonical current state. `events.jsonl` is append-only evidence. `verification.json` stores the latest verification result. Worker and verification logs are raw command evidence. Patch application writes a SHA-256-addressed evidence file under `patches/` plus a latest `patch-application.json` pointer. Shell worker output stays in `.devflow/workspaces/<task-id>/` until a human explicitly previews and promotes verified changes.

Mutating task operations use `.devflow/tasks/<task-id>/.lock/owner.json` as a live task-local lock. Concurrent `run`, `verify`, `apply-patch`, and `promote` operations for the same task are refused with owner details, and stale locks are recovered automatically.

## Safety Model And Known Limitations

Dev-Flow `0.1.0` is an unreleased local MVP for a trusted single-user machine. It is useful as a control-room kernel, but it is not a security sandbox for untrusted commands, agents, repositories, or multi-user execution.

- Shell and verification commands run as local subprocesses in the assigned `.devflow/workspaces/<task-id>/` directory with a filtered environment, timeout, process-group cleanup on POSIX systems, and capped worker logs.
- The shell worker is path-isolated, not sandboxed. A command can still use the local user's permissions, spawn processes until killed, read accessible files, use available network access, and consume local resources.
- Default task workspaces are copy-based scratchpads. This keeps the MVP simple but can be slow for large repositories and does not use git merge machinery inside the workspace.
- `devflow task create --git-worktree` creates a branch-backed worktree under `.devflow/worktrees/<task-id>/shell/`, records Git evidence, binds verification to the worker branch commit, and uses Git-aware promotion mechanics. Git cleanup commands are dry-run-first: use `devflow worktree list`, `devflow branch list`, `devflow worktree prune --dry-run`, `devflow branch archive <branch> --dry-run`, and `devflow task cleanup <task-id> --dry-run` before applying mutations.
- Promotion is explicit, readiness-gated, and human-controlled. Copy-workspace tasks promote by copying verified workspace changes back into the main checkout; Git worktree tasks promote through the worker branch path.
- The patch applier is a text-only MVP path with strong path validation and durable patch hash evidence. It intentionally rejects binary diffs, renames, mode changes, copies, and complex git metadata.

Use Dev-Flow only on repositories and worker commands you trust. The Git-native shell-worker path now moves worker isolation and promotion onto git worktrees/branches, binds verification to commits, extends strict readiness checks with Git facts, and includes dry-run-first cleanup for orphaned Dev-Flow worktrees and branches. Stricter command policy, multi-worker worktree scheduling, and optional network/resource controls remain later hardening layers.

## Durable Context Structure

The broader `.devflow/` tree is also the durable context layer for the control room. It contains project orientation, active goals, classified context, layered product and architecture notes, worker/model registries, lock documentation, derived reports, and preserved archive material.

Start with:

- [.devflow/project/project.yaml](.devflow/project/project.yaml): machine-readable project orientation.
- [.devflow/goals/bootstrap-devflow-filesystem/goal.yaml](.devflow/goals/bootstrap-devflow-filesystem/goal.yaml): active bootstrap filesystem goal.
- [.devflow/context/active/README.md](.devflow/context/active/README.md): context classification entry point.
- [.devflow/layers/architecture/contracts.md](.devflow/layers/architecture/contracts.md): layer-local contract pointers.
- [docs/devflow-control-loop-contracts.md](docs/devflow-control-loop-contracts.md): reference architecture for the target structure.

## Quick Start

Install locally from the repository root:

```bash
python -m venv .venv
.venv/bin/python -m pip install -e .
```

After a tagged public release exists, the intended user install paths are `pipx install devflow` for CLI use or `python -m pip install devflow` for library/CLI environments. Until then, use the local editable install above or install from a trusted source checkout.

Initialize the control-room structure:

```bash
.venv/bin/python -m devflow.cli init
.venv/bin/python -m devflow.cli doctor
```

Create, run, verify, inspect, and preview one default copy-workspace shell task:

```bash
TASK_ID=$(.venv/bin/python -m devflow.cli task create "write hello result" | sed -n 's/^Created \(task-[^:]*\):.*/\1/p')
.venv/bin/python -m devflow.cli task run "$TASK_ID" --worker shell -- /bin/sh -c "echo hello > result.txt"
.venv/bin/python -m devflow.cli task verify "$TASK_ID" --shell "test -f result.txt"
.venv/bin/python -m devflow.cli task show "$TASK_ID"
.venv/bin/python -m devflow.cli dashboard
.venv/bin/python -m devflow.cli task promote-preview "$TASK_ID"
```

Promotion is explicit and human-controlled:

```bash
.venv/bin/python -m devflow.cli task promote "$TASK_ID"
```

Use promotion only after reviewing the preview and verification evidence.
If the main checkout advanced after the task workspace was created, promotion refuses by default. Use `--force-stale-baseline` only after manually reviewing that stale-baseline risk.

Create an opt-in Git-native shell task:

```bash
TASK_ID=$(.venv/bin/python -m devflow.cli task create --git-worktree "write hello result" | sed -n 's/^Created \(task-[^:]*\):.*/\1/p')
.venv/bin/python -m devflow.cli task run "$TASK_ID" --worker shell -- /bin/sh -c "echo hello > result.txt && git add result.txt && git commit -m devflow-result"
.venv/bin/python -m devflow.cli task verify "$TASK_ID" --shell "test -f result.txt"
.venv/bin/python -m devflow.cli task promote-preview "$TASK_ID"
```

Git-native promotion refuses if the worker branch HEAD differs from the verified commit, the worktree is dirty after verification, the baseline is stale without explicit review, or merge conflicts are predicted.

`devflow doctor --strict` is a read-only readiness report. It now checks stale task locks, unsafe workspace paths, malformed or inconsistent JSON artifacts, missing worker/verification logs, malformed manual-agent evidence, missing patch evidence, and promoted-task consistency. It does not repair artifacts automatically.

`devflow reconcile` is a read-only crash/interruption report. It surfaces partial task/system event writes, task/system event divergence, interrupted promotion evidence such as stale promote locks, and inconsistent task artifacts. Use `--json` for machine-readable output or `--task <task-id>` to inspect one task. It does not repair artifacts automatically.

Manual proof-agent runs generate handoff evidence and then wait for worker-written evidence under `.devflow/tasks/<task-id>/agents/devflow-manual-codex-worker/`. Future provider adapters may be described in registries, but only the `shell` and `manual` adapters are executable in the stable runtime.

## Release And Versioning

- [CHANGELOG.md](CHANGELOG.md) records release notes, semantic versioning rules, and state compatibility requirements.
- [docs/RELEASE_CHECKLIST.md](docs/RELEASE_CHECKLIST.md) defines the pre-release validation gate.
- The package metadata uses this README as the public long description.
- No public release artifact has been published yet; `0.1.0` is the unreleased local MVP line.

## DevMode Relationship

DevMode is the portable discipline layer for agent behavior: mode gating, search-before-read context discipline, focused changes, and verification before completion.

Dev-Flow is the product in this repository: the local-first control room that owns task state, worker isolation, logs, verification evidence, and promotion readiness.

The canonical DevMode contract is [docs/devmode-contract.md](docs/devmode-contract.md). The boundary is documented in [docs/devmode-devflow-boundary.md](docs/devmode-devflow-boundary.md). DevMode guides humans and agents working in this repo; it is not the Dev-Flow runtime.

DevMode harness compatibility is tracked in [docs/harness-compatibility.md](docs/harness-compatibility.md) for Claude Code, Gemini CLI, Cursor, Codex, OpenCode, and VS Code / GitHub Copilot.

## Active References

- [PRODUCT_NORTH_STAR.md](PRODUCT_NORTH_STAR.md): long-term product identity and self-checks.
- [docs/mvp-contract.md](docs/mvp-contract.md): stable current command, filesystem, and safety contract.
- [docs/control-room-mvp.md](docs/control-room-mvp.md): near-term MVP authority.
- [docs/architecture/agent-registry-and-adapter-runtime.md](docs/architecture/agent-registry-and-adapter-runtime.md): next architecture direction for provider, agent, role, permission, adapter, and routing contracts.
- [docs/architecture/git-native-worker-isolation-and-promotion.md](docs/architecture/git-native-worker-isolation-and-promotion.md): opt-in Git-backed worker isolation, verification binding, and promotion readiness.
- [docs/architecture/agent-selection-and-context-routing.md](docs/architecture/agent-selection-and-context-routing.md): future task-fit, context-estimation, model-capability, context-pack, scout, and routing-quality design.
- [docs/roadmap.md](docs/roadmap.md): current sequencing and deferred work.
- [docs/agent-handoff.md](docs/agent-handoff.md): orientation for future agents.
- [docs/devflow-operating-model.md](docs/devflow-operating-model.md): role split between human, main chat agent, Dev-Flow kernel, worker agents, and DevMode.
- [docs/read-only-control-room-agent.md](docs/read-only-control-room-agent.md): main chat agent responsibilities and boundaries.
- [docs/devmode-devflow-boundary.md](docs/devmode-devflow-boundary.md): product/runtime boundary between DevMode and Dev-Flow.

## Development Boundary

Active control-room code belongs under:

```text
src/devflow/control_room/
```

Legacy software-factory files are quarantined under:

```text
src/devflow/_legacy/
```

Do not add new product features under top-level compatibility shims or `_legacy/`.

## Verification

Focused control-room verification:

```bash
.venv/bin/python -m pytest tests/test_architecture_boundaries.py tests/test_devflow_init_structure.py tests/test_control_room_shell.py tests/test_promote_preview.py tests/test_task_packet.py -q
```

Current development should keep the shell-worker/manual proof-agent loop stable while hardening opt-in Git-native worker isolation, commit-bound verification evidence, human-controlled promotion, and merge readiness.

## License

Dev-Flow is released under the [MIT License](LICENSE).

This repository also contains DevMode skill and harness material influenced by [Superpowers](https://github.com/obra/superpowers). Attribution details are in [ATTRIBUTION.md](ATTRIBUTION.md).
