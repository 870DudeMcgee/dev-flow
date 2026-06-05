# Operating Layer Approved Action Result Retention Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep the result of a browser-approved Action Rail verification or promotion visible after the UI refreshes its snapshot.

**Architecture:** This is a client-side state-retention fix in the local operating-layer UI. The server already returns the right command result and canonical state changes; the browser loses the visible result because `refreshSnapshotAfterApprovedVerification()` reloads `/api/snapshot`, then `renderActions()` selects the refreshed task's new next action when the just-run command disappears from `task.actions`.

**Tech Stack:** Python-bundled vanilla JavaScript string in `src/devflow/control_room/operating_layer_script.py`, static asset contract assertions in `tests/test_operating_layer.py`, manual browser QA through `devflow operating-layer serve`.

---

## Problem Evidence

Browser dogfood on June 5, 2026 created registered project `os-ui-browser-test-20260605t231043z` under `/private/tmp/devflow-os-ui-projects-20260605T231043Z/` and exercised the whole operating-layer UI:

- Read-only Action Rail execution preserved output correctly because no snapshot refresh replaced the selected action.
- Approved task verification ran successfully and updated the task state, but the preview immediately changed to `devflow task promote-preview task-0001 --project ...`; the `Exit 0` verification result was no longer visible.
- Approved task promotion ran successfully for clean-baseline `task-0004`; task state became `promoted`, but the preview immediately changed to `devflow task show task-0004 --project ...`; the `Exit 0` / `Promotion complete.` result was no longer visible.

The canonical backend behavior is correct. The UI should retain the just-run result as transient browser state while still refreshing task lanes, metrics, and evidence from filesystem truth.

## File Structure

- Modify `src/devflow/control_room/operating_layer_script.py`.
  - Owns `actionRunState`, approved-action execution, snapshot refresh, Action Rail rendering, and preview rendering.
  - Keep the fix here. Do not add server state, local storage, a database, or canonical task artifacts.
- Modify `tests/test_operating_layer.py`.
  - Existing tests assert operating-layer asset hooks and server behavior.
  - Add a focused asset contract test for the new client-side result-retention hooks.
- Optional manual QA only: use a temporary registered project under `/private/tmp`, not the main checkout.

## Task 1: Lock The Client-Side Hook Contract

**Files:**
- Modify: `tests/test_operating_layer.py`

- [ ] **Step 1: Add a focused asset contract test**

Add this test near `test_operating_layer_assets_facade_keeps_split_asset_contract`:

```python
def test_operating_layer_approved_action_result_retention_hooks_are_present() -> None:
    assert "lastApprovedActionResult" in APP_JS
    assert "rememberApprovedActionResult" in APP_JS
    assert "refreshSnapshotAfterApprovedAction" in APP_JS
    assert "preservedActionResultForSelectedTask" in APP_JS
    assert "Last approved command" in APP_JS
```

- [ ] **Step 2: Run the test and confirm it fails**

Run:

```bash
.venv/bin/python -m pytest tests/test_operating_layer.py::test_operating_layer_approved_action_result_retention_hooks_are_present -q
```

Expected: fail because the hook names are not present yet.

## Task 2: Preserve The Just-Run Approved Action Result Across Snapshot Refresh

**Files:**
- Modify: `src/devflow/control_room/operating_layer_script.py`

- [ ] **Step 1: Add transient result state**

Near the existing top-level state:

```javascript
let actionRunState = null;
let lastApprovedActionResult = null;
```

- [ ] **Step 2: Store enough context before refresh**

Add these helper functions near `renderActionResult`:

```javascript
function rememberApprovedActionResult(action, runState) {
  if (!action || !runState || runState.status === "running") return;
  lastApprovedActionResult = {
    ...runState,
    action: { ...action, label: "Last approved command" },
    projectId: selectedProjectId,
    taskId: selectedTaskId,
  };
}

function preservedActionResultForSelectedTask(actions) {
  if (!lastApprovedActionResult) return null;
  if (lastApprovedActionResult.projectId !== selectedProjectId) return null;
  if (lastApprovedActionResult.taskId !== selectedTaskId) return null;
  if (actions.some((action) => action.command === lastApprovedActionResult.command)) return null;
  return lastApprovedActionResult;
}
```

