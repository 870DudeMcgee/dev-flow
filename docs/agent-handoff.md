# Agent Handoff

Date: 2026-05-27

Local checkout: Use `<repo-root>` for portable command examples. This checkout is referred to as `DevFlow` in docs and handoffs. The old local path `/Users/jewelbait/Desktop/DevFlow` is quarantined and must not be used for current work. Do not assume every user's checkout folder is named `DevFlow`; future handoffs and command examples should use the actual path in context or a neutral placeholder such as `<repo-root>`.

## Current Direction

Dev-Flow is being rebuilt as a local-first control room for parallel AI coding workers.

The previous Dev-Flow direction has been archived. It is no longer the process authority for this repository.

Active source of truth:

- [PRODUCT_NORTH_STAR.md](../PRODUCT_NORTH_STAR.md)
- [docs/mvp-contract.md](mvp-contract.md)
- [docs/control-room-mvp.md](control-room-mvp.md)
- [docs/roadmap.md](roadmap.md)
- [README.md](../README.md)
- [docs/devflow-operating-model.md](devflow-operating-model.md) defines the role split between human, main chat/control-room agent, Dev-Flow kernel, worker agents, and DevMode.
- [docs/read-only-control-room-agent.md](read-only-control-room-agent.md) defines the main chat agent as read-only planner/spec/reviewer/coordinator.
- [docs/devmode-devflow-boundary.md](devmode-devflow-boundary.md) defines the boundary between DevMode discipline and Dev-Flow orchestration.
- [docs/architecture/git-native-worker-isolation-and-promotion.md](architecture/git-native-worker-isolation-and-promotion.md) defines the opt-in Git-backed worker branches/worktrees and Git-native promotion slice.
- [docs/architecture/multi-project-registry.md](architecture/multi-project-registry.md) defines the first-class multi-project registry and local-first project Git/GitHub policy.
- [docs/architecture/agent-registry-and-adapter-runtime.md](architecture/agent-registry-and-adapter-runtime.md) defines the next provider/agent/role registry and adapter runtime direction.
- [docs/architecture/agent-selection-and-context-routing.md](architecture/agent-selection-and-context-routing.md) defines the task-fit, context-estimation, model-capability, context-pack, scout, and routing-quality design. Milestone 17 has an approved evidence-only spec at [docs/superpowers/specs/2026-06-14-milestone-17-task-fit-context-routing-design.md](superpowers/specs/2026-06-14-milestone-17-task-fit-context-routing-design.md); autonomous routing remains excluded.
- [docs/integrations/hermes-operator-layer.md](integrations/hermes-operator-layer.md), [docs/integrations/hermes-command-allowlist.md](integrations/hermes-command-allowlist.md), [docs/integrations/hermes-imessage-exploration.md](integrations/hermes-imessage-exploration.md), [docs/integrations/hermes-local-parallelism.md](integrations/hermes-local-parallelism.md), and [docs/integrations/hermes-telegram-mac-mini-rollout.md](integrations/hermes-telegram-mac-mini-rollout.md) define Hermes as an external operator layer over supervisor-safe commands, including iMessage exploration, scheduled briefs, bounded local parallelism, and the Mac mini local-model rollout.


Archive note: legacy software-factory archives are quarantined outside the active repository tree. Do not recreate or consult in-repo archive copies as process authority.
Checkout quarantine note: do not restore material from `/Users/jewelbait/Desktop/DevFlow` into active authority unless the useful part is intentionally rewritten as current, non-archived source.

## Product Boundary

Dev-Flow is not the main coding brain. It coordinates replaceable workers and owns durable state, process isolation, status, logs, questions, result bundles, verification evidence, and merge readiness.

The current milestone is a shell-worker control-room contract plus one manual proof-agent handoff for `devflow-manual-codex-worker`, one legacy local Ollama advisory wrapper for Qwen/Qwopus/Gemma planning and review, the registry-backed `task run --worker qwopus-implementer` patch-proposal path, and the Hermes external operator layer over supervisor-safe commands. It includes task creation, isolated execution/handoff, local prompt-response capture, verification, visibility, iMessage readiness exploration, scheduled read-only briefs, bounded local parallelism policy, and human-controlled promotion.

