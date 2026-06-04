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

The current implemented slice starts with `devflow freshness loop`: it runs one read-mostly control iteration, writes `.devflow/freshness/latest.json`, updates derived per-goal loop state, appends loop history, detects stale goal/task guidance, records a loop-start Git decision, and projects per-goal parallel lanes. `devflow freshness run --max-iterations N` repeats those iterations inside an explicit bound, records `.devflow/freshness/control-runs/<run_id>.json`, stops on stable state, and stops before dispatch when Git or human action is required. `devflow freshness run --all-projects --max-iterations N` repeats read-mostly scans across registered project roots and writes the aggregate control-run report under `~/.devflow/freshness/control-runs/`; dispatch flags are refused in all-projects mode. Dirty state caused only by the loop's own derived `.devflow/freshness/` artifacts and per-goal `loop-state.json` files does not block the bounded runner from reaching stability, but task/workspace/source changes still surface as a checkpoint stop. It never commits, pushes, promotes, routes providers, or mutates task source code.

## Parallelism Model

Parallelism is allowed at every level only when ownership is explicit:

- Project level: each registered project has its own root, Git state, `.devflow/` state, goals, tasks, workspaces, and publication policy.
- Goal level: a goal can be sliced into tasks with declared risk, execution mode, checkpoint requirement, and parallel-safety hints.
- Task level: each task owns one isolated workspace or opt-in Git worktree and one active writer lock.
- Worker level: replaceable workers can run in parallel when their task boundaries, locks, Git baseline, and verification expectations do not conflict.
- Test level: verification commands are task-local evidence; the loop projects conflict-aware verification batches from each slice's `verification_policy` so focused tests can run in parallel when their declared file scopes do not overlap. Broader test suites are selected by blast radius before promotion or checkpoint.

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

Lane states are recommendations, not execution. `ready_to_create_task` means the slice is unblocked, declared `parallel_safe`, not high risk, and has no linked task yet. Ready lanes are grouped into `parallel_batches` using declared `shared_files`; lanes in the same batch have no declared shared-file conflict. `devflow freshness create-batch <goal_id> <batch_id>` can create the tasks for one currently projected safe batch, using existing goal-slice task creation and serial canonical state writes. `devflow freshness run --create-tasks` is the explicit repeated-loop dispatch mode for the first currently projected task batch; it loops again after task creation so the dirty task/workspace artifacts are reported as checkpoint work before more dispatch. When linked tasks exist and their slices declare concrete shell worker commands in `worker_policy` (`shell_commands`, `worker_commands`, `run_commands`, or related command lists), the loop emits conflict-aware `worker_batches`. `devflow freshness worker-batch <goal_id> <batch_id> --max-parallel N` runs one projected shell-worker batch through existing task workspaces, task mutation locks, worker logs, result artifacts, and task events. `devflow freshness run --execute-workers` is the explicit repeated-loop worker dispatch mode; after worker execution it loops again so workspace/task changes are surfaced as checkpoint work before more dispatch. `running`, `ready_to_promote`, `repair_or_verify`, `closed`, `complete`, and `blocked` keep existing work visible so Dev-Flow does not spawn conflicting work for the same slice.

Verification batches are also recommendations, not execution. When a linked task is ready to run or repair verification and its slice declares concrete commands in `verification_policy` (`focused_commands`, `verification_commands`, `test_commands`, `broad_commands`, or related command lists), the loop emits `verification_batches` with `devflow task verify ...` commands grouped by the same declared `shared_files` conflict boundary. This exposes test/process parallelism without starting test processes, rewriting verification evidence, or marking work complete.

The first execution helper for verification batches is task-grained. `devflow freshness verify-batch <goal_id> <batch_id> --max-parallel N` re-runs the bounded freshness projection, selects only a currently projected batch, groups commands by task, folds multiple commands for the same task into one shell script, and starts up to the requested bounded number of task verification subprocesses. `devflow freshness run --execute-verification` is the explicit dispatch mode for the repeated loop; it may run the first currently projected verification batch in a safe iteration, then loops again so changed verification evidence is observed and the next Git checkpoint opportunity is surfaced before more work. Each subprocess still flows through the existing `verify_task` path, task-local mutation lock, process-group cleanup, `logs/verify.log`, `verification.json`, and task events. The helpers write compact derived run reports under `.devflow/freshness/task-batch-runs/`, `.devflow/freshness/worker-runs/`, `.devflow/freshness/verification-runs/`, and `.devflow/freshness/control-runs/`; those reports are evidence about loop and batch execution, not goal-completion certificates. Failed task worker or verification runs are reported alongside successful task results instead of stopping the whole batch early.

The per-goal loop-state files are derived projections, not canonical goal source. They exist so each loop leaves current, inspectable state beside the goal it is evaluating without rewriting the human-authored goal brief, PRD, task slices, or handoff.

For registered project folders, `devflow freshness loop --all-projects` runs the project-local loop for each active registry entry. Each project keeps its own `.devflow/freshness/latest.json`; the registry-level aggregate lives at `~/.devflow/freshness/latest-all-projects.json` and rolls up project/goal counts for ready task lanes and verification batches. The aggregate is a control-room index over project-local truth, not a replacement for project-local state.

## Hermes And Local Models

Hermes can be an external operator or chat gateway over supervisor-safe Dev-Flow commands. A local model such as Qwopus can contribute bounded evidence, patch proposals, review notes, or goal-satisfaction judgments through the agent registry. Dev-Flow still owns the state machine, locks, verification, checkpoint decisions, merge readiness, and human-controlled publication.

Future Hermes or local-model goal integration must follow the existing adapter sequence. It must not bypass Dev-Flow task isolation, write directly to main, auto-promote, auto-push, or turn local advisory model output into canonical state without validation.
