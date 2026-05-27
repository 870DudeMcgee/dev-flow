# Task: 009 - CLI split chunk 6 task discovery helper
Status: COMPLETED
Goal: cli_module_deepening
Plan: 2026-05-27-devflow-agentic-control-plane-implementation-plan.md
Assigned Agent: vscode
Owner Lock: vscode-session-2026-05-27
Risk: LOW
Branch: devflow/task-009-vscode
Touched Files:
- src/devflow/manager.py
- src/devflow/cli.py

## 1. Objective

Move plan task discovery helper used by ready/next/graph from CLI into manager, preserving command behavior.

## 2. Allowed Files

- src/devflow/manager.py
- src/devflow/cli.py

## 3. Do Not Touch

- .env
- production secrets
- unrelated source files

## 4. Required Context

- Keep user-facing output unchanged.
- Keep refactor narrow and behavior-neutral.

## 5. Implementation Instructions

1. Add manager-level helper to load tasks from .devflow plans.
2. Rewire CLI ready/next/graph flow to use manager helper.
3. Remove local duplicate helper from CLI.

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

- Added manager-level plan task discovery helper in [src/devflow/manager.py](src/devflow/manager.py):
	- `load_all_plan_tasks`
- Updated CLI ready/next/graph flow to use manager helper in [src/devflow/cli.py](src/devflow/cli.py).
- Removed duplicated `_load_all_plan_tasks` from CLI.
- Verification passed:
	- `PYTHONPATH=src python3 -m unittest tests/test_cli.py -q`
	- `PYTHONPATH=src python3 -m unittest tests/test_manager.py -q`
