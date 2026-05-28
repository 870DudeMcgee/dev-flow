---
description: Activate DevMode master engineering workflow
---

# DevMode Master Workflow

Run DevMode for this task.

DevMode is the master engineering workflow. It includes:

- Superpowers `/using-superpowers` disciplined execution
- Matt Pocock engineering skills when relevant
- repo-local token optimization as a budget discipline
- Dev-Flow project rules

## Prime Directive

Use the full workflow intelligently, not wastefully.

Do not load every skill at once. Route to the right skill at the right time.

## Step 1: Classify the Task

Classify the task as one or more of:

- implementation
- bug fix
- test work
- documentation
- architecture/design
- code review
- cleanup/refactor
- investigation
- planning
- verification

## Step 2: Apply Baseline Superpowers Discipline

Use `/using-superpowers` behavior as the default execution discipline:

- understand the task
- inspect the minimum relevant context
- make a short plan when useful
- execute in small vertical slices
- verify the result
- report evidence

## Step 3: Apply Token Optimization as a Budget Discipline

Always apply token optimization as lightweight process constraints:

- search before broad reads
- read targeted sections first
- avoid re-reading known context
- summarize before expanding
- avoid transcript bloat
- do not invoke unrelated skills
- stop when the next safe action is obvious

## Step 4: Route to Matt Pocock Skills When Needed

Use `improve-codebase-architecture` only when the task involves:

- architecture
- module boundaries
- coupling
- codebase health
- refactor direction
- testability
- AI-navigability
- long-term maintainability

Use `grill-with-docs` only when the task involves:

- challenging a plan
- checking against docs
- checking against ADRs
- validating assumptions
- verifying spec alignment
- reviewing whether an implementation actually matches the intended design

Use `caveman` only when:

- the solution is overbuilt
- abstractions are premature
- the model proposes too many moving parts
- the implementation is clever instead of obvious
- a simpler design would satisfy the milestone

## Step 5: Apply Dev-Flow Project Rules

For this repository:

- Dev-Flow is a local-first control-room kernel, not a coding-agent wrapper.
- The filesystem is the source of truth.
- `task.yaml` is canonical task state.
- `events.jsonl`, `questions.jsonl`, logs, and `verification.json` are evidence.
- `summary.json` and packets are derived, not authoritative.
- Do not invent state.
- Do not bypass verification.
- Do not merge or promote automatically.
- Do not build future architecture unless the current milestone requires it.

## Step 6: Execute

Make the smallest useful change or produce the smallest useful plan.

Do not combine unrelated work.

Do not perform broad rewrites unless explicitly requested.

## Step 7: Verify

Run the narrowest meaningful verification command.

If verification cannot be run, say exactly why.

## Final Report

Decision:
Skills used:
Files inspected:
Files changed:
Verification:
Risks:
Next safe action:
