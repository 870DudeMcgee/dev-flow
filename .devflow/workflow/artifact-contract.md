# Devflow Artifact Contract

## Purpose

All workflow outputs must conform to these contracts. This ensures every orchestrator produces auditable, machine-parseable results that other agents can consume.

## Task Result Contract

When completing a task, produce:

```json
{
  "status": "ready | blocked | needs_review",
  "summary": "One-paragraph description of what was done",
  "changed_files": ["path/to/file1", "path/to/file2"],
  "verification": {
    "commands": ["python -m pytest tests/test_foo.py -v"],
    "status": "passed | failed | not_run",
    "notes": "Optional detail about failures or skipped checks"
  },
  "risks": ["Risk description if any"],
  "next_action": "Recommended follow-up"
}
```

Schema: `.devflow/skills/devflow-software-factory/resources/schemas/task-result.schema.json`

## Review Result Contract

When reviewing a diff, produce:

```json
{
  "status": "approve | changes_requested | blocked",
  "blocking_findings": [
    {"file": "path", "line": 42, "issue": "description"}
  ],
  "non_blocking_findings": [
    {"file": "path", "line": 10, "suggestion": "description"}
  ],
  "verification_required": ["command to run"],
  "summary": "One-paragraph review summary"
}
```

Schema: `.devflow/skills/devflow-software-factory/resources/schemas/review-result.schema.json`

## Diff Result Contract

When producing implementation diffs, produce:

```json
{
  "task_id": "T-001",
  "diff": "unified diff content",
  "files_touched": ["path/to/file"],
  "files_outside_allowed": [],
  "protected_files_touched": [],
  "apply_status": "pending | applied | rejected",
  "verification_status": "passed | failed | not_run"
}
```

Schema: `.devflow/skills/devflow-software-factory/resources/schemas/diff-result.schema.json`

## Report Format

Task reports in `.devflow/reports/<task-id>.report.md` must include:

1. **Summary** — what changed and why
2. **Files Changed** — list of paths
3. **Tests Run** — commands executed
4. **Verification Result** — passed / failed / not_run with evidence
5. **Known Risks** — anything the reviewer should know
6. **Follow-up Tasks** — recommended next work
7. **Status Transitions** — state changes during execution
