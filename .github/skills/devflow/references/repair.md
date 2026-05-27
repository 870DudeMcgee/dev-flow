# Devflow Repair Mode

Use this reference when verification or a Devflow run fails and the user wants a bounded repair.

Rules:

1. **NEVER run repair loops or modify code directly in the cloud LLM.**
2. **DELEGATE the repair process to the local qwen repair loop worker** by executing this command in the terminal:
   `PYTHONPATH=src python3 -m devflow agent repair <task_file> --profile repair`
3. This CLI command automatically creates a git checkpoint branch, classification loops, tests, and repair retries locally.
4. Once completed, read the generated JSON artifact from `.devflow/artifacts/<task_id>/` (e.g. `repair_result.json`).
5. Extract the final verified diff from the artifact's `diff` field and write it to Section 9 of the task markdown.
6. Read only the latest failure summary, current diff, and touched files.
7. Make the smallest possible repair.
8. Do not redesign or refactor.
9. Stop after the repair budget from `.devflow/config.json` is exhausted.
10. Report the failure classification, repair applied, verification result, risks, and next action.