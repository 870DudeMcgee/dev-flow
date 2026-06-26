from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock
import urllib.error

import pytest

from devflow.control_room.worker_adapter import UnsupportedWorkerAdapter, get_worker_adapter
from devflow.control_room.models import WorkerInput
from devflow.control_room.openai_chat_worker import OpenAIChatWorkerAdapter


def test_get_openai_chat_worker_adapter_rejects_experimental_runtime() -> None:
    with pytest.raises(UnsupportedWorkerAdapter, match="experimental_readonly"):
        get_worker_adapter("openai_chat")


def test_openai_chat_worker_success(tmp_path: Path) -> None:
    # Initialize mock git repository in tmp_path
    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=tmp_path, capture_output=True)

    # Write a test file and commit it
    test_file = tmp_path / "hello.txt"
    test_file.write_text("Hello World\n", encoding="utf-8")
    subprocess.run(["git", "add", "hello.txt"], cwd=tmp_path, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial commit"], cwd=tmp_path, capture_output=True)

    # Set up task directories
    task_dir = tmp_path / ".devflow" / "tasks" / "task-openaichat-1"
    task_dir.mkdir(parents=True)
    (task_dir / "logs").mkdir(parents=True)

    # Write task.yaml
    (task_dir / "task.yaml").write_text("id: task-openaichat-1\ntitle: Test Task\nstatus: created\n", encoding="utf-8")

    # Set up workspace (copy hello.txt to workspace)
    workspace_path = tmp_path / ".devflow" / "workspaces" / "task-openaichat-1"
    workspace_path.mkdir(parents=True)
    (workspace_path / "hello.txt").write_text("Hello World\n", encoding="utf-8")

    log_file = task_dir / "logs" / "worker.log"
    result_file = task_dir / "result.md"

    worker_input = WorkerInput(
        task_id="task-openaichat-1",
        repo_root=tmp_path,
        workspace_path=workspace_path,
        task_file=task_dir / "task.yaml",
        context_file=task_dir / "events.jsonl",
        status_file=task_dir / "task.yaml",
        questions_file=task_dir / "questions.jsonl",
        result_file=result_file,
        log_file=log_file,
        command=["openai_chat", "task"],
        timeout_seconds=60,
    )

    # Set up context pack JSON
    context_pack_data = {
        "context_pack": {
            "role": "worker",
            "context_layer": "L1",
            "includes": [],
            "excludes": [],
            "estimated_tokens": 100,
            "sources_metadata": [
                {
                    "path": "hello.txt",
                    "authority": "canonical",
                    "mode": "full",
                    "content": "Hello World\n"
                }
            ]
        }
    }
    (task_dir / "context-pack-worker.json").write_text(json.dumps(context_pack_data), encoding="utf-8")

    # Mock OpenAI API response returning a clean ready diff
    mock_response = MagicMock()
    choices_message = {
        "choices": [
            {
                "message": {
                    "content": json.dumps({
                        "status": "ready",
                        "diff": "diff --git a/hello.txt b/hello.txt\n--- a/hello.txt\n+++ b/hello.txt\n@@ -1 +1 @@\n-Hello World\n+Hello beautiful World\n",
                        "touched_paths": ["hello.txt"],
                        "risk": "low",
                        "confidence": 0.95
                    })
                }
            }
        ]
    }
    mock_response.read.return_value = json.dumps(choices_message).encode("utf-8")

    adapter = OpenAIChatWorkerAdapter()

    # Stub build_context_pack to return our dummy pack
    with patch("urllib.request.urlopen") as mock_urlopen, \
         patch("devflow.control_room.openai_chat_worker.build_context_pack", return_value=context_pack_data):
        mock_urlopen.return_value.__enter__.return_value = mock_response

        result = adapter.run(worker_input)

        assert result.status == "complete"
        assert "Worker completed successfully" in result.summary
        assert result.exit_code == 0
        assert log_file.exists()
        
        # Verify that workspace file hello.txt was NOT modified!
        assert (workspace_path / "hello.txt").read_text(encoding="utf-8") == "Hello World\n"
        
        # Verify proposed patch was written to evidence file
        patch_file = task_dir / "agents" / "default_agent" / "proposal.patch"
        assert patch_file.exists()
        assert "Hello beautiful World" in patch_file.read_text(encoding="utf-8")


def test_openai_chat_worker_connection_failure(tmp_path: Path) -> None:
    # Set up task directories
    task_dir = tmp_path / ".devflow" / "tasks" / "task-openaichat-2"
    task_dir.mkdir(parents=True)
    (task_dir / "logs").mkdir(parents=True)

    workspace_path = tmp_path / ".devflow" / "workspaces" / "task-openaichat-2"
    workspace_path.mkdir(parents=True)

    log_file = task_dir / "logs" / "worker.log"
    result_file = task_dir / "result.md"

    worker_input = WorkerInput(
        task_id="task-openaichat-2",
        repo_root=tmp_path,
        workspace_path=workspace_path,
        task_file=task_dir / "task.yaml",
        context_file=task_dir / "events.jsonl",
        status_file=task_dir / "task.yaml",
        questions_file=task_dir / "questions.jsonl",
        result_file=result_file,
        log_file=log_file,
        command=["openai_chat", "task"],
        timeout_seconds=60,
    )

    adapter = OpenAIChatWorkerAdapter()

    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Connection refused")), \
         patch("devflow.control_room.openai_chat_worker.build_context_pack", return_value={}):
        result = adapter.run(worker_input)

        assert result.status == "worker_failed"
        assert "Error connecting to OpenAI Chat agent" in result.summary
        assert result.exit_code == 1
        assert log_file.exists()


def test_openai_chat_worker_blocked_status(tmp_path: Path) -> None:
    # Set up task directories
    task_dir = tmp_path / ".devflow" / "tasks" / "task-openaichat-3"
    task_dir.mkdir(parents=True)
    (task_dir / "logs").mkdir(parents=True)

    workspace_path = tmp_path / ".devflow" / "workspaces" / "task-openaichat-3"
    workspace_path.mkdir(parents=True)

    log_file = task_dir / "logs" / "worker.log"
    result_file = task_dir / "result.md"

    worker_input = WorkerInput(
        task_id="task-openaichat-3",
        repo_root=tmp_path,
        workspace_path=workspace_path,
        task_file=task_dir / "task.yaml",
        context_file=task_dir / "events.jsonl",
        status_file=task_dir / "task.yaml",
        questions_file=task_dir / "questions.jsonl",
        result_file=result_file,
        log_file=log_file,
        command=["openai_chat", "task"],
        timeout_seconds=60,
    )

    mock_response = MagicMock()
    choices_message = {
        "choices": [
            {
                "message": {
                    "content": json.dumps({
                        "status": "blocked",
                        "blocked_reason": "prohibited pattern found",
                        "diff": "",
                        "touched_paths": [],
                        "risk": "critical",
                        "confidence": 0.0
                    })
                }
            }
        ]
    }
    mock_response.read.return_value = json.dumps(choices_message).encode("utf-8")

    adapter = OpenAIChatWorkerAdapter()

    with patch("urllib.request.urlopen") as mock_urlopen, \
         patch("devflow.control_room.openai_chat_worker.build_context_pack", return_value={}):
        mock_urlopen.return_value.__enter__.return_value = mock_response

        result = adapter.run(worker_input)

        assert result.status == "blocked"
        assert "prohibited pattern found" in result.summary
        assert result.exit_code == 1
