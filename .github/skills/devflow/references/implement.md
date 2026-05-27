# Devflow Implement Mode

Use this reference when the user wants the task implemented from a packet or approved plan.

Rules:

1. **NEVER implement the code or write tests directly in the cloud LLM.**
2. **DELEGATE code generation to the local qwen worker** by executing this command in the terminal:
   `PYTHONPATH=src python3 -m devflow agent implement <task_file> --profile implementer`
3. Once completed, read the generated JSON artifact from `.devflow/artifacts/<task_id>/` (e.g. `diff_result.json`).
4. Extract the proposed diff from the artifact's `diff` field and write it to Section 9 of the canonical task packet.
5. Only touch allowed files listed in the task packet.
6. Do not perform unrelated cleanup.
7. Do not change dependencies without approval.
8. Do not touch protected files without approval.
9. Run targeted verification after implementation via the `devflow run` preview step.
10. Stop if files outside allowed paths are required.
11. Report files changed, tests run, verification result, risks, and next action.