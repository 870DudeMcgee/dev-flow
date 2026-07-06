# Brainstorm Pipeline Browser Proof Fix Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` or `executing-plans` to implement this plan task-by-task. Track progress with the checkbox steps below.

Date: 2026-06-26
Status: ready for implementation handoff

## Goal

Make the browser Brainstorm-to-Pipeline path prove itself in a fresh Dev-Flow scratch project before any shipping decision.

After this slice:

- Sending a Brainstorm message from the active browser UI unlocks the next Pipeline action without a full page reload, even when the model provider is unavailable or returns an error.
- Browser reloads keep `brainstormSessionId`, first-viewport Brainstorm state, and Pipeline action buttons aligned to the same persisted session.
- Clicking the visible spec, plan, implementation, and create-task controls uses the session with the transcript and does not fail with `brainstorm session has no transcript`.
- Provider failure is visible evidence, not a dead end. Local stage artifacts still get written by the existing `use_model: false` or model-error fallback path.
- A fresh scratch browser proof covers Brainstorm -> Spec -> Plan -> Implementation -> Create task -> Run shell -> Verify -> Promote preview -> Promote.

## Current State

Start from clean `main` at:

```text
57f133cc docs: record control room cleanup release gate
```

Dev-Flow Git status before this plan was written:

- `origin/main` matches local `main`
- clean worktree
- `safe_for_worker_writes: yes`
- `safe_for_promotion: yes`
- `safe_for_push: yes`

A manual Playwright proof was run against a fresh scratch project at `/tmp/devflow-ui-proof.PMF88C` served on `http://127.0.0.1:8767`. The temporary screenshots are under `/tmp/devflow-ui-proof-flow/` while that `/tmp` evidence remains available.

Observed results:

- The UI loads and the first viewport exposes `Brainstorm`, `Pipeline`, `Worker lanes`, `Review queue`, `Evidence stream`, and `Next Task`.
- Sending a Brainstorm message records transcript evidence, but the provider call failed with `Provider 'openrouter' request failed: HTTP Error 404: Not Found`.
- The transcript endpoint was healthy for the submitted session. `/api/brainstorm/transcript?session_id=browser-mquybten` returned a Pipeline with transcript complete and `next_step_label: "Escalate to spec"`.
- The Pipeline controls did not unlock immediately after the message response. `button[data-brainstorm-stage]` did not render until a full page reload.
- After reload, the server first viewport displayed the persisted Pipeline, but browser JavaScript created or kept a different `brainstormSessionId`. Clicking the visible spec action posted to the wrong session and failed with `brainstorm session has no transcript: browser-mquyd7yo`.
- Once a task was created separately, the browser task loop worked: run shell, verify, promote preview, and promote completed through the UI.

Screenshots from the proof run, if still present:

- `/tmp/devflow-ui-proof-flow/02-after-send.png`: provider error after Brainstorm send.
- `/tmp/devflow-ui-proof-flow/05-reload-after-transcript.png`: persisted Pipeline visible after reload.
- `/tmp/devflow-ui-proof-flow/07-after-spec-click.png`: spec click failed because the browser used the wrong session.
- `/tmp/devflow-ui-proof-flow/08-task-created-ui.png` through `/tmp/devflow-ui-proof-flow/14-after-promote.png`: task-side loop working after a task exists.

## Non-Goals

- Do not ship, tag, publish, promote broadly, or push without explicit human approval.
- Do not use Computer Use; it is blocked on local macOS permissions and is not needed for this slice.
- Do not use Hyperplane.
- Do not replace the Brainstorm provider registry or make model success a prerequisite for local progress.
- Do not refactor unrelated operating-layer UI, task workbench, Graphify, or release-readiness code.
- Do not commit generated `graphify-out/`, `.devflow/`, screenshots, or scratch project evidence.

## Files Likely To Modify

- `src/devflow/control_room/operating_layer_script.py`
- `tests/test_operator_ui_browser.py`
- `tests/test_operating_layer.py`
- optionally `tests/test_brainstorm_workbench.py` if backend model-error fallback needs an additional focused assertion
- optionally `docs/architecture/control-room-cleanup-checkpoint-2026-06-25.md` to record the new functional proof outcome

