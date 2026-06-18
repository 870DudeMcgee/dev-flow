# Patch Evidence Ladder

Status: Current runtime alignment plus future roadmap. This document distinguishes implemented behavior from planned future milestones. Treat commands and artifacts as current only when source code and tests confirm them.

## Purpose

Dev-Flow uses a staged, inspectable, evidence-preserving path from worker/model output to reviewed patch candidate to dry-run preview to explicit isolated application to verification to human-controlled promotion.

This ladder exists because:

- model output must not directly mutate source
- patch candidates need review before application
- dry-run preview answers "what would happen?" before mutation
- patch application must be explicit and isolated
- verification must remain separate from patch application
- promotion must remain separate from verification
- humans control promotion to main

Dev-Flow is a local-first control room for AI coding workers. It is not the coding intelligence itself. Workers and models are replaceable. Filesystem state is sacred. Visibility is mandatory. Isolation comes before autonomy. Model output is evidence, not authority.

## Non-Negotiable Boundary

Patch dry-run preview must not:

- apply patches
- modify source files
- modify isolated workspace files
- stage files
- commit files
- run verification
- promote
- auto-route
- schedule work
- call local models
- call remote models
- call provider APIs
- alter registries
- add a database
- add a web dashboard beyond the approved local operating layer
- add a TUI dashboard
- perform background automation

Patch dry-run preview is evidence only.

## Current Runtime Context

Current runtime facts confirmed by source, tests, and active docs:

- Dev-Flow stores durable state under `.devflow/`.
- `.devflow/tasks/<task-id>/task.yaml` is canonical current task state.
- `.devflow/tasks/<task-id>/events.jsonl` is append-only task evidence.
- `.devflow/tasks/<task-id>/verification.json` stores the latest verification result.
- Worker logs are command evidence.
- Proposal artifacts are evidence.
- Patch review artifacts are evidence.
- Patch dry-run artifacts are evidence.
- Patch application writes durable evidence.
- `devflow task apply-patch` is the explicit mutation step for current patch application.
- `devflow task patch-dry-run` is implemented and covered by focused tests.
- `devflow task verify` is separate from patch application.
- `devflow task promote-preview` is separate from verification.
- `devflow task promote` is explicit and human-controlled.
- Default task workspaces live under `.devflow/workspaces/<task-id>/`.
- Opt-in Git-native shell task lanes are current through `devflow task create --git-worktree`, with worktrees under `.devflow/worktrees/<task-id>/shell/`.
- Patch parsing, touched-file extraction, path-risk classification, and workspace target resolution are centralized in `src/devflow/control_room/patch_proposal.py`. Patch review, patch dry-run, and patch apply delegate to that shared module instead of carrying separate parsing/path policy logic.

Current copy-workspace tasks and Git-native worktree tasks are both isolated task lanes. The default path is the copy workspace. The Git-native shell-worker path is opt-in and records Git facts, branch/worktree evidence, commit-bound verification, and Git-aware promotion readiness.

## Ladder Overview

```text
Idea Foundry intake, current
-> Goal / task planning
-> Project Code Map orientation, current
-> Bounded task packet
-> Worker/model evidence
-> Normalized proposal evidence
-> Patch candidate
-> Patch review
-> Patch dry-run preview
-> Explicit patch apply to isolated workspace
-> Dev-Flow-owned verification
-> Promotion preview
-> Human-controlled promotion
```

Patch dry-run is current implemented behavior. Project Code Map is the current upstream orientation layer through `CODE_MAP.md` and `devflow map init/show/check`.

Idea Foundry is the current local intake layer through `devflow idea capture/list/show/classify/promote/create-goal/create-task/archive`. It records raw idea evidence, human classification, and decision-only promotion notes under `.devflow/ideas/`; explicit bridge commands can then create linked goal/task state after prior promotion evidence. Idea creation commands do not run workers, call providers, verify, promote code, commit, push, open pull requests, or route models.

## Stage-by-Stage Contract

### A. Goal / Task Planning

Purpose: Turn selected work into a bounded task.

Status: Current for task creation and current stable evidence-only planning, scouting, routing, and scorecard helpers documented in the current contract. `devflow task pack` remains experimental-read-only.

Command surface:

- Current: `devflow task create`
- Current: `devflow task create --git-worktree`
- Stable evidence-only/manual planning aids: `devflow task fit`, `devflow task scout`, `devflow task route`, `devflow task scorecard`
- Experimental-read-only/manual planning aid: `devflow task pack`

