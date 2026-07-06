# DevFlow UI Operability and Levers Implementation Plan

Status: historical plan. Any local-worker examples in this file predate
`docs/local-worker-policy.md`, which is the current opt-in visible Qwen worker
selection rule: `qwen36_27b_mtp_coder` subagent spawn in Codex and
`hermes-qwen-mtp` as the same-lane Hermes MCP packet wrapper.

> **For Hermes:** Use subagent-driven-development skill to implement task-by-task.

**Goal:** Make the operating-layer UI a complete, testable control room where every surfaced state has an obvious lever, every lever is connected to the backend contract, and browser tests prove the real user flows work.

**Architecture:** Keep DevFlow as the source of truth for state, evidence, verification, and promotion. The browser is an approval-gated operator surface: it renders snapshot-backed state, collects concrete operator inputs, calls safe `/api/actions/run` endpoints, and refreshes to show evidence-backed outcomes. Hermes/local models remain bounded worker runtimes behind packet/dry-run/fake-executable gates; no browser path directly launches live Hermes unless a later explicitly approved slice adds that.

**Tech Stack:** Python stdlib HTTP server, Pydantic snapshot models, bundled Python string assets (`operating_layer_html.py`, `operating_layer_script.py`, `operating_layer_styles.py`), Typer CLI, Playwright-style browser tests, pytest.

---

## Current Diagnosis

The backend is mostly wired, but the UI is still missing operator levers:

1. AI worker cards render but do not execute anything.
   - `worker_options.py` builds Hermes serial-packet commands.
   - `task_workbench.py` attaches `worker_options` to task snapshot data.
   - `operating_layer_script.py::renderWorkerOptions()` renders the cards.
   - No click handler consumes `[data-worker-option-card]` / `[data-worker-command]`.

2. Generated AI worker commands still contain placeholders.
   - `worker_options.py::_serial_packet_command()` appends `--allowed-file <allowed-file> --verify <verification-command>`.
   - `operating_layer_server.py::_approved_agent_serial_packet_command_args()` correctly rejects placeholder values.
   - Therefore the UI must either derive concrete values or collect them before POST.

3. Serial/Hermes run state exists in backend JSON but is not a first-class UI surface.
   - `operating_layer.py` includes `serial_local_agent_run` in the snapshot.
   - Tests prove `launch_status`, `runtime_kind`, and `ready_for_verifier` projection.
   - The browser UI does not clearly render this status or the next manual verifier action.

4. Tests cover fragments but not the actual user journey.
   - Existing tests prove render, direct API POST, and backend projection.
   - Missing: click AI worker card → fill concrete packet inputs → create packet → refresh → show packet/run status.

---

## Design Principles

- **One visible lever per visible recommendation.** If the UI recommends a worker, there must be a button or form that does the safe next step.
- **No placeholder command execution.** Browser paths must refuse `<allowed-file>`, `<verification-command>`, `<reason>`, or `<command>` before POST.
- **No hidden state transitions.** After every action, refresh snapshot and show the new evidence path, status, and next safe action.
- **Browser allowed:** evidence-writing packet creation, read-only inspection, safe task-state transitions with approval.
- **Browser blocked:** live Hermes non-dry-run launch, raw model/provider execution, git promotion/push unless separately approved by existing policy.
- **Backend contract first, UI second.** Data in snapshot should be explicit; UI should not scrape command strings to infer critical state when backend can expose fields.
- **TDD every slice.** Each slice starts with one failing test that proves the missing lever or broken connection.

---

## Target User Flow

```text
Operator opens DevFlow UI
  → sees active task and recommended Hermes/local worker card
  → clicks “Create packet”
  → UI opens/expands packet form
  → operator confirms/edits allowed files and verification command
  → UI previews exact devflow agent serial-packet command
  → operator approves exact command
  → /api/actions/run creates packet only
  → UI refreshes snapshot
  → task/launchpad shows packet evidence path + next safe action
  → serial runtime card shows not_started / ready_for_launch
  → operator can copy terminal-only hermes-run dry-run/manual launch command
  → after external launch writes hermes-run.json, UI shows ready_for_verifier
  → operator has verifier lever or command copy for completion-verifier.py
```

---

## Slice 1 — Make AI Worker Cards Real Controls

**Goal:** Clicking a rendered AI worker card exposes an actionable packet-creation panel instead of being display-only.

**Files:**
- `src/devflow/control_room/operating_layer_script.py`
- `tests/test_operator_ui_browser.py`

**RED test:** Add browser test:

