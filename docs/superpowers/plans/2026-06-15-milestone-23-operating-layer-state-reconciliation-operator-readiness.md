# Milestone 23 Operating Layer State Reconciliation & Operator Readiness Implementation Plan

Status: planned. This file is the execution plan for `task-0137`.

> For agentic workers: implement this plan task-by-task. Keep all new product logic under `src/devflow/control_room/`; top-level CLI edits may only bridge to control-room functions.

**Goal:** Make status, scheduler, dashboard, supervisor, and operating-layer snapshot/UI agree on counts, goal lifecycle blockers, stale-task guidance, and next-safe-action behavior while showing plain descriptive task/project names first.

**Architecture:** Add or harden a shared read-only operator-readiness projection that normalizes task/goal/project display identity, lifecycle gating, stale directive warnings, count buckets, and next-safe-action priority. Consume that projection from existing surfaces instead of letting each surface invent its own answer.

**Tech Stack:** Python 3, Typer CLI, Pydantic models, filesystem artifacts, existing Dev-Flow projection modules, pytest, operating-layer browser snapshot tests.

## File Structure

- Create or modify `src/devflow/control_room/operator_readiness.py`: shared display identity, count, blocker, stale directive, and next-safe-action projection.
- Modify `src/devflow/control_room/status_projection.py` or existing status composition code to consume shared operator readiness.
- Modify `src/devflow/control_room/scheduler_projection.py` to lifecycle-gate worker-ready tasks consistently.
- Modify `src/devflow/control_room/dashboard.py` to render shared counts and plain-language labels.
- Modify `src/devflow/control_room/supervisor_surface.py` to include shared operator summary and warnings.
- Modify `src/devflow/control_room/operating_layer.py` and UI asset modules only as needed to consume shared labels/counts.
- Add focused tests such as `tests/test_operator_readiness.py`.
- Extend existing scheduler, dashboard, supervisor, status, and operating-layer tests.
- Extend `src/devflow/control_room/dogfood.py` with an operator reconciliation production-readiness case.
- Update active docs and write an implementation handoff at completion.

## Guardrails

- Keep the projection read-only.
- Do not mutate `.devflow/tasks`, `.devflow/goals`, `.devflow/freshness`, question records, verification evidence, Git state, or browser state from the projection.
- Do not add provider calls, autonomous routing, auto-resume, auto-verification, auto-promotion, commits, pushes, PRs, databases, hidden memory, or browser mutation expansion.
- Keep command strings as operational ids, but human-facing labels should use descriptive names first.
- Preserve existing supervisor approval classification.

---

## Task 1: Characterize Current Operator Mismatches

**Files:**
- Create `tests/test_operator_readiness.py`
- Read only relevant existing tests for scheduler/status/operating-layer fixtures

- [ ] Build a small fixture with:
  - a descriptive project/repo name
  - one goal with missing lifecycle state
  - one task titled like `G-0004 • Slice 2`
  - one descriptive task title
  - one stale freshness recommendation
- [ ] Assert the desired shared operator projection:
  - generated-name task resolves to a descriptive display title
  - missing-lifecycle goal blocks worker-ready status
  - next safe action is lifecycle repair or inspection, not worker dispatch
  - ids remain available as secondary metadata
- [ ] Run the focused test and confirm it fails before implementation.

Verification:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_operator_readiness.py -q
```

## Task 2: Add Shared Operator Readiness Projection

**Files:**
- Create or modify `src/devflow/control_room/operator_readiness.py`
- Read only the narrow projection helpers needed for task, goal, scheduler, freshness, and question state

- [ ] Define Pydantic models for display identity, count buckets, blockers, warnings, and next-safe-action.
- [ ] Derive project, goal, task, and worker display names from existing artifacts.
- [ ] Normalize count buckets from canonical task and goal state.
- [ ] Add lifecycle gating for goal-linked tasks.
- [ ] Detect stale directives when freshness or scheduler recommendations point at inactive, missing-lifecycle, closed, or superseded work.
- [ ] Implement next-safe-action priority from the design spec.
- [ ] Keep all functions read-only and deterministic.

Verification:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_operator_readiness.py -q
```

## Task 3: Thread Projection Into CLI Status, Scheduler, And Dashboard

**Files:**
- Modify status composition module
- Modify `src/devflow/control_room/scheduler_projection.py`
- Modify `src/devflow/control_room/dashboard.py`
- Extend existing focused tests

- [ ] Make `status --json` expose shared operator counts, warnings, and next safe action.
- [ ] Make scheduler ready/blocked counts use lifecycle-gated operator readiness.
- [ ] Make dashboard text use descriptive labels and the shared next-safe-action reason.
- [ ] Preserve existing JSON fields where external callers may depend on them; add fields rather than breaking consumers when possible.

Verification:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_scheduler_projection.py tests/test_control_room_dashboard.py -q
PYTHONPATH=src:. .venv/bin/devflow status --json
PYTHONPATH=src:. .venv/bin/devflow scheduler status --json
PYTHONPATH=src:. .venv/bin/devflow dashboard
```

## Task 4: Thread Projection Into Supervisor And Operating Layer

**Files:**
- Modify `src/devflow/control_room/supervisor_surface.py`
- Modify `src/devflow/control_room/operating_layer.py`
- Modify UI asset modules only for label/rendering changes
- Extend existing supervisor and operating-layer tests

- [ ] Add shared operator summary and warnings to supervisor packet output.
- [ ] Update operating-layer snapshot to use shared labels and counts.
- [ ] Ensure first-viewport directive and next action explain lifecycle/stale blockers plainly.
- [ ] Keep Action Rail command classification and browser mutation gates unchanged.
- [ ] Verify generated ids remain visible but secondary.

Verification:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_supervisor_operating_surface.py tests/test_operating_layer.py -q
PYTHONPATH=src:. .venv/bin/devflow supervisor packet --json
PYTHONPATH=src:. .venv/bin/devflow operating-layer snapshot --json
```

## Task 5: Add Dogfood Coverage

**Files:**
- Modify `src/devflow/control_room/dogfood.py`
- Modify `tests/test_dogfood_harness.py`

- [ ] Add an operator-reconciliation case with lifecycle, stale directive, question, generated-name, and descriptive-name fixtures.
- [ ] Assert the major surfaces agree on count buckets and next-safe-action class.
- [ ] Ensure dogfood closes any task evidence it creates as evidence-only.

Verification:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_dogfood_harness.py -q
PYTHONPATH=src:. .venv/bin/devflow dogfood run --suite production-readiness
```

## Task 6: Close The Milestone

**Files:**
- Update `docs/control-room-mvp.md`
- Update `docs/mvp-contract.md`
- Update `docs/roadmap.md`
- Update `docs/agent-handoff.md`
- Add implementation handoff under `docs/handoffs/`

- [ ] Mark Milestone 23 implemented only after code and dogfood verification pass.
- [ ] Run focused tests plus broader suite appropriate to touched modules.
- [ ] Run stale-context searches for old priority wording and confusing future-tense claims.
- [ ] Check Dev-Flow Git status is clean.
- [ ] Do not push or publish without explicit human approval.

Suggested final verification:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_operator_readiness.py tests/test_scheduler_projection.py tests/test_control_room_dashboard.py tests/test_supervisor_operating_surface.py tests/test_operating_layer.py tests/test_dogfood_harness.py -q
PYTHONPATH=src:. .venv/bin/devflow dogfood run --suite production-readiness
PYTHONPATH=src:. .venv/bin/devflow status --json
```
