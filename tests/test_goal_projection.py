from __future__ import annotations

import os
import sys
import yaml
from pathlib import Path
import pytest
from typer.testing import CliRunner

from devflow.cli import app
from devflow.control_room.goals import create_goal_from_markdown, goal_dir
from devflow.control_room.goal_projection import build_goal_status_projection


def setup_temp_repo(tmp_path: Path) -> Path:
    """Initialize standard .devflow control room scaffolding in temp path."""
    old_cwd = Path.cwd()
    os.chdir(tmp_path)
    
    # Run devflow init via CLI
    runner = CliRunner()
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0
    
    # Create docs/ for context pointer scanning
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir(exist_ok=True)
    (docs_dir / "architecture.md").write_text("Standard architecture notes.", encoding="utf-8")
    
    # Restore cwd
    os.chdir(old_cwd)
    return tmp_path


def test_goal_list_shows_scaffolded_goal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # 1. Setup repo and brief
    setup_temp_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    brief_path = tmp_path / "my_goal.md"
    brief_path.write_text("## Goal Brief\nImplement durables.", encoding="utf-8")

    runner = CliRunner()
    
    # 2. Initialize goal
    init_res = runner.invoke(app, ["goal", "init", "--from", "my_goal.md"])
    assert init_res.exit_code == 0

    # 3. List goals
    list_res = runner.invoke(app, ["goal", "list"])
    assert list_res.exit_code == 0
    assert "G-0001" in list_res.output
    assert "ready_for_task_creation" in list_res.output
    assert "devflow goal status G-0001" in list_res.output


