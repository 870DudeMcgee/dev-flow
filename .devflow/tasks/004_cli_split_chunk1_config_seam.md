# Task: 004 - CLI split chunk 1 config seam
Status: COMPLETED
Goal: cli_module_deepening
Plan: 2026-05-27-devflow-agentic-control-plane-implementation-plan.md
Assigned Agent: vscode
Owner Lock: vscode-session-2026-05-27
Risk: LOW
Branch: devflow/task-004-vscode
Touched Files:
- src/devflow/workspace.py
- src/devflow/cli.py
- src/devflow/agents/runner.py

## 1. Objective

Extract config loading into a dedicated workspace module and remove the agent runner dependency on `devflow.cli` internals, without changing behavior.

## 2. Allowed Files

- src/devflow/workspace.py
- src/devflow/cli.py
- src/devflow/agents/runner.py

## 3. Do Not Touch

- .env
- production secrets
- unrelated source files

## 4. Required Context

- Keep behavior and CLI output unchanged.
- Keep this as a tiny chunk in the CLI split effort.

## 5. Implementation Instructions

1. Add `src/devflow/workspace.py` with `default_config()` and `load_config()`.
2. Update `src/devflow/cli.py` to delegate `_default_config` and `_load_config` to the new module.
3. Update `src/devflow/agents/runner.py` to import `load_config` from `devflow.workspace`.

## 6. Patch Protocol

Unified diff only.

## 7. Verification Commands

- PYTHONPATH=src python3 -m unittest tests/test_cli.py -q
- PYTHONPATH=src python3 -m unittest tests/test_agent_repair.py -q

## 8. Failure Handling

- Patch apply failure: stop and report
- Verification failure: stop and report

## 9. Execution Results

```diff
# Add unified diff here.
```

## 10. Final Report

Completed.

- Added workspace config seam in [src/devflow/workspace.py](src/devflow/workspace.py).
- Delegated CLI config helpers to workspace module in [src/devflow/cli.py](src/devflow/cli.py).
- Removed repair agent dependency on CLI internals in [src/devflow/agents/runner.py](src/devflow/agents/runner.py).
- Verification passed:
	- `PYTHONPATH=src python3 -m unittest tests/test_cli.py -q`
	- `PYTHONPATH=src python3 -m unittest tests/test_agent_repair.py -q`
