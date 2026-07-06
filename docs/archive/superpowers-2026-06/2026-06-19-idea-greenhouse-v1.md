# Idea Greenhouse V1 Implementation Plan

Status: active implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `subagent-driven-development` to implement this task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn existing Idea Foundry intake into a visual, operator-centered Idea Greenhouse that supports zero-friction capture, lane-based idea visibility, safe parking, and obvious next actions.

**Architecture:** Build on the existing `.devflow/ideas/` filesystem source of truth and `src/devflow/control_room/idea_foundry.py` service. Add only the minimum missing service/state primitives (`parked` state and derived greenhouse lanes), project them into the operating-layer snapshot, then render a compact visual Greenhouse panel in the browser that captures ideas and shows Raw / Clarify / Candidate / Promoted / Parked / Archived lanes with per-card next actions. Browser mutations continue through existing approval-gated `/api/actions/run` paths.

**Tech Stack:** Python 3, Typer CLI, Pydantic snapshot models, Markdown/JSON/JSONL evidence, existing Dev-Flow atomic write helpers, operating-layer HTML/CSS/JS embedded assets, pytest.

---

## Product Intent

This plan implements the first concrete bridge from [docs/operator-centered-mission.md](../../operator-centered-mission.md):

```text
unlimited idea capture
  -> visible greenhouse lanes
  -> constrained active promotion
  -> one next action per idea
```

The point is not to create a new planning bureaucracy. The point is to let the operator dump ideas at full speed while Dev-Flow keeps them safe, visible, and separate from active execution.

## Current Reality From Code Audit

Existing implemented pieces:

- `src/devflow/control_room/idea_foundry.py`
  - `capture_idea`, `list_ideas`, `show_idea`, `classify_idea`, `promote_idea`, `archive_idea`, `record_idea_creation`
  - statuses: `inbox`, `classified`, `promoted`, `archived`
  - maturities: `spark`, `concept`, `candidate`, `goal_ready`, `task_ready`
  - evidence: `.devflow/ideas/<idea-id>/idea.json`, `raw.md`, `classification.md`, `promotion.md`, `events.jsonl`
- `src/devflow/control_room/idea_execution_bridge.py`
  - `preview_goal_from_idea`, `preview_task_from_idea`, `create_goal_from_idea`, `create_task_from_idea`
- `src/devflow/cli.py`
  - `devflow idea capture/list/show/classify/promote/scaffold-goal/create-goal/create-task/archive`
- `src/devflow/control_room/supervisor_surface.py`
  - idea capture/classify/promote/archive are approval-required evidence-writing commands
  - idea create-goal/create-task are approval-required task-state commands
- `src/devflow/control_room/operating_layer_server.py`
  - browser `/api/actions/run` already supports approved `devflow idea capture`
- `src/devflow/control_room/operating_layer.py`
  - snapshot does not yet expose Idea Foundry as a first-class visual projection
- `src/devflow/control_room/operating_layer_html.py` / `_script.py` / `_styles.py`
  - no Greenhouse panel exists yet

Important design decision:

- Do **not** create a second idea database.
- Do **not** call models in V1.
- Do **not** auto-promote ideas into tasks.
- Do **not** make parked ideas disappear.
- Do **not** make shell command boxes the primary interaction.

---

## V1 Scope

### Included

- Add `parked` as a non-destructive Idea Foundry status.
- Add `park_idea(root, idea_id, reason=...)` service function.
- Add `devflow idea park <idea-id> --reason ...` CLI command.
- Add deterministic derived Greenhouse lanes from existing idea metadata.
- Add operating-layer snapshot field `idea_greenhouse`.
- Add compact browser Greenhouse panel with:
  - zero-friction capture textbox;
  - lane counts;
  - cards for recent Raw / Clarify / Candidate / Promoted / Parked / Archived ideas;
  - clear next action labels/commands;
  - color-coded visual state.
- Reuse `/api/actions/run` for browser idea capture.
- Add browser-safe approval parsing for `devflow idea park` and `devflow idea archive` if the UI exposes those buttons.
- Add tests for service, CLI, snapshot, server approval, and UI asset contract.
- Update docs after tests pass.

### Explicitly Excluded From V1

