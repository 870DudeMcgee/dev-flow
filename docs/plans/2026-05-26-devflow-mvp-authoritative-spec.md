# devflow MVP Authoritative Spec

Date: 2026-05-26
Status: Single Source of Truth

## Product Statement

devflow MVP is a safe, file-based task runner for AI-generated unified diffs.

## Multi-Orchestrator Operating Mode

Codex Desktop, VS Code/Cline, and Antigravity are peer orchestrators.

Each orchestrator can run a full internal dev team (planning, implementation, testing, verification, reporting). Local models are worker agents, not orchestrators.

No IDE is permanently assigned to only planning, only diff writing, or only auditing.

Work is divided by claimed task, not by fixed IDE specialty. Once an orchestrator claims a task, it may complete the task end-to-end with its own subagents as long as it respects the task file, declared touched files, git branch policy, verification, and report requirements.

## Canonical CLI

- devflow init
- devflow status
- devflow run .devflow/tasks/<task>.md
- devflow run .devflow/tasks/<task>.md --yes

`devflow run <task>` validates and previews only. `--yes` is required to apply code changes.

## Canonical Protocol Tree

.devflow/
- config.json
- constitution.md
- goals/
- plans/
- tasks/
- workflows/
- skills/
- context/
- index/
- logs/
- reports/

## Enforceable Policy Source

config.json is authoritative for:
- git checkpoint strategy
- protected paths
- verification defaults
- failure taxonomy retry budgets

constitution.md is explanatory only.

## Canonical Task Schema

Header fields:
- Status
- Goal
- Plan
- Assigned Agent
- Owner Lock
- Risk
- Branch
- Touched Files

Sections:
1. Objective
2. Allowed Files
3. Do Not Touch
4. Required Context
5. Implementation Instructions
6. Patch Protocol
7. Verification Commands
8. Failure Handling
9. Execution Results
10. Final Report

Patch payload: fenced diff block.

`Allowed Files` entries may be exact paths, glob patterns such as `src/devflow/**`, or `...` shorthand such as `tests/...`.

Cross-IDE coordination headers should include:
- Assigned Agent
- Owner Lock
- Branch
- Touched Files

Task ownership rules:
- PENDING tasks may be claimed by any orchestrator.
- CLAIMED/RUNNING tasks are owned by their Assigned Agent and Owner Lock.
- Other orchestrators may review claimed tasks but must not mutate the task or touched files unless ownership is transferred.
- Direct human instruction can override ownership, but the task file should be updated immediately afterward.

MVP task status values:
- PENDING
- CLAIMED
- PREVIEWED
- RUNNING
- COMPLETED
- FAILED
- BLOCKED

`PREVIEWED` means the embedded unified diff passed validation/dry-run checks but was not applied because `--yes` was not provided.

## Protected Path Gate

If a diff touches any protected path pattern, execution stops before apply and status becomes BLOCKED.

## Clean Worktree Gate

Before `devflow run` mutates task files, reports, branches, or source files, the git worktree must be clean. Dirty worktrees stop the run before mutation and list changed files. Task files should be committed before execution.

## Verification Behavior

Selection priority:
1. Task-specified verification commands
2. Config-specified verification commands
3. Auto-detected commands
4. No verification available (explicitly reported)

## Failure Taxonomy (MVP)

- PATCH_APPLY_FAILURE
- SYNTAX_ERROR
- IMPORT_ERROR
- TEST_FAILURE
- LINT_FAILURE
- TYPE_ERROR
- PROTECTED_FILE_TOUCHED
- UNKNOWN_FAILURE

MVP requires classification and retry budgets only.

## Required Report

One report per run:
- .devflow/reports/<task-id>.report.md

Report fields:
- task id
- status
- checkpoint branch and base branch
- files changed
- protected files detected
- patch apply result
- verification commands and results
- failure classification
- rollback status
- final outcome

## Explicit Deprecations

Not part of MVP:
- XML search/replace edit mode
- slim prototype .devflow layout
- hardcoded orchestrator model endpoint
- full risk score engine
- planning command

## Coordination Guardrail

Do not rely on permanent IDE roles for safety. Safety comes from task claims, branch-per-task work, touched-file declarations, verification, rollback, and reports.