The initial Git-native production slice is implemented for shell workers: `devflow task create --git-worktree` creates a Dev-Flow-owned branch/worktree under `.devflow/worktrees/<task_id>/shell/`, verification binds to the worker branch commit, promotion preview reports Git readiness, and humans promote through Git-aware mechanics rather than blind copy-back.

## Code Architecture Boundary

The repository enforces a strict boundary between active and legacy code. Future agents must respect these rules:

1. **Active Core (`src/devflow/control_room/`):** This is the ONLY authoritative directory for active product code. All new control-room logic, features, and active implementations must be built here.
2. **Quarantined Legacy (`src/devflow/_legacy/`):** All legacy software-factory modules, runners, evaluators, memory systems, and agents are quarantined here. **New features or code changes must NEVER be added to this directory.**
3. **Compatibility Shims (top-level `src/devflow/*.py`):** These shims exist strictly to satisfy legacy import paths and tests. They dynamically proxy to legacy modules using `sys.modules[__name__] = _legacy_module`. They are temporary compatibility bridges; active control-room code must never import or depend on them.
4. **Canonical State:** The canonical runtime state of Dev-Flow is stored strictly as filesystem artifacts (e.g. `task.yaml`, `events.jsonl`, and task logs), NOT in memory, databases, or legacy summaries.



Normal local development install:

```bash
.venv/bin/python -m pip install -e .
```

That editable install exposes the console script declared in `pyproject.toml` as `devflow = "devflow.cli:main"`.

Current product contract:

