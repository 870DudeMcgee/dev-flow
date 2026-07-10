# V2 First Full-Loop Review — Priority List

Status: Active follow-up list
Date: 2026-07-10
Run reviewed: `.devflow/pipeline-runs/20260709-194406/`

This document records the second-opinion review of the first full V2 spine loop. It is an execution priority list, not a claim that the run completed successfully.

## Current Verdict

The deterministic V2 spine is operational: the targeted loop test suite passed, and the generated artifact workspace passed its eight tests plus an offline CLI smoke. The product build is **not yet complete**:

- the consolidated builder/judge stage failed after three rounds and exhausted its cap;
- the generated `brief_intelligence` package exists only inside the isolated pipeline workspace, not in the main checkout;
- the run is parked at `human_decision`, while `execution-control.json` still reports `running`;
- the artifact is missing required operational behavior, including explicit backfill/daily modes, cron scheduling, and idempotent queue updates;
- repository Ruff reports two errors in `src/devflow/loop/execution.py`.

A later GLM verifier passed the generated workspace after tests were run, but that does not override the failed builder/judge gate. The run remains a human-review item.

## Priority Order

### P0 — Repair truthfulness and gate finalization before another full loop

**Why first:** The operator must be able to trust the status board and evidence. A stale `running` control record and a failed builder/judge result followed by a `passed` verification can make an incomplete build appear complete.

**Work:**

1. Reconcile finalization so `execution-control.json` becomes terminal when the run reaches `human_decision`.
2. Make the final state explicitly distinguish:
   - builder/judge pass or failure;
   - verification pass or failure;
   - human decision pending;
   - product completion.
3. Prevent a verification receipt from promoting a run whose builder/judge gate failed unless the human decision explicitly authorizes that transition.
4. Preserve the decisive judge rationale in the compact summary, not only in the raw worker feed.

**Evidence:**

- `loop-state.json`: `stage = human_decision`.
- `execution-control.json`: `status = running`, `active_role = null`.
- `packet-consolidated-build-judge-summary.json`: `judge_decision = failed`, `build_cap_exhausted = true`.
- `run-log.jsonl`: final consolidated builder/judge dispatch exhausted three rounds.

**Acceptance evidence:** A synthetic failed build reaches a terminal, human-review state with no active execution owner; the board and JSON artifacts agree on stage, gate result, and next action.

### P0 — Preserve and expose builder/judge failure feedback

**Why first:** The loop did the right thing by rejecting incomplete output, but the failure feedback was difficult to recover from the compact artifacts. The first three failures were concrete: truncated/syntax-invalid output, missing modules/tests, and later import/path-contract problems.

**Work:**

1. Store the final judge rationale in the packet summary and verification view.
2. Keep each round's failure reason associated with its builder output.
3. Ensure the next bounded assignment contains the last judge failure, target files, and a complete-file/diff constraint.
4. Add a deterministic completeness check before the judge: declared files exist, Python parses, imports resolve, and test paths exist.

**Acceptance evidence:** A deliberately truncated or incomplete builder response is rejected with a concise actionable reason before semantic judging, and the next round receives that reason.

### P1 — Promote the generated artifact only after it meets the Definition of Done

**Why:** The built `brief_intelligence` package is currently stranded in `.devflow/pipeline-runs/20260709-194406/workspace/`. The main checkout has no corresponding source or tests.

**Work:**

1. Review the generated package against the complete Definition of Done.
2. Resolve the missing requirements listed below before promotion.
3. Use an explicit promotion path so the resulting source files and tests appear in the real checkout and Git diff.
4. Re-run tests from the promoted checkout, not only from the isolated workspace.

**Acceptance evidence:** `src/brief_intelligence/` and its tests exist in the main worktree, the promotion manifest names them, and the real checkout test command passes.

### P1 — Complete the artifact's required operational contract

**Why:** The current package passes its narrow tests, but its CLI does not implement the complete requested behavior.

**Required fixes:**

- Add explicit `--backfill` behavior for existing briefs.
- Add explicit `--daily` behavior for the current day's brief.
- Add a Hermes cron configuration or equivalent scheduled entry.
- Define the active-project context passed to the scorer rather than relying on an underspecified prompt.
- Decide whether scoring is intentionally one item per call or implement the planned 5–10 item batching; document the decision and test it.
- Validate that the expected input set is actually present; the reviewed workspace contained 3 reference files, not the original brief's expected 7 files / 38 unique items.

