from __future__ import annotations

import os
import tempfile
from pathlib import Path

from typer.testing import CliRunner

from devflow.cli import app
from devflow.control_room.persistence import get_task
from devflow.control_room.persistence import save_task
from devflow.control_room.paths import task_dir
from devflow.control_room.service import create_task
from devflow.control_room.supervisor import (
    build_supervisor_command,
    is_runnable_status,
    select_runnable_tasks,
)


runner = CliRunner()


def test_supervisor_selects_only_created_tasks() -> None:
    with _temp_project() as root:
        runnable = create_task(root, "runnable")
        skipped_statuses = [
            "running",
            "verified",
            "verification_failed",
            "failed",
            "blocked",
        ]
        for status in skipped_statuses:
            task = create_task(root, f"skip {status}")
            task.status = status
            save_task(task_dir(root, task.id), task)

        selected = select_runnable_tasks(root)

        assert [task.id for task in selected] == [runnable.id]


def test_supervisor_filters_selection_by_task_id() -> None:
    with _temp_project() as root:
        first = create_task(root, "first")
        second = create_task(root, "second")

        selected = select_runnable_tasks(root, task_id=second.id)

        assert [task.id for task in selected] == [second.id]
        assert is_runnable_status(first.status)


def test_supervisor_task_id_filter_skips_non_runnable_status() -> None:
    with _temp_project() as root:
        task = create_task(root, "blocked")
        task.status = "blocked"
        save_task(task_dir(root, task.id), task)

        selected = select_runnable_tasks(root, task_id=task.id)

        assert selected == []


def test_supervisor_builds_task_scoped_command_environment() -> None:
    with _temp_project() as root:
        task = create_task(root, "command envelope")

        command = build_supervisor_command(root, task.id)

        assert command.task_id == "task-0001"
        assert command.command == ["scripts/run-ollama-task"]
        assert command.env == {
            "DEVFLOW_TASK_ID": "task-0001",
            "DEVFLOW_TASK_DIR": ".devflow/tasks/task-0001",
            "DEVFLOW_WORKSPACE": ".devflow/workspaces/task-0001",
        }


def test_supervisor_command_accepts_worker_command_override() -> None:
    with _temp_project() as root:
        task = create_task(root, "command override")

        command = build_supervisor_command(root, task.id, worker_command="/bin/echo")

        assert command.command == ["/bin/echo"]


def test_supervise_once_runs_requested_task_through_shell_worker() -> None:
    with _temp_project() as root:
        first = create_task(root, "first")
        second = create_task(root, "second")
        worker = root / "worker.sh"
        worker.write_text(
            "#!/bin/sh\n"
            "printf '%s\\n%s\\n%s\\n' \"$DEVFLOW_TASK_ID\" \"$DEVFLOW_TASK_DIR\" \"$DEVFLOW_WORKSPACE\" > env.txt\n",
            encoding="utf-8",
        )
        worker.chmod(0o755)

        result = runner.invoke(
            app,
            ["supervise", "--once", "--task", second.id, "--worker-command", str(worker)],
        )

        assert result.exit_code == 0, result.output
        assert "task-0002: complete" in result.output
        assert get_task(root, first.id).status == "created"
        assert get_task(root, second.id).status == "complete"
        assert (root / ".devflow/workspaces/task-0002/env.txt").read_text(encoding="utf-8") == (
            "task-0002\n"
            ".devflow/tasks/task-0002\n"
            ".devflow/workspaces/task-0002\n"
        )


def test_supervise_once_prints_when_no_tasks_are_runnable() -> None:
    with _temp_project() as root:
        task = create_task(root, "already running")
        task.status = "running"
        save_task(task_dir(root, task.id), task)

        result = runner.invoke(app, ["supervise", "--once"])

        assert result.exit_code == 0, result.output
        assert "No runnable tasks." in result.output


def test_supervise_requires_once_for_first_slice() -> None:
    with _temp_project():
        result = runner.invoke(app, ["supervise"])

        assert result.exit_code == 1, result.output
        assert "supervise currently requires --once" in result.output


class _temp_project:
    def __enter__(self) -> Path:
        self._old_cwd = Path.cwd()
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        os.chdir(self.root)
        Path("project.txt").write_text("main checkout\n", encoding="utf-8")
        return self.root

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        os.chdir(self._old_cwd)
        self._tmp.cleanup()
