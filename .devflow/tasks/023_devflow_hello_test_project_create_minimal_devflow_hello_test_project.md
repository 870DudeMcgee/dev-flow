# Task: 023_devflow_hello_test_project - Create minimal Devflow hello test project
Status: COMPLETED
Goal: vscode_devflow_smoke_project
Plan:
Assigned Agent: vscode
Owner Lock: copilot-2026-05-27-devflow-hello
Risk: LOW
Branch: devflow/task-023_devflow_hello_test_project-vscode
Touched Files:
- examples/devflow-hello/README.md
- examples/devflow-hello/hello.py
- examples/devflow-hello/test_hello.py
- README.md
- docs/agent-handoff.md
- docs/roadmap.md

## 1. Objective

Create a tiny dependency-free project that can prove the Devflow workflow with a real red/green verification loop.

## 2. Allowed Files

- examples/devflow-hello/**
- README.md
- docs/agent-handoff.md
- docs/roadmap.md

## 3. Do Not Touch

- .env
- production secrets
- unrelated files outside Allowed Files

## 4. Required Context

- Keep the smoke project outside the main `src/devflow` package.
- Avoid dependencies so any orchestrator can run it with system Python.
- Use a narrow verification command: `python3 examples/devflow-hello/test_hello.py`.

## 5. Implementation Instructions

1. Add a failing unittest for the desired greeting behavior.
2. Implement the minimal greeting helper and script entrypoint.
3. Document the smoke project in its local README and repo overview docs.

## 6. Patch Protocol

Unified diff only.

## 7. Verification Commands

- python3 examples/devflow-hello/test_hello.py

## 8. Failure Handling

- Patch apply failure: stop and report
- Protected file touched: stop immediately
- Verification failure: rollback and report

## 9. Execution Results

```diff
# Add unified diff here.
```

## 10. Final Report

Completed.

- Added `examples/devflow-hello/hello.py` with `build_greeting(...)` and a script entrypoint.
- Added `examples/devflow-hello/test_hello.py` with two unittest checks.
- Added `examples/devflow-hello/README.md` and repo overview notes.
- Confirmed the expected red failure before implementation: `ModuleNotFoundError: No module named 'hello'`.

Verification passed:
- `python3 examples/devflow-hello/hello.py`
- `python3 examples/devflow-hello/test_hello.py`
- `git diff --check`
- `PYTHONPATH=src python3 -m unittest tests/test_cli.py -q`
- `PYTHONPATH=src python3 -m devflow status`
