# Control-Room Hotspot Follow-Up Plan

Date: 2026-07-02
Updated: 2026-07-04
Status: Planning checkpoint updated after the accepted route/test locality
review

Local-worker note: this plan records historical Ornith scout evidence. Current
local-worker selection is [docs/local-worker-policy.md](../local-worker-policy.md):
opt-in visible Codex `qwen36_27b_mtp_coder` worker, with `hermes-qwen-mtp` as
the same-lane Hermes MCP wrapper and Ornith as an explicit read-only exception
only.

Slice 7 is complete by accepted scope. The July 4 reassessment accepted the
route/test locality work that landed after this plan was first written: the
Idea Greenhouse asset split, Browser Action Executor, Builder-Judge Runtime
Registry, route-local tests, static asset test locality, and the CLI
`task_auto_run` command service are no longer future slices. This plan records
the next cleanup opportunities from the remaining Graphify/codebase hotspots. It
is a planning document only: do not treat it as authorization to implement all
slices at once.

Graphify is evidence, not authority. At the time of the asset-facade review,
`HEAD` was `af552b02` and `graphify-out/GRAPH_REPORT.md` was built from
`f8060799`, so the generated report was stale and used only as a ranking map.
The current evidence is the architecture checkpoint in
`docs/architecture/control-room-architecture-audit.md`, direct source
inspection, focused tests, Context Map MCP orientation, and local-worker
readiness evidence. Historical Ornith scout reports remain background evidence
only; current local-worker execution uses the Qwen lane described above.

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
| `src/devflow/control_room/operating_layer_script.py` | Browser app composition root and JavaScript asset facade. | Large `APP_JS` string with many client-side domains. | Yes, but narrower than before. Obsidian intake, architecture evidence, workbench, pipeline, and Idea Greenhouse have cohesive asset modules. The remaining high-leverage seam is the shared client action kernel around approved-command execution, task action dispatch, and action-result rendering. |
| `src/devflow/control_room/operating_layer_styles.py` | CSS assembly facade for shell, layout, brainstorm, workbench, architecture, focus, loops, and utilities. | Large `APP_CSS` string, even after model-picker and task-control extraction. | Mostly acceptable. Remaining selectors share shell variables, layout, utilities, and responsive rules. Split only when a visible UI surface can stand alone. |
| `src/devflow/control_room/operating_layer_server.py` | HTTP transport facade for assets, snapshot, actions, workbench, builder-judge, local model, browse, and health. | Many route methods, imports, and helper functions. | Improved. Browser action execution, Brainstorm payload shaping, Builder-Judge payload shaping, browse projection, and local-model ensure orchestration now live behind focused modules. The remaining server-side candidate is Workbench/Gates payload shaping, not another broad HTTP rewrite. |
| `src/devflow/control_room/dogfood.py` | Dogfood suite coordinator plus private case scripts. | Many case functions and dogfood-specific helpers. | Not currently. Slice 7 already extracted run-store helpers. The remaining module is coherent as the dogfood suite boundary. |
| `src/devflow/cli.py` | Typer command dispatcher and task workflow entrypoints. | Many command functions and local imports. | Improved for this plan: `task_auto_run` now delegates to `task_auto_run_command.py`. Most remaining commands are thin wrappers or intentionally coupled operator workflows. Do not churn CLI by size alone. |
| `tests/test_operating_layer.py` | Snapshot, projection, visual-QA, and remaining operating-layer contract tests. | Large test module with many independent failure modes. | Smaller and more coherent after route/static tests moved out. Continue moving tests only when a production module split creates a better test seam. Do not do a broad test rewrite. |
| `tests/test_operator_ui_browser.py` | Browser regression surface for the served operating layer. | Large Playwright-style browser file. | Leave mostly intact. It protects visible operator behavior and should be used as focused smoke coverage for UI slices. |
| `tests/test_local_ai_command.py` | Local-AI command and capacity workflow coverage. | Large test file with many command scenarios. | Not part of this active-hotspot slice. Defer unless local-AI command work resumes. |

