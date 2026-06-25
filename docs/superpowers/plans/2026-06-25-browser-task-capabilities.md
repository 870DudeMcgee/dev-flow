# Browser Task Capabilities Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the next control-room cleanup slice by deepening browser task actions into a typed task capability Module instead of scattering command-string inference across Python, JavaScript, and server approval code.

**Architecture:** Create a `browser_task_capabilities` Module whose Interface is a typed `BrowserTaskCapability` plus small builders for intent, labels, required inputs, and supervisor classification. `task_workbench.py` becomes the Adapter that maps task state into these capabilities; `operating_layer_script.py` consumes the capability fields first and keeps command inference only as a legacy fallback. `operating_layer_server.py` remains the approval-gated execution Adapter and should not become the place that invents UI controls.

**Tech Stack:** Python 3.14, Pydantic, Typer, pytest, Playwright-backed browser tests where needed, Graphify generated architecture evidence.

---

## Current State

This plan starts from commit `a61e22f refactor: extract task run command module` with one completed but uncommitted slice in the working tree:

- `src/devflow/cli.py`
- `src/devflow/control_room/task_patch_gate_command.py`
- `tests/test_task_patch_gate_command.py`

`graphify-out/` is untracked generated evidence and should remain uncommitted unless the human explicitly changes that policy.

The refactor has already made real progress:

- `src/devflow/control_room/service.py` is now a small stable facade.
- `src/devflow/cli.py` is still large, but core task command behavior has moved into deeper task Modules.
- `src/devflow/control_room/task_workbench.py` already emits `controls` with `intent`, `safety_class`, `requires_human_approval`, and `required_inputs`.
- `src/devflow/control_room/operating_layer_script.py` already has `taskCapabilities(...)` helpers, but still duplicates fallback inference rules that also exist in Python.

Do not continue extracting random CLI functions just because they are long. The next useful depth is the Browser Task Capabilities seam from `docs/architecture/operating-layer-ui-deepening-backlog.md`.

## Execution Rules

- Do not ask the human to approve ordinary repo inspection, file reads, targeted tests, Graphify refreshes, or local commits described in this plan.
- Do not push, publish, open a PR, run broad promotion, or commit `graphify-out/` without explicit human approval.
- Preserve current behavior first. The browser should still execute only through `/api/actions/run` with exact approval payload checks.
- Commit after Task 0, then commit again after the browser capability slice passes verification.

## File Structure

- Create `src/devflow/control_room/browser_task_capabilities.py`: typed capability Module and command-to-capability rules.
- Create `tests/test_browser_task_capabilities.py`: direct tests for the capability Interface.
- Modify `src/devflow/control_room/task_workbench.py`: replace local command inference helpers with the new Module.
- Modify `src/devflow/control_room/operating_layer.py`: expose the same optional capability fields on task actions as the workbench emits.
- Modify `src/devflow/control_room/operating_layer_script.py`: consume typed capability fields first; keep command inference as a legacy fallback only.
- Modify `tests/test_task_workbench_projection.py`: assert capability classification and required inputs through the workbench Interface.
- Modify `tests/test_operating_layer.py`: assert snapshot actions and controls expose typed capability fields and browser JavaScript still consumes task controls.
- Modify `docs/architecture/operating-layer-ui-deepening-backlog.md`: add a dated checkpoint under Candidate 2 after implementation.

---

### Task 0: Commit The Pending Patch-Gate Extraction

**Files:**
- Modify: `src/devflow/cli.py`
- Create: `src/devflow/control_room/task_patch_gate_command.py`
- Create: `tests/test_task_patch_gate_command.py`

- [ ] **Step 1: Confirm the expected dirty state**

Run:

```bash
git status --short
```

Expected shape:

```text
 M src/devflow/cli.py
?? graphify-out/
?? src/devflow/control_room/task_patch_gate_command.py
?? tests/test_task_patch_gate_command.py
```

- [ ] **Step 2: Rerun the focused patch-gate tests**

Run:

```bash
env PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_task_patch_gate_command.py tests/test_patch_review.py tests/test_patch_dry_run.py -q
```

Expected: all selected tests pass.

- [ ] **Step 3: Check whitespace**

Run:

```bash
git diff --check
```

Expected: no output.

- [ ] **Step 4: Stage only code and test files**

Run:

```bash
git add src/devflow/cli.py src/devflow/control_room/task_patch_gate_command.py tests/test_task_patch_gate_command.py
git status --short
```

Expected: the three slice files are staged; `graphify-out/` remains untracked.

- [ ] **Step 5: Commit the slice**

Run:

```bash
git diff --cached --check
git commit -m "refactor: extract task patch gate command module"
git rev-parse --short HEAD
```

Expected: a new local commit is created. Record the new short SHA in the final handoff.

---

### Task 1: Add Direct Browser Capability Tests

**Files:**
- Create: `tests/test_browser_task_capabilities.py`

- [ ] **Step 1: Write the failing test file**

Create `tests/test_browser_task_capabilities.py` with:

```python
from __future__ import annotations

from devflow.control_room.browser_task_capabilities import (
    build_browser_task_capability,
    dedupe_browser_task_capabilities,
    intent_for_command,
    label_for_intent,
    required_inputs_for_capability,
)


def test_capability_infers_intent_label_inputs_and_supervisor_policy() -> None:
    capability = build_browser_task_capability(
        "start_shell",
        "Start shell",
        "devflow task run task-0001 --worker shell -- <command>",
    )

    assert capability.intent == "start_shell"
    assert capability.label == "Start shell"
    assert capability.scope == "task"
    assert capability.enabled is True
    assert capability.required_inputs == ["shell_command"]
    assert capability.safety_class == "approval_required_worker_runtime"
    assert capability.requires_human_approval is True
    assert capability.supervisor_may_auto_run is False
    assert capability.reason


def test_command_helpers_cover_browser_task_actions() -> None:
    assert intent_for_command("devflow task verify task-0001 --shell \"<command>\"") == "verify"
    assert intent_for_command("devflow task promote-preview task-0001") == "review_preview"
    assert intent_for_command("devflow task promote task-0001") == "promote"
    assert intent_for_command("devflow task cleanup task-0001 --preview") == "cleanup_preview"
    assert intent_for_command("devflow task close task-0001 --outcome evidence-only --reason \"<reason>\"") == "close"
    assert intent_for_command("devflow task show task-0001") == "inspect"
    assert intent_for_command("devflow task log task-0001") == "inspect_log"
    assert label_for_intent("cleanup_preview") == "Cleanup preview"
    assert required_inputs_for_capability("verify", "devflow task verify task-0001 --shell \"<command>\"") == [
        "verification_command",
    ]
    assert required_inputs_for_capability(
        "close",
        "devflow task close task-0001 --outcome evidence-only --reason \"<reason>\"",
    ) == ["close_outcome", "close_reason"]


def test_capability_dedupe_preserves_first_capability_order() -> None:
    first = build_browser_task_capability("inspect", "Inspect", "devflow task show task-0001")
    duplicate = build_browser_task_capability("inspect", "Show task", "devflow task show task-0001")
    shell = build_browser_task_capability(
        "start_shell",
        "Start shell",
        "devflow task run task-0001 --worker shell -- <command>",
    )

    assert dedupe_browser_task_capabilities([first, duplicate, shell]) == (first, shell)
```

- [ ] **Step 2: Run the test to verify it fails for the right reason**

Run:

```bash
env PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_browser_task_capabilities.py -q
```

Expected: fails with `ModuleNotFoundError: No module named 'devflow.control_room.browser_task_capabilities'`.

---

### Task 2: Implement The Browser Task Capabilities Module

**Files:**
- Create: `src/devflow/control_room/browser_task_capabilities.py`

- [ ] **Step 1: Add the Module**

Create `src/devflow/control_room/browser_task_capabilities.py` with:

