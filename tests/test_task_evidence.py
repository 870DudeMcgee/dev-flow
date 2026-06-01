"""Tests for `devflow task evidence` CLI command.

Tests:
1. task with qwen-planner run.json appears in evidence summary
2. task with qwen-planner and gemma-reviewer shows both
3. failed/timeout run prints warning
4. verified task shows verification status
5. missing workspace fails clearly
6. legacy qwen-response.md/gemma-review.md artifacts are discovered
7. command is read-only
"""
from __future__ import annotations

import os
import tempfile
import json
from pathlib import Path

from typer.testing import CliRunner

from devflow.cli import app

runner = CliRunner()


def test_task_evidence_qwen_run_json() -> None:
    """Verifies task with qwen-planner run.json appears in evidence summary."""
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)

            runner.invoke(app, ["task", "create", "test task 1"])
            
            # Create a run.json for qwen-planner
            worker_dir = Path(".devflow/workspaces/task-0001/local-workers/qwen-planner")
            worker_dir.mkdir(parents=True, exist_ok=True)
            
            run_data = {
                "task_id": "task-0001",
                "worker_name": "qwen-planner",
                "model": "qwen3.6:latest",
                "command": ["ollama", "run", "qwen3.6:latest"],
                "started_at": "2026-06-01T12:00:00Z",
                "finished_at": "2026-06-01T12:03:04Z",
                "duration_seconds": 184.2,
                "timeout_seconds": 600,
                "exit_code": 0,
                "status": "success",
                "response_path": ".devflow/workspaces/task-0001/local-workers/qwen-planner/response.md",
            }
            (worker_dir / "run.json").write_text(json.dumps(run_data), encoding="utf-8")
            (worker_dir / "response.md").write_text("Planner response content", encoding="utf-8")

            result = runner.invoke(app, ["task", "evidence", "task-0001"])
            assert result.exit_code == 0, result.output
            assert "Task: task-0001 test task 1" in result.output
            assert "Status: created" in result.output
            assert "Local workers:" in result.output
            assert "qwen-planner" in result.output
            assert "success" in result.output
            assert "184s" in result.output
            assert "response.md" in result.output
            assert "Artifacts:" in result.output
            assert ".devflow/workspaces/task-0001/local-workers/qwen-planner/response.md" in result.output
        finally:
            os.chdir(old_cwd)


def test_task_evidence_qwen_and_gemma() -> None:
    """Verifies task with qwen-planner and gemma-reviewer shows both."""
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)

            runner.invoke(app, ["task", "create", "test task 2"])
            
            # Setup qwen-planner
            qwen_dir = Path(".devflow/workspaces/task-0001/local-workers/qwen-planner")
            qwen_dir.mkdir(parents=True, exist_ok=True)
            qwen_data = {
                "task_id": "task-0001",
                "worker_name": "qwen-planner",
                "model": "qwen3.6:latest",
                "duration_seconds": 184.0,
                "status": "success",
                "response_path": "local-workers/qwen-planner/response.md",
            }
            (qwen_dir / "run.json").write_text(json.dumps(qwen_data), encoding="utf-8")
            (qwen_dir / "response.md").touch()

            # Setup gemma-reviewer
            gemma_dir = Path(".devflow/workspaces/task-0001/local-workers/gemma-reviewer")
            gemma_dir.mkdir(parents=True, exist_ok=True)
            gemma_data = {
                "task_id": "task-0001",
                "worker_name": "gemma-reviewer",
                "model": "gemma4:latest",
                "duration_seconds": 61.2,
                "status": "success",
                "response_path": "local-workers/gemma-reviewer/response.md",
            }
            (gemma_dir / "run.json").write_text(json.dumps(gemma_data), encoding="utf-8")
            (gemma_dir / "response.md").touch()

            result = runner.invoke(app, ["task", "evidence", "task-0001"])
            assert result.exit_code == 0, result.output
            assert "qwen-planner" in result.output
            assert "184s" in result.output
            assert "gemma-reviewer" in result.output
            assert "61s" in result.output
        finally:
            os.chdir(old_cwd)


