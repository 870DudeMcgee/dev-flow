from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from devflow.cli import app
from devflow.control_room.persistence import save_task
from devflow.control_room.scout import run_scout_report, run_scout_reports, save_scout_report
from devflow.control_room.service import create_task


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


def test_run_scout_reports_returns_all_roles_without_provider_calls(tmp_path: Path) -> None:
    (tmp_path / ".devflow/tasks").mkdir(parents=True)
    (tmp_path / ".devflow/workspaces").mkdir(parents=True)
    task = create_task(tmp_path, "Route implementation worker safely")
    save_task(tmp_path / ".devflow/tasks" / task.id, task)

    reports = run_scout_reports(tmp_path, task.id, role="all")

    assert sorted(reports) == ["context", "repo_scope", "risk", "stale_context", "test"]
    assert reports["risk"]["scout_report"]["role"] == "risk_scout"
    assert reports["stale_context"]["scout_report"]["poison_context_risk"] in {"low", "high"}


def test_save_scout_report_returns_artifact_path(tmp_path: Path) -> None:
    (tmp_path / ".devflow/tasks").mkdir(parents=True)
    (tmp_path / ".devflow/workspaces").mkdir(parents=True)
    task = create_task(tmp_path, "Find likely tests")
    save_task(tmp_path / ".devflow/tasks" / task.id, task)

    report = run_scout_report(tmp_path, task.id, "test")
    path = save_scout_report(tmp_path, task.id, "test", report)

    assert path == tmp_path / ".devflow/tasks" / task.id / "scout-test.yaml"
    assert "scout_report:" in path.read_text(encoding="utf-8")


def test_scout_cli_json_is_stable_without_experimental_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / ".devflow/tasks").mkdir(parents=True)
    (tmp_path / ".devflow/workspaces").mkdir(parents=True)
    task = create_task(tmp_path, "Assess routing risks")
    save_task(tmp_path / ".devflow/tasks" / task.id, task)

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DEVFLOW_EXPERIMENTAL", raising=False)

    result = CliRunner().invoke(app, ["task", "scout", task.id, "--role", "risk", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["task_id"] == task.id
    assert payload["reports"]["risk"]["scout_report"]["role"] == "risk_scout"
    assert payload["artifact_paths"]["risk"] == f".devflow/tasks/{task.id}/scout-risk.yaml"
