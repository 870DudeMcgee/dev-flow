# Idea-to-Product Pipeline UI Implementation Plan

> **For Hermes:** Use `subagent-driven-development` skill to implement task-by-task. Work one slice at a time with browser RED tests first.

**Goal:** Reshape the operating-layer home UI into a single top-to-bottom visual representation of the DevFlow pipeline: Idea → Brainstorm → Spec → Plan → Implementation Task → Product/Review.

**Architecture:** Do not create a second workflow. Use existing `.devflow/ideas/`, `start_brainstorm_from_idea()`, brainstorm pipeline artifacts, task creation bridge, task snapshot, review queue, and evidence stream as the source of truth. The browser becomes a vertical operator journey with one canonical primary action at each stage; advanced/CLI-style actions remain in detail overlays.

**Tech Stack:** Python stdlib HTTP server, Pydantic snapshot models, bundled Python string assets (`operating_layer_html.py`, `operating_layer_script.py`, `operating_layer_styles.py`), Playwright browser tests, pytest.

---

## Current Diagnosis

The backend already has the elegant pipeline pieces:

- `src/devflow/control_room/brainstorm.py::start_brainstorm_from_idea()`
  - creates/reuses one brainstorm session per idea;
  - seeds transcript from idea raw text;
  - writes `source_idea_id` lineage;
  - updates idea metadata with `latest_brainstorm_session_id` and session paths.
- `src/devflow/control_room/brainstorm_pipeline.py`
  - computes `stages`, `next_step_label`, `operator_summary`, `task_action`, `implementation_context`, lineage, and artifact paths.
- `src/devflow/control_room/operating_layer_server.py::_handle_brainstorm_transcript()`
  - already returns `pipeline` from `load_brainstorm_pipeline_detail()`.
- `src/devflow/control_room/brainstorm_task_bridge.py::create_task_from_brainstorm()`
  - creates a task and writes `implementation-context.md` atomically.
- Existing tests already prove backend lineage:
  - `tests/test_brainstorm_workbench.py::test_start_brainstorm_from_idea_creates_session_and_seeds_transcript`
  - `tests/test_brainstorm_workbench.py::test_idea_started_brainstorm_lineage_flows_to_spec_plan_and_implementation`
  - `tests/test_brainstorm_task_bridge.py`

The confusing part is the browser shell:

1. Idea Greenhouse is visually below Brainstorm, even though idea is the first pipeline stage.
2. The good idea→brainstorm bridge exists, but its button is hidden in the idea detail overlay.
3. Frontend pipeline state is duplicated as JS booleans (`hasTranscript`, `hasSpec`, `hasPlan`, `hasImplementation`) instead of rendering backend `pipeline.stages`.
4. The Pipeline panel is a side card, not the primary top-to-bottom mental model.
5. The final transition into implementation/product is not visually represented as a continuation of the same journey.

---

## Design Target

Make the home page read vertically like the product pipeline:

```text
┌──────────────────────────────────────────────┐
│  1. IDEA                                    │
│  Capture box + selected/current idea card   │
│  [Continue brainstorm]                      │
├──────────────────────────────────────────────┤
│  2. BRAINSTORM                              │
│  Conversation seeded from selected idea     │
│  [Generate spec]                            │
├──────────────────────────────────────────────┤
│  3. SPEC                                    │
│  Status, artifact path, concise preview     │
│  [Generate plan]                            │
├──────────────────────────────────────────────┤
│  4. PLAN                                    │
│  Status, artifact path, concise preview     │
│  [Create implementation task]               │
├──────────────────────────────────────────────┤
│  5. IMPLEMENTATION TASK                     │
│  Task launchpad / worker packet / verify    │
│  [Start / verify / review]                  │
├──────────────────────────────────────────────┤
│  6. PRODUCT / REVIEW                        │
│  Review queue + evidence stream             │
└──────────────────────────────────────────────┘
```

The right mental model: **the UI is the pipeline, not panels beside a pipeline.**

