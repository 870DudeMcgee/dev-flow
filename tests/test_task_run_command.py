from __future__ import annotations

from pathlib import Path

import pytest

from devflow.control_room.seed import initialize_seed
from devflow.control_room.service import create_task
from devflow.control_room.task_run_command import (
    TRUSTED_LOCAL_WARNING,
    TaskRunCommandError,
    render_task_run_lines,
    run_task_command,
)


def test_task_run_command_renders_shell_success_lines(tmp_path: Path) -> None:
    task = create_task(tmp_path, "module shell run")

    result = run_task_command(
        tmp_path,
        task.id,
        ["/bin/sh", "-c", "printf ok > module.txt && echo done"],
    )

    assert result.exit_code == 0
    assert result.task.status == "complete"
    assert render_task_run_lines(result) == [
        TRUSTED_LOCAL_WARNING,
        f"{task.id}: complete",
        f"log_path: .devflow/tasks/{task.id}/logs/worker.log",
        f"result_path: .devflow/tasks/{task.id}/result.md",
        "latest_log_line: done",
    ]
    assert (tmp_path / ".devflow/workspaces" / task.id / "module.txt").read_text(encoding="utf-8") == "ok"


def test_task_run_command_returns_failed_worker_exit_code(tmp_path: Path) -> None:
    task = create_task(tmp_path, "module shell failure")

    result = run_task_command(tmp_path, task.id, ["/bin/sh", "-c", "echo bad; exit 7"])

    assert result.exit_code == 7
    assert result.task.status == "worker_failed"
    assert render_task_run_lines(result) == [
        TRUSTED_LOCAL_WARNING,
        f"{task.id}: worker_failed",
        f"log_path: .devflow/tasks/{task.id}/logs/worker.log",
        f"result_path: .devflow/tasks/{task.id}/result.md",
        "latest_log_line: bad",
    ]


def test_task_run_command_renders_project_scoped_task_ref(tmp_path: Path) -> None:
    task = create_task(tmp_path, "module project run")

    result = run_task_command(
        tmp_path,
        task.id,
        ["/bin/sh", "-c", "echo project"],
        project_id="alpha-app",
    )

    assert render_task_run_lines(result)[:3] == [
        TRUSTED_LOCAL_WARNING,
        f"alpha-app:{task.id}: complete",
        f"project_root: {tmp_path}",
    ]


def test_task_run_command_rejects_invalid_worker_with_cli_line(tmp_path: Path) -> None:
    task = create_task(tmp_path, "module invalid worker")

    with pytest.raises(TaskRunCommandError) as excinfo:
        run_task_command(tmp_path, task.id, ["/bin/sh", "-c", "echo no"], worker_adapter="codex")

    assert excinfo.value.exit_code == 1
    assert len(excinfo.value.lines) == 1
    assert "Adapter 'codex' is planned_not_executable and cannot execute" in excinfo.value.lines[0]
    assert "Stable runtime adapters: manual, shell." in excinfo.value.lines[0]


def test_task_run_command_renders_manual_warning_and_handoff_path(tmp_path: Path) -> None:
    initialize_seed(tmp_path)
    task = create_task(tmp_path, "module manual worker")

    result = run_task_command(tmp_path, task.id, [], worker_adapter="devflow-manual-codex-worker")

    assert result.exit_code == 0
    assert result.task.status == "blocked"
    assert "manual_handoff_path: .devflow/tasks/task-0001/agents/devflow-manual-codex-worker/handoff.md" in render_task_run_lines(result)

    direct_manual = create_task(tmp_path, "module direct manual")
    direct_result = run_task_command(tmp_path, direct_manual.id, [], worker_adapter="manual")

    assert render_task_run_lines(direct_result)[0] == "Warning: 'manual' worker is experimental and does not execute work."


def test_task_run_command_renders_registry_backed_ollama_patch_worker_lines(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    initialize_seed(tmp_path)
    task = create_task(tmp_path, "module ollama worker")

    def fake_run_shell_task(
        root: Path,
        task_id: str,
        command: list[str],
        timeout_seconds: int = 60,
        worker_adapter: str = "shell",
        env: dict[str, str] | None = None,
    ):
        assert root == tmp_path
        assert task_id == task.id
        assert command == []
        assert timeout_seconds == 123
        assert worker_adapter == "qwopus-implementer"
        assert env is None
        task.status = "complete"
        task.worker = worker_adapter
        task.last_exit_code = 0
        task.log_path = f".devflow/tasks/{task.id}/agents/qwopus-implementer/logs/worker.log"
        task.result_path = f".devflow/tasks/{task.id}/agents/qwopus-implementer/result.md"
        task.latest_log_line = "Worker completed successfully."
        return task

    monkeypatch.setattr("devflow.control_room.task_run_command.run_shell_task", fake_run_shell_task)

    result = run_task_command(
        tmp_path,
        task.id,
        [],
        worker_adapter="qwopus-implementer",
        timeout_seconds=123,
    )

    assert render_task_run_lines(result) == [
        "worker_mode: registry_backed_local_ollama_patch_worker",
        "worker_note: writes proposal.patch evidence only; Dev-Flow applies patches separately and verifies separately.",
        f"{task.id}: complete",
        f"log_path: .devflow/tasks/{task.id}/agents/qwopus-implementer/logs/worker.log",
        f"result_path: .devflow/tasks/{task.id}/agents/qwopus-implementer/result.md",
        f"agent_packet_path: .devflow/tasks/{task.id}/agents/qwopus-implementer/packet.json",
        f"raw_output_path: .devflow/tasks/{task.id}/agents/qwopus-implementer/raw_output.md",
        f"proposal_patch_path: .devflow/tasks/{task.id}/agents/qwopus-implementer/proposal.patch",
        f"run_metadata_path: .devflow/tasks/{task.id}/agents/qwopus-implementer/run.json",
        f"agent_result_path: .devflow/tasks/{task.id}/agents/qwopus-implementer/result.md",
        f"agent_log_path: .devflow/tasks/{task.id}/agents/qwopus-implementer/logs/worker.log",
        "latest_log_line: Worker completed successfully.",
        f"suggested_next_action: devflow task review-patch {task.id} --agent qwopus-implementer",
    ]