```python
def test_clicking_ai_worker_card_opens_packet_form(browser_page):
    page, _ = browser_page
    page.locator('#active-work-groups .worker-card', has_text='Browser active work').locator('[data-select-task]').first.click()
    ai_card = page.locator('[data-worker-option-card][data-worker-action-kind="serial_packet"]').first
    ai_card.click()
    expect(page.locator('#next-task-packet-panel')).to_be_visible()
    expect(page.locator('#next-task-packet-panel')).to_contain_text('Create serial packet')
    expect(page.locator('[data-packet-allowed-files]')).to_be_visible()
    expect(page.locator('[data-packet-verify-command]')).to_be_visible()
```

**Implementation:**
- Add click handler for `[data-worker-option-card]`.
- If card is disabled, show blocked reason and do not open the form.
- If `data-worker-action-kind="serial_packet"`, render packet panel in `#next-task-command-output` or a dedicated `#next-task-packet-panel` inside launchpad.
- Include:
  - worker label/profile/model
  - command preview
  - allowed files input
  - verification command input
  - approval button

**Verification:**

```bash
env PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_operator_ui_browser.py -q
```

---

## Slice 2 — Replace Placeholder Commands With Concrete Packet Inputs

**Goal:** The browser creates a valid, policy-approved serial packet command from operator inputs.

**Files:**
- `src/devflow/control_room/operating_layer_script.py`
- `tests/test_operator_ui_browser.py`

**RED test:** Extend the click-flow test:

```python
def test_ai_worker_packet_form_creates_packet(browser_page, scratch_state):
    page, _ = browser_page
    page.locator('#active-work-groups .worker-card', has_text='Browser active work').locator('[data-select-task]').first.click()
    page.locator('[data-worker-option-card][data-worker-action-kind="serial_packet"]').first.click()
    page.locator('[data-packet-allowed-files]').fill('src/example.py')
    page.locator('[data-packet-verify-command]').fill('python -m pytest tests/example.py -q')
    page.locator('[data-create-serial-packet]').click()
    expect(page.locator('#next-task-command-output')).to_contain_text('Exit 0', timeout=15_000)
    packet_dirs = list((scratch_state.root / '.devflow' / 'local-agent-runs').glob('*'))
    assert packet_dirs
    manifest = json.loads((packet_dirs[0] / 'run.json').read_text())
    assert manifest['runtime']['kind'] == 'hermes-profile'
    assert manifest['safety']['model_launch'] is False
```

**Implementation:**
- Add `materializeSerialPacketCommand(command, {allowedFiles, verifyCommand})`.
- Support comma/newline-separated allowed files.
- Repeat `--allowed-file` for each concrete file.
- Replace or remove placeholder tail from the base command.
- Shell-quote every value with existing `shellQuote()`.
- Reject empty values in the browser before POST.
- Reject any command still containing `<...>` before `runApprovedCommand()`.

**Verification:**

```bash
env PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_operator_ui_browser.py tests/test_supervisor_operating_surface.py -q
git diff --check
```

---

## Slice 3 — Move Packet Form Defaults Into Backend Snapshot Contract

**Goal:** UI does not guess defaults from command strings; backend provides recommended allowed files and verification commands.

**Files:**
- `src/devflow/control_room/worker_options.py`
- `src/devflow/control_room/task_workbench.py`
- `tests/test_worker_options_projection.py`
- `tests/test_operating_layer.py`

**Contract addition:** Extend `WorkerOption` with:

```python
recommended_allowed_files: list[str] = Field(default_factory=list)
recommended_verification_commands: list[str] = Field(default_factory=list)
needs_operator_inputs: list[str] = Field(default_factory=list)
```

**RED test:**

```python
def test_local_hermes_worker_option_exposes_packet_input_contract(tmp_root):
    # selected qwen-worker routing fixture
    entry = next(w for w in result['ai_workers'] if w.worker_id == 'qwen-worker')
    assert entry.needs_operator_inputs == ['allowed_files', 'verification_commands']
    assert '<allowed-file>' not in ' '.join(entry.recommended_allowed_files)
```

**Implementation:**
- For now, derive conservative defaults from task evidence:
  - implementation context path if present
  - task workspace files if known
  - no fake source file if not knowable
- Keep `needs_operator_inputs` when defaults are empty.
- UI pre-fills available recommendations but still lets operator edit.

**Verification:**

```bash
env PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_worker_options_projection.py tests/test_operating_layer.py -q
```

---

## Slice 4 — Render Serial Runtime / Hermes Run Status As A First-Class UI Panel

**Goal:** The snapshot's `serial_local_agent_run` data becomes visible and actionable in the browser.

**Files:**
- `src/devflow/control_room/operating_layer_html.py`
- `src/devflow/control_room/operating_layer_script.py`
- `src/devflow/control_room/operating_layer_styles.py`
- `tests/test_operator_ui_browser.py`

**UI panel:** Add a compact “Worker Runtime” panel near the launchpad with:

