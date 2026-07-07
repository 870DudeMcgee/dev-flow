---
name: using-devmode
description: Compatibility adapter for DevFlow workflow discipline.
---

# Using DevFlow Workflow

This skill name remains for compatibility with older harness checks. It is **not** a separate product authority and must not resurrect retired DevMode, control-room, roadmap, or north-star documents.

## Active Authority

1. User instruction for the current task.
2. `AGENTS.md` for repo operating rules.
3. `docs/DEVFLOW_SOURCE_OF_TRUTH.md` for product direction.
4. `docs/README.md` for the active docs allowlist.

Quarantined documents are recovery material only. Do not load them as current context unless the user explicitly asks for historical recovery.

## Mode Gate

Before changing files, classify the request:

- **Read-only**: audit, review, investigate, explain, plan, summarize, or unclear write permission. Do not edit, stage, commit, or create files.
- **Implementation**: fix, build, update, apply, or explicit permission to edit. Edit only relevant files, run targeted verification, and commit only when requested or clearly permitted.

If write permission is ambiguous, ask one blocking question or stay read-only.

## Token Budget

- Search before broad reads.
- Read targeted sections before whole files.
- Avoid repeated summaries, transcript bloat, and ceremonial narration.
- Stop when the next safe action is obvious.

## Skill Routing

Load only task-relevant skills. Do not load the whole skill tree as ritual.

| Task type | Useful skill |
|-----------|--------------|
| New product idea | `brainstorming` |
| Architecture/refactor | `improve-codebase-architecture` |
| Specs/docs assumptions | `grill-with-docs` |
| Implementation | `test-driven-development` |
| Bug/test failure | `systematic-debugging` |
| Completion check | `verification-before-completion` |
| Review request | `requesting-code-review` |
| Review response | `receiving-code-review` |
| Worker handoff | `worker-handoff` |

## Silent Work Mode

Use the workflow internally. Speak only when asking a blocking question, reporting final verified results, reporting a verification failure, or surfacing a risk that changes the next safe action.
