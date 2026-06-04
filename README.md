# Dev-Flow

Dev-Flow is a local-first control room for parallel AI coding workers.

Local checkout note: use `<repo-root>` for portable command examples. This checkout is referred to as `DevFlow` in docs and handoffs. The old local path `/Users/jewelbait/Desktop/DevFlow` is quarantined and must not be used for current work.

It is not the coding intelligence itself. It is the operational layer around coding intelligence: task state, isolated workspaces, locks and ownership, status, logs, verification evidence, and human-controlled promotion.

Workers are replaceable. The stable code-changing runtime supports shell workers, while the manual proof-agent handoff and legacy local Ollama advisory ladder produce evidence only. The registry-backed `devflow task run <task-id> --worker qwopus-implementer` path is the narrow first local Ollama patch-proposal runtime: it writes `proposal.patch` evidence for Dev-Flow to apply and verify. The local model worker pool adds registry-visible read-only profiles for Josh's heterogeneous Mac mini/Mac Studio Ollama fleet and writes generalized WorkerEvidence under task-local `local-model-runs/`. Remote provider adapters, autonomous routing, and broader orchestration remain non-stable until explicitly promoted through the registry and adapter-runtime sequence.

## Current Product Contract

The active runtime contract is [docs/mvp-contract.md](docs/mvp-contract.md). The near-term product direction is [docs/control-room-mvp.md](docs/control-room-mvp.md), grounded by [PRODUCT_NORTH_STAR.md](PRODUCT_NORTH_STAR.md).

The staged evidence path for proposal patches, patch review, patch dry-run preview, explicit patch application, verification, and human-controlled promotion is documented in [docs/architecture/patch-evidence-ladder.md](docs/architecture/patch-evidence-ladder.md). Future context intake layers such as Project Code Map and Idea Foundry are documented there as roadmap concepts, not current stable commands.

### Stable Commands
- **Initialization & Diagnostics**: `devflow init`, `devflow doctor`, `devflow reconcile`, `devflow freshness loop`
- **Dashboard**: `devflow dashboard`
- **Task Lifecycle**: `devflow task create`, `devflow task run --worker shell`, `devflow task run --worker qwopus-implementer`, `devflow task review-patch`, `devflow task patch-dry-run`, `devflow task apply-patch`, `devflow task local --worker qwen-planner`, `devflow task verify`, `devflow task finalize`, `devflow task close`, `devflow task list`, `devflow task show`, `devflow task log`
- **Policy & Evidence**: `devflow task orchestrate --plan-only`, `devflow worker validate-outcome`
- **Knowledge Foundry**: `devflow knowledge capture`, `devflow knowledge list`, `devflow knowledge show`, `devflow knowledge promote`, `devflow knowledge reject`, `devflow knowledge search`
- **Git-Native Task Lane**: `devflow task create --git-worktree`, `devflow task finalize` (dry-run & `--commit`)
- **Promotion & Merging**: `devflow task promote-preview`, `devflow task promote`
- **Git Cleanup & Repair**: `devflow worktree list`, `devflow worktree prune`, `devflow branch list`, `devflow branch archive`, `devflow task cleanup`

### Planning And Manual Transition Commands
- **Agent Registry**: `devflow agent list`, `devflow agent show`, `devflow agent policy`, `devflow agent packet`, `devflow agent run --task <task-id> --profile local-qwopus-inspector --dry-run --json`
- **Task Estimation**: `devflow task fit`, `devflow task pack`
- **Scouting & Routing**: `devflow task scout`, `devflow task route`, `devflow task scorecard`

These transition commands are allowed only as read-only or manual planning aids until promoted into the stable contract. Experimental ones remain gated outside the default help surface, and none of them execute provider APIs or make autonomous routing decisions in the stable runtime.

The current control-room MVP intentionally excludes enabled remote provider adapters, browser or web dashboards, database state, autonomous scheduling/routing, and provider-backed worktree orchestration. The practical local model pool is documented in [docs/architecture/local-model-worker-pool.md](docs/architecture/local-model-worker-pool.md). Hermes integration is documented as an external operator/chat gateway over existing supervisor-safe commands, not as a Dev-Flow runtime, in [docs/integrations/hermes-operator-layer.md](docs/integrations/hermes-operator-layer.md), [docs/integrations/hermes-command-allowlist.md](docs/integrations/hermes-command-allowlist.md), [docs/integrations/hermes-imessage-exploration.md](docs/integrations/hermes-imessage-exploration.md), [docs/integrations/hermes-local-parallelism.md](docs/integrations/hermes-local-parallelism.md), [docs/integrations/hermes-worker-evidence-synthesis.md](docs/integrations/hermes-worker-evidence-synthesis.md), and the setup rollout in [docs/integrations/hermes-telegram-mac-mini-rollout.md](docs/integrations/hermes-telegram-mac-mini-rollout.md). An opt-in Git-native shell-worker isolation and promotion slice is available through `devflow task create --git-worktree`, documented in [docs/architecture/git-native-worker-isolation-and-promotion.md](docs/architecture/git-native-worker-isolation-and-promotion.md). The future registries and adapter-runtime designs are documented in [docs/architecture/agent-registry-and-adapter-runtime.md](docs/architecture/agent-registry-and-adapter-runtime.md) and [docs/architecture/agent-selection-and-context-routing.md](docs/architecture/agent-selection-and-context-routing.md).

