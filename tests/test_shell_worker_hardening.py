from __future__ import annotations

import os
import tempfile
from pathlib import Path
import pytest

from devflow.control_room.shell_worker import ShellWorkerAdapter
from devflow.control_room.models import WorkerInput

def test_shell_worker_environment_filtering() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        workspace_path = tmp_path / "workspace"
        workspace_path.mkdir()
        log_file = tmp_path / "worker.log"
        result_file = tmp_path / "result.md"

        worker_input = WorkerInput(
            task_id="task-env-test",
            repo_root=tmp_path,
            workspace_path=workspace_path,
            task_file=tmp_path / "task.yaml",
            context_file=tmp_path / "events.jsonl",
            status_file=tmp_path / "task.yaml",
            questions_file=tmp_path / "questions.jsonl",
            result_file=result_file,
            log_file=log_file,
            command=["/bin/sh", "-c", "echo \"PATH_VAL=$PATH\"; echo \"SECRET_VAL=$MOCK_SECRET\"; echo \"INPUT_VAL=$MOCK_INPUT\""],
            timeout_seconds=60,
            env={"MOCK_INPUT": "explicit_allowed"}
        )

        os.environ["MOCK_SECRET"] = "parent_secret"
        os.environ["PATH"] = "/usr/bin:/bin"

        try:
            adapter = ShellWorkerAdapter()
            res = adapter.run(worker_input)

            assert res.status == "complete"
            log_content = log_file.read_text(encoding="utf-8")

            assert "PATH_VAL=/usr/bin:/bin" in log_content
            assert "SECRET_VAL=\n" in log_content or "SECRET_VAL=\r\n" in log_content
            assert "INPUT_VAL=explicit_allowed" in log_content

        finally:
            if "MOCK_SECRET" in os.environ:
                del os.environ["MOCK_SECRET"]

def test_shell_worker_custom_env_allowlist() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        workspace_path = tmp_path / "workspace"
        workspace_path.mkdir()
        log_file = tmp_path / "worker.log"
        result_file = tmp_path / "result.md"

        worker_input = WorkerInput(
            task_id="task-env-custom-test",
            repo_root=tmp_path,
            workspace_path=workspace_path,
            task_file=tmp_path / "task.yaml",
            context_file=tmp_path / "events.jsonl",
            status_file=tmp_path / "task.yaml",
            questions_file=tmp_path / "questions.jsonl",
            result_file=result_file,
            log_file=log_file,
            command=["/bin/sh", "-c", "echo \"CUSTOM_VAL=$MY_CUSTOM_VAR\""],
            timeout_seconds=60,
        )

        os.environ["MY_CUSTOM_VAR"] = "custom_allowed_secret"
        os.environ["DEVFLOW_ENV_ALLOWLIST"] = "MY_CUSTOM_VAR"

        try:
            adapter = ShellWorkerAdapter()
            res = adapter.run(worker_input)

            assert res.status == "complete"
            log_content = log_file.read_text(encoding="utf-8")
            assert "CUSTOM_VAL=custom_allowed_secret" in log_content

        finally:
            if "MY_CUSTOM_VAR" in os.environ:
                del os.environ["MY_CUSTOM_VAR"]
            if "DEVFLOW_ENV_ALLOWLIST" in os.environ:
                del os.environ["DEVFLOW_ENV_ALLOWLIST"]

def test_shell_worker_log_size_limit() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        workspace_path = tmp_path / "workspace"
        workspace_path.mkdir()
        log_file = tmp_path / "worker.log"
        result_file = tmp_path / "result.md"

        worker_input = WorkerInput(
            task_id="task-size-test",
            repo_root=tmp_path,
            workspace_path=workspace_path,
            task_file=tmp_path / "task.yaml",
            context_file=tmp_path / "events.jsonl",
            status_file=tmp_path / "task.yaml",
            questions_file=tmp_path / "questions.jsonl",
            result_file=result_file,
            log_file=log_file,
            command=["yes"],
            timeout_seconds=10,
        )

        adapter = ShellWorkerAdapter()
        res = adapter.run(worker_input)

        assert res.status == "worker_failed"
        assert "exceeded limit of 10MB" in res.summary
        assert log_file.exists()
        log_content = log_file.read_text(encoding="utf-8")
        assert "DEVFLOW ERROR" in log_content
        assert "exceeded limit of 10MB" in log_content
