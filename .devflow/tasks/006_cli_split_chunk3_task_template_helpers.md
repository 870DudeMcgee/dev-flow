# Task: 006 - CLI split chunk 3 task template helpers
Status: COMPLETED
Goal: cli_module_deepening
Plan: 2026-05-27-devflow-agentic-control-plane-implementation-plan.md
Assigned Agent: vscode
Owner Lock: vscode-session-2026-05-27
Risk: LOW
Branch: devflow/task-006-vscode
Touched Files:
- src/devflow/manager.py
- src/devflow/cli.py

## 1. Objective

Move Task template construction helpers from CLI into the Task module while preserving command behavior.

## 2. Allowed Files

- src/devflow/manager.py
- src/devflow/cli.py

## 3. Do Not Touch

- .env
- production secrets
- unrelated source files

## 4. Required Context

- Keep `devflow task new` output identical.
- Keep refactor narrow and behavior-neutral.

## 5. Implementation Instructions

1. Add Task template helpers to `src/devflow/manager.py`.
2. Update `src/devflow/cli.py` to call manager-owned template helper.
3. Remove duplicated CLI template helper implementations.

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

- Added Task template helper to [src/devflow/manager.py](src/devflow/manager.py).
- Updated CLI to use manager-owned template construction in [src/devflow/cli.py](src/devflow/cli.py).
- Removed duplicated template helper implementations from CLI.
- Verification passed:
	- `PYTHONPATH=src python3 -m unittest tests/test_cli.py -q`
	- `PYTHONPATH=src python3 -m unittest tests/test_manager.py -q`