- AI triage/model scoring.
- Similarity search/vector clustering.
- Daily digest automation.
- Telegram capture integration.
- Automatic goal/task creation from raw ideas.
- Background processing.
- New database tables.
- Provider-backed routing.

These belong in V1.5/V2 after the visual loop is real.

---

## Derived Greenhouse Lane Rules

Use a derived projection first. Avoid migrating old idea files unless necessary.

| Metadata condition | Greenhouse lane | Meaning | Primary next action |
|---|---|---|---|
| `status == inbox` and `maturity == spark` | `raw` | captured, unprocessed | classify or park |
| `status == classified` and `maturity in {spark, concept}` | `clarify` | needs shaping/questions | refine classification |
| `status == classified` and `maturity == candidate` | `candidate` | promising but not goal/task ready | promote readiness or park |
| `status == classified` and `maturity in {goal_ready, task_ready}` | `candidate` | ready for explicit promotion decision | promote to goal/task |
| `status == promoted` | `promoted` | human decision recorded | create goal/task or show created ref |
| `status == parked` | `parked` | safe later, not active | unpark/reclassify later |
| `status == archived` | `archived` | intentionally closed | inspect evidence only |

V1 can implement `parked`; V1 does **not** need an explicit `clustered` lane yet. Clustering is a V2 model/eval feature.

---

## File Structure

Modify:

- `src/devflow/control_room/idea_foundry.py`
- `src/devflow/cli.py`
- `src/devflow/control_room/supervisor_surface.py`
- `src/devflow/control_room/operating_layer.py`
- `src/devflow/control_room/operating_layer_server.py`
- `src/devflow/control_room/operating_layer_html.py`
- `src/devflow/control_room/operating_layer_script.py`
- `src/devflow/control_room/operating_layer_styles.py`
- `src/devflow/control_room/operating_layer_visual_qa.py`
- `tests/test_idea_foundry.py`
- `tests/test_supervisor_operating_surface.py`
- `tests/test_operating_layer.py`
- `README.md`
- `docs/control-room-mvp.md`
- `docs/mvp-contract.md`
- `docs/operator-centered-mission.md` only if implementation reveals a wording mismatch

Create only if needed:

- `tests/test_idea_greenhouse.py` if the snapshot projection becomes substantial enough to deserve its own test file.

---

## Working Rules

- Start from the current uncommitted docs baseline intentionally created by the operator-centered mission work. Do not revert those files.
- Before implementation, inspect `git status --short` and confirm no unrelated user changes are being overwritten.
- Use TDD for each behavior: failing test first, verify failure, implement, verify pass.
- Do not edit `src/devflow/_legacy/`.
- Do not add provider calls or background jobs.
- Keep browser mutations approval-gated.
- Run `scripts/run_tests.sh` equivalent for this repo if available; otherwise use the repo's existing venv/test command pattern already documented in Dev-Flow plans.
- For operating-layer UI changes, run targeted tests and, when practical, serve a cache-busted browser URL for visual verification.

---

## Task 1: Add Service Tests For Parked Ideas And Lane Projection

**Files:**

- Modify: `tests/test_idea_foundry.py`
- Possibly create: `tests/test_idea_greenhouse.py`

- [ ] **Step 1: Write failing tests for parking**

Append tests proving `park_idea` exists, preserves raw evidence, writes a reason, and emits an event.

```python
def test_park_idea_preserves_evidence_and_marks_safe_later(tmp_path: Path) -> None:
    item = capture_idea(tmp_path, "Build a voice capture inbox for ideas.", title="Voice idea capture")

    parked = park_idea(tmp_path, item["id"], reason="Great idea, not active this week.")

    assert parked["status"] == "parked"
    assert parked["park_reason"] == "Great idea, not active this week."
    assert parked["parked_at"] is not None
    idea_dir = tmp_path / ".devflow" / "ideas" / item["id"]
    assert (idea_dir / "raw.md").exists()
    assert '"event": "parked"' in (idea_dir / "events.jsonl").read_text(encoding="utf-8")
```

Expected RED: import error or missing `park_idea`.

- [ ] **Step 2: Write failing tests for derived lanes**

