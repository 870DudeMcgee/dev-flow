# Operating-Layer UI Deepening Backlog

Date: 2026-06-18
Status: active things to fix

## Purpose

This backlog records architecture friction found while investigating why the active operating-layer UI still feels hard to use. It is scoped to the current browser product served by `devflow operating-layer serve`, not the old `public/` files and not future Hyperplane or provider-runtime experiments.

No repo ADRs were found during this pass. `docs/control-room-mvp.md`, `docs/architecture/local-operating-layer-ui.md`, and `CONTEXT.md` are the domain sources for this backlog.

The architecture vocabulary below follows the `improve-codebase-architecture` skill: Module, Interface, Implementation, Depth, Seam, Adapter, Leverage, and Locality.

## Product Pressure

The current UI should let the operator answer these questions quickly:

- What tasks exist right now?
- Which tasks are active, blocked, failed, verified, promoted, or closed?
- Which worker or model is attached to each task?
- What did the worker actually do?
- What is the next safe action?
- Which controls are currently available: inspect, start, verify, retry, close, cleanup, or promote?

The product problem is not that the UI lacks data. The problem is that task state, worker/model identity, evidence, review readiness, and browser actions are spread across several shallow Modules. Small usability fixes often require changing snapshot projection, action command generation, server validation, and browser rendering together.

## Candidate 1: Task Workbench Projection Module

Priority: first.

Files:

- `src/devflow/control_room/operating_layer.py`
- `src/devflow/control_room/status_projection.py`
- `src/devflow/control_room/review_readiness.py`
- `src/devflow/control_room/git_worktree.py`
- `src/devflow/control_room/local_worker_lane.py`
- `tests/test_operating_layer.py`
- `tests/test_operator_ui_browser.py`

Problem:

`build_operating_layer_snapshot()` is a broad Module whose Interface is the whole UI snapshot. Its Implementation decides selected task, lane order, Worker lanes, Review queue, Evidence stream, gate receipts, worker activity, and review loop behavior. The Seam between canonical task state and the operator-facing Task workbench is implicit.

The deletion test says this Module is earning its keep, but its Depth is in the wrong place. If the task-workbench behavior were deleted from `operating_layer.py`, complexity would reappear across the browser and tests. That behavior deserves a deeper Module.

Solution:

Create a deeper Task workbench projection Module that owns task-centered usability state: selected task, visible lanes, review queue membership, evidence pointers, gate progress, worker/model labels, and task-scoped next safe actions. Keep the operating-layer snapshot as an Adapter that maps this projection into the existing public schema.

Benefits:

- Locality: task usability rules change in one place.
- Leverage: Worker lanes, Review queue, Evidence stream, Task Inspector, and health counts can consume the same projection.
- Tests can target the Task workbench Interface directly instead of inspecting a whole browser snapshot or searching a JavaScript blob.

Existing test anchors:

- `tests/test_operating_layer.py::test_operating_layer_snapshot_json_is_read_only_contract`
- `tests/test_operating_layer.py::test_operating_layer_groups_verification_and_promotion_lanes`
- `tests/test_operating_layer.py::test_operating_layer_snapshot_includes_scheduler_summary`
- `tests/test_operator_ui_browser.py::test_worker_row_selects_launchpad_and_runs_inline_shell_worker`
- `tests/test_operator_ui_browser.py::test_task_switcher_and_seeded_evidence_lane`

## Candidate 2: Browser Action/Capability Module

Priority: second.

Files:

- `src/devflow/control_room/operating_layer.py`
- `src/devflow/control_room/operating_layer_server.py`
- `src/devflow/control_room/supervisor_surface.py`
- `src/devflow/control_room/operating_layer_script.py`
- `tests/test_operating_layer.py`
- `tests/test_operator_ui_browser.py`

Problem:

The browser action Interface is mostly command strings. The Implementation builds commands in JavaScript, classifies them with supervisor policy, validates them again in the server, and exposes related action rows through the snapshot. Changing start, retry, close, cleanup preview, verification, or promotion requires keeping multiple interpretations aligned.

Solution:

Deepen browser actions into task-scoped capabilities. The UI should consume named capabilities with labels, safety classification, required inputs, exact command preview, and approval requirements. Server execution remains an Adapter at the approval Seam.

Benefits:

- Locality: command construction and validation rules stop drifting.
- Leverage: all UI surfaces can render the same task controls.
- Tests can assert capability behavior before involving the browser action endpoint.

Checkpoint 2026-06-25:

The browser task capability Interface now lives in `src/devflow/control_room/browser_task_capabilities.py`. `task_workbench.py` maps task state into typed capabilities, and browser JavaScript consumes capability fields before falling back to command inference for older snapshots. Server execution remains the approval-gated Adapter in `operating_layer_server.py`.

Existing test anchors:

- `tests/test_operating_layer.py::test_operating_layer_server_runs_approved_shell_worker_in_task_workspace`
- `tests/test_operating_layer.py::test_operating_layer_server_refuses_invalid_shell_worker_browser_runs`
- `tests/test_operator_ui_browser.py::test_action_api_blocks_unsafe_commands`
- `tests/test_supervisor_operating_surface.py::test_supervisor_policy_json_is_versioned_and_declares_boundaries`

## Candidate 3: Guided First-Viewport Presentation Module

Priority: third.

Files:

- `src/devflow/control_room/operating_layer_html.py`
- `src/devflow/control_room/operating_layer_styles.py`
- `src/devflow/control_room/operating_layer_script.py`
- `src/devflow/control_room/operating_layer_visual_qa.py`
- `tests/test_operator_ui_browser.py`

Problem:

Brainstorm, Pipeline, Next Task, Worker lanes, Review queue, and Evidence stream are rendered from a large JavaScript string where the Interface is DOM ids plus snapshot assumptions. The Implementation mixes rendering, selection state, command construction, evidence formatting, and browser action execution.

Solution:

Deepen the presentation Module around renderable slices derived from the snapshot. Keep direct DOM mutation as an Adapter. This does not need a frontend framework; it needs clearer presentation Interfaces.

Benefits:

- Locality: first-viewport layout and usability changes become easier to test.
- Leverage: the same renderable slices can support Overview and detail panels.
- Tests can move away from brittle string-presence checks.

Existing test anchors:

- `tests/test_operator_ui_browser.py::test_app_loads_assets_snapshot_health_without_console_errors_or_overflow`
- `tests/test_operator_ui_browser.py::test_home_prioritizes_brainstorm_workbench_without_closed_history_noise`
- `tests/test_operating_layer.py::test_operating_layer_visual_qa_plan_covers_core_regression_contracts`

## Candidate 4: Evidence And Review Detail Module

Priority: fourth.

Files:

- `src/devflow/control_room/operating_layer.py`
- `src/devflow/control_room/review_readiness.py`
- `src/devflow/control_room/worker_evidence.py`
- `src/devflow/control_room/agent_evidence.py`
- `tests/test_operating_layer.py`
- `tests/test_supervisor_operating_surface.py`

Problem:

Evidence stream and Review queue need concrete task/log/evidence data, but evidence pointers, event summaries, changed-file previews, review readiness, worker/model evidence, and promotion blockers are assembled in separate places. The current Interface exposes too much artifact knowledge to callers.

Solution:

Deepen an evidence/review detail Module that owns the operator-facing story of worker output, verification, promotion readiness, blockers, and evidence paths. Existing worker/model and git/local lane readers become Adapters at that Seam.

Benefits:

- Locality: evidence bugs stop being scattered across review and UI snapshot code.
- Leverage: Review queue, Evidence stream, Task Inspector, and promotion detail can share one story.
- Tests can verify evidence meaning without full browser rendering.

Existing test anchors:

- `tests/test_operating_layer.py::test_operating_layer_snapshot_includes_compact_agent_evidence_summary`
- `tests/test_supervisor_operating_surface.py::test_task_review_json_cites_evidence_paths_and_tolerates_missing_artifacts`
- `tests/test_operator_ui_browser.py::test_task_switcher_and_seeded_evidence_lane`

## Candidate 5: Brainstorm To Pipeline To Task Creation Module

Priority: fifth.

Files:

- `src/devflow/control_room/brainstorm.py`
- `src/devflow/control_room/operating_layer_server.py`
- `src/devflow/control_room/operating_layer_script.py`
- `tests/test_brainstorm_workbench.py`
- `tests/test_operating_layer.py`
- `tests/test_operator_ui_browser.py`

Problem:

Brainstorm records transcript/model evidence, Pipeline tracks stage state in JavaScript, escalation returns a task-create command, the browser executes it, and implementation context is written separately. The Interface between Brainstorm and Pipeline is a shallow payload convention.

Solution:

Deepen the Brainstorm/Pipeline Module around stage artifacts, advisory workers/models, implementation context, and the next executable task action. Model calls and task creation remain explicit Adapters at separate Seams.

Benefits:

- Locality: `Create task` behavior gets a single product path.
- Leverage: task creation, implementation context, and next launchpad selection can be tested without a full browser flow.
- The UI can make model identity and task creation evidence clearer.

Existing test anchors:

- `tests/test_brainstorm_workbench.py::test_brainstorm_escalation_writes_spec_plan_and_returns_task_action`
- `tests/test_operating_layer.py::test_operating_layer_server_exposes_brainstorm_message_and_escalation`
- `tests/test_operator_ui_browser.py::test_brainstorm_definition_of_done_persists_per_session`

## Recommended Order

1. Build the Task workbench projection Module.
2. Deepen browser task actions into task-scoped capabilities.
3. Split first-viewport presentation around renderable slices.
4. Consolidate evidence/review detail.
5. Deepen Brainstorm to Pipeline to task creation.

This order attacks the most painful usability roadblocks first: task visibility, task selection, task controls, and consistent next safe actions.
