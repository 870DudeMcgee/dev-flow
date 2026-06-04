# Goal Control Loop

Status: Active design direction

Dev-Flow's goal loop is a PLC-style control loop for local AI development work. Each iteration should read durable state, compare it to the active goal, decide the next safe control action, run only bounded work, record evidence, and repeat until the goal is verified, blocked, paused, or handed back to the operator.

This is inspired by the goal contracts in Codex and Hermes: a goal is persistent state with a completion condition, verification surface, constraints, lifecycle controls, and evidence-based completion. In Dev-Flow the scope is project-local control-room state, not hidden memory and not an autonomous coding brain.

## Loop Contract

Each loop iteration starts with Git hygiene before new work is spawned:

1. Inspect the project root and current branch.
2. If the tree is dirty, report a checkpoint opportunity before creating more work.
3. If clean `main` is ahead of `origin/main`, report a push opportunity.
4. If Git is conflicted, mid-operation, diverged, behind remote, detached, or off `main`, stop with the safest repair action.
5. Only then evaluate goals, task slices, linked tasks, freshness, parallelism, and verification evidence.

The current implemented slice is `devflow freshness loop`: it runs one read-mostly control iteration, writes `.devflow/freshness/latest.json`, updates derived per-goal loop state, appends loop history, detects stale goal/task guidance, records a loop-start Git decision, and projects per-goal parallel lanes. It never commits, pushes, promotes, routes providers, or mutates task source code.

## Parallelism Model

Parallelism is allowed at every level only when ownership is explicit:

- Project level: each registered project has its own root, Git state, `.devflow/` state, goals, tasks, workspaces, and publication policy.
- Goal level: a goal can be sliced into tasks with declared risk, execution mode, checkpoint requirement, and parallel-safety hints.
- Task level: each task owns one isolated workspace or opt-in Git worktree and one active writer lock.
- Worker level: replaceable workers can run in parallel when their task boundaries, locks, Git baseline, and verification expectations do not conflict.
- Test level: verification commands are task-local evidence; broader test suites are selected by blast radius before promotion or checkpoint.

Parallel speed comes from small bounded lanes, not from weakening isolation. A fast loop should do cheap state reads, emit compact decisions, and spawn work only when the state says it is safe.

## Goal State

Goals live under `.devflow/goals/<goal_id>/` with human-readable artifacts such as `goal.md`, `prd.md`, `task-slices.yaml`, `open-questions.yaml`, and `handoff.md`. Tasks link back to goal slices through `.devflow/tasks/<task_id>/goal-link.yaml`.

A future active-goal runtime should add lifecycle fields without replacing the existing scaffold:

- `active`, `paused`, `blocked`, `complete`, or `archived`
- verification surface and acceptance criteria
- loop budget and last iteration summary
- linked project id and task slice ids
- current blockers and next safe action
- last known Git checkpoint or push recommendation

Completion must remain evidence-based: verified task state, logs, tests, review capsules, promotion evidence, or an explicit blocker report. A goal is not complete just because a worker says it is probably done.

## Snapshot Shape

The freshness snapshot includes two loop-control sections:

- `loop_start_git`: whether the loop should checkpoint, push, sync, resolve Git state, or continue.
- `goal_loop`: one projection per goal with goal state, active linked tasks, completed slices, blocked lanes, ready parallel lane count, and lane-level commands.
- `.devflow/goals/<goal_id>/loop-state.json`: the latest derived state for one goal, including relevant findings and lane recommendations.
- `.devflow/freshness/events.jsonl`: append-only loop iteration history with event hashes.

Lane states are recommendations, not execution. `ready_to_create_task` means the slice is unblocked, declared `parallel_safe`, not high risk, and has no linked task yet. `running`, `ready_to_promote`, `repair_or_verify`, `closed`, `complete`, and `blocked` keep existing work visible so Dev-Flow does not spawn conflicting work for the same slice.

The per-goal loop-state files are derived projections, not canonical goal source. They exist so each loop leaves current, inspectable state beside the goal it is evaluating without rewriting the human-authored goal brief, PRD, task slices, or handoff.

For registered project folders, `devflow freshness loop --all-projects` runs the project-local loop for each active registry entry. Each project keeps its own `.devflow/freshness/latest.json`; the registry-level aggregate lives at `~/.devflow/freshness/latest-all-projects.json`. The aggregate is a control-room index over project-local truth, not a replacement for project-local state.

## Hermes And Local Models

Hermes can be an external operator or chat gateway over supervisor-safe Dev-Flow commands. A local model such as Qwopus can contribute bounded evidence, patch proposals, review notes, or goal-satisfaction judgments through the agent registry. Dev-Flow still owns the state machine, locks, verification, checkpoint decisions, merge readiness, and human-controlled publication.

Future Hermes or local-model goal integration must follow the existing adapter sequence. It must not bypass Dev-Flow task isolation, write directly to main, auto-promote, auto-push, or turn local advisory model output into canonical state without validation.
