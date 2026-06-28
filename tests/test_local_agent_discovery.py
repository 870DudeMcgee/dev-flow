from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from typer.testing import CliRunner

from devflow.cli import app
from devflow.control_room.agent_registry import load_agent_registry
from devflow.control_room.local_agent_discovery import (
    classify_local_model,
    parse_ollama_list,
    parse_ollama_show,
    rank_local_agent_candidates,
    write_selected_agent_evidence,
)
from devflow.control_room.service import create_task
from tests.helpers import setup_temp_git_repo


runner = CliRunner()


OLLAMA_LIST = """NAME                       ID              SIZE      MODIFIED
gemma4:12b-it-qat          38044be4f923    7.2 GB    3 days ago
"""


GEMMA4_12B_SHOW = """  Model
    architecture        gemma4
    parameters          11.9B
    context length      262144
    embedding length    3840
    quantization        Q4_0
    requires            0.30.5

  Capabilities
    completion
    vision
    audio
    tools
    thinking

  Parameters
    top_p          0.95
    temperature    1
    top_k          64

  License
    Apache License
"""


def test_parse_ollama_list_extracts_installed_models() -> None:
    models = parse_ollama_list(OLLAMA_LIST)

    assert len(models) == 1
    assert models[0].name == "gemma4:12b-it-qat"
    assert models[0].model_id == "38044be4f923"
    assert models[0].size == "7.2 GB"
    assert models[0].modified == "3 days ago"


def test_parse_ollama_show_and_classify_gemma4_12b_qat() -> None:
    manifest = parse_ollama_show("gemma4:12b-it-qat", GEMMA4_12B_SHOW)
    profile = classify_local_model(manifest)

    assert manifest.model == "gemma4:12b-it-qat"
    assert manifest.architecture == "gemma4"
    assert manifest.parameters == "11.9B"
    assert manifest.context_length == 262144
    assert manifest.embedding_length == 3840
    assert manifest.quantization == "Q4_0"
    assert "thinking" in manifest.capabilities
    assert profile.model == "gemma4:12b-it-qat"
    assert profile.provider == "ollama"
    assert profile.weight_class == "medium"
    assert profile.trust_level == "manifest_verified"
    assert "summarizer" in profile.allowed_roles
    assert "reviewer" in profile.allowed_roles
    assert "bounded_worker" in profile.allowed_roles
    assert "patch_proposer_candidate" in profile.allowed_roles


def test_rank_local_agent_candidates_selects_installed_registry_patch_agent(tmp_path: Path) -> None:
    _write_gemma_patch_agent_registry(tmp_path)
    registry = load_agent_registry(tmp_path)
    installed = parse_ollama_list(OLLAMA_LIST)

    selection = rank_local_agent_candidates(registry, installed, role="implementation_worker")

    assert selection.status == "selected"
    assert selection.selected_agent_id == "gemma4-12b-qat-implementer"
    assert selection.selected_model == "gemma4:12b-it-qat"
    assert selection.candidates[0].agent_id == "gemma4-12b-qat-implementer"
    missing = [candidate for candidate in selection.candidates if candidate.agent_id == "qwopus-implementer"]
    assert missing
    assert missing[0].eligible is False
    assert "model_not_installed" in missing[0].reasons


def test_rank_local_agent_candidates_refuses_when_installed_model_is_read_only(tmp_path: Path) -> None:
    registry = load_agent_registry(tmp_path)
    installed = parse_ollama_list(OLLAMA_LIST)

    selection = rank_local_agent_candidates(registry, installed, role="implementation_worker")

    assert selection.status == "no_eligible_agent"
    assert selection.selected_agent_id is None
    assert selection.unregistered_installed_models == []
    assert all(candidate.model != "gemma4:12b-it-qat" for candidate in selection.candidates)


def test_write_selected_agent_evidence_records_explicit_choice(tmp_path: Path) -> None:
    _write_gemma_patch_agent_registry(tmp_path)
    (tmp_path / ".devflow/tasks/task-0001").mkdir(parents=True)
    registry = load_agent_registry(tmp_path)
    selection = rank_local_agent_candidates(registry, parse_ollama_list(OLLAMA_LIST), role="implementation_worker")

    path = write_selected_agent_evidence(tmp_path, "task-0001", selection)

    assert path == tmp_path / ".devflow/tasks/task-0001/agent-selection.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["selected_agent_id"] == "gemma4-12b-qat-implementer"
    assert payload["selected_model"] == "gemma4:12b-it-qat"
    assert payload["next_command"] == "devflow task run task-0001 --worker gemma4-12b-qat-implementer"
    assert payload["will_run_worker"] is False


