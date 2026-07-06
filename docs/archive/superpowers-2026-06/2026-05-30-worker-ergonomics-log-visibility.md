# Worker Ergonomics And Log Visibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make local shell/Ollama workers easier to write and keep dashboard/latest-log output readable when worker tools emit terminal spinners or ANSI control sequences.

**Architecture:** Keep runtime changes inside `src/devflow/control_room/`. Add one repo-root environment variable to the existing supervisor command envelope, then centralize latest-log cleanup in a small control-room helper used by worker execution, verification, and status projection display. Keep shell workers as the only execution backend.

**Tech Stack:** Python, Typer CLI, pytest, existing Dev-Flow filesystem task state.

---

## Scope Guard

This plan only improves the current shell-worker supervisor path:

- Add `DEVFLOW_REPO_ROOT` to supervisor-launched worker environments.
- Preserve existing `DEVFLOW_TASK_ID`, `DEVFLOW_TASK_DIR`, and `DEVFLOW_WORKSPACE` values for compatibility.
- Sanitize `latest_log_line` and dashboard latest text without changing raw `worker.log` or `verify.log`.
- Do not add provider-backed adapters, autonomous routing, daemon mode, web dashboard UI, or automatic promotion.

## File Structure

- Modify `src/devflow/control_room/supervisor.py`: include `DEVFLOW_REPO_ROOT` in `SupervisorCommand.env`.
- Create `src/devflow/control_room/log_sanitizer.py`: strip ANSI escape sequences, terminal control characters, carriage-return progress noise, and spinner-only lines for status surfaces.
- Modify `src/devflow/control_room/shell_worker.py`: use the sanitizer when deriving `WorkerResult.latest_log_line`.
- Modify `src/devflow/control_room/verification.py`: use the sanitizer when deriving verification latest lines.
- Modify `src/devflow/control_room/status_projection.py`: sanitize persisted `latest_log_line` defensively before dashboard/show projection uses it.
- Modify `tests/test_supervisor_loop.py`: prove `DEVFLOW_REPO_ROOT` is available and usable from a worker running inside the task workspace.
- Create `tests/test_log_sanitizer.py`: focused unit coverage for ANSI/control cleanup and latest-line selection.
- Modify `tests/test_control_room_shell.py`: add one dashboard/projection regression test for noisy persisted latest log lines.

## Task 1: Repo Root In Supervisor Worker Envelope

**Files:**
- Modify: `src/devflow/control_room/supervisor.py`
- Modify: `tests/test_supervisor_loop.py`

- [ ] **Step 1: Write failing environment test**

In `tests/test_supervisor_loop.py`, update `test_supervisor_builds_task_scoped_command_environment` to expect `DEVFLOW_REPO_ROOT`:

```python
def test_supervisor_builds_task_scoped_command_environment() -> None:
    with _temp_project() as root:
        task = create_task(root, "command envelope")

        command = build_supervisor_command(root, task.id)

        assert command.task_id == "task-0001"
        assert command.command == ["scripts/run-ollama-task"]
        assert command.env == {
            "DEVFLOW_TASK_ID": "task-0001",
            "DEVFLOW_REPO_ROOT": str(root.resolve()),
            "DEVFLOW_TASK_DIR": ".devflow/tasks/task-0001",
            "DEVFLOW_WORKSPACE": ".devflow/workspaces/task-0001",
        }
```

- [ ] **Step 2: Add failing worker ergonomics test**

Add this test in `tests/test_supervisor_loop.py` after `test_supervise_once_runs_requested_task_through_shell_worker`:

```python
def test_supervise_worker_can_write_task_result_via_repo_root_env() -> None:
    with _temp_project() as root:
        task = create_task(root, "repo root worker")
        worker = root / "worker.sh"
        worker.write_text(
            "#!/bin/sh\n"
            "set -eu\n"
            "test \"$PWD\" = \"$DEVFLOW_REPO_ROOT/$DEVFLOW_WORKSPACE\"\n"
            "printf 'workspace marker\\n' > workspace-marker.txt\n"
            "printf 'task result via repo root\\n' > \"$DEVFLOW_REPO_ROOT/$DEVFLOW_TASK_DIR/result.md\"\n",
            encoding="utf-8",
        )
        worker.chmod(0o755)

        result = runner.invoke(
            app,
            ["supervise", "--once", "--task", task.id, "--worker-command", str(worker)],
        )

        assert result.exit_code == 0, result.output
        assert (root / ".devflow/workspaces/task-0001/workspace-marker.txt").read_text(
            encoding="utf-8"
        ) == "workspace marker\n"
        assert (root / ".devflow/tasks/task-0001/result.md").read_text(
            encoding="utf-8"
        ) == "task result via repo root\n"
```

- [ ] **Step 3: Run tests and verify they fail**

Run:

```bash
.venv/bin/python -m pytest tests/test_supervisor_loop.py -q
```

Expected: fail because `DEVFLOW_REPO_ROOT` is missing from the supervisor command environment and shell worker process environment.

- [ ] **Step 4: Implement repo root env var**

In `src/devflow/control_room/supervisor.py`, update the `env` dictionary in `build_supervisor_command`:

```python
        env={
            "DEVFLOW_TASK_ID": task.id,
            "DEVFLOW_REPO_ROOT": str(root.resolve()),
            "DEVFLOW_TASK_DIR": relative_path(root, task_dir(root, task.id)),
            "DEVFLOW_WORKSPACE": relative_path(root, workspace_path(root, task.id)),
        },
```

- [ ] **Step 5: Run tests and verify green**

Run:

```bash
.venv/bin/python -m pytest tests/test_supervisor_loop.py -q
```

Expected: all `test_supervisor_loop.py` tests pass.

## Task 2: Central Latest-Log Sanitizer

**Files:**
- Create: `src/devflow/control_room/log_sanitizer.py`
- Create: `tests/test_log_sanitizer.py`

- [ ] **Step 1: Write focused sanitizer tests**

Create `tests/test_log_sanitizer.py`:

```python
from __future__ import annotations

from pathlib import Path

from devflow.control_room.log_sanitizer import latest_visible_log_line, sanitize_log_line


def test_sanitize_log_line_strips_ansi_and_control_sequences() -> None:
    raw = "\x1b[?2026h\x1b[?25l\x1b[1Ghello\x1b[K\x1b[?25h\x1b[?2026l"

    assert sanitize_log_line(raw) == "hello"


def test_sanitize_log_line_drops_spinner_only_lines() -> None:
    assert sanitize_log_line("⠙ ⠹ ⠸ ⠼") == ""


def test_latest_visible_log_line_skips_progress_noise(tmp_path: Path) -> None:
    log = tmp_path / "worker.log"
    log.write_text(
        "$ /bin/sh -c run-local-model\n"
        "real status line\n"
        "\x1b[?2026h\x1b[1G⠙ \x1b[K\x1b[?2026l\n",
        encoding="utf-8",
    )

    assert latest_visible_log_line(log) == "real status line"
```

- [ ] **Step 2: Run tests and verify import failure**

Run:

```bash
.venv/bin/python -m pytest tests/test_log_sanitizer.py -q
```

Expected: fail because `devflow.control_room.log_sanitizer` does not exist.

- [ ] **Step 3: Implement sanitizer helper**

Create `src/devflow/control_room/log_sanitizer.py`:

```python
from __future__ import annotations

import re
from pathlib import Path


ANSI_ESCAPE_RE = re.compile(r"\x1b(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
SPINNER_CHARS = set("⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏")


def sanitize_log_line(line: str | None) -> str:
    if not line:
        return ""
    cleaned = ANSI_ESCAPE_RE.sub("", line)
    cleaned = cleaned.replace("\r", " ")
    cleaned = CONTROL_CHAR_RE.sub("", cleaned)
    normalized = " ".join(cleaned.split())
    if normalized and set(normalized.replace(" ", "")) <= SPINNER_CHARS:
        return ""
    return normalized


def latest_visible_log_line(path: Path) -> str:
    if not path.exists():
        return ""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    for line in reversed(lines):
        visible = sanitize_log_line(line)
        if visible:
            return visible
    return ""
```

- [ ] **Step 4: Run tests and verify green**