---

## Non-Negotiable UX Principles

- **Idea at the top.** Capture/select idea is the entry point.
- **Top-to-bottom flow.** No left/right cognitive jump for the canonical path.
- **One primary action.** At any moment the pipeline has one obvious next lever.
- **Backend state is source of truth.** Render `pipeline.stages` and `pipeline.next_step_label`; do not infer with parallel JS booleans.
- **Lineage over localStorage.** Use idea metadata and brainstorm session artifacts whenever available; localStorage is only a last selected-session convenience.
- **Advanced actions are secondary.** CLI previews, raw metadata, park/archive/classify forms belong in overlays/drawers, not the main path.
- **No new backend workflow unless a test proves a missing contract.** Existing endpoints cover the intended path.

---

## Proposed Page Structure

### Before

```text
center column: Brainstorm → Idea Greenhouse → Next Task
right column: Pipeline → Health → History
bottom: worker/review/evidence surfaces
```

### After

```text
main vertical pipeline:
  1. Idea Intake
  2. Brainstorm
  3. Spec
  4. Plan
  5. Implementation Task
  6. Product / Review Evidence

supporting side/drawer surfaces:
  - idea history/lane drawer
  - brainstorm history drawer
  - focus overlay for details
  - advanced command surfaces
```

Implementation can still use CSS grid internally, but the DOM/order and first viewport must communicate top-to-bottom progression.

---

## Data Contract

### Existing data to use directly

From `/api/snapshot`:

- `snapshot.idea_greenhouse`
- `snapshot.tasks`
- `snapshot.first_viewport`
- `snapshot.evidence`
- `snapshot.review_loop`

From `/api/brainstorm/transcript?session_id=...`:

- `messages`
- `spec`
- `plan`
- `implementation`
- `pipeline`
  - `stages[]`
  - `next_step_label`
  - `operator_summary`
  - `task_action`
  - `implementation_context`
  - `lineage`

### Frontend state target

Replace current duplicate state shape:

```js
let pipelineState = { hasTranscript: false, hasSpec: false, hasPlan: false, hasImplementation: false };
```

With:

```js
let activePipeline = null; // exact backend pipeline_detail/pipeline payload
let activeIdeaId = null;   // derived from activePipeline.lineage.source_idea_id or selected idea
```

Keep localStorage only for:

- `devflow-brainstorm-session` as last opened session fallback;
- per-session Definition of Done draft.

---

## Slice 1 — Vertical Skeleton: Idea At Top, Pipeline As Page Spine

**Goal:** Reorder the visible home UI so the first scroll reads Idea → Brainstorm → Pipeline artifacts → Task → Product/Review.

**Files:**

- `src/devflow/control_room/operating_layer_html.py`
- `src/devflow/control_room/operating_layer_styles.py`
- `src/devflow/control_room/operating_layer_script.py`
- `tests/test_operator_ui_browser.py`
- `tests/test_operating_layer.py`

**RED browser test:**

```python
def test_home_reads_top_to_bottom_as_idea_to_product_pipeline(browser_page: tuple[Page, list[str]]) -> None:
    page, _console_errors = browser_page
    metrics = page.evaluate(
        """() => {
          const order = [
            ['idea', '#idea-greenhouse-section'],
            ['brainstorm', '#brainstorm-section'],
            ['pipeline', '#pipeline-spine'],
            ['task', '#orchestrator-section'],
            ['product', '#product-review-section'],
          ];
          return order.map(([name, selector]) => {
            const element = document.querySelector(selector);
            const rect = element?.getBoundingClientRect();
            return [name, Boolean(rect), rect ? Math.round(rect.top) : null];
          });
        }"""
    )
    assert [name for name, exists, _top in metrics if exists] == [
        'idea', 'brainstorm', 'pipeline', 'task', 'product'
    ]
    tops = [top for _name, exists, top in metrics if exists]
    assert tops == sorted(tops)
    assert tops[0] < 160
```

