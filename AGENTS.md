# Dev-Flow Agent Operating Rule

This repository is being rebuilt into a simpler product: a local-first control room for parallel AI coding workers.

Do not use the archived legacy workflow as process authority. Do not require old task files, claim rituals, staged ceremonies, local-model delegation, memory, DAGs, traces, or old patch gates before doing ordinary work.

## Active Rule

Prefer direct implementation with small, verifiable changes.

Before code changes:

1. Read [PRODUCT_NORTH_STAR.md](PRODUCT_NORTH_STAR.md) and check the plan against its Periodic Self-Check section.
2. Read [docs/control-room-mvp.md](docs/control-room-mvp.md).
3. Read [docs/token-optimization.md](docs/token-optimization.md) and invoke [skills/token-optimization/SKILL.md](skills/token-optimization/SKILL.md) to route active context, search, and transcript policies.
4. Inspect only the smallest relevant implementation files.
5. Preserve useful code that supports the control-room MVP.
6. Bypass old workflow machinery that conflicts with the MVP.
7. Keep changes focused and verify them.

## Current Product Target

Dev-Flow owns:

- tasks
- isolated workspaces
- locks and ownership
- status
- questions
- logs
- reports
- verification
- merge readiness

Workers are replaceable. The first milestone supports shell workers only.

## First Milestone Commands

```bash
devflow init
devflow doctor
devflow task create "title"
devflow task list
devflow task show <task_id>
devflow task run <task_id> --worker shell -- <command>
devflow dashboard
```

Do not implement Aider, Hermes, OpenCode, memory, complex scheduling, or model routing until the shell-worker control room passes the acceptance gauntlet.

## Archived Material

Legacy workflow docs live under [docs/archive/legacy-devflow-software-factory-2026-05-27](docs/archive/legacy-devflow-software-factory-2026-05-27). Read them only as historical notes or salvage references.
