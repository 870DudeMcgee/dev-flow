# Task: 007 - CLI split chunk 4 task ops and IO
Status: COMPLETED
Goal: cli_module_deepening
Plan: 2026-05-27-devflow-agentic-control-plane-implementation-plan.md
Assigned Agent: vscode
Owner Lock: vscode-session-2026-05-27
Risk: LOW
Branch: devflow/task-007-vscode
Touched Files:
- src/devflow/manager.py
- src/devflow/cli.py

## 1. Objective

Move task file IO and task operations (claim/release/transition) from CLI into manager-level functions while preserving CLI behavior and output.

## 2. Allowed Files

- src/devflow/manager.py
- src/devflow/cli.py

## 3. Do Not Touch

- .env
- production secrets
- unrelated source files

## 4. Required Context

- Keep user-facing CLI messages and exit behavior stable.
- Keep refactor narrow and behavior-neutral.

## 5. Implementation Instructions

1. Add manager-level helpers for task file IO and claim/release/transition operations.
2. Rewire CLI command functions to call manager operations.
3. Remove duplicated operation logic from CLI.

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

- Added manager-level task IO and task operation functions in [src/devflow/manager.py](src/devflow/manager.py).
- Rewired CLI claim/release/transition/status and status-write paths to use manager functions in [src/devflow/cli.py](src/devflow/cli.py).
- Removed duplicated task-operation implementation from CLI.
- Verification passed:
	- `PYTHONPATH=src python3 -m unittest tests/test_cli.py -q`
	- `PYTHONPATH=src python3 -m unittest tests/test_manager.py -q`