def test_cli_discovers_and_selects_local_agent_with_mocked_ollama(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    _write_gemma_patch_agent_registry(tmp_path)
    create_result = runner.invoke(app, ["task", "create", "select installed local agent"])
    assert create_result.exit_code == 0, create_result.output

    monkeypatch.setattr(subprocess, "run", _fake_ollama_run)

    discover = runner.invoke(app, ["agent", "discover-local", "--json"])
    assert discover.exit_code == 0, discover.output
    discover_payload = json.loads(discover.output)
    assert discover_payload["installed_models"][0]["name"] == "gemma4:12b-it-qat"
    assert discover_payload["capability_profiles"][0]["model"] == "gemma4:12b-it-qat"

    select = runner.invoke(app, ["agent", "select-local", "task-0001", "--role", "implementation_worker", "--json"])
    assert select.exit_code == 0, select.output
    select_payload = json.loads(select.output)
    assert select_payload["selected_agent_id"] == "gemma4-12b-qat-implementer"
    assert select_payload["selection_path"] == ".devflow/tasks/task-0001/agent-selection.json"
    assert (tmp_path / ".devflow/tasks/task-0001/agent-selection.json").exists()


def test_select_local_project_scopes_selection_evidence_and_next_command(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    monkeypatch.setenv("DEVFLOW_HOME", (tmp_path / "home" / ".devflow").as_posix())
    projects_root = tmp_path / "projects"
    control_root = tmp_path / "control-room"
    control_root.mkdir()
    project = runner.invoke(
        app,
        [
            "project",
            "create",
            "Alpha App",
            "--projects-root",
            projects_root.as_posix(),
            "--source-control",
            "none",
        ],
    )
    assert project.exit_code == 0, project.output
    project_root = projects_root / "alpha-app"
    _write_gemma_patch_agent_registry(project_root)
    task = create_task(project_root, "select project local agent")

    monkeypatch.setattr(subprocess, "run", _fake_ollama_run)
    monkeypatch.chdir(control_root)

    select = runner.invoke(
        app,
        ["agent", "select-local", task.id, "--project", "alpha-app", "--role", "implementation_worker", "--json"],
    )

    assert select.exit_code == 0, select.output
    payload = json.loads(select.output)
    assert payload["selected_agent_id"] == "gemma4-12b-qat-implementer"
    assert payload["selection_path"] == f".devflow/tasks/{task.id}/agent-selection.json"
    assert payload["next_command"] == (
        f"devflow task run {task.id} --project alpha-app --worker gemma4-12b-qat-implementer"
    )
    saved = json.loads((project_root / ".devflow/tasks" / task.id / "agent-selection.json").read_text(encoding="utf-8"))
    assert saved["next_command"] == payload["next_command"]
    assert not (control_root / ".devflow").exists()


def _fake_ollama_run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
    if args == ["ollama", "list"]:
        return subprocess.CompletedProcess(args, 0, stdout=OLLAMA_LIST, stderr="")
    if args == ["ollama", "show", "gemma4:12b-it-qat"]:
        return subprocess.CompletedProcess(args, 0, stdout=GEMMA4_12B_SHOW, stderr="")
    return subprocess.CompletedProcess(args, 1, stdout="", stderr=f"unexpected command: {args}")


def _write_gemma_patch_agent_registry(root: Path) -> None:
    agents_dir = root / ".devflow" / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    (agents_dir / "registry.yaml").write_text(
        """version: 1
agents:
  gemma4-12b-qat-implementer:
    provider: ollama
    model: gemma4:12b-it-qat
    adapter: ollama_chat
    role: implementation_worker
    tier: strong_local
    default_mode: workspace_write
    execution_mode: automated
    workspace: isolated_task_workspace
    can_see:
      - task_packet
      - assigned_workspace
    can_touch:
      - "<workspace>/**"
      - "<task>/agents/gemma4-12b-qat-implementer/proposal.patch"
    cannot_touch:
      - "<main_checkout>/**"
      - ".git/**"
    allowed_reads:
      - "<task>/packet.json"
      - "<workspace>/**"
    allowed_writes:
      - "<workspace>/**"
      - "<task>/agents/gemma4-12b-qat-implementer/proposal.patch"
      - "<task>/agents/gemma4-12b-qat-implementer/result.md"
      - "<task>/agents/gemma4-12b-qat-implementer/run.json"
      - "<task>/agents/gemma4-12b-qat-implementer/raw_output.md"
      - "<task>/agents/gemma4-12b-qat-implementer/logs/**"
      - "<task>/agents/gemma4-12b-qat-implementer/worker_failed.json"
    forbidden_writes:
      - "<main_checkout>/**"
      - ".git/**"
    required_outputs:
      - "Write proposal.patch and result.md under the agent evidence directory."
    completion_rules:
      - "Dev-Flow applies proposal.patch separately."
    can_run_shell: false
    can_use_network: false
    can_promote: false
    enabled: true
""",
        encoding="utf-8",
    )