- current run id
- runtime kind
- Hermes profile
- launch status: `not_started`, `completed`, `failed`, `timeout`
- verification status
- evidence links/paths
- next safe action
- copyable dry-run/manual command text, but no live browser launch

**RED test:**

```python
def test_ui_renders_serial_runtime_status_after_packet_or_hermes_run(browser_page):
    page, _ = browser_page
    expect(page.locator('#serial-runtime-panel')).to_be_visible()
    expect(page.locator('#serial-runtime-panel')).to_contain_text('Worker Runtime')
    expect(page.locator('#serial-runtime-panel')).to_contain_text('next safe action')
```

**Implementation:**
- Add `renderSerialRuntimePanel(snapshot.serial_local_agent_run)`.
- Call it from `render()` or `renderFirstViewport()`.
- Add empty state: “No packet yet — create one from a worker card.”
- Add status colors using existing semantic tone classes.

**Verification:**

```bash
env PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_operator_ui_browser.py tests/test_operating_layer.py -q
```

---

## Slice 5 — Create A Unified Action Result / Error Surface

**Goal:** Every UI lever reports the same clear states: pending, succeeded, blocked by policy, validation error, command failure.

**Files:**
- `src/devflow/control_room/operating_layer_script.py`
- `src/devflow/control_room/operating_layer_styles.py`
- `tests/test_operator_ui_browser.py`

**RED tests:**
- Empty allowed files shows local validation error and does not POST.
- Placeholder command error displays in launchpad.
- Policy-blocked command shows classification reason, not generic failure.

**Implementation:**
- Centralize `renderActionPending()`, `renderActionResult()`, and validation display.
- Add `renderActionError({message, field})`.
- Include classification badge when payload has `classification.safety_class`.
- Keep output truncated and readable.

**Verification:**

```bash
env PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_operator_ui_browser.py -q
```

---

## Slice 6 — Focus Overlay Must Have The Same Levers As Launchpad

**Goal:** Clicking task detail/focus overlay should not become a read-only dead end.

**Files:**
- `src/devflow/control_room/operating_layer_script.py`
- `tests/test_operator_ui_browser.py`

**RED test:**

```python
def test_focus_overlay_shows_ai_worker_packet_controls(browser_page):
    page, _ = browser_page
    page.locator('[data-inspect-task="task-0001"]').first.click()
    expect(page.locator('#focus-content [data-worker-option-card]')).to_be_visible()
```

**Implementation:**
- Reuse `renderWorkerOptions(task)` in `openFocus()`.
- Reuse the same packet form renderer and command materialization helper.
- Ensure event delegation handles focus overlay controls.

**Verification:**

```bash
env PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_operator_ui_browser.py -q
```

---

## Slice 7 — Navigation / Information Architecture Pass

**Goal:** The UI should answer: “What can I do next?” in one viewport.

**Files:**
- `src/devflow/control_room/operating_layer_html.py`
- `src/devflow/control_room/operating_layer_script.py`
- `src/devflow/control_room/operating_layer_styles.py`
- `tests/test_operator_ui_browser.py`

**Changes:**
- Keep guided control room as primary surface.
- Launchpad is the main action surface.
- Worker Runtime panel sits next to/below launchpad.
- Review queue and evidence stream remain adjacent.
- Detail overlay is for depth, not required for basic actions.
- Remove or collapse any redundant read-only panel that duplicates state without a lever.

**RED checks:**
- In first viewport, browser can locate:
  - active task selector
  - recommended worker action
  - serial runtime status
  - latest evidence
  - review/verify action if applicable

**Verification:**

```bash
env PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_operator_ui_browser.py -q
```

---

## Slice 8 — Full UI Contract Test Suite

**Goal:** Lock down the whole operator journey.

**Files:**
- `tests/test_operator_ui_browser.py`
- Possibly new `tests/test_operating_layer_ui_contract.py`

**Add journeys:**

1. **New task → recommended worker → packet created**
2. **Packet exists → runtime panel shows launch/manual next action**
3. **Hermes run evidence exists → runtime panel shows ready for verifier**
4. **Failed Hermes run evidence exists → runtime panel shows failed + reconcile next action**
5. **Blocked worker option → visible disabled card with concrete reason**
6. **No AI worker option → shell fallback still works**
7. **Focus overlay mirrors launchpad controls**
8. **Policy-blocked hermes-run is never executable from browser**

**Verification:**

```bash
env PYTHONPATH=src:. .venv/bin/python -m pytest \
  tests/test_operator_ui_browser.py \
  tests/test_worker_options_projection.py \
  tests/test_supervisor_operating_surface.py \
  tests/test_operating_layer.py \
  -q

git diff --check
```

---

## Slice 9 — Polish Pass: Visual Levers, Accessibility, and Copy Affordances