```python
from __future__ import annotations

from collections.abc import Iterable

from pydantic import BaseModel, Field

from devflow.control_room.supervisor_surface import classify_supervisor_command


class BrowserTaskCapability(BaseModel):
    intent: str
    label: str
    command: str
    scope: str = "task"
    enabled: bool = True
    safety_class: str
    requires_human_approval: bool
    supervisor_may_auto_run: bool
    required_inputs: list[str] = Field(default_factory=list)
    reason: str | None = None


def build_browser_task_capability(
    intent: str,
    label: str,
    command: str,
    *,
    scope: str = "task",
    enabled: bool = True,
) -> BrowserTaskCapability:
    classification = classify_supervisor_command(command)
    return BrowserTaskCapability(
        intent=intent,
        label=label,
        command=command,
        scope=scope,
        enabled=enabled,
        safety_class=str(classification["safety_class"]),
        requires_human_approval=bool(classification["requires_human_approval"]),
        supervisor_may_auto_run=bool(classification["supervisor_may_auto_run"]),
        required_inputs=required_inputs_for_capability(intent, command),
        reason=classification.get("why_not_auto_runnable"),
    )


def intent_for_command(command: str) -> str:
    value = str(command or "")
    if " task run " in value and "--worker shell" in value:
        return "start_shell"
    if " task verify " in value:
        return "verify"
    if " task promote-preview " in value:
        return "review_preview"
    if " task promote " in value:
        return "promote"
    if " task cleanup " in value and "--preview" in value:
        return "cleanup_preview"
    if " task close " in value:
        return "close"
    if " task log " in value:
        return "inspect_log"
    if " task show " in value:
        return "inspect"
    return "next_safe_action"


def label_for_intent(intent: str) -> str:
    labels = {
        "start_shell": "Start shell",
        "retry": "Retry",
        "verify": "Verify",
        "review_preview": "Review preview",
        "promote": "Promote",
        "cleanup_preview": "Cleanup preview",
        "close": "Close",
        "inspect": "Inspect",
        "inspect_log": "Inspect log",
        "next_safe_action": "Next safe action",
    }
    return labels.get(intent, " ".join(part.capitalize() for part in intent.split("_")) or "Next safe action")


def label_for_command(command: str) -> str:
    return label_for_intent(intent_for_command(command))


def required_inputs_for_capability(intent: str, command: str) -> list[str]:
    value = str(command or "")
    if intent in {"start_shell", "retry"} or value.endswith(" -- <command>"):
        return ["shell_command"]
    if intent == "verify" or ' --shell "<command>"' in value or " --shell '<command>'" in value:
        return ["verification_command"]
    if intent == "close" or "<reason>" in value:
        return ["close_outcome", "close_reason"]
    return []


def dedupe_browser_task_capabilities(
    capabilities: Iterable[BrowserTaskCapability],
) -> tuple[BrowserTaskCapability, ...]:
    seen: set[tuple[str, str]] = set()
    deduped: list[BrowserTaskCapability] = []
    for capability in capabilities:
        key = (capability.intent, capability.command)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(capability)
    return tuple(deduped)


__all__ = [
    "BrowserTaskCapability",
    "build_browser_task_capability",
    "dedupe_browser_task_capabilities",
    "intent_for_command",
    "label_for_command",
    "label_for_intent",
    "required_inputs_for_capability",
]
```

- [ ] **Step 2: Run the direct capability tests**

Run:

```bash
env PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_browser_task_capabilities.py -q
```

Expected: `3 passed`.

---

### Task 3: Wire Task Workbench To The Capability Module

**Files:**
- Modify: `src/devflow/control_room/task_workbench.py`
- Modify: `src/devflow/control_room/operating_layer.py`
- Modify: `tests/test_task_workbench_projection.py`
- Modify: `tests/test_operating_layer.py`

- [ ] **Step 1: Replace the local classifier import in `task_workbench.py`**

Remove:

```python
from devflow.control_room.supervisor_surface import classify_supervisor_command
```

Add:

```python
from devflow.control_room.browser_task_capabilities import (
    build_browser_task_capability,
    intent_for_command,
    label_for_command,
)
```

- [ ] **Step 2: Add explicit capability fields to `TaskWorkbenchAction`**

Change `TaskWorkbenchAction` to:

```python
class TaskWorkbenchAction(BaseModel):
    label: str
    command: str
    scope: str
    safety_class: str
    requires_human_approval: bool
    supervisor_may_auto_run: bool
    intent: str | None = None
    required_inputs: list[str] = Field(default_factory=list)
    reason: str | None = None
```