- [ ] **Step 3: Rename and narrow the refresh helper**

Replace `refreshSnapshotAfterApprovedVerification(action)` with:

```javascript
async function refreshSnapshotAfterApprovedAction(action) {
  const priorTaskId = selectedTaskId;
  const priorRunState =
    actionRunState && actionRunState.command === action.command ? { ...actionRunState } : null;
  if (priorRunState) rememberApprovedActionResult(action, priorRunState);
  await loadSnapshot(selectedProjectId);
  if (priorTaskId && taskById(priorTaskId)) selectedTaskId = priorTaskId;
  if (lastApprovedActionResult && lastApprovedActionResult.taskId === selectedTaskId) {
    selectedActionCommand = lastApprovedActionResult.command;
    actionRunState = lastApprovedActionResult;
  } else {
    const refreshedAction = (taskById(selectedTaskId)?.actions || []).find((item) => item.command === action.command);
    if (refreshedAction) selectedActionCommand = refreshedAction.command;
  }
  render();
}
```

- [ ] **Step 4: Update the call site**

In `executeAction`, replace:

```javascript
await refreshSnapshotAfterApprovedVerification(action);
```

with:

```javascript
await refreshSnapshotAfterApprovedAction(action);
```

- [ ] **Step 5: Inject the preserved action into the rendered Action Rail list**

In `renderActions()`, after `const visibleActions = actions.slice(0, 8);`, replace the selection/list logic with this shape:

```javascript
  const preservedResult = preservedActionResultForSelectedTask(visibleActions);
  const renderedActions = preservedResult ? [preservedResult.action, ...visibleActions].slice(0, 8) : visibleActions;
  if (!renderedActions.some((action) => action.command === selectedActionCommand)) {
    selectedActionCommand = renderedActions[0].command;
  }
  renderedActions.forEach((action) => {
```

At the bottom of `renderActions()`, replace the preview call with:

```javascript
  renderActionPreview(renderedActions.find((action) => action.command === selectedActionCommand) || renderedActions[0]);
```

- [ ] **Step 6: Let the preview read preserved results**

In `renderActionPreview(action)`, replace:

```javascript
const actionResult = actionRunState && actionRunState.command === action.command ? actionRunState : null;
```

with:

```javascript
const preservedResult =
  lastApprovedActionResult && lastApprovedActionResult.command === action.command
    ? lastApprovedActionResult
    : null;
const actionResult =
  actionRunState && actionRunState.command === action.command ? actionRunState : preservedResult;
```

- [ ] **Step 7: Keep the old hook assertion updated**

In `tests/test_operating_layer.py`, replace existing assertions for `refreshSnapshotAfterApprovedVerification` with `refreshSnapshotAfterApprovedAction`.

## Task 3: Verify The Focused Tests

**Files:**
- Test: `tests/test_operating_layer.py`

- [ ] **Step 1: Run the focused asset test**

Run:

```bash
.venv/bin/python -m pytest tests/test_operating_layer.py::test_operating_layer_assets_facade_keeps_split_asset_contract tests/test_operating_layer.py::test_operating_layer_approved_action_result_retention_hooks_are_present -q
```

Expected: both tests pass.