Artifact surface:

- `.devflow/tasks/<task-id>/task.yaml`
- `.devflow/tasks/<task-id>/events.jsonl`
- optional generated packet/projection artifacts

Mutation and state:

- `task create` creates task state and workspace/worktree artifacts.
- Planning/scouting/routing helpers are not autonomous execution and must not become autonomous execution unless explicitly promoted by a later contract.

Type: Planning and task-state creation.

Human review boundary: A human chooses the work and controls when planning becomes execution.

### B. Project Code Map Orientation, Current

Purpose: Give workers a compact project orientation before scanning the repo.

Status: Current orientation layer.

Current files:

- `CODE_MAP.md`
- optionally `.code-map.yaml`

Current CLI:

- `devflow map init`
- `devflow map show`
- `devflow map check`

Mutation and state: Map commands create or inspect map files only. The map is read-only context for task packets and does not mutate task state.

Type: Current orientation context.

Human review boundary: Workers should read `CODE_MAP.md` before scanning the repo. Workers should propose map updates through task evidence instead of directly editing `CODE_MAP.md` unless explicitly authorized.

Boundary: Do not expand this layer here. Do not add provider calls, routing, autonomous execution, or promotion decisions to map behavior.

### C. Bounded Task Packet

Purpose: Give a worker enough context to act without flooding it with generated artifacts or stale evidence.

Status: Current. `src/devflow/control_room/task_packet.py` builds read-only task projections and excludes generated/recursive evidence.

Command surface:

- Current: `devflow task packet <task-id>`
- Current proof-agent packet: `devflow agent packet <task-id> devflow-manual-codex-worker`
- Experimental role pack: `devflow task pack <task-id> <role>`

Artifact surface:

- Dynamic task packet projection.
- Optional `.devflow/tasks/<task-id>/packet.json` derived state.
- Proof-agent packet/handoff evidence under `.devflow/tasks/<task-id>/agents/devflow-manual-codex-worker/`.

Generated artifact exclusion rule:

Default packets should exclude generated or recursive evidence such as:

- `local-model-runs/**`
- `proposal.md`
- `proposal.json`
- `proposal.patch`
- `patch-review.md`
- `patch-review.json`
- `patch-dry-run.md`
- `patch-dry-run.json`
- `logs/**`
- `raw_output.md`
- `run.json`
- `request.json`
- `response.json`
- `prompt.md`
- `response.md`
- `.pytest_cache/**`
- `__pycache__/**`
- `node_modules/**`
- `dist/**`
- `build/**`
- virtualenv folders such as `.venv/**` and `.venv-*/**`

Mutation and state: Packet generation is read-only or writes derived evidence only. It does not replace canonical `task.yaml`, `events.jsonl`, or `verification.json`.

Type: Evidence/context projection.

Human review boundary: Generated artifacts must not become default context unless explicitly reviewed and included by contract.

### D. Worker/Model Evidence

Purpose: Capture raw worker/model output as durable evidence.

Status: Current.

Command surface:

- Current code-changing shell worker: `devflow task run <task-id> --worker shell -- <command>`
- Current registry-backed local patch proposal worker: `devflow task run <task-id> --worker qwopus-implementer`
- Current legacy local advisory evidence wrapper: `devflow task local <task-id> --agent <agent-id>`
- Current manual proof-agent handoff: `devflow task run <task-id> --worker devflow-manual-codex-worker`

Artifact surface:

- Shell worker logs under task log paths.
- Registry-backed Qwopus evidence under `.devflow/tasks/<task-id>/agents/qwopus-implementer/`.
- Legacy local Ollama advisory evidence under `.devflow/workspaces/<task-id>/local-workers/<worker-name>/`.

Mutation and state:

- Shell worker mutates only its assigned isolated workspace/worktree.
- `qwopus-implementer` patch proposal output writes evidence only and does not edit, verify, or promote.
- Legacy local advisory commands write prompt/response evidence only and do not write `proposal.patch`.

Type: Worker/model evidence.

Human review boundary: Model output must not be treated as authority.

### E. Normalized Proposal Evidence

Purpose: Convert raw model/worker output into structured proposal evidence that Dev-Flow can inspect.

Status: Current for normalized local-model run proposal evidence and current for registry-backed Qwopus `proposal.patch` evidence.

Command surface:

- Current normalized local proposal path is surfaced by current CLI proposal/review commands.
- Current registry-backed patch proposal: `devflow task run <task-id> --worker qwopus-implementer`.

