# Milestone 24 Intent-To-Goal/Task Scaffold Implementation Plan

Status: selected as the next implementation slice. No runtime implementation has started.

> For agentic workers: implement this plan task-by-task. Keep all new product logic under `src/devflow/control_room/`; top-level CLI edits may only bridge to control-room functions.

**Goal:** Turn raw operator requests such as "build a search plugin" into safe, reviewable Dev-Flow goal/task scaffold proposals, then create canonical goal/task state only after explicit human approval.

**Architecture:** Reuse Idea Foundry as the raw intake authority. Add a bounded scaffold proposal layer that derives proposed goal artifacts and task slices from an idea, then thread that proposal through explicit approval commands, supervisor route-message pending actions, Telegram gateway responses, tests, dogfood, and active docs.

**Tech Stack:** Python 3, Typer CLI, filesystem JSON/YAML/Markdown evidence, existing idea/goal/task services, supervisor classifier, Telegram bridge modules, pytest, dogfood harness.

## File Structure

- Create `src/devflow/control_room/intent_scaffold.py`: deterministic intent normalization, scaffold proposal models, ambiguity/refusal handling, and evidence writers.
- Modify `src/devflow/control_room/idea_foundry.py` or the existing idea CLI composition only enough to add scaffold commands.
- Modify `src/devflow/control_room/idea_execution_bridge.py` so approved scaffold evidence can be consumed by `idea create-goal` and task creation paths.
- Modify `src/devflow/control_room/supervisor_surface.py` and `src/devflow/control_room/telegram_routing.py` so implementation-like raw messages produce scaffold pending actions without mutation.
- Modify `src/devflow/control_room/df_telegram_bridge.py` and `src/devflow/control_room/df_telegram_gateway_handler.py` to stop raw `/df` messages from directly creating goals/tasks without explicit approval.
- Add focused tests such as `tests/test_intent_scaffold.py`.
- Extend supervisor and Telegram bridge tests.
- Extend dogfood with an intent-scaffold case.
- Update active docs and write an implementation handoff at completion.

## Guardrails

- Do not call local or remote models from scaffold commands.
- Do not run workers, verification, promotion, git checkpoint, push, PR creation, release, or publication from scaffold commands.
- Keep raw request evidence under Idea Foundry or clearly linked idea-local evidence.
- Keep canonical goal/task writes behind explicit human approval commands.
- Keep `supervisor route-message` read-only.
- Keep Telegram/Hermes as an operator layer, not a Dev-Flow state owner.
- Do not add a database, hidden memory, RAG, embeddings, training, or autonomous routing.

---

## Task 1: Characterize Current Intent-To-Goal Behavior

**Files:**
- Create `tests/test_intent_scaffold.py`
- Read only the relevant sections of existing idea, goal, supervisor, and Telegram tests

- [ ] Add a failing test for a raw request such as "build a search plugin" that expects a scaffold proposal with title, acceptance criteria, affected areas, and useful task slices.
- [ ] Add a failing test that an ambiguous request produces questions and no canonical goal/task writes.
- [ ] Add a failing test that raw Telegram `/df ...` handling does not create goals/tasks without approval.
- [ ] Add a failing test that `supervisor route-message` returns a scaffold pending action while remaining read-only.

Verification:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_intent_scaffold.py -q
```

## Task 2: Add Deterministic Scaffold Proposal Service

**Files:**
- Create `src/devflow/control_room/intent_scaffold.py`
- Modify only narrow helper imports as needed

- [ ] Define scaffold proposal models for source idea, normalized intent, proposed goal, proposed task slices, questions, warnings, refusal reasons, and next commands.
- [ ] Normalize raw text deterministically using local heuristics only.
- [ ] Generate useful task slices with acceptance criteria, dependencies, risk, shared files, context pointers, and verification policy.
- [ ] Stop with questions/refusals when the request is ambiguous, too broad, unsafe, or outside the MVP.
- [ ] Write proposal evidence under the idea evidence tree without mutating canonical goal/task state.

Verification:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_intent_scaffold.py -q
```

## Task 3: Add Idea Scaffold Commands

**Files:**
- Modify idea CLI composition
- Modify `src/devflow/control_room/idea_foundry.py` only if command support needs service helpers
- Extend existing idea tests

