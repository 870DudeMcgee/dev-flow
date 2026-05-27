# Codex Project Notes

This repository uses the **Devflow Software Factory** workflow.

Codex should follow `AGENTS.md` as the primary instruction source.

## Quick start

1. Read `AGENTS.md` at session start.
2. For non-trivial tasks, use the `devflow-software-factory` skill (`.devflow/skills/devflow-software-factory/SKILL.md`).
3. Follow **PLAN → CONTEXT → TEST → IMPLEMENT → VERIFY → REVIEW → REPORT**.

## Worktree policy

One Codex agent = one task = one worktree = one branch.

```
T-001 -> worktree devflow/T-001-agent-codex
T-002 -> worktree devflow/T-002-agent-codex
```

## Prompt starters

**Plan:**
> Use the devflow-software-factory skill. Create a task packet for this goal first. Do not edit code yet.

**Implement:**
> Use the devflow-software-factory skill. Take task T-xxx only. Use the smallest context pack. Implement minimal diff. Run targeted verification.

**Review:**
> Use the devflow-software-factory skill as reviewer. Review the current diff against task T-xxx. Be strict about scope creep, protected files, missing tests, and unverified claims.

**Repair:**
> Use the devflow-software-factory skill as repair agent. Read only the latest failure log, the current diff, and touched files. Make the smallest repair. Do not redesign.

## References

- `AGENTS.md`
- `.devflow/workflow/DEVFLOW_WORKFLOW.md`
- `.devflow/skills/devflow-software-factory/SKILL.md`
