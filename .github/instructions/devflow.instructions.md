---
applyTo: "**"
---

# Devflow Workflow Enforcement

For any non-trivial software task, use:

**PLAN → CONTEXT → TEST → IMPLEMENT → VERIFY → REVIEW → REPORT**

## Required behavior

- Minimize context.
- Prefer existing repo maps and task packets.
- State intended files before changing them.
- Keep diffs narrow.
- Avoid dependency changes.
- Avoid protected files.
- Verify before claiming success.

## Token-saving behavior

When context is needed, first request or inspect:

1. `.devflow/context/repo-map.short.md`
2. The task packet
3. Relevant tests
4. Specific implementation files
5. Latest failure logs

Never paste entire files back to the user unless asked.

## References

- `AGENTS.md`
- `.devflow/workflow/DEVFLOW_WORKFLOW.md`
- `.devflow/workflow/token-policy.md`
