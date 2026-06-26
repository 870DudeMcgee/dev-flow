from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from devflow.cli import app
from devflow.control_room.agent_registry import load_agent_registry, load_provider_registry
from devflow.control_room.agent_runtime import agent_runtime_contract
from devflow.control_room.operating_layer import build_operating_layer_snapshot
from tests.helpers import setup_temp_git_repo


runner = CliRunner()


def test_agent_add_provider_dry_run_then_writes_structured_provider(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    dry_run = runner.invoke(
        app,
        [
            "agent",
            "add-provider",
            "local_gateway",
            "--adapter",
            "openai_compatible",
            "--base-url",
            "http://127.0.0.1:8000/v1",
            "--api-key-env",
            "LOCAL_GATEWAY_API_KEY",
            "--dry-run",
            "--json",
        ],
    )

    assert dry_run.exit_code == 0, dry_run.output
    dry_payload = json.loads(dry_run.output)
    assert dry_payload["dry_run"] is True
    assert dry_payload["will_write"] is False
    assert not (tmp_path / ".devflow/providers/local_gateway.yaml").exists()

    write = runner.invoke(
        app,
        [
            "agent",
            "add-provider",
            "local_gateway",
            "--adapter",
            "openai_compatible",
            "--base-url",
            "http://127.0.0.1:8000/v1",
            "--api-key-env",
            "LOCAL_GATEWAY_API_KEY",
            "--timeout-seconds",
            "45",
            "--json",
        ],
    )

    assert write.exit_code == 0, write.output
    payload = json.loads(write.output)
    assert payload["status"] == "created"
    provider = load_provider_registry(tmp_path).require_provider("local_gateway")
    assert provider.adapter == "openai_compatible"
    assert provider.base_url == "http://127.0.0.1:8000/v1"
    assert provider.api_key_env == "LOCAL_GATEWAY_API_KEY"
    assert provider.default_timeout_seconds == 45


def test_agent_add_model_generates_local_read_only_profile_with_runtime_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(
        app,
        [
            "agent",
            "add-model",
            "--provider",
            "ollama",
            "--model",
            "llama3.2:latest",
            "--authority",
            "read-only",
            "--role",
            "local_senior_worker",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    profile_id = payload["profile_id"]
    assert payload["status"] == "created"
    assert payload["dry_run"] is False

    agent = load_agent_registry(tmp_path).require_agent(profile_id)
    assert agent.provider == "ollama"
    assert agent.model == "llama3.2:latest"
    assert agent.default_mode == "read_only"
    assert agent.allowed_writes == ["<task>/local-model-runs/**"]
    assert "<workspace>/**" in agent.forbidden_writes
    contract = agent_runtime_contract(tmp_path, agent)
    assert contract["execution_surface"] == "agent_run"
    assert contract["agent_run_allowed"] is True
    assert contract["task_run_allowed"] is False
    assert contract["next_command"] == f"devflow agent run --task <task-id> --profile {profile_id} --json"


def test_agent_add_model_supports_generic_remote_advisory_and_patch_profiles(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    add_provider = runner.invoke(
        app,
        [
            "agent",
            "add-provider",
            "acme_ai",
            "--adapter",
            "openai_compatible",
            "--base-url",
            "https://models.example.test/v1",
            "--api-key-env",
            "ACME_AI_API_KEY",
            "--json",
        ],
    )
    assert add_provider.exit_code == 0, add_provider.output

    advisory = runner.invoke(
        app,
        [
            "agent",
            "add-model",
            "--provider",
            "acme_ai",
            "--model",
            "acme/careful-reviewer",
            "--authority",
            "advisory",
            "--role",
            "frontier_planner_architect_reviewer",
            "--json",
        ],
    )
    patch = runner.invoke(
        app,
        [
            "agent",
            "add-model",
            "--provider",
            "acme_ai",
            "--model",
            "acme/careful-coder",
            "--authority",
            "patch-proposer",
            "--role",
            "implementation_worker",
            "--json",
        ],
    )

    assert advisory.exit_code == 0, advisory.output
    assert patch.exit_code == 0, patch.output
    registry = load_agent_registry(tmp_path)
    advisory_agent = registry.require_agent(json.loads(advisory.output)["profile_id"])
    patch_agent = registry.require_agent(json.loads(patch.output)["profile_id"])
    assert agent_runtime_contract(tmp_path, advisory_agent)["execution_surface"] == "agent_advise"
    assert agent_runtime_contract(tmp_path, patch_agent)["execution_surface"] == "agent_propose_patch"
    assert agent_runtime_contract(tmp_path, patch_agent)["next_command"].startswith("devflow agent propose-patch")


def test_agent_add_model_refuses_unknown_role_and_conflicting_profile_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    unknown_role = runner.invoke(
        app,
        [
            "agent",
            "add-model",
            "--provider",
            "ollama",
            "--model",
            "llama3.2:latest",
            "--authority",
            "read-only",
            "--role",
            "made_up_role",
            "--json",
        ],
    )
    assert unknown_role.exit_code != 0
    assert "Unknown role" in unknown_role.output

    first = runner.invoke(
        app,
        [
            "agent",
            "add-model",
            "--provider",
            "ollama",
            "--model",
            "llama3.2:latest",
            "--authority",
            "read-only",
            "--role",
            "local_senior_worker",
            "--profile-id",
            "my-local-reviewer",
            "--json",
        ],
    )
    assert first.exit_code == 0, first.output

    conflict = runner.invoke(
        app,
        [
            "agent",
            "add-model",
            "--provider",
            "ollama",
            "--model",
            "qwen2.5-coder:7b-instruct",
            "--authority",
            "read-only",
            "--role",
            "local_senior_worker",
            "--profile-id",
            "my-local-reviewer",
            "--json",
        ],
    )
    assert conflict.exit_code != 0
    assert "already exists with different settings" in conflict.output


def test_agent_add_model_refuses_duplicate_builtin_model_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(
        app,
        [
            "agent",
            "add-model",
            "--provider",
            "ollama",
            "--model",
            "qwopus:latest",
            "--authority",
            "read-only",
            "--role",
            "local_senior_worker",
            "--json",
        ],
    )

    assert result.exit_code != 0
    assert "already registered" in result.output
    assert "local-qwopus-inspector" in result.output


def test_agent_catalog_reports_registered_and_unregistered_local_models(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    def fake_run_ollama(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
        if args == ["ollama", "list"]:
            return subprocess.CompletedProcess(
                args,
                0,
                stdout=(
                    "NAME              ID       SIZE      MODIFIED\n"
                    "llama3.2:latest   abc123   2.0 GB    1 day ago\n"
                    "registered:latest def456   4.0 GB    2 days ago\n"
                ),
                stderr="",
            )
        return subprocess.CompletedProcess(
            args,
            0,
            stdout=(
                "  Model\n"
                "    architecture        llama\n"
                "    parameters          8.0B\n"
                "    context length      8192\n"
                "    embedding length    4096\n"
                "    quantization        Q4_K_M\n"
                "  Capabilities\n"
                "    completion\n"
            ),
            stderr="",
        )

    monkeypatch.setattr("devflow.control_room.local_agent_discovery._run_ollama", fake_run_ollama)
    add_registered = runner.invoke(
        app,
        [
            "agent",
            "add-model",
            "--provider",
            "ollama",
            "--model",
            "registered:latest",
            "--authority",
            "read-only",
            "--role",
            "local_senior_worker",
            "--json",
        ],
    )
    assert add_registered.exit_code == 0, add_registered.output

    result = runner.invoke(app, ["agent", "catalog", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["schema_version"] == 1
    assert "ollama" in [provider["id"] for provider in payload["providers"]]
    assert "llama3.2:latest" in payload["local_ollama"]["unregistered_models"]
    assert "registered:latest" not in payload["local_ollama"]["unregistered_models"]
    assert any(profile["model"] == "registered:latest" for profile in payload["profiles"])


def test_operating_layer_snapshot_exposes_agent_catalog_and_model_actions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    snapshot = build_operating_layer_snapshot(tmp_path).model_dump(mode="json")

    assert snapshot["agent_catalog"]["schema_version"] == 1
    assert any(provider["id"] == "ollama" for provider in snapshot["agent_catalog"]["providers"])
    assert any(action["command"].startswith("devflow agent catalog") for action in snapshot["agent_catalog"]["actions"])
    assert any("agent add-model" in action["command"] for action in snapshot["agent_catalog"]["actions"])
