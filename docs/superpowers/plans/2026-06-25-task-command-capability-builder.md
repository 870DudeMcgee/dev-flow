# Task Command Capability Builder Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` or `executing-plans` to implement this plan task-by-task. Track progress with the checkbox steps below.

Date: 2026-06-25
Status: ready for implementation handoff

## Goal

Finish the next control-room cleanup slice by making `src/devflow/control_room/browser_task_capabilities.py` the single Module that owns task command templates, project scoping, typed capability construction, labels, required inputs, deduplication, and supervisor classification.

After this slice:

- `task_workbench.py` should decide which task controls/actions are available from task state.
- `browser_task_capabilities.py` should decide how those intents become scoped commands and typed capabilities.
- `operating_layer.py` should reuse the shared task command scoping helper instead of carrying its own copy.
- `operating_layer_script.py` may keep legacy fallback inference for older snapshots, but current snapshots should not depend on JavaScript command inference.
- `operating_layer_server.py` remains the approval-gated execution Adapter. Do not loosen its validation.

## Current State

Start from clean `main` after commit:

```text
39dd0c6 refactor: thin operating layer task workbench adapter
```

Current friction:

- `browser_task_capabilities.py` classifies command strings but does not build canonical task commands.
- `task_workbench.py` still hardcodes task command templates and owns `_scope_task_command()`.
- `operating_layer.py` still owns a separate `_scope_task_command()` for task-linked project, goal, and inbox commands.
- `operating_layer_script.py` still has legacy command inference helpers. Those can stay as compatibility fallback, but the current Python snapshot should provide complete capability metadata.

## Non-Goals

- Do not redesign the browser UI.
- Do not remove JavaScript legacy fallback unless a test proves every current snapshot path provides typed capabilities.
- Do not change browser action approval semantics.
- Do not change CLI command behavior.
- Do not widen allowed browser commands.
- Do not use Hyperplane for validation.
- Do not push, publish, promote, or open a PR.
- Do not commit `graphify-out/`.

## Files Likely To Modify

- `src/devflow/control_room/browser_task_capabilities.py`
- `src/devflow/control_room/task_workbench.py`
- `src/devflow/control_room/operating_layer.py`
- `tests/test_browser_task_capabilities.py`
- `tests/test_task_workbench_projection.py`
- `tests/test_operating_layer.py`
- `docs/architecture/operating-layer-ui-deepening-backlog.md`
- optionally `docs/architecture/control-room-cleanup-checkpoint-2026-06-25.md`

## Task 0: Confirm Baseline

- [ ] Run:

```bash
git status --short
PYTHONPATH=src:. .venv/bin/python -m devflow.cli git status
```

Expected:

- normal Git status is clean or dirty only from this plan file if it has not been committed
- no generated `graphify-out/` files appear in normal status

- [ ] Run:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_browser_task_capabilities.py tests/test_task_workbench_projection.py tests/test_operating_layer.py::test_operating_layer_task_cards_expose_state_specific_next_actions tests/test_operating_layer.py::test_project_scoped_operating_layer_snapshot_scopes_task_commands -q
```

Expected: pass before changes.

## Task 1: Add Direct Builder Tests

Files:

- Modify: `tests/test_browser_task_capabilities.py`

- [ ] Add tests for a new `scope_task_command(command, project_id)` helper.

Required examples:

```python
assert scope_task_command("devflow task show task-0001", "demo") == "devflow task show task-0001 --project demo"
assert scope_task_command("devflow task run task-0001 --worker shell -- <command>", "demo") == "devflow task run task-0001 --worker shell --project demo -- <command>"
assert scope_task_command('devflow task verify task-0001 --shell "<command>"', "demo") == 'devflow task verify task-0001 --shell "<command>" --project demo'
assert scope_task_command("devflow project status demo", "demo") == "devflow project status demo"
```

- [ ] Add tests for a new `build_task_capability(intent, task_id, project_id=None, enabled=True)` helper.

Cover these intents:

- `inspect`
- `inspect_log`
- `task_packet`
- `review_capsule`
- `start_shell`
- `retry`
- `verify`
- `review_preview`
- `promote`
- `cleanup_preview`
- `close`

Assert command strings, labels, required inputs, safety class, and approval flags for at least:

- `start_shell`
- `verify`
- `promote`
- `close`

- [ ] Add tests for `build_task_action_capabilities(...)`.

Expected action order:

1. next safe action, when supplied
2. inspect/show task
3. review capsule
4. task log
5. task packet
6. review preview and promote when ready to promote

- [ ] Add tests for `build_task_control_capabilities(...)`.

Expected control behavior:

- created task gets `inspect`, `start_shell`, and `close`
- failed verification gets `inspect`, `verify`, and `close`
- worker failed or timeout gets `inspect`, `retry`, and `close`
- ready-to-promote task gets `review_preview`, `promote`, and `close`
- closed task gets `inspect` and `cleanup_preview` when cleanup command is available

Run:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_browser_task_capabilities.py -q
```

