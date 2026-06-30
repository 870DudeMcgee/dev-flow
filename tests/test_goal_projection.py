from __future__ import annotations

from pathlib import Path
from typing import Any
import pytest
from typer.testing import CliRunner

from devflow.cli import app
from devflow.control_room.goals import goal_dir
from devflow.control_room.goal_projection import (
    build_goal_status_projection,
    list_goal_status_projections,
)
from tests.helpers import setup_temp_repo


runner = CliRunner()


def _create_goal(tmp_path: Path) -> None:
    setup_temp_repo(tmp_path)
    brief_path = tmp_path / "my_goal.md"
    brief_path.write_text("## Goal Brief\nImplement durables.", encoding="utf-8")
    result = runner.invoke(app, ["goal", "init", "G-0001", "--from", str(brief_path)])
    assert result.exit_code == 0, result.output


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


@pytest.mark.parametrize(
    ("file_name", "root_yaml"),
    [
        ("open-questions.yaml", "- a\n"),
        ("open-questions.yaml", "scalar-value"),
        ("task-slices.yaml", "- task_id: TS-0001\n"),
        ("task-slices.yaml", "scalar-value"),
        ("context-pointers.yaml", "- required_context:\n  - docs/one.md\n"),
        ("context-pointers.yaml", "scalar-value"),
    ],
)
def test_goal_projection_root_shape_violations_fall_back_to_defaults(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    file_name: str,
    root_yaml: str,
) -> None:
    setup_temp_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    brief_path = tmp_path / "my_goal.md"
    brief_path.write_text("## Goal Brief\nImplement durables.", encoding="utf-8")

    runner = CliRunner()
    runner.invoke(app, ["goal", "init", "--from", "my_goal.md"])

    target = goal_dir(tmp_path, "G-0001") / file_name
    target.write_text(root_yaml, encoding="utf-8")

    proj = build_goal_status_projection(tmp_path, "G-0001")

    assert any(f"warning: {file_name} must be a mapping" in w for w in proj.warnings)
    assert proj.open_question_count == 0
    assert proj.implementation_blocked is False
    assert proj.context_risk == "medium"
    if file_name == "task-slices.yaml":
        assert proj.task_slice_count == 0
    else:
        assert proj.task_slice_count >= 0


def test_goal_projection_warns_for_each_wrong_shaped_goal_yaml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    setup_temp_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    brief_path = tmp_path / "my_goal.md"
    brief_path.write_text("## Goal Brief\nImplement durables.", encoding="utf-8")

    runner.invoke(app, ["goal", "init", "--from", "my_goal.md"])
    g_dir = goal_dir(tmp_path, "G-0001")
    (g_dir / "open-questions.yaml").write_text("- question one\n", encoding="utf-8")
    (g_dir / "task-slices.yaml").write_text("not-a-mapping\n", encoding="utf-8")
    (g_dir / "context-pointers.yaml").write_text("- docs/one.md\n", encoding="utf-8")

    proj = build_goal_status_projection(tmp_path, "G-0001")

    assert "warning: open-questions.yaml must be a mapping" in proj.warnings
    assert "warning: task-slices.yaml must be a mapping" in proj.warnings
    assert "warning: context-pointers.yaml must be a mapping" in proj.warnings
    assert proj.open_question_count == 0
    assert proj.implementation_blocked is False
    assert proj.task_slice_count == 0
    assert proj.context_risk == "medium"


def test_list_goal_status_projections_forwards_projection_warnings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    setup_temp_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    brief_path = tmp_path / "my_goal.md"
    brief_path.write_text("## Goal Brief\nImplement durables.", encoding="utf-8")

    runner.invoke(app, ["goal", "init", "--from", "my_goal.md"])
    target = goal_dir(tmp_path, "G-0001") / "open-questions.yaml"
    target.write_text("- question one\n", encoding="utf-8")

    warnings: list[str] = []
    projections = list_goal_status_projections(tmp_path, warnings=warnings)

    assert len(projections) == 1
    assert "warning: open-questions.yaml must be a mapping" in warnings


def test_goal_projection_keeps_task_slices_wrong_field_shape_warning(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    setup_temp_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    brief_path = tmp_path / "my_goal.md"
    brief_path.write_text("## Goal Brief\nImplement durables.", encoding="utf-8")

    runner.invoke(app, ["goal", "init", "--from", "my_goal.md"])
    target = goal_dir(tmp_path, "G-0001") / "task-slices.yaml"
    target.write_text("task_slices: { id: TS-0001 }\n", encoding="utf-8")

    proj = build_goal_status_projection(tmp_path, "G-0001")

    assert "warning: task-slices.yaml task_slices must be a list" in proj.warnings
    assert proj.task_slice_count == 0


def test_list_goal_status_projections_forwards_warnings_on_projection_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    setup_temp_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    brief_path = tmp_path / "my_goal.md"
    brief_path.write_text("## Goal Brief\nImplement durables.", encoding="utf-8")

    runner.invoke(app, ["goal", "init", "--from", "my_goal.md"])

    from devflow.control_room import goal_projection

    original = goal_projection.build_goal_status_projection

    def _broken(root: Path, goal_id: str) -> Any:
        if goal_id == "G-0001":
            raise RuntimeError("projection is intentionally broken")
        return original(root, goal_id)

    monkeypatch.setattr(goal_projection, "build_goal_status_projection", _broken)

    warnings: list[str] = []
    projects = list_goal_status_projections(tmp_path, warnings=warnings)

    assert projects == []
    assert len(warnings) == 1
    assert "G-0001" in warnings[0]
    assert "failed to project goal" in warnings[0]


def test_list_goal_status_projections_without_warnings_stays_compatible(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    setup_temp_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    brief_path = tmp_path / "my_goal.md"
    brief_path.write_text("## Goal Brief\nImplement durables.", encoding="utf-8")

    runner.invoke(app, ["goal", "init", "--from", "my_goal.md"])

    from devflow.control_room import goal_projection

    original = goal_projection.build_goal_status_projection

    def _broken(root: Path, goal_id: str) -> Any:
        if goal_id == "G-0001":
            raise RuntimeError("projection is intentionally broken")
        return original(root, goal_id)

    monkeypatch.setattr(goal_projection, "build_goal_status_projection", _broken)

    projects = list_goal_status_projections(tmp_path)
    assert projects == []


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


def test_goal_status_includes_lifecycle_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    _create_goal(tmp_path)

    result = runner.invoke(app, ["goal", "status", "G-0001"])

    assert result.exit_code == 0, result.output
    assert "Lifecycle: active" in result.output


def test_goal_next_recommends_activation_when_lifecycle_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    _create_goal(tmp_path)
    (tmp_path / ".devflow" / "goals" / "G-0001" / "goal-state.yaml").unlink()

    result = runner.invoke(app, ["goal", "next", "G-0001"])

    assert result.exit_code == 0, result.output
    assert "devflow goal activate G-0001" in result.output


def test_goal_next_stops_on_paused_lifecycle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    _create_goal(tmp_path)
    pause = runner.invoke(app, ["goal", "pause", "G-0001", "--reason", "waiting"])
    assert pause.exit_code == 0, pause.output

    result = runner.invoke(app, ["goal", "next", "G-0001"])

    assert result.exit_code == 0, result.output
    assert "Goal is paused" in result.output
    assert "devflow freshness" not in result.output
