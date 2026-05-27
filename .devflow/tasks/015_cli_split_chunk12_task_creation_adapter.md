# Task: 015 - CLI split chunk 12 task creation adapter
Status: COMPLETED
Goal: cli_module_deepening
Plan: 2026-05-27-devflow-agentic-control-plane-implementation-plan.md
Assigned Agent: vscode
Owner Lock: vscode-session-2026-05-27
Risk: LOW
Branch: devflow/task-015-vscode
Touched Files:
- src/devflow/task_commands.py
- src/devflow/cli.py

## 1. Objective

Move task creation wrapper behavior into the task command adapter module while preserving path, slug, and output behavior.

## 2. Allowed Files

- src/devflow/task_commands.py
- src/devflow/cli.py

## 3. Do Not Touch

- .env
- production secrets
- unrelated source files

## 4. Required Context

- Preserve exact task path and message behavior for task creation.
- Keep refactor narrow and behavior-neutral.

## 5. Implementation Instructions

1. Add `task_new_command` to task command adapter module.
2. Rewire CLI `new_task` wrapper to delegate to adapter command.
3. Keep exception semantics and output unchanged.

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

- Added `task_new_command(...)` to [src/devflow/task_commands.py](src/devflow/task_commands.py), including slug/path generation and task file writing behavior.
- Rewired CLI `new_task(...)` in [src/devflow/cli.py](src/devflow/cli.py) to delegate to adapter command.
- Removed redundant task creation helper/import logic from CLI while preserving output and exception semantics.

Verification passed:
- `PYTHONPATH=src python3 -m unittest tests/test_cli.py -q`
- `PYTHONPATH=src python3 -m unittest tests/test_dag.py -q`
