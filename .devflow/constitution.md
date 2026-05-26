# devflow Constitution (MVP)

- GLOBAL RULE: Codex is the default orchestrator for all goal-driven work unless the human explicitly delegates a task to another orchestrator.
- Local models are the default bounded worker team for iterative coding, testing, repair, and summarization loops.
- Files and git are the source of truth.
- Unified diffs are the only supported patch protocol for MVP.
- Protected file changes require human approval before apply.
- Verification should run from task commands, config commands, or auto-detection.
- Reports are mandatory for every task run.
- devflow run previews by default; --yes is required to apply patches.
- devflow run must stop before mutation when the git worktree is dirty.
- Model/provider routing is post-MVP.
- Local-model output must flow through an orchestrator and the devflow safety contract before becoming repository state.
