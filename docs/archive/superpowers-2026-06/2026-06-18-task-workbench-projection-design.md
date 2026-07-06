# Task Workbench Projection Design

Date: 2026-06-18
Status: proposed for handoff

## Goal

Make the operating-layer UI usable by giving task-centered surfaces one deeper read model.

The Task workbench projection should answer, from filesystem-backed Dev-Flow state:

- Which task should the operator look at first?
- Which tasks are visible in Worker lanes?
- Which tasks belong in the Review queue?
- Which evidence belongs in the Evidence stream?
- Which worker/model is attached to each task?
- Which controls should the operator see now?
- What is the next safe action?

## Product Boundary

This is a read-model and UI-usability refactor. It must not create a database, spawn workers, call provider APIs, mutate canonical task state, verify tasks, promote tasks, push, publish, or open PRs.

The filesystem remains the source of truth. The browser continues to execute only the existing approval-gated action path.

## Current Friction

The active UI already has useful pieces, but they are spread across shallow Modules:

- `operating_layer.py` composes the whole snapshot and also decides lanes, focus task, task cards, review loop, evidence, gate receipts, and worker activity.
- `status_projection.py` owns task status and dashboard action logic.
- `review_readiness.py` owns review state, blockers, score, and next command.
- `git_worktree.py` and `local_worker_lane.py` expose worker-lane summaries.
- `operating_layer_script.py` reinterprets task lane and command strings to render Worker lanes, Review queue, Evidence stream, launchpad controls, and focus overlay actions.

The result is poor Locality. A small product fix like "show the task that system health says is active" or "make the retry/verify/promote control visible in the right place" can require touching multiple Modules and tests.

## Proposed Module

Add a Task workbench projection Module under:

```text
src/devflow/control_room/task_workbench.py
```

The Module should be read-only. Its Interface should be narrow enough that callers do not need to know how task status, review readiness, worker evidence, and promotion readiness are assembled.

Recommended public Interface:

```python
def build_task_workbench(root: Path, *, project_id: str | None = None) -> TaskWorkbench:
    ...
```

Recommended responsibilities behind that Interface:

- load task status projections
- derive lane membership and lane order
- choose the focus task
- produce task summaries for Worker lanes and the Next Task launchpad
- produce review queue items
- produce evidence stream pointers
- produce gate progress receipts
- produce worker/model activity rows
- produce task-scoped control descriptors
- expose warnings when optional evidence is missing or unreadable

`operating_layer.py` should become an Adapter that maps the Task workbench projection into the existing `OperatingLayerSnapshot` schema. That keeps snapshot schema churn low while moving product rules to the deeper Module.

## Interface Shape

The exact Pydantic model names are implementation details, but the Task workbench Interface should expose these concepts:

- `focus_task_id`
- `lanes`
- `tasks`
- `review_queue`
- `evidence_stream`
- `gate_receipts`
- `worker_activity`
- `counts`
- `warnings`

Each task summary should include:

- task id and title
- definition of done
- canonical status and display status
- lane
- worker/model label
- workspace path
- verification status and exit code
- review state and blockers
- promotion readiness and blockers
- latest event/output
- evidence paths
- next safe action
- controls available now

The Interface should make controls data-driven. The first pass can preserve existing command strings, but controls should be named by intent, for example `inspect`, `start_shell`, `verify`, `review_preview`, `promote`, `retry`, `close`, and `cleanup_preview`. This prepares candidate 2 without forcing it into the first refactor.

## Adapters And Seams

Expected Adapters behind the Task workbench Seam:

- `status_projection.py` for canonical task status, display status, verification, and dashboard action.
- `review_readiness.py` for review state, blockers, score, and review next command.
- `git_worktree.py` for git worker lane evidence and promotion readiness.
- `local_worker_lane.py` for local model/patch worker evidence.
- `agent_evidence.py` and task artifact readers for worker/model evidence summaries.
- Existing path helpers for relative evidence paths and artifact previews.

Expected callers:

- `operating_layer.py` for browser snapshot composition.
- Future focused tests for task-workbench behavior.
- Later, browser action/capability work can consume task controls from the same projection.

## Acceptance Criteria

The implementation is acceptable when:

1. `devflow operating-layer snapshot --json` remains read-only and preserves the current public schema unless changes are explicitly additive.
2. A newly created task appears in Worker lanes, is selected or selectable in the launchpad, shows worker/model identity, and exposes a concrete start action.
3. A completed task with worker output appears as needing verification and exposes verify action data.
4. A verified task with promotion readiness appears as ready to promote/review and exposes promotion preview or promote action data.
5. Failed, blocked, timeout, and verification-failed tasks appear in the Review queue with the reason and useful inspect/retry/verify command.
6. Closed tasks do not pollute the first-viewport Worker lanes, but cleanup preview remains available where supported.
7. System health active counts can be reconciled to visible task ids.
8. Existing browser behavior for selecting a task, running a shell worker, running verification, and reviewing promotion still passes.

## Non-Goals

- No visual redesign in the first pass.
- No new frontend framework.
- No broad JavaScript rewrite.
- No new database or daemon.
- No Hyperplane validation.
- No provider-backed worker execution.
- No cleanup apply, sync, push, PR, or publication from the browser.

## Test Strategy

Add focused task-workbench tests first. They should exercise the deeper Interface directly instead of requiring a browser.

Recommended new test file:

```text
tests/test_task_workbench_projection.py
```

Recommended scenarios:

- created task projects into `new` lane with `start_shell` or start control
- completed task projects into `needs_verification`
- failed verification projects into Review queue with inspect/verify evidence
- verified task with promotion preview projects into `ready_to_promote`
- local worker evidence names worker/model and evidence paths
- closed task is excluded from active Worker lanes but can expose cleanup preview

Then keep existing operating-layer tests as integration coverage:

- `tests/test_operating_layer.py::test_operating_layer_snapshot_json_is_read_only_contract`
- `tests/test_operating_layer.py::test_operating_layer_groups_verification_and_promotion_lanes`
- `tests/test_operating_layer.py::test_operating_layer_snapshot_includes_browser_review_loop_summary`
- `tests/test_operator_ui_browser.py::test_worker_row_selects_launchpad_and_runs_inline_shell_worker`
- `tests/test_operator_ui_browser.py::test_task_switcher_and_seeded_evidence_lane`

If the implementation changes layout or first-viewport rendering, run operating-layer visual QA and browser tests. If it only extracts read-model logic while preserving output, targeted Python tests are enough for the first pass.

## Risks

- The existing `OperatingLayerSnapshot` models live in `operating_layer.py`; moving too much at once could cause import cycles. Prefer a new internal projection model and a small Adapter in `operating_layer.py`.
- There are already unrelated UI/code changes in the worktree. The implementation agent must not revert them.
- Candidate 2, browser action/capability deepening, is adjacent. Do not accidentally widen browser mutation authority while adding task controls.
- Snapshot schema churn will make browser and tests noisy. Preserve the public schema for the first pass unless an additive field is necessary.

## Product Boundary Self-Check

- This builds the control room, not another coding agent.
- It makes work more visible and controllable.
- It increases Locality around task usability rules.
- It gives tests more Leverage by moving behavior behind a focused Interface.
- It keeps state sacred: task artifacts remain authoritative.
