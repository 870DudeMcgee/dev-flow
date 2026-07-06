# Operating-Layer Task Workbench Adapter Thinning Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` or `executing-plans` to implement this plan task-by-task. Track progress with the checkbox steps below.

Date: 2026-06-25
Status: ready for implementation handoff

## Goal

Finish cleanup slice 1 after the Task workbench refactor: make `src/devflow/control_room/operating_layer.py` a thinner Adapter over `src/devflow/control_room/task_workbench.py` for task-centered state.

The Task workbench Module should own the Interface for:

- selected/focus task
- task lanes
- task cards and controls
- promotion candidates
- evidence stream
- gate receipts
- worker activity
- task-centered review loop state

`operating_layer.py` should keep public snapshot models and non-task surface assembly, but it should not keep duplicate task-workbench logic.

## Current State

Start from clean `main` at commit `5eba865b` unless newer work has landed.

Recent verification before this plan:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_task_workbench_projection.py tests/test_brainstorm_task_bridge.py tests/test_operating_layer.py -q
# 80 passed

PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_architecture_boundaries.py tests/test_code_map_check.py tests/test_mvp_boundaries.py tests/test_project_scope_docs.py -q
# 21 passed

PYTHONPATH=src:. .venv/bin/python -m devflow.cli operating-layer visual-qa --json
# passed
```

Graphify was refreshed locally from current `HEAD` and reported:

- `647 files`
- `8675 nodes`
- `20879 edges`
- `521 communities`
- no dangling endpoints, duplicate edges, or relation variants

`graphify-out/` and `.devflow/operating-layer/` are ignored generated evidence. Do not commit them.

## Non-Goals

- Do not redesign the browser UI.
- Do not widen browser mutation safety.
- Do not change task lifecycle, verification, promotion, or worker runtime behavior.
- Do not use Hyperplane for validation.
- Do not run full pytest unless a broad shared behavior change escapes this slice.
- Do not push, publish, or promote without explicit human approval.

## Files Likely To Modify

- `src/devflow/control_room/operating_layer.py`
- `tests/test_operating_layer.py`
- `tests/test_task_workbench_projection.py` only if the workbench Interface needs one extra assertion
- `docs/architecture/operating-layer-ui-deepening-backlog.md`
- `docs/architecture/graphify-architecture-baseline.md` or `docs/architecture/control-room-cleanup-checkpoint-2026-06-25.md` only if recording refreshed Graphify metrics

## Task 0: Confirm Baseline And Working Tree

- [ ] Run:

```bash
git status --short
PYTHONPATH=src:. .venv/bin/python -m devflow.cli git status
```

Expected:

- normal Git status is clean
- Dev-Flow status is clean and safe for worker writes
- ignored generated evidence may exist, but it must not appear in normal `git status --short`

- [ ] Run the minimum baseline:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_task_workbench_projection.py tests/test_operating_layer.py::test_operating_layer_snapshot_json_is_read_only_contract tests/test_operating_layer.py::test_operating_layer_snapshot_includes_browser_review_loop_summary tests/test_operating_layer.py::test_operating_layer_groups_verification_and_promotion_lanes -q
```

Expected:

- all selected tests pass

## Task 1: Lock The Adapter Contract With A Focused Test

Files:

- Modify: `tests/test_operating_layer.py`

- [ ] Add a test named `test_operating_layer_reuses_task_workbench_for_task_centered_snapshot_fields`.

Use the existing `CliRunner` style in `tests/test_operating_layer.py`. Create a small task set that covers:

- created task
- completed task needing verification
- verified task ready for promotion

Build both:

```python
workbench = build_task_workbench(tmp_path)
snapshot = build_operating_layer_snapshot(tmp_path)
```

Assert these snapshot fields are direct Adapter mappings from the workbench:

- `snapshot.focus_task_id == workbench.focus_task_id`
- lane names and `task_ids` match
- task ids and task lanes match
- `promotion_desk` matches `workbench.promotion_candidates`
- `evidence` matches `workbench.evidence_stream`
- `gate_receipts` matches `workbench.gate_receipts`
- `worker_activity` matches `workbench.worker_activity`
- with no question/inbox overlay, `snapshot.review_loop.status`, `headline`, counts, evidence summary, browser mutation lists, and `next_safe_action` match `workbench.review_loop`

- [ ] Keep the existing failed-verification pressure test passing:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_operating_layer.py::test_operating_layer_review_loop_flags_failed_verification_decision_pressure -q
```

This preserves the current human-decision behavior while the adapter is thinned.

## Task 2: Make Review Loop Adapt From Task Workbench

Files:

- Modify: `src/devflow/control_room/operating_layer.py`

- [ ] Replace the call to `_review_loop_summary(...)` in `build_operating_layer_snapshot()` with a conversion from `task_workbench.review_loop`.
- [ ] Add or rename a small helper such as `_operating_review_loop_from_workbench(...)`.
- [ ] The helper should:
  - convert the workbench review loop into `OperatingLayerReviewLoop`
  - preserve `browser_allowed_mutations`, `browser_blocked_mutations`, counts, evidence summary, retention label, and next safe action from the workbench
  - overlay open question/human-decision inbox pressure only when `inbox` has items with kind `question`, `blocked_task`, `task_attention`, or `human_decision`
  - keep the current blocked-decision headline format: `1 decision item needs attention`

Run:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_operating_layer.py::test_operating_layer_snapshot_includes_browser_review_loop_summary tests/test_operating_layer.py::test_operating_layer_review_loop_flags_failed_verification_decision_pressure tests/test_operating_layer.py::test_project_scoped_operating_layer_snapshot_scopes_task_commands -q
```

