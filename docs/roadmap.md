# Roadmap

## Strategic Direction

Dev-Flow is a local-first control room for parallel AI coding workers.

The rebuild starts from a smaller foundation than the previous software-factory design:

- workers are replaceable
- state is sacred
- each task gets an isolated workspace
- visibility starts with CLI output and durable filesystem evidence
- context and results are durable artifacts
- autonomy is earned through reliability

Active specification: [docs/control-room-mvp.md](control-room-mvp.md)

Frozen MVP contract: [docs/mvp-contract.md](mvp-contract.md)

North Star: [PRODUCT_NORTH_STAR.md](../PRODUCT_NORTH_STAR.md)

Legacy archive: [docs/archive/legacy-devflow-software-factory-2026-05-27/README.md](archive/legacy-devflow-software-factory-2026-05-27/README.md)

## Phase 0: Documentation Reset

Goal: stop the old workflow docs from steering future implementation.

Done when:

- legacy workflow docs are archived
- README, roadmap, handoff, AGENTS, and Copilot instructions point at the new MVP
- old active instruction hooks are removed or rewritten
- files to keep, bypass, create, and first patch are documented

## Phase 1: Frozen Shell-Worker Contract

Goal: freeze the smallest shell-worker task contract and keep docs/tests aligned with it.

Local development install:

```bash
.venv/bin/python -m pip install -e .
```

Commands:

```bash
devflow --help
devflow task --help
devflow task create "example task"
devflow task run <task_id> --shell "echo hello > result.txt"
devflow task verify <task_id> --shell "test -f result.txt"
devflow task show <task_id>
devflow task list
```

Acceptance:

- stable task artifacts are created under `.devflow/tasks/<task_id>/`
- worker and verification logs are captured
- the command result stays in `.devflow/workspaces/<task_id>/`
- CLI shows task state from canonical `task.yaml` files
- editable install exposes the console script declared as `devflow = "devflow.cli:main"`
- no SQLite database or `.devflow/worktrees/` directory is created

## Phase 2: Shell Worker Safety

Goal: keep the shell-worker path isolated and observable without adding new runtime surfaces.

Acceptance:

- command runs in the assigned workspace
- worker log is captured
- tampered workspace paths are refused
- symlinks are skipped during scratchpad copy
- main checkout is untouched by workers

## Phase 3: Future Visibility Surfaces

Goal: improve visibility after the frozen command/filesystem/safety contract remains stable.

Acceptance:

- any dashboard or richer UI is proposed as a new contract change
- no browser UI, terminal dashboard, or frontend tooling is part of the frozen MVP

## Phase 4: Future Workspace Promotion

Goal: decide how work leaves the scratchpad workspace when the user explicitly approves it.

Status: out of the frozen MVP. Current shell-worker results remain in `.devflow/workspaces/<task_id>/`.

Acceptance:

- copy-back or promotion is explicit
- main checkout remains untouched until that future feature is designed
- git worktree orchestration remains out of scope

## Phase 5: Verification And Merge Readiness

Goal: make Dev-Flow own verification evidence before work can be considered merge-ready.

Status: first slice implemented with:

```bash
devflow task verify <task_id> --shell "test -f result.txt"
```

Acceptance:

- verification runs inside the task workspace
- `logs/verify.log` is written
- CLI shows verification status
- successful verification marks the task `verified`; failed verification marks it `verification_failed`

## Phase 6: Token Context Packet

Goal: help IDE agents use the smallest sufficient context without making Dev-Flow a coding agent.

Status: outside the frozen MVP contract. A completed helper exists as visible planning guidance that recommends context strategy. It does not execute token tools, route models, install hooks, or change shell-worker, merge, or verification behavior.

Acceptance:

- writes `.devflow/token-context/current.md`
- appends `.devflow/token-context/events.jsonl`
- records task description, mode, recommended tools, repo branch, git status, changed files, and task summaries
- gives explicit read-first and do-not-read guidance for IDE agents
- does not require token tools to be installed and does not enable hooks, MCP integrations, command rewrites, or model routing

## Phase 7: Task Packet Projection

Goal: give future worker adapters a bounded, read-only task projection without making packets a new source of truth.

Status: first builder slice implemented in `src/devflow/control_room/task_packet.py`. It reads canonical task files, bounds recent events, tail-limits worker and verification logs, reports omitted counts/truncation notes, and ignores missing, malformed, or conflicting `summary.json` cache data. No adapter consumes it yet.

Acceptance:

- `task.yaml`, `events.jsonl`, `verification.json`, `worker.log`, and `verify.log` remain canonical
- `summary.json` is derived/cache only
- packet generation is read-only and file-based
- Codex is not wired in

> [!IMPORTANT]
> **Next Priority**: Return focus back to the frozen shell-worker MVP: task lifecycle, workspace isolation, CLI visibility, verification, and future merge readiness.

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
