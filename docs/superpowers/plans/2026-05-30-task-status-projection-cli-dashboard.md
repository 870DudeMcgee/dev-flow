# Task Status Projection CLI/Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Centralize task status read-model logic for `devflow task list`, `devflow task show`, and `devflow dashboard`; follow-up packet migration was completed after the CLI/dashboard slice stabilized.

**Architecture:** Add one deep read-model module, `src/devflow/control_room/status_projection.py`, that loads a `TaskRecord` plus nearby lifecycle artifacts and resolves canonical precedence once. CLI, dashboard renderers, and TaskPacket verification fallbacks consume the projection instead of independently resolving status and verification precedence.

**Tech Stack:** Python, Typer, Pydantic task models, plain filesystem artifacts, pytest.

---

## Scope Guard

This plan is a read-side refactor only.

In scope:

- Add `src/devflow/control_room/status_projection.py`.
- Update `src/devflow/cli.py` for `task list` and `task show`.
- Update `src/devflow/control_room/dashboard.py`.
- Add focused tests in `tests/test_control_room_shell.py`.

Out of scope:

- Do not edit `src/devflow/control_room/task_packet.py`.
- Do not change lifecycle artifact writes in `service.py`, `persistence.py`, `verification.py`, or `shell_worker.py`.
- Do not add AI adapters, dashboard web UI, databases, model routing, or legacy workflow machinery.
- Do not write new active control-room features outside `src/devflow/control_room/`.

## File Structure

- Create: `src/devflow/control_room/status_projection.py`
  - Owns artifact precedence, display tokens, readiness display, and next-action text for read-only views.
  - Provides `build_task_status_projection(root: Path, task_id: str) -> TaskStatusProjection`.
  - Provides `list_task_status_projections(root: Path) -> list[TaskStatusProjection]`.
- Modify: `src/devflow/cli.py:98-203`
  - Replace inline task list/show artifact reads with projection rendering.
  - Keep current output labels and next-action strings stable.
- Modify: `src/devflow/cli.py:507-543`
  - Remove or stop using `_verify_token()` and `_suggest_next_action()` after equivalent projection methods exist.
- Modify: `src/devflow/control_room/dashboard.py:11-60`
  - Render projections instead of manually reading `summary.json` and `merge-readiness.json`.
- Test: `tests/test_control_room_shell.py`
  - Add regression tests proving CLI/dashboard views share canonical precedence and stay read-only.

---

### Task 1: Add Failing Projection Coverage

**Files:**
- Modify: `tests/test_control_room_shell.py`

- [ ] **Step 1: Add imports if needed**

Inspect the current imports at the top of `tests/test_control_room_shell.py`. If `json`, `Path`, `tempfile`, `os`, and `runner` are already imported, do not duplicate them.

- [ ] **Step 2: Add a failing test for shared canonical projection**

Append this test near the existing summary/dashboard hardening tests:

```python
def test_status_projection_keeps_cli_and_dashboard_on_canonical_state() -> None:
    from devflow.control_room.status_projection import build_task_status_projection

    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            assert runner.invoke(app, ["task", "create", "projection task"]).exit_code == 0
            assert runner.invoke(app, ["task", "run", "task-0001", "--shell", "echo done"]).exit_code == 0
            assert runner.invoke(app, ["task", "verify", "task-0001", "--shell", "echo ok"]).exit_code == 0

            task_path = Path(".devflow/tasks/task-0001")
            (task_path / "summary.json").write_text(
                json.dumps(
                    {
                        "task_id": "task-0001",
                        "title": "projection task",
                        "status": "worker_failed",
                        "workspace_path": ".devflow/workspaces/task-0001",
                        "latest_verification_status": "failed",
                        "latest_verification_exit_code": 99,
                        "latest_verification_log_path": "not-real.log",
                        "merge_ready": False,
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            projection = build_task_status_projection(Path.cwd(), "task-0001")
            assert projection.task.status == "verified"
            assert projection.verification_status == "passed"
            assert projection.verification_exit_code == 0
            assert projection.verification_log_path == ".devflow/tasks/task-0001/logs/verify.log"
            assert projection.merge_ready is True

            listing = runner.invoke(app, ["task", "list"])
            assert listing.exit_code == 0, listing.output
            assert "task-0001" in listing.output
            assert "verified" in listing.output
            assert "passed" in listing.output
            assert "worker_failed" not in listing.output
            assert "failed(exit=99)" not in listing.output

            show = runner.invoke(app, ["task", "show", "task-0001"])
            assert show.exit_code == 0, show.output
            assert "status: verified" in show.output
            assert "verification_status: passed" in show.output
            assert "verification_exit_code: 0" in show.output
            assert "verification_log_path: .devflow/tasks/task-0001/logs/verify.log" in show.output
            assert "suggested_next_action: Task is verified. Review promotion preview, then run 'devflow task promote task-0001' when ready." in show.output
            assert "not-real.log" not in show.output

            dashboard = runner.invoke(app, ["dashboard"])
            assert dashboard.exit_code == 0, dashboard.output
            assert "task-0001" in dashboard.output
            assert "verified" in dashboard.output
            assert "passed" in dashboard.output
            assert "verification_exit_code: 0" in dashboard.output
            assert "verification_log: .devflow/tasks/task-0001/logs/verify.log" in dashboard.output
            assert "merge_ready: yes" in dashboard.output
            assert "worker_failed" not in dashboard.output
            assert "not-real.log" not in dashboard.output
        finally:
            os.chdir(old_cwd)
```

- [ ] **Step 3: Add a failing test for projection read-only behavior**

Append this test near the existing read-only `task show` coverage:

```python
def test_status_projection_views_do_not_mutate_task_artifacts() -> None:
    from devflow.control_room.status_projection import list_task_status_projections

    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            assert runner.invoke(app, ["task", "create", "readonly projection"]).exit_code == 0
            assert runner.invoke(app, ["task", "run", "task-0001", "--shell", "echo done"]).exit_code == 0
            assert runner.invoke(app, ["task", "verify", "task-0001", "--shell", "echo ok"]).exit_code == 0

            task_path = Path(".devflow/tasks/task-0001")
            before = {path: path.read_bytes() for path in task_path.glob("**/*") if path.is_file()}

            projections = list_task_status_projections(Path.cwd())
            assert [projection.task.id for projection in projections] == ["task-0001"]
            assert runner.invoke(app, ["task", "list"]).exit_code == 0
            assert runner.invoke(app, ["task", "show", "task-0001"]).exit_code == 0
            assert runner.invoke(app, ["dashboard"]).exit_code == 0

            after = {path: path.read_bytes() for path in task_path.glob("**/*") if path.is_file()}
            assert after == before
        finally:
            os.chdir(old_cwd)
```

- [ ] **Step 4: Run the focused tests and verify they fail before implementation**

Run:

```bash
.venv/bin/python -m pytest tests/test_control_room_shell.py::test_status_projection_keeps_cli_and_dashboard_on_canonical_state tests/test_control_room_shell.py::test_status_projection_views_do_not_mutate_task_artifacts -q
```

Expected: at least one test fails because `status_projection.py` does not exist and callers have not been migrated.

---

### Task 2: Implement The Status Projection Module

**Files:**
- Create: `src/devflow/control_room/status_projection.py`
- Test: `tests/test_control_room_shell.py`

- [ ] **Step 1: Create the projection module**

Add `src/devflow/control_room/status_projection.py` with this structure:

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from devflow.control_room.models import TaskRecord
from devflow.control_room.paths import task_dir
from devflow.control_room.persistence import get_task, list_tasks
from devflow.control_room.readiness import promotion_readiness_errors


