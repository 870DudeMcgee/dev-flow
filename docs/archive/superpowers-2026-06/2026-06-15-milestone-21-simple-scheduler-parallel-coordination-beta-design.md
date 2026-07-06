# Milestone 21 Simple Scheduler / Parallel Coordination Beta Design

## Status

Planned for the next implementation agent after Milestone 20 has been promoted and pushed to `main`.

## Context

Dev-Flow now has strong single-lane visibility:

- shell-worker task isolation and verification evidence
- Git-native worker lane recovery
- registry-backed local patch-worker and read-only WorkerEvidence lanes
- goal freshness loops that project conflict-safe task creation, worker, and verification batches
- operating-layer visibility over tasks, questions, lanes, promotion readiness, and goal boards

The next product gap is coordination. The user should be able to ask, "What can run now, what is blocked, what is stale, what needs retry, and what is the safest next batch?" without reading individual task files, goal slices, or freshness reports.

Milestone 21 adds a simple scheduler projection. It is a control-room visibility and explicit-dispatch layer, not an autonomous background scheduler.

## Product Goal

Make parallel work more visible, bounded, and recoverable by projecting a scheduler view over existing task, goal, freshness, lock, question, verification, and worker-run evidence.

Success check:

```text
Can Dev-Flow show a safe ready queue, blocked/stale/retry states, and batch next actions for multiple tasks without owning verification, promotion, or hidden worker scheduling?
```

## Non-Goals

Milestone 21 must not add:

- remote provider execution
- autonomous routing or model selection beyond existing evidence-only commands
- background daemon scheduling
- auto-verification
- auto-promotion, auto-commit, auto-push, or pull requests
- database storage
- task mutation from the operating-layer browser beyond the stable guarded list of idea capture, task creation, shell worker execution, task verification, and task promotion
- worker-owned readiness certification

## User-Facing Contract

Add a read-only scheduler status command:

```bash
devflow scheduler status
devflow scheduler status --json
```

The command reports:

- queue status: `ready`, `blocked`, `running`, `stale`, `needs_retry`, `needs_review`, `ready_to_verify`, `ready_to_promote`
- counts by scheduler state
- conflict-safe task creation batches from the existing goal loop
- conflict-safe shell-worker batches from the existing goal loop
- conflict-safe verification batches from the existing goal loop
- stale running tasks based on task timestamps, timeout settings, and lock evidence
- blocked questions from existing `questions.jsonl` evidence
- dependency blockers from existing goal slice `blocked_by` data
- manual retry candidates and the exact command to request retry evidence
- one next safe action

Add one explicit retry-evidence command:

```bash
devflow scheduler retry <task_id> --reason "<reason>"
devflow scheduler retry <task_id> --reason "<reason>" --json
```

This command does not rerun work. It writes a small task-local retry request artifact and appends a task event so retry intent is durable and reviewable. The actual rerun stays an explicit trusted CLI command, usually `devflow task run`, `devflow freshness worker-batch`, or `devflow freshness verify-batch`.

## Data Model

Create `src/devflow/control_room/scheduler_projection.py`.

Core model:

```python
SchedulerTaskState = Literal[
    "ready",
    "running",
    "stale",
    "blocked",
    "needs_retry",
    "needs_review",
    "ready_to_verify",
    "ready_to_promote",
    "closed",
]
```

`SchedulerSnapshot` should include:

- `schema_version`
- `generated_at`
- `status`: `ready`, `blocked`, `stale`, or `idle`
- `counts`: map of scheduler state to count
- `max_parallel_recommendation`: derived from visible batch sizes, defaulting to the existing explicit CLI default of `4`
- `tasks`: compact scheduler records keyed by task id
- `batches`: normalized task creation, worker, and verification batches from the freshness goal loop
- `blocked_dependencies`: goal-slice blockers from `blocked_by`
- `stale_tasks`: running tasks that exceeded the passive stale threshold
- `retry_candidates`: failed, timed out, stale, or verification-failed tasks with an exact retry-request command
- `next_safe_action`: one CLI command or inspection action
- `evidence_paths`: existing task, freshness, worker-run, verification-run, and question artifacts used by the projection

The projection is derived and disposable. Canonical state remains task files, goal files, event logs, lock owner files, worker evidence, and verification evidence.

## State Rules

Scheduler state is deterministic:

- `stale`: task status is `running` and passive stale detection says it exceeded its allowed age.
- `running`: task status is `running` and not stale.
- `blocked`: task has open blocked-question evidence, goal slice blockers, paused/blocked lifecycle, or a freshness human-decision finding.
- `needs_retry`: task status is `worker_failed`, `timeout`, `failed`, or `verification_failed`, or an explicit retry request exists.
- `ready_to_promote`: task verification passed or task status is `verified`, and promotion-preview remains the next safe action.
- `ready_to_verify`: task has complete worker evidence but verification is not passed.
- `needs_review`: task has local worker, Git-native lane, or manual proof-agent evidence that needs review before verification/promotion.
- `ready`: task or goal lane appears in a currently projected conflict-safe batch.
- `closed`: task status is `closed` or `promoted`.

If more than one rule matches, use this priority:

```text
stale > blocked > needs_retry > running > ready_to_promote > ready_to_verify > needs_review > ready > closed
```

## Passive Stale Detection

Milestone 21 does not add active heartbeats. It adds passive stale projection:

- Use `task.started_at` for running tasks when available.
- Use `task.updated_at` as fallback.
- Use `task.timeout_seconds` when present.
- Default stale threshold is `max(timeout_seconds or 120, 300)` seconds.
- If `.devflow/tasks/<task_id>/.lock/owner.json` exists and is malformed or stale according to the existing strict-lock rules, mark the task stale and include the lock owner path.
- Do not remove locks from scheduler status. Existing lock cleanup remains owned by current lock/doctor behavior.

## Manual Retry Evidence

Retry evidence lives at:

```text
.devflow/tasks/<task_id>/retry-request.json
```

Schema:

```json
{
  "schema_version": 1,
  "task_id": "task-0001",
  "requested_at": "2026-06-15T00:00:00+00:00",
  "reason": "verification failed after worker run",
  "previous_status": "verification_failed",
  "previous_verification_status": "failed",
  "recommended_next_command": "devflow task next-action task-0001"
}
```

The command appends an event:

```json
{"event": "retry_requested", "reason": "..."}
```

It must not delete old logs, mutate workspace files, reset verification, clear worker evidence, or mark the task ready by itself.

## Surface Integration

Add the scheduler snapshot to:

- `devflow scheduler status --json`
- `devflow status --json` supervisor packet as `scheduler`
- `devflow supervisor packet --json` as `scheduler` and scheduler evidence paths
- operating-layer snapshot as `scheduler`
- operating-layer UI summary cards for queue, blocked, stale, retry, and next batch
- production-readiness dogfood as a new scheduler coordination case

The existing freshness commands remain the only dispatch commands for parallel task creation, worker batches, and verification batches:

```bash
devflow freshness create-batch <goal_id> <batch_id>
devflow freshness worker-batch <goal_id> <batch_id> --max-parallel <n>
devflow freshness verify-batch <goal_id> <batch_id> --max-parallel <n>
devflow freshness run --max-iterations <n> --create-tasks
devflow freshness run --max-iterations <n> --execute-workers
devflow freshness run --max-iterations <n> --execute-verification
```

Milestone 21 may point at these commands, but it must not create a new executor that bypasses them.

## Dogfood Case

Add a production-readiness case named `simple-scheduler-parallel-coordination`.

It should build a deterministic scratch repo with:

- two ready parallel-safe slices with disjoint `shared_files`
- one blocked slice with `blocked_by`
- one running task old enough to be stale
- one verification-failed task that becomes a retry candidate
- one task with blocked-question evidence

The case should assert:

- scheduler status exposes ready, blocked, stale, retry, and batch counts
- next safe action points to the first explicit existing command
- retry request writes only retry evidence and task event metadata
- no workers, verification, promotion, commits, pushes, provider calls, databases, or background daemons are invoked by scheduler status

## Documentation Updates

Update active docs to say:

- Milestone 20 is promoted and pushed on `main`.
- Milestone 21 is the next planned milestone.
- Simple scheduler beta is a derived projection and explicit retry-evidence layer over existing freshness/parallel commands.
- Provider adapters and autonomous routing remain excluded.

## Acceptance Criteria

- `devflow scheduler status --json` returns deterministic JSON from existing filesystem evidence.
- `devflow scheduler retry <task_id> --reason "<reason>" --json` writes retry evidence without rerunning work.
- Scheduler projection is visible in CLI, supervisor packet, operating-layer snapshot/UI, and dogfood.
- Stale running tasks are understandable with evidence paths and no destructive lock cleanup.
- Dependency-blocked slices and blocked-question tasks are visible as blocked work.
- Ready worker and verification batches are normalized from the existing goal loop.
- Focused tests cover state priority, stale detection, retry evidence, surface integration, and dogfood.
- Production-readiness dogfood remains Silver-or-better.
- Full release check passes before promotion.
