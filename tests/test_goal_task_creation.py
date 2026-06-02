from __future__ import annotations

import yaml
from pathlib import Path
import pytest
from typer.testing import CliRunner

from devflow.cli import app
from devflow.control_room.goals import goal_dir
from tests.helpers import setup_temp_git_repo


def test_slices_command_lists_slices(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Test 1: goal slices command lists starter slice
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    brief_path = tmp_path / "my_goal.md"
    brief_path.write_text("## Goal Brief\nImplement durables.", encoding="utf-8")

    runner = CliRunner()
    runner.invoke(app, ["goal", "init", "--from", "my_goal.md"])

    slices_res = runner.invoke(app, ["goal", "slices", "G-0001"])
    assert slices_res.exit_code == 0
    assert "Task Slices for G-0001" in slices_res.output
    assert "TS-0001" in slices_res.output
    assert "HITL" in slices_res.output
    assert "low" in slices_res.output  # low is starter slice risk
    assert "devflow goal create-task G-0001 TS-0001" in slices_res.output


def test_create_task_creates_normal_task(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Test 2: create-task creates normal DevFlow task
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    brief_path = tmp_path / "my_goal.md"
    brief_path.write_text("## Goal Brief\nImplement durables.", encoding="utf-8")

    runner = CliRunner()
    runner.invoke(app, ["goal", "init", "--from", "my_goal.md"])

    create_res = runner.invoke(app, ["goal", "create-task", "G-0001", "TS-0001"])
    assert create_res.exit_code == 0
    assert "Created task-0001 from G-0001 / TS-0001" in create_res.output
    assert "task-0001 — Starter task slice" in create_res.output
    assert ".devflow/tasks/task-0001" in create_res.output

    # Check normal DevFlow task files exist
    assert (tmp_path / ".devflow" / "tasks" / "task-0001" / "task.yaml").exists()

    # Assert task list shows it
    list_res = runner.invoke(app, ["task", "list"])
    assert list_res.exit_code == 0
    assert "task-0001" in list_res.output


def test_created_task_has_goal_link(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Test 3: created task has goal-link artifact
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    brief_path = tmp_path / "my_goal.md"
    brief_path.write_text("## Goal Brief\nImplement durables.", encoding="utf-8")

    runner = CliRunner()
    runner.invoke(app, ["goal", "init", "--from", "my_goal.md"])
    runner.invoke(app, ["goal", "create-task", "G-0001", "TS-0001"])

    goal_link_path = tmp_path / ".devflow" / "tasks" / "task-0001" / "goal-link.yaml"
    assert goal_link_path.exists()

    link_data = yaml.safe_load(goal_link_path.read_text(encoding="utf-8"))
    assert link_data["goal_id"] == "G-0001"
    assert link_data["slice_id"] == "TS-0001"
    assert link_data["created_from_goal_slice"] is True
    assert link_data["execution_mode"] == "HITL"
    assert link_data["human_checkpoint_required"] is True
    assert link_data["promotion_allowed"] is False
    assert link_data["risk"] == "low"
    assert link_data["context_strategy"] == "focused_task_packet"


def test_created_task_has_slice_md(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Test 4: created task has slice.md artifact
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    brief_path = tmp_path / "my_goal.md"
    brief_path.write_text("## Goal Brief\nImplement durables.", encoding="utf-8")

    runner = CliRunner()
    runner.invoke(app, ["goal", "init", "--from", "my_goal.md"])
    runner.invoke(app, ["goal", "create-task", "G-0001", "TS-0001"])

    slice_md_path = tmp_path / ".devflow" / "tasks" / "task-0001" / "slice.md"
    assert slice_md_path.exists()

    content = slice_md_path.read_text(encoding="utf-8")
    assert "TS-0001" in content
    assert "G-0001" in content
    assert "Acceptance Criteria" in content
    assert "Context Budget" in content
    assert "Verification Policy" in content
    assert "Promotion Boundary" in content


def test_create_task_no_execution_or_verification(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Test 5: create-task does not run worker or verify
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    brief_path = tmp_path / "my_goal.md"
    brief_path.write_text("## Goal Brief\nImplement durables.", encoding="utf-8")

    runner = CliRunner()
    runner.invoke(app, ["goal", "init", "--from", "my_goal.md"])
    runner.invoke(app, ["goal", "create-task", "G-0001", "TS-0001"])

    # Load task.yaml
    task_yaml = yaml.safe_load((tmp_path / ".devflow" / "tasks" / "task-0001" / "task.yaml").read_text(encoding="utf-8"))
    assert task_yaml["status"] == "created"
    assert task_yaml["verification_status"] == "not_run"

    # Verify worker.log is empty
    worker_log = tmp_path / ".devflow" / "tasks" / "task-0001" / "logs" / "worker.log"
    assert worker_log.exists()
    assert worker_log.read_text(encoding="utf-8") == ""

    # Verify verify.log is empty
    verify_log = tmp_path / ".devflow" / "tasks" / "task-0001" / "logs" / "verify.log"
    assert verify_log.exists()
    assert verify_log.read_text(encoding="utf-8") == ""


def test_task_show_includes_goal_link(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Test 6: task show includes goal link
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    brief_path = tmp_path / "my_goal.md"
    brief_path.write_text("## Goal Brief\nImplement durables.", encoding="utf-8")

    runner = CliRunner()
    runner.invoke(app, ["goal", "init", "--from", "my_goal.md"])
    runner.invoke(app, ["goal", "create-task", "G-0001", "TS-0001"])

    show_res = runner.invoke(app, ["task", "show", "task-0001"])
    assert show_res.exit_code == 0
    assert "Goal Link" in show_res.output
    assert "Goal: G-0001" in show_res.output
    assert "Slice: TS-0001" in show_res.output
    assert "Execution mode: HITL" in show_res.output
    assert "Promotion allowed: false" in show_res.output


def test_missing_slice_fails_clearly(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Test 7: missing slice fails clearly
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    brief_path = tmp_path / "my_goal.md"
    brief_path.write_text("## Goal Brief\nImplement durables.", encoding="utf-8")

    runner = CliRunner()
    runner.invoke(app, ["goal", "init", "--from", "my_goal.md"])

    create_res = runner.invoke(app, ["goal", "create-task", "G-0001", "TS-9999"])
    assert create_res.exit_code != 0
    assert "Slice ID 'TS-9999' not found in goal 'G-0001'" in create_res.output


def test_malformed_slices_fails_safely(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Test 8: malformed task-slices.yaml fails safely
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    brief_path = tmp_path / "my_goal.md"
    brief_path.write_text("## Goal Brief\nImplement durables.", encoding="utf-8")

    runner = CliRunner()
    runner.invoke(app, ["goal", "init", "--from", "my_goal.md"])

    # Corrupt task-slices.yaml
    slices_file = goal_dir(tmp_path, "G-0001") / "task-slices.yaml"
    slices_file.write_text("{malformed: [invalid", encoding="utf-8")

    slices_res = runner.invoke(app, ["goal", "slices", "G-0001"])
    # Should show error output clearly
    assert "malformed" in slices_res.output.lower() or slices_res.exit_code != 0

    # Ensure no task is created
    tasks_dir = tmp_path / ".devflow" / "tasks"
    if tasks_dir.exists():
        task_folders = [item for item in tasks_dir.iterdir() if item.is_dir() and item.name.startswith("task-")]
        assert len(task_folders) == 0


def test_repeated_create_task_is_allowed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Test 9: repeated create-task behavior is safe (allowed)
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    brief_path = tmp_path / "my_goal.md"
    brief_path.write_text("## Goal Brief\nImplement durables.", encoding="utf-8")

    runner = CliRunner()
    runner.invoke(app, ["goal", "init", "--from", "my_goal.md"])

    # Create first
    res1 = runner.invoke(app, ["goal", "create-task", "G-0001", "TS-0001"])
    assert res1.exit_code == 0
    assert "task-0001" in res1.output

    # Create second from same slice
    res2 = runner.invoke(app, ["goal", "create-task", "G-0001", "TS-0001"])
    assert res2.exit_code == 0
    assert "task-0002" in res2.output

    assert (tmp_path / ".devflow" / "tasks" / "task-0001" / "goal-link.yaml").exists()
    assert (tmp_path / ".devflow" / "tasks" / "task-0002" / "goal-link.yaml").exists()


def test_no_scheduler_registry_side_effects(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Test 10: no scheduler/model/registry side effects
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    brief_path = tmp_path / "my_goal.md"
    brief_path.write_text("## Goal Brief\nImplement durables.", encoding="utf-8")

    runner = CliRunner()
    runner.invoke(app, ["goal", "init", "--from", "my_goal.md"])
    runner.invoke(app, ["goal", "create-task", "G-0001", "TS-0001"])

    # Check no scheduler/local_model_adapter/worker registry file exists
    assert not (tmp_path / ".devflow" / "scheduler.yaml").exists()
    assert not (tmp_path / ".devflow" / "local_model_adapter").exists()


def test_dashboard_sees_created_task(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Test 11: dashboard sees created task
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    brief_path = tmp_path / "my_goal.md"
    brief_path.write_text("## Goal Brief\nImplement durables.", encoding="utf-8")

    runner = CliRunner()
    runner.invoke(app, ["goal", "init", "--from", "my_goal.md"])
    runner.invoke(app, ["goal", "create-task", "G-0001", "TS-0001"])

    dash_res = runner.invoke(app, ["dashboard"])
    assert dash_res.exit_code == 0
    assert "task-0001" in dash_res.output
    assert "Starter task slice" in dash_res.output
    assert "G-0001" in dash_res.output


def test_read_only_commands_remain_read_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Test 12: read-only commands remain read-only
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    brief_path = tmp_path / "my_goal.md"
    brief_path.write_text("## Goal Brief\nImplement durables.", encoding="utf-8")

    runner = CliRunner()
    runner.invoke(app, ["goal", "init", "--from", "my_goal.md"])
    runner.invoke(app, ["goal", "create-task", "G-0001", "TS-0001"])

    g_dir = goal_dir(tmp_path, "G-0001")
    t_dir = tmp_path / ".devflow" / "tasks" / "task-0001"

    # Snapshot all file sizes and modification times
    snapshot = {}
    for folder in [g_dir, t_dir]:
        for item in folder.rglob("*"):
            if item.is_file():
                snapshot[item.as_posix()] = (item.stat().st_size, item.read_bytes())

    # Run CLI projection/read-only actions
    runner.invoke(app, ["goal", "slices", "G-0001"])
    runner.invoke(app, ["goal", "list"])
    runner.invoke(app, ["goal", "status", "G-0001"])
    runner.invoke(app, ["task", "show", "task-0001"])
    runner.invoke(app, ["dashboard"])

    # Assert bytes are completely identical
    for folder in [g_dir, t_dir]:
        for item in folder.rglob("*"):
            if item.is_file():
                assert item.as_posix() in snapshot
                size, content = snapshot[item.as_posix()]
                assert item.stat().st_size == size
                assert item.read_bytes() == content
