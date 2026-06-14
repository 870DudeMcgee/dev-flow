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

Current completed hardening slices: [docs/architecture/git-native-worker-isolation-and-promotion.md](architecture/git-native-worker-isolation-and-promotion.md), [docs/architecture/patch-application-and-readiness-gating.md](architecture/patch-application-and-readiness-gating.md), Milestone 15 multi-project control-room hardening, and Milestone 16 agent registry runtime hardening.

Current follow-on boundary: model selection must stay registry-backed and model-agnostic. Dev-Flow may rank installed eligible agents for an explicit role and write Milestone 17 task-fit/context-routing evidence today, but autonomous best-model-for-any-task routing remains excluded until a later explicit autonomy policy promotes it.

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

Status: The stable proof-agent slice is implemented for `devflow-manual-codex-worker`: registry show, bounded packet, manual handoff, and task show/dashboard evidence visibility. A legacy local Ollama advisory wrapper is implemented as `devflow task local` for Qwen/Qwopus/Gemma planning, scouting, and review evidence; it captures prompt, raw response, stderr, and run metadata under the task workspace without writing `proposal.patch` or applying model output. The registry-backed local patch runtime is active for explicit patch agents such as `qwopus-implementer` and, when installed and selected by evidence, `gemma4-12b-qat-implementer`: it writes bounded evidence and `proposal.patch`, while Dev-Flow applies, verifies, and gates promotion. Milestone 16 added centralized runtime eligibility/refusal projection, role-scoped context-pack evidence, derived task-local agent evidence summaries, explicit local Ollama discovery/selection evidence, and local patch ladder dogfood. Milestone 17 added evidence-only task-fit, scout, route, and scorecard commands that write derived artifacts and recommended next commands only. Autonomous routing and remote provider-backed execution are not active.

Sequence:
- architecture document only
- agent registry loading
- `agent list`, `agent show`, and `agent packet` commands
- manual proof-agent adapter
- shell adapter alignment
- deterministic task-fit and context-size estimation (implemented as derived evidence through `task fit`)
- role-based context pack builder (implemented as derived evidence through `agent context-pack`)
- local Ollama advisory evidence wrapper for Qwen/Qwopus/Gemma (implemented as `task local`, not the canonical patch adapter)
- registry-backed Ollama patch adapter for explicit local patch workers such as `qwopus-implementer` and `gemma4-12b-qat-implementer`
- local scout reports as derived evidence (implemented through `task scout`)
- evidence-only routing decisions with candidate eligibility, rejections, unresolved roles, and recommended next commands (implemented through `task route`)
- routing-quality scorecards and escalation signals (implemented through `task scorecard`)
- OpenAI-compatible adapter for LM Studio and Grok-style APIs (future provider work)
- native OpenAI, Anthropic, and Gemini adapters (future provider work)
- autonomous routing engine that assigns or invokes workers (future autonomy work)
- metrics that drive autonomous policy, provider selection, or cost optimization beyond scorecard evidence (future autonomy work)

Acceptance:
- no agent owns canonical task state
- no provider secrets are stored in repo files
- manual and local paths work before remote provider calls
- routing records task-fit profile, context estimate, selected agents by role, rejected agents, reasons, mode, packet path, and policy version
- model selection uses capability profiles, installed-model evidence, useful context estimates, and explicit role policy instead of hard-coded agent names
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

Boundary: Idea Foundry promotion records intake and decision evidence only. Explicit goal/task creation is a separate Milestone 13 bridge command after prior promotion evidence. No Idea Foundry command runs workers, calls providers, verifies, commits, pushes, opens pull requests, routes models, or promotes code.

## Milestone 13: Idea-To-Execution Bridge

Status: implemented. Explicit `devflow idea create-goal` and `devflow idea create-task` commands now convert human-promoted ideas into linked goal or task state.

Goal: close the local-first path from human-reviewed idea intake to controlled Dev-Flow goal/task artifacts without making idea promotion automatic.

Boundary: creation requires matching prior `idea promote` evidence, writes bidirectional idea-to-goal/task links, and creates Dev-Flow state only. Idea creation commands do not run workers, call providers, verify, promote code, commit, push, open pull requests, or route models.

## Milestone 14: Goal Execution Control Loop

Status: implemented. Design and implementation planning history are preserved in [docs/superpowers/specs/2026-06-13-goal-execution-control-loop-design.md](superpowers/specs/2026-06-13-goal-execution-control-loop-design.md) and [docs/superpowers/plans/2026-06-13-goal-execution-control-loop.md](superpowers/plans/2026-06-13-goal-execution-control-loop.md).

Goal: make idea-created and manually created goals executable through explicit lifecycle state, freshness-loop recommendations, task-batch creation, shell worker batches, verification batches, review readiness, and human-controlled closure decisions.

Implemented: canonical `.devflow/goals/<goal_id>/goal-state.yaml`, hash-chained goal lifecycle events, `goal activate/pause/block/complete/archive`, lifecycle-aware `goal status` and `goal next`, freshness dispatch gating for non-active goals, closure-decision next actions after promoted task evidence, operating-layer lifecycle display, supervisor approval classification, and a dogfood test through task creation, shell worker batch, and verification batch.

