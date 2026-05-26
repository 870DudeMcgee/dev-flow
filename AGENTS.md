# Devflow Agent Operating Rule

This repository uses Codex (on Mac Studio) and Google Antigravity (on Mac Mini M1 16GB - Antigravity ONLY) as default peer orchestrators for development work.

## Default Workflow

- The active orchestrator (Codex or Antigravity) owns brainstorming, planning, research, coordination, task claiming, verification review, and final handoff.
- Local Ollama coding models are the worker team for bounded implementation loops: coding drafts, test drafts, failure explanations, repair suggestions, and summaries.
- Prefer the local worker path before spending cloud-model turns on iterative code/test/repair work.
- Keep `devflow` task files, reports, and git history as the coordination surface.
- Claim a task before mutating its task file or touched-file scope when working from a goal or task file.
- Keep the worktree clean before any `devflow run` operation that mutates task/report/code state.
- All local-model output must flow back through the active orchestrator and the `devflow` safety gates; local models do not mutate repo state directly.

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
