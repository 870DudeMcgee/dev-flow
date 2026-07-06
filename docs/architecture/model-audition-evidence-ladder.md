# Model Audition Evidence Ladder

Status: active architecture for read-only audition planning, explicit sequential local execution, and deterministic advisory scoring.

## Purpose

Dev-Flow needs a lightweight way to compare a few local models for a job type without turning model choice into autonomous routing. The Model Audition Evidence Ladder records which local profiles would be tried, why they are eligible, and where later run/score evidence would live.

This helps separate two failures:

- Dev-Flow control-room bug
- wrong local model for this job type

Auditions are advisory evidence. They do not edit source, apply patches, verify, promote, commit, merge, push, update routing policy, or call remote provider APIs.

For current local-worker sessions, use [docs/local-worker-policy.md](../local-worker-policy.md):
local workers are opt-in, Qwen 3.6 27B Q5 MTP is the normal single lane, Codex
uses a visible `qwen36_27b_mtp_coder` subagent spawn, and Hermes uses
`hermes-qwen-mtp` as the same-lane MCP packet wrapper. Audition candidates are
comparison evidence only.

## Public Interface

Dry-run planning:

```bash
devflow agent audition <task_id> --job review-debug --dry-run --json
```

Explicit sequential execution:

```bash
devflow agent audition <task_id> --job review-debug --execute --json
```

`--dry-run` selects installed, policy-safe local worker-pool profiles and writes a plan artifact. It does not call models.

`--execute` requires worker-safe Git state, reads the existing dry-run plan or creates a fresh one, then runs selected candidates sequentially through the existing local worker-pool boundary. It writes derived audition artifacts while preserving each model's WorkerEvidence under `local-model-runs`.

## Job Types And Candidate Sets

Each job type has at most three comparison candidates. Candidate names are
stable job-facing aliases; each alias resolves to a current agent-registry
profile when installed and policy-safe.

| Job type | Candidate aliases | Legacy comparison profiles |
| --- | --- | --- |
| `planning` | `local-planner`, `local-planner-64k`, `local-fast` | `hermes-qwen36-27b-q5-mtp`, `local-gemma4-qat` |
| `small-code` | `local-coder-medium`, `local-code-fallback` | `local-qwen25-coder-14b`, `local-gemma4-qat` |
| `hard-code` | `local-coder-medium`, `local-long-reviewer` | `local-qwen25-coder-14b`, `local-gemma4-qat` |
| `review-debug` | `local-reviewer-deep`, `local-code-reviewer` | `local-gemma4-qat`, `local-qwen25-coder-14b` |
| `summary-status` | `local-worker-fast`, `local-long-summary` | `hermes-qwen36-27b-q5-mtp`, `local-gemma4-qat` |

These candidates are audition evidence only. They are not automatic routing
policy and do not supersede the opt-in visible Codex `qwen36_27b_mtp_coder`
local-worker policy.

Eligibility requires:

- installed local Ollama model from `devflow agent discover-local --json`
- enabled registry profile
- read-only local model worker-pool permission surface
- no workspace writes
- no `proposal.patch` writes
- no promotion, Git, verification, shell, or arbitrary network authority

## Artifact Layout

Audition evidence is task-local derived evidence:

```text
.devflow/tasks/<task_id>/model-auditions/<audition_id>/
  plan.json
  runs.json
  scorecard.json
  report.md
```

Dry-run writes:

```text
.devflow/tasks/<task_id>/model-auditions/dry-run-<job_type>/plan.json
```

The plan records the task id/title/status, job type, installed local models, selected candidates, rejected candidates with reasons, mutation refusals, and expected worker-pool commands.

Execute writes:

```text
.devflow/tasks/<task_id>/model-auditions/execute-<job_type>/
  plan.json
  runs.json
  scorecard.json
  report.md
```

`runs.json` references the WorkerEvidence paths created by `run_local_model_profile`. `scorecard.json` is deterministic advisory evidence. `report.md` is a compact human-readable summary.

## Scoring Ladder

The scoring version ranks model outputs with deterministic checks before any subjective judgment:

- exact task id/title/status grounding
- required sections present
- no false claims of edits, verification, commits, promotion, merge, or push
- concrete next Dev-Flow action
- grounded in packet evidence
- missing evidence named instead of hallucinated
- latency/resource class recorded from the registry
- estimated human rework: `low`, `medium`, or `high`

Scores are advisory. They must not update routing policy automatically.

## Non-Goals

- autonomous routing
- provider-backed execution
- remote API calls
- patch application
- source or workspace edits
- verification, promotion, commit, merge, or push
- a second model registry
- a benchmark harness separate from Dev-Flow task evidence

## Next Implementation Slice

The next slice may deepen scoring with richer evidence categories or add opt-in execution controls such as `--max-candidates`, but the default cap stays three and results remain advisory evidence only.

## Dogfood

The production-readiness dogfood suite includes `model-audition-evidence`. It uses fixture local discovery and WorkerEvidence to prove dry-run, execute, scoring, and report artifacts without calling real models or providers.
