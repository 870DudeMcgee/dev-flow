# Codex Goal: Stabilize devflow MVP Into a Safe Multi-Orchestrator Runner

Date: 2026-05-26
Owner: Codex Desktop
Status: ACTIVE

## Recommended `/goal`

```text
/goal Stabilize the devflow MVP into a conservative, reliable, multi-orchestrator unified-diff runner.

Outcome:
Bring the current devflow repo to a coherent MVP where Codex Desktop, VS Code/Cline, and Antigravity can each operate as independent peer orchestrators with their own local-model subagent teams, while sharing one repo, task queue, git safety model, and report protocol.

The MVP is not an LLM orchestrator yet. It is a safe execution harness for AI-generated unified diffs embedded in canonical task markdown files.

Canonical architecture:
- Shared repo + .devflow files are the coordination plane.
- Each IDE is a peer orchestrator with a complete internal dev team.
- Local models are worker subagents, not repo-state owners.
- Work is divided by claimed task, not permanent IDE role.
- Task markdown is the canonical task status source.
- plan.json mirrors task status only as best-effort index state.
- git protects rollback and recovery.

MVP CLI:
- devflow init
- devflow status
- devflow run .devflow/tasks/<task>.md
- devflow run .devflow/tasks/<task>.md --yes

Run contract:
- Without --yes, devflow validates and previews only.
- With --yes, devflow applies, verifies, reports, and updates task status.
- The git worktree must be clean before devflow mutates task/report/source state.
- Protected paths block before apply.
- Allowed Files supports exact paths, glob patterns, and ... shorthand.
- Verification commands come from task, then config, then auto-detection.
- Failed verification must rollback source changes to checkpoint state and still write FAILED task/report state afterward.

Current stabilization queue:
1. Keep docs, tests, and code aligned after every slice.
2. Keep expanding focused tests for each safety behavior.
3. Clean generated caches before final responses.

Completed stabilization behavior:
- package metadata and CLI entrypoint
- peer-orchestrator task ownership metadata
- preview-by-default run contract with `--yes` apply
- clean-worktree run guard
- glob-aware Allowed Files checks
- conservative MVP config defaults
- checkpoint-based rollback after failed verification
- best-effort plan-status mirroring

Constraints:
- Do not introduce model/provider calls into MVP execution.
- Do not reintroduce XML search/replace as active protocol.
- Do not assume fixed global IDE roles.
- Do not silently apply patches.
- Do not run on dirty worktrees.
- Do not overwrite unrelated user/agent changes.
- Keep changes small, test-driven, and easy to inspect.

Verification:
- Run: PYTHONPATH=src python3 -m unittest discover -s tests -q
- Also run targeted tests for the current slice.
- Report if pytest or editable install cannot be verified because of local toolchain issues.

Stop conditions:
- Ambiguous safety semantics around rollback, dirty worktrees, or protected files.
- Any task requires destructive git operations beyond the established checkpoint model.
- Tests fail for reasons unrelated to the current slice and need human triage.
- Another agent claims the same files/task scope.
```

## Notes

This goal supersedes fixed-role coordination assumptions. Codex may lead while assigned by the human, but the architecture remains peer orchestrator based.
