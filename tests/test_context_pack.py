from __future__ import annotations

import json
from pathlib import Path
import pytest
from typer.testing import CliRunner

from devflow.control_room.persistence import save_task
from devflow.control_room.service import create_task
from devflow.control_room.context_pack import build_context_pack, save_context_pack, write_context_pack
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
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir(parents=True)
    sf = docs_dir / "DEVFLOW_SOURCE_OF_TRUTH.md"
    sf.write_text("# DevFlow Source of Truth\nIdea -> Brainstorm -> Spec -> Plan -> Judge -> Build -> Judge -> Verify\n", encoding="utf-8")

    # Add dummy source files
    src_dir = tmp_path / "src/devflow/control_room"
    src_dir.mkdir(parents=True)
    source_file = src_dir / "service.py"
    source_file.write_text("def run_task():\n    pass\n", encoding="utf-8")

    # 3. Test Planner Pack
    planner_pack = build_context_pack(tmp_path, task.id, "planner")
    cp = planner_pack["context_pack"]
    assert cp["role"] == "planner"
    assert any("docs/DEVFLOW_SOURCE_OF_TRUTH.md" in inc for inc in cp["includes"])
    # Planner excludes raw source code content
    assert any("src/devflow/control_room/service.py" in exc for exc in cp["excludes"])

    # Test Worker Pack
    worker_pack = build_context_pack(tmp_path, task.id, "worker")
    cp_w = worker_pack["context_pack"]
    assert cp_w["role"] == "worker"
    # Worker includes raw source code
    assert any("src/devflow/control_room/service.py" in inc for inc in cp_w["includes"])
    # Worker excludes vision docs
    assert any("docs/DEVFLOW_SOURCE_OF_TRUTH.md" in exc for exc in cp_w["excludes"])

    # 4. Save pack and verify yaml existence
    save_context_pack(tmp_path, task.id, "planner", planner_pack)
    yaml_file = task_dir_path / "context-pack-planner.yaml"
    assert yaml_file.exists()
    
    yaml_content = yaml_file.read_text(encoding="utf-8")
    assert "role: planner" in yaml_content
    assert "docs/DEVFLOW_SOURCE_OF_TRUTH.md" in yaml_content


def test_context_pack_cli_command(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # 1. Initialize structures
    (tmp_path / ".devflow/tasks").mkdir(parents=True)
    (tmp_path / ".devflow/workspaces").mkdir(parents=True)

    # 2. Create task
    task = create_task(tmp_path, "Clean up documentation in docs/DEVFLOW_SOURCE_OF_TRUTH.md")
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


def test_build_context_pack_is_role_scoped_and_derived(tmp_path: Path) -> None:
    task = create_task(tmp_path, "Implement context pack")

    pack = build_context_pack(
        tmp_path,
        task.id,
        agent_id="ornith-builder",
        role="implementation_worker",
    )

    assert pack.task_id == task.id
    assert pack.agent_id == "ornith-builder"
    assert pack.role == "implementation_worker"
    assert (
        pack.source_packet_path
        == f".devflow/tasks/{task.id}/context-packs/implementation_worker-ornith-builder.packet.json"
    )
    assert "<task>/task.yaml" in pack.included_sources
    assert ".env" in "\n".join(pack.excluded_sources)
    assert pack.estimated_chars > 0
    assert pack.estimated_tokens >= 1


def test_write_context_pack_writes_json_and_markdown_without_mutating_task(tmp_path: Path) -> None:
    task = create_task(tmp_path, "Write context pack")
    task_yaml = tmp_path / ".devflow" / "tasks" / task.id / "task.yaml"
    before = task_yaml.read_text(encoding="utf-8")

    result = write_context_pack(
        tmp_path,
        task.id,
        agent_id="ornith-builder",
        role="reviewer",
    )

    assert result.json_path.is_file()
    assert result.markdown_path.is_file()
    payload = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert payload["role"] == "reviewer"
    assert payload["agent_id"] == "ornith-builder"
    assert task_yaml.read_text(encoding="utf-8") == before


def test_agent_context_pack_cli_writes_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    assert runner.invoke(app, ["task", "create", "Context CLI"]).exit_code == 0

    result = runner.invoke(
        app,
        ["agent", "context-pack", "task-0001", "ornith-builder", "--role", "implementation_worker", "--json"],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["task_id"] == "task-0001"
    assert payload["agent_id"] == "ornith-builder"
    assert payload["json_path"].endswith("implementation_worker-ornith-builder.json")
