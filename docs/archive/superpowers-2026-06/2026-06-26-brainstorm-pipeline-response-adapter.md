# Brainstorm Pipeline Response Adapter Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` or `executing-plans` to implement this plan task-by-task. Track progress with the checkbox steps below.

Date: 2026-06-26
Status: ready for implementation handoff

## Goal

Finish the next operating-layer cleanup slice by making the existing `BrainstormPipelineDetail` and `BrainstormTaskCreationResult` models the current Interface for Brainstorm -> Pipeline -> Task creation responses.

After this slice:

- `src/devflow/control_room/brainstorm_pipeline.py` owns the typed response shape for escalation and task creation.
- `src/devflow/control_room/brainstorm.py` uses that response Interface instead of hand-assembling duplicate payload dictionaries.
- `src/devflow/control_room/operating_layer_server.py` remains a thin HTTP Adapter for Brainstorm/Pipeline requests.
- `src/devflow/control_room/operating_layer_script.py` consumes `pipeline_detail.task_action`, `pipeline_detail.implementation_context`, `post_create_action`, and `launchpad` as the current path.
- Legacy top-level fields such as `action`, `implementation_context`, and `implementation_context_path` remain compatibility mirrors, but browser task creation must not depend on them for current responses.
- Creating a task from an implementation-stage brainstorm should use `/api/brainstorm/create-task` whenever the typed pipeline response exposes a task action. The old two-step `devflow task create` plus context write path should remain only as a legacy fallback for older/partial payloads.

## Current State

Start from clean `main` after commit:

```text
82ff6a5c refactor: share evidence review detail
```

Current architecture state:

- Candidate 1 is complete: the Task workbench projection owns task-centered operating-layer state.
- Candidate 2 is complete: browser task capabilities own command construction and safety metadata.
- Candidate 3 is complete: first-viewport presentation is generated server-side and JavaScript is a DOM Adapter/fallback.
- Candidate 4 is complete: `EvidenceReviewDetail` owns the shared evidence/review story for Task workbench and Supervisor review output.
- Candidate 5 is partially complete: `brainstorm_pipeline.py` already has the deeper Module for pipeline detail, implementation context, task creation result, post-create action, and launchpad selection. The remaining friction is Adapter code still treating response dictionaries as the Interface.

Specific friction to remove:

- `brainstorm.py::escalate_brainstorm_session()` returns two hand-built dict shapes, one for implementation stage and one for other stages.
- The implementation-stage response mirrors typed data into top-level `action`, `implementation_context`, and `implementation_context_path`.
- `operating_layer_script.py` has `pipelineDetailFromPayload()`, `taskActionFromPipelinePayload()`, and `implementationContextFromPipelinePayload()` fallback helpers that still make legacy payload fields look current.
- Browser task creation currently uses `/api/brainstorm/create-task` only when `implementation_context.text` exists, even though `create_task_from_brainstorm()` can build context from implementation artifacts when spec/plan context is missing.

The deletion test says `brainstorm_pipeline.py` is earning its keep: deleting it would spread stage artifacts, lineage, task creation, implementation context, and launchpad selection across Brainstorm, server, browser, and tests. The next move is to make the remaining Adapters thinner.

## Non-Goals

- Do not redesign the browser UI.
- Do not change provider/model selection or add new model calls.
- Do not make provider-backed workers mutate code.
- Do not remove compatibility fields from HTTP JSON in this slice.
- Do not change task creation approval semantics beyond using the existing explicit `/api/brainstorm/create-task` bridge for current typed responses.
- Do not remove JavaScript fallback for older/partial payloads.
- Do not use Hyperplane for validation.
- Do not push, publish, promote, or open a PR.
- Do not commit `graphify-out/`.

## Files Likely To Modify

- `src/devflow/control_room/brainstorm_pipeline.py`
- `src/devflow/control_room/brainstorm.py`
- `src/devflow/control_room/operating_layer_server.py`
- `src/devflow/control_room/operating_layer_script.py`
- `tests/test_brainstorm_workbench.py`
- `tests/test_brainstorm_task_bridge.py`
- `tests/test_operating_layer.py`
- `tests/test_operator_ui_browser.py` only if browser behavior changes
- `docs/architecture/operating-layer-ui-deepening-backlog.md`
- optionally `docs/architecture/control-room-cleanup-checkpoint-2026-06-25.md`

## Task 0: Confirm Baseline

- [ ] Run:

```bash
git status --short
PYTHONPATH=src:. .venv/bin/python -m devflow.cli git status
```

Expected:

- clean working tree
- local `main` may be ahead of `origin/main`
- `safe_for_worker_writes: yes`

- [ ] Run focused baseline tests:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest \
  tests/test_brainstorm_workbench.py \
  tests/test_brainstorm_task_bridge.py \
  tests/test_operating_layer.py::test_operating_layer_server_exposes_brainstorm_message_and_escalation \
  -q
