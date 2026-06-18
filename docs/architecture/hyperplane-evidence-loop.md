# Hyperplane Evidence Loop

Status: Current evidence-only harness slice

Dev-Flow can optionally run Hyperplane as a task-local evaluation harness for local models and safety-critical control-room behavior.

This integration is advisory evidence only. It must not fine-tune weights, auto-route workers, edit source, apply patches, verify, promote, commit, merge, push, or update routing policy.

## Commands

```bash
devflow agent hyperplane <task_id> --suite worker-safety --target control-room --judge local-gemma4-doc-reviewer --dry-run --json
devflow agent hyperplane <task_id> --suite worker-safety --target control-room --judge local-gemma4-doc-reviewer --execute --json
devflow agent hyperplane-list <task_id> --json
devflow agent hyperplane-show <task_id> <run_id> --json
```

`hyperplane-eval>=0.1.14,<0.2` is an optional project extra. Execute mode fails closed with install guidance when the package is absent. Dry-run mode writes only a plan and does not import Hyperplane or call models.

## Artifact Contract

Each run writes under:

```text
.devflow/tasks/<task_id>/hyperplane-runs/<run_id>/
```

Required execute artifacts:

- `plan.json`
- `run.json`
- `summary.json`
- `findings.json`
- `report.md`

Optional copied Hyperplane artifacts:

- `master_report.html`
- `input_space_state*.json`

Derived model scorecards are written only under `.devflow/reports/model-scorecards/`. Proposed knowledge items remain proposed inside `summary.json`; they are not promoted to Knowledge Foundry automatically.

## Runtime Boundaries

- Default budgets are conservative: `depth=12`, `breadth=2`, one suite per command, sequential execution.
- Fast local judges default to `180s`; heavy/thinking judges default to `1800s`.
- The Dev-Flow local judge client omits forced `response_format={"type":"json_object"}` and records endpoint, model id, timeout, options, output budget, and raw failure text.
- Target and judge are separate. `control-room` is a Dev-Flow callable target. Local model profile targets are supported as evidence-only targets, but self-grading is refused unless `--allow-self-grading` is explicit.
- Execute mode requires worker-safe Git state before Hyperplane or model calls.

## First Suites

- `worker-safety`: destructive shell commands, privilege escalation, curl-pipe-shell, `rm --force`, and `shred`.
- `patch-compliance`: proposal-only output and no false mutation, test, verification, or promotion claims.
- `grounded-summary`: task id/title/status grounding and missing-evidence honesty.
- `uncertainty-refusal`: clear blocking questions or refusals for unsafe or underspecified requests.

Findings classify into exactly:

- `prompt_fix_candidate`
- `policy_gap`
- `test_case_candidate`
- `model_limitation`
- `harness_issue`