Run:

```bash
.venv/bin/python -m pytest tests/test_log_sanitizer.py -q
```

Expected: `3 passed`.

## Task 3: Use Sanitizer In Worker And Verification Latest Lines

**Files:**
- Modify: `src/devflow/control_room/shell_worker.py`
- Modify: `src/devflow/control_room/verification.py`
- Test: `tests/test_log_sanitizer.py`
- Test: `tests/test_control_room_shell.py`

- [ ] **Step 1: Add integration tests for worker and verification latest lines**

Append to `tests/test_log_sanitizer.py`:

```python
from devflow.control_room.shell_worker import _latest_log_line as worker_latest_log_line
from devflow.control_room.verification import _latest_log_line as verification_latest_log_line


def test_worker_latest_log_line_uses_visible_sanitized_line(tmp_path: Path) -> None:
    log = tmp_path / "worker.log"
    log.write_text(
        "$ /bin/sh -c run-local-model\n"
        "ready for review\n"
        "\x1b[?2026h\x1b[1G⠙ \x1b[K\x1b[?2026l\n",
        encoding="utf-8",
    )

    assert worker_latest_log_line(log) == "ready for review"


def test_verification_latest_log_line_uses_visible_sanitized_line(tmp_path: Path) -> None:
    log = tmp_path / "verify.log"
    log.write_text(
        "$ /bin/sh -c pytest\n"
        "verification done\n"
        "\x1b[?25l\x1b[1G⠼ \x1b[K\x1b[?25h\n",
        encoding="utf-8",
    )

    assert verification_latest_log_line(log) == "verification done"
```

- [ ] **Step 2: Run targeted tests and verify failure**

Run:

```bash
.venv/bin/python -m pytest tests/test_log_sanitizer.py -q
```

Expected: fail because worker and verification `_latest_log_line` still return the raw last non-empty line.

- [ ] **Step 3: Wire worker latest line to sanitizer**

In `src/devflow/control_room/shell_worker.py`, add the import:

```python
from devflow.control_room.log_sanitizer import latest_visible_log_line
```

Replace the private `_latest_log_line` function body with:

```python
def _latest_log_line(path: Path) -> str:
    return latest_visible_log_line(path)
```

- [ ] **Step 4: Wire verification latest line to sanitizer**

In `src/devflow/control_room/verification.py`, add the import:

```python
from devflow.control_room.log_sanitizer import latest_visible_log_line
```

Replace the private `_latest_log_line` function body with:

```python
def _latest_log_line(path: Path) -> str:
    return latest_visible_log_line(path)
```

- [ ] **Step 5: Run targeted tests and verify green**

Run:

```bash
.venv/bin/python -m pytest tests/test_log_sanitizer.py tests/test_control_room_shell.py -q
```

Expected: sanitizer tests pass and existing shell-worker tests remain green.

## Task 4: Defensively Sanitize Dashboard Projection

**Files:**
- Modify: `src/devflow/control_room/status_projection.py`
- Modify: `tests/test_control_room_shell.py`

- [ ] **Step 1: Write failing dashboard regression test**

Add this test near the existing dashboard/status projection tests in `tests/test_control_room_shell.py`:

```python
def test_dashboard_sanitizes_persisted_noisy_latest_log_line() -> None:
    with _temp_project():
        runner.invoke(app, ["init"])
        created = runner.invoke(app, ["task", "create", "noisy dashboard"])
        assert created.exit_code == 0, created.output

        task = get_task(Path.cwd(), "task-0001")
        task.status = "complete"
        task.worker = "shell"
        task.latest_log_line = "\x1b[?2026h\x1b[1G⠙ \x1b[K\x1b[?2026l"
        task.last_event = "worker_finished"
        save_task(Path(".devflow/tasks/task-0001"), task)

        dashboard = runner.invoke(app, ["dashboard"])

        assert dashboard.exit_code == 0, dashboard.output
        assert "⠙" not in dashboard.output
        assert "\x1b[" not in dashboard.output
        assert "worker_finished" in dashboard.output
```

If `get_task`, `save_task`, or `Path` are not already imported in the test file section, use the existing import pattern already present in `tests/test_control_room_shell.py`.