## Runtime Shape

Dev-Flow stores durable task state as local filesystem artifacts:

```text
.devflow/
  tasks/<task-id>/
    task.yaml
    events.jsonl
    verification.json
    closure.json
    cleanup.json
    orchestration-plan.yaml
    worker-outcome-validation.json
    agents/<agent-id>/packet.json
    agents/<agent-id>/raw_output.md
    agents/<agent-id>/proposal.patch
    agents/<agent-id>/result.md
    agents/<agent-id>/run.json
    agents/<agent-id>/logs/worker.log
    local-model-runs/<run-id>/proposal.md
    local-model-runs/<run-id>/proposal.json
    local-model-runs/<run-id>/proposal.patch
    local-model-runs/<run-id>/run.json
    local-model-runs/<run-id>/packet.md
    local-model-runs/<run-id>/response.md
    local-model-runs/<run-id>/raw_output.txt
    local-model-runs/<run-id>/error.txt
    local-model-runs/<run-id>/patch-review.md
    local-model-runs/<run-id>/patch-review.json
    local-model-runs/<run-id>/patch-dry-run.md
    local-model-runs/<run-id>/patch-dry-run.json
    logs/
      worker.log
      verify.log
    patch-application.json
    patches/<patch-hash>.json
  workspaces/<task-id>/
    local-workers/<worker-name>/prompt.md
    local-workers/<worker-name>/response.raw.md
    local-workers/<worker-name>/response.md
    local-workers/<worker-name>/run.json
    local-workers/<worker-name>/stderr.log
  worktrees/<task-id>/shell/                    # only for --git-worktree tasks
  tasks/<task-id>/workers/shell/git.json        # only for --git-worktree tasks
  tasks/<task-id>/workers/shell/diff.patch      # only for --git-worktree tasks
  tasks/<task-id>/workers/shell/diff-summary.json
  tasks/<task-id>/workers/shell/verification.json
  tasks/<task-id>/workers/shell/promotion-preview.json
  outcome-validations/<name>-validation.json
  knowledge/<knowledge-id>/knowledge.json
  knowledge/<knowledge-id>/note.md
  knowledge/<knowledge-id>/events.jsonl
```

`task.yaml` is canonical current state. `events.jsonl` is append-only evidence. `verification.json` stores the latest verification result. Worker and verification logs are raw command evidence. Patch application writes a SHA-256-addressed evidence file under `patches/` plus a latest `patch-application.json` pointer. Shell worker output and local Ollama prompt/response artifacts stay in `.devflow/workspaces/<task-id>/` until a human explicitly reviews them; promotion remains separate and verification-gated. Closing a task writes `closure.json`, marks it inactive, and preserves task evidence. Cleanup is preview-first and writes `cleanup.json` only when `--apply` removes safe task-owned runtime artifacts.

Mutating task operations use `.devflow/tasks/<task-id>/.lock/owner.json` as a live task-local lock. Concurrent `run`, `local`, `verify`, `apply-patch`, and `promote` operations for the same task are refused with owner details, and stale locks are recovered automatically.

## Safety Model And Known Limitations

Dev-Flow `0.1.0` is an unreleased local MVP for a trusted single-user machine. It is useful as a control-room kernel, but it is not a security sandbox for untrusted commands, agents, repositories, or multi-user execution.