- [ ] **Step 3: Replace workbench control/action builders**

Replace `_action(...)` and `_control(...)` with:

```python
def _action(label: str, command: str, scope: str) -> TaskWorkbenchAction:
    capability = build_browser_task_capability(
        intent_for_command(command),
        label,
        command,
        scope=scope,
    )
    return TaskWorkbenchAction(
        label=capability.label,
        command=capability.command,
        scope=capability.scope,
        safety_class=capability.safety_class,
        requires_human_approval=capability.requires_human_approval,
        supervisor_may_auto_run=capability.supervisor_may_auto_run,
        intent=capability.intent,
        required_inputs=capability.required_inputs,
        reason=capability.reason,
    )


def _control(intent: str, label: str, command: str) -> TaskWorkbenchControl:
    capability = build_browser_task_capability(intent, label, command)
    return TaskWorkbenchControl(**capability.model_dump())
```

- [ ] **Step 4: Remove duplicated helper functions from `task_workbench.py`**

Delete these functions from `task_workbench.py`:

```python
def _intent_for_command(command: str) -> str: ...
def _label_for_command(command: str) -> str: ...
def _required_inputs_for_control(intent: str, command: str) -> list[str]: ...
```

Then change the one `_task_controls(...)` call site from:

```python
commands.append((_intent_for_command(next_action_command), _label_for_command(next_action_command), next_action_command))
```

to:

```python
commands.append((intent_for_command(next_action_command), label_for_command(next_action_command), next_action_command))
```

- [ ] **Step 5: Mirror the action fields in the operating-layer snapshot model**

In `src/devflow/control_room/operating_layer.py`, change `OperatingLayerAction` to:

```python
class OperatingLayerAction(BaseModel):
    label: str
    command: str
    scope: str
    safety_class: str
    requires_human_approval: bool
    supervisor_may_auto_run: bool
    intent: str | None = None
    required_inputs: list[str] = Field(default_factory=list)
    reason: str | None = None
```

- [ ] **Step 6: Strengthen the workbench projection assertions**

In `tests/test_task_workbench_projection.py`, add these assertions near the existing control assertions:

```python
    assert new_controls["start_shell"].safety_class == "approval_required_worker_runtime"
    assert new_controls["start_shell"].requires_human_approval is True
    assert new_controls["start_shell"].supervisor_may_auto_run is False
    assert ready_controls["promote"].safety_class == "approval_required_git"
    assert ready_controls["promote"].requires_human_approval is True
```

- [ ] **Step 7: Strengthen the operating-layer snapshot assertions**

In `tests/test_operating_layer.py`, inside `test_operating_layer_snapshot_json_is_read_only_contract`, add:

```python
    assert payload["tasks"][0]["actions"][0]["intent"] == "start_shell"
    assert payload["tasks"][0]["actions"][0]["required_inputs"] == ["shell_command"]
```

- [ ] **Step 8: Run the workbench and snapshot tests**

Run:

```bash
env PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_browser_task_capabilities.py tests/test_task_workbench_projection.py tests/test_operating_layer.py::test_operating_layer_snapshot_json_is_read_only_contract tests/test_operating_layer.py::test_operating_layer_includes_multi_project_overview -q
```

Expected: all selected tests pass.

---

### Task 4: Make Browser JavaScript Treat Command Inference As Legacy Fallback

**Files:**
- Modify: `src/devflow/control_room/operating_layer_script.py`
- Modify: `tests/test_operating_layer.py`

- [ ] **Step 1: Rename the browser section comment**

In `src/devflow/control_room/operating_layer_script.py`, change:

```javascript
// === BROWSER ACTION CAPABILITIES ===
```

to:

```javascript
// === BROWSER TASK CAPABILITIES ===
```

- [ ] **Step 2: Mark `intentForCommand` as a fallback**

Add this comment immediately above `function intentForCommand(command) {`:

```javascript
// Legacy fallback for older snapshots. New task controls/actions should carry intent directly.
```

- [ ] **Step 3: Keep `normalizeCapability(...)` typed-field-first**

Verify this logic remains the shape of `normalizeCapability(...)`:

