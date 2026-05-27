# Devflow Agent Operating Rule

This repository uses the **Devflow Software Factory** workflow.

Before modifying code, you MUST follow this sequence:

1. Understand the task.
2. Identify the smallest relevant context.
3. Create or update a `.devflow/tasks/<task-id>.md` task packet unless the user explicitly requests a trivial one-shot edit.
4. State the planned files and verification command before implementation.
5. Prefer tests first for behavior changes.
6. Emit minimal diffs only.
7. Never modify files outside the task's allowed path list.
8. Run or request verification before declaring success.
9. Write a short completion report with: files changed, tests run, risks, follow-up tasks.

For details, read:
- `.devflow/workflow/DEVFLOW_WORKFLOW.md`
- `.devflow/workflow/token-policy.md`
- `.devflow/skills/devflow-software-factory/SKILL.md`

Follow **PLAN → CONTEXT → TEST → IMPLEMENT → VERIFY → REVIEW → REPORT**.

## Token Policy

Use the smallest sufficient context.

Do not read the whole repository unless the task explicitly requires architectural analysis.

Prefer:
- File tree summaries
- Ripgrep results
- Specific files named by the task
- Existing tests near the target code
- `.devflow/context/repo-map.short.md` when available

Avoid:
- Restating long files
- Pasting full logs when a summary is enough
- Broad rewrites
- Speculative refactors
- Unrelated cleanup

## Safety Policy

All code changes are untrusted proposals until validated.

Do not claim completion unless one of these is true:
- Verification passed, or
- The user explicitly accepted an unverified change, or
- You clearly state verification could not be run.

Protected files require explicit user approval:
- Lock files
- CI/CD files
- Credentials or secret handling
- Deployment configuration
- Destructive filesystem operations
- Authentication or authorization code

## Parallel Coordination

This repository supports three separate, parallel peer orchestrators:
1. **Codex** (Codex Desktop lane)
2. **VS Code / Copilot** (operating via IDE plugin/terminal)
3. **Google Antigravity** (operating on Mac Mini M1 16GB — Antigravity ONLY)

Coordination rules:
- Each orchestrator runs in its own workspace lane and claims separate tasks in `.devflow/tasks/` using unique agent IDs and owner locks.
- Each orchestrator instantiates and controls its own virtual dev team of local model workers (via Ollama) to handle high-turn coding, drafting, test repairs, and summaries.
- Prefer delegating low-level operations to local workers before spending cloud tokens.
- Coordination is decentralized: task markdown metadata, checkpoint branches, and reports are the safety surface.
- Claiming a task is strictly required before mutating its fenced diff block or touched files.
- The git worktree must be clean before running `devflow` status transitions.
- All local-model worker suggestions must flow back through the owning peer orchestrator and be validated by `devflow` safety gates before code mutation.

## Local Worker Defaults

- Preferred endpoint: `http://127.0.0.1:11434`
- Preferred Mac mini M1 16 GB worker profile: `mini`
- Preferred coding worker model: `qwen2.5-coder:14b`
- Fast fallback profile: `mini-fast`
- Fast fallback model: `qwen2.5-coder:7b-instruct`

## Goal Work

For any user goal, the active orchestrator should:

1. Brainstorm and shape the goal.
2. Create or update a `devflow` plan/task when the work has multiple steps or code changes.
3. Delegate bounded coding/testing/review loops to local workers where useful.
4. Apply changes through normal repo edits or `devflow run` safety gates, depending on task shape.
5. Verify locally before reporting completion.
