# Agent Handoff

Date: 2026-05-27

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
- [docs/architecture/agent-registry-and-adapter-runtime.md](architecture/agent-registry-and-adapter-runtime.md) defines the next provider/agent/role registry and adapter runtime direction.
- [docs/architecture/agent-selection-and-context-routing.md](architecture/agent-selection-and-context-routing.md) defines the future task-fit, context-estimation, model-capability, context-pack, scout, and routing-quality design.


Archive note: legacy software-factory archives are quarantined outside the active repository tree. Do not recreate or consult in-repo archive copies as process authority.

## Product Boundary

Dev-Flow is not the main coding brain. It coordinates replaceable workers and owns durable state, process isolation, status, logs, questions, result bundles, verification evidence, and merge readiness.

The current milestone is a non-AI shell-worker control-room contract plus one manual proof-agent handoff for `devflow-manual-codex-worker`, with task creation, isolated execution/handoff, verification, visibility, and human-controlled promotion.

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
- `devflow dashboard`
- `devflow task --help`
- `devflow task create "title"`
- `devflow task list`
- `devflow task show <task_id>`
- `devflow task run <task_id> --worker shell -- /bin/sh -c "echo hello > result.txt"`
- `devflow task verify <task_id> --shell "test -f result.txt"`
- `devflow task packet <task_id>`
- `devflow agent show devflow-manual-codex-worker`
- `devflow agent packet <task_id> devflow-manual-codex-worker`
- `devflow task run <task_id> --worker devflow-manual-codex-worker`
- `devflow task log <task_id>`
- `devflow task apply-patch <task_id>` with SHA-256 patch evidence under `.devflow/tasks/<task_id>/patches/`
- `devflow task promote-preview <task_id>`
- `devflow task promote <task_id>`
- filesystem task state with canonical `task.yaml`
- atomic write-then-replace for canonical `task.yaml`, derived `summary.json`, latest `verification.json`, and `merge-readiness.json`
- task append-only `events.jsonl`
- task-local worker logs, verification logs, verification JSON, and YAML artifacts
- strict doctor read-only diagnostics for stale locks, unsafe workspace paths, invalid JSON artifacts, missing logs, malformed manual-agent evidence, missing patch evidence, and promoted-task consistency
- read-only reconciliation reporting for partial task/system event writes, task/system event divergence, interrupted promotion evidence, and inconsistent task artifacts
- copied scratchpad workspaces under `.devflow/workspaces/<task_id>/`
- verification command execution inside task workspaces
- POSIX process-group cleanup for shell and verification timeout paths
- `verified` and `verification_failed` task statuses from verification
- text-only terminal dashboard from canonical task artifacts
- human-controlled promotion preview and promotion from isolated workspaces
- no SQLite database or `.devflow/worktrees/` directory in the MVP path
- read-only `TaskPacket` builder in `src/devflow/control_room/task_packet.py`; it is a derived projection only and is consumed by the manual proof-agent handoff without becoming canonical state
- design-only Agent Registry and Adapter Runtime architecture; not active runtime behavior yet
- design-only task-fit/context routing architecture; not active runtime behavior yet
- trusted-local safety model only: shell execution is path-isolated in a copied workspace, not OS-sandboxed

## Required Current Commands

```bash
devflow --help
devflow init
devflow doctor
devflow reconcile
devflow dashboard
devflow task --help
devflow task create "example task"
devflow task run <task_id> --worker shell -- /bin/sh -c "echo hello > result.txt"
devflow task verify <task_id> --shell "test -f result.txt"
devflow task show <task_id>
devflow task list
devflow task packet <task_id>
devflow task log <task_id>
devflow task promote-preview <task_id>
devflow task promote <task_id>
```

## Implementation Posture

- Read the North Star before implementation decisions and use its Periodic Self-Check to catch product drift.
- Prefer direct implementation over ceremonial workflow.
- Do not create legacy task files for this rebuild.
- Do not route implementation through old agent, memory, context-pack, DAG, trace, eval, or unified-diff runner surfaces.
- Treat browser/web dashboards, token-context runtime routing, task-fit/context routing runtime, worktree orchestration, databases, and provider-backed worker adapters as outside the current contract unless a future implementation explicitly promotes them.
- Future non-shell worker work beyond `devflow-manual-codex-worker` must follow the registry sequence: shell alignment, deterministic task-fit/context estimation, context pack building, local adapter, provider adapters, routing, and metrics.
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

Create one shell task, run `echo hello > result.txt`, verify `test -f result.txt`, list it, show it, inspect the dashboard, preview promotion, and promote only after explicit human approval. Confirm `result.txt` exists only in `.devflow/workspaces/<task_id>/` before promotion, the task artifacts exist, no SQLite database is created, and no `.devflow/worktrees/` directory is created.

Current verification covers the command/filesystem/safety contract, copied workspace isolation, append-only events, verification logs, tampered workspace refusal, symlink skipping, dashboard projection, and promotion safety in the focused tests. Focused task-packet projection coverage lives in `tests/test_task_packet.py`.

## Known Worktree State At Handoff

Before this documentation reset, the repository already had unrelated dirty files in public-site, agent, manager, script, test, and `.devflow` artifact/task/report areas. Future agents must not revert those unless explicitly asked.
