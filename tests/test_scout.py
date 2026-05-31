from __future__ import annotations

import json
from pathlib import Path
import pytest
from typer.testing import CliRunner

from devflow.control_room.persistence import save_task, get_task
from devflow.control_room.service import create_task
from devflow.control_room.scout import run_scout_report, save_scout_report
from devflow.cli import app


def test_scout_report_heuristics_and_saving(tmp_path: Path) -> None:
    # 1. Initialize seed structures
    (tmp_path / ".devflow/tasks").mkdir(parents=True)
    (tmp_path / ".devflow/workspaces").mkdir(parents=True)

    # 2. Create dummy task
    task = create_task(tmp_path, "Perform schema migration and update router configuration")
    task_dir_path = tmp_path / ".devflow/tasks" / task.id
    save_task(task_dir_path, task)

    # 3. Test Repo Scope Scout
    repo_scope_res = run_scout_report(tmp_path, task.id, "repo_scope")
    sr = repo_scope_res["scout_report"]
    assert sr["role"] == "repo_scope_scout"
    assert sr["estimated_scope"] == "small"
    assert "model profile compatibility" in sr["likely_risks"]

    # Test Risk Scout
    risk_res = run_scout_report(tmp_path, task.id, "risk")
    sr_risk = risk_res["scout_report"]
    assert sr_risk["role"] == "risk_scout"
    assert "task schema migration risk" in sr_risk["risks_detected"]
    assert "model routing and tier mapping regression" in sr_risk["risks_detected"]

    # Test Context Scout
    context_res = run_scout_report(tmp_path, task.id, "context")
    sr_context = context_res["scout_report"]
    assert sr_context["role"] == "context_scout"
    assert "project_index.yaml" in sr_context["missing_indexes_detected"]

    # Test Test Scout
    test_res = run_scout_report(tmp_path, task.id, "test")
    sr_test = test_res["scout_report"]
    assert sr_test["role"] == "test_scout"
    assert len(sr_test["likely_affected_test_files"]) > 0

    # Test Stale Context Scout
    stale_res = run_scout_report(tmp_path, task.id, "stale_context")
    sr_stale = stale_res["scout_report"]
    assert sr_stale["role"] == "stale_context_scout"

    # 4. Save and verify YAML files
    save_scout_report(tmp_path, task.id, "risk", risk_res)
    yaml_file = task_dir_path / "scout-risk.yaml"
    assert yaml_file.exists()
    yaml_content = yaml_file.read_text(encoding="utf-8")
    assert "role: risk_scout" in yaml_content
    assert "task schema migration risk" in yaml_content


def test_scout_cli_command(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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
    result = runner.invoke(app, ["task", "scout", task.id, "all"])

    assert result.exit_code == 0
    assert "Executed scout evaluation for task" in result.output
    assert "Scout Role:                  REPO_SCOPE_SCOUT" in result.output
    assert "Scout Role:                  RISK_SCOUT" in result.output
    assert "Scout Role:                  STALE_CONTEXT_SCOUT" in result.output

    # Check files exist
    assert (task_dir_path / "scout-repo_scope.yaml").exists()
    assert (task_dir_path / "scout-risk.yaml").exists()
    assert (task_dir_path / "scout-context.yaml").exists()
    assert (task_dir_path / "scout-test.yaml").exists()
    assert (task_dir_path / "scout-stale_context.yaml").exists()
