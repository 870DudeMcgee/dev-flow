# 2026-06-27 Graphify + Ponytail Architecture Subagent Handoff

## Status

needs-review

## Outcome

- A fresh Graphify architecture audit was run on 2026-06-27 from commit
  `818ddfd`.
- Ponytail skills were installed from `DietrichGebert/ponytail`:
  `ponytail`, `ponytail-review`, and `ponytail-audit`.
- The architecture work queue is documented in
  `docs/architecture/graphify-ponytail-architecture-work-2026-06-27.md`.
- A temporary visual report was generated at
  `/tmp/architecture-review-20260627T155650Z.html`.
- No product code was intentionally changed by this documentation handoff.

## Files Changed

- `docs/architecture/graphify-ponytail-architecture-work-2026-06-27.md`
  records the work items, Graphify evidence, Ponytail filter, risks, and
  parallelization map.
- `docs/handoffs/2026-06-27-graphify-ponytail-architecture-subagent-handoff.md`
  provides this paste-ready handoff prompt for the next session.

## Verification

Run before trusting this handoff as current:

```bash
git status --short
git diff --check
rg -n "Hyper[p]lane|hyper[p]lane" docs/architecture/graphify-ponytail-architecture-work-2026-06-27.md docs/handoffs/2026-06-27-graphify-ponytail-architecture-subagent-handoff.md
```

Expected:

- `git diff --check` reports no whitespace errors.
- A separate stale-checkout search for the quarantined legacy path named in
  `AGENTS.md` reports no matches in these new docs.
- Hyperplane appears only in the explicit non-recommendation/quarantine context.

## Risks

- The working tree had uncommitted code and doc changes before this handoff was
  written. The next session must not revert them.
- Work Item 1 and Work Item 3 both touch `operating_layer.py` and
  `tests/test_operating_layer.py`; do not run those implementation subagents in
  parallel in the same worktree.
- Work Item 2 may also touch `operating_layer.py` during integration. Serialize
  that part after Work Item 1.
- `graphify-out/` is generated and ignored. Do not commit it unless explicitly
  instructed.

## Recommended Next Steps

Use the prompt below in a fresh session. It is written for a coordinator agent
that can dispatch subagents and use isolated worktrees where appropriate.

## Next Safe Action

Paste the following prompt into a new Codex session from `<repo-root>` after
confirming the current working tree state.

---

# Prompt For Next Session

You are working in `/Users/josh/Desktop/Dev-Flow`.

Read these first:

1. `AGENTS.md`
2. `CONTEXT.md`
3. `docs/operator-centered-mission.md`
4. `docs/architecture/graphify-ponytail-architecture-work-2026-06-27.md`
5. `docs/handoffs/2026-06-27-graphify-ponytail-architecture-subagent-handoff.md`

Use these skills/processes:

- `improve-codebase-architecture` for Graphify-backed module deepening language.
- Ponytail full mode manually if the installed skill is not auto-listed:
  delete/reuse before adding seams; do not add a module unless it hides real
  implementation or deletes more complexity than it introduces.
- `subagent-driven-development` for work execution, but do not dispatch
  implementation subagents in parallel when their files overlap.
- `worker-handoff` for every subagent result and final session handoff.
- `verification-before-completion` before any completion claim.

Start with:

```bash
git status --short
git diff --stat
git diff --check
git rev-parse --short HEAD
env PYTHONPATH=src:. .venv/bin/python -m devflow.cli architecture audit --write-doc
.venv/bin/graphify diagnose multigraph --json --graph graphify-out/graph.json
```

Important:

- Preserve existing uncommitted work. Do not revert files you did not edit.
- Do not push, publish, promote, merge, or open PRs without explicit human
  approval.
- Do not use Hyperplane for this cleanup.
- Do not commit generated `graphify-out/` files.
- Keep all product behavior under `src/devflow/control_room/`, `tests/`, and
  docs unless a touched interface requires a CLI bridge.

## Coordination Plan

Use isolated worktrees if you have tooling for parallel subagents. If working in
one checkout, run only one implementation subagent at a time.

Parallel-safe wave:

- Subagent D: Work Item 4, Dogfood harness mechanics.
- Subagent A: Work Item 1, Task workbench mirroring deletion.

Only run those two in parallel if they are in isolated worktrees. They touch
different implementation/test files.

Serialized wave:

- Subagent B: Work Item 2, Agent catalog extraction.
- Subagent C: Work Item 3, Idea greenhouse projection extraction.

Run Work Item 1 before Work Item 3 because both edit `operating_layer.py` and
`tests/test_operating_layer.py`. Run operating-layer integration for Work Item 2
after Work Item 1 unless it is isolated and explicitly merged.

## Subagent A Prompt: Task Workbench Mirroring Deletion

Goal:

Delete shallow task-workbench mirroring in `operating_layer.py` while preserving
the browser snapshot contract.

Read:

- `docs/architecture/graphify-ponytail-architecture-work-2026-06-27.md`
  Work Item 1.
- `src/devflow/control_room/operating_layer.py`
- `src/devflow/control_room/task_workbench.py`
- `tests/test_operating_layer.py`
- `tests/test_task_workbench_projection.py`

Implementation constraints:

- Do not redesign the UI.
- Do not widen browser action permissions.
- Keep `build_operating_layer_snapshot()` as the public snapshot entrypoint.
- Prefer deleting duplicate `OperatingLayer*` task models if tests prove the
  Task workbench models can satisfy the snapshot contract.
- If a public model must remain for compatibility, keep the thinnest conversion
  helper and document why in the handoff.

Suggested steps:

1. Add or update a focused test proving snapshot task-centered fields match
   `build_task_workbench()` for lanes, tasks, promotion desk, evidence stream,
   gate receipts, worker activity, and review loop.
2. Remove duplicate task-centered conversions that the test proves unnecessary.
3. Keep question/inbox pressure overlay behavior intact.
4. Remove unused imports and helpers.
5. Run focused tests:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_task_workbench_projection.py tests/test_operating_layer.py -q
```

6. Run Graphify probes:

```bash
.venv/bin/graphify explain "control_room_operating_layer" --graph graphify-out/graph.json
.venv/bin/graphify explain "control_room_task_workbench" --graph graphify-out/graph.json
```

Report:

- Status: DONE, DONE_WITH_CONCERNS, NEEDS_CONTEXT, or BLOCKED.
- Files changed.
- Exact tests run and result.
- Whether `control_room_operating_layer` degree decreased, stayed flat, or
  increased.
- Any browser snapshot compatibility risk.

## Subagent D Prompt: Dogfood Harness Mechanics

Goal:

Deepen existing Dogfood case result mechanics without splitting every case into
its own module.

Read:

- `docs/architecture/graphify-ponytail-architecture-work-2026-06-27.md`
  Work Item 4.
- `src/devflow/control_room/dogfood.py`
- `src/devflow/control_room/dogfood_case_result.py`
- `src/devflow/control_room/dogfood_case_scratch.py`
- `tests/test_dogfood_harness.py`

Implementation constraints:

- Do not introduce a per-case module package.
- Do not add a registry abstraction unless it deletes more code than it adds.
- Keep Dogfood runtime behavior and evidence paths stable.
- Preserve current scratch repo helper behavior.

Suggested steps:

1. Find repeated state/artifact/command/lesson/cleanup patterns in case
   functions.
2. Move only repeated mechanics into `dogfood_case_result.py`.
3. Keep case-specific scenario logic in `dogfood.py`.
4. Add focused tests only when the moved mechanics are not already covered.
5. Run:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_dogfood_harness.py -q
.venv/bin/graphify explain "control_room_dogfood" --graph graphify-out/graph.json
.venv/bin/graphify explain "control_room_dogfood_case_result" --graph graphify-out/graph.json
```

Report:

- Status: DONE, DONE_WITH_CONCERNS, NEEDS_CONTEXT, or BLOCKED.
- Files changed.
- Exact tests run and result.
- Net line change.
- Any case evidence compatibility risk.

## Subagent B Prompt: Agent Catalog Projection Extraction

Goal:

Separate read-only Agent catalog projection from provider/model onboarding
mutations.

Read:

- `docs/architecture/graphify-ponytail-architecture-work-2026-06-27.md`
  Work Item 2.
- `src/devflow/control_room/agent_onboarding.py`
- `src/devflow/control_room/operating_layer.py`
- `src/devflow/control_room/operating_layer_server.py`
- `src/devflow/cli.py`
- `tests/test_agent_onboarding.py`
- relevant operating-layer agent catalog tests.

Implementation constraints:

- A new module is acceptable only if it carries real catalog projection
  implementation.
- Preserve compatibility imports if existing callers import
  `build_agent_catalog` from `agent_onboarding.py`.
- Do not create a constants-only safety module.
- Do not change provider/model registry write semantics.

Suggested steps:

1. Add or preserve tests around `build_agent_catalog()` output.
2. Extract catalog-only helpers into a module such as
   `src/devflow/control_room/agent_catalog.py`.
3. Keep `add_provider()`, `add_model()`, registry writes, and validation in
   `agent_onboarding.py`.
4. Update imports in CLI/server/operating layer after Work Item 1 has settled.
5. Run:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_agent_onboarding.py tests/test_operating_layer.py::test_operating_layer_snapshot_exposes_agent_catalog_and_model_actions -q
.venv/bin/graphify explain "control_room_agent_onboarding" --graph graphify-out/graph.json
```

Report:

- Status: DONE, DONE_WITH_CONCERNS, NEEDS_CONTEXT, or BLOCKED.
- Files changed.
- Exact tests run and result.
- Whether catalog read projection is now isolated from mutation writes.
- Any import compatibility risk.

## Subagent C Prompt: Idea Greenhouse Projection Extraction

Goal:

Move Idea greenhouse lanes/cards/evidence/action projection out of the broad
operating-layer snapshot module.

Read:

- `docs/architecture/graphify-ponytail-architecture-work-2026-06-27.md`
  Work Item 3.
- `src/devflow/control_room/operating_layer.py`
- `src/devflow/control_room/idea_foundry.py`
- `tests/test_operating_layer.py`
- optional existing idea tests.

Implementation constraints:

- Run after Work Item 1.
- Do not add model calls, background jobs, databases, or auto-promotion.
- Keep browser mutations approval-gated through existing action paths.
- A new module is acceptable only if it owns real projection implementation.

Suggested steps:

1. Add a focused projection test if Idea greenhouse behavior is currently tested
   only through the full snapshot.
2. Extract `_idea_greenhouse()` and related helpers into a projection module.
3. Keep operating-layer snapshot assembly thin.
4. Preserve lane ordering, counts, card limit, evidence paths, lineage, summaries,
   and primary actions.
5. Run:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_idea_foundry.py tests/test_operating_layer.py::test_operating_layer_projects_idea_greenhouse_lanes -q
.venv/bin/graphify explain "control_room_operating_layer" --graph graphify-out/graph.json
```

Report:

- Status: DONE, DONE_WITH_CONCERNS, NEEDS_CONTEXT, or BLOCKED.
- Files changed.
- Exact tests run and result.
- Any snapshot contract risk.

## Coordinator Review After Each Subagent

For each subagent result:

1. Inspect `git diff --stat` and the touched files.
2. Run the subagent's focused verification again in the coordinator worktree.
3. Run a spec compliance review:
   - Did it implement the requested work item?
   - Did it skip explicit non-goals?
   - Did it preserve operator-centered product behavior?
4. Run a Ponytail review:
   - What did it delete?
   - Did it add any shallow module, one-use interface, or speculative seam?
   - Is a smaller diff available?
5. If review finds issues, send the same subagent back with specific fixes.

## Final Verification

After all accepted slices are integrated:

```bash
git diff --check
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_task_workbench_projection.py tests/test_operating_layer.py tests/test_agent_onboarding.py tests/test_dogfood_harness.py -q
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_architecture_boundaries.py tests/test_code_map_check.py tests/test_mvp_boundaries.py tests/test_project_scope_docs.py -q
env PYTHONPATH=src:. .venv/bin/python -m devflow.cli architecture audit --write-doc
.venv/bin/graphify diagnose multigraph --json --graph graphify-out/graph.json
.venv/bin/graphify explain "control_room_operating_layer" --graph graphify-out/graph.json
.venv/bin/graphify explain "control_room_agent_onboarding" --graph graphify-out/graph.json
.venv/bin/graphify explain "control_room_dogfood" --graph graphify-out/graph.json
```

If operating-layer browser behavior changes, also run targeted UI/browser tests
or the operating-layer visual QA command documented in `AGENTS.md`.

## Final Handoff Required

End with:

```markdown
## Status
## Outcome
## Files Changed
## Verification
## Risks
## Recommended Next Steps
## Next Safe Action
```

Include Graphify metric deltas from the fresh audit and explain any target node
whose degree did not improve.
