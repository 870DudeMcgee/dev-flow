from __future__ import annotations

import json
from pathlib import Path
import pytest
from typer.testing import CliRunner

from devflow.control_room.persistence import save_task, get_task
from devflow.control_room.service import create_task
from devflow.control_room.context_pack import build_context_pack, save_context_pack
from devflow.cli import app


def test_context_pack_generation_and_saving(tmp_path: Path) -> None:
    # 1. Initialize seed structures
    (tmp_path / ".devflow/tasks").mkdir(parents=True)
    (tmp_path / ".devflow/workspaces").mkdir(parents=True)

    # 2. Create dummy task
    task = create_task(tmp_path, "Implement new model routing mechanism in src/devflow/control_room/service.py")
    task_dir_path = tmp_path / ".devflow/tasks" / task.id
    save_task(task_dir_path, task)

    # Add strategic files in mock root
    sf = tmp_path / "PRODUCT_NORTH_STAR.md"
    sf.write_text("# Product Vision\ncontrol room first milestone\n", encoding="utf-8")

    # Add dummy source files
    src_dir = tmp_path / "src/devflow/control_room"
    src_dir.mkdir(parents=True)
    source_file = src_dir / "service.py"
    source_file.write_text("def run_task():\n    pass\n", encoding="utf-8")

    # 3. Test Planner Pack
    planner_pack = build_context_pack(tmp_path, task.id, "planner")
    cp = planner_pack["context_pack"]
    assert cp["role"] == "planner"
    assert any("PRODUCT_NORTH_STAR.md" in inc for inc in cp["includes"])
    # Planner excludes raw source code content
    assert any("src/devflow/control_room/service.py" in exc for exc in cp["excludes"])

    # Test Worker Pack
    worker_pack = build_context_pack(tmp_path, task.id, "worker")
    cp_w = worker_pack["context_pack"]
    assert cp_w["role"] == "worker"
    # Worker includes raw source code
    assert any("src/devflow/control_room/service.py" in inc for inc in cp_w["includes"])
    # Worker excludes vision docs
    assert any("PRODUCT_NORTH_STAR.md" in exc for exc in cp_w["excludes"])

    # 4. Save pack and verify yaml existence
    save_context_pack(tmp_path, task.id, "planner", planner_pack)
    yaml_file = task_dir_path / "context-pack-planner.yaml"
    assert yaml_file.exists()
    
    yaml_content = yaml_file.read_text(encoding="utf-8")
    assert "role: planner" in yaml_content
    assert "PRODUCT_NORTH_STAR.md" in yaml_content


def test_context_pack_cli_command(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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
    result = runner.invoke(app, ["task", "pack", task.id, "planner"])

    assert result.exit_code == 0
    assert "Compiled context pack for task" in result.output
    assert "Role:                          PLANNER" in result.output
    assert "Wrote context-pack-planner.yaml" in result.output

    # Check file exists
    yaml_file = task_dir_path / "context-pack-planner.yaml"
    assert yaml_file.exists()
