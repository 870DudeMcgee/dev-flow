---
name: devflow
description: "Use when working on the DevFlow product-building loop."
argument-hint: "Describe the DevFlow task or question"
user-invocable: true
---

# DevFlow Product-Building Loop

Read `AGENTS.md`, then `docs/DEVFLOW_SOURCE_OF_TRUTH.md`. Those files outrank
this adapter. Do not use archived/generated handoffs as product authority.

DevFlow turns rough ideas into verified product implementations:

```text
Idea -> Brainstorm -> Spec -> Plan -> Planning Judge -> Build -> Build Judge -> Verify -> Next human decision
```

## Model And Machine Contract

- DevFlow is model-agnostic and machine-agnostic; no fixed fleet is the product.
- The seven roles may use any qualified eligible model through per-run overrides,
  deployment profiles, or automatic routing.
- Local models are host-specific. M4 Studio and M1 Mini local models are not
  interchangeable merely because both machines share the repository.
- Free-cloud and included-subscription models may be mixed with local models.
- Profiles are preference templates, not hardware discovery or fixed architecture.
- Host resources, registry eligibility, live endpoint identity, and role-audition
  evidence are different facts. Use all of them before recommending a profile.
- Never silently download, start, promote, or reassign a model. Present the
  closest proven profile/model recommendation for operator approval.

The exact profile catalog, current registry orientation, discovery mechanisms,
and known gaps live only in `docs/DEVFLOW_SOURCE_OF_TRUTH.md`.

## Current Runtime Surface

```bash
PYTHONPATH=src .venv/bin/python -m devflow.cli status serve
PYTHONPATH=src .venv/bin/python -m devflow.cli loop spine-fixture --json
```

The browser is both a brainstorm chat and live status/evidence surface. Hermes
is the messaging, tool, and bounded-worker orchestration harness. DevFlow owns
persisted pipeline state, evidence, verification, and the next human decision.

## Rules

- Orient from current source, configs, tests, and live evidence.
- Do not restore retired commands, compatibility shims, or historical UI flows.
- Do not treat a configured model as live or a live model as role-qualified.
- Do not claim a profile is offline when it contains cloud/subscription roles.
- Keep edits scoped and verify with real commands.
- Do not commit, merge, push, publish, or promote without explicit approval.
