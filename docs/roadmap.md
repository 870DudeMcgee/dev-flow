# Roadmap

## Strategic Direction

Dev-Flow is a local-first control room for parallel AI coding workers.

Local checkout: use `<repo-root>` for portable command examples. This checkout is referred to as `DevFlow` in docs and handoffs. The old local path `/Users/jewelbait/Desktop/DevFlow` is quarantined and must not be used for current work.

The rebuild starts from a smaller foundation than the previous software-factory design:

- workers are replaceable
- state is sacred
- each task gets an isolated workspace
- visibility starts with CLI output and durable filesystem evidence
- context and results are durable artifacts
- autonomy is earned through reliability

Active specification: [docs/control-room-mvp.md](control-room-mvp.md)

Current product contract: [docs/mvp-contract.md](mvp-contract.md)

Current production hardening slice: [docs/architecture/git-native-worker-isolation-and-promotion.md](architecture/git-native-worker-isolation-and-promotion.md) and [docs/architecture/patch-application-and-readiness-gating.md](architecture/patch-application-and-readiness-gating.md)

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

Status: first human-controlled copy-promotion slice is active.

Acceptance:

- promotion preview is explicit
- promotion requires verified readiness and human confirmation
- promotion refuses a stale task baseline unless `--force-stale-baseline` is explicitly provided after review
- main checkout remains untouched until explicit human promotion
- copy-workspace promotion remains the default path; Git worktree promotion is available through `devflow task create --git-worktree`

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
- `doctor --strict` reports stale task locks, unsafe workspace paths, invalid derived/canonical JSON artifacts, missing logs, malformed manual-agent evidence, missing patch evidence, promoted-task consistency, and Git-native worker branch sharing across tasks
- `devflow reconcile` reports partial task/system event writes, task/system event divergence, interrupted promotion evidence, and inconsistent task artifacts without changing files
- `devflow init`, `devflow doctor --strict`, and shell task runs visibly warn that shell execution is path-isolated, not sandboxed

Remaining before production-grade local beta:

- design a cautious `devflow repair --dry-run` follow-up after strict reporting stays stable
- add installed-wheel CLI smoke tests in CI
- publish passing CI evidence before tags or releases
- harden the opt-in Git-native worker isolation and promotion slice
- keep patch application documented as text-only until complex diffs are delegated to a git-native path

## Phase 4e: Git-Native Worker Isolation And Promotion

Goal: move worker isolation from copied scratchpads to Git branches/worktrees while keeping Dev-Flow-owned state, verification evidence, and human-controlled promotion.

Status: initial opt-in vertical slice implemented. Design and remaining contract: [docs/architecture/git-native-worker-isolation-and-promotion.md](architecture/git-native-worker-isolation-and-promotion.md).

Required first contract:

```text
task_id: task-001
worker_id: codex-implementation
base_branch: main
base_commit: <sha>
worker_branch: devflow/task-001/codex-implementation
worktree_path: .devflow/worktrees/task-001/codex-implementation
head_commit: <sha>
dirty: true/false
```

Minimum vertical slice:

- create a worktree-backed task with `devflow task create --git-worktree`
- create a task branch from current `main` HEAD
- create `.devflow/worktrees/<task_id>/<worker_id>/`
- run the shell worker inside that worktree
- record base commit, worker branch, worktree path, HEAD, and dirty state
- run verification inside that worktree
- bind verification to the worker branch HEAD commit
- make `devflow task promote-preview` report base commit, current main HEAD, worker branch HEAD, merge-base, stale-baseline state, changed/deleted/renamed/untracked/binary files, conflict prediction, verification status, and promotion readiness
- make post-finalize UX explicit: `finalize --commit` reports the worker-branch commit and unchanged main, `task show` points to `promote-preview`, and `promote-preview` states it is read-only
- refuse promotion when worker HEAD differs from the verified commit
- refuse promotion when main moved and stale baseline or conflicts are unresolved
- promote with Git-aware mechanics instead of blind workspace copy-back, completing the approved merge cleanly without staged leftovers

Git evidence artifacts should live under `.devflow/tasks/<task_id>/workers/<worker_id>/` and include `git.json`, `diff.patch`, `diff-summary.json`, `verification.json`, and `promotion-preview.json`.

`doctor --strict` now checks Git integrity for worktree-backed tasks: worker branch existence, worktree existence, safe worktree paths, base commit existence, branch ancestry, unique worker branch claims across tasks, verified commit matching worker HEAD, and dirty worktree state after verification.

Cleanup and repair are now cautious and dry-run-first: `devflow task cleanup <task_id> --dry-run`, `devflow worktree list`, `devflow worktree prune --dry-run`, `devflow branch list`, and `devflow branch archive <branch> --dry-run`. Mutating cleanup uses `--apply` and keeps branch deletion out of scope by archiving task branches under `devflow/archive/`.

This milestone must not become a generic sandboxing detour, provider-adapter expansion, autonomous routing layer, or release automation project.

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

Status: The stable proof-agent slice is implemented for `devflow-manual-codex-worker`: registry show, bounded packet, manual handoff, and task show/dashboard evidence visibility. A legacy local Ollama advisory wrapper is implemented as `devflow task local` for Qwen/Qwopus/Gemma planning, scouting, and review evidence; it captures prompt, raw response, stderr, and run metadata under the task workspace without writing `proposal.patch` or applying model output. The registry-backed `devflow task run <task-id> --worker qwopus-implementer` path is active as the canonical local patch-proposal runtime: it writes bounded evidence and `proposal.patch`, while Dev-Flow applies, verifies, and gates promotion. Context packing and conservative routing remain experimental planning aids. Remote provider-backed execution is not active.

