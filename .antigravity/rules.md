# Antigravity Rules: Devflow Software Factory

All Antigravity agents working in this repository must follow the Devflow workflow.

## Mandatory workflow

For non-trivial changes:

1. Read `AGENTS.md`.
2. Read `.devflow/workflow/DEVFLOW_WORKFLOW.md`.
3. Create or update a task packet in `.devflow/tasks/`.
4. Build minimal context.
5. Plan before editing.
6. Prefer tests first.
7. Implement minimal diff.
8. Verify.
9. Review.
10. Report.

## Agent behavior

Agents must not:
- Modify protected files without approval
- Run destructive commands
- Add dependencies without approval
- Rewrite unrelated files
- Claim verification passed unless commands were actually run

Agents must:
- Keep context small
- Use targeted searches
- Summarize long logs
- Preserve artifacts
- Stop when blocked

## References

- `AGENTS.md`
- `.devflow/workflow/DEVFLOW_WORKFLOW.md`
- `.devflow/workflow/token-policy.md`
- `.devflow/skills/devflow-software-factory/SKILL.md`
