# Milestone 18 Operating-Layer Beta Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the local browser operating layer reliable enough to use as Dev-Flow's daily review and approval surface.

**Architecture:** Preserve filesystem artifacts as source of truth and keep the browser as a guarded projection over existing Dev-Flow state. Add one derived review-loop summary to the operating-layer snapshot, render it in the browser near the Action Rail and review page, keep result-retention client-side, and remove active-doc wording that still treats completed result-retention hooks as future work.

**Tech Stack:** Python 3, Pydantic, Typer, pytest, vanilla JavaScript bundled through `operating_layer_script.py`, existing Dev-Flow task/verification/promotion artifacts.

---

## File Structure

- Modify `src/devflow/control_room/operating_layer.py`: add a derived `OperatingLayerReviewLoop` snapshot model and helper built from existing task, gate, promotion, and action evidence.
- Modify `src/devflow/control_room/operating_layer_script.py`: render the review-loop summary in the browser and keep existing approved-action result retention intact.
- Modify `src/devflow/control_room/operating_layer_styles.py`: add compact review-loop UI styles without changing the page structure or broad visual system.
- Modify `tests/test_operating_layer.py`: lock the review-loop snapshot contract, UI asset hooks, approved-action result retention hooks, and mutation boundary.
- Modify `docs/architecture/local-operating-layer-ui.md`: mark result retention as implemented and make the next safe slice review-loop beta hardening.
- Modify `docs/agent-handoff.md`: remove stale wording that says result retention is the next pending UI action.
- Modify `docs/control-room-mvp.md`: note Milestone 18 operating-layer beta as the current UI hardening direction after Milestone 17.
- Modify `docs/superpowers/specs/2026-06-14-milestone-18-operating-layer-beta-design.md`: keep the design aligned with final implementation evidence if scope changes during execution.

## Task 1: Lock Current Result-Retention Baseline

**Files:**
- Test: `tests/test_operating_layer.py`

- [ ] **Step 1: Run focused hook test**

Run:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_operating_layer.py::test_operating_layer_approved_action_result_retention_hooks_are_present -q
```

Expected: pass. Current main already has `lastApprovedActionResult`, `rememberApprovedActionResult`, `refreshSnapshotAfterApprovedAction`, `preservedActionResultForSelectedTask`, and `Last approved command` in `APP_JS`.

- [ ] **Step 2: Run server approval behavior tests**

Run:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest \
  tests/test_operating_layer.py::test_operating_layer_server_runs_approved_task_verification \
  tests/test_operating_layer.py::test_operating_layer_server_runs_approved_task_promotion \
  tests/test_operating_layer.py::test_operating_layer_server_blocks_approval_required_actions \
  -q
```

Expected: pass. Approved verification and promotion execute only with exact approval evidence; broad worker-runtime actions stay blocked.

- [ ] **Step 3: Record baseline if tests fail**

If either command fails, stop and repair the existing result-retention or approval-gate behavior before continuing. Do not add review-loop UI on top of a broken approval baseline.

## Task 2: Add Review-Loop Snapshot Summary

**Files:**
- Modify: `src/devflow/control_room/operating_layer.py`
- Modify: `tests/test_operating_layer.py`

- [ ] **Step 1: Write failing snapshot contract test**

Append this test near the existing snapshot tests in `tests/test_operating_layer.py`:

```python
def test_operating_layer_snapshot_includes_browser_review_loop_summary(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    assert runner.invoke(app, ["task", "create", "browser review task"]).exit_code == 0
    run = runner.invoke(app, ["task", "run", "task-0001", "--shell", "echo done > result.txt"])
    assert run.exit_code == 0, run.output

    snapshot = build_operating_layer_snapshot(tmp_path)
    payload = snapshot.model_dump(mode="json")

    review_loop = payload["review_loop"]
    assert review_loop["status"] == "needs_verification"
    assert review_loop["headline"] == "1 task needs verification"
    assert review_loop["next_safe_action"] == 'devflow task verify task-0001 --shell "<command>"'
    assert review_loop["browser_allowed_mutations"] == ["task verification", "task promotion"]
    assert "worker execution" in review_loop["browser_blocked_mutations"]
    assert "task creation" in review_loop["browser_blocked_mutations"]
    assert review_loop["needs_verification_count"] == 1
    assert review_loop["ready_to_promote_count"] == 0
    assert review_loop["blocked_decision_count"] == 0
    assert review_loop["last_result_retention"] == "browser-session"
    assert review_loop["evidence_summary"] == "1 task has worker output; 0 tasks have passed verification; 0 tasks are ready for promotion."

    verify = runner.invoke(app, ["task", "verify", "task-0001", "--shell", "test -f result.txt"])
    assert verify.exit_code == 0, verify.output

    promoted_snapshot = build_operating_layer_snapshot(tmp_path).model_dump(mode="json")
    review_loop = promoted_snapshot["review_loop"]
    assert review_loop["status"] == "ready_to_promote"
    assert review_loop["headline"] == "1 task ready for browser approval"
    assert review_loop["next_safe_action"] == "devflow task promote-preview task-0001"
    assert review_loop["needs_verification_count"] == 0
    assert review_loop["ready_to_promote_count"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_operating_layer.py::test_operating_layer_snapshot_includes_browser_review_loop_summary -q
```

Expected: fail with `KeyError: 'review_loop'`.

- [ ] **Step 3: Add the Pydantic model**

In `src/devflow/control_room/operating_layer.py`, add this class after `OperatingLayerMissionFeedItem`:

```python
class OperatingLayerReviewLoop(BaseModel):
    status: str
    headline: str
    next_safe_action: str
    browser_allowed_mutations: list[str] = Field(default_factory=list)
    browser_blocked_mutations: list[str] = Field(default_factory=list)
    needs_verification_count: int = 0
    ready_to_promote_count: int = 0
    blocked_decision_count: int = 0
    last_result_retention: str = "browser-session"
    evidence_summary: str = ""
```

Add this field to `OperatingLayerSnapshot` after `mission_feed`:

```python
    review_loop: OperatingLayerReviewLoop
```

- [ ] **Step 4: Wire the helper into snapshot construction**

In `build_operating_layer_snapshot()`, add `review_loop` to the returned `OperatingLayerSnapshot` after `mission_feed`:

```python
        review_loop=_review_loop_summary(
            tasks,
            inbox=inbox,
            gate_receipts=gate_receipts,
            promotion_desk=promotion_desk,
            next_action=dashboard.next_action,
        ),
```

Add this helper near `_mission_feed()`:

```python
def _review_loop_summary(
    tasks: list[OperatingLayerTask],
    *,
    inbox: list[OperatingLayerInboxItem],
    gate_receipts: list[OperatingLayerGateReceipt],
    promotion_desk: list[OperatingLayerPromotionCandidate],
    next_action: DashboardNextAction,
) -> OperatingLayerReviewLoop:
    needs_verification = [task for task in tasks if task.lane == "needs_verification"]
    ready_to_promote = [task for task in tasks if task.lane == "ready_to_promote"]
    blocked_decisions = [
        item for item in inbox if item.kind in {"blocked_task", "failed_task", "freshness_human_decision", "question"}
    ]
    verified_count = sum(1 for gate in gate_receipts if gate.verification)
    worker_output_count = sum(1 for gate in gate_receipts if gate.worker_evidence)

    if blocked_decisions:
        status = "needs_human_decision"
        headline = f"{len(blocked_decisions)} decision item{'s' if len(blocked_decisions) != 1 else ''} need attention"
    elif ready_to_promote:
        status = "ready_to_promote"
        headline = f"{len(ready_to_promote)} task{'s' if len(ready_to_promote) != 1 else ''} ready for browser approval"
    elif needs_verification:
        status = "needs_verification"
        headline = f"{len(needs_verification)} task{'s' if len(needs_verification) != 1 else ''} need{'s' if len(needs_verification) == 1 else ''} verification"
    else:
        status = "watching"
        headline = "No browser approval items are waiting"

    promotion_command = promotion_desk[0].command if promotion_desk else None
    command = (
        next_action.command
        or promotion_command
        or (ready_to_promote[0].next_action.command if ready_to_promote else None)
        or (needs_verification[0].next_action.command if needs_verification else None)
        or "devflow dashboard"
    )

    return OperatingLayerReviewLoop(
        status=status,
        headline=headline,
        next_safe_action=command,
        browser_allowed_mutations=["task verification", "task promotion"],
        browser_blocked_mutations=[
            "task creation",
            "worker execution",
            "patch application",
            "git publication",
            "provider-backed model calls",
            "autonomous routing execution",
        ],
        needs_verification_count=len(needs_verification),
        ready_to_promote_count=len(ready_to_promote),
        blocked_decision_count=len(blocked_decisions),
        last_result_retention="browser-session",
        evidence_summary=(
            f"{worker_output_count} task{'s' if worker_output_count != 1 else ''} "
            f"has{'ve' if worker_output_count != 1 else ''} worker output; "
            f"{verified_count} task{'s' if verified_count != 1 else ''} "
            f"has{'ve' if verified_count != 1 else ''} passed verification; "
            f"{len(ready_to_promote)} task{'s' if len(ready_to_promote) != 1 else ''} "
            f"{'are' if len(ready_to_promote) != 1 else 'is'} ready for promotion."
        ),
    )
```

- [ ] **Step 5: Run focused snapshot test**

Run:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_operating_layer.py::test_operating_layer_snapshot_includes_browser_review_loop_summary -q
```

Expected: pass.

## Task 3: Render Review-Loop Summary In The Browser

**Files:**
- Modify: `src/devflow/control_room/operating_layer_script.py`
- Modify: `src/devflow/control_room/operating_layer_styles.py`
- Modify: `tests/test_operating_layer.py`

- [ ] **Step 1: Add failing asset hook assertions**

In `tests/test_operating_layer.py`, add these assertions to `test_operating_layer_static_server_serves_split_assets` after the existing Action Rail assertions:

```python
        assert "renderReviewLoopSummary" in js
        assert "review-loop-card" in js
        assert "Browser approvals" in js
        assert "snapshot.review_loop" in js
```

Add these assertions after the CSS response is read in the same test:

```python
        assert ".review-loop-card" in css
        assert ".review-loop-metrics" in css
```

If that test does not currently hold CSS and JS in separate variables, keep the existing request pattern and add the CSS assertions where `css` is already decoded.

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_operating_layer.py::test_operating_layer_static_server_serves_split_assets -q
```

Expected: fail because the review-loop UI hooks are not present yet.

- [ ] **Step 3: Call the renderer**

In `src/devflow/control_room/operating_layer_script.py`, inside `render()`, add this call immediately after `renderActions();`:

```javascript
  renderReviewLoopSummary();
```

- [ ] **Step 4: Add the renderer**

In `src/devflow/control_room/operating_layer_script.py`, add this function immediately before `renderActions()`:

```javascript
function renderReviewLoopSummary() {
  const container = byId("action-preview");
  const loop = snapshot.review_loop;
  if (!container || !loop || !sectionExpanded("actions")) return;
  const existing = container.querySelector("[data-review-loop-summary]");
  if (existing) existing.remove();
  const card = document.createElement("div");
  const statusClass = String(loop.status || "watching").replace(/[^a-z0-9_-]/gi, "");
  card.className = `review-loop-card ${statusClass}`;
  card.setAttribute("data-review-loop-summary", "true");
  card.innerHTML = `
    <div class="section-heading">
      <span>Browser approvals</span>
      <strong>${escapeHtml(loop.status || "watching")}</strong>
    </div>
    <p>${escapeHtml(loop.headline || "No browser approval items are waiting")}</p>
    <div class="review-loop-metrics">
      <span><strong>${escapeHtml(loop.needs_verification_count)}</strong> verify</span>
      <span><strong>${escapeHtml(loop.ready_to_promote_count)}</strong> promote</span>
      <span><strong>${escapeHtml(loop.blocked_decision_count)}</strong> decisions</span>
    </div>
    <code>${escapeHtml(loop.next_safe_action || "devflow dashboard")}</code>
    <p class="label">${escapeHtml(loop.evidence_summary || "No review evidence yet.")}</p>
  `;
  container.prepend(card);
}
```

- [ ] **Step 5: Keep preview rendering from erasing the summary**

In `renderActionPreview(action)`, replace the line:

```javascript
  preview.innerHTML = "";
```

with:

```javascript
  preview.querySelectorAll(":scope > *:not([data-review-loop-summary])").forEach((node) => node.remove());
```

In the `if (!action)` block, replace:

```javascript
    preview.innerHTML = `<div class="empty">Select an action to inspect command safety</div>`;
```

with:

```javascript
    preview.insertAdjacentHTML("beforeend", `<div class="empty">Select an action to inspect command safety</div>`);
```

In the main preview assignment, replace:

```javascript
  preview.innerHTML = `