class TaskStatusProjection(BaseModel):
    task: TaskRecord
    task_path: Path
    verification_status: str
    verification_exit_code: int | None
    verification_log_path: str | None
    verification_command: str | None
    merge_ready: bool | None
    readiness_reasons: list[str]
    suggested_next_action: str

    model_config = {"arbitrary_types_allowed": True}

    @property
    def verify_token(self) -> str:
        if self.verification_status == "passed":
            return "passed"
        if self.verification_status == "failed":
            if self.verification_exit_code is not None:
                return f"failed(exit={self.verification_exit_code})"
            return "failed"
        return self.verification_status or "not_run"

    @property
    def latest(self) -> str:
        return self.task.latest_log_line or self.task.last_event or ""


def list_task_status_projections(root: Path) -> list[TaskStatusProjection]:
    return [build_task_status_projection(root, task.id, task=task) for task in list_tasks(root)]


def build_task_status_projection(root: Path, task_id: str, task: TaskRecord | None = None) -> TaskStatusProjection:
    record = task or get_task(root, task_id)
    path = task_dir(root, record.id)
    verification = _read_verification(path / "verification.json", record)
    merge_ready, readiness_reasons = _read_merge_readiness(path / "merge-readiness.json")
    if merge_ready is None:
        promotion_errors = promotion_readiness_errors(record, path)
        readiness_reasons = []
    else:
        promotion_errors = [] if merge_ready else readiness_reasons

    verification_status = _string_or_default(verification.get("status"), record.verification_status)
    verification_exit_code = _int_or_none(verification.get("exit_code"), record.verification_exit_code)
    verification_log_path = _string_or_default(verification.get("log_path"), record.verification_log_path)
    verification_command = _string_or_default(verification.get("command"), record.verification_command)

    return TaskStatusProjection(
        task=record,
        task_path=path,
        verification_status=verification_status,
        verification_exit_code=verification_exit_code,
        verification_log_path=verification_log_path,
        verification_command=verification_command,
        merge_ready=merge_ready,
        readiness_reasons=readiness_reasons,
        suggested_next_action=_suggest_next_action(
            record.status,
            verification_status,
            record.id,
            promotion_ready=not promotion_errors,
        ),
    )


def _read_verification(path: Path, task: TaskRecord) -> dict[str, Any]:
    fallback = {
        "task_id": task.id,
        "status": task.verification_status,
        "exit_code": task.verification_exit_code,
        "log_path": task.verification_log_path,
        "command": task.verification_command,
    }
    if not path.exists():
        return fallback
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return fallback
    if not isinstance(data, dict):
        return fallback
    if data.get("task_id") not in (None, task.id):
        return fallback
    return {**fallback, **data}


def _read_merge_readiness(path: Path) -> tuple[bool | None, list[str]]:
    if not path.exists():
        return None, []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None, []
    if not isinstance(data, dict):
        return None, []
    ready = data.get("ready")
    if not isinstance(ready, bool):
        return None, []
    reasons = data.get("reasons", [])
    if not isinstance(reasons, list):
        reasons = []
    return ready, [str(reason) for reason in reasons]


def _string_or_default(value: Any, default: str | None) -> str | None:
    return value if isinstance(value, str) else default


def _int_or_none(value: Any, default: int | None) -> int | None:
    return value if isinstance(value, int) else default


def _suggest_next_action(
    status: str, verification_status: str, task_id: str, promotion_ready: bool = False
) -> str:
    if status == "created":
        return f"Run the task using 'devflow task run {task_id} --worker shell -- <command>'"
    if status == "running":
        return "Monitor the execution or wait for the task to complete."
    if status == "complete":
        return f"Verify the task using 'devflow task verify {task_id} -- <command>'"
    if status == "promoted":
        return "Task has been promoted. Review main checkout changes, then commit manually if appropriate."
    if status == "verified" and promotion_ready:
        return f"Task is verified. Review promotion preview, then run 'devflow task promote {task_id}' when ready."
    if status == "verified" or verification_status == "passed":
        return "Task is verified, but promotion readiness evidence is incomplete. Re-run verification before promotion."
    if status == "verification_failed" or verification_status == "failed":
        return f"Fix the failure and re-run verification using 'devflow task verify {task_id} -- <command>'"
    if status == "worker_failed":
        return f"Inspect the logs, fix the failure, and re-run using 'devflow task run {task_id} --worker shell -- <command>'"
    if status == "timeout":
        return f"Re-run the task with an increased timeout using 'devflow task run {task_id} --timeout-seconds <seconds> --worker shell -- <command>'"
    if status == "blocked":
        return "Resolve the workspace or safety block before running again."
    return "Check task status and logs for the next logical step."
