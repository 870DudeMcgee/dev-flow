# Task: 005 - CLI split chunk 2 task mutation helpers
Status: COMPLETED
Goal: cli_module_deepening
Plan: 2026-05-27-devflow-agentic-control-plane-implementation-plan.md
Assigned Agent: vscode
Owner Lock: vscode-session-2026-05-27
Risk: LOW
Branch: devflow/task-005-vscode
Touched Files:
- src/devflow/manager.py
- src/devflow/cli.py

## 1. Objective

Move Task markdown mutation helpers from CLI into the Task module while preserving command behavior.

## 2. Allowed Files

- src/devflow/manager.py
- src/devflow/cli.py

## 3. Do Not Touch

- .env
- production secrets
- unrelated source files

## 4. Required Context

- No user-facing CLI behavior changes.
- Keep refactor narrow and reversible.

## 5. Implementation Instructions

1. Add Task markdown mutation helpers to `src/devflow/manager.py`.
2. Update `src/devflow/cli.py` to import and use those helpers.
3. Remove duplicated helper implementations from CLI.

## 6. Patch Protocol

Unified diff only.

## 7. Verification Commands

- PYTHONPATH=src python3 -m unittest tests/test_cli.py -q
- PYTHONPATH=src python3 -m unittest tests/test_manager.py -q

## 8. Failure Handling

- Patch apply failure: stop and report
- Verification failure: stop and report

## 9. Execution Results

```diff
# Add unified diff here.
```

## 10. Final Report

Completed.

- Added Task markdown mutation helpers to [src/devflow/manager.py](src/devflow/manager.py).
- Updated CLI to use manager-owned helpers in [src/devflow/cli.py](src/devflow/cli.py).
- Removed duplicated helper implementations from CLI.
- Verification passed:
	- `PYTHONPATH=src python3 -m unittest tests/test_cli.py -q`
	- `PYTHONPATH=src python3 -m unittest tests/test_manager.py -q`
