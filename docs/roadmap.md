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

Current product contract: [docs/mvp-contract.md](mvp-contract.md)

Next architecture direction: [docs/architecture/agent-registry-and-adapter-runtime.md](architecture/agent-registry-and-adapter-runtime.md), with future task-fit/context routing defined in [docs/architecture/agent-selection-and-context-routing.md](architecture/agent-selection-and-context-routing.md)

North Star: [PRODUCT_NORTH_STAR.md](../PRODUCT_NORTH_STAR.md)

Operating Model Boundaries:
- [docs/devflow-operating-model.md](devflow-operating-model.md) defines the role split between human, main chat/control-room agent, Dev-Flow kernel, worker agents, and DevMode.
- [docs/read-only-control-room-agent.md](read-only-control-room-agent.md) defines the main chat agent as read-only planner/spec/reviewer/coordinator.
- [docs/devmode-devflow-boundary.md](devmode-devflow-boundary.md) defines the boundary between DevMode discipline and Dev-Flow orchestration.


Legacy archive note: software-factory archive material is quarantined outside the active repository tree. The roadmap should not point future work at in-repo archive copies.

## Phase 0: Documentation Reset

Goal: stop the old workflow docs from steering future implementation.

Done when:

- legacy workflow docs are archived
- README, roadmap, handoff, AGENTS, and Copilot instructions point at the new MVP
- old active instruction hooks are removed or rewritten
- files to keep, bypass, create, and first patch are documented

## Phase 1: Shell-Worker Contract

Goal: keep the shell-worker task contract and docs/tests aligned.

Local development install:

```bash
.venv/bin/python -m pip install -e .
```

Commands:

```bash
devflow --help
devflow init
devflow doctor
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

Acceptance:

- stable task artifacts are created under `.devflow/tasks/<task_id>/`
- worker and verification logs are captured
- the command result stays in `.devflow/workspaces/<task_id>/`
- CLI shows task state from canonical `task.yaml` files
- editable install exposes the console script declared as `devflow = "devflow.cli:main"`
- text-only terminal dashboard reads canonical task state
- promotion preview and human-controlled promotion are available for verified tasks
- no SQLite database or `.devflow/worktrees/` directory is created

## Phase 2: Shell Worker Safety

Goal: keep the shell-worker path isolated and observable without adding new runtime surfaces.

Acceptance:

- command runs in the assigned workspace
- worker log is captured
- tampered workspace paths are refused
- symlinks are skipped during scratchpad copy
- main checkout is untouched by workers

## Phase 3: Visibility Surfaces

Goal: improve visibility while preserving filesystem-backed control-room state.

Acceptance:

- text-only terminal dashboard remains active and read-only
- browser UI, web dashboard, or frontend tooling requires a future contract change

## Phase 4: Workspace Promotion

Goal: keep work in the scratchpad workspace until the user explicitly approves promotion.

Status: first human-controlled promotion slice is active.

Acceptance:

- promotion preview is explicit
- promotion requires verified readiness and human confirmation
- promotion refuses a stale task baseline unless `--force-stale-baseline` is explicitly provided after review
- main checkout remains untouched until explicit human promotion
- git worktree orchestration remains out of scope

## Phase 4b: Manual Proof-Agent Truthfulness

Goal: make manual proof-agent state evidence-driven rather than keypress-driven.

Status: active for the stable proof-agent handoff.

Acceptance:

- manual handoff generation leaves tasks awaiting human evidence
- `task show` and `dashboard` distinguish awaiting human, blocked question, worker failure, and result-present evidence
- worker result evidence does not imply verification or promotion readiness
- pressing Enter in an interactive manual handoff does not mark work complete

## Phase 4c: Adapter Maturity Boundary

Goal: keep future adapter descriptions from becoming phantom runtime support.

Status: implemented and guarded by focused contract tests.

Acceptance:

- adapters are classified as `stable_runtime`, `experimental_readonly`, or `planned_not_executable`
- only `shell` and `manual` are executable stable-runtime adapters
- planned provider adapters fail clearly if task execution is attempted
- registry files are parsed with PyYAML and validated through Pydantic

## Phase 4d: Local Production Hardening

Goal: make the local single-user MVP more trustworthy without pretending it is a sandboxed general-purpose orchestrator.

Status: active hardening slice.

Implemented:

- package metadata uses [README.md](../README.md) as the public long description and identifies Dev-Flow as an alpha CLI product
- README and MVP contract state the trusted-local safety model and known limitations
- shell and verification subprocesses use process-group cleanup on POSIX timeout paths
- canonical task YAML/JSON artifacts use atomic write-then-replace for `task.yaml`, `summary.json`, `verification.json`, and `merge-readiness.json`
- patch application records real SHA-256 patch hashes, hash-addressed patch evidence artifacts, changed-file summaries, and latest patch application evidence
- `doctor --strict` reports stale task locks, unsafe workspace paths, invalid derived/canonical JSON artifacts, missing logs, malformed manual-agent evidence, missing patch evidence, and promoted-task consistency
- `devflow init`, `devflow doctor --strict`, and shell task runs visibly warn that shell execution is path-isolated, not sandboxed

Remaining before production-grade local beta:

- add read-only crash/interruption reconciliation reporting for partial event writes, interrupted promotion, and task/system event divergence
- design a cautious `devflow repair --dry-run` follow-up after strict reporting stays stable
- add installed-wheel CLI smoke tests in CI
- publish passing CI evidence before tags or releases
- decide whether the next workspace/promotion step is documented copy-promotion hardening or git worktree promotion
- keep patch application documented as text-only until complex diffs are delegated to a git-native path

## Dogfooding Requirement

Future implementation slices should use Dev-Flow shell tasks or local worker commands where practical. The purpose is to exercise task isolation, logs, verification evidence, dashboard visibility, promotion previews, and handoff quality while building Dev-Flow itself. This requirement does not authorize provider-backed adapters, autonomous routing, scheduling, databases, or old workflow machinery.

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

Status: outside the current runtime contract. A completed helper exists as visible planning guidance that recommends context strategy. It does not execute token tools, route models, install hooks, or change shell-worker, promotion, or verification behavior.

Acceptance:

- writes `.devflow/token-context/current.md`
- appends `.devflow/token-context/events.jsonl`
- records task description, mode, recommended tools, repo branch, git status, changed files, and task summaries
- gives explicit read-first and do-not-read guidance for IDE agents
- does not require token tools to be installed and does not enable hooks, MCP integrations, command rewrites, or autonomous routing

## Phase 7: Task Packet Projection

Goal: give future worker adapters a bounded, read-only task projection without making packets a new source of truth.

Status: first builder slice implemented in `src/devflow/control_room/task_packet.py`. It reads canonical task files, bounds recent events, tail-limits worker and verification logs, reports omitted counts/truncation notes, ignores missing, malformed, or conflicting `summary.json` cache data, and adds proof-agent role/permission/output fields for `devflow-manual-codex-worker`.

Acceptance:

- `task.yaml`, `events.jsonl`, `verification.json`, `worker.log`, and `verify.log` remain canonical
- `summary.json` is derived/cache only
- packet generation is read-only and file-based
- Codex is only supported through a human-launched manual handoff; no provider API or autonomous adapter is wired in

## Phase 8: Agent Registry And Adapter Runtime

Goal: make replaceable agents real by defining durable provider, agent, model capability, role, permission, adapter, workspace, evidence, task-fit, context, and routing contracts before enabling non-shell workers.

Status: The stable proof-agent slice is implemented for `devflow-manual-codex-worker`: registry show, bounded packet, manual handoff, and task show/dashboard evidence visibility. Context packing and conservative routing remain experimental planning aids. Full provider-backed execution is not active.

Sequence:
- architecture document only
- agent registry loading
- `agent list`, `agent show`, and `agent packet` commands
- manual proof-agent adapter
- shell adapter alignment
- deterministic task-fit and context-size estimation
- role-based context pack builder
- Ollama adapter for Qwen
- OpenAI-compatible adapter for LM Studio and Grok-style APIs
- native OpenAI, Anthropic, and Gemini adapters
- local scout reports as optional evidence
- routing engine
- metrics for local success rate, frontier escalations, verification failures, rework, useful context limits, and cost avoided

Acceptance:
- no agent owns canonical task state
- no provider secrets are stored in repo files
- manual and local paths work before remote provider calls
- routing records task-fit profile, context estimate, selected agents by role, rejected agents, reasons, mode, packet path, and policy version
- model selection uses capability profiles and useful context estimates instead of hard-coded agent names
- planners, workers, reviewers, verifiers, summarizers, and scouts receive role-specific context packs
- verification and promotion remain explicit Dev-Flow/human-controlled steps

Related design contracts:
- [docs/architecture/agent-registry-and-adapter-runtime.md](architecture/agent-registry-and-adapter-runtime.md)
- [docs/architecture/agent-selection-and-context-routing.md](architecture/agent-selection-and-context-routing.md)
- [docs/adapter-contract.md](adapter-contract.md)
- [docs/task-packet-contract.md](task-packet-contract.md)

> [!IMPORTANT]
> **Next Priority**: Keep focus on the shell-worker control room plus the stable manual proof-agent. Do not jump directly into provider-backed adapters, complex scheduling, web dashboards, autonomous routing, or legacy workflow machinery.

## Later, Not Now

- Aider adapter
- Hermes supervisor
- OpenCode adapter
- dependency scheduler
- question resume flow
- protected path gates
- autonomous routing
- memory
- PR automation