- [ ] **Step 2: Run the existing approved-action server tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_operating_layer.py::test_operating_layer_server_runs_approved_task_verification tests/test_operating_layer.py::test_operating_layer_server_runs_approved_task_promotion tests/test_operating_layer.py::test_operating_layer_server_blocks_approval_required_actions -q
```

Expected: all three tests pass. This confirms the client-only change did not weaken server guardrails.

## Task 4: Browser QA The Actual Regression

**Files:**
- No source edits in this task.

- [ ] **Step 1: Create a temporary registered project**

Run from `<repo-root>`:

```bash
TS=$(date -u +%Y%m%dT%H%M%SZ)
ROOT="/private/tmp/devflow-approved-result-retention-$TS"
.venv/bin/python -m devflow.cli project create "Approved Result Retention $TS" --projects-root "$ROOT"
```

Expected: command prints a project id and path.

- [ ] **Step 2: Create verification and promotion tasks**

Use the project id from Step 1:

```bash
PROJECT="<project-id-from-step-1>"
.venv/bin/python -m devflow.cli task create --project "$PROJECT" "Browser verification result remains visible"
.venv/bin/python -m devflow.cli task run task-0001 --project "$PROJECT" --worker shell -- /bin/sh -c 'printf "verification result\n" > result.txt'
.venv/bin/python -m devflow.cli git checkpoint --message "test: checkpoint retention project baseline" --yes
.venv/bin/python -m devflow.cli task create --project "$PROJECT" "Browser promotion result remains visible"
.venv/bin/python -m devflow.cli task run task-0002 --project "$PROJECT" --worker shell -- /bin/sh -c 'printf "promotion result\n" > promoted.txt'
.venv/bin/python -m devflow.cli task verify task-0002 --project "$PROJECT" --shell 'test -s promoted.txt'
.venv/bin/python -m devflow.cli task promote-preview task-0002 --project "$PROJECT"
```

Expected: `task-0001` is complete and needs verification; `task-0002` is verified and ready to promote with a valid baseline.

- [ ] **Step 3: Serve the UI**

Run:

```bash
.venv/bin/python -m devflow.cli operating-layer serve --host 127.0.0.1 --port 8766
```

Expected: prints `Dev-Flow Operating Layer: http://127.0.0.1:8766`.

- [ ] **Step 4: Browser-check approved verification result retention**

Open `http://127.0.0.1:8766`, select the temporary project, select `task-0001`, enter verification command `test -s result.txt`, and click `Approve and run verification`.

Expected visible result after snapshot refresh:

```text
Last approved command
Exit 0
task-0001: verification passed
```

Expected refreshed state on the same screen:

```text
task-0001
Verification passed
devflow task promote-preview task-0001
```

- [ ] **Step 5: Browser-check approved promotion result retention**

Select `task-0002`, choose `Approve promotion`, add a short context note, and click `Approve & promote`.

Expected visible result after snapshot refresh:

```text
Last approved command
Exit 0
Promotion complete.
```

Expected refreshed state:

```text
task-0002
promoted
devflow task show task-0002
```

- [ ] **Step 6: Browser-check blocked worker runtime remains blocked**

Create or select an unrun task. Confirm the `devflow task run ... --worker shell ...` action still shows `Approval required in CLI` and cannot run from the browser.

Expected: no `Execute` button for worker runtime, and a direct `/api/actions/run` request still returns `409 Conflict` with `"executed": false`.

## Task 5: Final Verification

**Files:**
- No source edits in this task.

- [ ] **Step 1: Run focused tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_operating_layer.py -q
```

Expected: all operating-layer tests pass.

- [ ] **Step 2: Run visual QA contract**

Run:

```bash
.venv/bin/python -m devflow.cli operating-layer visual-qa --json
```

Expected: all checks have `"status": "pass"`.

- [ ] **Step 3: Check Git state through Dev-Flow**

Run:

```bash
.venv/bin/python -m devflow.cli git status
```

Expected: only the intended operating-layer files and tests are dirty. Do not revert unrelated existing dirty files.

## Constraints For The Next Agent

- Keep all active code edits inside `src/devflow/control_room/` plus focused tests in `tests/test_operating_layer.py`.
- Do not add backend persistence, local storage, a database, provider calls, worker execution from the browser, or broad mutation commands.
- Keep result retention transient to the current browser session.
- Keep server-side approval checks authoritative; the browser result card is display state only.
- Do not weaken `/api/actions/run` classification or approval phrase checks.
