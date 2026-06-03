---
name: hermes-devflow
description: Use when Hermes Agent OS operates Dev-Flow as an external read-only chat/operator gateway.
---

# Hermes Dev-Flow Operator Skill

Hermes is an operator, chat, and scheduling layer over Dev-Flow. Hermes is not Dev-Flow's source of truth, runtime, memory layer, or orchestration brain.

## Path Authority

Josh's current canonical checkout:

```text
/Users/jewelbait/Desktop/Local AI Dev Team
```

Prohibited old checkout:

```text
/Users/jewelbait/Desktop/DevFlow
```

Never use the old path for current work. Do not assume every user's checkout folder is named `DevFlow`.

## Command Prefix

Run Dev-Flow commands from the repo root with:

```bash
PYTHONPATH=src .venv/bin/python -m devflow.cli
```

## Default Mode

Default to read-only. Dev-Flow artifacts beat Hermes memory every time.

Use these first:

- `PYTHONPATH=src .venv/bin/python -m devflow.cli status --json`
- `PYTHONPATH=src .venv/bin/python -m devflow.cli dashboard --json`
- `PYTHONPATH=src .venv/bin/python -m devflow.cli supervisor policy --json`
- `PYTHONPATH=src .venv/bin/python -m devflow.cli supervisor packet --json`
- `PYTHONPATH=src .venv/bin/python -m devflow.cli task next-action <task-id> --json`
- `PYTHONPATH=src .venv/bin/python -m devflow.cli task review <task-id> --json`

## Approved Command Groups

Read-only inspection:

- status, dashboard, supervisor policy, supervisor packet
- task list, show, log, next-action, review
- task promote-preview as non-promoting preview
- git status
- worktree list
- branch list
- knowledge list, show, search

Explicit approval required:

- knowledge capture
- task create, close, cleanup preview/apply
- task run, review-patch, patch-dry-run, apply-patch, verify

High-risk explicit approval required:

- task promote
- git commit, merge, push
- sync-main
- push-main

Forbidden:

- direct `.devflow/` mutation
- direct source edits
- direct git index, branch, remote, or promotion-state mutation
- raw destructive cleanup such as `rm -rf`
- hidden canonical state in Hermes memory
- use of `/Users/jewelbait/Desktop/DevFlow` for current work

## Response Format

Use this format for operator replies:

```markdown
## Status

## Evidence

## Risks

## Next safe action

## Command
```

## Promotion Rule

Never promote, push, merge, delete, or directly edit without explicit human approval and current Dev-Flow readiness evidence.