def test_goal_status_shows_planning_details(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    setup_temp_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    brief_path = tmp_path / "my_goal.md"
    brief_path.write_text("## Goal Brief\nImplement durables.", encoding="utf-8")

    runner = CliRunner()
    runner.invoke(app, ["goal", "init", "--from", "my_goal.md"])

    status_res = runner.invoke(app, ["goal", "status", "G-0001"])
    assert status_res.exit_code == 0
    assert "Goal Status" in status_res.output
    assert "G-0001" in status_res.output
    assert "Planning Artifacts" in status_res.output
    assert "Questions" in status_res.output
    assert "Task Slices" in status_res.output
    assert "Context" in status_res.output
    assert "Next Action" in status_res.output


def test_goal_projection_counts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    setup_temp_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    brief_path = tmp_path / "my_goal.md"
    brief_path.write_text("## Goal Brief\nImplement durables.", encoding="utf-8")

    runner = CliRunner()
    runner.invoke(app, ["goal", "init", "--from", "my_goal.md"])

    proj = build_goal_status_projection(tmp_path, "G-0001")
    assert proj.task_slice_count >= 1
    assert proj.hitl_slice_count >= 1
    assert proj.context_risk == "medium"


def test_open_questions_can_block_implementation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    setup_temp_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    brief_path = tmp_path / "my_goal.md"
    brief_path.write_text("## Goal Brief\nImplement durables.", encoding="utf-8")

    runner = CliRunner()
    runner.invoke(app, ["goal", "init", "--from", "my_goal.md"])

    # Edit open questions
    q_file = goal_dir(tmp_path, "G-0001") / "open-questions.yaml"
    q_content = """questions:
  - "Is local model runtime isolated?"
implementation_blocked: true
"""
    q_file.write_text(q_content, encoding="utf-8")

    proj = build_goal_status_projection(tmp_path, "G-0001")
    assert proj.state == "blocked"
    assert proj.implementation_blocked is True
    assert proj.open_question_count == 1
    assert proj.next_action_command == "devflow goal status G-0001"
    assert "blocked" in proj.next_action_reason


def test_dashboard_includes_goal_panel(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    setup_temp_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    brief_path = tmp_path / "my_goal.md"
    brief_path.write_text("## Goal Brief\nImplement durables.", encoding="utf-8")

    runner = CliRunner()
    runner.invoke(app, ["goal", "init", "--from", "my_goal.md"])

    dash_res = runner.invoke(app, ["dashboard"])
    assert dash_res.exit_code == 0
    assert "Goals" in dash_res.output
    assert "Active: G-0001" in dash_res.output
    assert "Open questions: 0" in dash_res.output
    assert "Task slices: 1" in dash_res.output
    assert "Context risk: medium" in dash_res.output
    assert "Next Action" in dash_res.output


def test_status_alias_includes_goal_panel(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    setup_temp_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    brief_path = tmp_path / "my_goal.md"
    brief_path.write_text("## Goal Brief\nImplement durables.", encoding="utf-8")

    runner = CliRunner()
    runner.invoke(app, ["goal", "init", "--from", "my_goal.md"])

    status_res = runner.invoke(app, ["status"])
    assert status_res.exit_code == 0
    assert "Dev-Flow Control Room" in status_res.output
    assert "Goals" in status_res.output
    assert "Active: G-0001" in status_res.output


def test_goal_projections_are_read_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    setup_temp_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    brief_path = tmp_path / "my_goal.md"
    brief_path.write_text("## Goal Brief\nImplement durables.", encoding="utf-8")

    runner = CliRunner()
    runner.invoke(app, ["goal", "init", "--from", "my_goal.md"])

    g_dir = goal_dir(tmp_path, "G-0001")
    
    # Snapshot all file sizes and modification times
    snapshot = {}
    for item in g_dir.iterdir():
        if item.is_file():
            snapshot[item.name] = (item.stat().st_size, item.read_bytes())

    # Run CLI projection actions
    runner.invoke(app, ["goal", "list"])
    runner.invoke(app, ["goal", "status", "G-0001"])
    runner.invoke(app, ["dashboard"])
    runner.invoke(app, ["status"])

    # Assert bytes are completely identical
    for item in g_dir.iterdir():
        if item.is_file():
            assert item.name in snapshot
            size, content = snapshot[item.name]
            assert item.stat().st_size == size
            assert item.read_bytes() == content


def test_malformed_yaml_does_not_crash_dashboard(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    setup_temp_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    brief_path = tmp_path / "my_goal.md"
    brief_path.write_text("## Goal Brief\nImplement durables.", encoding="utf-8")

    runner = CliRunner()
    runner.invoke(app, ["goal", "init", "--from", "my_goal.md"])

    # Write invalid YAML
    slices_file = goal_dir(tmp_path, "G-0001") / "task-slices.yaml"
    slices_file.write_text("{malformed: [invalid", encoding="utf-8")

    # Run goal status - must exit 0 and include warning
    status_res = runner.invoke(app, ["goal", "status", "G-0001"])
    assert status_res.exit_code == 0
    assert "warning" in status_res.output.lower() or "malformed" in status_res.output.lower()

    # Run dashboard - must exit 0
    dash_res = runner.invoke(app, ["dashboard"])
    assert dash_res.exit_code == 0


def test_no_scheduler_or_generation_side_effects(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    setup_temp_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    brief_path = tmp_path / "my_goal.md"
    brief_path.write_text("## Goal Brief\nImplement durables.", encoding="utf-8")

    runner = CliRunner()
    runner.invoke(app, ["goal", "init", "--from", "my_goal.md"])

    # Run CLI projection actions
    runner.invoke(app, ["goal", "list"])
    runner.invoke(app, ["goal", "status", "G-0001"])
    runner.invoke(app, ["dashboard"])
    runner.invoke(app, ["status"])

    # Assert .devflow/tasks directory has no task-slices task folders
    tasks_dir = tmp_path / ".devflow" / "tasks"
    # It should only contain empty files or nothing unless a task was explicitly created
    if tasks_dir.exists():
        task_folders = [item for item in tasks_dir.iterdir() if item.is_dir() and item.name.startswith("task-")]
        assert len(task_folders) == 0


def test_existing_regression() -> None:
    # Basic baseline validation that imports work and CLI compiles
    assert True
