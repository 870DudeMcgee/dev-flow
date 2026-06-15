from __future__ import annotations

from pathlib import Path

from devflow.control_room.persistence import get_task
from devflow.df_telegram_bridge import run_telegram_to_devflow_pipeline


def test_telegram_bridge_creates_valid_tasks_and_workspaces(tmp_path: Path) -> None:
    result = run_telegram_to_devflow_pipeline("smoke test", tmp_path)

    assert result["status"] == "ok"
    assert result["goal_id"] == "G-0001"
    assert result["task_ids"] == ["task-0001", "task-0002"]

    for task_id in result["task_ids"]:
        task = get_task(tmp_path, task_id)
        assert task.status == "created"
        assert task.verification_status == "not_run"
        assert task.verification_command == "test -f .devflow/goals/G-0001/success.json"
        assert (tmp_path / task.workspace).is_dir()
        assert result["dispatch"][task_id]["status"] == "created"
