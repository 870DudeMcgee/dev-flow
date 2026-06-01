"""Tests for `devflow task open` CLI command.

Tests:
1. Finds qwen-response.md in a task workspace.
2. Finds gemma-review.md in a task workspace.
3. Prefers local-workers/<worker>/response.md when --worker is provided.
4. --raw prefers response.raw.md.
5. --list prints candidates without opening.
6. Missing task workspace fails clearly.
7. Path resolution cannot escape the workspace.
8. Platform open command is mocked; tests must not actually open applications.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from typer.testing import CliRunner

from devflow.cli import app
from devflow.control_room.service import get_task

runner = CliRunner()


def test_finds_qwen_response() -> None:
    """Verifies devflow task open task-0001 finds and opens qwen-response.md."""
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)

            runner.invoke(app, ["task", "create", "test task 1"])
            
            # Setup qwen-response.md under workspaces/task-0001/
            ws_dir = Path(".devflow/workspaces/task-0001")
            ws_dir.mkdir(parents=True, exist_ok=True)
            qwen_file = ws_dir / "qwen-response.md"
            qwen_file.write_text("Qwen response", encoding="utf-8")

            # Mock subprocess.run to verify it tries to open the correct file
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0)
                
                result = runner.invoke(app, ["task", "open", "task-0001"])
                assert result.exit_code == 0, result.output
                assert ".devflow/workspaces/task-0001/qwen-response.md" in result.output
                
                # Verify mock was called with darwin's open, or linux's xdg-open depending on target/mock
                mock_run.assert_called_once()
                args, _ = mock_run.call_args
                assert str(qwen_file.resolve()) in args[0]
        finally:
            os.chdir(old_cwd)


def test_finds_gemma_review() -> None:
    """Verifies devflow task open task-0001 finds and opens gemma-review.md."""
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)

            runner.invoke(app, ["task", "create", "test task 2"])
            
            ws_dir = Path(".devflow/workspaces/task-0001")
            ws_dir.mkdir(parents=True, exist_ok=True)
            review_file = ws_dir / "gemma-review.md"
            review_file.write_text("Gemma review", encoding="utf-8")

            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0)
                
                result = runner.invoke(app, ["task", "open", "task-0001"])
                assert result.exit_code == 0, result.output
                assert ".devflow/workspaces/task-0001/gemma-review.md" in result.output
                
                mock_run.assert_called_once()
                args, _ = mock_run.call_args
                assert str(review_file.resolve()) in args[0]
        finally:
            os.chdir(old_cwd)


def test_prefers_worker() -> None:
    """Verifies --worker prefers local-workers/<worker>/response.md."""
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)

            runner.invoke(app, ["task", "create", "test task 3"])
            
            ws_dir = Path(".devflow/workspaces/task-0001")
            ws_dir.mkdir(parents=True, exist_ok=True)
            
            # Create a general qwen-response.md and a worker specific gemma response
            qwen_file = ws_dir / "qwen-response.md"
            qwen_file.write_text("Qwen response", encoding="utf-8")
            
            worker_dir = ws_dir / "local-workers" / "gemma-reviewer"
            worker_dir.mkdir(parents=True, exist_ok=True)
            gemma_file = worker_dir / "response.md"
            gemma_file.write_text("Gemma response", encoding="utf-8")

            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0)
                
                # Call with --worker gemma-reviewer
                result = runner.invoke(app, ["task", "open", "task-0001", "--worker", "gemma-reviewer"])
                assert result.exit_code == 0, result.output
                assert ".devflow/workspaces/task-0001/local-workers/gemma-reviewer/response.md" in result.output
                
                mock_run.assert_called_once()
                args, _ = mock_run.call_args
                assert str(gemma_file.resolve()) in args[0]
        finally:
            os.chdir(old_cwd)


def test_raw_prefers_response_raw() -> None:
    """Verifies --raw prefers response.raw.md."""
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)

            runner.invoke(app, ["task", "create", "test task 4"])
            
            ws_dir = Path(".devflow/workspaces/task-0001")
            ws_dir.mkdir(parents=True, exist_ok=True)
            
            worker_dir = ws_dir / "local-workers" / "qwen-planner"
            worker_dir.mkdir(parents=True, exist_ok=True)
            
            response_file = worker_dir / "response.md"
            response_file.write_text("Qwen formatted", encoding="utf-8")
            
            raw_file = worker_dir / "response.raw.md"
            raw_file.write_text("Qwen raw", encoding="utf-8")

            # Test 1: without --raw, prefers response.md
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0)
                result = runner.invoke(app, ["task", "open", "task-0001", "--worker", "qwen-planner"])
                assert result.exit_code == 0, result.output
                assert "response.md" in result.output
                assert "response.raw.md" not in result.output

            # Test 2: with --raw, prefers response.raw.md
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0)
                result = runner.invoke(app, ["task", "open", "task-0001", "--worker", "qwen-planner", "--raw"])
                assert result.exit_code == 0, result.output
                assert "response.raw.md" in result.output
                assert "Opened: .devflow/workspaces/task-0001/local-workers/qwen-planner/response.raw.md" in result.output
        finally:
            os.chdir(old_cwd)


def test_list_prints_candidates() -> None:
    """Verifies --list prints candidates without opening them."""
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)

            runner.invoke(app, ["task", "create", "test task 5"])
            
            ws_dir = Path(".devflow/workspaces/task-0001")
            ws_dir.mkdir(parents=True, exist_ok=True)
            
            (ws_dir / "qwen-response.md").write_text("qwen", encoding="utf-8")
            (ws_dir / "gemma-review.md").write_text("gemma", encoding="utf-8")

            with patch("subprocess.run") as mock_run:
                result = runner.invoke(app, ["task", "open", "task-0001", "--list"])
                assert result.exit_code == 0, result.output
                
                # Should print list
                assert "Candidate output files in priority order:" in result.output
                assert "qwen-response.md" in result.output
                assert "gemma-review.md" in result.output
                
                # Should NOT call open
                mock_run.assert_not_called()
        finally:
            os.chdir(old_cwd)


def test_missing_workspace_fails() -> None:
    """Verifies missing task or missing workspace fails clearly."""
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)

            # Test missing task
            result = runner.invoke(app, ["task", "open", "task-9999"])
            assert result.exit_code == 1
            assert "Error: Task 'task-9999' not found." in result.output

            # Test missing workspace dir
            runner.invoke(app, ["task", "create", "test task 6"])
            # delete workspaces dir
            import shutil
            shutil.rmtree(".devflow/workspaces/task-0001")
            
            result = runner.invoke(app, ["task", "open", "task-0001"])
            assert result.exit_code == 1
            assert "Error: Task workspace not found at" in result.output
        finally:
            os.chdir(old_cwd)


def test_path_resolution_traversal_safety() -> None:
    """Verifies paths outside the task workspace cannot escape."""
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)

            runner.invoke(app, ["task", "create", "test task 7"])
            
            ws_dir = Path(".devflow/workspaces/task-0001")
            ws_dir.mkdir(parents=True, exist_ok=True)
            
            # Setup a symlink to outside the workspace
            outside_file = Path(tmp) / "outside.md"
            outside_file.write_text("Outside", encoding="utf-8")
            
            # create a symlink to outside_file
            (ws_dir / "outside_link.md").symlink_to(outside_file)

            with patch("subprocess.run") as mock_run:
                # With traversal check, it should ignore outside_link.md or fail because no valid candidates are found
                result = runner.invoke(app, ["task", "open", "task-0001"])
                assert result.exit_code == 1
                assert "Error: No candidate output files found" in result.output
                mock_run.assert_not_called()
        finally:
            os.chdir(old_cwd)


def test_mocked_open_command() -> None:
    """Verifies the system open call handles exceptions gracefully by printing path."""
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)

            runner.invoke(app, ["task", "create", "test task 8"])
            
            ws_dir = Path(".devflow/workspaces/task-0001")
            ws_dir.mkdir(parents=True, exist_ok=True)
            (ws_dir / "response.md").write_text("response", encoding="utf-8")

            # Mock subprocess.run to raise exception (representing opening failure)
            with patch("subprocess.run", side_effect=Exception("Failed to spawn")):
                result = runner.invoke(app, ["task", "open", "task-0001"])
                # Command should still exit successfully (read-only print fallback), but notify the failure
                assert result.exit_code == 0, result.output
                assert "Failed to open automatically. Exact path:" in result.output
                assert "response.md" in result.output
        finally:
            os.chdir(old_cwd)
