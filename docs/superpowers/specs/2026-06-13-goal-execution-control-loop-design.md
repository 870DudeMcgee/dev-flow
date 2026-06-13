# Goal Execution Control Loop Design

Status: planned Milestone 14 design; implementation is the next milestone.
Date: 2026-06-13

## Purpose

Milestone 13 made human-reviewed ideas convertible into linked Dev-Flow goal or task state. The next logical milestone is to make a created goal executable through the existing control-room loop without adding autonomous routing or new provider-backed workers.

Milestone 14 should prove this path:

```text
promoted idea
-> explicit goal creation
-> active goal lifecycle
-> projected task slices
-> explicit task-batch creation
-> explicit shell worker batch
-> explicit verification batch
-> review/promote readiness
-> evidence-based goal closure decision
```

The feature should make goal execution feel like a bounded control loop: read durable state, choose the next safe action, optionally run one explicitly requested bounded batch, record evidence, and stop for checkpoint, push, review, or human decision.

## Current State

Current implemented behavior already includes:

- `devflow idea create-goal` and `devflow idea create-task` for explicit idea bridge creation.
- Goal scaffolds under `.devflow/goals/<goal_id>/`.
- Goal task slices in `.devflow/goals/<goal_id>/task-slices.yaml`.
- Task links in `.devflow/tasks/<task_id>/goal-link.yaml`.
- `devflow freshness loop` for read-mostly goal/task/freshness projection.
- `devflow freshness create-batch`, `worker-batch`, `verify-batch`, and `run` dispatch modes.
- Derived per-goal loop state at `.devflow/goals/<goal_id>/loop-state.json`.

The missing product contract is a first-class goal lifecycle and a tested end-to-end goal execution lane. Today `GoalStatusProjection.state` is inferred from scaffold artifacts and open questions. There is no canonical goal lifecycle evidence that says a goal is active, paused, blocked, complete, or archived, and there is no milestone-level dogfood path that proves an idea-created goal can move safely through task creation, worker execution, verification, review readiness, and closure decision.

## Goals

Milestone 14 should:

1. Add a durable goal lifecycle artifact without replacing existing goal scaffold files.
2. Make `devflow goal status`, `goal next`, `freshness loop`, and the operating layer use lifecycle state consistently.
3. Keep loop-start Git hygiene as the first control decision before task creation, workers, or verification.
4. Preserve explicit dispatch. The loop may recommend actions; batch commands may run only when the human invokes explicit dispatch flags or batch commands.
5. Add a deterministic dogfood test path for one small goal moving through task creation, shell worker batch execution, verification batch execution, and review readiness.
6. Add evidence-backed goal closure decision support without auto-closing goals.

## Non-Goals

Milestone 14 must not add:

- Aider, Hermes runtime, OpenCode, Codex, Claude Code, or remote provider-backed execution.
- Autonomous routing, task-fit runtime selection, model memory, vector search, RAG, or training.
- Automatic goal creation during `idea promote`.
- Automatic worker execution after goal creation.
- Automatic verification, promotion, commit, push, pull request creation, or goal closure.
- A database or daemon.
- Browser-side execution of worker, batch, patch-application, task-creation, git-publish, or provider commands.

## Lifecycle Contract

Add a canonical goal lifecycle artifact:

```text
.devflow/goals/<goal_id>/goal-state.yaml
```

Initial schema:

```yaml
schema_version: 1
goal_id: G-0001
lifecycle: active
status_reason: ""
created_at: "2026-06-13T00:00:00+00:00"
updated_at: "2026-06-13T00:00:00+00:00"
last_decision: activated
last_decision_command: devflow goal activate G-0001
```

Allowed lifecycle values:

- `active`: loop may project task, worker, verification, review, and closure recommendations.
- `paused`: loop reports the pause and does not project new task/worker/verification dispatch for the goal.
- `blocked`: loop reports the blocker and does not project new task/worker/verification dispatch for the goal.
- `complete`: loop reports complete and does not project new dispatch.
- `archived`: loop reports archived and does not project new dispatch.

Lifecycle events should append to:

```text
.devflow/goals/<goal_id>/events.jsonl
```

Goal lifecycle events are canonical evidence for goal decisions. Existing `.devflow/freshness/events.jsonl` remains derived loop history.

## CLI Contract

Add narrowly scoped commands:

```bash
devflow goal activate <goal_id> --reason "ready to execute"
devflow goal pause <goal_id> --reason "waiting on review"
devflow goal block <goal_id> --reason "needs human answer"
devflow goal complete <goal_id> --reason "all slices promoted and reviewed"
devflow goal archive <goal_id> --reason "superseded"
```

Command behavior:

- Each command validates the goal exists.
- Each command writes `goal-state.yaml`.
- Each command appends a hash-chained event to `.devflow/goals/<goal_id>/events.jsonl`.
- Each command prints the new lifecycle, goal path, and safest next command.
- Commands do not create tasks, run workers, verify, promote, checkpoint, push, or open pull requests.

`devflow goal status <goal_id>` and `devflow goal next <goal_id>` should show lifecycle state and lifecycle reason. If `goal-state.yaml` is missing, status may infer existing scaffold state for backward compatibility but should recommend activation before execution dispatch.

## Freshness Loop Contract

`devflow freshness loop` should treat lifecycle state as a control gate:

- Missing `goal-state.yaml`: report a lifecycle finding and recommend `devflow goal activate <goal_id> --reason "..."`
- `active`: existing projection behavior continues.
- `paused`: no task/worker/verification batches for that goal; next action should explain the pause.
- `blocked`: no task/worker/verification batches; next action should name the blocker.
- `complete`: no dispatch batches; next action should be review/archive only if needed.
- `archived`: omit dispatch batches and mark the goal non-active in loop output.

When all slices have promoted task evidence, the loop should report a closure-decision state rather than marking the goal complete. The next action should be:

```bash
devflow goal complete <goal_id> --reason "all task slices promoted and reviewed"
```

This preserves the current rule: completion is evidence-backed and human-controlled.

## Batch Execution Contract

Milestone 14 should not invent new batch execution engines. It should harden and dogfood existing commands:

```bash
devflow freshness create-batch <goal_id> <batch_id>
devflow freshness worker-batch <goal_id> <batch_id> --max-parallel 2
devflow freshness verify-batch <goal_id> <batch_id> --max-parallel 2
devflow freshness run --max-iterations 3 --create-tasks
devflow freshness run --max-iterations 3 --execute-workers
devflow freshness run --max-iterations 3 --execute-verification
```

Acceptance for dispatch:

- Dispatch still refuses unsafe Git state.
- Dispatch still uses existing task/workspace locks.
- Dispatch writes derived batch reports only.
- Dispatch stops after changed task/workspace/evidence state so checkpoint/push opportunities surface before additional work.
- Failed worker or verification subprocesses are reported per task without hiding successful lanes.

## Operating Layer Contract

The local operating layer should expose goal lifecycle state as derived display data:

- Goal cards include lifecycle and reason.
- Orchestrator next safe action prefers lifecycle repair or activation when relevant.
- Paused, blocked, complete, and archived goals do not show ready dispatch buttons.
- Active goals show existing task/worker/verification batch recommendations.

The browser remains a guarded derived surface. It should not execute lifecycle mutations in this milestone unless those commands are separately classified and approved through the existing supervisor approval model. Read-only display is sufficient for the milestone.

## Supervisor Policy Contract

Supervisor classification should be explicit:

- `devflow goal list`, `show`, `status`, `next`, `slices`: read-only.
- `devflow goal activate`, `pause`, `block`, `complete`, `archive`: approval-required goal/task state mutation.
- Freshness read-only projection commands remain read-only.
- Freshness create/worker/verify batch commands remain approval-required mutations or runtimes according to existing policy.

## Data Model Boundaries

Canonical:

- `.devflow/goals/<goal_id>/goal.yaml`
- `.devflow/goals/<goal_id>/goal-state.yaml`
- `.devflow/goals/<goal_id>/events.jsonl`
- `.devflow/goals/<goal_id>/task-slices.yaml`
- `.devflow/tasks/<task_id>/task.yaml`
- `.devflow/tasks/<task_id>/goal-link.yaml`
- `.devflow/tasks/<task_id>/verification.json`

Derived:

- `.devflow/goals/<goal_id>/loop-state.json`
- `.devflow/freshness/latest.json`
- `.devflow/freshness/events.jsonl`
- `.devflow/freshness/task-batch-runs/*.json`
- `.devflow/freshness/worker-runs/*.json`
- `.devflow/freshness/verification-runs/*.json`
- operating-layer snapshots

No derived artifact may become the source of truth for lifecycle decisions.

## Implementation Notes

Likely files:

- `src/devflow/control_room/goal_lifecycle.py`: new lifecycle service, schema, rendering helpers, event append logic.
- `src/devflow/control_room/goals.py`: initialize `goal-state.yaml` for newly created goals.
- `src/devflow/control_room/goal_projection.py`: include lifecycle fields in `GoalStatusProjection`.
- `src/devflow/control_room/goal_loop.py`: suppress dispatch projections for non-active goals and emit closure-decision next actions.
- `src/devflow/control_room/freshness.py`: include lifecycle findings and state hash inputs.
- `src/devflow/control_room/operating_layer.py`: expose lifecycle fields in goal board/spec board projections.
- `src/devflow/control_room/supervisor_surface.py`: classify new goal lifecycle commands.
- `src/devflow/cli.py`: wire lifecycle commands.

Focused tests should live near:

- `tests/test_goal_lifecycle.py`
- `tests/test_freshness_loop.py`
- `tests/test_goal_projection.py`
- `tests/test_operating_layer.py`
- `tests/test_supervisor_operating_surface.py`

## Acceptance Criteria

Milestone 14 is done when:

1. New goals get `goal-state.yaml` with `lifecycle: active`.
2. Existing goals without lifecycle state still render safely and recommend activation.
3. `goal activate/pause/block/complete/archive` write canonical lifecycle evidence and hash-chained goal events.
4. `goal status` and `goal next` show lifecycle-aware state and next commands.
5. `freshness loop` does not project task, worker, or verification dispatch for paused, blocked, complete, or archived goals.
6. `freshness loop` projects closure-decision next action when all slices have promoted task evidence.
7. The operating-layer snapshot includes lifecycle state for goal display.
8. Supervisor policy classifies lifecycle mutations as approval-required state changes.
9. A dogfood test demonstrates an active goal moving through task creation, worker batch, verification batch, and review readiness without automatic promotion or completion.
10. Docs and handoff identify Milestone 14 as planned next work without describing it as current runtime.

## Verification Plan

Minimum focused suite:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest \
  tests/test_goal_lifecycle.py \
  tests/test_goal_projection.py \
  tests/test_freshness_loop.py \
  tests/test_operating_layer.py \
  tests/test_supervisor_operating_surface.py \
  -v
```

CLI smoke:

```bash
PYTHONPATH=src:. .venv/bin/devflow goal init G-9998 --from docs/superpowers/specs/2026-06-13-goal-execution-control-loop-design.md
PYTHONPATH=src:. .venv/bin/devflow goal status G-9998
PYTHONPATH=src:. .venv/bin/devflow goal pause G-9998 --reason "smoke pause"
PYTHONPATH=src:. .venv/bin/devflow freshness loop --json
```

Use a temporary directory or test fixture for CLI smoke that mutates `.devflow/`.

Final milestone verification should include:

```bash
git diff --check
PYTHONPATH=src:. .venv/bin/devflow dogfood run --suite production-readiness
PYTHONPATH=src:. .venv/bin/devflow git status
```

Do not claim milestone completion until fresh verification evidence exists and active docs no longer preserve stale Milestone 13-as-next-priority wording.