Artifact surface:

- `.devflow/tasks/<task-id>/local-model-runs/<run-id>/proposal.md`
- `.devflow/tasks/<task-id>/local-model-runs/<run-id>/proposal.json`
- `.devflow/tasks/<task-id>/local-model-runs/<run-id>/proposal.patch`
- `.devflow/tasks/<task-id>/agents/<agent-id>/proposal.patch`

Mutation and state: Proposal evidence does not apply patches, verify, or promote.

Type: Evidence.

Human review boundary: A proposal patch is not applied automatically. Proposal evidence does not equal verification or promotion readiness.

### F. Patch Candidate

Purpose: Represent a candidate unified diff that may be reviewed, dry-run, and explicitly applied later.

Status: Current.

Artifact surface:

- `proposal.patch` under normalized local-model run evidence.
- `proposal.patch` under agent evidence, including the current `qwopus-implementer` path.

Mutation and state: A patch candidate is evidence only.

Type: Evidence.

Human review boundary: Patch candidates require review. Dangerous paths and generated artifacts must be rejected or flagged by review/application layers. Patch candidates should remain isolated in task/worker/run evidence folders.

### G. Patch Review

Purpose: Inspect patch candidate risk before dry-run or application.

Status: Current. `src/devflow/control_room/patch_review.py` writes review evidence for normalized local-model runs.

Command surface:

- Current: `devflow task review-patch <task-id>`
- Current: `devflow task review-patch <task-id> --run-id <run-id>`

Artifact surface:

- `.devflow/tasks/<task-id>/local-model-runs/<run-id>/patch-review.json`
- `.devflow/tasks/<task-id>/local-model-runs/<run-id>/patch-review.md`

Current review statuses:

- `no_patch_candidate`
- `invalid_patch`
- `dangerous_patch`
- `review_required`
- `low_risk_candidate`
- `unknown`

Current risk values:

- `low`
- `medium`
- `high`
- `critical`
- `unknown`

Mutation and state: Patch review writes review evidence only.

Type: Evidence/gate.

Human review boundary: Patch review must not apply changes, verify, promote, or replace human review. Patch review is a gate before dry-run and application.

### H. Patch Dry-run Preview

Purpose: Answer: "If this reviewed `proposal.patch` candidate were applied to the isolated task workspace, what would happen?"

Status: Current implemented behavior.

Current command:

- `devflow task patch-dry-run <task-id>`
- `devflow task patch-dry-run <task-id> --run-id <run-id>`

Current inputs:

- `task.yaml`
- `proposal.patch`
- `patch-review.json`
- isolated task workspace

Current outputs:

- `.devflow/tasks/<task-id>/local-model-runs/<run-id>/patch-dry-run.json`
- `.devflow/tasks/<task-id>/local-model-runs/<run-id>/patch-dry-run.md`

Current behavior:

- selects the latest reviewed local-model run deterministically when `--run-id` is omitted
- reads `proposal.patch`
- reads `patch-review.json`
- inspects the isolated task workspace from `task.yaml`
- parses unified diff enough to evaluate hunk applicability
- reports clean, missing, conflict, dangerous/rejected, invalid, and workspace-missing states
- writes dry-run evidence only
- surfaces latest dry-run evidence in `task show`
- never mutates source or workspace files
- never verifies
- never promotes
- never stages
- never commits
- never calls models
- never calls network APIs

Current dry-run statuses:

- `would_apply_cleanly`
- `would_create_files`
- `would_modify_with_warnings`
- `missing_target_file`
- `hunk_mismatch`
- `rejected_by_patch_review`
- `invalid_patch`
- `workspace_missing`

`dangerous_patch`, `invalid_patch`, and `no_patch_candidate` review statuses map to `rejected_by_patch_review`. `unknown` is a current risk value and fallback display value; it is not a current dry-run status.

Current risk values:

- `low`
- `medium`
- `high`
- `critical`
- `unknown`

Mutation and state: Patch dry-run writes dry-run artifacts under the selected local-model run only. It does not change canonical `task.yaml`, latest `verification.json`, source files, workspace files, Git index, commits, verification state, or promotion state.

Type: Evidence.

Human review boundary: Dry-run is not patch application, verification, or promotion readiness. Dry-run evidence makes later explicit patch application safer, more visible, and easier to review.

### I. Explicit Patch Apply to Isolated Workspace

Purpose: Apply a reviewed and dry-run-checked patch only after explicit human command.