```

- [ ] **Step 2: Run the focused tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_control_room_shell.py::test_status_projection_keeps_cli_and_dashboard_on_canonical_state tests/test_control_room_shell.py::test_status_projection_views_do_not_mutate_task_artifacts -q
```

Expected: tests still fail because CLI and dashboard do not consume the projection yet.

---

### Task 3: Migrate CLI List And Show

**Files:**
- Modify: `src/devflow/cli.py:98-203`
- Modify: `src/devflow/cli.py:507-543`
- Test: `tests/test_control_room_shell.py`

- [ ] **Step 1: Update imports**

In `src/devflow/cli.py`, import the projection builders:

```python
from devflow.control_room.status_projection import build_task_status_projection, list_task_status_projections
```

- [ ] **Step 2: Update `task_list()`**

Replace the body of `task_list()` with projection rendering:

```python
def task_list() -> None:
    """List tasks from the control-room task files."""
    projections = list_task_status_projections(Path.cwd())
    if not projections:
        typer.echo("No tasks found.")
        return
    typer.echo(f"{'Task':<10} {'Status':<20} {'Verify':<16} {'Updated':<25} Title")
    typer.echo("-" * 97)
    for projection in projections:
        task = projection.task
        typer.echo(
            f"{task.id:<10} {task.status:<20} {projection.verify_token:<16} "
            f"{task.updated_at.isoformat():<25} {task.title}"
        )
```

- [ ] **Step 3: Update `task_show()` verification/readiness fields**

Inside `task_show()`, after loading `task`, create the projection:

```python
projection = build_task_status_projection(Path.cwd(), task_id, task=task)
task_path = projection.task_path
```

Then remove the inline `verification.json` read block and render these fields from the projection:

```python
typer.echo(f"verification_status: {projection.verification_status}")
typer.echo(f"verification_command: {projection.verification_command or ''}")
if projection.verification_exit_code is not None:
    typer.echo(f"verification_exit_code: {projection.verification_exit_code}")
typer.echo(f"verification_log_path: {projection.verification_log_path or ''}")
typer.echo(f"exit_code: {task.last_exit_code if task.last_exit_code is not None else ''}")
typer.echo(f"suggested_next_action: {projection.suggested_next_action}")
```

Replace the `merge-readiness.json` rendering block with:

```python
if projection.merge_ready is not None:
    ready_str = "yes" if projection.merge_ready else "no"
    typer.echo(f"merge_ready: {ready_str}")
    if projection.readiness_reasons:
        typer.echo("readiness_reasons:")
        for reason in projection.readiness_reasons:
            typer.echo(f"  - {reason}")
```

Keep promoted changes, packet artifact status, latest event tail, question tail, and result summary rendering unchanged.

- [ ] **Step 4: Remove unused helpers**

If no references remain, remove `_verify_token()` and `_suggest_next_action()` from `src/devflow/cli.py`.

