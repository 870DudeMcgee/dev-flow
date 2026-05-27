# GitHub Copilot Instructions

This repository uses the **Devflow Software Factory** workflow.

Before making non-trivial code changes:

1. Read `AGENTS.md`.
2. Follow `.devflow/workflow/DEVFLOW_WORKFLOW.md` if the task involves code, tests, refactors, architecture, or bug fixes.
3. Use the smallest sufficient context.
4. Do not scan the entire repository unless the task requires architecture-level analysis.
5. Prefer task packets in `.devflow/tasks/`.
6. Prefer red/green/repair for behavior changes.
7. Emit minimal diffs.
8. Run or request verification.
9. Finish with a report.

Do not perform unrelated cleanup.
Do not change protected files without explicit user approval.
Do not claim tests passed unless they were actually run.
