---
name: devmode
description: Master engineering workflow for Dev-Flow. Use for software development tasks that should combine Superpowers disciplined execution, Matt Pocock engineering skills, token optimization, and Dev-Flow project rules.
---

# DevMode Skill

DevMode is the master workflow router.

When invoked through `/devmode`, output exactly:

```text
DevMode loaded: token optimization, repo discipline, read-only/implementation gating.
```

Then continue silently. Do not output a skills-used line.

It includes:

- Superpowers disciplined execution as the default baseline
- Matt Pocock engineering skills when relevant
- token optimization as an always-on budget discipline
- Dev-Flow repo-specific operating rules

## Baseline

Use `using-superpowers` behavior for all development tasks:

- understand the task
- gather minimal context
- plan briefly when useful
- execute in small vertical slices
- verify
- report evidence

## Mode Gate

Classify mode before acting:

- Read-only: audit, review, investigate, explain, plan, summarize, or unclear write permission. Do not edit, stage, commit, or create files.
- Implementation: fix, build, update, apply, or explicit permission to edit. Edit only relevant files, run targeted verification, and commit only when explicitly requested or permitted and verification passes.

If write permission is ambiguous, ask one blocking question or stay read-only.

## Token Budget

Token optimization is mandatory by default:

- search before broad reads
- inspect only files needed for the task
- read targeted sections before whole files
- avoid repeated context and repeated summaries
- do not load unrelated skills, workflows, or docs
- do not create handoff docs unless explicitly requested
- do not run extra checks beyond the requested or narrowest meaningful checks
- do not run ruff
- do not scan the whole repo unless needed
- stop when the next safe action is obvious

## Routing

Use sub-skills deliberately.

Do not load all sub-skills by default.

### Architecture

Use `improve-codebase-architecture` when the task concerns:

- module boundaries
- coupling
- architecture
- refactoring
- codebase health
- testability
- AI navigability

### Docs and Assumptions

Use `grill-with-docs` when the task concerns:

- specs
- docs
- ADRs
- plans
- assumptions
- implementation alignment

### Simplicity

Use `caveman` when the task or proposed solution is:

- overbuilt
- too clever
- overly abstract
- bigger than the milestone requires

### Token Escalation

Consult the token-optimization package only when:

- the repo context is large
- repeated reads are happening
- the transcript is growing
- the agent wants to inspect too many files
- the model is producing bloated plans

## Dev-Flow Rules

- Dev-Flow is local-first.
- Agents are replaceable.
- State is sacred.
- Visibility is mandatory.
- Verification belongs to Dev-Flow.
- Humans control promotion to main.
- Implement small vertical slices.
- Avoid future architecture.
- Preserve canonical artifacts.
- Do not add adapters, model routing, dashboard servers, databases, merge automation, or PR automation unless explicitly required.

## Silent Work Mode

Run DevMode silently.

Use Superpowers, Matt Pocock skills, token optimization, and Dev-Flow rules internally. Do not narrate the workflow.

Do not produce progress narration unless the user explicitly asks for a live walkthrough.

Avoid phrases like:

- "I'll..."
- "I'm going to..."
- "I'm reading..."
- "I'm checking..."
- "Let me..."
- "Good..."
- "Actually..."
- "Now I..."
- "Starting..."
- "Completed..."
- "The plan is..."

Only speak when:

- asking a blocking question
- reporting the final result
- reporting a verification failure
- reporting a risk that changes the next safe action

## Output

Decision:
Files changed:
Verification:
Risks:
Next safe action: