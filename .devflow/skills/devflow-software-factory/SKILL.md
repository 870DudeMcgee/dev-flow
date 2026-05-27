---
name: devflow-software-factory
description: Use this for any non-trivial software engineering task. It enforces token-efficient planning, context minimization, artifact-based coding, test-first implementation, verification, review, and reporting.
---

# Devflow Software Factory Skill

## Goal

Complete software engineering tasks using the smallest sufficient context, bounded artifacts, minimal diffs, and explicit verification.

## Prime Directive

You are not an autonomous repo-mutating agent. You are a proposal generator operating inside the Devflow control plane.

All mutations must be:
1. Scoped to allowed paths
2. Explainable in a one-paragraph summary
3. Represented as a unified diff or explicit file edit
4. Verified with evidence
5. Reported

## Workflow

Follow: **PLAN → CONTEXT → TEST → IMPLEMENT → VERIFY → REVIEW → REPORT**

For the full specification, read: `.devflow/workflow/DEVFLOW_WORKFLOW.md`

### 1. Classify the task

Classify as one of:

- **trivial edit** — single line, no tests needed
- **bug fix** — behavior change with test coverage
- **feature** — new functionality
- **refactor** — structural change, no behavior change
- **test-only** — adding or fixing tests
- **docs-only** — documentation changes
- **investigation** — research, no code changes
- **high-risk change** — auth, payments, CI, dependencies

If trivial, proceed with a minimal edit and report. Otherwise, create or use a task packet.

### 2. Build smallest context

Use this priority order:

1. Task packet (`.devflow/tasks/<id>.md`)
2. Repo map (`.devflow/context/repo-map.short.md`)
3. Targeted search results
4. Relevant existing tests
5. Specific implementation files
6. Recent failure logs

**Do not read unrelated files.** See `.devflow/workflow/token-policy.md`.

### 3. Plan

Before editing, state:

- Objective
- Allowed files
- Expected verification command
- Risks
- Whether tests should be written first

### 4. Test

For behavior changes, prefer red/green:

- Write or identify a failing test
- Explain expected failure
- Avoid broad test rewrites

See `.devflow/workflow/verification-policy.md`.

### 5. Implement

Rules:

- Minimal diff
- No unrelated cleanup
- No dependency changes unless approved
- No protected file changes unless approved
- Preserve public API unless task says otherwise

### 6. Verify

Run the narrowest relevant verification first, then broader if warranted.

Classify failures: `syntax`, `import`, `type`, `assertion`, `lint`, `environment`, `flaky`, `unknown`.

Repair only with bounded loops.

### 7. Review

Review for:

- Task compliance
- Scope creep
- Missing tests
- Safety risks
- Maintainability

See `.devflow/workflow/role-contracts.md` for the Reviewer role contract.

### 8. Report

Always end with:

- Summary
- Files changed
- Tests run
- Verification result
- Known risks
- Next recommended action

See `.devflow/workflow/artifact-contract.md` for output schemas.

## Token Minimization Rules

- Summarize before expanding.
- Prefer paths and symbols over full files.
- Ask for missing context only when it blocks safe progress.
- Do not include long explanations in code-edit responses.
- Do not repeat unchanged code.
- Do not produce large plans for tiny edits.

See `.devflow/workflow/token-policy.md` for the full policy.

## Output Contracts

When asked to produce a task result, use:

```json
{
  "status": "ready | blocked | needs_review",
  "summary": "",
  "changed_files": [],
  "verification": {
    "commands": [],
    "status": "passed | failed | not_run",
    "notes": ""
  },
  "risks": [],
  "next_action": ""
}
```

Schema: `resources/schemas/task-result.schema.json`

## CLI Integration

When possible, use the `devflow` CLI instead of improvising:

```bash
devflow task new <id> <title>     # Create task packet
devflow task claim <file> --agent <agent> --lock <lock>
devflow context build <file> --role <role>
devflow run <file>                # Preview mode
devflow run <file> --yes          # Apply + verify
devflow task transition <file> --to <state>
devflow doctor                   # Health check
```

## References

- Full workflow: `.devflow/workflow/DEVFLOW_WORKFLOW.md`
- Token policy: `.devflow/workflow/token-policy.md`
- Artifact contracts: `.devflow/workflow/artifact-contract.md`
- Role contracts: `.devflow/workflow/role-contracts.md`
- Verification policy: `.devflow/workflow/verification-policy.md`