Boundary: goal lifecycle and freshness execution commands do not call providers, route models, auto-promote, auto-commit, auto-push, open pull requests, or mark goals complete without explicit human command evidence.

## Milestone 14A: Goal Loop Hardening And Release Readiness

Status: complete closure slice. The evidence run blocks deferred Hermes goal `G-0001` instead of activating it into the next dispatch lane, runs bounded freshness checks, production-readiness dogfood, full pytest, stale-context scan, operating-layer visual QA, and release-readiness gates.

Goal: dogfood the Milestone 14 goal loop against live Dev-Flow state and close the milestone with explicit release-readiness evidence.

Boundary: this is not a feature expansion. It does not implement provider adapters, autonomous routing, multi-project UI work, Hermes runtime behavior, automatic promotion, automatic commits, automatic pushes, pull requests, or automatic goal completion.

## Milestone 15: Multi-Project Control Room Hardening

Status: implemented and dogfooded. Milestone 15 cleaned stale global registry behavior, aligned missing-project diagnostics around `project doctor`, preserved project-local `.devflow/` authority, and improved multi-project freshness/status/dashboard behavior. Milestone 15B then created a durable real project at `/Users/josh/DevFlow Projects/milestone-15b-dogfood-project`, required an explicit local Git baseline before project-scoped task creation, ran a verified project-scoped shell task, promoted it, and pushed CI-fixing evidence through `main`.

Goal: make the existing multi-project registry, status, freshness, and dashboard surfaces reliable enough for the next control-room workflow.

Closure evidence:

- `DEVFLOW_HOME=/Users/josh/.devflow PYTHONPATH=src:. .venv/bin/devflow freshness run --all-projects --max-iterations 1 --json` checks the durable project registry without the old stale-path blocker.
- `task create --project` refuses unborn managed Git projects until a project-local baseline commit exists, so promotion previews and copied workspaces have a real baseline.
- GitHub Actions CI passed on `301869c86ad566b2728e1e9adaf4206fb08f863c` after the project-baseline review-readiness fixture was made CI-safe.

Boundary: this slice should not add provider-backed workers, autonomous routing, old workflow machinery, databases, or PR automation. It should preserve project-local `.devflow/` authority and human-controlled publication.

## Milestone 16: Agent Registry Runtime Hardening

Status: implemented and dogfooded. Design, implementation plan, and repair-plan evidence live in [docs/superpowers/specs/2026-06-13-milestone-16-agent-registry-runtime-hardening-design.md](superpowers/specs/2026-06-13-milestone-16-agent-registry-runtime-hardening-design.md), [docs/superpowers/plans/2026-06-13-milestone-16-agent-registry-runtime-hardening.md](superpowers/plans/2026-06-13-milestone-16-agent-registry-runtime-hardening.md), and [docs/superpowers/plans/2026-06-14-gemma-native-patch-output-reliability.md](superpowers/plans/2026-06-14-gemma-native-patch-output-reliability.md).

Goal: make the existing agent registry and current executable worker paths behave like one permissioned runtime contract before any remote provider execution is promoted.

Implemented:

- centralize runtime eligibility, execution-surface, and refusal decisions for shell, manual, registry-backed local patch, and read-only local worker-pool profiles
- add role-scoped context pack evidence built from canonical task packets
- normalize current worker evidence summaries so shell, manual, local patch, and local model evidence can be inspected through one derived projection
- dogfood the current local patch ladder through explicit local-agent selection, patch proposal generation, review, dry-run, and refusal-safe application gates without provider calls
- document that local model selection is model-agnostic: installed-model discovery and selected-agent evidence choose eligible profiles by role, while autonomous best-model-for-any-task routing remains excluded beyond the implemented Milestone 17 evidence-only routing commands
- update active docs so Milestone 16 is a completed hardening slice, not a remote-provider or autonomous-routing launch

Boundary: this milestone must not enable OpenAI, Anthropic, Gemini, xAI, LM Studio, or OpenAI-compatible remote execution through stable task runs. It must not add autonomous routing, PR automation, hidden memory, database state, or worker-owned verification/promotion.

## Milestone 17: Task-Fit Context Routing Evidence

Status: implemented. Design and implementation plan live in [docs/superpowers/specs/2026-06-14-milestone-17-task-fit-context-routing-design.md](superpowers/specs/2026-06-14-milestone-17-task-fit-context-routing-design.md) and [docs/superpowers/plans/2026-06-14-milestone-17-task-fit-context-routing-evidence.md](superpowers/plans/2026-06-14-milestone-17-task-fit-context-routing-evidence.md).

Goal: promote deterministic task-fit, context estimation, scout, routing, and routing-quality artifacts into an explicit evidence-only control-room slice.

Boundary: this milestone must not add autonomous routing, automatic worker execution, remote provider API calls, silent model substitution, worker-owned verification/promotion, commits, pushes, pull requests, hidden memory, vector search, RAG, embeddings, or training. Routing decisions may recommend next commands, but humans or explicit dogfood lanes still invoke execution.

## Later, Not Now

- Aider adapter
- Hermes external operator/chat gateway over supervisor-safe commands; no Hermes runtime adapter or source-of-truth role
- OpenCode adapter
- dependency scheduler
- question resume flow
- protected path gates
- autonomous routing beyond read-only projections and explicit human commands
- memory
- PR automation