```

with:

```javascript
  preview.insertAdjacentHTML("beforeend", `
```

and replace the closing statement:

```javascript
  `;
```

with:

```javascript
  `);
```

- [ ] **Step 6: Add styles**

In `src/devflow/control_room/operating_layer_styles.py`, add this CSS near the existing Action Rail styles:

```css
.review-loop-card {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px;
  background: var(--panel-2);
  display: grid;
  gap: 8px;
}

.review-loop-card.ready_to_promote {
  border-color: var(--teal);
}

.review-loop-card.needs_human_decision {
  border-color: var(--red);
}

.review-loop-metrics {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.review-loop-metrics span {
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 8px;
  background: var(--panel);
}
```

- [ ] **Step 7: Run asset test**

Run:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_operating_layer.py::test_operating_layer_static_server_serves_split_assets -q
```

Expected: pass.

## Task 4: Clean Stale Operating-Layer Docs

**Files:**
- Modify: `docs/architecture/local-operating-layer-ui.md`
- Modify: `docs/agent-handoff.md`
- Modify: `docs/control-room-mvp.md`
- Modify: `docs/superpowers/specs/2026-06-14-milestone-18-operating-layer-beta-design.md`

- [ ] **Step 1: Search stale result-retention wording**

Run:

```bash
rg -n "preserve approved|result retention|result-retention|pending UI action|Next Safe Slice|Last approved command" docs PRODUCT_NORTH_STAR.md README.md
```

Expected: identify active docs that still call result retention future or pending.

- [ ] **Step 2: Update architecture doc**

In `docs/architecture/local-operating-layer-ui.md`, replace the `## Next Safe Slice` numbered list with:

```markdown
## Next Safe Slice

Prepare the operating-layer beta review loop:

1. Verify approved Action Rail command-result retention through focused tests and browser QA.
2. Add a derived review-loop summary to the snapshot so the browser can explain verification, promotion, and human-decision pressure without raw logs.
3. Keep the dogfood production-readiness visual QA case passing with deterministic fallback, external/Appshot, or optional Playwright evidence.
4. Review the full operating-layer diff for accidental scope creep.
5. Keep all active docs aligned with the guarded control-layer contract.
6. Run focused and broader verification.
7. Stage/commit only after human approval.

Do not add worker execution, task creation, patch application, git publication, or broad mutation buttons to the browser shell as part of this checkpoint. Keep approved browser mutations limited to exact task verification and exact task promotion through the guarded `/api/actions/run` approval path.
```

- [ ] **Step 3: Update agent handoff**

In `docs/agent-handoff.md`, replace the `## Pending Operating-Layer Plan` section with:

```markdown
## Pending Operating-Layer Plan

The next safe UI milestone is Milestone 18 Operating-Layer Beta: verify approved Action Rail result retention, remove stale pending-result-retention wording, add a derived browser review-loop summary, and dogfood exact browser verification and promotion without expanding browser mutations beyond the current guarded approval path.
```

- [ ] **Step 4: Update MVP current-priority line**

In `docs/control-room-mvp.md`, replace the current-priority paragraph that ends with Milestone 17 with:

```markdown
> **Current Priority**: Milestone 14 goal execution control loop, Milestone 14A hardening, Milestone 15/15B multi-project control-room hardening, Milestone 16 agent registry runtime hardening, and Milestone 17 task-fit/context-routing evidence are complete. Milestone 18 Operating-Layer Beta is the next browser review-loop hardening direction: verify approved Action Rail result retention, improve browser review-loop visibility, and keep exact verification/promotion as the only browser-approved mutations. Current model selection is registry-backed and model-agnostic at the explicit-role level through local discovery, selected-agent evidence, and derived routing evidence. Autonomous best-model-for-any-task routing remains excluded and must not enable remote provider execution, autonomous routing, auto-promotion, auto-commit, auto-push, pull requests, databases, or worker-owned verification.
```

- [ ] **Step 5: Re-run stale wording search**

Run:

```bash
rg -n "pending UI action|preserve approved Action Rail command results after snapshot refresh using|result retention as future|result-retention.*pending" docs PRODUCT_NORTH_STAR.md README.md
```

Expected: no matches.

## Task 5: Verify Review Loop And Mutation Boundary

**Files:**
- No new file modifications expected unless tests expose a gap.

- [ ] **Step 1: Run focused operating-layer tests**

Run:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_operating_layer.py -q
```

Expected: pass.

- [ ] **Step 2: Run visual QA plan**

Run:

```bash
PYTHONPATH=src:. .venv/bin/devflow operating-layer visual-qa --json
```

Expected: pass JSON with `surface` or `visual_flow` describing the operating layer, desktop/mobile viewports, no-horizontal-overflow coverage, Orchestrator-first coverage, worker progress rows, and Action Rail safety states.

- [ ] **Step 3: Run production-readiness dogfood**

Run:

```bash
PYTHONPATH=src:. .venv/bin/devflow dogfood run --suite production-readiness
```

Expected: pass with Silver-or-better readiness. If it fails below Silver, fix the smallest real operating-layer regression instead of weakening dogfood.

- [ ] **Step 4: Run release companion gate**

Run:

```bash
./scripts/release-check.sh
```

Expected: pass with packaging build, `twine check`, and wheel smoke install enabled.

- [ ] **Step 5: Confirm repo state**

Run:

```bash
git diff --check
devflow git status
```

Expected: `git diff --check` has no output. `devflow git status` reports the expected branch and only the Milestone 18 files as dirty before checkpoint.

## Task 6: Browser Dogfood Acceptance

**Files:**
- No source changes expected unless browser QA finds a defect.

- [ ] **Step 1: Create temporary dogfood project**

Run:

```bash
ROOT=$(mktemp -d -t devflow-m18-browser-XXXXXX)
PROJECT_ROOT="$ROOT/project"
mkdir -p "$PROJECT_ROOT"
cd "$PROJECT_ROOT"
git init
git config user.email devflow@example.test
git config user.name "DevFlow Test"
git commit --allow-empty -m "initial"
PYTHONPATH=/Users/josh/Desktop/Dev-Flow/src:/Users/josh/Desktop/Dev-Flow /Users/josh/Desktop/Dev-Flow/.venv/bin/devflow init
PYTHONPATH=/Users/josh/Desktop/Dev-Flow/src:/Users/josh/Desktop/Dev-Flow /Users/josh/Desktop/Dev-Flow/.venv/bin/devflow task create "Milestone 18 browser review loop"
PYTHONPATH=/Users/josh/Desktop/Dev-Flow/src:/Users/josh/Desktop/Dev-Flow /Users/josh/Desktop/Dev-Flow/.venv/bin/devflow task run task-0001 --worker shell -- /bin/sh -c 'printf "browser review evidence\n" > result.txt'
```

Expected: task `task-0001` has worker output and needs verification.

- [ ] **Step 2: Start local operating-layer server**

Run from `$PROJECT_ROOT`:

```bash
PYTHONPATH=/Users/josh/Desktop/Dev-Flow/src:/Users/josh/Desktop/Dev-Flow /Users/josh/Desktop/Dev-Flow/.venv/bin/devflow operating-layer serve --host 127.0.0.1 --port 8765
```

Expected: server prints a local URL and stays running.

- [ ] **Step 3: Browser-check verification**

Open `http://127.0.0.1:8765`, select `task-0001`, enter verification command:

```bash
test -s result.txt
```

Click `Approve and run verification`.

Expected visible state after snapshot refresh:

```text
Exit 0
task-0001: verification passed
Last approved command
```

The review-loop summary should show one promotion-ready item or the correct promotion next action.

- [ ] **Step 4: Browser-check promotion**

In the browser, approve promotion for the exact task promotion command and add this context note:

```text
Milestone 18 browser review loop dogfood.
```

Expected visible state after snapshot refresh:

```text
Exit 0
Promotion complete.
Last approved command
```

The task state should be `promoted`, and the browser should not offer broad worker execution, task creation, patch application, git publication, provider calls, or autonomous routing as approved browser mutations.

- [ ] **Step 5: Stop server and inspect canonical evidence**

Stop the server with `Ctrl-C`, then run:

```bash
PYTHONPATH=/Users/josh/Desktop/Dev-Flow/src:/Users/josh/Desktop/Dev-Flow /Users/josh/Desktop/Dev-Flow/.venv/bin/devflow task show task-0001
test -f .devflow/tasks/task-0001/verification.json
test -f .devflow/tasks/task-0001/promotion-context.md
```

Expected: task show agrees with the browser state, and both evidence files exist.

## Task 7: Final Review And Checkpoint

**Files:**
- Review all modified files.

- [ ] **Step 1: Review final diff**

Run:

```bash
git diff -- src/devflow/control_room/operating_layer.py src/devflow/control_room/operating_layer_script.py src/devflow/control_room/operating_layer_styles.py tests/test_operating_layer.py docs/architecture/local-operating-layer-ui.md docs/agent-handoff.md docs/control-room-mvp.md docs/superpowers/specs/2026-06-14-milestone-18-operating-layer-beta-design.md docs/superpowers/plans/2026-06-14-milestone-18-operating-layer-beta.md
```

Expected: diff only covers Milestone 18 operating-layer beta scope.

- [ ] **Step 2: Confirm boundary self-check**

Check the diff against these constraints:

```text
No browser task creation.
No browser worker execution.
No browser patch application.
No browser git publication.
No provider-backed model calls.
No autonomous routing execution.
No database-backed operating-layer state.
No hidden memory/vector/RAG/embedding/training surface.
```

Expected: all statements remain true.

- [ ] **Step 3: Create checkpoint only after approval**

After verification passes and the human approves committing, run:

```bash
devflow git checkpoint --message "feat: harden operating-layer beta review loop" --yes
```

Expected: checkpoint created through the Dev-Flow Git bridge.
