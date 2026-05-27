# Task: 013 - CLI split chunk 10 task transition adapter
Status: COMPLETED
Goal: cli_module_deepening
Plan: 2026-05-27-devflow-agentic-control-plane-implementation-plan.md
Assigned Agent: vscode
Owner Lock: vscode-session-2026-05-27
Risk: LOW
Branch: devflow/task-013-vscode
Touched Files:
- src/devflow/task_commands.py
- src/devflow/cli.py

## 1. Objective

Move task transition wrapper behavior into the task command adapter module while preserving CLI output.

## 2. Allowed Files

- src/devflow/task_commands.py
- src/devflow/cli.py

## 3. Do Not Touch

- .env
- production secrets
- unrelated source files

## 4. Required Context

- Preserve exact transition output lines for CLI tests.
- Keep refactor narrow and behavior-neutral.

## 5. Implementation Instructions

1. Add `task_transition_command` to task command adapter module.
2. Rewire CLI `transition_task` wrapper to delegate to adapter.
3. Keep existing exception handling and output semantics unchanged.

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

- Added `task_transition_command(task_file, to_state, reason, artifact_id)` to [src/devflow/task_commands.py](src/devflow/task_commands.py).
- Rewired `transition_task` wrapper in [src/devflow/cli.py](src/devflow/cli.py) to delegate to adapter.
- Preserved exception handling and transition output format exactly.

Verification passed:
- `PYTHONPATH=src python3 -m unittest tests/test_cli.py -q`
- `PYTHONPATH=src python3 -m unittest tests/test_dag.py -q`