Status: Current. Milestone 9 hardening requires matching fresh acceptable patch review and dry-run evidence before mutation.

Command surface:

- Current: `devflow task apply-patch <task-id> --agent <agent-id>`
- Current: `devflow task apply-patch <task-id> --run-id <run-id>`

Artifact surface:

- `.devflow/tasks/<task-id>/patch-application.json`
- `.devflow/tasks/<task-id>/patches/<patch-hash>.json`
- `patch_applied` events in `.devflow/tasks/<task-id>/events.jsonl`

Mutation and state: Patch apply mutates the isolated task workspace and writes durable patch application evidence. Current patch application supports validated text patches, records the matching review and dry-run evidence paths, and rejects unsupported complex metadata.

Type: Mutation.

Human review boundary: Patch apply must remain explicit and isolated. Patch apply does not equal verification or promotion.

### J. Verification

Purpose: Dev-Flow evaluates whether the changed workspace satisfies the task's verification command or evidence requirements.

Status: Current.

Command surface:

- Current: `devflow task verify <task-id> --shell "<command>"`

Artifact surface:

- `.devflow/tasks/<task-id>/verification.json`
- `.devflow/tasks/<task-id>/logs/verify.log`
- Git-native worker verification artifacts for `--git-worktree` tasks

Mutation and state: Verification writes verification evidence and canonical task verification fields. It runs separately from patch application.

Type: Verification.

Human review boundary: Verification is Dev-Flow-owned. Worker/model output does not self-certify verification.

### K. Promotion Preview

Purpose: Show what promotion would do before changing the main checkout or target branch.

Status: Current.

Command surface:

- Current: `devflow task promote-preview <task-id>`

Artifact surface:

- Current promotion/readiness summaries and Git-native `promotion-preview.json` evidence where applicable.

Mutation and state: Promotion preview is a readiness/evidence surface and not promotion.

Type: Evidence/readiness.

Human review boundary: Promotion preview should be reviewed by a human.

### L. Human-Controlled Promotion

Purpose: Move verified task results into the main checkout/branch only after explicit human command.

Status: Current.

Command surface:

- Current: `devflow task promote <task-id>`

Mutation and state: Promotion mutates the main checkout/target branch only after explicit command and readiness checks.

Type: Promotion.

Human review boundary: Promotion is human-controlled, readiness-gated, and must not be automatic.

## Artifact Map

