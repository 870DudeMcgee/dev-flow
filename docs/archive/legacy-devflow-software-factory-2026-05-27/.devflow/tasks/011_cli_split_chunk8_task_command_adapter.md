# Task: 011 - CLI split chunk 8 task command adapter
Status: COMPLETED
Goal: cli_module_deepening
Plan: 2026-05-27-devflow-agentic-control-plane-implementation-plan.md
Assigned Agent: vscode
Owner Lock: vscode-session-2026-05-27
Risk: LOW
Branch: devflow/task-011-vscode
Touched Files:
- src/devflow/task_commands.py
- src/devflow/cli.py

## 1. Objective

Move ready/next/graph task command behavior into a dedicated adapter module while preserving CLI output and behavior.

## 2. Allowed Files

- src/devflow/task_commands.py
- src/devflow/cli.py

## 3. Do Not Touch

- .env
- production secrets
- unrelated source files

## 4. Required Context

- Keep user-facing output unchanged.
- Keep refactor narrow and behavior-neutral.

## 5. Implementation Instructions

1. Add dedicated task command adapter module for ready/next/graph behavior.
2. Rewire CLI wrappers to delegate to adapter functions.
3. Keep command wiring and output shape stable.

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

- Added dedicated task command adapter module in [src/devflow/task_commands.py](src/devflow/task_commands.py):
	- `task_ready_command`
	- `task_next_command`
	- `task_graph_command`
- Rewired CLI wrappers to delegate to adapter module in [src/devflow/cli.py](src/devflow/cli.py).
- Verification passed:
	- `PYTHONPATH=src python3 -m unittest tests/test_cli.py -q`
	- `PYTHONPATH=src python3 -m unittest tests/test_dag.py -q`
