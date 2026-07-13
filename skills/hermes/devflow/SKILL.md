---
name: hermes-devflow
description: Use when Hermes operates the current DevFlow loop.
---

# Hermes DevFlow Operator Skill

Read `<repo-root>/AGENTS.md` and
`<repo-root>/docs/DEVFLOW_SOURCE_OF_TRUTH.md` first. DevFlow artifacts and live
source/config evidence outrank Hermes memory and this adapter.

## Ownership

- **DevFlow:** persisted pipeline state, stage artifacts, evidence, verification,
  model-role routing contracts, and the next human decision.
- **Hermes:** chat/messaging, tools, bounded worker orchestration, and one of the
  brainstorm entry surfaces.
- **Browser:** brainstorm chat plus live pipeline status/evidence.
- **Operator:** model/profile choice, approval, taste, and final decisions.

## Model And Machine Discipline

DevFlow is model-agnostic and machine-agnostic. Never assume a fixed fleet.
Resolve the active profile and registry, then distinguish:

1. host resources and plausible local capacity;
2. local models configured for this host;
3. the model actually resident at an endpoint (`/health`, `/v1/models`);
4. roles proven by audition evidence;
5. cloud/free and Hermes-subscription targets currently available.

M4 Studio local models do not exist on the M1 Mini unless separately installed
and qualified. Cloud and subscription models can be shared across machines when
the required credential/OAuth is configured. Recommend the closest proven
profile and compatible local models, but do not silently download, start,
promote, or reassign anything.

See the source-of-truth sections **Model Routing & Operating Modes** and
**Machine Agnosticism And Capability Discovery** for exact profiles, current
registry orientation, and implementation gaps.

## Current Command Surface

Run from `<repo-root>`:

```bash
PYTHONPATH=src .venv/bin/python -m devflow.cli status serve
PYTHONPATH=src .venv/bin/python -m devflow.cli loop spine-fixture --json
```

Do not recommend removed commands such as `dashboard`, `supervisor`, `project`,
`task`, `knowledge`, `sync-main`, or `push-main`; they are not present in the
current V2 CLI.

## Safety

- Default to read-only inspection.
- Never mutate `.devflow/` state directly.
- Never start a local model blindly; inspect the approved fleet manager and live
  endpoint identity first.
- Never promote, commit, merge, push, delete, or publish without explicit human
  approval and current verification evidence.
- Report actual routed model identity and fallback use; never imply a model was
  selected when the surface does not expose that control.

## Response Shape

```markdown
## Status
## Evidence
## Risks
## Next safe action
```
