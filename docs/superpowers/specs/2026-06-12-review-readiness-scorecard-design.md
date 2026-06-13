# Review Readiness Scorecard Design

Date: 2026-06-12
Status: Implemented; awaiting checkpoint once unrelated dirty work is resolved

## Purpose

Dev-Flow already has the control-loop pieces for verification and review readiness: task status projections, promotion readiness checks, review capsules, freshness verification batches, and bounded verification execution. The next milestone should not add autonomous routing or a second loop engine. It should add one read-only readiness projection that answers: "Which tasks are ready for human review, which are not, and what is the safest next command?"

This milestone supports the agent-loop strategy by making review readiness an explicit control-room signal. Dev-Flow remains the state, evidence, verification, and promotion authority. Workers do not self-certify readiness, and the loop does not promote work.

## Scope

Implement a derived `ReviewReadinessProjection` for active tasks. The projection is read-only and must not run verification, create promotion previews, render or export review capsules, apply patches, promote, close, or mutate task state.

The projection should classify each task into one deterministic `review_state`:

- `ready_for_review`: verification passed and promotion preview evidence is available enough for a human to inspect with a review capsule.
- `needs_verification`: worker output or completion evidence exists, but verification has not passed.
- `verification_failed`: latest verification failed and needs inspection or repair.
- `needs_promotion_preview`: verification passed, but promotion preview evidence is missing or unavailable.
- `blocked`: task is blocked or awaiting human input.
- `worker_failed`: worker failed before reviewable output.
- `running`: task is still running or in progress.
- `not_ready`: no safer review action is inferred yet.

Each projection should include:

- `score`: a simple deterministic 0-100 sorting value, not an approval grade.
- `blockers`: concrete reasons preventing human review.
- `evidence`: relevant paths such as `task.yaml`, `verification.json`, `promotion-preview.json`, worker logs, verification logs, and result files when available.
- `next_command`: the safest exact command, such as `devflow task verify ...`, `devflow task promote-preview ...`, `devflow task capsule ...`, or `devflow task show ...`.

## Surfaces

Expose the scorecard through three small surfaces:

1. `devflow task review-ready [<task_id>] --json`
   - Read-only task-level or all-task readiness output.
   - Useful for CLI debugging, tests, and future loop consumers.

2. `devflow freshness loop`
   - Add aggregate counts such as `ready_for_review_count`, `needs_verification_count`, and `review_blocked_count`.
   - Do not alter verification batch projection or dispatch behavior.

3. Operating-layer snapshot
   - Include review readiness state, blockers, score, and next command in existing task/action surfaces.
   - The local UI can then show "ready for review" as a first-class lane without adding new mutation powers.

Review capsule rendering stays explicit. A ready task should point to `devflow task capsule <task_id>` rather than creating a capsule automatically.

## Implementation Shape

Add a narrow `src/devflow/control_room/review_readiness.py` module. It should reuse existing logic instead of creating a parallel readiness model:

- `build_task_status_projection` for task status, verification state, logs, manual-agent evidence, and next-action context.
- `promotion_readiness_errors` for promotion readiness blockers.
- Existing promotion-preview loading rules or a small shared helper so CLI, capsules, and readiness do not drift.

The command layer should call the projection and serialize stable JSON. Freshness and operating-layer code should consume the same projection instead of duplicating classification rules.

## Data Flow

```text
task.yaml + verification.json + promotion-preview.json + logs/result evidence
-> TaskStatusProjection
-> ReviewReadinessProjection
-> task review-ready CLI
-> freshness aggregate counts
-> operating-layer snapshot fields
```

No canonical task state changes during this flow. Any generated output is command output or derived snapshot data only.

## Error Handling

Unreadable or malformed evidence should not crash the scorecard unless the target task itself cannot be loaded. Instead, classify the task as not ready or blocked with a concrete blocker such as "verification.json is invalid JSON" or "promotion preview is missing".

Path handling must preserve existing safety rules. Evidence paths should be project-relative when possible, and unsafe workspace or changed-file paths should not be opened by the readiness projection.

## Tests

Focused tests should cover:

- Verified task with passed verification and promotion preview available returns `ready_for_review` with next command `devflow task capsule <task_id>`.
- Complete or manual-result task without passed verification returns `needs_verification`.
- Failed verification returns `verification_failed`.
- Verified task without promotion preview returns `needs_promotion_preview`.
- Blocked, worker-failed, and running tasks return non-review states.
- Freshness aggregate counts match projected task states.
- `devflow task review-ready` is read-only and creates no files.

## Non-Goals

- No autonomous routing.
- No automatic verification execution.
- No automatic promotion-preview generation.
- No automatic review-capsule export.
- No promotion, push, merge, PR automation, or hidden approval.
- No new worker runtime or model adapter.

## Approval

The design was discussed and approved interactively on 2026-06-12, then implemented as the shared review-readiness projection, `devflow task review-ready`, freshness aggregate counts, and operating-layer task fields. Final checkpointing remains separate from implementation because this checkout also contains unrelated dirty work from another session.