**Acceptance evidence:** CLI help exposes the supported modes; backfill and daily modes have fixture tests; the scheduled command is copy-pasteable and points at real paths; an end-to-end run records input count, unique count, scoring mode, output path, and queue result.

### P1 — Make Brainstorm Queue updates idempotent

**Why:** The current appender adds the same High-tier items every time the pipeline runs. The reviewed queue already contains duplicates from repeated offline runs.

**Work:**

1. Choose a stable deduplication key, preferably normalized wikilink plus source identity or an explicit item ID.
2. Skip entries already present in the queue.
3. Add tests for first append, repeated append, and changed-reason behavior.
4. Keep timestamps useful without making them part of the duplicate key.

**Acceptance evidence:** Running the same input twice produces zero new queue entries on the second run.

### P2 — Fix verification accounting and test-result evidence

**Why:** The persisted `test-result.json` reported `passed: 0`, `failed: 0`, and `errors: 0` even though the output showed eight passing tests. That weakens automated accountability.

**Work:**

1. Count passed tests from structured pytest output or a reliable result format.
2. Persist stdout/stderr tails and the exact working directory.
3. Make a nonzero exit code or any failed test impossible to record as `status: passed`.
4. Add a regression test for result parsing.

**Acceptance evidence:** A run with eight passing tests records `passed: 8`; a failing fixture records a failed status and nonzero/failed counts.

### P2 — Make the generated test/import contract portable

**Why:** The builder/judge feedback repeatedly found fragile or missing imports and test paths before the final workspace happened to pass. The implementation should not depend on a special current directory or ad hoc `sys.path` mutation.

**Work:**

1. Use the repository's supported `src` layout and test invocation.
2. Remove fragile path assumptions from generated tests.
3. Add an import smoke from the documented command and from a different working directory.
4. Include syntax compilation and module import checks in the builder preflight.

**Acceptance evidence:** Tests pass using the documented command from the repository root and from a separate working directory with `PYTHONPATH` set as documented.

### P3 — Clear the existing V2 lint failures

**Why:** These are small but objective quality failures in the active execution path.

**Work:**

- Remove or use `build_evidence` in `src/devflow/loop/execution.py`.
- Remove the unnecessary `f` prefix reported at line 1615.
- Re-run Ruff over the changed V2 modules.

**Acceptance evidence:** Ruff returns exit code `0` for `src/devflow/loop` and the targeted tests remain green.

### P3 — Add a clean full-loop regression fixture

**Why:** The first run mixed multiple packets, retries, verifier attempts, stale-state transitions, and a greenfield artifact. A deterministic fixture should prove the spine independently of live model variability.

**Work:**

1. Keep one fixture for a passing bounded build.
2. Keep one fixture for builder/judge cap exhaustion.
3. Keep one fixture for human review after verification.
4. Assert that failed builder/judge output cannot be represented as product completion.
5. Assert that all stage artifacts point to the same run and workspace.

**Acceptance evidence:** The fixture covers the complete state path and catches the current `running` versus `human_decision` inconsistency.

## Recommended Execution Sequence

1. Repair final-state/gate semantics and preserve judge rationale.
2. Add deterministic builder preflight and test-result accounting.
3. Complete the artifact contract: backfill, daily mode, scheduling, and queue idempotence.
4. Promote the artifact into the main checkout through an explicit reviewed step.
5. Fix Ruff errors.
6. Run the promoted artifact end-to-end, then run the clean full-loop regression fixture.

Do not treat the generated workspace as production-integrated until the P0 and P1 items have passing evidence.

## Evidence Index

- Run state: `.devflow/pipeline-runs/20260709-194406/loop-state.json`
- Execution control: `.devflow/pipeline-runs/20260709-194406/execution-control.json`
- Consolidated build/judge result: `.devflow/pipeline-runs/20260709-194406/packet-consolidated-build-judge-summary.json`
- Build manifest: `.devflow/pipeline-runs/20260709-194406/build-manifest.json`
- Persisted test result: `.devflow/pipeline-runs/20260709-194406/test-result.json`
- Full event history: `.devflow/pipeline-runs/20260709-194406/run-log.jsonl`
- Generated workspace: `.devflow/pipeline-runs/20260709-194406/workspace/`
- V2 source lint target: `src/devflow/loop/execution.py`