**Implementation notes:**

- Move Idea Greenhouse markup above Brainstorm in the primary DOM order.
- Rename/introduce a clear pipeline container id: `#pipeline-spine`.
- Keep existing `#idea-greenhouse-section`, `#brainstorm-section`, `#orchestrator-section` ids for compatibility.
- Add `#product-review-section` wrapping review queue + evidence stream or a compact product/review lane.
- Update mobile CSS order so Idea remains first. Current tests assert Brainstorm first on mobile; update those tests to match the new product decision.
- Do not remove detail overlay or existing launchpad behavior.

**Verification:**

```bash
env PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_operator_ui_browser.py::test_home_reads_top_to_bottom_as_idea_to_product_pipeline -q
node --check /tmp/extracted-operating-layer.js  # or existing extraction helper if present
env PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_operating_layer.py -q
```

---

## Slice 2 — Promote Existing Idea→Brainstorm Bridge To The Main Card Action

**Goal:** Every visible idea card has a primary `Continue brainstorm` action that calls existing `/api/brainstorm/start-from-idea` and switches the pipeline to that idea-linked session.

**Files:**

- `src/devflow/control_room/operating_layer_script.py`
- `src/devflow/control_room/operating_layer_styles.py`
- `tests/test_operator_ui_browser.py`
- `tests/test_operating_layer.py`

**RED browser test:**

```python
def test_idea_card_continue_brainstorm_seeds_pipeline_session(
    browser_page: tuple[Page, list[str]],
    scratch_state: ScratchState,
) -> None:
    page, _console_errors = browser_page

    page.locator('#idea-capture-title').fill('Pipeline UI idea')
    page.locator('#idea-capture-text').fill('Make the UI flow from idea to product.')
    page.locator('#idea-capture-submit').click()
    expect(page.locator('#idea-greenhouse-lanes')).to_contain_text('Pipeline UI idea', timeout=15_000)

    card = page.locator('.idea-card', has_text='Pipeline UI idea').first
    expect(card.locator('[data-idea-brainstorm]')).to_be_visible()
    card.locator('[data-idea-brainstorm]').click()

    expect(page.locator('#brainstorm-transcript')).to_contain_text('Make the UI flow from idea to product.', timeout=15_000)
    expect(page.locator('#pipeline-spine')).to_contain_text('Idea')
    expect(page.locator('#pipeline-spine')).to_contain_text('Brainstorm')
    session_id = page.evaluate("() => localStorage.getItem('devflow-brainstorm-session')")
    assert session_id and '-source-I-' in session_id
```

**Implementation notes:**

- Add `data-idea-brainstorm` button to `renderIdeaCard()`; do not require opening focus overlay.
- Reuse the existing document click handler for `[data-idea-brainstorm]`.
- Pass `profile_id` only if needed later; current backend ignores it.
- After successful start/reuse:
  - set `brainstormSessionId`;
  - update localStorage fallback;
  - call `loadBrainstormTranscript(data.session_id)`;
  - call `refreshPipelineState()`;
  - focus Brainstorm input;
  - show inline success on the card or pipeline spine.
- Keep the overlay button too, but demote its copy to “Open linked brainstorm”.

**Verification:**

```bash
env PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_operator_ui_browser.py::test_idea_card_continue_brainstorm_seeds_pipeline_session -q
env PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_brainstorm_workbench.py::test_start_brainstorm_from_idea_creates_session_and_seeds_transcript -q
```

---

## Slice 3 — Render Backend Pipeline Directly; Delete JS Boolean State Machine

**Goal:** The visible pipeline stages come from backend `pipeline.stages`, including implementation, artifact paths, status, next step, and operator summary.

**Files:**

- `src/devflow/control_room/operating_layer_script.py`
- `src/devflow/control_room/operating_layer_styles.py`
- `tests/test_operator_ui_browser.py`
- `tests/test_operating_layer.py`

**RED asset contract test:**

