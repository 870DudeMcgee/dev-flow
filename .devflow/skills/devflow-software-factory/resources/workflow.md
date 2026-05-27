# Devflow Software Factory — Condensed Workflow Reference

This is a compact reference for context-limited environments. For the full specification, see `DEVFLOW_WORKFLOW.md`.

## Workflow

**PLAN → CONTEXT → TEST → IMPLEMENT → VERIFY → REVIEW → REPORT**

## Quick Reference

| Phase | Key Rule |
|-------|----------|
| PLAN | Classify task, create packet, list allowed files |
| CONTEXT | Use smallest sufficient context; search before reading |
| TEST | Red/green first for behavior changes |
| IMPLEMENT | Minimal diff, no cleanup, no dependency changes |
| VERIFY | Targeted first, then broader; classify failures |
| REVIEW | Compliance, scope creep, missing tests, safety |
| REPORT | Summary, files, tests, result, risks, next action |

## Stop Conditions

- File outside allowed paths
- Protected file needs edit
- Dependency change needed
- Verification cannot run
- Repair budget exhausted
- Task too large, should split

## Task Result Schema

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
