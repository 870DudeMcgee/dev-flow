from __future__ import annotations

import json
import subprocess
import threading
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from typer.testing import CliRunner

from devflow.cli import app
from devflow.control_room.agent_registry import load_agent_registry, load_provider_registry
from devflow.control_room.agent_runtime import agent_runtime_contract
from devflow.control_room.local_model_inventory import build_local_model_inventory
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


def test_agent_catalog_marks_local_availability_and_discovers_hermes_custom_models(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", tmp_path.as_posix())

    server, thread = _start_models_server(
        {
            "object": "list",
            "data": [
                {
                    "id": "qwen35-9b-mtp",
                    "object": "model",
                    "owned_by": "llamacpp",
                    "meta": {"n_ctx": 65536, "n_params": 9197093888},
                }
            ],
        }
    )
    port = server.server_address[1]
    hermes_config = tmp_path / ".hermes" / "config.yaml"
    hermes_config.parent.mkdir(parents=True)
    hermes_config.write_text(
        f"""custom_providers:
- name: qwen35-mtp
  base_url: http://127.0.0.1:{port}/v1
  api_mode: chat_completions
  model: qwen35-9b-mtp
  models:
    qwen35-9b-mtp:
      context_length: 65536
      n_params: 9B
      supports_vision: false
""",
        encoding="utf-8",
    )

    def fake_run_ollama(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
        if args == ["ollama", "list"]:
            return subprocess.CompletedProcess(
                args,
                0,
                stdout="NAME                       ID              SIZE      MODIFIED\n"
                "gemma4:12b-it-qat          38044be4f923    7.2 GB    3 days ago\n",
                stderr="",
            )
        return subprocess.CompletedProcess(
            args,
            0,
            stdout=(
                "  Model\n"
                "    architecture        gemma4\n"
                "    parameters          11.9B\n"
                "    context length      262144\n"
                "    embedding length    3840\n"
                "    quantization        Q4_0\n"
                "  Capabilities\n"
                "    completion\n"
                "    thinking\n"
            ),
            stderr="",
        )

    monkeypatch.setattr("devflow.control_room.local_agent_discovery._run_ollama", fake_run_ollama)
    add_gemma = runner.invoke(
        app,
        [
            "agent",
            "add-model",
            "--provider",
            "ollama",
            "--model",
            "gemma4:12b-it-qat",
            "--authority",
            "patch-proposer",
            "--role",
            "implementation_worker",
            "--profile-id",
            "gemma4-12b-qat-implementer",
            "--json",
        ],
    )
    assert add_gemma.exit_code == 0, add_gemma.output
    try:
        result = runner.invoke(app, ["agent", "catalog", "--json"])
    finally:
        server.shutdown()
        thread.join(timeout=5)

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    profiles = {profile["id"]: profile for profile in payload["profiles"]}
    assert profiles["gemma4-12b-qat-implementer"]["availability"]["status"] == "available"
    assert profiles["qwopus-implementer"]["availability"]["status"] == "missing"
    assert profiles["qwopus-implementer"]["availability"]["reason"] == "model_not_installed"

    local_endpoints = payload["local_openai_compatible"]
    assert local_endpoints["status"] == "ready"
    provider = next(item for item in local_endpoints["providers"] if item["id"] == "hermes:qwen35-mtp")
    assert provider["id"] == "hermes:qwen35-mtp"
    assert provider["source"] == "hermes"
    assert provider["status"] == "ready"
    assert provider["advertised_models"][0]["id"] == "qwen35-9b-mtp"
    assert provider["advertised_models"][0]["context_length"] == 65536
    assert local_endpoints["unregistered_models"] == [
        {
            "base_url": f"http://127.0.0.1:{port}/v1",
            "model": "qwen35-9b-mtp",
            "provider_id": "hermes:qwen35-mtp",
            "source": "hermes",
        }
    ]


def test_agent_catalog_prefers_qwen35_and_marks_heavy_models_unsafe_on_mac_mini(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", tmp_path.as_posix())
    monkeypatch.setenv("DEVFLOW_MACHINE_RAM_GB", "16")

    server, thread = _start_models_server(
        {
            "object": "list",
            "data": [
                {
                    "id": "qwen35-9b-mtp",
                    "object": "model",
                    "owned_by": "llamacpp",
                    "meta": {"n_ctx": 65536, "n_params": 9197093888},
                },
                {
                    "id": "qwen-heavy-32b",
                    "object": "model",
                    "owned_by": "llamacpp",
                    "meta": {"n_ctx": 131072, "n_params": 32000000000},
                },
            ],
        }
    )
    port = server.server_address[1]
    hermes_config = tmp_path / ".hermes" / "config.yaml"
    hermes_config.parent.mkdir(parents=True)
    hermes_config.write_text(
        f"""model:
  default: qwen35-9b-mtp
  provider: custom:qwen35-mtp
  base_url: http://127.0.0.1:{port}/v1
  context_length: 65536
  supports_vision: false
custom_providers:
- name: qwen35-mtp
  base_url: http://127.0.0.1:{port}/v1
  api_mode: chat_completions
  model: qwen35-9b-mtp
  models:
    qwen35-9b-mtp:
      context_length: 65536
      n_params: 9B
      supports_vision: false
""",
        encoding="utf-8",
    )

    try:
        result = runner.invoke(app, ["agent", "catalog", "--json"])
    finally:
        server.shutdown()
        thread.join(timeout=5)

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    policy = payload["local_model_policy"]
    assert policy["default_model"] == "qwen35-9b-mtp"
    assert policy["default_provider_id"] == "hermes:qwen35-mtp"
    assert policy["local_model_concurrency"]["mode"] == "single_flight"
    assert policy["machine"]["total_memory_gb"] == 16
    assert policy["machine"]["max_recommended_weight_class"] == "medium"

    provider = next(item for item in payload["local_openai_compatible"]["providers"] if item["id"] == "hermes:qwen35-mtp")
    qwen = next(item for item in provider["advertised_models"] if item["id"] == "qwen35-9b-mtp")
    configured_qwen = next(item for item in provider["configured_models"] if item["id"] == "qwen35-9b-mtp")
    heavy = next(item for item in provider["advertised_models"] if item["id"] == "qwen-heavy-32b")
    assert qwen["machine_fit"]["status"] == "preferred"
    assert qwen["machine_fit"]["weight_class"] == "medium"
    assert configured_qwen["n_params"] == 9_000_000_000
    assert configured_qwen["machine_fit"]["weight_class"] == "medium"
    assert heavy["machine_fit"]["status"] == "not_recommended"
    assert "16 GB" in heavy["machine_fit"]["reason"]
    commands = [action["command"] for action in payload["actions"]]
    assert f"devflow agent add-provider qwen35-mtp --adapter openai_compatible --base-url http://127.0.0.1:{port}/v1" in commands
    assert (
        "devflow agent add-model --provider qwen35-mtp --model qwen35-9b-mtp "
        "--authority advisory --role frontier_planner_architect_reviewer --profile-id local-qwen35-mtp"
    ) in commands


def test_local_model_inventory_builds_machine_summary_and_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", tmp_path.as_posix())
    monkeypatch.setenv("DEVFLOW_MACHINE_RAM_GB", "16")

    server, thread = _start_models_server(
        {
            "object": "list",
            "data": [
                {
                    "id": "qwen35-9b-mtp",
                    "object": "model",
                    "owned_by": "llamacpp",
                    "meta": {"n_ctx": 65536, "n_params": 9197093888},
                }
            ],
        }
    )
    port = server.server_address[1]
    hermes_config = tmp_path / ".hermes" / "config.yaml"
    hermes_config.parent.mkdir(parents=True)
    hermes_config.write_text(
        f"""model:
  default: qwen35-9b-mtp
  provider: custom:qwen35-mtp
  base_url: http://127.0.0.1:{port}/v1
  context_length: 65536
custom_providers:
- name: qwen35-mtp
  base_url: http://127.0.0.1:{port}/v1
  model: qwen35-9b-mtp
""",
        encoding="utf-8",
    )

    add_provider = runner.invoke(
        app,
        [
            "agent",
            "add-provider",
            "qwen35-mtp",
            "--adapter",
            "openai_compatible",
            "--base-url",
            f"http://127.0.0.1:{port}/v1",
            "--json",
        ],
    )
    assert add_provider.exit_code == 0, add_provider.output
    add_model = runner.invoke(
        app,
        [
            "agent",
            "add-model",
            "--provider",
            "qwen35-mtp",
            "--model",
            "qwen35-9b-mtp",
            "--authority",
            "advisory",
            "--role",
            "frontier_planner_architect_reviewer",
            "--profile-id",
            "local-qwen35-mtp",
            "--json",
        ],
    )
    assert add_model.exit_code == 0, add_model.output

    try:
        result = runner.invoke(app, ["agent", "catalog", "--json"])
    finally:
        server.shutdown()
        thread.join(timeout=5)

    assert result.exit_code == 0, result.output
    inventory = build_local_model_inventory(json.loads(result.output))

    assert inventory["schema_version"] == 1
    assert inventory["summary"]["default_model"] == "qwen35-9b-mtp"
    assert inventory["summary"]["default_provider_id"] == "qwen35-mtp"
    assert inventory["summary"]["machine_label"] == "16GB mac_mini"
    assert inventory["summary"]["concurrency_label"] == "one local model at a time"
    assert inventory["summary"]["available_profile_count"] >= 1
    qwen = next(row for row in inventory["rows"] if row["row_id"] == "profile:local-qwen35-mtp")
    assert qwen == {
        "row_id": "profile:local-qwen35-mtp",
        "kind": "registered_profile",
        "provider_id": "qwen35-mtp",
        "provider_label": "qwen35-mtp",
        "model": "qwen35-9b-mtp",
        "profile_id": "local-qwen35-mtp",
        "selectable_profile_id": "local-qwen35-mtp",
        "status": "available",
        "status_label": "Available",
        "source": "local_openai_compatible",
        "adapter": "openai_compatible",
        "role": "frontier_planner_architect_reviewer",
        "authority": "advisory",
        "size": None,
        "context_length": 65536,
        "n_params": 9197093888,
        "weight_class": "medium",
        "machine_fit_status": "preferred",
        "machine_fit_reason": "Preferred local Hermes model for this machine.",
        "action": None,
        "detail": "Registered profile is available on this machine.",
    }


def test_local_model_inventory_adds_concrete_ollama_onboarding_action(
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
                stdout="NAME              ID       SIZE      MODIFIED\n"
                "qwen3:14b         abc123   9.3 GB    1 day ago\n",
                stderr="",
            )
        return subprocess.CompletedProcess(
            args,
            0,
            stdout=(
                "  Model\n"
                "    architecture        qwen3\n"
                "    parameters          14.0B\n"
                "    context length      40960\n"
                "    quantization        Q4_K_M\n"
                "  Capabilities\n"
                "    completion\n"
            ),
            stderr="",
        )

    monkeypatch.setattr("devflow.control_room.local_agent_discovery._run_ollama", fake_run_ollama)

    result = runner.invoke(app, ["agent", "catalog", "--json"])

    assert result.exit_code == 0, result.output
    inventory = build_local_model_inventory(json.loads(result.output))
    row = next(row for row in inventory["rows"] if row["kind"] == "unregistered_ollama_model")
    assert row["model"] == "qwen3:14b"
    assert row["status"] == "needs_profile"
    assert row["action"]["label"] == "Add profile"
    assert row["action"]["command"] == (
        "devflow agent add-model --provider ollama --model qwen3:14b "
        "--authority read-only --role local_senior_worker --json"
    )


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


def _start_models_server(payload: dict[str, object]) -> tuple[ThreadingHTTPServer, threading.Thread]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path != "/v1/models":
                self.send_error(404)
                return
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread
