# DeepSeek Repair Loop

Operator-approved autonomous repair loop for Dev-Flow tasks using DeepSeek via OpenRouter. The loop is driven by a recurring Hermes cron job (`9ff249f1186d`) that runs every 15 minutes by default. Each run performs at most one bounded repair task.

## Script

`/Users/jewelbait/.hermes/scripts/devflow_repair_loop.sh`

## Lock

`.devflow/locks/deepseek-repair-loop.lock`

Prevents concurrent repair loop runs.

## Kill Switches

- `.devflow/disable-deepseek-repair-loop`
- `.devflow/locks/disable-deepseek-repair-loop`

Either file existing disables the repair loop entirely.

## Evidence Directory

`.devflow/reports/hermes-deepseek-repair-runs`

Stores per-run evidence artifacts.

## OpenRouter Key Loading

The script loads the OpenRouter API key from the Hermes environment. Secrets are never logged.

## Target Selection

The cron job selects a repair target using the following precedence:

1. **Explicit title** – If the environment variable `DEVFLOW_REPAIR_TITLE` is set, its value is used as the task title.
2. **Request file** – If `DEVFLOW_REPAIR_TITLE` is not set, the job reads `/Users/jewelbait/.hermes/devflow_repair_request.txt`. If the file is present and non-empty, its content is consumed as the task title and the file is removed.
3. **Advisory-derived** – If neither an explicit title nor a request file is available, the job consults the advisory. A repair run proceeds only when the advisory includes an exact `devflow task create` target. Otherwise the cron run skips after recording evidence.

## One-Task Flow

For each repair attempt, the loop executes exactly one task through these gates:

1. **advisory** – Load task context and constraints.
2. **task create** – Create the repair task in Dev-Flow.
3. **propose-patch** – Generate a candidate patch.
4. **review-patch** – Human or automated review gate.
5. **patch-dry-run** – Validate patch applies cleanly.
6. **apply-patch** – Apply the approved patch.
7. **verify** – Run verification checks.
8. **promote** – Promote verified changes.
9. **checkpoint** – Record state for recovery.
10. **push** – Push changes to remote.

## Safety

- Lock file prevents overlapping runs.
- Kill switches allow immediate operator disable.
- Secrets are never written to logs or evidence.
- Each task flows through the full gate sequence; no gate is skipped.
- Malformed patch hunks are rejected before apply so dry-run and apply gates stay aligned.

## Failed Probe Cleanup

When a repair probe task fails (e.g., a patch cannot be generated, review rejects the change, or verification fails), the failed task remains in the task list and can pollute advisory context for subsequent repair runs. To prevent this, operators should close failed probe tasks after a later successful repair has been promoted:

```bash
devflow task close <task-id> --outcome rejected --reason "superseded by <successful-task-id>"
```
Closing as `rejected` removes the stale probe from the active task set and keeps the advisory clean. The `--reason` text should include `superseded by <successful-task-id>` when a newer successful task replaces the failed probe. This cleanup step is separate from the one-task repair loop; the cron loop itself must still run at most one bounded repair task per tick. Pruning or bulk cleanup of old tasks remains an independent operation outside the repair loop.
