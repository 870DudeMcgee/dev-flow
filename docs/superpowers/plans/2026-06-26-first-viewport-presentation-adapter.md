# First Viewport Presentation Adapter Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` or `executing-plans` to implement this plan task-by-task. Track progress with the checkbox steps below.

Date: 2026-06-26
Status: ready for implementation handoff

## Goal

Finish the next operating-layer UI cleanup slice by making the Python `FirstViewportPresentation` Module the current Interface for the first viewport, while keeping `operating_layer_script.py` as a DOM Adapter.

After this slice:

- `src/devflow/control_room/operating_layer_first_viewport.py` owns the first-viewport presentation shape for Brainstorm, Pipeline, Next Task, Worker lanes, Review queue, Evidence stream, and Launchpad.
- `src/devflow/control_room/operating_layer_script.py` consumes `snapshot.first_viewport` as the default current path.
- JavaScript fallback builders may remain for older or partial snapshots, but current snapshots should not be rebuilt from raw `tasks`, `review_loop`, and `evidence` unless `first_viewport` is missing or incomplete.
- Browser behavior and visual layout should not change except where tests reveal a bug in fallback precedence.

## Current State

Start from clean `main` after commit:

```text
e38f3b4 refactor: centralize task command capabilities
```

Current architecture state:

- Candidate 1 is complete: `task_workbench.py` owns task-centered projection and `operating_layer.py` is a thinner Adapter.
- Candidate 2 is complete: `browser_task_capabilities.py` owns task command templates, project scoping, typed capability construction, required inputs, and supervisor classification.
- Candidate 3 is partially complete: `operating_layer_first_viewport.py` exists and builds typed first-viewport slices, but `operating_layer_script.py` still has `buildFirstViewportPresentation(snap)` and several fallback card builders that can recreate the same presentation from raw snapshot fields.

The remaining friction is not the UI appearance. It is that first-viewport meaning is split across Python projection and JavaScript reconstruction, so changing Worker lanes, Review queue, Evidence stream, Launchpad, or Pipeline state still requires understanding both.

## Non-Goals

- Do not redesign the UI.
- Do not change layout, colors, spacing, or copy unless a test proves current rendering is wrong.
- Do not introduce a frontend framework.
- Do not remove compatibility fallback for older snapshots unless every browser entry point is proven to receive `snapshot.first_viewport`.
- Do not change browser action approval policy.
- Do not use Hyperplane for validation.
- Do not push, publish, promote, or open a PR.
- Do not commit `graphify-out/`.

## Files Likely To Modify

- `src/devflow/control_room/operating_layer_first_viewport.py`
- `src/devflow/control_room/operating_layer_script.py`
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
  tests/test_operating_layer.py::test_first_viewport_module_shapes_brainstorm_pipeline_and_launchpad \
  tests/test_operating_layer.py::test_operating_layer_snapshot_json_is_read_only_contract \
  tests/test_operating_layer.py::test_operating_layer_snapshot_includes_browser_review_loop_summary \
  tests/test_operating_layer.py::test_operating_layer_task_cards_expose_state_specific_next_actions \
  -q
```

Expected: pass before changes.

## Task 1: Lock Python Presentation As The Current Interface

Files:

- Modify: `tests/test_operating_layer.py`

- [ ] Add or extend a test that compares first-viewport snapshot fields to direct `build_first_viewport_presentation(build_task_workbench(root), root=root)` output.

Required assertions:

- `payload["first_viewport"]["active_task_count"]`
- `payload["first_viewport"]["total_task_count"]`
- `payload["first_viewport"]["next_task"]`
- `payload["first_viewport"]["worker_lanes"]`
- `payload["first_viewport"]["review_queue"]`
- `payload["first_viewport"]["evidence_stream"]`
- `payload["first_viewport"]["launchpad"]`

- [ ] Include at least these task states in the fixture:
  - created task
  - task with worker output needing verification
  - verified task ready for promotion

- [ ] Keep the existing Brainstorm/Pipeline test intact:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_operating_layer.py::test_first_viewport_module_shapes_brainstorm_pipeline_and_launchpad -q
```

Expected: pass.

## Task 2: Make JavaScript Prefer Server Presentation

Files:

- Modify: `src/devflow/control_room/operating_layer_script.py`
- Modify: `tests/test_operating_layer.py`

- [ ] Replace `buildFirstViewportPresentation(snap)` with a smaller Adapter function, for example `firstViewportPresentationFromSnapshot(snap)`.
- [ ] The current path should return `snap.first_viewport` when it has:
  - `schema_version`
  - `launchpad`
  - array `worker_lanes`
  - array `review_queue`
  - array `evidence_stream`
- [ ] Move raw snapshot reconstruction into a clearly named fallback helper, for example `fallbackFirstViewportPresentation(source)`.
- [ ] Add a visible comment stating the fallback exists for older/partial snapshots only.
- [ ] Ensure `render()` calls the server-first Adapter, not the fallback builder directly.

Update string-level tests in `tests/test_operating_layer.py`:

- [ ] Assert the new server-first Adapter function name appears in `APP_JS`.
- [ ] Assert fallback wording appears, such as `older/partial snapshots`.
- [ ] Assert `renderFirstViewport` still appears.
- [ ] Remove or update assertions that require the old `buildFirstViewportPresentation` name if that function is renamed.

Run:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_operating_layer.py::test_operating_layer_task_cards_expose_state_specific_next_actions -q
```

Expected: pass.

## Task 3: Reduce Duplicate Card Reconstruction

Files:

- Modify: `src/devflow/control_room/operating_layer_script.py`

- [ ] Keep DOM rendering functions:
  - `renderWorkerLanes`
  - `renderReviewQueue`
  - `renderEvidenceStream`
  - `renderOrchestrator`
  - `renderFirstViewport`
- [ ] Move or rename raw reconstruction helpers so their fallback role is obvious:
  - `taskCardFromSnapshotTask`
  - `reviewCardFromSnapshotTask`
  - `evidenceCardFromSnapshotPointer`
- [ ] Ensure these helpers are called only from the fallback presentation builder.
- [ ] Do not add new first-viewport derivation logic to render functions.

Run:

```bash
rg -n "taskCardFromSnapshotTask|reviewCardFromSnapshotTask|evidenceCardFromSnapshotPointer|fallbackFirstViewportPresentation|firstViewportPresentationFromSnapshot" src/devflow/control_room/operating_layer_script.py
```

Expected:

- fallback helpers are called only by the fallback builder
- `render()` uses the server-first Adapter

## Task 4: Keep Pipeline And Brainstorm Runtime Overrides Intentional

Files:

- Modify: `src/devflow/control_room/operating_layer_script.py`
- Modify: `tests/test_operating_layer.py`

The browser has local Brainstorm/Pipeline state while the operator is actively chatting. Preserve that interaction, but make it explicit.

- [ ] Keep `renderPipeline()` able to use current in-browser pipeline state during an active session.
- [ ] Keep `shouldUsePresentationPipeline()` or replace it with an equivalent helper whose name makes the override explicit.
- [ ] Add or adjust a string-level test asserting this intentional browser runtime override remains documented in `APP_JS`.
- [ ] Do not let local browser state override Worker lanes, Review queue, Evidence stream, or Launchpad when `snapshot.first_viewport` is present.

Run:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_operating_layer.py::test_operating_layer_server_exposes_brainstorm_message_and_escalation tests/test_operating_layer.py::test_first_viewport_module_shapes_brainstorm_pipeline_and_launchpad -q
```

Expected: pass.

## Task 5: Browser Smoke For The First Viewport

Files:

- Modify: `tests/test_operator_ui_browser.py` only if behavior assertions need alignment

- [ ] Run focused browser tests:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest \
  tests/test_operator_ui_browser.py::test_app_loads_assets_snapshot_health_without_console_errors_or_overflow \
  tests/test_operator_ui_browser.py::test_product_stage_contains_task_launchpad_review_and_evidence \
  tests/test_operator_ui_browser.py::test_task_switcher_and_seeded_evidence_lane \
  -q
```

Expected: pass.

- [ ] If these tests are slow or browser dependencies fail locally, record the exact failure and run the operating-layer visual QA CLI in Task 7.

## Task 6: Update Architecture Notes

Files:

- Modify: `docs/architecture/operating-layer-ui-deepening-backlog.md`
- Optional modify: `docs/architecture/control-room-cleanup-checkpoint-2026-06-25.md`

- [ ] Add a dated Candidate 3 checkpoint saying Python `FirstViewportPresentation` is now the current Interface and JavaScript reconstruction is a fallback Adapter for older/partial snapshots.
- [ ] If Graphify is refreshed, record only lightweight metrics in the cleanup checkpoint doc.
- [ ] Do not commit generated `graphify-out/` files.

## Task 7: Verification

Minimum verification:

```bash
git diff --check
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_operating_layer.py -q
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_architecture_boundaries.py tests/test_code_map_check.py tests/test_mvp_boundaries.py tests/test_project_scope_docs.py -q
PYTHONPATH=src:. .venv/bin/python -m devflow.cli map check
PYTHONPATH=src:. .venv/bin/python -m devflow.cli operating-layer visual-qa --json
PYTHONPATH=src:. .venv/bin/python -m devflow.cli git status
```

Browser verification when practical:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest \
  tests/test_operator_ui_browser.py::test_app_loads_assets_snapshot_health_without_console_errors_or_overflow \
  tests/test_operator_ui_browser.py::test_product_stage_contains_task_launchpad_review_and_evidence \
  tests/test_operator_ui_browser.py::test_task_switcher_and_seeded_evidence_lane \
  -q
```

Graphify verification:

```bash
.venv/bin/graphify update .
.venv/bin/graphify diagnose multigraph --json --graph graphify-out/graph.json
.venv/bin/graphify explain "control_room_operating_layer_first_viewport" --graph graphify-out/graph.json
.venv/bin/graphify explain "control_room_operating_layer" --graph graphify-out/graph.json
```

Expected:

- no graph structural errors
- `operating_layer_script.py` may remain large, but first-viewport derivation should be easier to explain: server presentation first, fallback second, DOM rendering last

## Done Means

- `snapshot.first_viewport` is the current first-viewport presentation Interface.
- JavaScript first-viewport reconstruction is clearly fallback-only.
- Render functions consume presentation slices and do not derive new first-viewport state from raw tasks.
- Brainstorm/Pipeline in-browser runtime override remains explicit and tested.
- Focused operating-layer and browser checks pass.
- Architecture notes record the Candidate 3 checkpoint.

## Rollback Notes

This slice should be behavior-preserving. If browser rendering regresses, revert changes in `operating_layer_script.py`, related tests, and Candidate 3 docs from this slice only. Do not revert prior Task workbench, command capability, evidence detail, or Brainstorm pipeline refactors.
