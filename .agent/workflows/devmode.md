---
description: Activate DevMode master engineering workflow
---

# DevMode Master Workflow

Run DevMode for this task.

## Goal

Complete the user's development task with the smallest safe amount of context, the fewest useful tokens, and concrete verification evidence.

## Operating Rules

1. Classify the task.
2. Decide whether this is:
   * implementation
   * bug fix
   * test work
   * documentation
   * architecture/design
   * code review
   * cleanup/refactor
   * investigation only
3. Identify the minimum files needed.
4. Search before broad reads.
5. Read only targeted sections first.
6. Do not load unrelated skills, workflows, docs, or prior conversations.
7. Make the smallest safe vertical change.
8. Do not combine unrelated refactors with the requested task.
9. Verify with the narrowest meaningful command.
10. Report only useful evidence.

## Routing Rules

Use DevMode alone for normal implementation.

Use architecture review only when the task involves:
* boundaries
* coupling
* long-term design
* major refactors
* unclear ownership
* module structure

Use docs-grill behavior only when the task involves:
* checking alignment with project docs
* reviewing a proposed plan
* verifying whether an implementation matches a spec
* challenging assumptions

Use caveman simplification only when:
* the solution is over-abstracted
* the code is clever instead of clear
* the implementation is larger than the problem
* the agent starts proposing frameworks, abstractions, or future architecture not needed for the current slice

Use token optimization behavior always, but only as lightweight process constraints:
* search before reading
* summarize before expanding
* avoid repeated context
* avoid transcript bloat
* choose narrow role/context

## Hard Stops

Do not:
* read the whole repo unless the task truly requires it
* run multiple review rituals by default
* produce long plans before inspecting relevant context
* rewrite unrelated files
* create future architecture unless requested
* claim tests passed without running or explaining verification
* keep talking when the next action should be a focused edit/check

## Final Response Format

Decision:
Files inspected:
Files changed:
Verification:
Risks:
Next safe action:
