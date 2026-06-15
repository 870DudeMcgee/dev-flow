# Milestone 23 Operating Layer State Reconciliation & Operator Readiness Design

## Status

Planned. Milestone task: `task-0137`.

## Context

Dev-Flow now has the pieces of a local-first control room: task state, goal lifecycle, scheduler projection, questions, worker evidence, verification, promotion readiness, supervisor packets, and a browser operating layer. The next problem is operator trust.

The human should not have to reconcile `G-0004`, `task-0136`, stale freshness guidance, and differing ready/blocked counts by hand. The operating layer must present the same state as `status`, `scheduler`, `dashboard`, and `supervisor`, using plain descriptive labels first and machine ids second.

This milestone focuses on visibility, naming, lifecycle reconciliation, stale-directive handling, and next-safe-action agreement across existing surfaces.

## Product Goal

Make Dev-Flow answer "what should I do now?" consistently and in human-readable language across CLI, supervisor, and browser surfaces.

Success check:

```text
Can a human open the operating layer or run status/scheduler/dashboard/supervisor commands and see the same counts, the same lifecycle blockers, the same stale-task guidance, and descriptive task/project names without decoding internal ids?
```

## Non-Goals

Milestone 23 must not add:

- provider-backed execution
- autonomous routing or best-model-for-any-task execution
- automatic worker resume
- automatic verification
- automatic promotion, commit, push, pull request, or publication
- database storage
- hidden memory, vector search, RAG, embeddings, or training
- browser-side mutation beyond the existing exact verification and exact promotion approvals
- Git-native worktrees as the default runtime
- new worker adapters

## User-Facing Contract

These surfaces must agree on active counts, blocked counts, stale counts, lifecycle blockers, and next-safe-action priority:

```bash
devflow status --json
devflow scheduler status
devflow scheduler status --json
devflow dashboard
devflow supervisor packet --json
devflow operating-layer snapshot --json
```

The human-facing text surfaces should lead with descriptive labels:

```text
Project: Local AI Dev Team
Goal: Operating Layer State Reconciliation & Operator Readiness
Task: Reconcile operator counts across status/scheduler/dashboard
ID: task-0137
```

Internal ids remain visible, copyable, and stable, but they should not be the primary name when a descriptive title exists.

## Reconciliation Contract

Add or harden one shared read-only operator-state projection that the major surfaces can consume. It should normalize:

- task identity: `display_title`, `task_id`, `project_id`, `goal_id`, optional `slice_id`
- project identity: descriptive project name first, registry id second
- goal identity: goal title or intent title first, `G-*` id second
- task state buckets: ready, running, blocked, stale, needs_review, ready_to_verify, ready_to_promote, closed
- lifecycle blockers: missing, paused, blocked, complete, archived goal lifecycle state
- stale directives: freshness guidance that references superseded, closed, archived, missing-lifecycle, or non-active work
- question blockers: open questions before worker dispatch
- next-safe-action priority and reason

The projection is derived evidence only. It must not mutate task state, goal state, freshness snapshots, questions, verification evidence, worker evidence, Git state, or browser state.

## Plain-Language Naming Rules

Human labels should be derived conservatively from existing artifacts:

- Project: registry `name` or repository folder name, with project id secondary.
- Goal: `goal.md` title, intent metadata title, or a cleaned brief title before falling back to `G-*`.
- Task: `task.yaml` title if descriptive; if the title is a generated slice label such as `G-0004 • Slice 2`, include the parent goal title and slice title when available.
- Worker: existing plain display names such as "Shell worker", "Qwopus implementer", and "Gemma reviewer".
- Commands and evidence paths may still use ids because they are operational handles.

Generated ids should appear as metadata, not as the main noun in first-viewport UI or next-action copy.

## Next-Safe-Action Priority

All operator surfaces should choose next actions in the same conservative order:

1. Git safety or dirty-state checkpoint requirement.
2. Open human question requiring answer or resolve.
3. Goal lifecycle repair before dispatching goal-linked tasks.
4. Stale/conflicting directive repair.
5. Failed verification or explicit retry request.
6. Review or promotion readiness requiring human approval.
7. Ready verification for completed worker output.
8. Ready worker dispatch only when the task is active, unblocked, and its linked goal lifecycle allows work.
9. Read-only inspection when no safer mutation is appropriate.

Each next action should include a reason that names the blocker in plain language.

## Surface Requirements

`status --json`:

- expose the shared operator counts and selected next safe action
- include warnings when raw scheduler/freshness/task projections disagree

`scheduler status`:

- stop marking tasks ready for worker dispatch when linked goal lifecycle is missing, paused, blocked, complete, or archived
- show lifecycle repair commands before worker-run commands

`dashboard`:

- use the same counts and next-safe-action reason as scheduler/status
- render descriptive task and goal labels with ids secondary

`supervisor packet`:

- include the shared operator summary, warnings, and one next safe action
- keep mutation commands approval-classified

`operating-layer snapshot/UI`:

- use the shared counts and labels
- make the first viewport explain current directive, active blockers, and next action without id decoding
- show stale directives as human-decision items, not as worker-ready tasks
- keep Action Rail mutation boundaries unchanged

## Dogfood Case

Add a deterministic production-readiness case for operator reconciliation. It should create or fixture:

- one active descriptive task
- one generated-name task linked to a descriptive goal
- one goal with missing lifecycle state
- one stale freshness recommendation
- one open or answered question

The case should assert that status, scheduler, dashboard, supervisor, and operating-layer snapshot agree on counts and next-safe-action class.

## Acceptance Criteria

- `status --json`, `scheduler status --json`, `dashboard`, `supervisor packet --json`, and `operating-layer snapshot --json` agree on active, ready, blocked, stale, review-ready, and promotion-ready counts for the same repository state.
- Tasks linked to missing or inactive goal lifecycle state are not surfaced as worker-ready until the lifecycle blocker is resolved.
- Generated labels such as `G-0004 • Slice 2` are not the primary human-facing task name when goal or slice context can produce a descriptive name.
- Stale freshness directives become explicit human-decision warnings with clear repair or inspection commands.
- The operating-layer first viewport uses descriptive project, goal, task, and worker labels with ids secondary.
- Existing approval gates for worker execution, verification, promotion, Git publication, and browser mutation remain intact.
- Production-readiness dogfood covers the reconciliation case.
- Active docs and handoff point future agents at Milestone 23 as the next implementation slice.