```javascript
function normalizeCapability(raw) {
  if (!raw || !raw.command) return null;
  const intent = raw.intent || intentForCommand(raw.command);
  const requiredInputs = Array.isArray(raw.required_inputs) && raw.required_inputs.length
    ? raw.required_inputs
    : inferredRequiredInputs(intent, raw.command);
  return {
    intent,
    label: raw.label || labelForIntent(intent),
    command: raw.command,
    scope: raw.scope || 'task',
    enabled: raw.enabled !== false,
    safety_class: raw.safety_class || '',
    requires_human_approval: Boolean(raw.requires_human_approval),
    supervisor_may_auto_run: Boolean(raw.supervisor_may_auto_run),
    required_inputs: requiredInputs,
    reason: raw.reason || null,
  };
}
```

- [ ] **Step 4: Update the JavaScript contract test**

In `tests/test_operating_layer.py`, inside `test_operating_layer_task_cards_expose_state_specific_next_actions`, update the string assertion:

```python
    assert "BROWSER TASK CAPABILITIES" in APP_JS
    assert "Legacy fallback for older snapshots" in APP_JS
    assert "raw.intent || intentForCommand(raw.command)" in APP_JS
    assert "raw.required_inputs" in APP_JS
```

Remove the old assertion:

```python
    assert "BROWSER ACTION CAPABILITIES" in APP_JS
```

- [ ] **Step 5: Run the JavaScript contract test**

Run:

```bash
env PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_operating_layer.py::test_operating_layer_task_cards_expose_state_specific_next_actions -q
```

Expected: the test passes.

---

### Task 5: Verify Server Approval Still Owns Execution

**Files:**
- Modify only if tests reveal a real mismatch: `src/devflow/control_room/operating_layer_server.py`
- Test: existing server and browser tests

- [ ] **Step 1: Run the approval-path regression tests**

Run:

```bash
env PYTHONPATH=src:. .venv/bin/python -m pytest \
  tests/test_operating_layer.py::test_operating_layer_server_runs_approved_shell_worker_in_task_workspace \
  tests/test_operating_layer.py::test_operating_layer_server_refuses_invalid_shell_worker_browser_runs \
  tests/test_operator_ui_browser.py::test_action_api_blocks_unsafe_commands \
  tests/test_supervisor_operating_surface.py::test_supervisor_policy_json_is_versioned_and_declares_boundaries \
  -q
```

Expected: all selected tests pass.

- [ ] **Step 2: If a test fails, keep the server as the Adapter**

Only edit `operating_layer_server.py` if a capability command emitted by the workbench is not accepted by an existing exact approval parser. Do not move browser rendering or capability selection into the server. The only acceptable server edits in this task are parser alignment fixes for commands already approved by existing policy.

---

### Task 6: Update Architecture Checkpoint

**Files:**
- Modify: `docs/architecture/operating-layer-ui-deepening-backlog.md`

- [ ] **Step 1: Add a checkpoint under Candidate 2**

Under `## Candidate 2: Browser Action/Capability Module`, add this after the Benefits list:

```markdown
Checkpoint 2026-06-25:

The browser task capability Interface now lives in `src/devflow/control_room/browser_task_capabilities.py`. `task_workbench.py` maps task state into typed capabilities, and browser JavaScript consumes capability fields before falling back to command inference for older snapshots. Server execution remains the approval-gated Adapter in `operating_layer_server.py`.
```

- [ ] **Step 2: Run stale-context and whitespace checks**

Run:

```bash
rg -n "BROWSER ACTION CAPABILITIES|_intent_for_command|_required_inputs_for_control" src/devflow/control_room tests docs
git diff --check
```

Expected: `rg` should find no stale `BROWSER ACTION CAPABILITIES` string and no deleted Python helper names. `git diff --check` should produce no output.

---

### Task 7: Run Final Verification And Graphify

**Files:**
- Generated/untracked evidence: `graphify-out/`

- [ ] **Step 1: Run the focused regression bundle**

Run:

```bash
env PYTHONPATH=src:. .venv/bin/python -m pytest \
  tests/test_browser_task_capabilities.py \
  tests/test_task_workbench_projection.py \
  tests/test_operating_layer.py::test_operating_layer_snapshot_json_is_read_only_contract \
  tests/test_operating_layer.py::test_operating_layer_includes_multi_project_overview \
  tests/test_operating_layer.py::test_operating_layer_task_cards_expose_state_specific_next_actions \
  tests/test_operating_layer.py::test_operating_layer_server_runs_approved_shell_worker_in_task_workspace \
  tests/test_operating_layer.py::test_operating_layer_server_refuses_invalid_shell_worker_browser_runs \
  tests/test_operator_ui_browser.py::test_action_api_blocks_unsafe_commands \
  tests/test_supervisor_operating_surface.py::test_supervisor_policy_json_is_versioned_and_declares_boundaries \
  -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Compile touched Python files**

Run:

```bash
env PYTHONPATH=src:. .venv/bin/python -m py_compile \
  src/devflow/control_room/browser_task_capabilities.py \
  src/devflow/control_room/task_workbench.py \
  src/devflow/control_room/operating_layer.py \
  tests/test_browser_task_capabilities.py \
  tests/test_task_workbench_projection.py \
  tests/test_operating_layer.py
```

Expected: no output.

- [ ] **Step 3: Refresh Graphify evidence**

Run:

```bash
.venv/bin/graphify update .
.venv/bin/graphify diagnose multigraph --graph graphify-out/graph.json
```

Expected: Graphify completes and the multigraph diagnosis reports no missing, dangling, duplicate, or collapsed endpoint edge groups.

- [ ] **Step 4: Inspect the Graphify connection for the new Module**

Run:

```bash
.venv/bin/graphify explain "control_room_browser_task_capabilities" --graph graphify-out/graph.json
```

Expected: the new Module appears in the graph and is reached from `control_room_task_workbench`. If Graphify uses a slightly different node id, run:

```bash
rg -n "browser_task_capabilities|BrowserTaskCapability" graphify-out/GRAPH_REPORT.md graphify-out/graph.json
```

Record the observed node id and metrics in the final handoff.

---

### Task 8: Commit The Browser Capability Slice

**Files:**
- Create: `src/devflow/control_room/browser_task_capabilities.py`
- Create: `tests/test_browser_task_capabilities.py`
- Modify: `src/devflow/control_room/task_workbench.py`
- Modify: `src/devflow/control_room/operating_layer.py`
- Modify: `src/devflow/control_room/operating_layer_script.py`
- Modify: `tests/test_task_workbench_projection.py`
- Modify: `tests/test_operating_layer.py`
- Modify: `docs/architecture/operating-layer-ui-deepening-backlog.md`

- [ ] **Step 1: Confirm `graphify-out/` stays untracked**

Run:

```bash
git status --short
```

Expected: source, tests, and docs are modified or untracked; `graphify-out/` is still untracked generated evidence.

- [ ] **Step 2: Stage only intended source, test, and doc files**

Run:

```bash
git add \
  src/devflow/control_room/browser_task_capabilities.py \
  src/devflow/control_room/task_workbench.py \
  src/devflow/control_room/operating_layer.py \
  src/devflow/control_room/operating_layer_script.py \
  tests/test_browser_task_capabilities.py \
  tests/test_task_workbench_projection.py \
  tests/test_operating_layer.py \
  docs/architecture/operating-layer-ui-deepening-backlog.md
git diff --cached --check
```

Expected: no whitespace errors.

- [ ] **Step 3: Commit**

Run:

```bash
git commit -m "refactor: deepen browser task capabilities"
git status --short
```

Expected: local commit created. Remaining dirt should be only untracked `graphify-out/`.

## Done State

The slice is done when:

- Pending Slice 18 is committed separately.
- `src/devflow/control_room/browser_task_capabilities.py` owns task capability intent, labels, required inputs, dedupe, and supervisor classification.
- `task_workbench.py` no longer owns duplicate capability inference helpers.
- The snapshot exposes typed capability fields for both task controls and task actions.
- Browser JavaScript uses capability fields first and labels command inference as a legacy fallback.
- The approval endpoint behavior is unchanged and still refuses unsafe commands.
- Focused tests, compile checks, `git diff --check`, and Graphify diagnosis pass.
- Two local commits exist: the patch-gate extraction commit and `refactor: deepen browser task capabilities`.
