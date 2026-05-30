# Ollama Supervisor Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a minimal supervisor loop that launches local Ollama workers as task-scoped shell commands without adding Codex, model routing, or complex scheduling.

**Architecture:** Keep all active runtime code in `src/devflow/control_room/`. The supervisor reads canonical task files, chooses explicit runnable tasks, and delegates execution to the existing shell-worker service while passing task/workspace paths through environment variables. The task folder is the control envelope; the workspace remains the edit sandbox.

**Tech Stack:** Python, Typer CLI, pytest, existing Dev-Flow filesystem task state.

---

## File Structure

- Create `src/devflow/control_room/supervisor.py`: task selection and command construction for one supervisor pass.
- Modify `src/devflow/control_room/service.py`: expose a narrow function that runs a task with additional environment variables, or keep the environment handling inside `supervisor.py` if the existing shell adapter can support it cleanly.
- Modify `src/devflow/cli.py`: add `devflow supervise --once`, `--task <task_id>`, and `--worker-command <path>`.
- Add `tests/test_supervisor_loop.py`: focused tests for task selection, command environment, skip behavior, and CLI output.

## Task 1: Supervisor Selection Rules

**Files:**
- Create: `src/devflow/control_room/supervisor.py`
- Test: `tests/test_supervisor_loop.py`

- [ ] **Step 1: Write failing tests for runnable task selection**

Add tests that create three task records and assert only `created` tasks are selected. Include `running`, `verified`, `verification_failed`, `failed`, and `blocked` as skipped statuses.

- [ ] **Step 2: Run the failing test**

Run:

```bash
.venv/bin/python -m pytest tests/test_supervisor_loop.py -q
```

Expected: fail because `devflow.control_room.supervisor` does not exist.

- [ ] **Step 3: Implement minimal selection**

Add a small selector in `src/devflow/control_room/supervisor.py`:

```python
RUNNABLE_STATUSES = {"created"}

def is_runnable_status(status: str) -> bool:
    return status in RUNNABLE_STATUSES
```

Add a function that lists tasks through existing persistence/service helpers and filters by status and optional task id.

- [ ] **Step 4: Verify**

Run:

```bash
.venv/bin/python -m pytest tests/test_supervisor_loop.py -q
```

Expected: pass for selection tests.

## Task 2: Task-Scoped Ollama Command Envelope

**Files:**
- Modify: `src/devflow/control_room/supervisor.py`
- Test: `tests/test_supervisor_loop.py`

- [ ] **Step 1: Write failing tests for command environment**

Assert the supervisor builds these environment values for `task-0001`:

```text
DEVFLOW_TASK_ID=task-0001
DEVFLOW_TASK_DIR=.devflow/tasks/task-0001
DEVFLOW_WORKSPACE=.devflow/workspaces/task-0001
```

- [ ] **Step 2: Implement command envelope**

Add a small dataclass:

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class SupervisorCommand:
    task_id: str
    command: list[str]
    env: dict[str, str]
```

Build the command from `--worker-command`, defaulting to `["scripts/run-ollama-task"]`.

- [ ] **Step 3: Verify**

Run:

```bash
.venv/bin/python -m pytest tests/test_supervisor_loop.py -q
```

Expected: pass.

## Task 3: One-Pass CLI

**Files:**
- Modify: `src/devflow/cli.py`
- Modify: `src/devflow/control_room/supervisor.py`
- Test: `tests/test_supervisor_loop.py`

- [ ] **Step 1: Write failing CLI tests**

Use `CliRunner` to assert:

- `devflow supervise --once --task task-0001 --worker-command /bin/echo` runs exactly that task.
- `devflow supervise --once` prints `No runnable tasks.` when none are in `created`.
- Running without `--once` exits nonzero with a clear message for the first slice.

- [ ] **Step 2: Implement CLI command**

Add a top-level Typer command:

```python
@app.command("supervise")
def supervise_command(
    once: bool = typer.Option(False, "--once"),
    task_id: str | None = typer.Option(None, "--task"),
    worker_command: str = typer.Option("scripts/run-ollama-task", "--worker-command"),
) -> None:
    ...
```

Reject missing `--once` for now.

- [ ] **Step 3: Delegate execution through existing shell-worker path**

Call the existing shell-task execution path so logs, events, status, result artifacts, and packet generation stay consistent.

- [ ] **Step 4: Verify**

Run:

```bash
.venv/bin/python -m pytest tests/test_supervisor_loop.py -q
```

Expected: pass.

## Task 4: End-To-End Dogfood Verification

**Files:**
- No new runtime files unless tests reveal a small missing seam.

- [ ] **Step 1: Create a task**

Run:

```bash
TASK_ID=$(.venv/bin/devflow task create "ollama supervisor smoke" | sed -n 's/^Created \(task-[^:]*\):.*/\1/p')
```

- [ ] **Step 2: Run supervisor with a harmless local command**

Run:

```bash
.venv/bin/devflow supervise --once --task "$TASK_ID" --worker-command /bin/echo
```

Expected: task status moves through the existing shell-worker path and `logs/worker.log` exists.

- [ ] **Step 3: Verify task visibility**

Run:

```bash
.venv/bin/devflow task show "$TASK_ID"
.venv/bin/devflow dashboard
```

Expected: CLI surfaces show worker command, status, log path, and latest event.

- [ ] **Step 4: Run focused and full verification**

Run:

```bash
.venv/bin/python -m pytest tests/test_supervisor_loop.py tests/test_control_room_shell.py -q
.venv/bin/devflow doctor
```

Expected: all pass.

## Self-Review Notes

- Scope is intentionally limited to one-pass supervision.
- No Codex agent, web dashboard, scheduler, model router, or automatic promotion is introduced.
- The design keeps task folders as control envelopes and workspaces as edit sandboxes.
