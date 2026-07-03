# Control-Room Hotspot Follow-Up Plan

Date: 2026-07-02
Status: Planning checkpoint after the combined operating-layer asset split

Slice 7 is complete by accepted scope. This plan records the next cleanup
opportunities from the remaining Graphify/codebase hotspots. It is a planning
document only: do not treat it as authorization to implement all slices at once.

Graphify is evidence, not authority. At the time of the asset-facade review,
`HEAD` was `af552b02` and `graphify-out/GRAPH_REPORT.md` was built from
`f8060799`, so the generated report was stale and used only as a ranking map.
The current evidence was the architecture checkpoint in
`docs/architecture/control-room-architecture-audit.md`, direct source
inspection, focused tests, and local Ornith 9B read-only scout reports.

## Constraints

- Do not reopen Slice 7 unless an actual regression is found.
- Do not propose line-count churn or deletion of active product code.
- Preserve `src/devflow/control_room/operating_layer_assets.py` as the facade
  exporting `APP_JS`, `APP_CSS`, and `INDEX_HTML`.
- Keep `APP_JS` and `APP_CSS` facade assembly unless a slice has focused tests
  that justify changing the served asset contract.
- Prefer module boundaries that reduce coupling, clarify ownership, or isolate
  behavior with targeted tests.
- Treat tests as regression evidence, not shipping evidence.

## Subagent Execution

The combined asset-facade review used bounded local Ornith 9B read-only scouts:

| Lane | Scope | Outcome |
|---|---|---|
| JS scout | `src/devflow/control_room/operating_layer_script.py` plus extracted JS modules | Confirmed `APP_JS` splices Obsidian intake, workbench, pipeline, and architecture evidence exactly once in dependency-safe order. |
| CSS scout | `src/devflow/control_room/operating_layer_styles.py`, `operating_layer_task_control_styles.py`, and extracted CSS modules | Confirmed each extracted CSS section is included once and `PIPELINE_CSS` remains routed through `TASK_CONTROL_WORKBENCH_CSS`. |
| Docs/tests scout | Architecture docs and focused asset tests | Confirmed Graphify staleness language and flagged this plan when it still treated already-extracted asset boundaries as future work. |

## Accepted Asset-Facade Boundary

The current combined asset split covers these client-side surfaces:

- Workbench JS/CSS.
- Obsidian intake JS/CSS.
- Pipeline JS/CSS.
- Architecture evidence JS/CSS.

Keep `APP_JS` and `APP_CSS` as the served facade contract. `APP_JS` should
splice the extracted JavaScript modules once in this order: Obsidian intake,
workbench, pipeline, architecture evidence. `APP_CSS` should include each
extracted CSS section once, with `PIPELINE_CSS` spliced through
`TASK_CONTROL_WORKBENCH_CSS` rather than directly from
`operating_layer_styles.py`.

Do not reopen the workbench, Obsidian intake, pipeline, or architecture evidence
asset boundaries unless review or runtime verification finds an actual
regression.

## Current Hotspot Map

| Path | Current role | Why Graphify flags it | Real architecture problem? |
|---|---|---|---|
| `src/devflow/control_room/operating_layer_script.py` | Browser app composition root and JavaScript asset facade. | Large `APP_JS` string with many client-side domains. | Partly. Obsidian intake, architecture evidence, workbench, and render-only task controls have cohesive boundaries. Snapshot hydration, render fanout, polling, and shared action execution should stay in place for now. |
| `src/devflow/control_room/operating_layer_styles.py` | CSS assembly facade for shell, layout, brainstorm, workbench, architecture, focus, loops, and utilities. | Large `APP_CSS` string, even after model-picker and task-control extraction. | Mostly acceptable. Remaining selectors share shell variables, layout, utilities, and responsive rules. Split only when a visible UI surface can stand alone. |
| `src/devflow/control_room/operating_layer_server.py` | HTTP transport facade for assets, snapshot, actions, workbench, builder-judge, local model, browse, and health. | Many route methods, imports, and helper functions. | Yes for `/api/actions/run`, which mixes policy, approval, subprocess execution, truncation, and response shaping. Builder-judge runtime state is the second candidate. |
| `src/devflow/control_room/dogfood.py` | Dogfood suite coordinator plus private case scripts. | Many case functions and dogfood-specific helpers. | Not currently. Slice 7 already extracted run-store helpers. The remaining module is coherent as the dogfood suite boundary. |
| `src/devflow/cli.py` | Typer command dispatcher and task workflow entrypoints. | Many command functions and local imports. | Only `task_auto_run` is a real next extraction target. Most remaining commands are thin wrappers or intentionally coupled operator workflows. |
| `tests/test_operating_layer.py` | Mixed static asset, server, route, concurrency, and UI contract tests. | Large test module with many independent failure modes. | Test hotspot only. Improve failure locality after production splits; do not do a broad rewrite. |
| `tests/test_operator_ui_browser.py` | Browser regression surface for the served operating layer. | Large Playwright-style browser file. | Leave mostly intact. It protects visible operator behavior and should be used as focused smoke coverage for UI slices. |
| `tests/test_local_ai_command.py` | Local-AI command and capacity workflow coverage. | Large test file with many command scenarios. | Not part of this active-hotspot slice. Defer unless local-AI command work resumes. |

## Recommended Future Slices

### Slice 8: Idea Greenhouse Asset Boundary

Files touched:

- `src/devflow/control_room/operating_layer_script.py`
- `src/devflow/control_room/operating_layer_styles.py`
- New Idea Greenhouse JS/CSS asset modules
- Focused Idea Greenhouse asset tests

Boundary:

- Before extracting, run a fresh scout pass over Idea Greenhouse state ownership,
  task creation and brainstorm touchpoints, and static test tokens.
- Move Idea Greenhouse render helpers, detail forms, classify/park/archive UI
  helpers, and Idea-specific click handling into a dedicated JS asset module
  only where they do not pull in the shared browser action kernel.
- Move `.idea-greenhouse-*`, `.idea-lane*`, `.idea-card*`,
  `.idea-detail-*`, and related Idea-specific selectors into a dedicated CSS
  asset module.
- Keep `APP_JS`, `APP_CSS`, and `operating_layer_assets.py` as the served
  facade contract.

Expected benefit:

- Extracts an adjacent but less stateful surface after the accepted asset split.
- Keeps task creation and Brainstorm session management visible as explicit
  touchpoints rather than accidentally moving shared state.
- Gives the next slice focused static-asset tests before any broader session
  refactor.

Risk:

- Idea detail actions share approved-command plumbing with task controls.
- `data-idea-brainstorm` starts or continues Brainstorm sessions, so session
  adoption and transcript loading must stay exact.
- Brainstorm session management itself should remain deferred until after this
  slice is accepted.

Focused tests:

```bash
env PYTHONPATH=src:. .venv/bin/python -m pytest \
  tests/test_operating_layer.py -k "idea_greenhouse or data-idea or classify or park_archive" -q
env PYTHONPATH=src:. .venv/bin/python -m pytest \
  tests/test_operator_ui_browser.py -k idea_greenhouse -q
```

Estimated size: medium.

### Slice 9: Browser Action Executor

Files touched:

- `src/devflow/control_room/operating_layer_server.py`
- New `src/devflow/control_room/browser_action_executor.py`
- Focused action-run tests if a direct service-level test is useful

Boundary:

- Extract the `/api/actions/run` branch from `do_POST`.
- Move command classification, `resolve_browser_action()`,
  `command_args_for_approved_browser_action()`, approval handling,
  subprocess execution, output truncation, promotion-context writing, and the
  stable action response envelope into a small service.
- Keep HTTP parsing and `_send_json()` / `_send_action_error()` behavior in the
  request handler unless the response envelope is moved behind a typed result.

Expected benefit:

- Removes the clearest server-side coupling hotspot.
- Makes browser-approved command execution easier to test without reasoning
  through the whole HTTP handler.

Risk:

- Stable JSON error shape, timeout handling, retriable flags, and output
  truncation are user-visible contracts.

Focused tests:

```bash
env PYTHONPATH=src:. .venv/bin/python -m pytest \
  tests/test_operating_layer.py -k "browser_action_policy or runs_approved or blocks_approval or action_run or shell_worker_browser_runs or disallowed_browser_mutations" -q
```

Estimated size: medium.

### Slice 10: Builder-Judge Runtime Registry

Files touched:

- `src/devflow/control_room/operating_layer_server.py`
- New builder-judge runtime registry helper
- Focused builder-judge server tests

Boundary:

- Move `_bj_state_lock`, `_bj_running_loops`, `_bj_threads`, and `_bj_*`
  registry helpers out of the HTTP module.
- Keep route methods responsible for payload parsing and response status.

Expected benefit:

- Separates concurrency/state retention from the HTTP facade.
- Gives completed-thread retention and running-loop visibility one owner.

Risk:

- `_handle_builder_judge_status()` currently merges in-memory running state with
  newer file-backed rounds. That behavior must be preserved exactly.

Focused tests:

```bash
env PYTHONPATH=src:. .venv/bin/python -m pytest \
  tests/test_operating_layer.py -k "builder_judge_async_start_status_and_list_are_consistent_under_concurrency or builder_judge_completed_thread_entries_are_bounded or builder_judge_background_failure_stays_visible" -q
```

Estimated size: medium.

### Slice 11: CLI `task_auto_run` Service

Files touched:

- `src/devflow/cli.py`
- New CLI command helper or service module
- `tests/test_task_auto_run_cli.py`

Boundary:

- Move the body of `task_auto_run()` into a focused command service that owns
  fit estimation, routing, registry validation, adapter validation, worker
  execution, and rendered output lines.
- Leave the Typer function as a thin option parser and exit-code adapter.

Expected benefit:

- Isolates the only remaining CLI command that mixes policy, selection,
  validation, and execution.
- Keeps broad task command workflows intact instead of doing random CLI churn.

Risk:

- CLI output is a contract. Preserve line ordering and wording unless tests
  deliberately change with the slice.

Focused tests:

```bash
env PYTHONPATH=src:. .venv/bin/python -m pytest \
  tests/test_task_auto_run_cli.py \
  tests/test_cli_experimental.py -q
```

Estimated size: small to medium.

### Slice 12: Static Asset Test Locality

Files touched:

- `tests/test_operating_layer.py`
- New `tests/test_operating_layer_assets.py`

Boundary:

- Move pure `APP_JS`, `APP_CSS`, and `INDEX_HTML` contract tests out of the
  mixed operating-layer server test file.
- Do not rewrite browser tests or broad server fixtures.

Expected benefit:

- Improves failure locality after JS/CSS asset splits.
- Keeps static asset drift from obscuring runtime route failures.

Risk:

- Low, but avoid turning this into a general test cleanup project.

Focused tests:

```bash
env PYTHONPATH=src:. .venv/bin/python -m pytest \
  tests/test_operating_layer_assets.py \
  tests/test_operating_layer.py -k "architecture_artifact_route or builder_judge or obsidian or action_run" -q
```

Estimated size: small.

## Do-Not-Touch List

- `src/devflow/control_room/operating_layer_assets.py`: keep the public asset
  facade exporting `APP_JS`, `APP_CSS`, and `INDEX_HTML`.
- `render()`, `renderFirstViewport()`, snapshot hydration, brainstorm-session
  adoption, and pipeline adoption in `operating_layer_script.py`: these are the
  client composition root and live snapshot bridge.
- Workbench, Obsidian intake, pipeline, and architecture evidence asset modules:
  treat them as the accepted combined asset-facade boundary unless a regression
  appears.
- Brainstorm session management: defer until after the Idea Greenhouse boundary,
  because it shares more behavior with task creation, transcript loading,
  pipeline adoption, and workbench state.
- `runApprovedCommand()`, `executeAction()`, and `setupTaskSurfaceActions()`:
  these are cross-cutting policy/action glue for tasks, ideas, local-model
  setup, and architecture actions. Revisit after the server action executor is
  isolated.
- `dogfood.py` case scripts: large but coherent as dogfood suite behavior after
  Slice 7's run-store extraction.
- Thin CLI wrappers and coupled task workflows such as `task run`,
  `task verify`, `task promote`, `task review-patch`, and `task patch-dry-run`.
- CSS shell tokens, global utilities, and responsive rules in
  `operating_layer_styles.py`.

## Verification Plan

Run `git diff --check` for every slice.

For UI or asset slices, also run the focused browser smoke when practical:

```bash
env PYTHONPATH=src:. .venv/bin/python -m pytest \
  tests/test_operator_ui_browser.py::test_app_loads_assets_snapshot_health_without_console_errors_or_overflow -q
```

For served operating-layer validation, use the module entrypoint when the
console script is unavailable:

```bash
env PYTHONPATH=src:. .venv/bin/python -m devflow.cli operating-layer serve
curl -fsS http://127.0.0.1:8765/healthz
curl -fsS http://127.0.0.1:8765/api/snapshot >/tmp/devflow-snapshot.json
curl -fsSI http://127.0.0.1:8765/app.js
curl -fsSI http://127.0.0.1:8765/app.css
```

If the architecture evidence itself is refreshed, use the repo-owned audit path
instead of ad hoc Graphify commands:

```bash
env PYTHONPATH=src:. .venv/bin/python -m devflow.cli architecture audit --write-doc
```

Then confirm `graphify-out/GRAPH_REPORT.md` was built from the current
`git rev-parse --short HEAD`.

## First Recommended Next Slice

Start with Slice 8, Idea Greenhouse Asset Boundary.

It is adjacent to the accepted asset split but less stateful than Brainstorm
session management. Before extracting it, run a fresh scout pass over Idea
Greenhouse state ownership, task creation touchpoints, brainstorm touchpoints,
and static test tokens. Defer Brainstorm session management until after this
boundary is accepted.