```

Expected: pass before changes.

## Task 1: Add A Typed Escalation Response Interface

Files:

- Modify: `src/devflow/control_room/brainstorm_pipeline.py`
- Modify: `tests/test_brainstorm_workbench.py`

- [ ] Add a typed escalation response model to `brainstorm_pipeline.py` named `BrainstormEscalationResult`.
- [ ] Include these fields:
  - `schema_version: int = 1`
  - `status: str = "ready"`
  - `session_id: str`
  - `stage: str`
  - `artifact_path: str | None`
  - `lineage: dict[str, Any] | None`
  - `model_info: dict[str, Any] | None`
  - `pipeline_detail: BrainstormPipelineDetail`
  - compatibility mirror `action: BrainstormTaskCreationAction | None`
  - compatibility mirror `implementation_context: str | None`
  - compatibility mirror `implementation_context_path: str | None`
- [ ] Add a helper named `build_brainstorm_escalation_result(detail, artifact_path, model_info)` that creates the response from a `BrainstormPipelineDetail`.
- [ ] Add or adjust a direct test proving:
  - `pipeline_detail.task_action` is the source of truth for implementation-stage task creation.
  - top-level `action` mirrors `pipeline_detail.task_action` for compatibility.
  - top-level `implementation_context` mirrors `pipeline_detail.implementation_context.text` for compatibility.
  - non-implementation stages return no task action but still return `pipeline_detail`.

Run:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_brainstorm_workbench.py -q
```

Expected before implementation: new direct assertions may fail because responses are still hand-built.

## Task 2: Use The Response Interface In Brainstorm

Files:

- Modify: `src/devflow/control_room/brainstorm.py`
- Modify: `tests/test_brainstorm_workbench.py`

- [ ] Replace the duplicate response dict construction in `escalate_brainstorm_session()` with the new response helper.
- [ ] Keep the existing artifact-writing and provider/model generation flow unchanged.
- [ ] Keep persisted `pipeline.json` unchanged except for additive fields already produced by `BrainstormPipelineDetail`.
- [ ] Preserve existing JSON keys and values that current tests assert:
  - `status`
  - `session_id`
  - `stage`
  - `artifact_path`
  - `lineage`
  - `action`
  - `model_info`
  - `pipeline_detail`
  - `implementation_context`
  - `implementation_context_path`
- [ ] Remove any now-unused local response-building branches.

Run:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_brainstorm_workbench.py -q
```

Expected: pass.

## Task 3: Keep The HTTP Server A Thin Adapter

Files:

- Modify: `src/devflow/control_room/operating_layer_server.py`
- Modify: `tests/test_operating_layer.py`

- [ ] Confirm `/api/brainstorm/escalate` returns the typed escalation result unchanged after validation.
- [ ] Confirm `/api/brainstorm/create-task` returns `BrainstormTaskCreationResult` fields from `create_task_from_brainstorm()` unchanged.
- [ ] Inspect `/api/brainstorm/transcript`; if `BrainstormSessionSnapshot.model_dump(mode="json")` already includes the same `pipeline` field, remove the redundant reassignment.
- [ ] Add or adjust tests proving:
  - escalation response contains `pipeline_detail.task_action`.
  - `action` equals `pipeline_detail.task_action` as a compatibility mirror.
  - transcript response contains `pipeline.task_action` with the same command after implementation escalation.
  - create-task response contains `post_create_action`, `launchpad`, `pipeline_detail.launchpad_selection`, `context_path`, and `evidence_paths`.

Run:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest \
  tests/test_operating_layer.py::test_operating_layer_server_exposes_brainstorm_message_and_escalation \
  tests/test_brainstorm_task_bridge.py \
  -q
```

Expected: pass.

## Task 4: Make Browser Brainstorm Consumption Detail-First

Files:

- Modify: `src/devflow/control_room/operating_layer_script.py`
- Modify: `tests/test_operating_layer.py`
- Modify: `tests/test_brainstorm_task_bridge.py`

- [ ] Keep these helper names for test stability and document their Adapter role:
  - `pipelineDetailFromPayload(payload)`
  - `taskActionFromPipelinePayload(payload)`
  - `implementationContextFromPipelinePayload(payload)`
- [ ] Add a visible comment containing `Legacy Brainstorm payload fallback` near the top-level `payload.action` and `payload.implementation_context` fallback path.
- [ ] For current implementation-stage typed responses, call `createTaskFromBrainstorm(brainstormSessionId, taskAction.title, ...)` whenever `pipeline_detail.task_action` exists.
- [ ] Do not require `pipeline_detail.implementation_context.text` before using `/api/brainstorm/create-task`; the bridge can build task context from available Brainstorm artifacts.
- [ ] Keep the old `runApprovedCommand(taskAction.command, {})` path only for older/partial payloads that lack a typed pipeline task action.
- [ ] Keep post-create launchpad behavior driven by `bridgePayload.launchpad` and `bridgePayload.post_create_action`.
- [ ] Preserve existing visible messaging, including the implementation context target line.

