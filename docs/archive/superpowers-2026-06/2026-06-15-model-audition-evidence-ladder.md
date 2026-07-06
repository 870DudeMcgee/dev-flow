# Model Audition Evidence Ladder Plan

Status: active implementation plan. Dry-run planning, explicit sequential execute, and deterministic advisory scoring are implemented.

## Goal

Build a read-only model audition workflow so Dev-Flow can compare one to three local models for a job type and preserve the result as advisory evidence without enabling autonomous routing.

## Constraints

- Keep control-room implementation in `src/devflow/control_room/`.
- Reuse `devflow agent discover-local --json`, the agent registry, `run_local_model_profile`, and WorkerEvidence.
- Do not create a parallel model registry or benchmark harness.
- Do not let auditions edit source, write `proposal.patch`, apply patches, verify, promote, commit, merge, push, or call remote provider APIs.
- Cap default candidates at three.

## Slice 1: Dry-Run Planning

Implemented command:

```bash
devflow agent audition <task_id> --job review-debug --dry-run --json
```

Acceptance:

- Unknown job types fail clearly and list valid job types.
- Dry-run selects only installed, enabled, read-only local worker-pool profiles.
- Patch-capable or workspace-writing profiles are rejected with reasons.
- Candidate count is capped at three.
- The command writes `.devflow/tasks/<task_id>/model-auditions/dry-run-<job_type>/plan.json`.
- The command does not call models, edit source, write `proposal.patch`, apply patches, verify, promote, commit, merge, or push.

## Slice 2: Explicit Sequential Execute

Implemented command:

```bash
devflow agent audition <task_id> --job review-debug --execute --json
```

Acceptance:

- Refuse unsafe Git/Dev-Flow state before worker writes.
- Read the existing dry-run plan or create a fresh plan.
- Run selected candidates sequentially through `run_local_model_profile`.
- Preserve each model run under existing `local-model-runs`.
- Write audition-level `runs.json`.
- Stop on local model client failures without mutating task canonical state.

## Slice 3: Scorecard And Report

Implemented artifacts:

```text
.devflow/tasks/<task_id>/model-auditions/<audition_id>/
  scorecard.json
  report.md
```

Acceptance:

- Deterministic scoring ranks grounded, contract-following output above generic or hallucinated output.
- Scorecard names missing evidence instead of inferring it.
- Report is human-readable and advisory only.
- No routing policy is updated automatically.

## Tests

Current focused tests live in `tests/test_model_audition.py`:

- dry-run writes plan without model calls
- unknown job type lists valid job types
- unsafe patch-capable profile is rejected
- `--execute` runs selected candidates through mocked `run_local_model_profile` and writes `runs.json`, `scorecard.json`, and `report.md`
- unsafe Git state refuses before model calls
- deterministic dogfood case `model-audition-evidence` proves dry-run, execute, scoring, report artifacts, and no provider/source mutation using fixture WorkerEvidence
