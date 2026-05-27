# Task: 020 - CLI split chunk 17 admin adapter cluster
Status: COMPLETED
Goal: cli_module_deepening
Plan: 2026-05-27-devflow-agentic-control-plane-implementation-plan.md
Assigned Agent: vscode
Owner Lock: vscode-session-2026-05-27
Risk: MEDIUM
Branch: devflow/task-020-vscode
Touched Files:
- src/devflow/admin_commands.py
- src/devflow/cli.py

## 1. Objective

Move doctor/init-adapters and adapter-template generation cluster out of CLI into a dedicated admin commands module.

## 2. Allowed Files

- src/devflow/admin_commands.py
- src/devflow/cli.py

## 3. Do Not Touch

- .env
- production secrets
- unrelated source files

## 4. Required Context

- Preserve output and behavior for doctor and init-adapters commands.
- Keep generated file content identical.

## 5. Implementation Instructions

1. Create admin command module with doctor/init-adapters/template helpers and content generators.
2. Rewire CLI doctor and init-adapters commands to delegate.
3. Keep init workspace behavior by delegating template writes to the new module.

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

- Added dedicated admin command module [src/devflow/admin_commands.py](src/devflow/admin_commands.py) containing:
	- orchestrator template generation helpers
	- `doctor_command_impl()`
	- `init_adapters_command_impl()`
	- all adapter content generators used by init-adapters
- Rewired [src/devflow/cli.py](src/devflow/cli.py):
	- `doctor_command()` delegates to `doctor_command_impl()`
	- `init_adapters_command(...)` delegates to `init_adapters_command_impl(...)`
	- init workspace template write path uses `write_orchestrator_templates()` from admin module

Verification passed:
- `PYTHONPATH=src python3 -m unittest tests/test_cli.py -q`
- `PYTHONPATH=src python3 -m unittest tests/test_dag.py -q`