## Task 0: Confirm Baseline

- [ ] Run:

```bash
git status --short
PYTHONPATH=src:. .venv/bin/python -m devflow.cli git status
git log --oneline -5
```

Expected:

- normal Git status is clean
- Dev-Flow reports `safe_for_worker_writes: yes`
- `origin/main` and local `main` are aligned before implementation starts
- latest commit is `57f133cc docs: record control room cleanup release gate`

## Task 1: Add Failing Coverage For The Two Browser Bugs

Files:

- `tests/test_operator_ui_browser.py`
- `tests/test_operating_layer.py`

- [ ] Add a browser test that proves a Brainstorm message response refreshes Pipeline without a reload.

Recommended shape:

- Use the served UI from the existing browser fixture or a small dedicated browser fixture.
- Avoid live model dependency. Use Playwright request routing for `/api/brainstorm/message` and `/api/brainstorm/transcript?*`, or use a deterministic server setup where the provider is unavailable.
- Submit a message through `#brainstorm-chat-form`.
- Return or produce a failed provider payload that includes the same `session_id` and a transcript-backed Pipeline where Brainstorm is complete and Spec is the next action.
- Assert, without page reload, that the Pipeline renders an enabled `data-brainstorm-stage="spec"` action or enabled primary Pipeline action for Spec.
- Assert `localStorage.getItem("devflow-brainstorm-session")` matches the response `session_id`.

- [ ] Add a browser test that proves reload session adoption.

Recommended shape:

- In the scratch project, create `.devflow/brainstorms/browser-existing/transcript.jsonl` with one user message before or during the test.
- Reload the page after that session exists.
- Assert the browser adopts `browser-existing` as the active session when the first viewport presents that session.
- Click the enabled spec action.
- Assert the UI does not append `brainstorm session has no transcript`.
- Assert `.devflow/brainstorms/browser-existing/spec.md` exists or that the transcript endpoint reports `pipeline.has_spec is true`.

- [ ] Add or extend a server/unit test in `tests/test_operating_layer.py` that documents the backend contract used by the browser:

```text
POST /api/brainstorm/message
  -> returns session_id even when status is failed because the provider is unavailable
GET /api/brainstorm/transcript?session_id=<same>
  -> returns pipeline.session_id == <same>
  -> returns pipeline.stages
  -> marks Brainstorm complete when transcript records exist
  -> exposes Spec as the first actionable stage
```

- [ ] Run the new tests and confirm they fail for the expected reasons before editing implementation:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest \
  tests/test_operator_ui_browser.py \
  tests/test_operating_layer.py \
  -k 'brainstorm or pipeline' \
  -q
```

Expected initial failures:

- Pipeline action is not enabled after message submission.
- Reloaded browser uses a different session ID than the first-viewport Pipeline session.

## Task 2: Centralize Browser Brainstorm Session Authority

File:

- `src/devflow/control_room/operating_layer_script.py`

- [ ] Replace direct repeated assignments to `brainstormSessionId` and `localStorage.setItem("devflow-brainstorm-session", ...)` with one small helper, for example:

```javascript
function setActiveBrainstormSession(sessionId) {
  const sid = String(sessionId || '').trim();
  if (!sid) return false;
  brainstormSessionId = sid;
  localStorage.setItem('devflow-brainstorm-session', sid);
  loadBrainstormDefinitionOfDone();
  return true;
}
```

- [ ] Use the helper in:

- top-level initialization
- `newBrainstormSession()`
- `loadBrainstormSessions()` click handler
- Idea detail `data-idea-brainstorm` handler
- `sendBrainstormMessage()` response handling
- `loadBrainstormTranscript(sessionId)`
- any create-task or Pipeline bridge code that changes active Brainstorm context

- [ ] In `loadSnapshot(project)`, before `render()`, adopt the first-viewport Brainstorm session when the snapshot presents a persisted session and the browser has not already loaded matching Pipeline state.

Implementation constraint:

- Keep the browser and first viewport internally consistent. If `snapshot.first_viewport.pipeline.session_id` is `browser-existing`, `brainstormSessionId` must also be `browser-existing` before `renderFirstViewport()` decides whether to apply the presentation Pipeline.

- [ ] Preserve user control:

- `New session` still creates a fresh browser session and clears the visible transcript.
- Selecting a session from the side list still overrides the first-viewport latest session.
- Starting a Brainstorm from an idea still sets that idea-linked session active.

## Task 3: Refresh Pipeline State After Every Brainstorm Message

File:

- `src/devflow/control_room/operating_layer_script.py`

- [ ] In the Brainstorm form submit handler, after `sendBrainstormMessage(msg)` returns:

- set the active session from `payload.session_id` when present
- render the assistant or provider-error message as it does today
- always call `await refreshPipelineState()` before `loadBrainstormSessions()`
- keep focus restoration and send-button re-enable behavior unchanged

- [ ] Change `refreshPipelineState()` to preserve the full backend Pipeline object, not only the `stages` array.

Current behavior to replace:

```javascript
pipelineState.stages = data.pipeline?.stages || [];
```

Required behavior:

```javascript
pipelineState = data.pipeline && Array.isArray(data.pipeline.stages)
  ? data.pipeline
  : { stages: [] };
