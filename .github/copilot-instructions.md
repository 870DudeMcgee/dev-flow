# GitHub Copilot Instructions

This repository is being rebuilt into a simpler product: a local-first control room for parallel AI coding workers.

Do not use the archived legacy workflow as the process authority for this rebuild.

## Active Source Of Truth

Start from [AGENTS.md](../AGENTS.md) for the repo-level operating rule.

Read [PRODUCT_NORTH_STAR.md](../PRODUCT_NORTH_STAR.md) before implementation decisions and check your plan against its Periodic Self-Check section. If a proposed change does not move Dev-Flow toward the North Star, do not implement it.

Read [docs/control-room-mvp.md](../docs/control-room-mvp.md) before non-trivial code changes.

Use [skills/token-optimization/SKILL.md](../skills/token-optimization/SKILL.md) to activate token-optimization mode and load only the relevant subskills for the current role.

## Working Rules

- Prefer direct implementation over ceremonial workflow.
- Use concise, technical, action-oriented output.
- Do not restate project background unless asked.
- Search before reading large files.
- Summarize command output before expanding into logs.
- Preserve exact commands, failures, test counts, commit hashes, and git status.
- Respect one-writer-at-a-time; if writer/reviewer role is unclear, ask before editing.
- Do not create legacy `.devflow/tasks/*.md` task files unless the user explicitly asks.
- Do not follow archived staged-workflow rituals.
- Do not delegate implementation to old local-model agent commands.
- Preserve useful code only when it supports the new control-room MVP.
- Keep unrelated dirty worktree changes intact.
- Verify with the narrowest useful command and report what actually ran.

## First Milestone

Implement a non-AI control room with shell workers only.

Required commands:

```bash
devflow init
devflow doctor
devflow task create "title"
devflow task list
devflow task show <task_id>
devflow task run <task_id> --worker shell -- <command>
devflow task verify <task_id> -- <command>
devflow dashboard
```

Do not implement Aider, Hermes, OpenCode, memory, complex scheduling, or model routing yet.
