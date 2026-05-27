# Devflow Repair Mode

Use this reference when verification or a Devflow run fails and the user wants a bounded repair.

Rules:

1. Read only the latest failure summary, current diff, and touched files.
2. Classify the failure type: syntax, import, type, assertion, lint, environment, flaky, or unknown.
3. Make the smallest possible repair.
4. Do not redesign or refactor.
5. Run targeted verification after repair.
6. Stop after the repair budget from `.devflow/config.json` is exhausted.
7. Report the failure classification, repair applied, verification result, risks, and next action.