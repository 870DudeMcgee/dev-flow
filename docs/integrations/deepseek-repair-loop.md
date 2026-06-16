# DeepSeek Repair Loop

Operator-approved autonomous repair loop for Dev-Flow tasks using DeepSeek via OpenRouter.

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
