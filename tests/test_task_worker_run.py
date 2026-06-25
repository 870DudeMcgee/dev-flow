from __future__ import annotations

import json
from pathlib import Path

import pytest

from devflow.control_room.service import create_task, get_task, run_shell_task
from devflow.control_room.task_worker_run import run_task_worker


def test_run_task_worker_successful_shell_run(tmp_path: Path) -> None:
    task = create_task(tmp_path, "direct worker run")

    result = run_task_worker(tmp_path, task.id, ["/bin/sh", "-c", "printf ok > worker.txt"])

    assert result.status == "complete"
    assert result.worker == "shell"
    assert result.last_exit_code == 0
    assert result.log_path == f".devflow/tasks/{task.id}/logs/worker.log"
    assert result.result_path == f".devflow/tasks/{task.id}/result.md"
    assert (tmp_path / ".devflow/workspaces" / task.id / "worker.txt").read_text(encoding="utf-8") == "ok"
    assert not (tmp_path / "worker.txt").exists()


def test_service_run_shell_task_wrapper_compatibility(tmp_path: Path) -> None:
    task = create_task(tmp_path, "service wrapper")

    result = run_shell_task(tmp_path, task.id, ["/bin/sh", "-c", "echo wrapped > wrapped.txt"])

    assert result.status == "complete"
    assert (tmp_path / ".devflow/workspaces" / task.id / "wrapped.txt").read_text(encoding="utf-8") == "wrapped\n"
    events = _event_names(tmp_path, task.id)
    assert events == ["task_created", "worker_started", "worker_finished"]


def test_run_task_worker_refuses_destructive_command(tmp_path: Path) -> None:
    task = create_task(tmp_path, "refuse destructive")

    with pytest.raises(ValueError, match="Refusing obviously destructive command"):
        run_task_worker(tmp_path, task.id, ["/bin/sh", "-c", "rm -rf /"])

    updated = get_task(tmp_path, task.id)
    assert updated.status == "blocked"
    assert "command_refused" in _event_names(tmp_path, task.id)


def test_run_task_worker_refuses_tampered_workspace(tmp_path: Path) -> None:
    task = create_task(tmp_path, "refuse tampered workspace")
    _replace_workspace(tmp_path, task.id, ".")

    with pytest.raises(ValueError, match="Refusing unsafe task workspace"):
        run_task_worker(tmp_path, task.id, ["/bin/sh", "-c", "echo bad > main_checkout_write.txt"])

    assert not (tmp_path / "main_checkout_write.txt").exists()
    updated = get_task(tmp_path, task.id)
    assert updated.status == "blocked"
    assert "workspace_refused" in _event_names(tmp_path, task.id)


def test_run_task_worker_writes_packet_and_result_evidence(tmp_path: Path) -> None:
    task = create_task(tmp_path, "packet and result evidence")

    result = run_task_worker(tmp_path, task.id, ["/bin/sh", "-c", "echo evidence"])

    assert result.status == "complete"
    task_path = tmp_path / ".devflow" / "tasks" / task.id
    packet = json.loads((task_path / "packet.json").read_text(encoding="utf-8"))
    assert packet["task_id"] == task.id
    assert packet["workspace_path"] == "<workspace>"
    result_text = (task_path / "result.md").read_text(encoding="utf-8")
    assert f"# Result: {task.id}" in result_text
    assert "Worker completed successfully" in result_text
    assert "## Command" in result_text


def _replace_workspace(root: Path, task_id: str, workspace: str) -> None:
    task_yaml = root / ".devflow" / "tasks" / task_id / "task.yaml"
    lines = task_yaml.read_text(encoding="utf-8").splitlines()
    updated = [f'workspace: "{workspace}"' if line.startswith("workspace:") else line for line in lines]
    task_yaml.write_text("\n".join(updated) + "\n", encoding="utf-8")


def _event_names(root: Path, task_id: str) -> list[str]:
    events_path = root / ".devflow" / "tasks" / task_id / "events.jsonl"
    return [
        json.loads(line)["event"]
        for line in events_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
