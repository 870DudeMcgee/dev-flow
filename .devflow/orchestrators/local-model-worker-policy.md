# Local Model Worker Policy

Local models are worker subagents for peer orchestrators.

## Default Operating Rule (This Workspace)

For all goal-driven work, Codex is the default orchestrator lane unless the human explicitly assigns a different orchestrator for a specific task.

Default execution split:

- Codex orchestrates brainstorming, planning, research, decomposition, policy checks, and final verification decisions.
- Local qwen workers execute high-turn implementation and repair loops (coding, tests, reviewer feedback synthesis, and bounded retries).
- All repo mutations still flow through task files, unified diffs, `devflow run` gates, and reports.

Override rule:

- Human instruction can temporarily delegate orchestration of a specific task to VS Code/Copilot or Antigravity.
- Absent explicit delegation, stay in Codex-orchestrated mode.

They may help with:

- patch drafting
- test generation
- failure explanation
- small repair loops
- summarization

They must not mutate repo state directly.

All local-model outputs should flow back through an orchestrator, then through task files, unified diffs, verification, and reports.

Current preferred endpoint:

- http://127.0.0.1:11434

Candidate models:

- qwen2.5-coder:1.5b
- qwen2.5-coder:7b-instruct (fast fallback for constrained 16 GB machines)
- qwen2.5-coder:14b (preferred coding worker for Mac mini M1 16 GB)
- qwen2.5-coder:32b-instruct
