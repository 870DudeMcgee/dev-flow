# devflow MVP Authoritative Plan (Normalized)

Date: 2026-05-26
Status: AUTHORITATIVE FOR MVP

This plan supersedes prior hybrid drafts that centered XML search/replace and vendor-specific orchestration.

## Peer-Orchestrator Model

Codex Desktop, VS Code/Copilot, and Antigravity are peer orchestrators. Each IDE can run its own complete subagent dev team for planning, implementation, test generation, verification, and reporting.

Work is divided by task ownership, not by permanent IDE role. A task may be claimed by any orchestrator; the claiming orchestrator owns that task end-to-end until it completes, fails, blocks, or releases ownership.

Local models are worker subagents used by the orchestrators. Local models do not own repo state directly.

## MVP Source of Truth

devflow MVP is a safe, file-based task runner for AI-generated unified diffs.

It must:
1. Initialize the full .devflow protocol tree.
2. Read a canonical task markdown file.
3. Create a git checkpoint branch.
4. Accept/apply unified diffs.
5. Block protected-file changes.
6. Run auto-detected verification (or configured commands).
7. Classify failures with retry budgets.
8. Roll back on failure.
9. Write one task report per run.
10. Expose status.

## Canonical CLI Contract (MVP)

- devflow init
- devflow status
- devflow run .devflow/tasks/001_example.md
- devflow run .devflow/tasks/001_example.md --yes

`devflow run <task>` previews by default. `--yes` is required to apply the patch.

Deferred to next milestone:
- devflow plan
- devflow goal new
- devflow task next
- automated orchestration routing and DAG execution

## Canonical .devflow Tree

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

MVP may leave some directories empty; full automation for index/skills/context is out of scope.

## Patch Protocol

Unified diff is the only MVP patch format.

Deprecated for MVP:
- XML search/replace patch protocol

## Task Ownership Protocol

Task Markdown is the coordination unit. Recommended coordination headers:

- Status
- Assigned Agent
- Owner Lock
- Branch
- Touched Files

Status lifecycle:

- PENDING
- CLAIMED
- PREVIEWED
- RUNNING
- COMPLETED
- FAILED
- BLOCKED

`PREVIEWED` means the patch passed validation/dry-run checks but was not applied.

Other orchestrators must treat claimed tasks and declared touched files as read-only unless ownership is transferred or the human explicitly overrides the lock.

## Checkpointing

Configurable policy with branch default:

- git.checkpoint_strategy: branch
- git.branch_prefix: devflow/task-
- git.auto_commit_on_success: false

Before run mutation, the git worktree must be clean. Dirty worktrees stop before task/report/source mutation and list changed files.

## Protected Files

Policy is enforced from config.json (machine-readable).

If a patch touches a protected path, stop before apply and require human approval.

## Verification

Priority order:
1. Commands explicitly configured in .devflow/config.json
2. Auto-detected common tooling
3. If none available, continue and report verification unavailable

Python-oriented defaults for empty config:
- test_command: pytest
- lint_command: ruff check .
- typecheck_command: null
- format_check_command: null

## Failure Taxonomy (MVP)

Classify with retry budgets only:
- PATCH_APPLY_FAILURE
- SYNTAX_ERROR
- IMPORT_ERROR
- TEST_FAILURE
- LINT_FAILURE
- TYPE_ERROR
- PROTECTED_FILE_TOUCHED
- UNKNOWN_FAILURE

Routing metadata may remain in schema but is not required in MVP execution.

## Reports

Mandatory output:
- .devflow/reports/<task-id>.report.md

Required report fields:
- task id
- status
- branch/checkpoint used
- files changed
- protected files detected
- patch apply result
- verification commands run
- verification result
- failure classification if any
- rollback status
- final outcome