Add a service-level helper test. The helper name can be `greenhouse_lane_for_idea` or private `_greenhouse_lane_for_idea`; prefer public if `operating_layer.py` will import it.

```python
def test_greenhouse_lane_projection_uses_existing_status_and_maturity(tmp_path: Path) -> None:
    raw = capture_idea(tmp_path, "Raw thought")
    concept = capture_idea(tmp_path, "Needs clarification")
    classify_idea(tmp_path, concept["id"], maturity="concept", note="Needs sharper scope.")
    candidate = capture_idea(tmp_path, "Promising candidate")
    classify_idea(tmp_path, candidate["id"], maturity="candidate", note="Looks promising.")
    ready = capture_idea(tmp_path, "Task-sized idea")
    classify_idea(tmp_path, ready["id"], maturity="task_ready", note="Ready for task promotion.")
    promote_idea(tmp_path, ready["id"], target="task", rationale="Human approved.")
    parked = capture_idea(tmp_path, "Later idea")
    park_idea(tmp_path, parked["id"], reason="Later.")

    lanes = {item["id"]: greenhouse_lane_for_idea(item) for item in list_ideas(tmp_path)}

    assert lanes[raw["id"]] == "raw"
    assert lanes[concept["id"]] == "clarify"
    assert lanes[candidate["id"]] == "candidate"
    assert lanes[ready["id"]] == "promoted"
    assert lanes[parked["id"]] == "parked"
```

Expected RED: helper/status missing.

- [ ] **Step 3: Verify RED**

Run:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_idea_foundry.py -q
```

Expected: fails only for missing parked/lane behavior, not unrelated collection errors.

---

## Task 2: Implement Parked Ideas And Lane Helper

**Files:**

- Modify: `src/devflow/control_room/idea_foundry.py`
- Test: `tests/test_idea_foundry.py`

- [ ] **Step 1: Extend status constants and metadata**

In `idea_foundry.py`:

```python
ALLOWED_IDEA_STATUSES = {"inbox", "classified", "promoted", "parked", "archived"}
```

In `capture_idea`, add after `archive_reason`:

```python
        "parked_at": None,
        "park_reason": None,
```

- [ ] **Step 2: Add `park_idea`**

Add near `archive_idea`:

```python
def park_idea(root: Path, idea_id: str, *, reason: str) -> dict[str, Any]:
    metadata = _get_idea(root, idea_id)
    if metadata["status"] == "archived":
        raise IdeaFoundryError(f"Archived idea cannot be parked: {idea_id}")
    now = utc_now().isoformat()
    metadata["status"] = "parked"
    metadata["updated_at"] = now
    metadata["parked_at"] = now
    metadata["park_reason"] = reason.strip() or "No reason supplied."
    _write_idea(root, metadata)
    _append_idea_event(root, idea_id, "parked", {"parked_at": now, "reason": metadata["park_reason"]})
    return metadata
```

- [ ] **Step 3: Add lane helper**

```python
def greenhouse_lane_for_idea(metadata: dict[str, Any]) -> str:
    status = metadata.get("status")
    maturity = metadata.get("maturity")
    if status == "parked":
        return "parked"
    if status == "archived":
        return "archived"
    if status == "promoted":
        return "promoted"
    if status == "inbox":
        return "raw"
    if status == "classified" and maturity in {"spark", "concept"}:
        return "clarify"
    if status == "classified" and maturity in {"candidate", "goal_ready", "task_ready"}:
        return "candidate"
    return "raw"
```

- [ ] **Step 4: Verify GREEN**

Run:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_idea_foundry.py -q
```

Expected: all Idea Foundry tests pass.

---

## Task 3: Add CLI And Supervisor Support For Parking

**Files:**

- Modify: `src/devflow/cli.py`
- Modify: `src/devflow/control_room/supervisor_surface.py`
- Modify: `tests/test_idea_foundry.py`
- Modify: `tests/test_supervisor_operating_surface.py`

- [ ] **Step 1: Add failing CLI test**

Add to `tests/test_idea_foundry.py`:

```python
def test_cli_park_idea(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["idea", "capture", "Save this for later", "--title", "Later idea"])

    result = runner.invoke(app, ["idea", "park", "I-0001", "--reason", "Not this week."])
    shown = runner.invoke(app, ["idea", "show", "I-0001"])

    assert result.exit_code == 0, result.output
    assert "status: parked" in result.output
    assert "evidence_deleted: no" in result.output
    assert "status: parked" in shown.output
```

Expected RED: no such command.

- [ ] **Step 2: Add `idea park` CLI command**

In `src/devflow/cli.py`, add before `idea_archive`:

```python
@idea_app.command("park")
def idea_park(
    idea_id: str,
    reason: str = typer.Option("No reason supplied.", "--reason", help="Why this idea is safe to revisit later."),
) -> None:
    """Park an idea without losing its evidence."""
    try:
        from devflow.control_room.idea_foundry import IdeaFoundryError, park_idea

        item = park_idea(Path.cwd(), idea_id, reason=reason)
    except IdeaFoundryError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"idea_id: {item['id']}")
    typer.echo(f"status: {item['status']}")
    typer.echo("evidence_deleted: no")
```

- [ ] **Step 3: Add supervisor policy coverage**

Add `"devflow idea park"` to `APPROVAL_REQUIRED_EVIDENCE_WRITING_COMMANDS`.

Add a test in `tests/test_supervisor_operating_surface.py` confirming:

```python
classification = classify_supervisor_command("devflow idea park I-0001 --reason 'not now'")
assert classification["safety_class"] == APPROVAL_REQUIRED_EVIDENCE_WRITING
```

- [ ] **Step 4: Verify**

Run:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_idea_foundry.py tests/test_supervisor_operating_surface.py -q
```

Expected: pass.

---

## Task 4: Add Idea Greenhouse Snapshot Projection

**Files:**

- Modify: `src/devflow/control_room/operating_layer.py`
- Modify or create tests: `tests/test_operating_layer.py` or `tests/test_idea_greenhouse.py`

- [ ] **Step 1: Add failing snapshot test**

Add to `tests/test_operating_layer.py` or `tests/test_idea_greenhouse.py`:

```python
def test_operating_layer_projects_idea_greenhouse_lanes(tmp_path: Path) -> None:
    raw = capture_idea(tmp_path, "Raw idea", title="Raw idea")
    concept = capture_idea(tmp_path, "Needs clarity", title="Needs clarity")
    classify_idea(tmp_path, concept["id"], maturity="concept", note="Needs clearer scope.")
    candidate = capture_idea(tmp_path, "Candidate idea", title="Candidate idea")
    classify_idea(tmp_path, candidate["id"], maturity="candidate", note="Worth considering.")
    parked = capture_idea(tmp_path, "Parked idea", title="Parked idea")
    park_idea(tmp_path, parked["id"], reason="Not now.")

    payload = build_operating_layer_snapshot(tmp_path).model_dump()
    greenhouse = payload["idea_greenhouse"]

    assert greenhouse["counts"]["raw"] == 1
    assert greenhouse["counts"]["clarify"] == 1
    assert greenhouse["counts"]["candidate"] == 1
    assert greenhouse["counts"]["parked"] == 1
    assert greenhouse["primary_next_action"]["label"] == "Classify raw idea"
    assert greenhouse["lanes"][0]["id"] == "raw"
```

Expected RED: `idea_greenhouse` missing.

- [ ] **Step 2: Add Pydantic models**

In `operating_layer.py` near other snapshot models:

```python
class OperatingLayerIdeaAction(BaseModel):
    label: str
    command: str | None = None
    safety_class: str = "read_only"
    requires_human_approval: bool = False

class OperatingLayerIdeaCard(BaseModel):
    id: str
    title: str
    lane: str
    status: str
    maturity: str
    tags: list[str] = Field(default_factory=list)
    source: str | None = None
    updated_at: str | None = None
    summary: str = ""
    primary_action: OperatingLayerIdeaAction | None = None

class OperatingLayerIdeaLane(BaseModel):
    id: str
    label: str
    tone: str
    count: int
    cards: list[OperatingLayerIdeaCard] = Field(default_factory=list)