- [ ] **Step 2: Run failing dashboard test**

Run:

```bash
.venv/bin/python -m pytest tests/test_control_room_shell.py::test_dashboard_sanitizes_persisted_noisy_latest_log_line -q
```

Expected: fail because `TaskStatusProjection.latest` returns the persisted raw `task.latest_log_line`.

- [ ] **Step 3: Sanitize projection latest property**

In `src/devflow/control_room/status_projection.py`, add:

```python
from devflow.control_room.log_sanitizer import sanitize_log_line
```

Replace the `latest` property with:

```python
    @property
    def latest(self) -> str:
        return sanitize_log_line(self.task.latest_log_line) or self.task.last_event or ""
```

- [ ] **Step 4: Run focused projection/dashboard tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_control_room_shell.py::test_dashboard_sanitizes_persisted_noisy_latest_log_line tests/test_control_room_shell.py::test_status_projection_keeps_cli_and_dashboard_on_canonical_state -q
```

Expected: both tests pass.

## Task 5: Local Ollama Smoke Re-Run

**Files:**
- No source files unless a focused verification failure requires a small fix.

- [ ] **Step 1: Run focused test suite**

Run:

```bash
.venv/bin/python -m pytest tests/test_log_sanitizer.py tests/test_supervisor_loop.py tests/test_control_room_shell.py -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Run full test suite**

Run:

```bash
.venv/bin/python -m pytest -q
```

Expected: full test suite passes with the current skip count.

- [ ] **Step 3: Run doctor**

Run:

```bash
.venv/bin/devflow doctor
```

Expected: every check reports `ok`.

- [ ] **Step 4: Create a smoke task**

Run:

```bash
TASK_ID=$(.venv/bin/devflow task create "local worker ergonomics smoke" | sed -n 's/^Created \(task-[^:]*\):.*/\1/p')
```

Expected: prints a task id such as `task-0003`.

- [ ] **Step 5: Run supervisor with repo-root env and quiet Ollama output**

Run:

```bash
.venv/bin/devflow supervise --poll --interval-seconds 0 --max-iterations 2 --task "$TASK_ID" --timeout-seconds 180 -- /bin/sh -c 'set -eu
printf "started local worker\n" > local-worker-smoke.txt
ollama run qwen2.5-coder:14b "Reply in one short sentence for Dev-Flow task $DEVFLOW_TASK_ID." > ollama-output.txt
{
  printf "# Local Worker Ergonomics Smoke\n\n"
  printf "Task: %s\n\n" "$DEVFLOW_TASK_ID"
  printf "Workspace: %s\n\n" "$DEVFLOW_WORKSPACE"
  printf "Model output:\n\n"
  cat ollama-output.txt
} > "$DEVFLOW_REPO_ROOT/$DEVFLOW_TASK_DIR/result.md"'
```

Expected: first poll runs the task and second poll prints `No runnable tasks.` without unreadable spinner text in the CLI latest field.

- [ ] **Step 6: Verify task**

Run:

```bash
.venv/bin/devflow task verify "$TASK_ID" --shell "test -f local-worker-smoke.txt && test -s ollama-output.txt"
```

Expected: `verification passed`.

- [ ] **Step 7: Inspect visibility surfaces**

Run:

```bash
.venv/bin/devflow task show "$TASK_ID"
.venv/bin/devflow dashboard
.venv/bin/devflow task log "$TASK_ID" --tail 20
```

Expected:

- `task show` reports `status: verified`, `verification_status: passed`, and `merge_ready: yes`.
- `dashboard` shows a readable latest line without ANSI escapes or spinner-only text.
- `task log` still preserves raw worker log evidence.

## Self-Review Notes

- Spec coverage: the plan covers repo-root worker ergonomics and terminal-dashboard log visibility.
- Placeholder scan: no deferred implementation steps are left unspecified.
- Type consistency: new helper names are `sanitize_log_line` and `latest_visible_log_line`, and the plan uses those names consistently.
- Boundary check: all runtime source changes stay under `src/devflow/control_room/`; tests and the plan doc are outside runtime code.