def test_task_evidence_failed_timeout_warning() -> None:
    """Verifies failed/timeout runs print warnings and missing input worker logs."""
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)

            runner.invoke(app, ["task", "create", "test task 3"])
            
            # Setup a failed planner
            qwen_dir = Path(".devflow/workspaces/task-0001/local-workers/qwen-planner")
            qwen_dir.mkdir(parents=True, exist_ok=True)
            qwen_data = {
                "task_id": "task-0001",
                "worker_name": "qwen-planner",
                "model": "qwen3.6:latest",
                "duration_seconds": 10.0,
                "status": "failed",
                "response_path": "local-workers/qwen-planner/response.md",
                "error_message": "Exit code 1",
            }
            (qwen_dir / "run.json").write_text(json.dumps(qwen_data), encoding="utf-8")
            (qwen_dir / "response.md").touch()

            # Setup a timeout gemma-reviewer
            gemma_dir = Path(".devflow/workspaces/task-0001/local-workers/gemma-reviewer")
            gemma_dir.mkdir(parents=True, exist_ok=True)
            gemma_data = {
                "task_id": "task-0001",
                "worker_name": "gemma-reviewer",
                "model": "gemma4:latest",
                "duration_seconds": 600.0,
                "status": "timeout",
                "response_path": "local-workers/gemma-reviewer/response.md",
                "error_message": "Local worker 'gemma-reviewer' timed out after 600 seconds. Missing input worker output: qwen-planner",
            }
            (gemma_dir / "run.json").write_text(json.dumps(gemma_data), encoding="utf-8")
            (gemma_dir / "response.md").touch()

            result = runner.invoke(app, ["task", "evidence", "task-0001"])
            assert result.exit_code == 0, result.output
            assert "Warnings:" in result.output
            assert "- failed worker run: qwen-planner" in result.output
            assert "- timeout worker run: gemma-reviewer" in result.output
            assert "- missing input-worker output for: gemma-reviewer" in result.output
        finally:
            os.chdir(old_cwd)


def test_task_evidence_verified_status() -> None:
    """Verifies verified task shows verification status and command."""
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)

            runner.invoke(app, ["task", "create", "test task 4"])
            
            # Setup a passed verification
            t_dir = Path(".devflow/tasks/task-0001")
            t_dir.mkdir(parents=True, exist_ok=True)
            verification_data = {
                "schema_version": 1,
                "task_id": "task-0001",
                "command": "pytest tests/test_task_open.py -q",
                "status": "passed",
                "exit_code": 0,
            }
            (t_dir / "verification.json").write_text(json.dumps(verification_data), encoding="utf-8")

            # Need to touch workspace so checking it passes
            ws_dir = Path(".devflow/workspaces/task-0001")
            ws_dir.mkdir(parents=True, exist_ok=True)

            result = runner.invoke(app, ["task", "evidence", "task-0001"])
            assert result.exit_code == 0, result.output
            assert "Verification:" in result.output
            assert "passed  pytest tests/test_task_open.py -q" in result.output
            assert "unverified task" not in result.output
        finally:
            os.chdir(old_cwd)


def test_task_evidence_missing_workspace() -> None:
    """Verifies missing workspace fails clearly."""
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)

            runner.invoke(app, ["task", "create", "test task 5"])
            
            # Remove workspace folder
            import shutil
            shutil.rmtree(".devflow/workspaces/task-0001")

            result = runner.invoke(app, ["task", "evidence", "task-0001"])
            assert result.exit_code == 1, result.output
            assert "Error: Task workspace not found at" in result.output
        finally:
            os.chdir(old_cwd)


def test_task_evidence_legacy_artifacts() -> None:
    """Verifies legacy qwen-response.md/gemma-review.md artifacts are discovered and prioritized."""
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)

            runner.invoke(app, ["task", "create", "test task 6"])
            
            ws_dir = Path(".devflow/workspaces/task-0001")
            ws_dir.mkdir(parents=True, exist_ok=True)
            
            # Legacy files
            (ws_dir / "qwen-response.md").write_text("qwen response", encoding="utf-8")
            (ws_dir / "gemma-review.md").write_text("gemma review", encoding="utf-8")

            result = runner.invoke(app, ["task", "evidence", "task-0001"])
            assert result.exit_code == 0, result.output
            assert "Artifacts:" in result.output
            assert "qwen-response.md" in result.output
            assert "gemma-review.md" in result.output
        finally:
            os.chdir(old_cwd)


def test_task_evidence_read_only() -> None:
    """Verifies devflow task evidence is read-only and task info is unchanged."""
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)

            runner.invoke(app, ["task", "create", "test task 7"])
            
            ws_dir = Path(".devflow/workspaces/task-0001")
            ws_dir.mkdir(parents=True, exist_ok=True)

            yaml_path = Path(".devflow/tasks/task-0001/task.yaml")
            mtime_before = yaml_path.stat().st_mtime

            result = runner.invoke(app, ["task", "evidence", "task-0001"])
            assert result.exit_code == 0, result.output

            mtime_after = yaml_path.stat().st_mtime
            # Ensure task.yaml was not modified
            assert mtime_before == mtime_after
        finally:
            os.chdir(old_cwd)