- Shell and verification commands run as local subprocesses in the assigned `.devflow/workspaces/<task-id>/` directory with a filtered environment, timeout, process-group cleanup on POSIX systems, and capped worker logs.
- `devflow task run <task-id> --worker qwopus-implementer` calls local Ollama through the registry-backed adapter, preserves raw output, and writes a proposed unified diff to `.devflow/tasks/<task-id>/agents/qwopus-implementer/proposal.patch`. This is the canonical local implementation route. Dev-Flow requires fresh acceptable patch review and dry-run evidence before explicit patch application, then runs verification and gates promotion separately.
- `devflow task local` remains a legacy advisory wrapper around `ollama run <model>` for local Qwen/Qwopus/Gemma ladder evidence. It captures raw stdout/stderr plus `run.json`, treats success as subprocess exit code `0` only, and does not write `proposal.patch`, apply model output, verify, commit, merge, promote, route models, or call remote provider APIs.
- `devflow task orchestrate <task-id> --plan-only` writes orchestration policy evidence only. It records Git/DevMode guardrails, worker roles, permissions, stop conditions, and human-promotion requirements; it does not execute workers, call providers, apply patches, verify, promote, or mutate main.
- `devflow worker validate-outcome <outcome.json>` validates worker outcome metadata only and writes validation evidence. It does not run agents, apply patches, verify code, promote tasks, route models, or mutate `task.yaml`.
- Knowledge Foundry commands store proposed/promoted/rejected reusable notes under `.devflow/knowledge/`. Knowledge promotion is separate from task promotion; capture never converts ideas into tasks or goals and is not ML training, hidden memory, vector search, or RAG.
- `devflow dogfood run --suite production-readiness` runs a deterministic local production-readiness harness and writes scorecards under `.devflow/dogfood/`. It exercises existing task, orchestration, worker outcome, verification, and knowledge surfaces; it does not call providers, route models, promote, push, create a dashboard, create a database, or train anything.
- The shell worker is path-isolated, not sandboxed. A command can still use the local user's permissions, spawn processes until killed, read accessible files, use available network access, and consume local resources.
- Default task workspaces are copy-based scratchpads. This keeps the MVP simple and is the default mode, but it can be slow for large repositories, does not use git merge machinery inside the workspace, and is recommended only for simple/experimental work.
- **Git-Native Task Lanes**: `devflow task create --git-worktree` is strongly recommended for all serious, high-assurance development work. It creates an isolated, branch-backed worktree under `.devflow/worktrees/<task-id>/shell/`, records Git evidence, binds verification directly to the worker branch commit, and uses robust Git-aware promotion mechanics rather than simple filesystem copies.
- Git cleanup commands are preview-first: use `devflow worktree list`, `devflow branch list`, `devflow worktree prune --dry-run`, `devflow branch archive <branch> --dry-run`, and `devflow task cleanup <task-id> --preview` before applying closed-task cleanup. `devflow task cleanup <task-id> --dry-run` remains available as a compatibility preview for existing Git-native cleanup reporting.
- Promotion is explicit, readiness-gated, and human-controlled. Copy-workspace tasks promote by copying verified workspace changes back into the main checkout; Git worktree tasks promote through Git branch merges.
- The patch applier is a text-only MVP path with strong path validation and durable patch hash evidence. It intentionally rejects binary diffs, renames, mode changes, copies, and complex git metadata.

### Safe Alpha Usage

To ensure safety and reliability during the trusted-local alpha phase, strictly adhere to these practices:
1. **Trusted Repos Only**: Use Dev-Flow only on repositories and with worker commands that you fully trust.
2. **Git-Native Lanes**: Prefer `devflow task create --git-worktree` for high-assurance tasks where branch semantics, merge conflict prediction, and commit-bound verification matter.
3. **Verify Before Promotion**: Always execute and review task verifications (`devflow task verify`) before running promotion.
4. **Inspect Previews**: Always review the promotion preview via `devflow task promote-preview` before committing to a merge.
5. **Local User Permissions**: Remember that shell commands run with standard local user permissions and are path-isolated, not sandboxed or security-isolated.
6. **Remote Providers Non-Stable**: Remote provider adapters (e.g. OpenAI, Anthropic, Gemini) are experimental planning aids and not stable, executable production runtimes. Standard task execution refuses to run them.

Use Dev-Flow only on repositories and worker commands you trust. The Git-native shell-worker path now moves worker isolation and promotion onto git worktrees/branches, binds verification to commits, extends strict readiness checks with Git facts, and includes dry-run-first cleanup for orphaned Dev-Flow worktrees and branches. Stricter command policy, multi-worker worktree scheduling, Ollama keep-alive/model-stop controls, and optional network/resource controls remain later hardening layers.

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

Run the local production-readiness dogfood suite:

```bash
.venv/bin/python -m devflow.cli dogfood list
.venv/bin/python -m devflow.cli dogfood run --suite production-readiness
.venv/bin/python -m devflow.cli dogfood report latest
```

The score is deterministic local evidence, not autonomous model execution. Silver is the default pass gate for the production-readiness suite.

Run the preferred local Qwopus patch-proposal path:

```bash
.venv/bin/python -m devflow.cli task run "$TASK_ID" --worker qwopus-implementer
.venv/bin/python -m devflow.cli task show "$TASK_ID"
.venv/bin/python -m devflow.cli task review-patch "$TASK_ID" --agent qwopus-implementer
.venv/bin/python -m devflow.cli task patch-dry-run "$TASK_ID" --agent qwopus-implementer
.venv/bin/python -m devflow.cli task apply-patch "$TASK_ID" --agent qwopus-implementer
.venv/bin/python -m devflow.cli task verify "$TASK_ID" --shell "<test-command>"
.venv/bin/python -m devflow.cli task promote-preview "$TASK_ID"
```

`task show` surfaces the latest Qwopus run status, raw output path, proposal patch path/size, proposed files, and the next safe command. If Qwopus fails or returns no usable diff, create a compact frontier-review handoff without calling remote providers:

```bash
.venv/bin/python -m devflow.cli task escalation-packet "$TASK_ID" --agent qwopus-implementer
```

Capture optional legacy local Qwen/Qwopus/Gemma advisory evidence without auto-editing files:

```bash
.venv/bin/python -m devflow.cli task local "$TASK_ID" --agent qwen-planner
.venv/bin/python -m devflow.cli task local "$TASK_ID" --agent qwopus-implementer
.venv/bin/python -m devflow.cli task local "$TASK_ID" --agent gemma-reviewer --input-worker qwopus-implementer
```

Canonical Qwopus artifacts are written under `.devflow/tasks/<task-id>/agents/qwopus-implementer/` as `packet.json`, `raw_output.md`, `proposal.patch`, `result.md`, `run.json`, and `logs/worker.log`. Local advisory artifacts are written under `.devflow/workspaces/<task-id>/local-workers/<worker-name>/` as prompt, raw response, normalized response copy, stderr, and run metadata. Even when the legacy advisory worker name is `qwopus-implementer`, this path is not the canonical patch worker; use `devflow task run <task-id> --worker qwopus-implementer` to produce `proposal.patch`.

Capture policy, validation, and knowledge evidence without executing workers or promotion:

```bash
.venv/bin/python -m devflow.cli task orchestrate "$TASK_ID" --plan-only
.venv/bin/python -m devflow.cli worker validate-outcome <path-to-outcome.json>
.venv/bin/python -m devflow.cli knowledge capture --from-task "$TASK_ID"
.venv/bin/python -m devflow.cli knowledge list
```

Promotion is explicit and human-controlled:

```bash
.venv/bin/python -m devflow.cli task promote "$TASK_ID"
```

Use promotion only after reviewing the preview and verification evidence.
If the main checkout advanced after the task workspace was created, promotion refuses by default. Use `--force-stale-baseline` only after manually reviewing that stale-baseline risk.

Create an opt-in Git-native shell task and finalize it:

```bash
TASK_ID=$(.venv/bin/python -m devflow.cli task create --git-worktree "write hello result" | sed -n 's/^Created \(task-[^:]*\):.*/\1/p')
.venv/bin/python -m devflow.cli task run "$TASK_ID" --worker shell -- /bin/sh -c "echo hello > result.txt"
.venv/bin/python -m devflow.cli task verify "$TASK_ID" --shell "test -f result.txt"
.venv/bin/python -m devflow.cli task finalize "$TASK_ID"
.venv/bin/python -m devflow.cli task finalize "$TASK_ID" --commit
.venv/bin/python -m devflow.cli task promote-preview "$TASK_ID"
.venv/bin/python -m devflow.cli task promote "$TASK_ID"
```

Git-native promotion refuses if the worker branch HEAD differs from the verified commit, the worktree is dirty after verification, the baseline is stale without explicit review, or merge conflicts are predicted.

### Task Lifecycle And Closure

A task normally moves through active work, verification, optional finalization, promotion, and closure:

- **Active task**: created, running, complete, blocked, failed, or awaiting verification.
- **Verified task**: verification evidence passed and promotion readiness can be inspected.
- **Finalized task**: a Git-native worker lane has reviewed/staged task-owned changes and optionally committed them.
- **Promoted task**: verified changes were explicitly promoted to the main checkout.
- **Closed task**: the task is inactive with a recorded outcome and reason; evidence stays under `.devflow/tasks/<task-id>/`.
- **Cleanup preview/apply**: preview shows task-owned runtime artifacts that can be removed; apply removes only conservative `.devflow` runtime targets and writes cleanup evidence.