- `devflow --help`
- `devflow init`
- `devflow doctor`
- `devflow reconcile`
- `devflow freshness loop`
- `devflow dashboard`
- `devflow task --help`
- `devflow task create "title"`
- `devflow task list`
- `devflow task show <task_id>`
- `devflow task run <task_id> --worker shell -- /bin/sh -c "echo hello > result.txt"`
- `devflow task local <task_id> --agent qwen-planner`
- `devflow task local <task_id> --agent qwopus-implementer`
- `devflow task local <task_id> --agent gemma-reviewer --input-worker qwopus-implementer`
- `devflow task verify <task_id> --shell "test -f result.txt"`
- `devflow task packet <task_id>`
- `devflow agent show devflow-manual-codex-worker`
- `devflow agent packet <task_id> devflow-manual-codex-worker`
- `devflow task run <task_id> --worker devflow-manual-codex-worker`
- `devflow task log <task_id>`
- `devflow task apply-patch <task_id>` with SHA-256 patch evidence under `.devflow/tasks/<task_id>/patches/`
- `devflow task orchestrate <task_id> --plan-only`
- `devflow worker validate-outcome <path-to-outcome-json>`
- `devflow knowledge capture/list/show/promote/reject/search`
- `devflow task promote-preview <task_id>`
- `devflow task promote <task_id>`
- filesystem task state with canonical `task.yaml`
- atomic write-then-replace for canonical `task.yaml`, derived `summary.json`, latest `verification.json`, and `merge-readiness.json`
- task append-only `events.jsonl`
- task-local worker logs, verification logs, verification JSON, and YAML artifacts
- local Ollama worker artifacts under `.devflow/workspaces/<task_id>/local-workers/<worker-name>/`: `prompt.md`, `response.raw.md`, `response.md`, `run.json`, and `stderr.log`
- strict doctor read-only diagnostics for stale locks, unsafe workspace paths, invalid JSON artifacts, missing logs, malformed manual-agent evidence, missing patch evidence, promoted-task consistency, and Git-native worker branch sharing across tasks
- read-only reconciliation reporting for partial task/system event writes, task/system event divergence, interrupted promotion evidence, and inconsistent task artifacts
- freshness loop snapshots under `.devflow/freshness/latest.json` that compare canonical goal/task state with linked task slices and handoffs, then stop for a human decision when repair is ambiguous
- copied scratchpad workspaces under `.devflow/workspaces/<task_id>/`
- verification command execution inside task workspaces
- POSIX process-group cleanup for shell and verification timeout paths
- `verified` and `verification_failed` task statuses from verification
- text-only terminal dashboard from canonical task artifacts
- human-controlled promotion preview and promotion from isolated workspaces
- no SQLite database; default copy-workspace tasks do not create `.devflow/worktrees/`
- read-only `TaskPacket` builder in `src/devflow/control_room/task_packet.py`; it is a derived projection only and is consumed by the manual proof-agent handoff without becoming canonical state
- design-only Agent Registry and Adapter Runtime architecture; not active runtime behavior yet
- design-only task-fit/context routing architecture; not active runtime behavior yet
- opt-in Git-native shell-worker isolation and promotion slice through `devflow task create --git-worktree`
- explicit post-finalize Git-native UX: `task finalize --commit` reports that the commit landed on the task worker branch and main is unchanged; `task show` points finalized-but-unpromoted tasks to `devflow task promote-preview <task_id>`; `promote-preview` is read-only and points to `devflow task promote <task_id>`; Git-native promotion completes the approved merge without leaving staged leftovers
- dry-run-first Git cleanup/repair commands: `devflow worktree list`, `devflow worktree prune`, `devflow branch list`, `devflow branch archive`, and `devflow task cleanup`
- first-class multi-project registry commands: `devflow project create`, `devflow project import`, `devflow project list/show/status/doctor/archive/remove`, `devflow project connect-github`, `devflow dashboard --all-projects`, and `devflow status --all-projects --json`
- plan-only orchestration policy evidence, worker outcome metadata validation evidence, and human-reviewed Knowledge Foundry notes
- trusted-local safety model only: shell execution is path-isolated in a copied workspace, not OS-sandboxed
- integrated control-room refactoring modules documented in [docs/architecture/control-room-refactoring-integration.md](architecture/control-room-refactoring-integration.md): shared patch proposal parsing/path policy, centralized provider patch evidence behavior, projection-based status/dashboard/review capsule decisions, and task lifecycle write facade

## Git-Native Slice

Implemented from [docs/architecture/git-native-worker-isolation-and-promotion.md](architecture/git-native-worker-isolation-and-promotion.md):

- create a Dev-Flow task branch from current `main` HEAD
- create `.devflow/worktrees/<task_id>/<worker_id>/`
- run the shell worker and verification inside that worktree
- record base commit, worker branch, worktree path, worker HEAD, and dirty state
- bind verification to the exact worker HEAD commit
- make `promote-preview` report base commit, main HEAD, worker branch HEAD, merge-base, changed/deleted/renamed/untracked/binary files, conflict prediction, verification status, and promotion readiness
- refuse promotion if worker HEAD changed after verification
- refuse promotion if main moved and stale baseline or conflicts are unresolved
- promote with Git-aware mechanics under human control
- detect shared Git worker branch claims during `doctor --strict`
- list owned/orphaned Dev-Flow worktrees and branches, prune orphaned worktrees with `--apply`, and archive task branches under `devflow/archive/`

## Required Current Commands

```bash
devflow --help
devflow init
devflow doctor
devflow git status
devflow sync-main
devflow reconcile
devflow freshness loop
devflow dashboard
devflow task --help
devflow task create "example task"
devflow task run <task_id> --worker shell -- /bin/sh -c "echo hello > result.txt"
devflow task verify <task_id> --shell "test -f result.txt"
devflow task show <task_id>
devflow task list
devflow task packet <task_id>
devflow task log <task_id>
devflow task orchestrate <task_id> --plan-only
devflow worker validate-outcome <path-to-outcome-json>
devflow knowledge capture --from-task <task_id>
devflow task promote-preview <task_id>
devflow task promote <task_id>
devflow push-main
```

