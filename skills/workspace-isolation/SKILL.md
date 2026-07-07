---
name: workspace-isolation
description: Use when working inside a multi-agent project, assigned workspace, or Dev-Flow task — prevents worker writes outside assigned boundaries
---

# Workspace Isolation

## Overview

Parallel work is only safe when workers cannot damage each other's work. Every task should have clear ownership boundaries.

**Core principle:** Stay in your lane. If a file isn't in your scope, don't touch it.

**Violating the letter of this rule is violating the spirit of this rule.**

## The Iron Law

```
NO WRITES OUTSIDE ASSIGNED WORKSPACE
```

If you haven't confirmed the file is in your assigned scope, you cannot edit it.

## When to Use

**Activates automatically when:**
- `.devflow/` directory exists in the project
- You are assigned a task workspace
- Multiple agents are working on the same project
- You are working in a git worktree

**Also use when:**
- Contributing to any shared repository
- Working alongside other developers or agents
- Any situation where concurrent edits could conflict

## The Process

```
BEFORE any file edit:

1. CHECK: Am I in my assigned workspace?
2. VERIFY: Is this file within my allowed scope?
3. IF NO: Escalate to the coordinator. Do not touch the file.
4. IF YES: Proceed with the edit.
```

## Boundary Rules

- Never edit files in the main checkout from a worker workspace
- Never edit files assigned to another worker
- Never edit protected paths unless explicitly authorized:
  - `AGENTS.md`
  - `docs/DEVFLOW_SOURCE_OF_TRUTH.md`
  - `README.md` (at project root)
  - Configuration files (`.gitignore`, `pyproject.toml`, etc.)
- If you need something outside scope → report the need, don't touch the file
- If you find a bug outside scope → file a finding in your report, don't fix it

## Rationalization Prevention

| Excuse | Reality |
|--------|---------|
| "Quick fix to this other file" | Not your file. Report it. |
| "It's a one-line change" | One line in the wrong file = merge conflict. |
| "Nobody else is editing this" | You don't know that. Stay in scope. |
| "I need to fix the root cause" | File a finding. Don't cross boundaries. |
| "It'll save time" | Conflicts waste more time than reporting. |
| "The coordinator won't mind" | Ask. Don't assume. |

## Red Flags — STOP

- About to edit a file outside your workspace
- About to commit to main/master from a task workspace
- About to modify a file you didn't create and isn't in your scope
- About to delete or rename files outside your workspace
- About to modify a protected path without explicit authorization

**All of these mean: STOP. Report the need. Don't touch it.**

## Dev-Flow Integration

When `.devflow/` exists:

- Your workspace is `/.devflow/workspaces/<task_id>/`
- `task.yaml` defines your scope and boundaries
- All edits must stay within the workspace directory
- Results are promoted through Dev-Flow's review/merge process
- Never write directly to the main checkout

## Integration

- Works with `devmode:using-git-worktrees` for workspace creation
- Works with `devmode:worker-handoff` for boundary communication
- Works with `devmode:finishing-a-development-branch` for safe promotion

## Verification

Before completing work:
- Confirm all changed files are within your assigned scope
- `git diff --name-only` should show only files in your workspace
- No files outside your workspace were modified

## The Bottom Line

**Your workspace is your sandbox. Everything inside is yours. Everything outside is not.**

If you need something outside, communicate. Don't reach.
