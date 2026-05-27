# Task: 021 - CLI split chunk 18 lifecycle impact adapter
Status: COMPLETED
Goal: cli_module_deepening
Plan: 2026-05-27-devflow-agentic-control-plane-implementation-plan.md
Assigned Agent: vscode
Owner Lock: vscode-session-2026-05-27
Risk: LOW
Branch: devflow/task-021-vscode
Touched Files:
- src/devflow/lifecycle_commands.py
- src/devflow/cli.py

## 1. Objective

Move init/status/impact command logic into a dedicated lifecycle adapter module so CLI remains parser/dispatch focused.

## 2. Allowed Files

- src/devflow/lifecycle_commands.py
- src/devflow/cli.py

## 3. Do Not Touch

- .env
- production secrets
- unrelated source files

## 4. Required Context

- Preserve current output and exit behavior for init/status/impact commands.
- Keep refactor narrow and behavior-neutral.

## 5. Implementation Instructions

1. Add lifecycle commands module with init/status/impact implementations.
2. Rewire CLI wrappers to delegate.
3. Remove stale imports in CLI after extraction.

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

- Added lifecycle command module [src/devflow/lifecycle_commands.py](src/devflow/lifecycle_commands.py) containing:
	- `init_workspace_command(...)`
	- `status_workspace_command()`
	- `impact_command_impl(...)`
- Rewired [src/devflow/cli.py](src/devflow/cli.py):
	- `init_workspace()` delegates to lifecycle command
	- `status_workspace()` delegates to lifecycle command
	- `impact_command(...)` delegates to lifecycle command
- Removed now-redundant in-CLI implementations and stale imports.

Verification passed:
- `PYTHONPATH=src python3 -m unittest tests/test_cli.py -q`
- `PYTHONPATH=src python3 -m unittest tests/test_dag.py -q`