## Implementation Posture

- Read the North Star before implementation decisions and use its Periodic Self-Check to catch product drift.
- Prefer direct implementation over ceremonial workflow.
- Do not create legacy task files for this rebuild.
- Do not route implementation through old agent, memory, context-pack, DAG, trace, eval, or unified-diff runner surfaces. Knowledge Foundry is a separate human-reviewed curation layer, not hidden memory.
- Treat autonomous browser/web dashboard mutation surfaces, token-context runtime routing, autonomous task-fit/context routing runtime, databases, and provider-backed worker adapters as outside the current contract unless a future implementation explicitly promotes them. Milestone 17 is approved only for evidence-only task-fit/context-routing artifacts. The approved local operating-layer UI is a guarded control surface over existing filesystem evidence: its Action Rail may execute supervisor-classified read-only Dev-Flow commands plus exact approval-gated task verification and task promotion commands, while worker execution, task creation/patch application, git publication, and other approval-required commands stay blocked for trusted CLI execution. Default runtime behavior stays copy-workspace unless `--git-worktree` is requested.
- Future non-shell worker work beyond `devflow-manual-codex-worker`, the narrow `task local` advisory wrapper, and the registry-backed `task run --worker qwopus-implementer` patch runtime must follow the registry sequence: shell alignment, deterministic task-fit/context estimation, context pack building, local adapter, provider adapters, routing, and metrics.
- Dogfood future implementation slices through Dev-Flow shell tasks or local worker commands where practical, so Dev-Flow tests its own isolation, logs, verification evidence, dashboard visibility, promotion previews, and handoff quality.
- Close every meaningful milestone or product-direction change by aligning active docs, removing stale context, verifying, committing, merging to `main`, pushing, and writing a compact handoff with one next safe action.
- Treat stale plans, archived workflow instructions, old command lists, and conflicting architecture notes as poison context. Delete, rewrite, or quarantine them before they can steer another agent.
- Salvage useful code only when it supports the new control-room MVP.
- Keep unrelated dirty worktree changes intact.

## Useful Existing Code To Inspect Later

- `src/devflow/cli.py`: current CLI entry point, but likely too broad.
- `src/devflow/runner.py`: possible shell and verification helper salvage.
- `src/devflow/failures.py`: possible simple failure taxonomy salvage.

## Acceptance Check

Create one default shell task, run `echo hello > result.txt`, verify `test -f result.txt`, list it, show it, inspect the dashboard, preview promotion, and promote only after explicit human approval. Confirm `result.txt` exists only in `.devflow/workspaces/<task_id>/` before promotion and the task artifacts exist. For the Git-native path, create a task with `--git-worktree`, commit worker changes on `devflow/<task_id>/shell`, verify, finalize preview, finalize with `--commit`, confirm `task show` directs the next action to `promote-preview`, preview Git readiness without changing main, and promote only after explicit human approval.

Current verification covers the command/filesystem/safety contract, copied workspace isolation, append-only events, verification logs, tampered workspace refusal, symlink skipping, dashboard projection, and promotion safety in the focused tests. Focused task-packet projection coverage lives in `tests/test_task_packet.py`.

Goal `G-0001` integration notes live in [docs/architecture/control-room-refactoring-integration.md](architecture/control-room-refactoring-integration.md).

## Pending Operating-Layer Plan

The next safe UI action is [docs/superpowers/plans/2026-06-05-operating-layer-approved-action-result-retention.md](superpowers/plans/2026-06-05-operating-layer-approved-action-result-retention.md): preserve the visible result of browser-approved verification/promotion commands after `/api/snapshot` refresh while keeping server-side approval guardrails authoritative.

## Known Worktree State At Handoff

Before this documentation reset, the repository already had unrelated dirty files in public-site, agent, manager, script, test, and `.devflow` artifact/task/report areas. Future agents must not revert those unless explicitly asked.