class OperatingLayerIdeaGreenhouse(BaseModel):
    headline: str
    counts: dict[str, int] = Field(default_factory=dict)
    lanes: list[OperatingLayerIdeaLane] = Field(default_factory=list)
    primary_next_action: OperatingLayerIdeaAction | None = None
```

Add field to `OperatingLayerSnapshot`:

```python
    idea_greenhouse: OperatingLayerIdeaGreenhouse | None = None
```

- [ ] **Step 3: Build projection from existing ideas**

Implement helper:

```python
IDEA_LANE_ORDER = ["raw", "clarify", "candidate", "promoted", "parked", "archived"]
IDEA_LANE_LABELS = {
    "raw": "Raw",
    "clarify": "Clarify",
    "candidate": "Candidate",
    "promoted": "Promoted",
    "parked": "Parked",
    "archived": "Archived",
}
IDEA_LANE_TONES = {
    "raw": "muted",
    "clarify": "purple",
    "candidate": "blue",
    "promoted": "green",
    "parked": "slate",
    "archived": "dark",
}
```

Actions:

```python
raw -> devflow idea classify <id> --maturity concept --note "<note>"
clarify -> devflow idea classify <id> --maturity candidate --note "<note>"
candidate/task_ready -> devflow idea promote <id> --to task --rationale "<rationale>"
candidate/goal_ready -> devflow idea promote <id> --to goal --rationale "<rationale>"
promoted/task -> devflow idea create-task <id> --dry-run
promoted/goal -> devflow idea create-goal <id> --dry-run
parked -> devflow idea show <id>
archived -> devflow idea show <id>
```

Do not use placeholder commands as browser one-click actions when required input is missing. For cards that need note/rationale, show the action label and command text, but mark `requires_human_approval=True` only if the command is concrete.

- [ ] **Step 4: Wire into `build_operating_layer_snapshot`**

Import from `idea_foundry`:

```python
from devflow.control_room.idea_foundry import IdeaFoundryError, greenhouse_lane_for_idea, list_ideas
```

Use safe fallback: if `.devflow/ideas/` is absent or malformed, show empty greenhouse rather than breaking the whole snapshot.

- [ ] **Step 5: Verify snapshot tests**

Run:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_operating_layer.py -q
```

Expected: pass.

---

## Task 5: Add Browser Approval Support For Safe Idea Actions

**Files:**

- Modify: `src/devflow/control_room/operating_layer_server.py`
- Modify: `tests/test_operating_layer.py`

- [ ] **Step 1: Add tests for approved idea park/archive**

The browser already supports approved idea capture. If the Greenhouse UI exposes Park/Archive buttons, add tests proving the server accepts only concrete safe commands.

Test cases:

```python
assert _approved_idea_capture_command_args('devflow idea capture "raw idea" --source operating-layer')
assert _approved_idea_evidence_command_args('devflow idea park I-0001 --reason "not this week"')
assert _approved_idea_evidence_command_args('devflow idea archive I-0001 --reason "duplicate"')
```

And reject:

```python
"devflow idea park I-0001 --reason <reason>"
"devflow idea classify I-0001 --maturity candidate --note <note>"
"devflow idea promote I-0001 --to task --rationale <rationale>"
```

Reason: V1 can safely one-click park/archive when reason is concrete, but classify/promote need real human content and should open/copy a command rather than silently run placeholders.

- [ ] **Step 2: Implement parser**

Add `_approved_idea_evidence_command_args(command)` that allows:

- `devflow idea park <id> --reason <concrete reason>`
- `devflow idea archive <id> --reason <concrete reason>`

Do not allow `classify` or `promote` until the UI provides a real note/rationale form.

- [ ] **Step 3: Wire approval chain**

In `_handle_action_run`, add `approved_idea_evidence = False`, evaluate it near `approved_idea_capture`, include it in the approval `or` chain, and route to `_approved_idea_evidence_command_args`.

- [ ] **Step 4: Verify server tests**

