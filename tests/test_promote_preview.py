from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from devflow.cli import app
from devflow.control_room.service import get_task

runner = CliRunner()


def test_promote_preview_missing_task() -> None:
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            res = runner.invoke(app, ["task", "promote-preview", "task-9999"])
            assert res.exit_code == 1
            assert "Task not found" in res.output or "task-9999" in res.output
        finally:
            os.chdir(old_cwd)


def test_promote_preview_missing_workspace() -> None:
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            created = runner.invoke(app, ["task", "create", "test task"])
            assert created.exit_code == 0

            workspace_dir = Path(".devflow/workspaces/task-0001")
            assert workspace_dir.exists()
            shutil.rmtree(workspace_dir)

            res = runner.invoke(app, ["task", "promote-preview", "task-0001"])
            assert res.exit_code == 1
            assert "Workspace directory does not exist" in res.output
        finally:
            os.chdir(old_cwd)


def test_promote_preview_unsafe_workspace() -> None:
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            created = runner.invoke(app, ["task", "create", "test task"])
            assert created.exit_code == 0

            yaml_path = Path(".devflow/tasks/task-0001/task.yaml")
            content = yaml_path.read_text(encoding="utf-8")
            content = content.replace('workspace: ".devflow/workspaces/task-0001"', 'workspace: "/usr/bin"')
            yaml_path.write_text(content, encoding="utf-8")

            res = runner.invoke(app, ["task", "promote-preview", "task-0001"])
            assert res.exit_code == 1
            assert "Refusing unsafe task workspace" in res.output
        finally:
            os.chdir(old_cwd)


def test_promote_preview_added_modified_deleted() -> None:
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            Path("stay.txt").write_text("unchanged content\n", encoding="utf-8")
            Path("modify.txt").write_text("old content\n", encoding="utf-8")
            Path("delete.txt").write_text("to be deleted\n", encoding="utf-8")

            created = runner.invoke(app, ["task", "create", "preview-test"])
            assert created.exit_code == 0

            workspace_dir = Path(".devflow/workspaces/task-0001")
            assert workspace_dir.exists()

            Path(workspace_dir / "added.txt").write_text("new file\n", encoding="utf-8")
            Path(workspace_dir / "modify.txt").write_text("new content\n", encoding="utf-8")
            Path(workspace_dir / "delete.txt").unlink()

            ignored_dir = workspace_dir / ".venv"
            ignored_dir.mkdir()
            Path(ignored_dir / "venv_file.txt").write_text("ignored\n", encoding="utf-8")

            task_yaml_path = Path(".devflow/tasks/task-0001/task.yaml")
            task_yaml_before = task_yaml_path.read_text(encoding="utf-8")

            res = runner.invoke(app, ["task", "promote-preview", "task-0001"])
            assert res.exit_code == 0, res.output

            assert "Added files:" in res.output
            assert "  - added.txt" in res.output
            assert "Modified files:" in res.output
            assert "  - modify.txt" in res.output
            assert "Deleted files:" in res.output
            assert "  - delete.txt" in res.output

            assert "--- Diffs ---" in res.output
            assert "+++ b/added.txt" in res.output
            assert "+new file" in res.output
            assert "--- a/modify.txt" in res.output
            assert "+++ b/modify.txt" in res.output
            assert "-old content" in res.output
            assert "+new content" in res.output
            assert "--- a/delete.txt" in res.output
            assert "-to be deleted" in res.output

            assert "venv_file.txt" not in res.output
            assert ".venv" not in res.output

            assert task_yaml_path.read_text(encoding="utf-8") == task_yaml_before
        finally:
            os.chdir(old_cwd)


def test_promote_preview_no_changes() -> None:
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            Path("file.txt").write_text("content\n", encoding="utf-8")
            created = runner.invoke(app, ["task", "create", "no changes task"])
            assert created.exit_code == 0

            res = runner.invoke(app, ["task", "promote-preview", "task-0001"])
            assert res.exit_code == 0
            assert "No changes to promote" in res.output
        finally:
            os.chdir(old_cwd)
