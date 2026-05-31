from __future__ import annotations

import json
from pathlib import Path
import pytest
from typer.testing import CliRunner

from devflow.control_room.persistence import save_task, get_task
from devflow.control_room.service import create_task
from devflow.control_room.scorecard import generate_scorecard, save_scorecard
from devflow.cli import app


def test_scorecard_metrics_and_saving(tmp_path: Path) -> None:
    # 1. Initialize structures
    (tmp_path / ".devflow/tasks").mkdir(parents=True)
    (tmp_path / ".devflow/workspaces").mkdir(parents=True)

    # 2. Create task
    task = create_task(tmp_path, "Clean up documentation files")
    task_dir_path = tmp_path / ".devflow/tasks" / task.id
    task.status = "complete"
    task.verification_status = "passed"
    save_task(task_dir_path, task)

    # Add verification events
    events_file = task_dir_path / "events.jsonl"
    events_file.write_text('{"event": "verification_finished", "status": "passed"}\n', encoding="utf-8")

    # Run scorecard
    scorecard_res = generate_scorecard(tmp_path, task.id)
    sc = scorecard_res["scorecard"]

    assert sc["task_id"] == task.id
    assert sc["first_run_pass"] is True
    assert sc["boundary_violations"] is False
    assert sc["frontier_escalation_needed"] is False
    assert sc["overall_quality_rating"] == 1.0

    # Save and verify
    save_scorecard(tmp_path, task.id, scorecard_res)
    yaml_file = task_dir_path / "scorecard.yaml"
    assert yaml_file.exists()
    yaml_content = yaml_file.read_text(encoding="utf-8")
    assert "scorecard:" in yaml_content
    assert "first_run_pass: true" in yaml_content


def test_scorecard_cli_command(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # 1. Initialize structures
    (tmp_path / ".devflow/tasks").mkdir(parents=True)
    (tmp_path / ".devflow/workspaces").mkdir(parents=True)

    # 2. Create task
    task = create_task(tmp_path, "Clean up documentation in PRODUCT_NORTH_STAR.md")
    task_dir_path = tmp_path / ".devflow/tasks" / task.id
    save_task(task_dir_path, task)

    # Monkeypatch Cwd to point to our tmp_path
    monkeypatch.chdir(tmp_path)

    runner = CliRunner()
    result = runner.invoke(app, ["task", "scorecard", task.id])

    assert result.exit_code == 0
    assert "Compiled routing-quality scorecard for task" in result.output
    assert "Wrote scorecard.yaml" in result.output

    # Check files exist
    yaml_file = task_dir_path / "scorecard.yaml"
    assert yaml_file.exists()