Run:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_operating_layer.py -q
```

---

## Task 6: Add Idea Greenhouse HTML Skeleton

**Files:**

- Modify: `src/devflow/control_room/operating_layer_html.py`
- Modify: `tests/test_operating_layer.py`
- Modify: `src/devflow/control_room/operating_layer_visual_qa.py`

- [ ] **Step 1: Add failing asset contract test**

Assert served HTML includes:

- `idea-greenhouse-section`
- `idea-capture-form`
- `idea-greenhouse-lanes`
- `idea-greenhouse-primary-action`

- [ ] **Step 2: Add panel after Brainstorm and before Next Task**

Insert after `</section>` for `brainstorm-section`:

```html
<section id="idea-greenhouse-section" class="panel idea-greenhouse-section" aria-label="Idea Greenhouse">
  <div class="panel-header">
    <div>
      <h2 class="panel-title">Idea Greenhouse</h2>
      <p class="panel-subtitle">Capture fast. Sort later. Keep active work constrained.</p>
    </div>
    <output id="idea-greenhouse-status" class="status-pill muted" aria-live="polite">Ready</output>
  </div>

  <form id="idea-capture-form" class="idea-capture-form">
    <textarea id="idea-capture-text" rows="3" placeholder="Dump the idea here. No organization required."></textarea>
    <div class="composer-row">
      <input id="idea-capture-title" type="text" placeholder="Optional title">
      <button id="idea-capture-submit" class="btn btn-primary" type="submit">Capture idea</button>
    </div>
  </form>

  <div id="idea-greenhouse-primary-action" class="idea-primary-action"></div>
  <div id="idea-greenhouse-lanes" class="idea-greenhouse-lanes"></div>
