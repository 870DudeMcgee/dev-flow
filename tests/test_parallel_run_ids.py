from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any
from unittest.mock import patch

from typer.testing import CliRunner

from devflow.cli import app
from devflow.control_room.service import get_task
from devflow.control_room.local_ollama_worker import find_latest_worker_evidence
from devflow.control_room.locks import task_mutation_lock, TaskLockError

runner = CliRunner()


def _create_task(title: str) -> None:
    result = runner.invoke(app, ["task", "create", title])
    assert result.exit_code == 0, result.output


def test_two_runs_same_worker_different_evidence_directories(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.chdir(tmp_path)
    _create_task("Isolated runs test")

    # Run 1
    with patch("devflow.control_room.local_ollama_worker.subprocess.run") as run_mock:
        run_mock.return_value = subprocess.CompletedProcess(
            ["ollama", "run", "qwen3.6:latest"],
            0,
            stdout="first response",
            stderr="",
        )
        result1 = runner.invoke(app, ["task", "local", "task-0001", "--worker", "qwen-planner"])
        assert result1.exit_code == 0

    # Run 2
    time.sleep(0.01)
    with patch("devflow.control_room.local_ollama_worker.subprocess.run") as run_mock:
        run_mock.return_value = subprocess.CompletedProcess(
            ["ollama", "run", "qwen3.6:latest"],
            0,
            stdout="second response",
            stderr="",
        )
        result2 = runner.invoke(app, ["task", "local", "task-0001", "--worker", "qwen-planner"])
        assert result2.exit_code == 0

    workspace = tmp_path / ".devflow" / "workspaces" / "task-0001"
    worker_dir = workspace / "local-workers" / "qwen-planner"

    run_dirs = sorted(list(worker_dir.glob("run_*")), key=lambda d: (d / "run.json").stat().st_mtime)
    assert len(run_dirs) == 2, f"Should have exactly 2 run subdirectories, got: {run_dirs}"
    assert run_dirs[0] != run_dirs[1]

    # Verify content isolation
    assert (run_dirs[0] / "response.md").read_text(encoding="utf-8") == "first response"
    assert (run_dirs[1] / "response.md").read_text(encoding="utf-8") == "second response"


def test_two_different_workers_do_not_overwrite_each_other(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.chdir(tmp_path)
    _create_task("Two workers test")

    with patch("devflow.control_room.local_ollama_worker.subprocess.run") as run_mock:
        run_mock.return_value = subprocess.CompletedProcess(
            ["ollama", "run", "qwen3.6:latest"],
            0,
            stdout="planner plan content",
            stderr="",
        )
        result1 = runner.invoke(app, ["task", "local", "task-0001", "--worker", "qwen-planner"])
        assert result1.exit_code == 0

    with patch("devflow.control_room.local_ollama_worker.subprocess.run") as run_mock:
        run_mock.return_value = subprocess.CompletedProcess(
            ["ollama", "run", "qwen3.6:latest"],
            0,
            stdout="implementer patch content",
            stderr="",
        )
        result2 = runner.invoke(app, ["task", "local", "task-0001", "--worker", "qwen-implementer"])
        assert result2.exit_code == 0

    workspace = tmp_path / ".devflow" / "workspaces" / "task-0001"

    # Verify separate structures exist and are not modified
    planner_dir, planner_resp = find_latest_worker_evidence(workspace, "qwen-planner")
    impl_dir, impl_resp = find_latest_worker_evidence(workspace, "qwen-implementer")

    assert planner_dir is not None
    assert impl_dir is not None
    assert "local-workers/qwen-planner" in str(planner_dir)
    assert "local-workers/qwen-implementer" in str(impl_dir)

    assert planner_resp.read_text(encoding="utf-8") == "planner plan content"
    assert impl_resp.read_text(encoding="utf-8") == "implementer patch content"


def test_reviewer_fallback_picks_latest_run(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.chdir(tmp_path)
    _create_task("Reviewer fallback test")

    # Write old planner run
    with patch("devflow.control_room.local_ollama_worker.subprocess.run") as run_mock:
        run_mock.return_value = subprocess.CompletedProcess(
            ["ollama", "run", "qwen3.6:latest"],
            0,
            stdout="planner plan v1",
            stderr="",
        )
        runner.invoke(app, ["task", "local", "task-0001", "--worker", "qwen-planner"])

    time.sleep(0.01)

    # Write new planner run
    with patch("devflow.control_room.local_ollama_worker.subprocess.run") as run_mock:
        run_mock.return_value = subprocess.CompletedProcess(
            ["ollama", "run", "qwen3.6:latest"],
            0,
            stdout="planner plan v2 (latest)",
            stderr="",
        )
        runner.invoke(app, ["task", "local", "task-0001", "--worker", "qwen-planner"])

    # Run reviewer with fallback to planner
    with patch("devflow.control_room.local_ollama_worker.subprocess.run") as run_mock:
        run_mock.return_value = subprocess.CompletedProcess(
            ["ollama", "run", "gemma4:latest"],
            0,
            stdout="reviewer verdict",
            stderr="",
        )
        runner.invoke(app, ["task", "local", "task-0001", "--worker", "gemma-reviewer"])

    workspace = tmp_path / ".devflow" / "workspaces" / "task-0001"
    gemma_dir, _ = find_latest_worker_evidence(workspace, "gemma-reviewer")
    assert gemma_dir is not None
    prompt = (gemma_dir / "prompt.md").read_text(encoding="utf-8")

    assert "Input worker: qwen-planner" in prompt
    assert "planner plan v2 (latest)" in prompt
    assert "planner plan v1" not in prompt


def test_local_evidence_runs_do_not_mark_task_verified_or_promotion_ready(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.chdir(tmp_path)
    _create_task("Verification test")

    # Check initially not run/ready
    task = get_task(tmp_path, "task-0001")
    assert task.verification_status == "not_run"

    # Run local worker
    with patch("devflow.control_room.local_ollama_worker.subprocess.run") as run_mock:
        run_mock.return_value = subprocess.CompletedProcess(
            ["ollama", "run", "qwen3.6:latest"],
            0,
            stdout="planner response",
            stderr="",
        )
        runner.invoke(app, ["task", "local", "task-0001", "--worker", "qwen-planner"])

    # Verify task state on disk
    task = get_task(tmp_path, "task-0001")
    assert task.verification_status == "not_run"
    assert task.status != "verified"

    # Verify merge readiness does not say ready
    mr_path = tmp_path / ".devflow" / "tasks" / "task-0001" / "merge-readiness.json"
    assert mr_path.exists()
    mr_data = json.loads(mr_path.read_text(encoding="utf-8"))
    assert mr_data["ready"] is False
    assert any("verification status" in r for r in mr_data["reasons"])


def test_concurrency_and_locks_are_not_weakened(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.chdir(tmp_path)
    _create_task("Locking test")

    # Verify that shell execution / verify / promote locks still prevent state mutations
    with task_mutation_lock(tmp_path, "task-0001", "promote") as lock_dir:
        # Try to promote again, should raise TaskLockError
        try:
            with task_mutation_lock(tmp_path, "task-0001", "promote"):
                assert False, "Should raise TaskLockError"
        except TaskLockError:
            pass

        # Try to run verify, should raise TaskLockError
        try:
            with task_mutation_lock(tmp_path, "task-0001", "verify"):
                assert False, "Should raise TaskLockError"
        except TaskLockError:
            pass

        # Try to run apply-patch, should raise TaskLockError
        try:
            with task_mutation_lock(tmp_path, "task-0001", "apply-patch"):
                assert False, "Should raise TaskLockError"
        except TaskLockError:
            pass