Expected before implementation: fail because the new helpers do not exist.

## Task 2: Deepen `browser_task_capabilities.py`

Files:

- Modify: `src/devflow/control_room/browser_task_capabilities.py`

- [ ] Add `scope_task_command(command: str, project_id: str | None) -> str`.
- [ ] Add `build_task_capability(intent: str, task_id: str, *, project_id: str | None = None, enabled: bool = True, command: str | None = None, label: str | None = None, scope: str = "task") -> BrowserTaskCapability`.
- [ ] Add `build_task_action_capabilities(task_id: str, *, project_id: str | None, next_action_command: str | None, ready_to_promote: bool) -> tuple[BrowserTaskCapability, ...]`.
- [ ] Add `build_task_control_capabilities(task_id: str, *, project_id: str | None, task_status: str, next_action_command: str | None, suggested_next_action: str | None, failed_verification: bool, worker_failed: bool, timed_out: bool, ready_to_promote: bool) -> tuple[BrowserTaskCapability, ...]`.
- [ ] Keep `intent_for_command()`, `label_for_intent()`, `label_for_command()`, `required_inputs_for_capability()`, and `dedupe_browser_task_capabilities()` as compatibility helpers.
- [ ] Export the new helpers in `__all__`.

Implementation constraints:

- Preserve current project-scoping behavior exactly, including inserting `--project <id>` before the shell command separator for `task run`.
- Preserve current placeholder commands: `<command>` and `<reason>`.
- Preserve current safety classification by calling `classify_supervisor_command()` through `build_browser_task_capability()`.
- Raise `ValueError` for unknown task capability intents. Do not silently emit arbitrary task commands.

Run:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_browser_task_capabilities.py -q
```

Expected: pass.

## Task 3: Migrate Task Workbench To The Builder

Files:

- Modify: `src/devflow/control_room/task_workbench.py`
- Modify: `tests/test_task_workbench_projection.py`

- [ ] Replace `_task_actions()` command tuple construction with `build_task_action_capabilities(...)`.
- [ ] Replace `_task_controls()` command tuple construction with `build_task_control_capabilities(...)`.
- [ ] Replace local `_scope_task_command()` usage with imported `scope_task_command()`.
- [ ] Remove `_scope_task_command()` from `task_workbench.py` if no longer used.
- [ ] Keep `TaskWorkbenchAction` and `TaskWorkbenchControl` models for now to preserve the workbench Interface.
- [ ] Convert `BrowserTaskCapability` values into those models with `model_dump()`.

Run:

```bash
rg -n "devflow task (show|capsule|log|packet|run|verify|promote|cleanup|close)|def _scope_task_command" src/devflow/control_room/task_workbench.py
```

Expected:

- no matches for hardcoded task command templates or local scoping helper
- if a match remains, it must be explained in the handoff as intentionally outside capability construction

Run:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_task_workbench_projection.py tests/test_browser_task_capabilities.py -q
```

Expected: pass.

## Task 4: Reuse Shared Scoping In Operating Layer

Files:

- Modify: `src/devflow/control_room/operating_layer.py`
- Modify: `tests/test_operating_layer.py`

- [ ] Import `scope_task_command()` from `browser_task_capabilities.py`.
- [ ] Replace local `_scope_task_command()` calls with the shared helper.
- [ ] Remove the local `_scope_task_command()` helper from `operating_layer.py` if no longer used.
- [ ] Keep `_action()` in `operating_layer.py`; it still adapts general project, goal, idea, and inbox commands into `OperatingLayerAction`.
- [ ] Confirm non-task commands are unchanged by the shared scoping helper.

Run:

```bash
rg -n "def _scope_task_command|devflow task run .*<command>|devflow task verify .*<command>|devflow task promote-preview|devflow task promote " src/devflow/control_room/operating_layer.py
```

Expected:

- no local `_scope_task_command()`
- no task command template construction outside documented non-workbench command sources

Run:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_operating_layer.py::test_operating_layer_snapshot_json_is_read_only_contract tests/test_operating_layer.py::test_operating_layer_task_cards_expose_state_specific_next_actions tests/test_operating_layer.py::test_project_scoped_operating_layer_snapshot_scopes_task_commands tests/test_operating_layer.py::test_operating_layer_server_runs_approved_shell_worker_in_task_workspace tests/test_operating_layer.py::test_operating_layer_server_refuses_invalid_shell_worker_browser_runs -q
```

Expected: pass.

## Task 5: Keep Browser JavaScript As A Consumer, Not A Source Of Truth

Files:

- Modify: `src/devflow/control_room/operating_layer_script.py` only if needed
- Modify: `tests/test_operating_layer.py`

- [ ] Confirm `taskCapabilities(task)` consumes `task.controls` and `task.actions` before `task.next_action`.
- [ ] Keep `intentForCommand()`, `labelForIntent()`, and `inferredRequiredInputs()` only as legacy fallback helpers.
- [ ] Add or adjust an `APP_JS` assertion that current snapshots are expected to carry typed fields:

```python
assert "for (const control of task?.controls || []) push(control);" in APP_JS
assert "for (const action of task?.actions || []) push(action);" in APP_JS
assert "Legacy fallback for older snapshots" in APP_JS
```

- [ ] Do not add new JavaScript command templates for task controls.

Run:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_operating_layer.py::test_operating_layer_task_cards_expose_state_specific_next_actions -q
```

Expected: pass.

## Task 6: Update Architecture Notes

Files:

- Modify: `docs/architecture/operating-layer-ui-deepening-backlog.md`
- Optional modify: `docs/architecture/control-room-cleanup-checkpoint-2026-06-25.md`

- [ ] Add a dated Candidate 2 checkpoint saying `browser_task_capabilities.py` now owns task command templates and project scoping as well as classification.
- [ ] If Graphify is refreshed, record only lightweight metrics in the cleanup checkpoint doc.
- [ ] Do not commit generated `graphify-out/` files.

## Task 7: Verification

Minimum verification:

```bash
git diff --check
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_browser_task_capabilities.py tests/test_task_workbench_projection.py tests/test_operating_layer.py -q
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_architecture_boundaries.py tests/test_code_map_check.py tests/test_mvp_boundaries.py tests/test_project_scope_docs.py -q
PYTHONPATH=src:. .venv/bin/python -m devflow.cli map check
PYTHONPATH=src:. .venv/bin/python -m devflow.cli operating-layer visual-qa --json
PYTHONPATH=src:. .venv/bin/python -m devflow.cli git status
```

If browser controls or launchpad behavior changes, also run:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_operator_ui_browser.py::test_worker_row_selects_launchpad_and_runs_inline_shell_worker tests/test_operator_ui_browser.py::test_task_switcher_and_seeded_evidence_lane tests/test_operator_ui_browser.py::test_product_stage_contains_task_launchpad_review_and_evidence -q
```

Graphify verification:

```bash
.venv/bin/graphify update .
.venv/bin/graphify diagnose multigraph --json --graph graphify-out/graph.json
.venv/bin/graphify explain "control_room_browser_task_capabilities" --graph graphify-out/graph.json
.venv/bin/graphify explain "control_room_task_workbench" --graph graphify-out/graph.json
.venv/bin/graphify explain "control_room_operating_layer" --graph graphify-out/graph.json
```

Expected:

- no graph structural errors
- `control_room_browser_task_capabilities` degree increases because it owns more command behavior
- `control_room_task_workbench` and `control_room_operating_layer` should not gain new task command-template responsibility

## Done Means

- Task command templates and project scoping live in `browser_task_capabilities.py`.
- `task_workbench.py` asks for capabilities instead of assembling task command strings.
- `operating_layer.py` reuses shared task command scoping.
- Existing snapshot command strings remain unchanged.
- Existing browser approval gates remain unchanged.
- Focused Python and visual QA verification pass.
- Architecture notes record the Candidate 2 checkpoint.

## Rollback Notes

This slice should be a behavior-preserving extraction. If regression appears, revert the changes in `browser_task_capabilities.py`, `task_workbench.py`, `operating_layer.py`, and their tests from this slice only. Do not revert the prior Task workbench projection or operating-layer adapter-thinning commits.
