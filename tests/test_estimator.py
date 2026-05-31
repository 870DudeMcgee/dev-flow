from __future__ import annotations

import json
from pathlib import Path
import pytest
from typer.testing import CliRunner

from devflow.control_room.persistence import save_task, get_task
from devflow.control_room.service import create_task
from devflow.control_room.estimator import estimate_task_fit, save_task_fit
from devflow.cli import app


def test_estimator_heuristics_and_saving(tmp_path: Path) -> None:
    # 1. Initialize seed structures
    (tmp_path / ".devflow/tasks").mkdir(parents=True)
    (tmp_path / ".devflow/workspaces").mkdir(parents=True)

    # 2. Create dummy task
    task = create_task(tmp_path, "Fix failing python tests and runtime errors")
    task.verification_command = "pytest tests/test_something.py"
    # Create task.yaml
    task_dir_path = tmp_path / ".devflow/tasks" / task.id
    save_task(task_dir_path, task)

    # Add a custom description in task.yaml to simulate realistic input
    task_yaml_file = task_dir_path / "task.yaml"
    existing_yaml = task_yaml_file.read_text(encoding="utf-8")
    task_yaml_file.write_text(existing_yaml + "\ndescription: This task is about fixing a bug in estimator.py.\n", encoding="utf-8")

    # Add dummy files inside temporary directory to scan
    test_file = tmp_path / "test_dummy.py"
    test_file.write_text("def test_dummy():\n    assert True\n", encoding="utf-8")

    source_file = tmp_path / "estimator.py"
    source_file.write_text("# dummy source code\ndef calculate():\n    pass\n", encoding="utf-8")

    # Write events.jsonl
    events_file = task_dir_path / "events.jsonl"
    events_file.write_text('{"event": "created"}\n' * 50, encoding="utf-8")

    # Run estimator
    fit_data = estimate_task_fit(tmp_path, task.id)

    # Asserts on task_fit
    tf = fit_data["task_fit"]
    assert tf["task_type"] == "test_repair"
    assert tf["repo_scope"] in ("small", "medium", "large")
    assert tf["context_requirement"] in ("low", "medium", "high", "critical")
    assert tf["reasoning_requirement"] == "medium"
    assert tf["code_edit_risk"] == "medium"
    assert tf["architectural_risk"] == "low"
    assert tf["requires_big_picture"] is False
    assert tf["requires_current_repo_state"] is True
    assert tf["requires_historical_project_context"] is False
    assert tf["context_layer"] in ("L0", "L1", "L2", "L3", "L4", "L5")
    assert tf["confidence"] > 0.0

    # Asserts on repo_scan
    rs = fit_data["repo_scan"]
    assert rs["relevant_files_count"] >= 0
    assert rs["test_files_needed"] >= 0
    assert rs["task_history_tokens"] > 0
    assert rs["total_context_estimate"] > 0

    # Test saving
    save_task_fit(tmp_path, task.id, fit_data)
    yaml_file = task_dir_path / "task-fit.yaml"
    assert yaml_file.exists()
    yaml_content = yaml_file.read_text(encoding="utf-8")
    assert "task_fit:" in yaml_content
    assert "repo_scan:" in yaml_content
    assert "task_type: test_repair" in yaml_content


def test_estimator_cli_command(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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
    result = runner.invoke(app, ["task", "fit", task.id])

    assert result.exit_code == 0
    assert "Estimated task-fit profile" in result.output
    assert "Task Type:" in result.output
    assert "Wrote task-fit.yaml" in result.output

    # Check that task-fit.yaml actually exists
    yaml_file = task_dir_path / "task-fit.yaml"
    assert yaml_file.exists()
    assert "task_type: documentation_cleanup" in yaml_file.read_text(encoding="utf-8")