- [ ] **Step 5: Run focused CLI tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_control_room_shell.py::test_status_projection_keeps_cli_and_dashboard_on_canonical_state tests/test_control_room_shell.py::test_task_show_verification_metadata_and_next_actions tests/test_control_room_shell.py::test_task_show_missing_and_malformed_readiness -q
```

Expected: the new projection test may still fail on dashboard, but `task list` and `task show` assertions should pass.

---

### Task 4: Migrate Dashboard Rendering

**Files:**
- Modify: `src/devflow/control_room/dashboard.py:1-72`
- Test: `tests/test_control_room_shell.py`

- [ ] **Step 1: Update imports**

Replace the `json` import and `list_tasks` import with:

```python
from devflow.control_room.status_projection import list_task_status_projections
```

Keep `Path`, `os`, and `time`.

- [ ] **Step 2: Replace manual artifact reads**

Replace `render_dashboard()` with this projection-based version:

```python
def render_dashboard(repo_root: Path | None = None) -> str:
    root = (repo_root or Path.cwd()).resolve()
    projections = list_task_status_projections(root)
    lines = [
        "Dev-Flow Control Room",
        f"root: {root}",
        "",
        f"{'Task':<10} {'Status':<20} {'Verify':<12} {'Worker':<8} Latest",
        "-" * 82,
    ]
    if not projections:
        lines.append("No tasks found.")
    for projection in projections:
        task = projection.task
        lines.append(
            f"{task.id:<10} {task.status:<20} {projection.verification_status:<12} "
            f"{task.worker:<8} {projection.latest}"
        )
        lines.append(f"  workspace: {task.workspace}")
        if task.log_path:
            lines.append(f"  log: {task.log_path}")
        if task.result_path:
            lines.append(f"  result: {task.result_path}")
        if projection.verification_exit_code is not None:
            lines.append(f"  verification_exit_code: {projection.verification_exit_code}")
        if projection.verification_log_path:
            lines.append(f"  verification_log: {projection.verification_log_path}")
        if projection.merge_ready is not None:
            merge_ready = "yes" if projection.merge_ready else "no"
            lines.append(f"  merge_ready: {merge_ready}")
    return "\n".join(lines) + "\n"
```

Remove `_summary_matches_task()` after the dashboard no longer calls it.

- [ ] **Step 3: Run dashboard-focused tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_control_room_shell.py::test_status_projection_keeps_cli_and_dashboard_on_canonical_state tests/test_control_room_shell.py::test_task_summary_hardening_and_fallbacks -q
```

Expected: pass.

---

### Task 5: Verify The Full Slice

**Files:**
- Modify only files already listed above.

- [ ] **Step 1: Run focused MVP tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_control_room_shell.py tests/test_promote_preview.py -q
```

Expected: pass.

- [ ] **Step 2: Run packet tests as a guardrail**

Run:

```bash
.venv/bin/python -m pytest tests/test_task_packet.py -q
```

Expected: pass. These tests should pass without editing `task_packet.py`.

- [ ] **Step 3: Run full tests**

Run:

```bash
.venv/bin/python -m pytest -q
```

Expected: pass.

- [ ] **Step 4: Check worktree scope**

Run:

```bash
git status --short
```

Expected: only these files are modified or added:

```text
M src/devflow/cli.py
M src/devflow/control_room/dashboard.py
A src/devflow/control_room/status_projection.py
M tests/test_control_room_shell.py
```

This plan file may also appear if it has not already been committed.

---

## Packet Migration Handoff

## Status

complete

## Files Changed

- `src/devflow/control_room/status_projection.py` (new shared read model for CLI/dashboard status projection)
- `src/devflow/cli.py` (consumer of the shared projection for `task list` and `task show`)
- `src/devflow/control_room/dashboard.py` (consumer of the shared projection)
- `src/devflow/control_room/task_packet.py` (consumer of projection-backed task and verification fallbacks while preserving packet-specific redaction and virtualization)
- `tests/test_control_room_shell.py` (CLI/dashboard projection regression coverage)
- `tests/test_task_packet.py` (packet projection fallback regression coverage)

## Verification

- `.venv/bin/python -m pytest tests/test_control_room_shell.py tests/test_task_packet.py -q`: pass.
- `.venv/bin/python -m pytest -q`: pass.

## Risks

- `task_packet.py` still owns packet-specific summary filtering, truncation notes, path virtualization, and secret redaction.
- Projection use is intentionally limited to task loading and verification fallback precedence.

## Next Safe Action

- Review and commit the completed projection plus packet migration slice.