Expected: pass.

## Task 3: Delete Orphaned Task-Centered Helpers From `operating_layer.py`

Files:

- Modify: `src/devflow/control_room/operating_layer.py`

After Task 2, these helpers should be unused in `operating_layer.py` and should be removed if `rg` confirms no call sites:

- `_focus_task_id`
- `_worker_activity`
- `_normalized_worker`
- `_worker_profile`
- `_worker_code`
- `_worker_state`
- `_worker_state_class`
- `_worker_task_failed`
- `_worker_task_verified_or_ready`
- `_gate_receipts`
- `_task_actions`
- `_merge_readiness_exists`

Keep `_scope_task_command()` and `_action()` because project, goal, idea, inbox, and action-rail surfaces still use them.

`_plain_worker_name()` is currently used by `_plain_feed_kind()`. Either keep it, or rename it to a more generic `_plain_label()` and update that call. Do not keep worker-specific naming helpers just for dead worker-activity code.

Run:

```bash
rg -n "_focus_task_id\\(|_worker_activity\\(|_gate_receipts\\(|_task_actions\\(|_merge_readiness_exists\\(|_worker_profile\\(|_worker_state\\(|_worker_task" src/devflow/control_room/operating_layer.py
```

Expected:

- no matches except lines intentionally retained with a clear non-task-workbench purpose

## Task 4: Tighten The Adapter Shape

Files:

- Modify: `src/devflow/control_room/operating_layer.py`

- [ ] Keep `_operating_task_from_workbench()` as the single task-card conversion point.
- [ ] Keep public `OperatingLayer*` models if they are part of the snapshot contract.
- [ ] Remove imports that only supported deleted helpers.
- [ ] Confirm `TaskStatusProjection` remains imported only if still needed by `_questions()` or `_inbox_items()`.
- [ ] Do not move project, goal, idea greenhouse, scheduler, local model runtime, or agent catalog behavior into `task_workbench.py`.

Run:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_operating_layer.py::test_operating_layer_snapshot_json_is_read_only_contract tests/test_operating_layer.py::test_operating_layer_groups_verification_and_promotion_lanes tests/test_operating_layer.py::test_operating_layer_snapshot_includes_compact_agent_evidence_summary -q
```

Expected:

- pass

## Task 5: Update Architecture Notes

Files:

- Modify: `docs/architecture/operating-layer-ui-deepening-backlog.md`
- Optional modify: `docs/architecture/control-room-cleanup-checkpoint-2026-06-25.md`
- Optional modify: `docs/architecture/graphify-architecture-baseline.md`

- [ ] Add a dated checkpoint under Candidate 1 saying the Task workbench projection is now the task-centered Interface and `operating_layer.py` has been thinned to an Adapter.
- [ ] If Graphify is refreshed, record only lightweight metrics in an architecture checkpoint doc. Do not commit `graphify-out/`.
- [ ] Do not rewrite future architecture docs as current runtime behavior.

## Task 6: Verification

Minimum verification:

```bash
git diff --check
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_task_workbench_projection.py tests/test_operating_layer.py -q
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_architecture_boundaries.py tests/test_code_map_check.py tests/test_mvp_boundaries.py tests/test_project_scope_docs.py -q
PYTHONPATH=src:. .venv/bin/python -m devflow.cli map check
PYTHONPATH=src:. .venv/bin/python -m devflow.cli operating-layer visual-qa --json
PYTHONPATH=src:. .venv/bin/python -m devflow.cli git status
```

If browser-rendered task controls, Worker lanes, Review queue, or Evidence stream change, also run:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_operator_ui_browser.py::test_task_switcher_and_seeded_evidence_lane tests/test_operator_ui_browser.py::test_worker_row_selects_launchpad_and_runs_inline_shell_worker tests/test_operator_ui_browser.py::test_product_stage_contains_task_launchpad_review_and_evidence -q
```

Graphify verification:

```bash
.venv/bin/graphify update .
.venv/bin/graphify diagnose multigraph --json --graph graphify-out/graph.json
.venv/bin/graphify explain "control_room_operating_layer" --graph graphify-out/graph.json
.venv/bin/graphify explain "control_room_task_workbench" --graph graphify-out/graph.json
```

Expected:

- no graph structural errors
- `control_room_operating_layer` degree does not increase from the pre-slice value of `118`
- if the degree does not decrease, explain why in the handoff

## Done Means

- `operating_layer.py` no longer contains unused duplicate task-workbench helpers.
- `build_operating_layer_snapshot()` maps task-centered fields from `build_task_workbench()`.
- Review loop behavior still preserves browser safety and human-decision pressure.
- Snapshot contract tests and Task workbench tests pass.
- Operating-layer visual QA passes.
- Architecture docs record the Candidate 1 checkpoint.
- `graphify-out/` remains ignored generated evidence.

## Rollback Notes

This slice should be mostly deletion plus adapter rewiring. If a regression appears, revert only the adapter changes in `operating_layer.py` and the related test/doc edits from this slice. Do not revert the existing Task workbench, browser capability, evidence detail, or Brainstorm pipeline Modules.
