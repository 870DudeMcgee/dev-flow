---
name: devflow
description: "Use when working on the DevFlow product-building loop."
argument-hint: "Describe the DevFlow task or question"
user-invocable: true
---

# DevFlow Product-Building Loop

Use this skill only for the current DevFlow product direction.

Active source of truth: `docs/DEVFLOW_SOURCE_OF_TRUTH.md`.

DevFlow is the local operating layer for turning rough ideas into verified product implementations. Obsidian owns broad knowledge/context; DevFlow owns the active product-building loop.

## Rules

- Prefer direct implementation over process ceremony.
- Do not use quarantined, deleted, or archived legacy workflows as authority.
- Do not create legacy task files unless explicitly requested.
- Do not route work through old agent, memory, context, DAG, trace, eval, or unified-diff runner surfaces.
- Keep the active runtime focused on the current product-building loop unless the task explicitly implements a next approved sequence.
- Verify narrowly and report what actually ran.
- After every major feature, milestone, or direction change, align active docs, remove stale context, verify, commit, merge to `main`, push when approved, and write a compact handoff with one next safe action.
- Treat stale plans, archived workflow instructions, old command lists, and conflicting architecture notes as poison context. Delete, rewrite, or quarantine them before they can steer another agent.

## Current Loop

Keep work aligned with:

```text
Idea -> definition -> spec -> plan -> planning judge -> bounded tasks -> builder/judge execution -> verification -> next human decision
```

## Not Yet

- Aider
- Hermes
- OpenCode
- memory
- complex scheduling
- autonomous routing
- PR automation

Non-local adapters must not become the product identity. Treat model/runtime details as bounded implementation lanes, not the source of truth.