## Completed Since This Plan

These entries were future slices in the original July 2 plan but are current
source/test reality after the accepted July 4 route/test locality review.

### Idea Greenhouse Asset Boundary

Status: complete by current source.

Evidence:

- `operating_layer_idea_greenhouse_script.py` and
  `operating_layer_idea_greenhouse_styles.py` own the Idea Greenhouse asset
  surface.
- `tests/test_operating_layer_assets.py` verifies the Idea Greenhouse JS/CSS
  are facade parts, included once, and do not own `runApprovedCommand`,
  `executeAction`, or `setupTaskSurfaceActions`.

### Browser Action Executor

Status: complete by current source.

Evidence:

- `browser_action_executor.py` owns command classification, approval resolution,
  subprocess execution, timeout handling, promotion-context writing, output
  truncation, and typed action response shaping.
- `operating_layer_server.py` keeps HTTP parsing and `_send_json()` /
  `_send_action_error()` mapping.
- `tests/test_browser_action_routes.py` and `tests/test_browser_action_policy.py`
  cover the browser action route and resolver contracts.

### Builder-Judge Runtime And Route Locality

Status: complete for the previously named runtime-registry slice; improved with
route payload locality.

Evidence:

- `builder_judge_runtime_registry.py` owns running-loop/thread retention.
- `operating_layer_builder_judge_routes.py` owns Builder-Judge route payload
  shaping and read/status behavior.
- `tests/test_operating_layer_builder_judge_routes.py` covers the route-local
  async/status/list/failure contracts.

### CLI `task_auto_run` Command Service

Status: complete by current source.

Evidence:

- `src/devflow/cli.py` delegates `task auto-run` to
  `run_task_auto_run_command(...)`.
- `task_auto_run_command.py` owns the command-specific routing/execution/output
  contract.
- `tests/test_task_auto_run_cli.py` covers the command facade behavior.

### Static Asset And Route Test Locality

Status: complete enough for the current route/test locality acceptance.

Evidence:

- `tests/test_operating_layer_assets.py` owns pure `APP_JS`, `APP_CSS`, and
  `INDEX_HTML` contract checks.
- Route-local files now cover browser actions, Brainstorm, browse,
  Builder-Judge, local-model ensure, Obsidian, and static/project routes.
- `tests/test_operating_layer.py` remains for snapshot/projection/visual-QA and
  operating-layer contracts that do not yet have a clearer production seam.

## Recommended Future Slices

### Next Slice: Client Action Kernel Extraction

Files touched:

- `src/devflow/control_room/operating_layer_script.py`
- New `src/devflow/control_room/operating_layer_action_kernel_script.py`
- `tests/test_operating_layer_assets.py`
- Focused browser smoke when practical

Seam:

- Extract the client action kernel around `renderActionPending()`,
  `renderActionError()`, `renderActionResult()`, `runApprovedCommand()`,
  `executeAction()`, command-copy helpers, and `setupTaskSurfaceActions()`.
- Preserve the exact `APP_JS` served facade and JavaScript load order.
- Keep feature-specific handlers in their existing feature modules unless the
  action kernel can call them through existing globals without changing runtime
  behavior.
- Keep `APP_JS`, `APP_CSS`, and `operating_layer_assets.py` as the served
  facade contract.

Expected benefit:

- Removes the largest remaining shared browser-action seam from the client
  composition root now that the server-side Browser Action Executor is isolated.
- Gives approval payload construction, action result rendering, command copying,
  and task action dispatch one local test surface.
- Keeps feature modules deep: Idea Greenhouse, Workbench, Pipeline, Obsidian,
  and Architecture Evidence should call or register with the action kernel
  rather than re-owning approval mechanics.

Risk:

- `setupTaskSurfaceActions()` is a cross-cutting event delegation hub for task
  controls, idea controls, local-model setup, refactor tabs, command copying,
  and promotion context. Keep the first extraction mechanical.
