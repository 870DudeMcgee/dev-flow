from __future__ import annotations

import os
import subprocess
from pathlib import Path

import yaml
from typer.testing import CliRunner

from devflow.cli import app
from devflow.control_room.orchestration_plan import build_orchestration_plan, validate_orchestration_plan
from devflow.control_room.service import create_task
from devflow.control_room.task_closure import close_task


runner = CliRunner()


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)


def _init_clean_devmode_repo(root: Path) -> None:
    _git(root, "init", "-b", "main")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "Test User")
    (root / "README.md").write_text("# Test Repo\n", encoding="utf-8")
    skill = root / "skills" / "using-devmode" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("name: using-devmode\n", encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "baseline")


def _commit_all(root: Path, message: str = "task baseline") -> None:
    _git(root, "add", ".")
    _git(root, "commit", "-m", message)


def test_plan_only_creates_orchestration_plan_for_active_task(tmp_path: Path) -> None:
    _init_clean_devmode_repo(tmp_path)
    task = create_task(tmp_path, "Split UI and verifier work")
    _commit_all(tmp_path)

    old_cwd = Path.cwd()
    try:
        os.chdir(tmp_path)
        result = runner.invoke(app, ["task", "orchestrate", task.id, "--plan-only"])
    finally:
        os.chdir(old_cwd)

    assert result.exit_code == 0, result.output
    assert "provider_calls: none" in result.output
    assert "workers_executed: none" in result.output
    assert "main_changed: no" in result.output
    assert "serial_local_agent_pipeline: implementer -> verifier -> tiny_repair -> supervisor_final_gate" in result.output

    plan_path = tmp_path / ".devflow" / "tasks" / task.id / "orchestration-plan.yaml"
    plan = yaml.safe_load(plan_path.read_text(encoding="utf-8"))
    assert plan["schema_version"] == 1
    assert plan["policy_version"]
    assert plan["mode"] == "plan_only"
    assert plan["git_baseline"]["current_branch"] == "main"
    assert plan["devmode_required"] is True
    assert plan["parallelism_allowed"] is True
    assert plan["promotion"]["requires_human"] is True
    assert plan["promotion"]["requires_verification_passed"] is True
    assert plan["promotion"]["allowed_by_workers"] is False
    assert all(role["can_promote"] is False for role in plan["roles"])
    serial = plan["serial_local_agent_pipeline"]
    assert serial["strategy"] == "serial_specialists"
    assert serial["single_flight_required"] is True
    assert serial["acceptance_owner"] == "supervisor_final_gate"
    assert [phase["phase"] for phase in serial["phases"]] == [
        "implementer",
        "verifier",
        "tiny_repair",
        "supervisor_final_gate",
    ]
    assert serial["phases"][0]["may_edit"] is True
    assert serial["phases"][1]["may_edit"] is False
    assert serial["phases"][2]["context_policy"] == "fresh_tiny_repair_packet"
    assert serial["phases"][3]["agent_kind"] == "supervisor"
    assert all(phase["can_promote"] is False for phase in serial["phases"])


def test_closed_task_is_refused(tmp_path: Path) -> None:
    _init_clean_devmode_repo(tmp_path)
    task = create_task(tmp_path, "Closed task")
    close_task(tmp_path, task.id, outcome="rejected", reason="done elsewhere")

    old_cwd = Path.cwd()
    try:
        os.chdir(tmp_path)
        result = runner.invoke(app, ["task", "orchestrate", task.id, "--plan-only"])
    finally:
        os.chdir(old_cwd)

    assert result.exit_code == 1
    assert "inactive" in result.output
    assert not (tmp_path / ".devflow" / "tasks" / task.id / "orchestration-plan.yaml").exists()


def test_validator_rejects_read_only_source_write_and_planned_execution(tmp_path: Path) -> None:
    _init_clean_devmode_repo(tmp_path)
    task = create_task(tmp_path, "Validate role policy")
    _commit_all(tmp_path)
    plan = build_orchestration_plan(tmp_path, task)

    plan["roles"][0]["can_write"] = ["src/devflow/control_room/new.py"]
    errors = validate_orchestration_plan(plan)
    assert any("read_only role cannot have source write permissions" in error for error in errors)

    plan = build_orchestration_plan(tmp_path, task)
    plan["roles"][6]["execution_mode"] = "workspace_write"
    errors = validate_orchestration_plan(plan)
    assert any("planned_not_executable role cannot be scheduled" in error for error in errors)

    plan = build_orchestration_plan(tmp_path, task)
    plan["serial_local_agent_pipeline"]["phases"][1]["may_edit"] = True
    errors = validate_orchestration_plan(plan)
    assert any("verification/final gate must not edit" in error for error in errors)

    plan = build_orchestration_plan(tmp_path, task)
    plan["serial_local_agent_pipeline"]["phases"] = list(reversed(plan["serial_local_agent_pipeline"]["phases"]))
    errors = validate_orchestration_plan(plan)
    assert any("implementer -> verifier -> tiny_repair -> supervisor_final_gate" in error for error in errors)


def test_parallelism_false_when_git_state_is_dirty_or_task_is_ambiguous(tmp_path: Path) -> None:
    _init_clean_devmode_repo(tmp_path)
    task = create_task(tmp_path, "unclear?")
    _commit_all(tmp_path)
    (tmp_path / "dirty.txt").write_text("dirty\n", encoding="utf-8")

    plan = build_orchestration_plan(tmp_path, task)

    assert plan["parallelism_allowed"] is False
    active = {item["condition"] for item in plan["stop_conditions"] if item["active"]}
    assert "dirty_git_tree" in active
    assert "human_clarification_needed" in active


def test_validator_rejects_unsafe_paths(tmp_path: Path) -> None:
    _init_clean_devmode_repo(tmp_path)
    task = create_task(tmp_path, "Unsafe path validation")
    _commit_all(tmp_path)
    plan = build_orchestration_plan(tmp_path, task)

    plan["roles"][2]["can_write"] = ["../outside.py"]
    errors = validate_orchestration_plan(plan)
    assert any("parent traversal rejected" in error for error in errors)

    plan = build_orchestration_plan(tmp_path, task)
    plan["roles"][2]["can_write"] = ["/tmp/outside.py"]
    errors = validate_orchestration_plan(plan)
    assert any("absolute path rejected" in error for error in errors)


def test_command_preserves_existing_task_artifacts(tmp_path: Path) -> None:
    _init_clean_devmode_repo(tmp_path)
    task = create_task(tmp_path, "Preserve artifacts")
    _commit_all(tmp_path)
    task_dir = tmp_path / ".devflow" / "tasks" / task.id
    before = {
        "task": (task_dir / "task.yaml").read_text(encoding="utf-8"),
        "verification": (task_dir / "verification.json").read_text(encoding="utf-8"),
        "closure_exists": (task_dir / "closure.json").exists(),
        "cleanup_exists": (task_dir / "cleanup.json").exists(),
    }

    old_cwd = Path.cwd()
    try:
        os.chdir(tmp_path)
        result = runner.invoke(app, ["task", "orchestrate", task.id, "--plan-only"])
    finally:
        os.chdir(old_cwd)

    assert result.exit_code == 0, result.output
    assert (task_dir / "task.yaml").read_text(encoding="utf-8") == before["task"]
    assert (task_dir / "verification.json").read_text(encoding="utf-8") == before["verification"]
    assert (task_dir / "closure.json").exists() is before["closure_exists"]
    assert (task_dir / "cleanup.json").exists() is before["cleanup_exists"]
