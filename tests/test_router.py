from __future__ import annotations

import json
from pathlib import Path
import pytest
from typer.testing import CliRunner

from devflow.control_room.persistence import save_task, get_task
from devflow.control_room.service import create_task
from devflow.control_room.router import route_task, save_routing_decision
from devflow.cli import app


def test_router_heuristics_and_saving(tmp_path: Path) -> None:
    # 1. Initialize structures
    (tmp_path / ".devflow/tasks").mkdir(parents=True)
    (tmp_path / ".devflow/workspaces").mkdir(parents=True)
    (tmp_path / ".devflow/agents").mkdir(parents=True)

    # 2. Write mock agents registry.yaml
    registry_file = tmp_path / ".devflow/agents/registry.yaml"
    registry_file.write_text("""version: 1
default_agent: local-shell
agents:
  local-shell:
    provider: shell
    model: local-shell
    adapter: shell
    role: test_runner
    tier: local
    default_mode: verify_only
    workspace: isolated_task_workspace
    enabled: true
  qwen-senior:
    provider: local
    model: qwen2.5-coder:14b
    adapter: ollama_chat
    role: senior_developer_worker
    tier: strong_local
    default_mode: workspace_write
    workspace: isolated_task_workspace
    enabled: true
  openai-architect:
    provider: openai
    model: gpt-4o
    adapter: openai_chat
    role: frontier_planner_architect
    tier: frontier
    default_mode: read_only
    workspace: isolated_task_workspace
    enabled: true
""", encoding="utf-8")

    # Create dummy task
    task = create_task(tmp_path, "Refactor core model selection algorithms")
    task_dir_path = tmp_path / ".devflow/tasks" / task.id
    save_task(task_dir_path, task)

    # Run router
    routing_res = route_task(tmp_path, task.id)
    rd = routing_res["routing_decision"]

    # Verify agent matching selections
    assert rd["task_id"] == task.id
    selected = rd["selected"]
    assert selected["planner"] == "openai-architect"
    assert selected["worker"] == "qwen-senior"
    assert selected["reviewer"] == "openai-architect" # Fallback cheapest/only eligible for reviewer/architect in registry

    # Test saving
    save_routing_decision(tmp_path, task.id, routing_res)
    yaml_file = task_dir_path / "routing-decision.yaml"
    assert yaml_file.exists()
    
    yaml_content = yaml_file.read_text(encoding="utf-8")
    assert "routing_decision:" in yaml_content
    assert "selected:" in yaml_content
    assert "planner: openai-architect" in yaml_content


def test_router_cli_command(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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
    result = runner.invoke(app, ["task", "route", task.id])

    assert result.exit_code == 0
    assert "Executed routing mapping for task" in result.output
    assert "Wrote routing-decision.yaml" in result.output

    # Check files exist
    yaml_file = task_dir_path / "routing-decision.yaml"
    assert yaml_file.exists()
