from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from devflow.control_room.service import create_task, get_task
from devflow.control_room.task_local_worker_run import run_task_local_worker


def test_run_task_local_worker_successful_planner_run_updates_task_and_events(tmp_path: Path) -> None:
    task = create_task(tmp_path, "Plan locally")

    with patch("devflow.control_room.local_ollama_worker.subprocess.run") as run_mock:
        run_mock.return_value = subprocess.CompletedProcess(
            ["ollama", "run", "qwen3.6:latest"],
            0,
            stdout="planner body",
            stderr="planner diagnostic\n",
        )

        result = run_task_local_worker(tmp_path, task.id, "qwen-planner")

    assert result.status == "success"
    assert result.exit_code == 0
    assert result.timeout_seconds == 600
    assert run_mock.call_args.kwargs["timeout"] == 600

    updated = get_task(tmp_path, task.id)
    assert updated.status == "complete"
    assert updated.last_event == "local_worker_finished"
    assert updated.last_exit_code == 0
    assert updated.latest_log_line == "planner diagnostic"
    assert updated.log_path == _relative(tmp_path, result.stderr_path)
    assert updated.result_path == _relative(tmp_path, result.response_path)
    assert updated.finished_at == result.finished_at

    started, finished = _local_worker_events(tmp_path, task.id)
    assert started["event"] == "local_worker_started"
    assert started["worker_name"] == "qwen-planner"
    assert started["model"] == "qwen3.6:latest"
    assert started["artifact_dir"] == _relative(tmp_path, result.artifact_dir)
    assert started["input_worker"] is None
    assert started["run_id"] == result.run_id
    assert finished["event"] == "local_worker_finished"
    assert finished["worker_name"] == "qwen-planner"
    assert finished["model"] == "qwen3.6:latest"
    assert finished["status"] == "success"
    assert finished["exit_code"] == 0
    assert finished["run_id"] == result.run_id
    assert finished["run_json_path"] == _relative(tmp_path, result.run_json_path)
    assert finished["response_path"] == _relative(tmp_path, result.response_path)
    assert finished["stderr_path"] == _relative(tmp_path, result.stderr_path)


def test_run_task_local_worker_missing_input_worker_marks_task_failed(tmp_path: Path) -> None:
    task = create_task(tmp_path, "Review missing planner")

    with patch("devflow.control_room.local_ollama_worker.subprocess.run") as run_mock:
        result = run_task_local_worker(
            tmp_path,
            task.id,
            "gemma-reviewer",
            input_worker="qwen-planner",
        )

    run_mock.assert_not_called()
    assert result.status == "failed"
    assert result.exit_code == 1
    assert result.error_message is not None
    assert "Missing input worker output" in result.error_message

    updated = get_task(tmp_path, task.id)
    assert updated.status == "worker_failed"
    assert updated.last_exit_code == 1
    assert updated.latest_log_line == result.error_message
    assert updated.log_path == _relative(tmp_path, result.stderr_path)
    assert updated.result_path == _relative(tmp_path, result.response_path)
    assert result.error_message in result.stderr_path.read_text(encoding="utf-8")

    started, finished = _local_worker_events(tmp_path, task.id)
    assert started["event"] == "local_worker_started"
    assert started["worker_name"] == "gemma-reviewer"
    assert started["model"] == "gemma4:latest"
    assert started["input_worker"] == "qwen-planner"
    assert started["run_id"] == result.run_id
    assert finished["event"] == "local_worker_finished"
    assert finished["worker_name"] == "gemma-reviewer"
    assert finished["status"] == "failed"
    assert finished["exit_code"] == 1
    assert finished["run_id"] == result.run_id


def test_run_task_local_worker_validates_timeout_and_worker_name(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Local worker timeout must be greater than zero"):
        run_task_local_worker(tmp_path, "task-0001", "qwen-planner", timeout_seconds=0)

    with pytest.raises(ValueError, match="Local worker timeout must be greater than zero"):
        run_task_local_worker(tmp_path, "task-0001", "qwen-planner", timeout_seconds=-1)

    with pytest.raises(ValueError, match="Unknown local worker 'not-real'"):
        run_task_local_worker(tmp_path, "task-0001", "not-real")


def test_service_run_local_model_task_remains_stable_facade(tmp_path: Path) -> None:
    from devflow.control_room import service

    sentinel = object()
    with patch("devflow.control_room.service.run_task_local_worker", return_value=sentinel) as delegate:
        result = service.run_local_model_task(
            tmp_path,
            "task-0001",
            "qwen-planner",
            input_worker="previous-worker",
            timeout_seconds=42,
        )

    assert result is sentinel
    delegate.assert_called_once_with(
        tmp_path,
        "task-0001",
        "qwen-planner",
        input_worker="previous-worker",
        timeout_seconds=42,
    )


def test_run_task_local_worker_refreshes_git_worktree_dirty_state(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    task = create_task(tmp_path, "Dirty git worktree", git_worktree=True)

    def fake_ollama_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        cwd = Path(kwargs["cwd"])
        (cwd / "dirty-from-local-worker.txt").write_text("dirty\n", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout="planner body", stderr="")

    with patch("devflow.control_room.local_ollama_worker.subprocess.run", side_effect=fake_ollama_run):
        result = run_task_local_worker(tmp_path, task.id, "qwen-planner")

    assert result.status == "success"
    updated = get_task(tmp_path, task.id)
    assert updated.workspace_dirty is True

    git_evidence_path = tmp_path / ".devflow" / "tasks" / task.id / "workers" / "shell" / "git.json"
    git_evidence = json.loads(git_evidence_path.read_text(encoding="utf-8"))
    assert git_evidence["dirty"] is True
    assert git_evidence["task_id"] == task.id
    assert git_evidence["worker_id"] == "shell"


def _local_worker_events(root: Path, task_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    events_path = root / ".devflow" / "tasks" / task_id / "events.jsonl"
    events = [
        json.loads(line)
        for line in events_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    local_events = [event for event in events if event["event"].startswith("local_worker_")]
    assert len(local_events) == 2
    return local_events[0], local_events[1]


def _relative(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _init_git_repo(root: Path) -> None:
    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=root, check=True)
    (root / "README.md").write_text("base\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=root, check=True, capture_output=True, text=True)
    subprocess.run(["git", "branch", "-M", "main"], cwd=root, check=True)
