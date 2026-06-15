from __future__ import annotations

import json
import subprocess
from pathlib import Path

from typer.testing import CliRunner

from devflow.cli import app
from devflow.control_room.service import create_task
from devflow.control_room.supervisor_surface import (
    APPROVAL_REQUIRED_TASK_STATE,
    APPROVAL_REQUIRED_WORKER_RUNTIME,
    PURE_READ_ONLY,
)
from devflow.control_room.telegram_routing import route_telegram_message


runner = CliRunner()


def _read_json(result) -> dict:
    assert result.exit_code == 0, result.output
    return json.loads(result.output)


def _snapshot(root: Path) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file() and ".git" not in path.parts:
            files[path.relative_to(root).as_posix()] = path.read_bytes()
    return files


def test_simple_chat_defaults_to_gemma_footer(tmp_path: Path) -> None:
    decision = route_telegram_message(tmp_path, "ping")

    assert decision["route"] == "simple_chat"
    assert decision["model"] == "gemma4:latest"
    assert decision["action"] == "answer"
    assert decision["routing_footer"] == "route: simple_chat\nmodel: gemma4:latest\naction: answer"


def test_devflow_status_routes_to_safe_read_command(tmp_path: Path) -> None:
    create_task(tmp_path, "status task")

    decision = route_telegram_message(tmp_path, "quick DevFlow status please")

    assert decision["route"] == "devflow_read"
    assert decision["model"] == "gemma4:latest"
    assert decision["action"] == "run_safe_command"
    assert decision["recommended_command"] == "devflow status --json"
    assert decision["command_classification"]["safety_class"] == PURE_READ_ONLY
    assert decision["operator_plan"]["next_step"] == "run_recommended_command"
    assert decision["operator_plan"]["may_auto_run_command"] is True
    assert decision["operator_plan"]["telegram_reply_style"] == "short_summary_with_footer"


def test_devflow_status_tool_name_routes_to_safe_read_command(tmp_path: Path) -> None:
    decision = route_telegram_message(
        tmp_path,
        "Call devflow_status and summarize active_task_count in one short sentence.",
    )

    assert decision["route"] == "devflow_read"
    assert decision["action"] == "run_safe_command"
    assert decision["recommended_command"] == "devflow status --json"
    assert decision["operator_plan"]["next_step"] == "run_recommended_command"


def test_planning_and_deep_review_select_local_reasoning_models(tmp_path: Path) -> None:
    plan = route_telegram_message(tmp_path, "please plan the release risk review")
    deep = route_telegram_message(tmp_path, "deep architecture decision on the routing layer")

    assert plan["route"] == "plan"
    assert plan["model"] == "qwen3.6:latest"
    assert plan["action"] == "answer"
    assert deep["route"] == "deep_review"
    assert deep["model"] == "qwopus:latest"
    assert deep["action"] == "answer"
    assert deep["operator_plan"]["next_step"] == "answer_with_model"
    assert deep["operator_plan"]["model"] == "qwopus:latest"


def test_implementation_routes_to_task_or_codex_goal_without_model(tmp_path: Path) -> None:
    task_decision = route_telegram_message(tmp_path, "fix the failing dashboard tests")
    codex_decision = route_telegram_message(tmp_path, "create a Codex goal to refactor routing")

    assert task_decision["route"] == "implementation"
    assert task_decision["model"] is None
    assert task_decision["action"] == "create_task"
    assert task_decision["routing_footer"] == "route: implementation\nmodel: none\naction: create_task"
    assert task_decision["operator_plan"]["next_step"] == "request_human_approval"
    assert task_decision["operator_plan"]["approval_required"] is True
    assert task_decision["operator_plan"]["pending_action"]["kind"] == "devflow_command"
    assert task_decision["operator_plan"]["pending_action"]["command"].startswith("devflow task create ")
    assert "devflow task create" in task_decision["operator_plan"]["approval_prompt_hint"]
    assert codex_decision["route"] == "implementation"
    assert codex_decision["action"] == "create_codex_goal"
    assert codex_decision["operator_plan"]["pending_action"] is None


def test_project_read_routes_to_project_list(tmp_path: Path) -> None:
    decision = route_telegram_message(tmp_path, "list projects")

    assert decision["route"] == "devflow_read"
    assert decision["action"] == "run_safe_command"
    assert decision["recommended_command"] == "devflow project list"
    assert decision["command_classification"]["safety_class"] == PURE_READ_ONLY
    assert decision["operator_plan"]["next_step"] == "run_recommended_command"


