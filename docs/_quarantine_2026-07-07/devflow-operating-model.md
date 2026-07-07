# Dev-Flow Operating Model

## Purpose

This document defines the operating model for Dev-Flow.

Dev-Flow is a local-first control room for replaceable coding workers. It exists to let a human developer coordinate AI-assisted work without losing visibility, safety, context, or control.

Dev-Flow is not the coding intelligence itself. It is the operational layer around coding intelligence.

## Core Thesis

Dev-Flow separates planning, execution, observation, verification, and promotion.

The intended model is:

```text
Human
  -> main chat / control-room agent
  -> Dev-Flow kernel
  -> isolated worker agents
  -> verified reviewable results
  -> human-controlled promotion
```

The main chat/control-room agent plans and reviews in read-only mode.

Worker agents perform mutating work only inside isolated task-owned spaces.

Dev-Flow owns state, visibility, verification, promotion readiness, and human-controlled promotion.

## Roles

### Human

The human is the final authority.

The human:

* defines goals
* approves scope
* answers worker questions
* decides whether work is accepted
* controls promotion to the main checkout or main branch
* may override automation when needed

No worker, supervisor, or chat agent should silently promote work without human approval.

### Main Chat / Control-Room Agent

The main chat/control-room agent is the user’s planning, specification, review, and coordination partner.

It is read-only by default.

It may:

* brainstorm
* clarify goals
* decompose work
* draft task specs
* propose task packets
* review worker handoffs
* compare claims against evidence
* identify risks
* recommend next safe actions

It must not directly edit repo files, stage files, commit, push, merge, or bypass Dev-Flow task state.

### Dev-Flow Kernel

The Dev-Flow kernel owns the control plane.

It owns:

* task state
* task artifacts
* worker ownership
* isolated workspaces
* append-only events
* logs
* questions and answers
* verification evidence
* result bundles
* readiness state
* promotion gates

The kernel should be boring, durable, observable, and recoverable.

### Worker Agents

Workers are replaceable executors.

A worker may be a shell command today and an AI coding tool later.

Workers receive bounded task context and operate inside task-owned isolation boundaries.

Future agents are not personalities. They are permissioned execution contracts resolved through the Agent Registry and Adapter Runtime architecture in [docs/architecture/agent-registry-and-adapter-runtime.md](architecture/agent-registry-and-adapter-runtime.md): provider, model, model capability, role, adapter, workspace, allowed context, allowed writes, evidence trail, and routing rules. Future routing must follow [docs/architecture/agent-selection-and-context-routing.md](architecture/agent-selection-and-context-routing.md): classify task fit, estimate context and risk, build role-specific context packs, then select the cheapest capable agent for each role.

A worker should produce:

* status updates
* logs
* changed artifacts
* questions when blocked
* verification evidence
* a handoff or result summary

Workers do not own Dev-Flow state. They report into it.

Workers must not merge directly to main.

### DevMode

DevMode is the portable discipline layer for agent behavior.

DevMode may guide how agents plan, read context, edit, verify, review, and hand off work.

DevMode is not the Dev-Flow runtime.

Dev-Flow may use DevMode discipline, but Dev-Flow owns task state, worker isolation, verification execution, and promotion readiness.

## Permission Boundaries

Dev-Flow depends on strict permission boundaries.

The default boundary is:

```text
main chat/control-room agent: read-only planning and review
worker agent: mutates only assigned task workspace
Dev-Flow kernel: owns task state and verification records
human: approves promotion
```

A worker must not modify the main checkout directly.

The main chat/control-room agent must not become an implicit implementation worker.

## Task Lifecycle

A typical Dev-Flow task moves through this lifecycle:

```text
spec proposed
task created
workspace prepared
worker assigned
worker runs
logs captured
questions surfaced if needed
result produced
verification runs
handoff written
review performed
human approves or rejects promotion
```

The exact status names may evolve, but the lifecycle must preserve visibility, isolation, verification, and human control.

## State Ownership

Dev-Flow state must be durable and inspectable.

Canonical state should live in files that humans and agents can inspect.

Current canonical artifacts include:

* `task.yaml`
* `events.jsonl`
* `questions.jsonl` when present
* `verification.json`
* `logs/worker.log`
* `logs/verify.log`

Derived summaries, packets, reports, and projections may exist, but they must not replace canonical state.

## Isolation Model

Every task should have an isolation boundary.

The current MVP uses copied task workspaces under:

```text
.devflow/workspaces/<task_id>/
```

Worker and verification commands run inside the assigned task workspace.

The initial Git-native isolation slice is active for shell workers through `devflow task create --git-worktree`: each task gets a branch and worktree under `.devflow/worktrees/<task_id>/shell/`, with Git facts recorded as Dev-Flow evidence. Multi-worker attempts remain follow-up work.

The principle is stable:

```text
one task -> one isolated workspace -> one worker owner -> one result bundle -> one review path
```

## Verification And Promotion

Dev-Flow owns verification evidence.

Workers may run or request verification, but Dev-Flow records the result.

Work is not ready for promotion until verification evidence exists or the lack of verification is explicitly recorded.

Promotion must be human-controlled.

The production promotion direction is Git-native: worker branches propose diffs, Dev-Flow previews merge readiness and verification evidence, and humans promote with Git-aware mechanics. Copy-back and patch application remain MVP or transitional paths. None of those should bypass human review.

## What Dev-Flow Is Not

Dev-Flow is not:

* a coding agent
* a prompt pack
* a model router
* a memory framework
* a hidden autonomous software factory
* a replacement for human review
* a tool that lets workers silently merge to main

Dev-Flow should make agent work visible, isolated, recoverable, and reviewable.

## MVP Boundary

The current MVP remains the shell-worker control room.

It proves:

* task creation
* task-local filesystem artifacts
* isolated workspaces
* shell worker execution
* worker logs
* verification execution
* verification logs
* CLI visibility
* canonical filesystem state

Enabled non-shell worker adapters, browser/web dashboard mutation surfaces outside the approved operating layer, scheduling, automatic commits, automatic pull requests, and automated promotion are deferred layers unless explicitly promoted into the active contract. Git-native shell-worker isolation and promotion is opt-in; default task creation remains copy-workspace. The current text-only terminal dashboard, guarded local operating layer, and human-controlled promotion commands are active contract surfaces. Non-shell adapter work must start with registry loading, manual packets, and shell alignment before non-local execution or autonomous assignment.

## Future Direction

The long-term direction is a human-supervised multi-worker control room.

Dev-Flow should eventually support:

* multiple isolated workers
* dependency-aware scheduling
* read-only supervisor access
* structured worker questions
* review-ready result bundles
* safe promotion paths
* multi-project visibility

The control room comes first. Intelligence plugs in later.

### Design-To-Contract Bridge

The next design layer is documented separately:

- [docs/workflow-preview.md](workflow-preview.md) defines the human-reviewable plan created before workers are created or run.
- [docs/architecture/agent-registry-and-adapter-runtime.md](architecture/agent-registry-and-adapter-runtime.md) defines registered agent roles, permissions, allowed context, allowed writes, and evidence trails.
- [docs/dynamic-worker-orchestration.md](dynamic-worker-orchestration.md) defines the future direction for decomposing goals into isolated worker tasks while preserving local state, replaceable workers, and human-controlled promotion.

These documents are design contracts only. They do not imply current runtime implementation.
