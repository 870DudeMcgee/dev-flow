from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from devflow.cli import app
from devflow.control_room.persistence import save_task
from devflow.control_room.service import create_task


def test_stable_routing_evidence_commands_resolve_ancestor_project_root(
    tmp_path: Path,
    monkeypatch,
) -> None:
    (tmp_path / ".devflow/tasks").mkdir(parents=True)
    (tmp_path / ".devflow/workspaces").mkdir(parents=True)
    task = create_task(tmp_path, "Clean up documentation")
    save_task(tmp_path / ".devflow/tasks" / task.id, task)
    nested = tmp_path / "src" / "devflow" / "control_room"
    nested.mkdir(parents=True)
    monkeypatch.chdir(nested)

    runner = CliRunner()
    commands = [
        ["task", "fit", task.id, "--json"],
        ["task", "scout", task.id, "--role", "risk", "--json"],
        ["task", "route", task.id, "--json"],
        ["task", "scorecard", task.id, "--json"],
    ]

    for command in commands:
        result = runner.invoke(app, command)
        assert result.exit_code == 0, result.output
        assert json.loads(result.output)["task_id"] == task.id

    task_dir = tmp_path / ".devflow/tasks" / task.id
    assert (task_dir / "task-fit.yaml").exists()
    assert (task_dir / "scout-risk.yaml").exists()
    assert (task_dir / "routing-decision.yaml").exists()
    assert (task_dir / "routing-quality-scorecard.yaml").exists()
