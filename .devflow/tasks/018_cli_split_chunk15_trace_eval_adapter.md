# Task: 018 - CLI split chunk 15 trace eval adapter
Status: COMPLETED
Goal: cli_module_deepening
Plan: 2026-05-27-devflow-agentic-control-plane-implementation-plan.md
Assigned Agent: vscode
Owner Lock: vscode-session-2026-05-27
Risk: LOW
Branch: devflow/task-018-vscode
Touched Files:
- src/devflow/trace_eval_commands.py
- src/devflow/cli.py

## 1. Objective

Move trace and eval command wrapper behavior into a dedicated adapter module while preserving CLI output and exit semantics.

## 2. Allowed Files

- src/devflow/trace_eval_commands.py
- src/devflow/cli.py

## 3. Do Not Touch

- .env
- production secrets
- unrelated source files

## 4. Required Context

- Preserve output lines and exit behavior for trace list/inspect and eval run/compare commands.
- Keep refactor narrow and behavior-neutral.

## 5. Implementation Instructions

1. Add trace/eval adapter module.
2. Rewire CLI wrappers to delegate.
3. Keep current error handling unchanged.

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

- Added dedicated trace/eval adapter module [src/devflow/trace_eval_commands.py](src/devflow/trace_eval_commands.py) with:
	- `trace_list_command()`
	- `trace_inspect_command(trace_id)`
	- `eval_run_command(role)`
	- `eval_compare_command(prompt_a, prompt_b)`
- Rewired CLI wrappers in [src/devflow/cli.py](src/devflow/cli.py) to delegate to adapter functions.
- Preserved existing output lines and exit semantics.

Verification passed:
- `PYTHONPATH=src python3 -m unittest tests/test_cli.py -q`
- `PYTHONPATH=src python3 -m unittest tests/test_dag.py -q`
