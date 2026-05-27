# /devflow

Use this workflow for any software engineering task.

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

### 2. Task packet

Create or update:

`.devflow/tasks/<task-id>.md`

Include:

- Objective
- Allowed files
- Context files
- Acceptance criteria
- Verification commands
- Risk tier
- Protected paths
- Status

### 3. Context

Read only:

1. `AGENTS.md`
2. `.devflow/workflow/DEVFLOW_WORKFLOW.md`
3. Task packet
4. Repo map
5. Relevant tests
6. Relevant implementation files

Do not scan the entire repo unless the task is architecture-level.

### 4. Plan checkpoint

Before editing, output:

- Intended files
- Intended tests
- Verification command
- Risk tier
- Stop conditions

### 5. Test-first

For behavior changes, write or identify failing tests first.

### 6. Implement

Make minimal changes only.

### 7. Verify

Run targeted verification.
If failure occurs, classify it and repair with a bounded loop.

### 8. Review

Review for scope, safety, tests, and maintainability.

### 9. Report

Write:

`.devflow/reports/<task-id>.report.md`

Include:

- Summary
- Files changed
- Tests run
- Result
- Risks
- Follow-up tasks
