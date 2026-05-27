# Task: 016 - CLI split chunk 13 run task runner delegate
Status: COMPLETED
Goal: cli_module_deepening
Plan: 2026-05-27-devflow-agentic-control-plane-implementation-plan.md
Assigned Agent: vscode
Owner Lock: vscode-session-2026-05-27
Risk: MEDIUM
Branch: devflow/task-016-vscode
Touched Files:
- src/devflow/runner.py
- src/devflow/cli.py

## 1. Objective

Move the `run_task` workflow implementation out of CLI and into runner module, leaving CLI as a thin delegate while preserving behavior and output.

## 2. Allowed Files

- src/devflow/runner.py
- src/devflow/cli.py

## 3. Do Not Touch

- .env
- production secrets
- unrelated source files

## 4. Required Context

- Preserve all current status transitions, report behavior, and output lines.
- Keep command semantics for preview/apply/rollback unchanged.

## 5. Implementation Instructions

1. Add `run_task_workflow(task_file, yes)` to runner module using existing behavior.
2. Rewire CLI `run_task` wrapper to delegate.
3. Remove no-longer-used CLI imports.

## 6. Patch Protocol

Unified diff only.

## 7. Verification Commands

- PYTHONPATH=src python3 -m unittest tests/test_cli.py -q
- PYTHONPATH=src python3 -m unittest tests/test_dag.py -q

## 8. Failure Handling

- Patch apply failure: stop and report
- Verification failure: stop and report

## 9. Execution Results

```diff
# Add unified diff here.
```

## 10. Final Report

Completed.

- Added `run_task_workflow(task_file, yes, cwd)` in [src/devflow/runner.py](src/devflow/runner.py) by moving the full prior `run_task` workflow implementation from CLI.
- Rewired `run_task(...)` in [src/devflow/cli.py](src/devflow/cli.py) to a thin delegate to `run_task_workflow(...)`.
- Cleaned stale CLI imports/helpers that were only needed by the old in-module workflow.

Regression fixes applied during this chunk:
- Resolved circular import by moving `load_config` import inside `run_task_workflow`.
- Fixed config call signature to `load_config()`.
- Imported `invalidate_memories` in runner to preserve memory invalidation behavior.

Verification passed:
- `PYTHONPATH=src python3 -m unittest tests/test_cli.py -q`
- `PYTHONPATH=src python3 -m unittest tests/test_dag.py -q`
