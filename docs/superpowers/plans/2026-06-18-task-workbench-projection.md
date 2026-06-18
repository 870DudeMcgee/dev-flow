# Task Workbench Projection Implementation Plan

Date: 2026-06-18
Status: ready for implementation handoff

## Goal

Implement the Task workbench projection Module described in `docs/superpowers/specs/2026-06-18-task-workbench-projection-design.md`.

The first implementation should improve architecture and testability without changing the operator-facing browser contract more than necessary.

## Files To Add

- `src/devflow/control_room/task_workbench.py`
- `tests/test_task_workbench_projection.py`

## Files Likely To Modify

- `src/devflow/control_room/operating_layer.py`
- `tests/test_operating_layer.py`
- `tests/test_operator_ui_browser.py` only if browser behavior changes
- `docs/architecture/local-operating-layer-ui.md` only if the active architecture description needs alignment after implementation

## Task 1: Lock The Current Task Workbench Behavior

- [ ] Add `tests/test_task_workbench_projection.py`.
- [ ] Create fixtures using existing CLI helpers or persistence helpers for these task states:
  - created
  - completed with worker output
  - verification failed
  - verified and ready for promotion
  - closed
  - local worker evidence when practical
- [ ] Assert the intended Task workbench behavior directly:
  - focus task priority
  - lane membership
  - visible active task ids
  - worker/model label
  - next safe action
  - available controls
  - evidence paths

Run:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_task_workbench_projection.py -q
```

Expected before implementation: fail because the Module does not exist.

## Task 2: Add The Read-Only Task Workbench Module

- [ ] Add `src/devflow/control_room/task_workbench.py`.
- [ ] Define a small internal Pydantic model set for the workbench projection.
- [ ] Implement `build_task_workbench(root: Path, *, project_id: str | None = None) -> TaskWorkbench`.
- [ ] Keep the Module read-only.
- [ ] Use existing Modules as Adapters:
  - `status_projection.py`
  - `review_readiness.py`
  - `git_worktree.py`
  - `local_worker_lane.py`
  - `agent_evidence.py`
  - existing path and artifact helpers
- [ ] Keep task controls intent-labeled even if they still carry command strings.

Run:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_task_workbench_projection.py -q
```

Expected: pass.

## Task 3: Adapt The Existing Operating-Layer Snapshot

- [ ] Refactor `build_operating_layer_snapshot()` so task-centered fields come from `build_task_workbench()`.
- [ ] Preserve the existing public `OperatingLayerSnapshot` schema where possible:
  - `focus_task_id`
  - `lanes`
  - `tasks`
  - `evidence`
  - `gate_receipts`
  - `worker_activity`
  - `review_loop`
- [ ] Leave non-task-wide fields in `operating_layer.py`:
  - project identity
  - freshness
  - goals and spec board
  - multi-project overview
  - operator readiness
  - agent catalog
  - action rail
- [ ] Keep `_scope_task_command()` behavior consistent for project-scoped snapshots.

Run:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest \
  tests/test_task_workbench_projection.py \
  tests/test_operating_layer.py::test_operating_layer_snapshot_json_is_read_only_contract \
  tests/test_operating_layer.py::test_operating_layer_groups_verification_and_promotion_lanes \
  tests/test_operating_layer.py::test_operating_layer_snapshot_includes_browser_review_loop_summary \
  tests/test_operating_layer.py::test_operating_layer_snapshot_includes_scheduler_summary \
  -q
```

Expected: pass.

## Task 4: Repair Any Browser Drift

Only do this if Task 3 changes snapshot details used by the browser.

- [ ] Confirm Worker lanes still show active tasks and no closed history noise.
- [ ] Confirm Review queue still selects the promotion candidate.
- [ ] Confirm Evidence stream still links task evidence.
- [ ] Confirm shell start and verification controls still work from the launchpad.

Run, when practical:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest \
  tests/test_operator_ui_browser.py::test_worker_row_selects_launchpad_and_runs_inline_shell_worker \
  tests/test_operator_ui_browser.py::test_review_queue_selects_promotion_candidate_and_runs_preview \
  tests/test_operator_ui_browser.py::test_task_switcher_and_seeded_evidence_lane \
  tests/test_operator_ui_browser.py::test_worker_lanes_are_overview_not_primary_action_surface \
  -q
```

Expected: pass.

## Task 5: Document The Final Interface

- [ ] Update `docs/architecture/local-operating-layer-ui.md` only if the implementation changes the active architecture description.
- [ ] Add a short note to `docs/architecture/control-room-refactoring-integration.md` only if the Task workbench Module becomes an integrated current Module.
- [ ] Avoid stale future-tense docs. If the plan changes during implementation, update this plan or mark the changed part completed/deferred.

## Verification Policy

Minimum focused verification:

```bash
git diff --check
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_task_workbench_projection.py -q
PYTHONPATH=src:. .venv/bin/python -m pytest \
  tests/test_operating_layer.py::test_operating_layer_snapshot_json_is_read_only_contract \
  tests/test_operating_layer.py::test_operating_layer_groups_verification_and_promotion_lanes \
  tests/test_operating_layer.py::test_operating_layer_snapshot_includes_browser_review_loop_summary \
  -q
```

If browser rendering or controls change:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_operator_ui_browser.py -q
```

If the first viewport changes visually, also run:

```bash
devflow operating-layer visual-qa --write-current --json
```

## Handoff Notes For The Implementation Agent

- You are not alone in the codebase. There are unrelated code/UI changes in the worktree. Do not revert them.
- Keep edits focused under `src/devflow/control_room/` and `tests/`.
- Preserve browser mutation safety. This task should not widen approved browser commands.
- Prefer extraction plus tests over a visual redesign.
- Do not use Hyperplane for validation.
- Treat this as current operating-layer work, not future provider-runtime architecture.

## Done Means

- The Task workbench projection Module exists and is tested directly.
- `operating_layer.py` delegates task-centered projection behavior to it.
- Existing operating-layer snapshot behavior still passes focused tests.
- The browser still shows active tasks, next actions, worker/model labels, Review queue items, and Evidence stream items.
- The next implementation step can be candidate 2: Browser action/capability Module.
