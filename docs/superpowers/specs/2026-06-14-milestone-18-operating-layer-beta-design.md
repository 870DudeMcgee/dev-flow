# Milestone 18 Operating-Layer Beta Design

## Goal

Make the local browser operating layer trustworthy enough to use as the daily Dev-Flow review surface.

Milestone 18 should let Dev-Flow answer: "What is happening across my projects, what needs my decision, what evidence proves it, and what is the next safe action I can approve without reading raw logs?"

## Trigger Evidence

Milestone 17 made task-fit, scout, route, and scorecard evidence explicit while keeping execution human-invoked. The next product gap is not another routing or provider layer. It is the control room itself.

The active operating-layer architecture already has:

- `devflow operating-layer snapshot --json`
- `devflow operating-layer serve --host 127.0.0.1 --port 8765`
- project drilldown over registry-backed projects
- hash-routed pages for overview, workers, goals, progress, actions, evidence, and review
- supervisor-classified Action Rail commands
- read-only browser command execution
- exact approval-gated task verification
- exact approval-gated task promotion

Current main already contains client-side approved Action Rail result-retention hooks. Active docs still describe that issue as the pending UI action, so Milestone 18 must start by verifying the hook behavior end to end and cleaning stale operating-layer guidance before broadening the browser review loop.

## Product Decision

Milestone 18 is an operating-layer beta hardening milestone, not a new automation milestone.

Promote these pieces:

1. Verify approved verification and promotion command result retention after snapshot refresh.
2. Remove active-doc wording that still frames result retention as future work.
3. Tighten Action Rail rendering around exact safe next actions, explicit approval gates, command previews, and bounded command output.
4. Improve task, goal, evidence, and review drilldowns so readiness can be understood without opening raw logs.
5. Dogfood a real browser review loop: create a task, run a worker through the CLI, verify from the browser, promote from the browser, and confirm evidence stays visible.
6. Keep production-readiness dogfood and operating-layer visual QA as the milestone readiness gate.

Keep these deferred:

- browser task creation
- browser worker execution
- browser patch application
- git publication from the browser
- provider-backed workers
- autonomous routing or automatic worker assignment
- PR automation
- database-backed operating-layer state
- hidden memory, vector search, RAG, embeddings, or training

## Rejected Approaches

### Jump To Remote Provider Adapters

Provider execution is attractive, but it would move Dev-Flow toward being another coding agent before the control room feels reliable. The North Star says visibility, isolation, recovery, and human approval come first.

### Add More Browser Mutations

Task creation, worker execution, patch application, and git publication are useful future surfaces. They are too risky for this milestone because the browser approval model has only been proven for exact verification and exact promotion commands. Expanding mutation scope now would weaken the safety story.

### Treat The Result-Retention Fix As A Tiny One-Off

The immediate bug is small, but the product problem is larger: the browser must preserve proof, explain state changes, and keep the next safe action obvious. Milestone 18 should use the small fix as the first acceptance slice of a broader review-loop beta.

## Architecture

Implementation should stay inside `src/devflow/control_room/`.

Thin CLI wiring may remain in `src/devflow/cli.py` only where existing `devflow operating-layer` commands require it. Browser assets should continue through the existing split modules:

- `operating_layer.py` for derived snapshot composition
- `operating_layer_server.py` for local HTTP routing and guarded command execution
- `operating_layer_assets.py` as the public asset facade
- `operating_layer_html.py`, `operating_layer_styles.py`, and `operating_layer_script.py` for bundled UI assets

The filesystem remains the source of truth. Browser-only retention must not write canonical task state, local storage, a database, or extra `.devflow/` artifacts. It may hold transient in-memory client state for the current browser session.

## UX Contract

The beta review loop should prioritize proof over decoration:

1. The first screen names the current project, health state, active decision items, and next safe action.
2. A selected task shows status, workspace/worktree context, latest event, verification state, promotion readiness, evidence paths, and bounded previews.
3. The Action Rail shows command preview, safety classification, required approval text, and command result.
4. After approved verification or promotion, the UI refreshes from `/api/snapshot` while preserving the just-run result for the selected task.
5. If the task's next action changes after refresh, both facts remain understandable: the last approved command result and the new next safe action.
6. Unsafe or unsupported actions remain blocked with clear reasons and CLI-first next steps.

## Command And Mutation Boundary

Stable commands remain:

```bash
devflow operating-layer snapshot --json
devflow operating-layer serve --host 127.0.0.1 --port 8765
```

The browser may execute:

- supervisor-classified `pure_read_only` Dev-Flow commands
- exact human-approved `devflow task verify <task_id> ...` commands
- exact human-approved `devflow task promote <task_id> ...` commands

The browser must continue to block:

- worker execution
- task creation
- patch review, dry-run, or application
- git checkpoint, push, sync, publication, or PR commands
- provider-backed model calls
- autonomous routing execution

## Error Handling

Milestone 18 should make failure states plain:

- If snapshot refresh fails after an approved action, keep the command result visible and show refresh failure separately.
- If the selected task disappears or changes project scope, keep the result visible only when it can still be tied to the same project and task id.
- If the refreshed task no longer includes the prior action, display it as "Last approved command" instead of pretending it is still the current next action.
- If server-side approval fails, show the refusal reason and do not update retained success state.
- If command output is capped, mark it clearly and point to the relevant task log or evidence path when available.

## Testing

Focused tests should cover:

- client asset hooks for approved-action result retention
- server behavior for approved verification, approved promotion, and blocked approval-required actions
- snapshot shape stability for task progress, evidence, review, Action Rail, and project drilldown
- no broad mutation commands exposed through the browser action path

Manual or browser QA should cover:

- desktop and mobile operating-layer rendering
- no overflow in key review surfaces
- Orchestrator-first ordering
- worker progress rows
- Action Rail safety state
- approved verification result retention after refresh
- approved promotion result retention after refresh

Milestone readiness should include:

```bash
.venv/bin/python -m pytest tests/test_operating_layer.py -q
devflow dogfood run --suite production-readiness
./scripts/release-check.sh
```

Before calling the milestone ship-ready, run release readiness with captured full-suite and stale-context evidence:

```bash
devflow release readiness --pytest-evidence <pytest-log> --stale-context-evidence <stale-context-log>
```

## Acceptance Check

Create a temporary project and exercise the browser review loop:

1. Create a task.
2. Run a shell worker from the CLI.
3. Open `devflow operating-layer serve`.
4. Select the task in the browser.
5. Approve and run exact verification from the browser.
6. Confirm the verification result remains visible after `/api/snapshot` refresh.
7. Confirm the task now presents promotion readiness or the correct next safe action.
8. Approve and run exact promotion from the browser.
9. Confirm the promotion result remains visible after refresh.
10. Confirm canonical task state, evidence paths, and project status agree with the browser.

## Product Boundary Self-Check

- This builds the control room, not another coding agent.
- It makes parallel work more visible, reviewable, and recoverable.
- It reduces log-reading ceremony instead of adding workflow rituals.
- It keeps state clear: filesystem artifacts remain authoritative, browser retention is transient display state.
- It works without paid frontier-model credits.
- Workers remain replaceable because the UI reads evidence rather than depending on a worker implementation.
- The main repo stays protected because browser mutations remain narrowly approval-gated.
- Failures become more understandable at the browser decision point.
- This is useful in the MVP and does not depend on speculative provider architecture.
