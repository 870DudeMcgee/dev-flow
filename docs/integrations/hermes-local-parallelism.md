# Hermes Local Parallelism

Hermes may help coordinate local-worker parallelism around Dev-Flow. Hermes must not become the runtime, source of truth, or autonomous swarm controller.

Current local-worker selection is opt-in and single-lane visible-Qwen-worker-first; see
[docs/local-worker-policy.md](../local-worker-policy.md). This document
describes future parallelism levels and legacy Dev-Flow evidence paths, not a
standing instruction to spawn multiple local workers. The normal Codex proof is
a visible `qwen36_27b_mtp_coder` subagent response; Hermes MCP should use
`hermes-qwen-mtp` for the same single-lane packet semantics.

Use `<repo-root>` for portable command examples. This checkout is referred to as `DevFlow` in docs and handoffs. `/Users/jewelbait/Desktop/DevFlow` is quarantined and forbidden for current work. Do not assume every checkout is named `DevFlow`.

Dev-Flow artifacts beat Hermes memory. Human approval controls mutation and promotion.

## Parallelism Ladder

### Level 0: Manual Only

Josh runs all commands. Hermes summarizes status and recommends the next safe action.

### Level 1: One Local Worker

One approved worker runs on one task. Dev-Flow owns logs, evidence, verification, and promotion readiness.

### Level 2: One Writer + One Reviewer

One writer works in one task workspace/worktree. One reviewer inspects evidence or a patch proposal. The reviewer is read-only unless Josh approves an evidence-writing review command.

### Level 3: Multiple Read-Only Reviewers

Several reviewers may inspect separate tasks, status packets, patches, or logs. Many read-only reviewers are allowed because they do not share a write target.

### Level 4: Multiple Isolated Writers On Separate Tasks

Multiple writers may run only when each writer has one task, one owner, and one isolated workspace/worktree/branch. No shared write target is allowed.

### Level 5: Supervisor-Managed Swarm, No Auto-Promotion

A future supervisor can propose and launch bounded workers only after Dev-Flow proves isolation, ownership, evidence, and verification gates. Even here there is no auto-promotion, no auto-push, and no merge without Josh.

## Constraints

CPU is not the only bottleneck. The practical limits are usually:

- memory and unified memory pressure
- machine class: Mac mini small utility workers vs Mac Studio heavy local workers
- Ollama/model memory use
- disk I/O
- log readability
- git contention
- verification time
- UI responsiveness
- evidence completeness

Rules:

- one task per worker
- one worktree/branch per writer
- many read-only reviewers allowed
- no shared write target
- no direct `.devflow/` mutation by Hermes
- no direct source edits by Hermes
- no promotion without Dev-Flow readiness evidence and human approval
- no auto-promotion

## Dogfood Experiments

Run these as proposals first. Record metrics before raising the level.

### 1 Local Worker

- Create one task.
- Run one explicitly selected Qwen local worker after approval, or a legacy
  local patch/evidence worker only when the experiment is specifically about
  that surface.
- Verify patch quality, log readability, and task completion time.

### 2 Local Workers

- Run one writer and one reviewer on separate evidence paths.
- Prefer the opt-in Qwen lane for current local-worker packets. Use
  `task run --worker qwopus-implementer` only when deliberately testing the
  legacy proposal-evidence path, then use `task review-patch` for review
  evidence.
- Confirm no shared write target and no main checkout edits.

### 3 Local Workers

- Run one writer and two read-only reviewers.
- Compare review usefulness versus memory pressure and log noise.
- Keep mutation commands human-approved.

### 4 Local Workers

- Run writers only on separate tasks with separate worktrees/branches.
- Confirm `devflow worktree list`, `devflow branch list`, and `devflow git status` remain understandable.
- Stop if verification, logs, or UI responsiveness degrade.

## Metrics To Record

- CPU load
- memory pressure
- Ollama/model memory use
- task completion time
- patch quality
- verification pass/fail
- UI responsiveness
- log readability
- git cleanliness
- evidence completeness

## Future Dry-Run Command Spec

A future command may look like:

```bash
devflow dogfood local-parallel --workers 2 --profile qwopus --dry-run
```

or:

```bash
devflow swarm run --level 2 --task <task-id> --profile local-qwopus --dry-run
```

Specification:

- dry-run/proposal first
- bounded worker count
- reject worker counts outside the selected level
- no shared writer target
- one task/worktree per writer
- read-only reviewers preferred
- Dev-Flow owns verification and readiness evidence
- no provider-backed execution unless explicitly promoted into the stable contract
- machine assignment must respect registry `machine_class` metadata and actual `ollama show` manifests
- no auto-promotion
- no `git push`, merge, promotion, cleanup apply, or destructive command

Hermes may prepare the proposal and ask Josh to approve an exact Dev-Flow command. Hermes must not spawn unbounded workers or treat its own memory as scheduler state.
