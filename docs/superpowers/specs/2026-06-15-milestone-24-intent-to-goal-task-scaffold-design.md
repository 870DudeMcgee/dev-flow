# Milestone 24 Intent-To-Goal/Task Scaffold Design

## Status

Implemented on `main` on 2026-06-15. This design is retained as historical milestone context; use active docs for current product status.

## Context

Dev-Flow now has local Idea Foundry intake, explicit idea-to-goal/task bridge commands, goal lifecycle state, task-slice execution, scheduler visibility, questions, supervisor packets, and an operating layer that agrees on the next safe action.

The remaining gap is the first North Star moment:

```text
I describe what I want built.
Dev-Flow turns it into a reviewable goal with clear task slices.
I approve the scaffold before anything mutates or runs.
```

There is already Telegram/DM-adjacent code under `src/devflow/control_room/df_telegram_bridge.py`, but the current direction must not be a hidden auto-runner. Milestone 24 turns raw operator requests into bounded, reviewable scaffold evidence that flows through existing Idea Foundry, goal, task, scheduler, and supervisor boundaries.

## Product Goal

Make an operator message like "build a search plugin" become a safe Dev-Flow scaffold proposal: raw idea evidence, normalized intent, proposed goal artifacts, proposed task slices, review warnings, and explicit approval commands.

Success check:

```text
Can I send or paste a raw operator request and get a clear goal/task scaffold proposal, approve it, and see created Dev-Flow goal/task state without workers running, providers being called, or hidden state becoming authoritative?
```

## Non-Goals

Milestone 24 must not add:

- provider-backed execution
- autonomous routing or best-model-for-any-task execution
- automatic worker execution
- automatic verification
- automatic promotion, commit, push, pull request, release, or publication
- browser mutation expansion beyond existing approval-gated verification/promotion controls
- database storage
- hidden memory, vector search, RAG, embeddings, or training
- worker-owned verification or promotion
- Hermes, Telegram, or any chat gateway as a second source of truth
- Git-native worktrees as the default runtime

## User-Facing Contract

The preferred operator path should be:

```bash
devflow supervisor route-message "build a search plugin" --json
devflow idea capture "build a search plugin"
devflow idea classify <idea_id> --maturity goal_ready
devflow idea scaffold-goal <idea_id> --dry-run
devflow idea scaffold-goal <idea_id>
devflow idea promote <idea_id> --to goal --rationale "human reviewed scaffold"
devflow idea create-goal <idea_id>
devflow goal status <goal_id>
```

If implementation chooses different exact command names, the contract must still preserve these states:

- raw message stored as Idea Foundry evidence
- deterministic scaffold proposal before canonical goal/task writes
- explicit human classification/promotion before goal creation
- explicit human approval before task records are created
- no worker execution from the scaffold path
- no provider calls from the scaffold path

Telegram/Hermes integration may expose this as a pending action, but it must not directly create goals, create tasks, run workers, verify, promote, push, or publish from a raw message without an explicit approval command.

## Scaffold Evidence Contract

The scaffold proposal should be a durable, reviewable artifact under the existing idea evidence tree, such as:

```text
.devflow/ideas/<idea_id>/goal-scaffold/
  scaffold.json
  scaffold.md
  proposed-goal.md
  proposed-task-slices.yaml
  warnings.json
```

The proposal should include:

- source idea id and raw request hash
- title and cleaned summary
- affected areas
- proposed goal description
- acceptance criteria
- proposed task slices with titles, summaries, risk, dependencies, shared files, and verification policy
- context pointers to read and pointers to avoid
- human questions when the request is ambiguous
- approval command recommendations
- refusal reasons when the request is too broad, unsafe, or outside the MVP contract

This evidence is derived until the human runs an approval command. Canonical goal/task state remains under `.devflow/goals/` and `.devflow/tasks/`.

## Task-Slice Quality Rules

Generated task slices should be useful enough for parallel coding workers:

- one clear title per slice
- acceptance criteria tied to observable files, commands, or behavior
- explicit shared files when known
- risk classification
- verification policy
- human checkpoint requirement for risky work
- dependencies only when required
- no "starter task slice" placeholder when the request has enough detail

When the request lacks enough detail, the scaffold should produce questions and stop before creating canonical goals or tasks.

## Supervisor And Telegram Boundary

`devflow supervisor route-message "<raw>" --json` should classify implementation-like requests as scaffold candidates and return a safe pending action. The pending action may point to an approval-gated scaffold command, but the route-message command itself remains read-only.

Existing Telegram bridge behavior should be brought into this boundary:

- raw `/df ...` messages become pending scaffold proposals or idea-capture instructions
- responses should say whether the next step is approval, question answering, or read-only inspection
- created goal/task ids should only appear after explicit approval
- task execution remains a separate trusted CLI or approved operating-layer action

## Acceptance Criteria

- A raw request can be captured and turned into a deterministic scaffold proposal without creating a goal, task, worker run, verification run, promotion, commit, push, or provider call.
- The scaffold proposal has enough structure to create a meaningful Dev-Flow goal and task slices after approval.
- Ambiguous or unsafe raw requests produce questions/refusals instead of placeholder tasks.
- Approved scaffold creation reuses existing Idea Foundry and goal/task state boundaries instead of adding a parallel source of truth.
- `supervisor route-message` and Telegram-facing code recommend or store approval-gated pending actions, not hidden mutations.
- Active docs explain that Milestone 24 is an intent-scaffold milestone, not an autonomous agent or provider-runtime milestone.
- Production-readiness dogfood covers at least one raw request through scaffold proposal and approved goal/task creation evidence without worker execution.
