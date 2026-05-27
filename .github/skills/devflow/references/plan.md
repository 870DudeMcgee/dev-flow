# Devflow Plan Mode

Use this reference when the user wants Devflow planning or when the task is not yet ready for implementation.

Given the user's goal, produce a minimal implementation plan.

Return:

1. Task classification: trivial, bug fix, feature, refactor, test, docs, investigation, or high-risk.
2. Proposed task packet.
3. Allowed files.
4. Context needed.
5. Tests to add or run.
6. Risk tier: LOW, MEDIUM, or HIGH.
7. Verification command.
8. Smallest next action.

Do not write code in plan mode.