**Goal:** Make actionable things visually distinct from read-only state.

**Files:**
- `src/devflow/control_room/operating_layer_styles.py`
- `src/devflow/control_room/operating_layer_script.py`
- `tests/test_operator_ui_browser.py`

**Changes:**
- Buttons use semantic color:
  - teal/green: safe evidence-writing action
  - amber: verification / caution
  - red: close/reconcile
  - blue/indigo: inspect/read-only
- Add copy buttons for terminal-only commands.
- Add keyboard activation for worker cards (`Enter` / `Space`).
- Add ARIA labels for action cards and forms.
- Disabled worker cards show reason inline.

**Verification:**

```bash
env PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_operator_ui_browser.py -q
```

---

## Slice 10 — Aggregate Verification and Closure

**Goal:** Prove the full UI system works without live model/Hermes launches.

**Commands:**

```bash
env PYTHONPATH=src:. .venv/bin/python -m py_compile \
  src/devflow/control_room/operating_layer.py \
  src/devflow/control_room/operating_layer_server.py \
  src/devflow/control_room/operating_layer_script.py \
  src/devflow/control_room/worker_options.py \
  src/devflow/control_room/serial_local_agent_run.py

env PYTHONPATH=src:. .venv/bin/python -m pytest \
  tests/test_operator_ui_browser.py \
  tests/test_worker_options_projection.py \
  tests/test_supervisor_operating_surface.py \
  tests/test_operating_layer.py \
  tests/test_serial_local_agent_run.py \
  tests/test_hermes_worker_runtime.py \
  -q

git diff --check
```

**Manual smoke if server is available:**

```bash
env PYTHONPATH=src:. .venv/bin/python -m devflow.cli operating-layer --port 8766
```

Then open:

```text
http://localhost:8766
```

Smoke checklist:

- UI loads without console errors.
- Active task is visible.
- Recommended Hermes/local worker card is visible.
- Clicking card opens packet form.
- Empty form blocks locally.
- Concrete allowed file + verify command creates packet.
- Runtime panel refreshes with packet evidence.
- Browser does not offer live Hermes launch.
- Focus overlay exposes equivalent controls.

---

## Risks / Edge Cases

| Risk | Mitigation |
|---|---|
| UI posts placeholder command | Browser validation + server validation + regression tests. |
| Operator cannot infer allowed files | Backend exposes recommended defaults and form requires explicit confirmation. |
| Worker card looks clickable but is disabled | Disabled state must include blocked reason and no click action. |
| Browser accidentally launches Hermes | Keep `hermes-run` non-dry-run blocked by policy; tests assert 409. |
| UI duplicates launchpad/focus logic | Extract shared render/helper functions in bundled JS. |
| Snapshot has data but UI hides it | First-viewport contract test must assert visible levers/status. |
| Tests only inspect data attributes | Add real click → POST → evidence-created tests. |

---

## Definition of Done

- [ ] Every visible recommended worker has an actionable UI path or a visible blocked reason.
- [ ] AI worker card click can create a packet with concrete allowed files and verification command.
- [ ] Browser never runs live Hermes/model/provider paths.
- [ ] Serial/Hermes runtime status is visible in the UI.
- [ ] Focus overlay has the same core levers as the launchpad.
- [ ] Action results are visible and understandable.
- [ ] Browser tests cover real click flows, not only data attributes.
- [ ] Aggregate focused tests pass.
- [ ] `git diff --check` passes.

---

## Compact Handoff Prompt

```text
Work in /Users/jewelbait/Desktop/Local AI Dev Team.

Implement Slice 1 only from:
docs/superpowers/plans/2026-06-21-devflow-ui-operability-and-levers.md

Goal: make AI worker cards in the operating-layer launchpad open a real packet-creation panel instead of being display-only. Do not launch Hermes, local models, providers, or workers.

Read first:
- docs/superpowers/plans/2026-06-21-devflow-ui-operability-and-levers.md
- src/devflow/control_room/operating_layer_script.py
- src/devflow/control_room/worker_options.py
- src/devflow/control_room/task_workbench.py
- src/devflow/control_room/operating_layer_server.py
- tests/test_operator_ui_browser.py

Implement Slice 1 only:
- Add/adjust a browser test proving clicking `[data-worker-option-card][data-worker-action-kind="serial_packet"]` opens a packet form/panel.
- Add UI event handling for AI worker cards.
- Disabled cards should show blocked reason and not open the form.
- Do not POST or create packets yet; Slice 1 only exposes the lever and form.

Run focused verification:
env PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_operator_ui_browser.py -q
git diff --check

Stop after Slice 1. Report files changed, exact test output, risks, and next safe slice. Do not stage, commit, push, or continue to Slice 2 unless explicitly approved.
```