- `runApprovedCommand()` refreshes snapshots after successful actions; preserve
  that timing and selected-project behavior.
- Static string tests alone are not enough; run the browser smoke.

Focused tests:

```bash
env PYTHONPATH=src:. .venv/bin/python -m pytest \
  tests/test_operating_layer_assets.py -q
env PYTHONPATH=src:. .venv/bin/python -m pytest \
  tests/test_operator_ui_browser.py::test_app_loads_assets_snapshot_health_without_console_errors_or_overflow -q
```

Estimated size: medium.

### Server Follow-Up: Workbench/Gates Route Payload Locality

Files touched:

- `src/devflow/control_room/operating_layer_server.py`
- New Workbench/Gates route helper if the seam stays coherent
- Focused `tests/test_operating_layer.py` cases or new route-local tests

Seam:

- Consider moving `_handle_workbench_implement()` payload validation,
  implementation package construction, config construction, and async start
  handoff into a focused route helper.
- Keep HTTP parsing, status mapping, and `_send_action_error()` behavior in the
  request handler unless a typed result improves the interface.

Expected benefit:

- Continues the same server pattern established by Brainstorm, Builder-Judge,
  browse, local-model ensure, and Browser Action Executor extractions.
- Makes the workbench implementation path easier to test without reasoning
  through the full HTTP handler.

Risk:

- Workbench errors currently map to a mix of conflict, validation, OS, and
  internal action-error envelopes. Preserve status codes and retriable flags.
- This is lower priority than the client action kernel because server-side
  locality already improved substantially.

Focused tests:

```bash
env PYTHONPATH=src:. .venv/bin/python -m pytest \
  tests/test_operating_layer.py -k "workbench_implement or gates_setup" -q
```

Estimated size: medium.

### Deferred: Local-AI Command And Fleet Modules

Files touched:

- `src/devflow/control_room/local_ai_command.py`
- `src/devflow/control_room/local_ai_fleet.py`
- `tests/test_local_ai_command.py`

Seam:

- Reassess only when local-AI command work resumes. Graphify still flags these
  modules, but current product pressure is on the operating-layer action path.

Expected benefit:

- Avoids mixing local-AI command cleanup into the operating-layer refactor.
- Keeps model/runtime policy changes tied to explicit local-worker tasks.

Risk:

- Local worker policy is current and Qwen-first, but local fleet command
  behavior has a wide test blast radius. Do not use it as filler cleanup.

Focused tests when reopened:

```bash
env PYTHONPATH=src:. .venv/bin/python -m pytest \
  tests/test_local_ai_command.py -q
```

Estimated size: medium to large; not next.

## Do-Not-Touch List

- `src/devflow/control_room/operating_layer_assets.py`: keep the public asset
  facade exporting `APP_JS`, `APP_CSS`, and `INDEX_HTML`.
- `render()`, `renderFirstViewport()`, snapshot hydration, brainstorm-session
  adoption, and pipeline adoption in `operating_layer_script.py`: these are the
  client composition root and live snapshot bridge.
- Workbench, Obsidian intake, pipeline, and architecture evidence asset modules:
  treat them as the accepted combined asset-facade boundary unless a regression
  appears.
- Idea Greenhouse asset modules: accepted as extracted. Do not move task
  creation, classify/park/archive forms, or brainstorm touchpoints back into
  `operating_layer_script.py`.
- Brainstorm session management: route payloads are localized, but client
  session adoption/transcript loading remains coupled to task creation,
  pipeline adoption, and workbench state. Defer unless the client action-kernel
  extraction exposes a real regression.
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

Start with Client Action Kernel Extraction.

The server-side Browser Action Executor is now isolated, and Idea Greenhouse is
already an accepted asset module. The remaining high-leverage operating-layer
seam is the shared client action kernel in `operating_layer_script.py`, especially
`runApprovedCommand()`, `executeAction()`, and `setupTaskSurfaceActions()`.
Extract it mechanically, preserve the served `APP_JS` facade, and verify with
asset tests plus the focused browser smoke.
