from __future__ import annotations

import sys
from pathlib import Path
import pytest

from devflow.control_room.worker_adapter import get_worker_adapter
from devflow.control_room.models import WorkerInput
from devflow.control_room.manual_worker import ManualWorkerAdapter


def test_get_manual_worker_adapter() -> None:
    adapter = get_worker_adapter("manual")
    assert isinstance(adapter, ManualWorkerAdapter)
    assert adapter.name == "manual"


def test_manual_worker_non_interactive(tmp_path: Path) -> None:
    workspace_path = tmp_path / "workspace"
    log_file = tmp_path / "logs" / "worker.log"
    result_file = tmp_path / "result.md"

    worker_input = WorkerInput(
        task_id="task-manual-1",
        repo_root=tmp_path,
        workspace_path=workspace_path,
        task_file=tmp_path / "task.yaml",
        context_file=tmp_path / "events.jsonl",
        status_file=tmp_path / "task.yaml",
        questions_file=tmp_path / "questions.jsonl",
        result_file=result_file,
        log_file=log_file,
        command=["manual", "task"],
        timeout_seconds=60,
    )

    adapter = ManualWorkerAdapter()
    
    result = adapter.run(worker_input)

    assert result.status == "complete"
    assert "Awaiting human" in result.summary
    assert result.exit_code == 0
    assert log_file.exists()
    
    log_content = log_file.read_text(encoding="utf-8")
    assert "=== Manual Worker Escalation for Task task-manual-1 ===" in log_content
    assert "Awaiting human manual execution..." in log_content


def test_manual_worker_interactive_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    workspace_path = tmp_path / "workspace"
    log_file = tmp_path / "logs" / "worker.log"
    result_file = tmp_path / "result.md"

    worker_input = WorkerInput(
        task_id="task-manual-2",
        repo_root=tmp_path,
        workspace_path=workspace_path,
        task_file=tmp_path / "task.yaml",
        context_file=tmp_path / "events.jsonl",
        status_file=tmp_path / "task.yaml",
        questions_file=tmp_path / "questions.jsonl",
        result_file=result_file,
        log_file=log_file,
        command=["manual", "task"],
        timeout_seconds=60,
    )

    adapter = ManualWorkerAdapter()

    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    if hasattr(sys.stdin, "_mocked"):
        monkeypatch.setattr(sys.stdin, "_mocked", False)

    import builtins
    monkeypatch.setattr(builtins, "input", lambda prompt="": "")

    result = adapter.run(worker_input)

    assert result.status == "complete"
    assert result.summary == "Manual work completed by user"
    assert result.exit_code == 0
    assert log_file.exists()


def test_manual_worker_interactive_cancelled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    workspace_path = tmp_path / "workspace"
    log_file = tmp_path / "logs" / "worker.log"
    result_file = tmp_path / "result.md"

    worker_input = WorkerInput(
        task_id="task-manual-3",
        repo_root=tmp_path,
        workspace_path=workspace_path,
        task_file=tmp_path / "task.yaml",
        context_file=tmp_path / "events.jsonl",
        status_file=tmp_path / "task.yaml",
        questions_file=tmp_path / "questions.jsonl",
        result_file=result_file,
        log_file=log_file,
        command=["manual", "task"],
        timeout_seconds=60,
    )

    adapter = ManualWorkerAdapter()

    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    if hasattr(sys.stdin, "_mocked"):
        monkeypatch.setattr(sys.stdin, "_mocked", False)

    import builtins
    def mock_input_interrupt(prompt=""):
        raise KeyboardInterrupt()
    monkeypatch.setattr(builtins, "input", mock_input_interrupt)

    result = adapter.run(worker_input)

    assert result.status == "worker_failed"
    assert result.summary == "Manual session cancelled by user"
    assert result.exit_code == 1
    assert log_file.exists()
