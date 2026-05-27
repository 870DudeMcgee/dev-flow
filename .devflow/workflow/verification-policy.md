# Devflow Verification Policy

## Core Rule

Do not claim success without evidence.

If verification was not run, state that explicitly. Never say "tests passed" unless they were actually executed and the output confirms it.

## Red/Green/Repair Loop

For behavior changes, follow this cycle:

1. **RED** — Write or identify a failing test that captures the desired behavior. Confirm it fails.
2. **GREEN** — Implement the minimal change to make the test pass. Confirm it passes.
3. **REFACTOR** — Clean up only within the allowed paths. Confirm tests still pass.
4. **REPAIR** — If verification fails after implementation, classify the failure and apply bounded repair.

Use `devflow task transition <task> --to RED|GREEN|REFACTOR|REPORT` to track state.

## Verification Order

1. **Targeted first** — run the narrowest relevant check (single test file, single type check).
2. **Broader if warranted** — for MEDIUM/HIGH risk, run the full test suite after targeted passes.
3. **Lint/format** — run after implementation, before review.

## Failure Classification

When verification fails, classify the failure before attempting repair:

| Type | Description | Retryable | Default Budget |
|------|-------------|-----------|----------------|
| `SYNTAX_ERROR` | Parse/syntax error in changed code | Yes | 1 |
| `IMPORT_ERROR` | Missing or broken imports | Yes | 1 |
| `TYPE_ERROR` | Type checking failure | Yes | 1 |
| `TEST_FAILURE` | Assertion failure in tests | Yes | 1 |
| `LINT_FAILURE` | Linter violation | Yes | 1 |
| `PATCH_APPLY_FAILURE` | Diff could not be applied | Yes | 1 |
| `ENVIRONMENT` | Missing dependency, wrong runtime | No | 0 |
| `FLAKY` | Non-deterministic failure | No | 0 |
| `PROTECTED_FILE_TOUCHED` | Protected file changed without approval | No | 0 |
| `UNKNOWN_FAILURE` | Unclassifiable failure | No | 0 |

Retry budgets are configured in `.devflow/config.json` under `failure_taxonomy`.

## Repair Rules

1. Read only the failure output, current diff, and touched files.
2. Make the smallest possible fix.
3. Do not redesign or refactor during repair.
4. Track each repair attempt as a state transition.
5. If the budget is exhausted, stop and report the failure with classification.

## Rollback Policy

- `devflow run <task> --yes` creates a checkpoint branch before applying patches.
- If verification fails after apply, rollback to the checkpoint automatically.
- The rollback is recorded in the task report.

## Protected File Policy

Protected paths (defined in `.devflow/config.json`) require explicit human approval before modification:

- `.env`, `.env.*`, secrets, auth, payments, billing, migrations
- `.github/workflows/**`
- Lock files (`package-lock.json`, `pnpm-lock.yaml`, `yarn.lock`, `poetry.lock`)
- `requirements*.txt`, `pyproject.toml`

The `devflow run` pipeline blocks protected file changes in the diff before apply.