</section>
```

- [ ] **Step 3: Verify asset test fails only until JS/CSS are added**

Run targeted operating-layer tests.

---

## Task 7: Add Greenhouse CSS

**Files:**

- Modify: `src/devflow/control_room/operating_layer_styles.py`

- [ ] **Step 1: Add compact lane/card styling**

Use existing variables and preserve no-horizontal-overflow.

Required classes:

```css
.idea-greenhouse-section { }
.idea-capture-form { }
.idea-greenhouse-lanes { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }
.idea-lane { border: 1px solid var(--border); border-radius: 12px; background: var(--bg-2); }
.idea-lane-header { display: flex; justify-content: space-between; align-items: center; }
.idea-card { border-left: 3px solid var(--border); }
.idea-card.raw { border-left-color: var(--text-muted); }
.idea-card.clarify { border-left-color: #a371f7; }
.idea-card.candidate { border-left-color: var(--blue); }
.idea-card.promoted { border-left-color: var(--accent); }
.idea-card.parked { border-left-color: #6e7681; }
.idea-card.archived { opacity: 0.72; }
.idea-primary-action { }
```

Add responsive fallback:

```css
@media (max-width: 900px) {
  .idea-greenhouse-lanes { grid-template-columns: 1fr; }
}
```

- [ ] **Step 2: Keep visual hierarchy compact**

Cards should show:

```text
[I-0001] Title
lane/status · maturity · updated age
Primary next action
```

Do not render raw idea bodies in cards by default.

---

## Task 8: Add Greenhouse JavaScript Rendering And Capture

**Files:**

- Modify: `src/devflow/control_room/operating_layer_script.py`
- Modify: `tests/test_operating_layer.py`

- [ ] **Step 1: Add failing JS token tests**

Assert JS contains:

- `setupIdeaGreenhouse`
- `renderIdeaGreenhouse`
- `captureIdeaFromGreenhouse`
- `idea-greenhouse-lanes`

- [ ] **Step 2: Wire setup into `init()`**

In `init()`:

```javascript
setupIdeaGreenhouse();
```

- [ ] **Step 3: Render from snapshot**

In `render()` or `renderFirstViewport()`, call:

```javascript
renderIdeaGreenhouse(snapshot?.idea_greenhouse || null);
```

Do **not** let snapshot refresh clobber the capture textarea while the user is typing. Only render lane/card containers.

- [ ] **Step 4: Implement capture flow**

`captureIdeaFromGreenhouse()` should:

1. Read textarea and optional title.
2. If empty, show inline status: `Write the idea first.`
3. Build command:

```javascript
const command = `devflow idea capture ${shellQuoteLike(text)} --source operating-layer${title ? ` --title ${shellQuoteLike(title)}` : ''} --tag greenhouse`;
```

Use an existing command escaping helper if present. If not, add a small local single-quote escape helper and unit/token tests.

4. POST to `/api/actions/run` with the exact approval payload required by the server:

```javascript
{
  command,
  human_approved: true,
  approval_phrase: 'I approve this exact Dev-Flow command',
  approved_command: command
}
```

5. On success, clear textarea, show `Captured I-000X`, reload snapshot.
6. On failure, show red status and do not clear text.

- [ ] **Step 5: Render cards and next actions**

`renderIdeaGreenhouse(greenhouse)` should render lanes in server-provided order. Each card should include:

- idea id badge;
- title;
- maturity/status badge;
- tag pills up to 3;
- primary action label;
- button only when action command is concrete and browser-approved;
- otherwise a small `<code>` command hint or `Open CLI` text.

V1 button actions:

- capture: real submit;
- park/archive if implemented as approved concrete commands;
- show/copy command for classify/promote/create.

Do not run placeholder classify/promote commands from the browser.

- [ ] **Step 6: Verify JS syntax**

Because JS is embedded in a Python triple-quoted string, avoid raw `\n` escape mistakes. Use `String.fromCharCode(10)` if constructing multi-line strings.

Run:

```bash
PYTHONPATH=src:. .venv/bin/python - <<'PY'
from pathlib import Path
from devflow.control_room.operating_layer_script import APP_JS
Path('/tmp/devflow-operating-layer.js').write_text(APP_JS, encoding='utf-8')
PY
node --check /tmp/devflow-operating-layer.js
```

Expected: `node --check` exits 0.

---

## Task 9: Operating-Layer Tests And Visual QA Tokens

**Files:**

- Modify: `tests/test_operating_layer.py`
- Modify: `src/devflow/control_room/operating_layer_visual_qa.py`

- [ ] **Step 1: Update server smoke/asset tests**

Assert served HTML/CSS/JS contain Greenhouse tokens:

- `Idea Greenhouse`
- `idea-capture-form`
- `idea-greenhouse-lanes`
- `.idea-card`
- `renderIdeaGreenhouse`

- [ ] **Step 2: Update static visual QA contract**

Add checks for:

```text
idea-greenhouse-section appears after brainstorm-section and before orchestrator-section
idea-capture-form exists
idea-greenhouse-lanes exists
```

- [ ] **Step 3: Add no-horizontal-overflow expectation if browser tests exist**

If `tests/test_operator_ui_browser.py` has layout metrics, add a check that the Greenhouse lanes wrap at mobile width.

- [ ] **Step 4: Verify targeted tests**

Run:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_operating_layer.py -q
```

---

## Task 10: Documentation Alignment

**Files:**

- Modify: `README.md`
- Modify: `docs/control-room-mvp.md`
- Modify: `docs/mvp-contract.md`
- Possibly modify: `docs/operator-centered-mission.md`

- [ ] **Step 1: Document Greenhouse as current local intake UI**

Add language that Idea Foundry is now visible in the operating layer as Idea Greenhouse V1.

Required wording points:

- capture remains local evidence under `.devflow/ideas/`;
- parking is non-destructive and preserves raw evidence;
- browser capture/parking uses approval-gated Dev-Flow commands;
- promotion still requires explicit human decision;
- V1 does not run models or auto-create tasks.

- [ ] **Step 2: Stale-context search**

Run:

```bash
rg -n "Idea Foundry.*future|Greenhouse.*future only|idea greenhouse.*not implemented|no Idea Greenhouse|devflow idea park.*do not exist" README.md docs src tests
```

Expected: no stale authority claims.

---

## Task 11: End-To-End User Flow Verification

**Files:** no new production files unless a bug is found.

- [ ] **Step 1: Run focused tests**

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest \
  tests/test_idea_foundry.py \
  tests/test_supervisor_operating_surface.py \
  tests/test_operating_layer.py \
  -q
```

Expected: pass.

- [ ] **Step 2: Serve the UI**

```bash
env PYTHONPATH=src:. .venv/bin/python -m devflow.cli operating-layer serve --port 8766
```

Open cache-busted URL:

```text
http://127.0.0.1:8766/?cb=idea-greenhouse-v1
```

- [ ] **Step 3: Manual walkthrough**

Follow the actual operator path:

```text
Open operating layer
  -> see Idea Greenhouse panel
  -> type messy idea with no tags/title
  -> Capture idea
  -> idea appears in Raw lane
  -> card shows primary next action
  -> park/archive action is visible where supported
  -> classify/promote commands are visible but not unsafe one-click placeholders
```

- [ ] **Step 4: Check evidence**

Inspect:

```text
.devflow/ideas/I-0001/idea.json
.devflow/ideas/I-0001/raw.md
.devflow/ideas/I-0001/events.jsonl
```

Expected:

- raw text preserved;
- source is `operating-layer`;
- `greenhouse` tag exists if added by UI;
- event log records creation;
- no task/goal/worker/verification artifacts created by capture.

- [ ] **Step 5: Visual check**

Confirm:

- lane colors are distinct;
- no horizontal overflow at desktop width;
- mobile/narrow layout stacks lanes;
- capture input is not erased by snapshot refresh while typing;
- no panel ends in a dead-end state.

---

## Verification Command Set

Use the repo wrapper if available. If not, use the existing venv commands documented in this repo's plans.

Minimum targeted verification after implementation:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_idea_foundry.py -q
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_supervisor_operating_surface.py -q
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_operating_layer.py -q
PYTHONPATH=src:. .venv/bin/python - <<'PY'
from pathlib import Path
from devflow.control_room.operating_layer_script import APP_JS
Path('/tmp/devflow-operating-layer.js').write_text(APP_JS, encoding='utf-8')
PY
node --check /tmp/devflow-operating-layer.js
```

Documentation-only/stale-context verification:

```bash
rg -n "Idea Foundry.*future|Greenhouse.*future only|idea greenhouse.*not implemented|no Idea Greenhouse|devflow idea park.*do not exist" README.md docs src tests
```

Final broader check if implementation touches all layers:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest \
  tests/test_idea_foundry.py \
  tests/test_idea_execution_bridge.py \
  tests/test_supervisor_operating_surface.py \
  tests/test_operating_layer.py \
  tests/test_operator_ui_browser.py \
  -q
```

`tests/test_operator_ui_browser.py` may require Playwright/Chromium; if unavailable, record that as an environment limitation and still perform static visual QA plus browser/manual screenshot if possible.

---

## Implementation Notes For Subagents

- This is a **visual control-room feature**, not an AI triage feature yet.
- Preserve existing Idea Foundry files and semantics.
- Prefer derived projections over state migrations.
- Do not invent a second source of truth.
- Do not let the UI run placeholder commands.
- Do not silently auto-promote or auto-create tasks.
- Every card needs either a concrete safe action or a clear command hint.
- The operator's cognitive-load reduction is the acceptance criterion.

---

## Definition Of Done

This plan is complete when:

- `devflow idea park` works and preserves evidence.
- Operating-layer snapshot includes `idea_greenhouse` with lane counts and cards.
- Browser UI includes a compact Idea Greenhouse panel.
- The operator can capture a raw idea from the browser without choosing a project/tag/priority.
- Captured ideas appear visually in the Raw lane.
- Parked ideas appear visually in the Parked lane and are not treated as active work.
- Each visible idea card has a next action label.
- No browser action runs placeholder classify/promote commands.
- Tests listed above pass or any unavailable browser-only test is explicitly documented.
- Docs describe Greenhouse V1 as current behavior, not future intent.

---

## Suggested V1.5 / V2 Follow-Ups

After V1 is real and visually verified:

1. **Triage command:** `devflow idea triage --dry-run` creates deterministic or model-backed review evidence.
2. **Digest:** daily/session digest with top candidates, parked count, stale raw ideas, and one recommended next action.
3. **Scoring fields:** energy, leverage, feasibility, strategic fit, effort.
4. **Duplicate grouping:** local text similarity first; model clustering later.
5. **Telegram capture:** route approved Telegram messages into `devflow idea capture`.
6. **Promotion wizard:** browser forms for real classify/promote rationale instead of command hints.
7. **WIP limit warnings:** alert when candidate/active/promoted queues exceed limits.
8. **Model scorecard feedback:** track which ideas/tasks produce successful shipped work.
