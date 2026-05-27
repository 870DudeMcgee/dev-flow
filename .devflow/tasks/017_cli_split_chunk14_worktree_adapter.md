# Task: 017 - CLI split chunk 14 worktree adapter
Status: COMPLETED
Goal: cli_module_deepening
Plan: 2026-05-27-devflow-agentic-control-plane-implementation-plan.md
Assigned Agent: vscode
Owner Lock: vscode-session-2026-05-27
Risk: LOW
Branch: devflow/task-017-vscode
Touched Files:
- src/devflow/worktree_commands.py
- src/devflow/cli.py

## 1. Objective

Move worktree command wrapper behavior into a dedicated adapter module while preserving CLI output.

## 2. Allowed Files

- src/devflow/worktree_commands.py
- src/devflow/cli.py

## 3. Do Not Touch

- .env
- production secrets
- unrelated source files

## 4. Required Context

- Preserve exact printed output for worktree create/status/remove commands.
- Keep refactor narrow and behavior-neutral.

## 5. Implementation Instructions

1. Add worktree command adapter module with create/status/remove command handlers.
2. Rewire CLI wrappers to delegate.
3. Keep current error handling and output semantics unchanged.

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

- Added dedicated worktree adapter module [src/devflow/worktree_commands.py](src/devflow/worktree_commands.py) with:
	- `worktree_create_command(task_file, agent)`
	- `worktree_status_command()`
	- `worktree_remove_command(task_file, keep_artifacts=False)`
- Rewired CLI wrappers in [src/devflow/cli.py](src/devflow/cli.py) to delegate to adapter commands.
- Preserved output and error semantics for create/status/remove worktree commands.

Verification passed:
- `PYTHONPATH=src python3 -m unittest tests/test_cli.py -q`
- `PYTHONPATH=src python3 -m unittest tests/test_dag.py -q`
