# GitHub Copilot Instructions for DevFlow

Read `docs/DEVFLOW_SOURCE_OF_TRUTH.md` for the canonical DevFlow product direction.
Read `AGENTS.md` for repo-level agent operating rules.
This harness file is an adapter, not the source of truth.

Instruction priority:
1. Platform, system, developer, and safety instructions
2. Explicit user instructions
3. Repository instructions such as this file, `AGENTS.md`, and task-relevant skills

Operating rules:
- Prefer targeted search/read operations before opening whole files.
- Avoid ceremonial output, repeated summaries, and unnecessary restatement.
- Do not claim completion without verification evidence.
- Use one writer at a time. If another agent may be editing, stay read-only.
- Preserve worktree state. Do not delete or overwrite work to recover from confusion.
- Report conflicts, uncertainty, failed verification, and next safe action clearly.