Sequence:
- architecture document only
- agent registry loading
- `agent list`, `agent show`, and `agent packet` commands
- manual proof-agent adapter
- shell adapter alignment
- deterministic task-fit and context-size estimation
- role-based context pack builder
- local Ollama advisory evidence wrapper for Qwen/Qwopus/Gemma (implemented as `task local`, not the canonical patch adapter)
- registry-backed Ollama patch adapter for `task run --worker qwopus-implementer`
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
- future local resource controls may add Ollama keep-alive or model-stop behavior, but the first local wrapper does not manage model memory

Related design contracts:
- [docs/architecture/agent-registry-and-adapter-runtime.md](architecture/agent-registry-and-adapter-runtime.md)
- [docs/architecture/agent-selection-and-context-routing.md](architecture/agent-selection-and-context-routing.md)
- [docs/architecture/patch-evidence-ladder.md](architecture/patch-evidence-ladder.md)
- [docs/adapter-contract.md](adapter-contract.md)
- [docs/task-packet-contract.md](task-packet-contract.md)

## Milestone 8A: Patch Evidence Ladder Documentation Alignment

Status: current documentation milestone.

Goal: align active documentation around the staged path from proposal evidence to patch review, patch dry-run preview, explicit isolated patch application, Dev-Flow-owned verification, promotion preview, and human-controlled promotion.

Acceptance:

- current patch dry-run behavior is documented as evidence only
- current, planned, and deferred behavior are clearly separated
- current Project Code Map orientation is documented
- current Idea Foundry local intake is documented separately
- no source, test, runtime, provider, dashboard, database, routing, or automation behavior changes are included

## Milestone 8B: Deterministic Patch Dry-run Preview

Status: implemented in commit `1acc4ce` according to milestone handoff and confirmed by current source/tests.

Command:

```bash
devflow task patch-dry-run <task-id>
devflow task patch-dry-run <task-id> --run-id <run-id>
```

Boundary: no mutation. Patch dry-run writes `patch-dry-run.json` and `patch-dry-run.md` evidence only and does not apply patches, verify, promote, stage, commit, call models, or call provider APIs.

## Milestone 9: Explicit Reviewed Patch Apply To Isolated Workspace

Status: implemented. Gating details and pre-conditions are documented in [docs/architecture/patch-application-and-readiness-gating.md](architecture/patch-application-and-readiness-gating.md).

Goal: harden explicit patch application so it requires fresh acceptable patch review and dry-run evidence before mutating the isolated task workspace.

Boundary: patch application remains the explicit mutation boundary. It must not imply verification or promotion readiness.

## Milestone 10: Verification/Readiness Hardening Around Applied Patches

Status: implemented. State transitions and gating logic are documented in [docs/architecture/patch-application-and-readiness-gating.md](architecture/patch-application-and-readiness-gating.md).

Goal: tighten verification and readiness evidence around applied patches while keeping verification separate from apply-patch and promotion.

Initial hardening slice: applying a reviewed patch invalidates prior verification evidence, resets promotion readiness to "not ready", and requires a fresh Dev-Flow verification run. Verification after an applied patch binds `verification.json` to the latest `patch-application.json` hash so stale pre-patch verification cannot satisfy readiness.

## Milestone 11: Project Code Map MVP

Status: implemented and dogfooded in Dev-Flow. The 11A contract, 11B `map init`, 11C `map show`, 11D `map check`, and 11E bounded `CODE_MAP.md` task-packet excerpt are complete.

Goal: introduce a compact project orientation layer, likely `CODE_MAP.md` with an optional `.code-map.yaml` companion, so workers can orient before broad repo scans.

Boundary: `CODE_MAP.md` is human-authored read-only orientation context. `.code-map.yaml` remains reserved future metadata. Routing and provider behavior remain out of scope.

## Milestone 12: Idea Foundry MVP

Status: implemented in the first local intake slice. Capture, list, show, classify, promote-decision, and archive commands are current; automatic goal/task creation remains out of scope.

Goal: capture raw ideas, classify them later, link them to project/goal context, and explicitly promote mature ideas into goals or tasks only after human review.

Boundary: Idea Foundry records intake and promotion decision evidence only. It does not create goals, create tasks, run workers, call providers, verify, commit, push, or promote code.

> [!IMPORTANT]
> **Next Priority**: Implement Milestone 13 from [docs/superpowers/specs/2026-06-13-idea-to-execution-bridge-design.md](superpowers/specs/2026-06-13-idea-to-execution-bridge-design.md) and [docs/superpowers/plans/2026-06-13-idea-to-execution-bridge.md](superpowers/plans/2026-06-13-idea-to-execution-bridge.md). Keep creation explicit and human-reviewed; do not add automatic creation during `idea promote`, provider-backed classification, or routing.

## Milestone 13: Idea-To-Execution Bridge

Status: planned; design and implementation plan are written, implementation is not started.

Goal: add explicit `devflow idea create-goal` and `devflow idea create-task` commands so a human-promoted idea can create linked Dev-Flow goal or task state.

Boundary: creation commands require prior idea promotion evidence, write bidirectional idea/goal or idea/task links, and stop. They do not run workers, call providers, verify, promote code, commit, push, open pull requests, or route models.

## Later, Not Now

- Aider adapter
- Hermes external operator/chat gateway over supervisor-safe commands; no Hermes runtime adapter or source-of-truth role
- OpenCode adapter
- dependency scheduler
- question resume flow
- protected path gates
- autonomous routing
- memory
- PR automation