def test_simple_folder_project_create_routes_to_pending_action(tmp_path: Path) -> None:
    decision = route_telegram_message(tmp_path, "create a simple folder project named telegram-smoke-test")

    assert decision["route"] == "implementation"
    assert decision["model"] is None
    assert decision["action"] == "create_project"
    assert decision["recommended_command"] == "devflow project create telegram-smoke-test --source-control none"
    assert decision["command_classification"]["safety_class"] == APPROVAL_REQUIRED_TASK_STATE
    assert decision["operator_plan"]["next_step"] == "request_human_approval"
    assert decision["operator_plan"]["pending_action"] == {
        "schema_version": 1,
        "kind": "devflow_command",
        "command": "devflow project create telegram-smoke-test --source-control none",
        "execute_once": True,
        "approval_required": True,
        "safety_class": APPROVAL_REQUIRED_TASK_STATE,
        "source": "operator_plan",
    }


def test_build_project_phrase_routes_to_pending_action(tmp_path: Path) -> None:
    decision = route_telegram_message(tmp_path, "build a simple folder project named telegram-smoke-test")

    assert decision["route"] == "implementation"
    assert decision["action"] == "create_project"
    assert decision["operator_plan"]["pending_action"]["command"] == (
        "devflow project create telegram-smoke-test --source-control none"
    )


def test_embedded_safe_command_may_auto_run(tmp_path: Path) -> None:
    decision = route_telegram_message(tmp_path, "run `devflow supervisor packet --json`")

    assert decision["route"] == "devflow_read"
    assert decision["model"] == "gemma4:latest"
    assert decision["action"] == "run_safe_command"
    assert decision["recommended_command"] == "devflow supervisor packet --json"
    assert decision["command_classification"]["supervisor_may_auto_run"] is True


def test_embedded_agent_dry_run_command_may_auto_run(tmp_path: Path) -> None:
    decision = route_telegram_message(
        tmp_path,
        "run devflow agent run --task task-0001 --profile local-gemma4-summarizer --dry-run --json",
    )

    assert decision["route"] == "devflow_read"
    assert decision["action"] == "run_safe_command"
    assert decision["command_classification"]["safety_class"] == PURE_READ_ONLY
    assert decision["command_classification"]["supervisor_may_auto_run"] is True
    assert decision["operator_plan"]["next_step"] == "run_recommended_command"


def test_high_risk_command_requires_approval_instead_of_running(tmp_path: Path) -> None:
    decision = route_telegram_message(tmp_path, "run devflow task run task-0001 --worker shell -- echo hi")

    assert decision["route"] == "implementation"
    assert decision["model"] is None
    assert decision["action"] == "answer"
    assert decision["command_classification"]["safety_class"] == APPROVAL_REQUIRED_WORKER_RUNTIME
    assert decision["command_classification"]["requires_human_approval"] is True
    assert "human approval" in decision["reason"]
    assert decision["operator_plan"]["next_step"] == "request_human_approval"
    assert decision["operator_plan"]["recommended_command"] == "devflow task run task-0001 --worker shell -- echo hi"
    assert "I approve this exact Dev-Flow command" in decision["operator_plan"]["approval_prompt_hint"]


def test_dirty_git_tree_blocks_implementation_routing(tmp_path: Path) -> None:
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True, text=True)
    (tmp_path / "dirty.txt").write_text("dirty\n", encoding="utf-8")

    decision = route_telegram_message(tmp_path, "implement a new worker")

    assert decision["route"] == "devflow_read"
    assert decision["model"] == "gemma4:latest"
    assert decision["action"] == "answer"
    assert "dirty_git_tree_no_implementation" in decision["overrides"]


def test_dirty_git_tree_does_not_block_project_create_routing(tmp_path: Path) -> None:
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True, text=True)
    (tmp_path / "dirty.txt").write_text("dirty\n", encoding="utf-8")

    decision = route_telegram_message(tmp_path, "create a simple folder project named telegram-smoke-test")

    assert decision["route"] == "implementation"
    assert decision["action"] == "create_project"
    assert decision["operator_plan"]["pending_action"]["command"] == (
        "devflow project create telegram-smoke-test --source-control none"
    )


def test_unverified_task_blocks_implementation_routing(tmp_path: Path) -> None:
    task = create_task(tmp_path, "unverified task")

    decision = route_telegram_message(tmp_path, f"fix {task.id}")

    assert decision["route"] == "devflow_read"
    assert decision["model"] == "gemma4:latest"
    assert decision["action"] == "answer"
    assert "unverified_task_no_implementation" in decision["overrides"]
    assert decision["task_state"]["task_id"] == task.id


def test_supervisor_route_message_cli_is_read_only(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    create_task(tmp_path, "operator route")
    before = _snapshot(tmp_path)

    result = runner.invoke(app, ["supervisor", "route-message", "status please", "--json"])

    assert _snapshot(tmp_path) == before
    payload = _read_json(result)
    assert payload["route"] == "devflow_read"
    assert payload["routing_footer"] == "route: devflow_read\nmodel: gemma4:latest\naction: run_safe_command"
    assert payload["operator_plan"]["next_step"] == "run_recommended_command"
