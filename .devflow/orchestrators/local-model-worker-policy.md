# Local Model Worker Policy

Local models are worker subagents for peer orchestrators.

## Default Operating Rule (This Workspace)

For all goal-driven work, orchestration is peer-parallel with no permanent default orchestrator.

Default execution split:

- Each orchestrator (VS Code/Copilot, Codex, Antigravity) handles brainstorming, planning, research, decomposition, policy checks, and final verification decisions for its claimed tasks.
- Local qwen workers execute high-turn implementation and repair loops (coding, tests, reviewer feedback synthesis, and bounded retries).
- All repo mutations still flow through task files, unified diffs, `devflow run` gates, and reports.

Override rule:

- Human instruction can assign, transfer, or prioritize ownership of specific tasks across orchestrator lanes.
- Absent explicit reassignment, the current claiming orchestrator remains owner of its claimed tasks.

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
