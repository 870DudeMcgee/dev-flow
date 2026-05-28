# /devflow

Legacy alias only. Prefer `/devmode` for all software engineering tasks.

When this workflow is invoked, activate DevMode and output exactly one confirmation line:

```text
DevMode loaded: token optimization, repo discipline, read-only/implementation gating.
```

Then continue silently. Do not output a skills-used line.

Antigravity workflows are prompt/rule mechanisms, not true reusable skill loaders like Superpowers.

## Inputs

- User goal
- Current repository state
- Optional task ID

## Steps

### 1. Intake

Classify the task:

- trivial
- bug fix
- feature
- refactor
- docs
- test
- investigation
- high-risk

If trivial, proceed with a minimal edit and report.
If non-trivial, continue.

### 2. Mode gate

Classify mode before acting:

- Read-only: audit, review, investigate, explain, plan, summarize, or unclear write permission. Do not edit, stage, commit, or create files.
- Implementation: fix, build, update, apply, or explicit permission to edit. Edit only relevant files, verify, and commit only when explicitly requested or permitted and verification passes.

### 3. Context

Read only the smallest useful set:

1. `AGENTS.md`
2. `PRODUCT_NORTH_STAR.md` when making implementation decisions
3. `docs/control-room-mvp.md` for non-trivial code changes
4. Relevant tests
5. Relevant implementation files

Search before broad reads. Do not scan the entire repo unless the task requires it.

### 4. Token discipline

- No repeated summaries or ceremonial output.
- No unnecessary docs or handoff files.
- No ruff.
- No extra checks beyond requested or targeted verification.

### 5. Test-first when useful

For behavior changes, write or identify failing tests first.

### 6. Implement

Make minimal relevant changes only. Do not build future architecture.

### 7. Verify

Run targeted verification.
If failure occurs, classify it and repair with a bounded loop.

### 8. Review

Review for scope, safety, tests, and maintainability.

### 9. Report

Report compactly in chat. Do not create report or handoff files unless explicitly requested.

- Summary
- Files changed
- Tests run
- Result
- Risks