String-level test expectations:

- [ ] Assert `Legacy Brainstorm payload fallback` appears in `APP_JS`.
- [ ] Assert `createTaskFromBrainstorm(\n                  brainstormSessionId,` still appears.
- [ ] Assert the current typed path checks `detail.task_action` or an equivalent detail-first expression before legacy `payload.action`.
- [ ] Assert the browser does not gate `/api/brainstorm/create-task` behind `implContext?.text`.

Run:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest \
  tests/test_brainstorm_task_bridge.py::test_operating_layer_js_uses_active_brainstorm_session_for_atomic_bridge \
  tests/test_operating_layer.py::test_operating_layer_javascript_bundle_contains_interactive_handlers \
  -q
```

Expected: pass.

## Task 5: Preserve First Viewport And Pipeline Behavior

Files:

- Modify: `tests/test_operating_layer.py` only if response-shape assertions need alignment
- Modify: `tests/test_operator_ui_browser.py` only if browser behavior changes

- [ ] Run:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest \
  tests/test_operating_layer.py::test_first_viewport_module_shapes_brainstorm_pipeline_and_launchpad \
  tests/test_operating_layer.py::test_operating_layer_server_exposes_brainstorm_message_and_escalation \
  tests/test_brainstorm_workbench.py \
  tests/test_brainstorm_task_bridge.py \
  -q
```

Expected: pass.

- [ ] If practical, run the focused browser test for Brainstorm/Pipeline:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest \
  tests/test_operator_ui_browser.py::test_brainstorm_definition_of_done_persists_per_session \
  -q
```

Expected: pass, or record the exact local browser dependency failure.

## Task 6: Update Architecture Notes

Files:

- Modify: `docs/architecture/operating-layer-ui-deepening-backlog.md`
- Optional modify: `docs/architecture/control-room-cleanup-checkpoint-2026-06-25.md`

- [ ] Add a dated Candidate 5 checkpoint saying `BrainstormPipelineDetail` and `BrainstormTaskCreationResult` are now the current Brainstorm -> Pipeline -> Task creation Interface.
- [ ] Mention that `brainstorm.py`, `operating_layer_server.py`, and `operating_layer_script.py` are now Adapters that preserve legacy mirrors for compatibility.
- [ ] If Graphify is refreshed, record only lightweight metrics in the cleanup checkpoint doc.
- [ ] Do not commit generated `graphify-out/` files.

## Task 7: Verification

Minimum verification:

```bash
git diff --check
PYTHONPATH=src:. .venv/bin/python -m pytest \
  tests/test_brainstorm_workbench.py \
  tests/test_brainstorm_task_bridge.py \
  tests/test_operating_layer.py::test_operating_layer_server_exposes_brainstorm_message_and_escalation \
  tests/test_operating_layer.py::test_first_viewport_module_shapes_brainstorm_pipeline_and_launchpad \
  tests/test_operating_layer.py::test_operating_layer_javascript_bundle_contains_interactive_handlers \
  -q
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_architecture_boundaries.py tests/test_code_map_check.py tests/test_mvp_boundaries.py tests/test_project_scope_docs.py -q
PYTHONPATH=src:. .venv/bin/python -m devflow.cli map check
PYTHONPATH=src:. .venv/bin/python -m devflow.cli git status
```

Browser verification when practical:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest \
  tests/test_operator_ui_browser.py::test_brainstorm_definition_of_done_persists_per_session \
  -q
```

Graphify verification:

```bash
.venv/bin/graphify update .
.venv/bin/graphify diagnose multigraph --json --graph graphify-out/graph.json
.venv/bin/graphify explain "control_room_brainstorm_pipeline" --graph graphify-out/graph.json
.venv/bin/graphify explain "control_room_brainstorm" --graph graphify-out/graph.json
.venv/bin/graphify explain "control_room_operating_layer_server" --graph graphify-out/graph.json
```

Expected:

- tests pass
- no `graphify-out/` files are committed
- `control_room_brainstorm_pipeline` remains the deep Module for Brainstorm/Pipeline meaning
- `brainstorm.py`, `operating_layer_server.py`, and browser JavaScript read as thinner Adapters

## Rollback And Risk Notes

- Main compatibility risk: browser or tests may still depend on top-level `action`, `implementation_context`, or `implementation_context_path`. Keep those fields as mirrors in this slice.
- Main behavior risk: the browser currently falls back to `devflow task create` when implementation context text is absent. The bridge should replace that for current typed responses because it can derive context from implementation artifacts; retain the legacy path only for older/partial payloads.
- Main product risk: task creation must remain explicit and visible. Do not add hidden automatic model execution, worker execution, verification, promotion, commit, push, or publish.
- Rollback path: revert the browser detail-first change first. The typed response helper can remain if it preserves the legacy response keys.
