# /devmode

Activate DevMode for the current task.

Output exactly one line:

```text
DevMode loaded: token optimization, repo discipline, read-only/implementation gating.
```

Then continue silently. Do not output a skills-used line.

Antigravity workflows are prompt/rule mechanisms, not true reusable skill loaders like Superpowers. This file is the closest reliable `/devmode` entry point for Antigravity.

## Contract

- Use Superpowers-style discipline: understand, search, inspect only needed files, small plan when useful, small slice, verify, concise evidence.
- Token optimization is mandatory: no broad scans, repeated summaries, ceremonial output, unnecessary docs, unnecessary commits, extra checks, or ruff.
- Follow `AGENTS.md`, `PRODUCT_NORTH_STAR.md`, and `docs/control-room-mvp.md` for repo direction.
- Do not use archived `.devflow/workflow/**` or legacy software-factory docs as process authority.
- Do not add adapters, model routing, dashboard servers, databases, merge automation, or PR automation unless explicitly required.

## Mode Gate

- Read-only prompts: audit, review, investigate, explain, plan, summarize, or unclear write permission. Do not edit, stage, commit, or create files.
- Implementation prompts: fix, build, update, apply, or explicit permission to edit. Edit only relevant files, run targeted verification, and commit only when explicitly requested or permitted and verification passes.

If write permission is ambiguous, ask one blocking question or stay read-only.