```bash
devflow task close task-0016 --outcome rejected --reason "Qwopus proposal was unsafe; manual repair committed separately."
devflow task cleanup task-0016 --preview
devflow task cleanup task-0016 --apply
```
After `task finalize --commit`, the commit is on the task worker branch and main is unchanged; `task show` points the operator to `devflow task promote-preview <task_id>`. `promote-preview` is read-only and reports that main will not change until `devflow task promote <task_id>`. Git-native `promote` completes the approved merge as a clean main-branch commit instead of leaving staged merge leftovers.

`devflow doctor --strict` is a read-only readiness report. It now checks stale task locks, unsafe workspace paths, malformed or inconsistent JSON artifacts, missing worker/verification logs, malformed manual-agent evidence, missing patch evidence, promoted-task consistency, and Git-native worker branch sharing across tasks. It does not repair artifacts automatically.

`devflow reconcile` is a read-only crash/interruption report. It surfaces partial task/system event writes, task/system event divergence, interrupted promotion evidence such as stale promote locks, and inconsistent task artifacts. Use `--json` for machine-readable output or `--task <task-id>` to inspect one task. It does not repair artifacts automatically.

`devflow freshness loop` runs one goal/task/document freshness pass, writes `.devflow/freshness/latest.json`, and reports contradictions such as a goal handoff claiming promotion is pending after a linked task has been promoted. If repair is ambiguous, it exits with a human-decision status instead of rewriting goal or handoff artifacts. `devflow freshness run --max-iterations N` repeats that pass within a bounded PLC-style control run and writes `.devflow/freshness/control-runs/<run_id>.json`; `--all-projects` repeats bounded-parallel, read-mostly scans across registered project roots while keeping project-local state canonical. `--create-tasks`, `--execute-workers`, and `--execute-verification` are required before it dispatches projected task creation, shell-worker, or verification work. `devflow freshness create-batch <goal_id> <batch_id>` creates tasks for one currently projected conflict-safe parallel batch. `devflow freshness worker-batch <goal_id> <batch_id> --max-parallel N` runs one currently projected shell-worker batch through task-local workspaces and logs. `devflow freshness verify-batch <goal_id> <batch_id> --max-parallel N` executes one currently projected verification batch, preserves task-local verification evidence, and writes a derived run report without marking the goal complete.

Manual proof-agent runs generate handoff evidence and then wait for worker-written evidence under `.devflow/tasks/<task-id>/agents/devflow-manual-codex-worker/`. Future remote provider adapters may be described in registries, but only `shell`, `manual`, and approved local Ollama patch agents such as `qwopus-implementer` are executable through `task run`; local Qwen/Qwopus/Gemma evidence capture uses `task local` and does not apply model output.

## Release And Versioning

- [CHANGELOG.md](CHANGELOG.md) records release notes, semantic versioning rules, and state compatibility requirements.
- [docs/RELEASE_CHECKLIST.md](docs/RELEASE_CHECKLIST.md) defines the pre-release validation gate.
- The package metadata uses this README as the public long description.
- No public release artifact has been published yet; `0.1.0` is the unreleased local MVP line.

## DevMode Relationship

DevMode is the portable discipline layer for agent behavior: mode gating, search-before-read context discipline, focused changes, and verification before completion.

Dev-Flow is the product in this repository: the local-first control room that owns task state, worker isolation, logs, verification evidence, and promotion readiness.

The canonical DevMode contract is [docs/devmode-contract.md](docs/devmode-contract.md). The boundary is documented in [docs/devmode-devflow-boundary.md](docs/devmode-devflow-boundary.md), and the Git policy bridge is documented in [docs/devmode-git-policy-bridge.md](docs/devmode-git-policy-bridge.md). DevMode guides humans and agents working in this repo; it is not the Dev-Flow runtime.

Git-changing actions should use Dev-Flow guardrail commands where available: `devflow git status`, `devflow sync-main`, `devflow task promote-preview`, `devflow task promote`, and `devflow push-main`.

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
Do not restore quarantined local checkout material from `/Users/jewelbait/Desktop/DevFlow` into active authority unless it is intentionally rewritten as current source.

## Verification

Focused control-room verification:

```bash
.venv/bin/python -m pytest tests/test_architecture_boundaries.py tests/test_devflow_init_structure.py tests/test_control_room_shell.py tests/test_promote_preview.py tests/test_task_packet.py -q
```

Current development should keep the shell-worker/manual proof-agent loop stable while tightening verification and readiness evidence around applied patches without collapsing apply-patch, verification, or promotion into one step.

## License

Dev-Flow is released under the [MIT License](LICENSE).

This repository also contains DevMode skill and harness material influenced by [Superpowers](https://github.com/obra/superpowers). Attribution details are in [ATTRIBUTION.md](ATTRIBUTION.md).
