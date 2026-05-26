# Devflow Agent Operating Rule

This repository supports three separate, parallel peer orchestrators for development work:
1. **Codex** (Codex Desktop lane)
2. **VS Code / Copilot** (operating via IDE plugin/terminal)
3. **Google Antigravity** (operating on Mac Mini M1 16GB - Antigravity ONLY)

## Parallel Coordination Workflow

To work on multiple tasks in parallel without conflicts:
- Each orchestrator runs in its own workspace lane or physical machine and claims separate tasks in `.devflow/tasks/` using unique agent IDs and owner locks.
- Each orchestrator instantiates and controls its own virtual dev team of local model workers (via Ollama or local worker scripts) to handle high-turn coding, drafting, test repairs, and summaries.
- Prefer delegating low-level operations to the local worker dev team before spending cloud tokens.
- Coordination remains decentralized: task markdown metadata, checkpoint branches, and reports are the safety surface.
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
