# Control Room Cleanup Release Gate Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` or `executing-plans` to implement this plan task-by-task. Track progress with the checkbox steps below.

Date: 2026-06-26
Status: ready for implementation handoff

## Goal

Close out the operating-layer/control-room cleanup phase with a broad release-readiness gate before any push, promotion, tag, build, or publication.

After this slice:

- The five operating-layer cleanup candidates have current broad verification evidence.
- Full pytest, production-readiness dogfood, operating-layer visual QA, stale-context scan, Graphify diagnostics, and Dev-Flow release readiness have been run or explicitly blocked with evidence.
- `docs/architecture/control-room-cleanup-checkpoint-2026-06-25.md` records the final verification outcome for the cleanup train now ending at the implementation commit.
- The repo remains clean, `graphify-out/` remains uncommitted generated evidence, and the next safe action is either repair the first failing gate or ask for explicit approval to push/tag/build.

## Current State

Start from clean `main` after commit:

```text
8894e3e6 refactor: adapt brainstorm pipeline responses
```

Current branch state reported by the prior agent:

- clean worktree
- local `main` is 9 commits ahead of `origin/main`
- `safe_for_worker_writes: yes`

Architecture cleanup state:

- Candidate 1 complete: Task workbench projection Module.
- Candidate 2 complete: browser task capability Module.
- Candidate 3 complete: first-viewport presentation Module.
- Candidate 4 complete: evidence/review detail Module.
- Candidate 5 complete: Brainstorm/Pipeline response Interface.

The next step is not another refactor. It is a release/readiness Adapter slice: gather the evidence required by the existing release-readiness Interface and update the cleanup checkpoint with the result.

## Non-Goals

- Do not push, publish, promote, tag, build a final release, or open a PR without explicit human approval.
- Do not commit `graphify-out/`.
- Do not use Hyperplane.
- Do not add product features.
- Do not weaken or skip a failed release gate. Repair the smallest real blocker or report it clearly.
- Do not treat older `.devflow/release/candidate-5-*` logs as current evidence for this cleanup train; they predate these operating-layer refactors.

## Files Likely To Modify

- `docs/architecture/control-room-cleanup-checkpoint-2026-06-25.md`
- optionally `docs/architecture/operating-layer-ui-deepening-backlog.md` if final status wording needs closure
- optionally a new handoff under `docs/handoffs/` if the implementation agent wants a durable final report

Runtime evidence should be written under `.devflow/release/control-room-cleanup-2026-06-26/` and should remain untracked because `.devflow/` is ignored.

## Task 0: Confirm Baseline

- [ ] Run:

```bash
git status --short
PYTHONPATH=src:. .venv/bin/python -m devflow.cli git status
git log --oneline -10
```

Expected:

- normal Git status is clean
- `main` is ahead of `origin/main`
- `safe_for_worker_writes: yes`
- latest implementation commit is `8894e3e6 refactor: adapt brainstorm pipeline responses`

- [ ] Create the evidence directory:

```bash
mkdir -p .devflow/release/control-room-cleanup-2026-06-26
```

## Task 1: Run Focused Smoke Before Expensive Gates

Files:

- No source edits expected

- [ ] Run the focused operating-layer/control-room smoke first:

```bash
set -o pipefail
PYTHONPATH=src:. .venv/bin/python -m pytest \
  tests/test_task_workbench_projection.py \
  tests/test_browser_task_capabilities.py \
  tests/test_evidence_review_detail.py \
  tests/test_brainstorm_workbench.py \
  tests/test_brainstorm_task_bridge.py \
  tests/test_operating_layer.py \
  tests/test_supervisor_operating_surface.py \
  -q | tee .devflow/release/control-room-cleanup-2026-06-26/focused-operating-layer.log
```

Expected: pass.

If this fails, stop and repair the smallest real regression before running full pytest.

## Task 2: Capture Full Pytest Evidence

Files:

- Runtime evidence only

- [ ] Run full pytest and capture the complete output:

```bash
set -o pipefail
PYTHONPATH=src:. .venv/bin/python -m pytest tests --ignore=scratch -q --tb=short \
  | tee .devflow/release/control-room-cleanup-2026-06-26/full-pytest.log
```

Expected:

- exit code `0`
- evidence log contains a summary matching `N passed`
- no `failed` or `error` summary

If this fails, stop and repair the first failing regression. Do not edit the log to make release readiness pass.

## Task 3: Run Production-Readiness Dogfood

Files:

- Runtime evidence under `.devflow/dogfood/`
- Runtime release note under `.devflow/release/control-room-cleanup-2026-06-26/`

- [ ] Run:

```bash
set -o pipefail
PYTHONPATH=src:. .venv/bin/python -m devflow.cli dogfood run \
  --suite production-readiness \
  | tee .devflow/release/control-room-cleanup-2026-06-26/dogfood-production-readiness.log
```

Expected:

- exit code `0`
- Silver threshold met
- no root runtime evidence is written unless the command explicitly says it used a scratch project

- [ ] Record the latest dogfood run id for release readiness:

```bash
PYTHONPATH=src:. .venv/bin/python -m devflow.cli dogfood report latest \
  > .devflow/release/control-room-cleanup-2026-06-26/dogfood-report.md
```

Inspect the `dogfood_run_id:` line in `dogfood-production-readiness.log`. Use `--dogfood-run latest` only if the latest run is the one just produced; otherwise pass the recorded run id explicitly in Task 6.

## Task 4: Capture Operating-Layer Visual QA Evidence

Files:

- Runtime visual QA evidence under `.devflow/visual-qa/`
- Runtime release log under `.devflow/release/control-room-cleanup-2026-06-26/`

- [ ] Run:

```bash
set -o pipefail
PYTHONPATH=src:. .venv/bin/python -m devflow.cli operating-layer visual-qa \
  --write-current \
  --update-baseline \
  --json \
  | tee .devflow/release/control-room-cleanup-2026-06-26/operating-layer-visual-qa.json
```

Expected:

- exit code `0`
- desktop and mobile current/baseline evidence exists under `.devflow/visual-qa/`
- no horizontal overflow regression
- first viewport still exposes Brainstorm, Pipeline, Worker lanes, Review queue, and Evidence stream

If the command reports marker warnings, inspect them. Known warning classes may be documented in the checkpoint only if they do not contradict the current product contract.

## Task 5: Capture Stale-Context Evidence

Files:

- Runtime evidence only

- [ ] Run the release-readiness stale-context scan exactly as the release Module expects:

```bash
rg -n "(must use /Users/jewelbait/Desktop/DevFlow|old checkout path is current|legacy workflow authority|autonomous routing is active)" \
  AGENTS.md PRODUCT_NORTH_STAR.md README.md docs src/devflow/control_room tests \
  --glob '!src/devflow/control_room/release_readiness.py' \
  > .devflow/release/control-room-cleanup-2026-06-26/stale-context.log || true
```

Expected:

- `.devflow/release/control-room-cleanup-2026-06-26/stale-context.log` is empty

If it contains matches, either fix stale context in tracked docs/source/tests or explain why the release-readiness stale-context contract itself needs a follow-up. Do not pass a non-empty file to release readiness and claim success.

## Task 6: Run Dev-Flow Release Readiness

Files:

- Runtime evidence only unless the checkpoint doc is updated afterward

- [ ] Run:

```bash
set -o pipefail
PYTHONPATH=src:. .venv/bin/python -m devflow.cli release readiness \
  --pytest-evidence .devflow/release/control-room-cleanup-2026-06-26/full-pytest.log \
  --stale-context-evidence .devflow/release/control-room-cleanup-2026-06-26/stale-context.log \
  --dogfood-run latest \
  --json \
  | tee .devflow/release/control-room-cleanup-2026-06-26/release-readiness.json
```

Expected:

- status is `passed`
- checks are passed:
  - clean Dev-Flow Git status
  - full pytest
  - production-readiness dogfood
  - operating-layer visual QA evidence
  - stale-context scan
  - standard handoff report

If Task 3 recorded a specific dogfood run id that is not the latest run anymore, replace `latest` with that run id.

If status is `blocked`, stop and repair the first blocked gate named by `next_safe_action`.

## Task 7: Refresh Graphify As Architecture Evidence

Files:

- `graphify-out/` generated evidence only
- optional docs checkpoint update

- [ ] Run:

```bash
.venv/bin/graphify update .
.venv/bin/graphify diagnose multigraph --json --graph graphify-out/graph.json \
  > .devflow/release/control-room-cleanup-2026-06-26/graphify-multigraph-diagnose.json
.venv/bin/graphify explain "control_room_operating_layer" --graph graphify-out/graph.json \
  > .devflow/release/control-room-cleanup-2026-06-26/graphify-operating-layer.txt
.venv/bin/graphify explain "control_room_task_workbench" --graph graphify-out/graph.json \
  > .devflow/release/control-room-cleanup-2026-06-26/graphify-task-workbench.txt
.venv/bin/graphify explain "control_room_browser_task_capabilities" --graph graphify-out/graph.json \
  > .devflow/release/control-room-cleanup-2026-06-26/graphify-browser-task-capabilities.txt
.venv/bin/graphify explain "control_room_operating_layer_first_viewport" --graph graphify-out/graph.json \
  > .devflow/release/control-room-cleanup-2026-06-26/graphify-first-viewport.txt
.venv/bin/graphify explain "control_room_evidence_review_detail" --graph graphify-out/graph.json \
  > .devflow/release/control-room-cleanup-2026-06-26/graphify-evidence-review-detail.txt
.venv/bin/graphify explain "control_room_brainstorm_pipeline" --graph graphify-out/graph.json \
  > .devflow/release/control-room-cleanup-2026-06-26/graphify-brainstorm-pipeline.txt
```

Expected:

- multigraph diagnostic reports no structural graph problems
- generated `graphify-out/` remains ignored
- lightweight metrics can be copied into the checkpoint doc, but generated files are not committed

## Task 8: Update Cleanup Checkpoint

Files:

- Modify: `docs/architecture/control-room-cleanup-checkpoint-2026-06-25.md`

- [ ] Add a final section for the release gate at current head.
- [ ] Include:
  - current head SHA
  - local ahead count
  - focused smoke result
  - full pytest result and evidence path
  - dogfood result and run id/evidence path
  - visual QA result/evidence path
  - stale-context scan result/evidence path
  - release-readiness status/evidence path
  - Graphify diagnostic summary and key degree metrics
  - final next safe action
- [ ] Update stale wording in `Remaining Risks` if it still says no full release gate has run after the gate passes.
- [ ] Keep the checkpoint honest if any gate blocks. Do not mark release readiness as passed unless the command passed.

Run:

```bash
git diff --check
rg -n "No full release gate has run|23-commit phase|24-commit cleanup train|a67db3c" docs/architecture/control-room-cleanup-checkpoint-2026-06-25.md
```

Expected:

- no whitespace errors
- no stale statements remain unless intentionally quoted as history with current correction nearby

## Task 9: Final Status And Commit

Files:

- Commit only tracked docs changes
- Do not stage `.devflow/`, `graphify-out/`, `dist/`, or other runtime/build evidence

- [ ] Run:

```bash
git status --short
git diff -- docs/architecture/control-room-cleanup-checkpoint-2026-06-25.md
git diff --check
PYTHONPATH=src:. .venv/bin/python -m devflow.cli git status
```

Expected:

- tracked dirty files are limited to checkpoint docs
- `.devflow/` and `graphify-out/` do not appear in normal status
- Dev-Flow status remains safe for worker writes

- [ ] Commit the checkpoint update:

```bash
git add docs/architecture/control-room-cleanup-checkpoint-2026-06-25.md
git commit -m "docs: record control room cleanup release gate"
```

- [ ] Run final status:

```bash
git status --short
PYTHONPATH=src:. .venv/bin/python -m devflow.cli git status
```

Expected:

- clean worktree
- no operation in progress
- if all gates passed, `safe_for_push: yes`

## Rollback And Risk Notes

- Runtime evidence under `.devflow/` is intentionally ignored. Do not force-add it.
- `graphify-out/` is intentionally generated evidence. Do not force-add it.
- `dist/` may be produced if the release-check companion script is run separately; it is ignored and should not be committed.
- If full pytest or dogfood fails, the right output is a blocked handoff with the failing command and first failure, not a docs-only success commit.
- If release readiness passes, still do not push. The next action is to ask the human for explicit approval before `PYTHONPATH=src:. .venv/bin/python -m devflow.cli push-main`.