```

- [ ] Make `loadBrainstormTranscript(sessionId)` set the active session to `data.session_id || sessionId` before assigning Pipeline state.

- [ ] Keep provider errors visible in the transcript. A failed provider response should still leave the user with an actionable next Pipeline step when transcript evidence exists.

## Task 4: Ensure Stage Buttons Do Not Dead-End On Provider Failure

Files:

- `src/devflow/control_room/operating_layer_script.py`
- optionally `tests/test_brainstorm_workbench.py`

- [ ] Verify the existing backend behavior first:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_brainstorm_workbench.py -k 'manual or escalation' -q
```

Expected:

- manual spec and plan escalation writes artifacts
- model-error escalation returns `status: ready` and records the model error in the artifact instead of throwing

- [ ] If coverage is missing for model-error stage escalation, add one focused test in `tests/test_brainstorm_workbench.py`:

- seed a transcript
- monkeypatch the provider call to raise an HTTP-style error
- call `escalate_brainstorm_session(..., stage="spec", use_model=True)`
- assert the response is `status == "ready"`
- assert `model_info.used_model is false`
- assert `spec.md` exists and contains `Model error:`
- assert `pipeline_detail.has_spec is true`

- [ ] In the browser stage-click handler, keep the model identity message but treat a returned `payload.model_info.error` as a non-blocking warning when `payload.status === "ready"`.

Expected UI behavior:

- The user sees the provider/model error.
- The local artifact path is shown.
- Pipeline advances to the next stage after `refreshPipelineState()`.

## Task 5: Prove Brainstorm -> Task Creation From The Browser

Files:

- `tests/test_operator_ui_browser.py`
- optionally `docs/architecture/control-room-cleanup-checkpoint-2026-06-25.md`

- [ ] Add a browser test or extend the new browser proof so it completes this sequence from a fresh scratch project:

1. Submit a Brainstorm message.
2. Generate or escalate Spec.
3. Generate or escalate Plan.
4. Create the Implementation stage.
5. Click the browser task creation action.
6. Assert a new task appears in the Next Task launchpad and worker lanes.
7. Assert the task has Brainstorm lineage and an implementation context path.

Test constraints:

- Do not require a live OpenRouter, Ollama, or other provider call.
- Do not fake task creation after the stage bridge. The create-task step must hit the real `/api/brainstorm/create-task` route.
- The UI must name the selected model or provider-error evidence when a model path is attempted.

## Task 6: Run A Fresh Scratch Functional Proof

Files:

- runtime evidence only under `/tmp` or ignored `.devflow/`

- [ ] Create a fresh scratch repo outside this checkout:

```bash
SCRATCH="$(mktemp -d /tmp/devflow-ui-proof.XXXXXX)"
cd "$SCRATCH"
git init
git config user.email devflow-proof@example.invalid
git config user.name "DevFlow Proof"
printf '# UI proof\n' > README.md
git add README.md
git commit -m 'initial proof repo'
PYTHONPATH="<repo-root>/src:<repo-root>" "<repo-root>/.venv/bin/python" -m devflow.cli init
```

Replace `<repo-root>` with this checkout path only in the shell variable or command invocation. Do not write the absolute checkout path into tracked docs.

- [ ] Serve the active product UI from the scratch repo:

```bash
PYTHONPATH="<repo-root>/src:<repo-root>" "<repo-root>/.venv/bin/python" -m devflow.cli operating-layer serve --host 127.0.0.1 --port 8767
```

- [ ] Use Playwright against `http://127.0.0.1:8767` and capture screenshots under `/tmp/devflow-ui-proof-flow-<timestamp>/`.

Required proof steps:

1. Load the page and capture the first viewport.
2. Submit a Brainstorm message.
3. Without reloading, confirm the Spec action is enabled.
4. Click Spec and confirm `.devflow/brainstorms/<session>/spec.md` exists.
5. Click Plan and confirm `.devflow/brainstorms/<session>/plan.md` exists.
6. Fill Definition of Done with `proof.txt exists and contains ui-proof`.
7. Click Create Task and confirm the new task is selected in the launchpad.
8. Use the UI shell runner to run `printf ui-proof > proof.txt`.
9. Use the UI verify control with `test "$(cat proof.txt)" = ui-proof`.
10. Use the UI promote preview control.
11. Use the UI promote control.
12. Confirm `$SCRATCH/proof.txt` exists and contains `ui-proof`.

Expected:

- no `brainstorm session has no transcript` message
- provider errors are visible but non-blocking
- Pipeline advances after each browser action
- task-side run, verify, preview, and promote still work

## Task 7: Run Focused Verification

Files:

- no additional source edits expected

- [ ] Run:

```bash
git diff --check
PYTHONPATH=src:. .venv/bin/python -m pytest \
  tests/test_brainstorm_workbench.py \
  tests/test_brainstorm_task_bridge.py \
  tests/test_operating_layer.py \
  tests/test_operator_ui_browser.py \
  -q
PYTHONPATH=src:. .venv/bin/python -m devflow.cli operating-layer visual-qa --json
PYTHONPATH=src:. .venv/bin/python -m devflow.cli git status
```

Expected:

- all focused tests pass
- visual QA passes and still shows the current first-viewport workbench
- worktree is clean or only contains the intended tracked edits before commit
- `safe_for_worker_writes: yes`

## Task 8: Documentation And Final Handoff

Files:

- `docs/architecture/control-room-cleanup-checkpoint-2026-06-25.md`

- [ ] If the scratch proof passes, add a short dated note to the checkpoint with:

- the test commands that passed
- scratch proof location
- screenshots directory
- provider behavior observed
- final Dev-Flow git status

- [ ] Commit the implementation and checkpoint update with a concise message such as:

```bash
git add src/devflow/control_room/operating_layer_script.py tests/test_operator_ui_browser.py tests/test_operating_layer.py tests/test_brainstorm_workbench.py docs/architecture/control-room-cleanup-checkpoint-2026-06-25.md
git commit -m "fix: stabilize brainstorm pipeline browser flow"
```

Only include `tests/test_brainstorm_workbench.py` and the checkpoint doc if they were changed.

## Rollback And Risk Notes

- The riskiest behavior change is automatic adoption of the first-viewport Brainstorm session on reload. Keep selection from the session list and `New session` explicit so the operator can still switch context.
- Do not silence provider errors. The correct behavior is visible provider failure plus continued local artifact progress.
- Avoid string-only tests as the sole coverage. The browser bug was a runtime state bug; at least one Playwright test must exercise the actual DOM state.
- If browser proof fails after unit tests pass, trust the browser proof and repair the runtime flow before marking this slice complete.

## Next Safe Action

Start with Task 1 and write the failing browser tests for immediate Pipeline unlock and reload session adoption. Do not change implementation until those failures are captured.