| Artifact | Current/Future | Owner | Meaning | Mutating? | Notes |
| --- | --- | --- | --- | --- | --- |
| `.devflow/tasks/<task-id>/task.yaml` | Current | Dev-Flow | Canonical task state | Yes, by Dev-Flow | Source of current task state |
| `.devflow/tasks/<task-id>/events.jsonl` | Current | Dev-Flow | Append-only task evidence | Yes, append-only | Event history |
| `.devflow/tasks/<task-id>/verification.json` | Current | Dev-Flow | Latest verification result | Yes, by verify | Separate from apply and promote |
| `.devflow/tasks/<task-id>/patch-application.json` | Current | Dev-Flow | Latest patch application pointer | Yes, by apply-patch | Mutation evidence |
| `.devflow/tasks/<task-id>/patches/<patch-hash>.json` | Current | Dev-Flow | Hash-addressed patch application evidence | Yes, by apply-patch | Records changed files and patch hash |
| `.devflow/tasks/<task-id>/agents/<agent-id>/proposal.patch` | Current | Worker/Dev-Flow evidence | Agent patch candidate | No source mutation | Current for `qwopus-implementer` |
| `.devflow/tasks/<task-id>/agents/<agent-id>/raw_output.md` | Current | Worker evidence | Raw model/worker output | No source mutation | Evidence only |
| `.devflow/tasks/<task-id>/agents/<agent-id>/run.json` | Current | Worker evidence | Run metadata | No source mutation | Evidence only |
| `.devflow/tasks/<task-id>/agents/<agent-id>/logs/worker.log` | Current | Worker evidence | Worker log | No source mutation | Evidence only |
| `.devflow/tasks/<task-id>/local-model-runs/<run-id>/proposal.md` | Current | Dev-Flow evidence | Normalized proposal prose | No source mutation | Evidence only |
| `.devflow/tasks/<task-id>/local-model-runs/<run-id>/proposal.json` | Current | Dev-Flow evidence | Normalized proposal metadata | No source mutation | Evidence only |
| `.devflow/tasks/<task-id>/local-model-runs/<run-id>/proposal.patch` | Current | Dev-Flow evidence | Candidate unified diff | No source mutation | Reviewed/dry-run before application |
| `.devflow/tasks/<task-id>/local-model-runs/<run-id>/patch-review.md` | Current | Dev-Flow evidence | Human-readable patch review | No source mutation | Review evidence only |
| `.devflow/tasks/<task-id>/local-model-runs/<run-id>/patch-review.json` | Current | Dev-Flow evidence | Patch review result | No source mutation | Gate before dry-run |
| `.devflow/tasks/<task-id>/local-model-runs/<run-id>/patch-dry-run.md` | Current | Dev-Flow evidence | Human-readable dry-run preview | No source mutation | Evidence only |
| `.devflow/tasks/<task-id>/local-model-runs/<run-id>/patch-dry-run.json` | Current | Dev-Flow evidence | Structured dry-run preview | No source mutation | Evidence only |
| `.devflow/workspaces/<task-id>/` | Current | Dev-Flow/worker lane | Default isolated task workspace | Yes, by assigned workers/apply/verify artifacts | Main checkout remains separate until promotion |
| `.devflow/worktrees/<task-id>/shell/` | Current opt-in | Dev-Flow/worker lane | Git-native shell task worktree | Yes, by assigned shell worker | Only for `--git-worktree` tasks |
| `CODE_MAP.md` | Current | Human/Dev-Flow | Project orientation map | Read-only context | Managed by `devflow map init/show/check` |
| `.code-map.yaml` | Future | Human/Dev-Flow | Optional machine-readable map companion | Future | No current command |
| `.devflow/ideas/<idea-id>/idea.json` | Current | Human/Dev-Flow | Idea metadata | Intake evidence only | Project-local Idea Foundry |
| `.devflow/ideas/<idea-id>/raw.md` | Current | Human/Dev-Flow | Raw captured idea | Intake evidence only | Project-local Idea Foundry |
| `.devflow/ideas/<idea-id>/classification.md` | Current | Human/Dev-Flow | Idea classification evidence | Intake evidence only | Project-local Idea Foundry |
| `.devflow/ideas/<idea-id>/promotion.md` | Current | Human/Dev-Flow | Idea promotion decision | Decision evidence only | Does not create goals/tasks |
| `.devflow/ideas/<idea-id>/goal-brief.md` | Current | Dev-Flow | Goal source brief from idea | Goal creation input only | Requires prior goal promotion |
| `.devflow/ideas/<idea-id>/task-brief.md` | Current | Dev-Flow | Task source brief from idea | Task creation input only | Requires prior task promotion |
| `.devflow/ideas/<idea-id>/events.jsonl` | Current | Dev-Flow | Idea event evidence | Append-only evidence | Project-local Idea Foundry |
| `.devflow/goals/<goal-id>/idea-link.yaml` | Current | Dev-Flow | Link from goal back to idea | Link evidence only | Created by `idea create-goal` |
| `.devflow/tasks/<task-id>/idea.md` | Current | Dev-Flow | Task brief copied from idea | Task context only | Created by `idea create-task` |
| `.devflow/tasks/<task-id>/idea-link.yaml` | Current | Dev-Flow | Link from task back to idea | Link evidence only | Created by `idea create-task` |

## Relationship to Existing task apply-patch

The existing patch application path remains the explicit mutation boundary. Patch dry-run preview sits before patch application and does not replace the patch applier. Apply-patch now refuses mutation unless the selected patch has matching fresh acceptable review and dry-run evidence.

## Relationship to Verification

Patch dry-run is not verification. Dry-run answers whether a patch appears applicable to the isolated workspace. Verification answers whether the resulting workspace satisfies the task's verification command or evidence requirements. These must remain separate.

## Relationship to Promotion

Patch review, patch dry-run, patch application, and verification do not automatically promote work. Promotion remains explicit, readiness-gated, and human-controlled.

## Future Context Intake Roadmap

### Project Code Map, Current

Purpose: Give every worker a fast orientation layer before task execution so agents waste fewer tokens rediscovering the repo and are less likely to edit the wrong files.

Planned files:

- `CODE_MAP.md`
- `.code-map.yaml`, optional future machine-readable companion

Suggested `CODE_MAP.md` sections:

- Project Purpose
- Read This First
- Core Areas
- Common Workflows
- Files to Avoid
- Architecture Rules
- Verification Commands
- Map Maintenance Rules

Current commands:

- `devflow map init`
- `devflow map show`
- `devflow map check`

Current behavior:

