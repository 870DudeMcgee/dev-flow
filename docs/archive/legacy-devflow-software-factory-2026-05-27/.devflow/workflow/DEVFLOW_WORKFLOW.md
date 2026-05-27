# Devflow Software Factory Workflow

## Purpose

This workflow makes AI coding agents safe, token-efficient, and auditable.

It applies to all non-trivial code, test, refactor, bug-fix, architecture, and documentation tasks.

## Core Principles

1. **Least context** — use the smallest sufficient context for the task.
2. **Least privilege** — only touch allowed files; protected files require approval.
3. **Least mutation** — emit the smallest diff that satisfies the task.
4. **Maximum verification** — verify before claiming success; evidence before assertions.
5. **Artifact-first work** — all mutations are represented as diffs or explicit file edits with provenance.
6. **Human-readable reports** — every task ends with a report.

## Workflow States

### PLAN

1. Classify the task: trivial edit, bug fix, feature, refactor, test-only, docs-only, investigation, or high-risk change.
2. Identify risk tier (LOW / MEDIUM / HIGH).
3. Create or update a task packet in `.devflow/tasks/`.
4. List allowed paths and expected touched files.
5. State the verification commands.
6. If trivial, proceed directly with a minimal edit and report.

### CONTEXT

Read only the smallest sufficient context, in this priority order:

1. Task packet
2. `.devflow/context/repo-map.short.md` (repo map)
3. Targeted search results (ripgrep, symbol search)
4. Relevant existing tests near target code
5. Specific implementation files named by the task
6. Recent failure logs

**Do not scan the entire repository** unless the task explicitly requires architecture-level analysis.

### TEST

For behavior changes, prefer red/green test-first:

1. Write or identify a failing test that captures the desired behavior.
2. Explain the expected failure.
3. Avoid broad test rewrites — keep test changes scoped to the task.

If no test is practical, explain why in the plan.

### IMPLEMENT

Rules:

- Minimal diff only.
- No unrelated cleanup.
- No dependency changes unless explicitly approved.
- No protected file changes unless explicitly approved.
- Preserve public API unless the task explicitly says otherwise.
- Do not rewrite files that are not in the allowed paths.

### VERIFY

1. Run the narrowest relevant verification first (targeted test, type check).
2. Run broader verification if warranted by risk tier.
3. Classify any failures using the taxonomy: `syntax`, `import`, `type`, `assertion`, `lint`, `environment`, `flaky`, `unknown`.
4. Repair only with bounded loops (respect retry budget from config).
5. Do not claim success without evidence.

### REVIEW

Review the completed work for:

- Task compliance — does the diff satisfy the acceptance criteria?
- Scope creep — did unrelated changes sneak in?
- Missing tests — are behavior changes covered?
- Safety risks — protected files, secrets, destructive operations?
- Maintainability — will another developer understand this?

### REPORT

Always end with a report containing:

- Summary of what changed
- Files changed
- Tests run
- Verification result (passed / failed / not_run)
- Known risks
- Follow-up tasks or next recommended action

Reports are written to `.devflow/reports/<task-id>.report.md`.

## Stop Conditions

Stop and ask/report if:

- Required file is outside allowed paths
- Protected files need edits
- Dependency changes are needed
- Verification cannot run
- Repair loop exceeds retry budget
- Task is too large and should be split
- Context is missing and blocks safe progress

## Parallel Coordination

This repository supports three peer orchestrators: Codex Desktop, VS Code/Copilot, and Google Antigravity.

- Each orchestrator runs its own full dev-team subagent stack.
- No single IDE is the permanent coordination lead.
- Task-level ownership is assigned explicitly via `devflow task claim`.
- Claimed tasks and their declared touched files are read-only to other orchestrators.
- Local models (Ollama) are worker subagents, not orchestrators.
- All repo mutations flow through task files, unified diffs, `devflow run` safety gates, and reports.

## References

- Token minimization: `.devflow/workflow/token-policy.md`
- Artifact contracts: `.devflow/workflow/artifact-contract.md`
- Role definitions: `.devflow/workflow/role-contracts.md`
- Verification rules: `.devflow/workflow/verification-policy.md`
- Skill: `.devflow/skills/devflow-software-factory/SKILL.md`
- CLI enforcement: `devflow run`, `devflow doctor`
