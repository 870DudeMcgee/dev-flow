# Devflow Implement Mode

Use this reference when the user wants the task implemented from a packet or approved plan.

Rules:

1. Only touch allowed files listed in the task packet.
2. Emit minimal diffs.
3. Do not perform unrelated cleanup.
4. Do not change dependencies without approval.
5. Do not touch protected files without approval.
6. Run targeted verification after implementation.
7. Stop if files outside allowed paths are required.
8. Report files changed, tests run, verification result, risks, and next action.