- `devflow task packet` includes a bounded `CODE_MAP.md` excerpt if it exists
- worker instructions should tell the worker to read `CODE_MAP.md` before broad repo scanning
- if `CODE_MAP.md` is missing, Dev-Flow continues safely and `devflow map check` clearly says no code map exists
- workers should propose map updates inside task evidence rather than silently editing the map
- agents must not directly edit `CODE_MAP.md` unless the task explicitly grants that permission

Boundary: Do not expand Project Code Map as part of patch dry-run work. It remains human-authored read-only orientation context and must not route models, call providers, mutate task state, or make promotion decisions.

### Idea Foundry, Current Local Intake

Purpose: Capture raw ideas, classify them later, link them to product/project/goal context, and explicitly promote mature ideas into goals or tasks only after human review.

Current commands:

- `devflow idea capture "<text>"`
- `devflow idea list`
- `devflow idea show <idea_id>`
- `devflow idea classify <idea_id> --maturity goal_ready`
- `devflow idea promote <idea_id> --to goal --rationale "human reviewed"`
- `devflow idea create-goal <idea_id> --dry-run`
- `devflow idea create-goal <idea_id>`
- `devflow idea create-task <idea_id> --dry-run`
- `devflow idea create-task <idea_id>`
- `devflow idea archive <idea_id> --reason "superseded"`

Current filesystem:

- `.devflow/ideas/<idea_id>/idea.json`
- `.devflow/ideas/<idea_id>/raw.md`
- `.devflow/ideas/<idea_id>/classification.md`
- `.devflow/ideas/<idea_id>/promotion.md`
- `.devflow/ideas/<idea_id>/goal-brief.md`
- `.devflow/ideas/<idea_id>/task-brief.md`
- `.devflow/ideas/<idea_id>/events.jsonl`
- `.devflow/goals/<goal_id>/idea-link.yaml`
- `.devflow/tasks/<task_id>/idea.md`
- `.devflow/tasks/<task_id>/idea-link.yaml`

Current `idea.json` fields:

- `schema_version`
- `id`
- `title`
- `status`
- `maturity`
- `tags`
- `source`
- `promotion_target`
- `created_at`
- `updated_at`
- `classified_at`
- `promoted_at`
- `archived_at`
- `raw_path`
- `classification_path`
- `promotion_path`
- `created_goal_id`
- `created_goal_path`
- `created_task_id`
- `created_task_path`
- `created_from_idea_at`
- `creation_command`

Current statuses:

- `inbox`
- `classified`
- `promoted`
- `archived`

Current maturity values:

- `spark`
- `concept`
- `candidate`
- `goal_ready`
- `task_ready`

Boundary: Idea Foundry promotion is decision evidence only and never creates tasks/goals automatically. Explicit `idea create-goal` and `idea create-task` commands require prior matching promotion evidence and create linked Dev-Flow state only. Idea creation commands do not run workers, call providers, verify, promote code, commit, push, open pull requests, route models, or mutate task readiness.

## Deferred Behavior

The following remain deferred and are not part of the current stable runtime:

- web dashboard beyond the approved local operating layer
- TUI dashboard
- database
- vector search
- Notion integration
- background automation
- autonomous routing
- provider-backed orchestration
- automatic patch application
- automatic verification
- automatic promotion
- automatic PR creation
- remote model execution through stable task runs

## Suggested Roadmap Placement

- Milestone 8A: Documentation alignment for Patch Evidence Ladder and context-intake roadmap.
- Milestone 8B: Deterministic patch dry-run preview. Status: implemented in commit `1acc4ce` according to milestone handoff and confirmed by current source/tests. Command: `devflow task patch-dry-run <task-id>` with optional `--run-id <run-id>`. Boundary: no mutation.
- Milestone 9: Explicit reviewed patch apply to isolated workspace only. Status: implemented; apply-patch now requires fresh acceptable patch review and dry-run evidence before mutating the isolated workspace.
- Milestone 10: Verification/readiness hardening around applied patches. Status: implemented; applying a patch now invalidates prior verification/readiness evidence, and fresh verification binds `verification.json` to the latest patch application hash.
- Milestone 11: Project Code Map MVP.
- Milestone 12: Idea Foundry MVP. Status: implemented in the first local intake slice.
- Milestone 13: Idea-To-Execution Bridge. Status: implemented; explicit `idea create-goal` and `idea create-task` commands create linked goal/task state after prior promotion evidence without running workers, providers, verification, promotion, commits, pushes, pull requests, or model routing.
