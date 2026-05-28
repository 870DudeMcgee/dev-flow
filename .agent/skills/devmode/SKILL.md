---
name: devmode
description: Master engineering workflow for Dev-Flow. Use for software development tasks that should combine Superpowers disciplined execution, Matt Pocock engineering skills, token optimization as a budget discipline, and Dev-Flow project rules.
---

# DevMode Skill

DevMode is the master workflow router.

It includes:

- Superpowers `/using-superpowers` disciplined execution as the default baseline
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

### Token Budget

Use token optimization whenever:

- the repo context is large
- repeated reads are happening
- the transcript is growing
- the active agent wants to inspect too many files
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

Report only after all work is done. Omit empty fields. Use this format:

Decision:
Files changed:
Verification:
Risks:
Next safe action:
