# Subagent Rehab

Use subagents only when work can be isolated cleanly. Do not parallelize agents that touch the same files in one worktree.

## Roles

- Graph scout: selects candidates from Graphify evidence and source inspection.
- Ponytail reviewer: rejects fake seams, broad rewrites, and one-adapter abstractions.
- Implementation worker: changes one safe slice with tests.
- Graph delta reviewer: refreshes scorecards and checks generated files stay ignored.
- Final synthesizer: merges evidence into a concise handoff.

Templates live in [prompts/](prompts/).

## Worktree Rules

- Use isolated worktrees for parallel implementation.
- Serialize slices that touch the same source or test files.
- Never resolve merge conflicts by guessing. Hand off the conflict and the competing intent.
- Do not run promotion, push, PR, or publish commands without explicit human approval.
- Keep generated `graphify-out/` files out of commits.

## Review Gates

Before accepting an implementation worker result:

1. Focused tests pass.
2. Scorecard freshness passes.
3. The diff deletes or concentrates complexity.
4. No new one-adapter seam appears.
5. Handoff includes files changed, verification, risks, and next safe action.

If any gate fails, inject a correction into the loop or stop for review.