```python
def test_operating_layer_js_uses_backend_pipeline_contract_not_boolean_pipeline_state() -> None:
    assert 'activePipeline' in APP_JS
    assert 'pipeline.stages' in APP_JS or '.stages' in APP_JS
    assert 'next_step_label' in APP_JS
    assert 'operator_summary' in APP_JS
    assert 'let pipelineState = { hasTranscript' not in APP_JS
```

**RED browser test:**

```python
def test_pipeline_spine_renders_backend_stages_and_single_next_action(browser_page: tuple[Page, list[str]]) -> None:
    page, _console_errors = browser_page
    page.locator('#idea-capture-title').fill('Backend pipeline render')
    page.locator('#idea-capture-text').fill('Use pipeline.stages directly.')
    page.locator('#idea-capture-submit').click()
    page.locator('.idea-card', has_text='Backend pipeline render').first.locator('[data-idea-brainstorm]').click()

    spine = page.locator('#pipeline-spine')
    expect(spine).to_contain_text('Idea')
    expect(spine).to_contain_text('Brainstorm')
    expect(spine).to_contain_text('Spec')
    expect(spine).to_contain_text('Plan')
    expect(spine).to_contain_text('Implementation')
    expect(spine.locator('[data-pipeline-primary-action]')).to_contain_text(re.compile('Spec|spec'))
```

**Implementation notes:**

- `refreshPipelineState()` should fetch transcript and set `activePipeline = data.pipeline || null`.
- `loadBrainstormTranscript()` should also set `activePipeline = data.pipeline || null`.
- `renderPipeline()` becomes `renderPipelineSpine(activePipeline)`.
- Render stages from `activePipeline.stages`, not hardcoded `brainstorm/spec/plan` array.
- Add an explicit “Idea” visual row before backend stages when `activePipeline.lineage.source_idea_id` exists.
- Map statuses:
  - `complete`, `accepted`, `passed` → complete/check
  - `draft` → complete-but-needs-review or draft badge
  - `pending` → pending
  - current next stage → active
- Render one primary button from `activePipeline.next_step_label` and current missing stage.
- Keep quality gate buttons secondary/advanced; do not put them beside every stage in the main spine.

**Ponytail deletion:** Remove or stop using the frontend `pipelineState` boolean state machine.

**Verification:**

```bash
env PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_operating_layer.py::test_operating_layer_js_uses_backend_pipeline_contract_not_boolean_pipeline_state -q
env PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_operator_ui_browser.py::test_pipeline_spine_renders_backend_stages_and_single_next_action -q
```

---

## Slice 4 — Single Primary Pipeline Action: Spec → Plan → Task

**Goal:** The pipeline spine exposes exactly one canonical next action at a time and refreshes itself after each click.

**Files:**

- `src/devflow/control_room/operating_layer_script.py`
- `tests/test_operator_ui_browser.py`

**RED browser test:**

```python
def test_pipeline_primary_action_advances_spec_plan_task_creation(
    browser_page: tuple[Page, list[str]],
    scratch_state: ScratchState,
) -> None:
    page, _console_errors = browser_page
    page.locator('#idea-capture-title').fill('Ship vertical pipeline')
    page.locator('#idea-capture-text').fill('Idea should become spec, plan, task, product.')
    page.locator('#idea-capture-submit').click()
    page.locator('.idea-card', has_text='Ship vertical pipeline').first.locator('[data-idea-brainstorm]').click()

    primary = page.locator('#pipeline-spine [data-pipeline-primary-action]')
    expect(primary).to_contain_text(re.compile('Spec|spec'))
    primary.click()
    expect(page.locator('#pipeline-spine')).to_contain_text('spec.md', timeout=20_000)

    primary = page.locator('#pipeline-spine [data-pipeline-primary-action]')
    expect(primary).to_contain_text(re.compile('Plan|plan'))
    primary.click()
    expect(page.locator('#pipeline-spine')).to_contain_text('plan.md', timeout=20_000)

    page.locator('#brainstorm-definition-of-done').fill('Task exists with implementation context.')
    primary = page.locator('#pipeline-spine [data-pipeline-primary-action]')
    expect(primary).to_contain_text(re.compile('Task|task'))
    primary.click()
    expect(page.locator('#orchestrator-goal-title')).to_contain_text('task-', timeout=20_000)
    assert list((scratch_state.root / '.devflow' / 'workspaces').glob('task-*/implementation-context.md'))
```

**Implementation notes:**

- The primary action should call existing `escalateBrainstormStage(stage, useModel)`.
- Derive action stage from backend pipeline, not hardcoded active CSS class:
  - no spec → `stage='spec'`
  - no plan → `stage='plan'`
  - no implementation → `stage='implementation'`
  - task exists → scroll/select task in launchpad
- On spec/plan success:
  - set `activePipeline = payload.pipeline_detail || activePipeline`;
  - render pipeline spine immediately;
  - append transcript status only as secondary evidence, not the only feedback.
- On implementation success:
  - call existing `/api/brainstorm/create-task` atomic bridge;
  - refresh snapshot;
  - select created task in launchpad;
  - mark implementation/task row complete.
- Add local pending/working status on the button: `Generating spec...`, `Generating plan...`, `Creating task...`.
- If the backend returns an error, show it inline in the pipeline spine and do not silently ignore.

**Verification:**

```bash
env PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_operator_ui_browser.py::test_pipeline_primary_action_advances_spec_plan_task_creation -q
env PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_brainstorm_task_bridge.py tests/test_brainstorm_workbench.py -q
```

---

## Slice 5 — Product/Review Stage: Finish The Visual Story

**Goal:** After task creation, the bottom of the pipeline shows product progress: selected task, worker lever, verification, review queue, and evidence stream as the final stage of the same journey.

**Files:**

- `src/devflow/control_room/operating_layer_html.py`
- `src/devflow/control_room/operating_layer_script.py`
- `src/devflow/control_room/operating_layer_styles.py`
- `tests/test_operator_ui_browser.py`

**RED browser test:**

```python
def test_product_stage_contains_task_launchpad_review_and_evidence(browser_page: tuple[Page, list[str]]) -> None:
    page, _console_errors = browser_page
    product = page.locator('#product-review-section')
    expect(product).to_be_visible()
    expect(product).to_contain_text('Product / Review')
    expect(product).to_contain_text('Worker lanes')
    expect(product).to_contain_text('Review queue')
    expect(product).to_contain_text('Evidence stream')
```

**Implementation notes:**

- Wrap or visually group existing worker lanes, review queue, and evidence stream under `#product-review-section`.
- Keep existing IDs used by tests and click handlers.
- Add a short stage explainer: “Product means task evidence, verification, review, and promotion.”
- After task creation from pipeline, scroll/focus to the Implementation Task stage, not random history or the old side panel.

**Verification:**

```bash
env PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_operator_ui_browser.py::test_product_stage_contains_task_launchpad_review_and_evidence -q
```

---

## Slice 6 — Session Recovery From Idea Lineage, Not Anonymous Browser Sessions

**Goal:** On load, prefer the most recent idea-linked brainstorm session over creating a confusing anonymous `browser-*` pipeline.

**Files:**

- `src/devflow/control_room/operating_layer_script.py`
- `tests/test_operator_ui_browser.py`
- `tests/test_operating_layer.py`

**RED asset contract test:**

```python
def test_operating_layer_js_recovers_brainstorm_session_from_idea_lineage() -> None:
    assert 'latest_brainstorm_session_id' in APP_JS
    assert 'restoreBrainstormSessionFromIdeaLineage' in APP_JS
```

**Implementation notes:**

- Add `restoreBrainstormSessionFromIdeaLineage(greenhouse)`:
  - if localStorage session exists and transcript exists, keep it;
  - otherwise scan visible/recent ideas for `metadata.lineage.latest_brainstorm_session_id` or `metadata.latest_brainstorm_session_id`;
  - set `brainstormSessionId` to that session and load transcript;
  - otherwise create anonymous `browser-*` only when the user actually starts a freeform brainstorm.
- Update `newBrainstormSession()` copy so it is clearly “New freeform brainstorm” and not the normal idea pipeline.

**Verification:**

```bash
env PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_operating_layer.py::test_operating_layer_js_recovers_brainstorm_session_from_idea_lineage -q
env PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_operator_ui_browser.py -q
```

---

## Slice 7 — Polish And Remove Confusing Duplicate Actions

**Goal:** Main UI presents one canonical path; detail overlays preserve advanced controls without competing with the pipeline.

**Files:**

- `src/devflow/control_room/operating_layer_script.py`
- `src/devflow/control_room/operating_layer_styles.py`
- `tests/test_operating_layer.py`
- `tests/test_operator_ui_browser.py`

**Changes:**

- In main idea cards:
  - primary: `Continue brainstorm`
  - secondary tiny text/status: lane/maturity/age
  - move classify/promote/park/archive commands to focus overlay.
- In pipeline spine:
  - primary: one next action only
  - secondary: artifact links/status badges
  - QC Gate hidden under “Advanced checks” or a collapsed secondary area.
- In Brainstorm:
  - keep chat, but show “Seeded from I-xxxx” when lineage exists.
- In history:
  - demote history to side drawer/collapsible region, not the main flow.

**RED tests:**

```python
def test_main_pipeline_has_one_primary_action_per_stage(browser_page: tuple[Page, list[str]]) -> None:
    page, _console_errors = browser_page
    assert page.locator('[data-pipeline-primary-action]').count() <= 1
    assert page.locator('.idea-card [data-idea-brainstorm]').count() >= 1
```

**Verification:**

```bash
env PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_operator_ui_browser.py tests/test_operating_layer.py -q
git diff --check
```

---

## Final Verification Matrix

Run after all slices:

```bash
env PYTHONPATH=src:. .venv/bin/python -m pytest \
  tests/test_operator_ui_browser.py \
  tests/test_operating_layer.py \
  tests/test_brainstorm_workbench.py \
  tests/test_brainstorm_task_bridge.py \
  tests/test_supervisor_operating_surface.py -q

git diff --check
```

Manual smoke:

```bash
env PYTHONPATH=src:. .venv/bin/python -m devflow.cli operating-layer serve --host 127.0.0.1 --port 8765
open http://127.0.0.1:8765
```

Expected manual result:

1. Idea section is first.
2. Capture/select idea.
3. Click `Continue brainstorm`.
4. Brainstorm transcript is seeded from the idea.
5. Pipeline spine shows Idea → Brainstorm → Spec → Plan → Implementation → Product/Review.
6. One primary button advances the next missing stage.
7. Task creation focuses the launchpad and writes `implementation-context.md`.
8. Review/evidence/product stage remains visible as the bottom of the same flow.

---

## Explicit Non-Scope

- No new model/provider calls beyond existing brainstorm escalation behavior.
- No new database or state store.
- No new backend workflow unless RED tests prove existing contracts cannot support the UI.
- No automatic task execution after task creation.
- No git promotion/push from browser.
- No live Hermes/Qwen launch from browser; keep existing serial packet safety boundary.

---

## Implementation Order Summary

1. Vertical skeleton: Idea first, product last.
2. Promote card-level `Continue brainstorm` using existing endpoint.
3. Render backend `pipeline.stages`; remove duplicate JS booleans.
4. Single primary action advances Spec → Plan → Task.
5. Product/Review stage wraps task/review/evidence surfaces.
6. Recover sessions from idea lineage before anonymous browser sessions.
7. Polish and demote duplicate/advanced actions.

This is the Ponytail path: **show the pipeline that already exists, delete duplicate frontend state, and make the shortest real path impossible to miss.**
