from __future__ import annotations

import os
import json
import yaml
from pathlib import Path
import pytest
from typer.testing import CliRunner

from devflow.cli import app
from devflow.control_room.goals import goal_dir
from tests.helpers import setup_temp_git_repo


def test_1_packet_for_non_goal_task_still_works(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Test 1: packet for non-goal task still works
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    runner = CliRunner()
    create_res = runner.invoke(app, ["task", "create", "normal task"])
    assert create_res.exit_code == 0

    packet_res = runner.invoke(app, ["task", "packet", "task-0001"])
    assert packet_res.exit_code == 0
    
    packet = json.loads(packet_res.output)
    assert packet["task_id"] == "task-0001"
    assert packet["title"] == "normal task"
    assert packet["goal_context"] is None


def test_2_packet_for_goal_linked_task_includes_goal_context(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Test 2: packet for goal-linked task includes goal context
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    brief_path = tmp_path / "my_goal.md"
    brief_path.write_text("## Goal Brief\nImplement durables.", encoding="utf-8")

    runner = CliRunner()
    runner.invoke(app, ["goal", "init", "--from", "my_goal.md"])
    runner.invoke(app, ["goal", "create-task", "G-0001", "TS-0001"])

    packet_res = runner.invoke(app, ["task", "packet", "task-0001"])
    assert packet_res.exit_code == 0
    
    packet = json.loads(packet_res.output)
    gc = packet["goal_context"]
    assert gc is not None
    assert gc["linked"] is True
    assert gc["goal_id"] == "G-0001"
    assert gc["slice_id"] == "TS-0001"
    assert gc["execution_mode"] == "HITL"
    assert gc["human_checkpoint_required"] is True
    assert gc["promotion_allowed"] is False
    assert gc["risk"] == "low"


def test_3_packet_includes_task_slice_acceptance_criteria(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Test 3: packet includes task slice acceptance criteria
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    brief_path = tmp_path / "my_goal.md"
    brief_path.write_text("## Goal Brief\nImplement durables.", encoding="utf-8")

    runner = CliRunner()
    runner.invoke(app, ["goal", "init", "--from", "my_goal.md"])
    runner.invoke(app, ["goal", "create-task", "G-0001", "TS-0001"])

    packet_res = runner.invoke(app, ["task", "packet", "task-0001"])
    packet = json.loads(packet_res.output)
    
    ts = packet["task_slice"]
    assert ts is not None
    assert ts["title"] == "Starter task slice"
    assert "baseline" in ts["summary"].lower()
    assert isinstance(ts["acceptance_criteria"], list)
    assert len(ts["acceptance_criteria"]) > 0
    assert "goal.md" in ts["required_artifacts"]


def test_4_packet_includes_context_budget_and_forbidden_context(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Test 4: packet includes context budget and forbidden context
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    brief_path = tmp_path / "my_goal.md"
    brief_path.write_text("## Goal Brief\nImplement durables.", encoding="utf-8")

    runner = CliRunner()
    runner.invoke(app, ["goal", "init", "--from", "my_goal.md"])
    runner.invoke(app, ["goal", "create-task", "G-0001", "TS-0001"])

    packet_res = runner.invoke(app, ["task", "packet", "task-0001"])
    packet = json.loads(packet_res.output)
    
    cb = packet["context_budget"]
    assert cb is not None
    assert cb["strategy"] == "focused_task_packet"
    assert "archived_docs" in cb["forbidden_context"]
    assert "do_not_load_entire_repo" in cb["warnings"]


def test_5_packet_includes_verification_policy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Test 5: packet includes verification policy
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    brief_path = tmp_path / "my_goal.md"
    brief_path.write_text("## Goal Brief\nImplement durables.", encoding="utf-8")

    runner = CliRunner()
    runner.invoke(app, ["goal", "init", "--from", "my_goal.md"])
    runner.invoke(app, ["goal", "create-task", "G-0001", "TS-0001"])

    packet_res = runner.invoke(app, ["task", "packet", "task-0001"])
    packet = json.loads(packet_res.output)
    
    vp = packet["verification_policy"]
    assert vp is not None
    assert vp["test_first_required"] is True
    assert vp["red_green_required"] is True
    assert isinstance(vp["required_evidence"], list)


def test_6_packet_does_not_load_archived_context_by_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Test 6: packet does not load archived context by default
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    brief_path = tmp_path / "my_goal.md"
    brief_path.write_text("## Goal Brief\nImplement durables.", encoding="utf-8")

    # Create an archived plan inside the workspace docs
    archive_dir = tmp_path / "docs" / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive_plan = archive_dir / "old-plan.md"
    archive_plan.write_text("SUPER_SECRET_ARCHIVED_PLAN content that should be excluded", encoding="utf-8")

    runner = CliRunner()
    runner.invoke(app, ["goal", "init", "--from", "my_goal.md"])

    # The context-pointers.yaml automatically parses docs and adds it to stale_or_archived_context
    runner.invoke(app, ["goal", "create-task", "G-0001", "TS-0001"])

    packet_res = runner.invoke(app, ["task", "packet", "task-0001"])
    assert packet_res.exit_code == 0
    packet = json.loads(packet_res.output)

    # Let's ensure the secret archived content is NOT inside the serialized packet
    serialized = json.dumps(packet)
    assert "SUPER_SECRET_ARCHIVED_PLAN" not in serialized
    
    # Assert a warning or exclusion exists in operator_warnings or is documented
    warnings = packet["operator_warnings"]
    assert any("docs/archive" in w or "Archived context" in w for w in warnings)


def test_7_packet_caps_large_prd_content(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Test 7: packet caps large PRD content
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    brief_path = tmp_path / "my_goal.md"
    brief_path.write_text("## Goal Brief\nImplement durables.", encoding="utf-8")

    runner = CliRunner()
    runner.invoke(app, ["goal", "init", "--from", "my_goal.md"])
    
    # Overwrite prd.md with a very large text
    prd_path = goal_dir(tmp_path, "G-0001") / "prd.md"
    large_text = "# PRD\n" + ("A" * 5000) + "\nDISTINCTIVE_TAIL"
    prd_path.write_text(large_text, encoding="utf-8")

    runner.invoke(app, ["goal", "create-task", "G-0001", "TS-0001"])

    packet_res = runner.invoke(app, ["task", "packet", "task-0001"])
    assert packet_res.exit_code == 0
    packet = json.loads(packet_res.output)

    included = packet["bounded_sources"]["included_summaries"]
    prd_summary = next(item for item in included if "prd.md" in item["source"])
    
    assert prd_summary["truncated"] is True
    assert prd_summary["original_chars"] > 4000
    assert prd_summary["included_chars"] == 4000
    assert "DISTINCTIVE_TAIL" not in prd_summary["content"]
    assert len(prd_summary["content"]) <= 4000


def test_8_preview_is_read_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Test 8: preview is read-only
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    brief_path = tmp_path / "my_goal.md"
    brief_path.write_text("## Goal Brief\nImplement durables.", encoding="utf-8")

    runner = CliRunner()
    runner.invoke(app, ["goal", "init", "--from", "my_goal.md"])
    runner.invoke(app, ["goal", "create-task", "G-0001", "TS-0001"])

    t_dir = tmp_path / ".devflow" / "tasks" / "task-0001"
    g_dir = goal_dir(tmp_path, "G-0001")

    # Snapshot all file contents
    snapshot = {}
    for folder in [g_dir, t_dir]:
        for item in folder.rglob("*"):
            if item.is_file():
                snapshot[item.as_posix()] = item.read_bytes()

    # Run preview packet command
    packet_res = runner.invoke(app, ["task", "packet", "task-0001"])
    assert packet_res.exit_code == 0

    # Ensure no files were modified or written
    for folder in [g_dir, t_dir]:
        for item in folder.rglob("*"):
            if item.is_file():
                assert item.as_posix() in snapshot
                assert item.read_bytes() == snapshot[item.as_posix()]


def test_9_save_writes_packet_artifact_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Test 9: save writes packet artifact only
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    brief_path = tmp_path / "my_goal.md"
    brief_path.write_text("## Goal Brief\nImplement durables.", encoding="utf-8")

    runner = CliRunner()
    runner.invoke(app, ["goal", "init", "--from", "my_goal.md"])
    runner.invoke(app, ["goal", "create-task", "G-0001", "TS-0001"])

    # Run packet with --save
    save_res = runner.invoke(app, ["task", "packet", "task-0001", "--save"])
    assert save_res.exit_code == 0
    assert "Wrote .devflow/tasks/task-0001/packet.json" in save_res.output
    assert "Wrote .devflow/tasks/task-0001/packet.md" in save_res.output

    # Verify files exist
    assert (tmp_path / ".devflow" / "tasks" / "task-0001" / "packet.json").exists()
    assert (tmp_path / ".devflow" / "tasks" / "task-0001" / "packet.md").exists()

    # Verify task state is unchanged
    task_yaml = yaml.safe_load((tmp_path / ".devflow" / "tasks" / "task-0001" / "task.yaml").read_text(encoding="utf-8"))
    assert task_yaml["status"] == "created"


def test_10_malformed_context_pointers_yaml_fails_safely_or_warns(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Test 10: malformed context-pointers.yaml fails safely or warns
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    brief_path = tmp_path / "my_goal.md"
    brief_path.write_text("## Goal Brief\nImplement durables.", encoding="utf-8")

    runner = CliRunner()
    runner.invoke(app, ["goal", "init", "--from", "my_goal.md"])
    runner.invoke(app, ["goal", "create-task", "G-0001", "TS-0001"])

    # Corrupt context-pointers.yaml
    cp_path = goal_dir(tmp_path, "G-0001") / "context-pointers.yaml"
    cp_path.write_text("{invalid: yaml [", encoding="utf-8")

    packet_res = runner.invoke(app, ["task", "packet", "task-0001"])
    assert packet_res.exit_code == 0
    
    packet = json.loads(packet_res.output)
    cb = packet["context_budget"]
    assert cb is not None
    # Context budget falls back to defaults safely
    assert cb["strategy"] == "focused_task_packet"
    
    # Warning was captured in operator_warnings
    warnings = packet["operator_warnings"]
    assert any("context-pointers.yaml" in w and "failed to parse" in w for w in warnings)


def test_11_missing_goal_artifact_warns(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Test 11: missing goal artifact warns
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    brief_path = tmp_path / "my_goal.md"
    brief_path.write_text("## Goal Brief\nImplement durables.", encoding="utf-8")

    runner = CliRunner()
    runner.invoke(app, ["goal", "init", "--from", "my_goal.md"])
    runner.invoke(app, ["goal", "create-task", "G-0001", "TS-0001"])

    # Delete prd.md
    prd_path = goal_dir(tmp_path, "G-0001") / "prd.md"
    prd_path.unlink()

    packet_res = runner.invoke(app, ["task", "packet", "task-0001"])
    assert packet_res.exit_code == 0
    
    packet = json.loads(packet_res.output)
    warnings = packet["operator_warnings"]
    assert any("prd.md is missing" in w for w in warnings)
    
    # Assert other details still populated
    assert packet["task_id"] == "task-0001"
    assert packet["goal_context"]["linked"] is True


def test_12_no_worker_model_registry_side_effects(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Test 12: no worker/model/registry side effects
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    brief_path = tmp_path / "my_goal.md"
    brief_path.write_text("## Goal Brief\nImplement durables.", encoding="utf-8")

    runner = CliRunner()
    runner.invoke(app, ["goal", "init", "--from", "my_goal.md"])
    runner.invoke(app, ["goal", "create-task", "G-0001", "TS-0001"])

    packet_res = runner.invoke(app, ["task", "packet", "task-0001"])
    assert packet_res.exit_code == 0

    # Assert task status remains created
    task_yaml = yaml.safe_load((tmp_path / ".devflow" / "tasks" / "task-0001" / "task.yaml").read_text(encoding="utf-8"))
    assert task_yaml["status"] == "created"
    assert task_yaml["verification_status"] == "not_run"

    # Assert no worker log is written or runs
    worker_log = tmp_path / ".devflow" / "tasks" / "task-0001" / "logs" / "worker.log"
    assert worker_log.read_text(encoding="utf-8") == ""
