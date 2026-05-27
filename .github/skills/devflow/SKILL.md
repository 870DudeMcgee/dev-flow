---
name: devflow
description: "Use when working on the new Dev-Flow control-room MVP: shell-worker control plane, task state, isolated workspaces, CLI, dashboard, logs, questions, results, and verification."
argument-hint: "Describe the control-room MVP task or question"
user-invocable: true
---

# Dev-Flow Control-Room MVP

Use this skill only for the new Dev-Flow product direction.

Active source of truth: `docs/control-room-mvp.md`.

Product North Star: `PRODUCT_NORTH_STAR.md`. Read it before implementation decisions and check plans against its Periodic Self-Check section.

## Rules

- Prefer direct implementation over process ceremony.
- Do not use archived legacy workflows as authority.
- Do not create legacy task files unless explicitly requested.
- Do not route work through old agent, memory, context, DAG, trace, eval, or unified-diff runner surfaces.
- Keep the first milestone focused on shell workers only.
- Verify narrowly and report what actually ran.

## First Milestone

Build a non-AI control room with these commands:

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

Acceptance test:

1. create one shell task that succeeds
2. create one shell task that fails
3. create one shell task that times out

The CLI and dashboard must show all three accurately with status and logs.

## Not Yet

- Aider
- Hermes
- OpenCode
- memory
- complex scheduling
- model routing
- PR automation
