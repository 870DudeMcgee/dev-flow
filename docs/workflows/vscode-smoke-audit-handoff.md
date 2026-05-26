# VS Code Smoke Audit Handoff

Date: 2026-05-26
Status: ACTIVE
Scope: VS Code/Copilot only

## Purpose

Run a repeatable audit pass in VS Code/Copilot against the completed smoke proving task to validate that handoff artifacts are sufficient for peer continuation.

## Audit Inputs

- task file: `.devflow/tasks/002_smoke_multi_agent_task.md`
- report file: `.devflow/reports/002.report.md`
- plan file: `.devflow/plans/002_smoke_multi_agent.plan.json`
- touched source files:
  - `smoke_todo_cli/todo_cli.py`
  - `smoke_todo_cli/tests/test_todo_cli.py`

## Preconditions

1. Open the smoke repo workspace in VS Code.
2. Ensure local worker preflight was run according to `docs/workflows/local-worker-health-check-runbook.md`.
3. Confirm task status is `COMPLETED` before audit edits.
4. Confirm orchestrator lane is VS Code/Copilot and local worker lane is qwen via Ollama.

## VS Code Audit Procedure

1. Verify task metadata consistency.
   - `Status` is `COMPLETED`.
   - `Assigned Agent`, `Owner Lock`, and `Touched Files` are present.

2. Verify report correctness.
   - `Status: COMPLETED`.
   - `Patch Apply Result: applied`.
   - verification command exists and has exit 0.
   - status transitions include `PREVIEWED -> RUNNING -> COMPLETED`.

3. Verify source/code alignment.
   - `smoke_todo_cli/todo_cli.py` contains `add-item` flow with missing-item guard.
   - `smoke_todo_cli/tests/test_todo_cli.py` contains both add-item tests.

4. Verify runtime behavior in integrated terminal.

```bash
PYTHONDONTWRITEBYTECODE=1 /Users/jewelbait/Desktop/Local\ AI\ Dev\ Team/.venv/bin/python -m unittest discover -s smoke_todo_cli/tests -q
```

Expected:
- 4 tests run
- all pass

5. Verify safety decisions from report.
   - dirty-worktree decision recorded
   - protected-path decision recorded
   - allowed-files decision recorded

6. Write audit note (read-only by default).
   - Add findings under a new section in the handoff doc.
   - Do not mutate touched source files unless human requests follow-up changes.

## Findings Template

Use this format in your audit note:

```md
## VS Code Audit: Task 002

- Result: PASS | FAIL
- Metadata consistency: PASS | FAIL
- Report consistency: PASS | FAIL
- Source alignment: PASS | FAIL
- Verification rerun: PASS | FAIL
- Notes:
  - <observation>
  - <risk or follow-up>
```

## Known Edge Cases (From Proving)

- Embedded unified diffs can fail if final hunks end on blank context lines and extraction trims trailing whitespace.
- Immediate preview/apply in the same second can collide checkpoint branch names; rerun apply from a clean worktree.

## Definition of Done

- VS Code audit result recorded with PASS/FAIL
- any failure includes exact command output and a proposed remediation
- if PASS, handoff states task is ready for next scoped milestone