- [ ] Add `devflow idea scaffold-goal <idea_id> --dry-run`.
- [ ] Add `devflow idea scaffold-goal <idea_id>` to write proposal evidence.
- [ ] Refuse scaffold writes unless the idea exists and is not archived/rejected.
- [ ] Require explicit human classification and matching promotion before canonical goal/task creation.
- [ ] Print one next safe action after every scaffold command.

Verification:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_idea_foundry.py tests/test_idea_execution_bridge.py tests/test_intent_scaffold.py -q
PYTHONPATH=src:. .venv/bin/devflow idea scaffold-goal <idea_id> --dry-run
```

## Task 4: Consume Approved Scaffold Evidence During Goal/Task Creation

**Files:**
- Modify `src/devflow/control_room/idea_execution_bridge.py`
- Modify goal/task creation helpers only where necessary
- Extend focused bridge tests

- [ ] Make `idea create-goal` use approved scaffold evidence when present.
- [ ] Preserve current behavior when no scaffold evidence exists.
- [ ] Ensure created goals contain meaningful `goal.md`, `prd.md`, `task-slices.yaml`, risks, questions, context pointers, and handoff content.
- [ ] If task records are created from scaffold evidence, require explicit approval and keep workers unrun.
- [ ] Record bidirectional idea-to-goal/task links.

Verification:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_idea_execution_bridge.py tests/test_goal_lifecycle.py tests/test_goal_projection.py tests/test_intent_scaffold.py -q
```

## Task 5: Thread Safe Pending Actions Into Supervisor And Telegram

**Files:**
- Modify `src/devflow/control_room/supervisor_surface.py`
- Modify `src/devflow/control_room/telegram_routing.py`
- Modify `src/devflow/control_room/df_telegram_bridge.py`
- Modify `src/devflow/control_room/df_telegram_gateway_handler.py`
- Extend supervisor/Telegram tests

- [ ] Make implementation-like raw messages classify as scaffold candidates.
- [ ] Keep `supervisor route-message` read-only and return approval-gated pending actions.
- [ ] Make `/df ...` responses show the pending scaffold/idea action instead of directly creating goal/task state.
- [ ] Add explicit copyable approval commands.
- [ ] Preserve current read-only and simple-chat routing behavior.

Verification:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_supervisor_operating_surface.py tests/test_telegram_routing.py tests/test_df_telegram_bridge.py tests/test_intent_scaffold.py -q
PYTHONPATH=src:. .venv/bin/devflow supervisor route-message "build a search plugin" --json
```

## Task 6: Add Dogfood Coverage

**Files:**
- Modify `src/devflow/control_room/dogfood.py`
- Modify `tests/test_dogfood_harness.py`

- [ ] Add a production-readiness case for intent-to-goal scaffold.
- [ ] Exercise raw idea capture, scaffold dry-run, scaffold evidence write, human promotion simulation, goal creation, task-slice projection, and refusal-safe no-worker-execution checks.
- [ ] Assert the case closes any task evidence it creates as evidence-only.
- [ ] Assert no provider calls, worker runs, verification, promotion, commits, or pushes are performed.

Verification:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_dogfood_harness.py -q
PYTHONPATH=src:. .venv/bin/devflow dogfood run --suite production-readiness
```

## Task 7: Close The Milestone

**Files:**
- Update `docs/control-room-mvp.md`
- Update `docs/mvp-contract.md`
- Update `docs/roadmap.md`
- Update `docs/agent-handoff.md`
- Add implementation handoff under `docs/handoffs/`

- [ ] Mark Milestone 24 implemented only after code, focused tests, dogfood, stale-context scan, and release-readiness evidence pass.
- [ ] Remove stale active-doc claims that raw Telegram messages directly create goals/tasks.
- [ ] Keep historical plans/handoffs clearly historical when retained.
- [ ] Do not push, tag, publish, or select the next milestone without explicit human approval.

Suggested final verification:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_intent_scaffold.py tests/test_idea_foundry.py tests/test_idea_execution_bridge.py tests/test_supervisor_operating_surface.py tests/test_telegram_routing.py tests/test_df_telegram_bridge.py tests/test_dogfood_harness.py -q
PYTHONPATH=src:. .venv/bin/devflow dogfood run --suite production-readiness
rg -n "raw Telegram.*directly creates|auto-runs workers|provider-backed intent scaffold|Milestone 24.*implemented" README.md docs AGENTS.md -S
```
