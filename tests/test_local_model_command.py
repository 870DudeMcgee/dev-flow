from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from devflow.control_room.local_model_command import local_model_app


QWEN36_PS_OUTPUT = """
24842 1 S 123456 /opt/homebrew/bin/llama-server -m /Users/test/.hermes/models/gguf/qwen3.6-27b-mtp-q5/Qwen3.6-27B-Q5_K_M.gguf --alias qwen36-27b-q5-mtp --host 127.0.0.1 --port 8083 --ctx-size 65536 --no-webui
"""


def test_local_model_command_status_json_reports_running_process(monkeypatch: pytest.MonkeyPatch) -> None:
    from devflow.control_room import local_model_server

    monkeypatch.setattr(
        local_model_server,
        "list_local_model_server_processes",
        lambda include_ollama=False: local_model_server.parse_local_model_server_processes(QWEN36_PS_OUTPUT),
    )

    result = CliRunner().invoke(local_model_app, ["status", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["action"] == "status"
    assert payload["running_count"] == 1
    assert payload["processes"][0]["pid"] == 24842
    assert payload["processes"][0]["model"] == "qwen36-27b-q5-mtp"


def test_local_model_command_stop_dry_run_accepts_no_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from devflow.control_room import local_model_server

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        local_model_server,
        "list_local_model_server_processes",
        lambda include_ollama=False: local_model_server.parse_local_model_server_processes(QWEN36_PS_OUTPUT),
    )

    result = CliRunner().invoke(local_model_app, ["stop", "--dry-run", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "would_stop"
    assert payload["processes"][0]["pid"] == 24842


def test_local_model_command_start_requires_explicit_server() -> None:
    result = CliRunner().invoke(local_model_app, ["start", "--dry-run", "--json"])

    assert result.exit_code != 0
    assert "Missing argument" in result.output


def test_local_model_command_start_accepts_managed_server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from devflow.control_room import local_model_server

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(local_model_server, "list_local_model_server_processes", lambda include_ollama=False: [])

    result = CliRunner().invoke(local_model_app, ["start", "qwen36-27b-q5-mtp", "--dry-run", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["server"] == "qwen36-27b-q5-mtp"
    assert payload["profile"] == "hermes-qwen36-27b-q5-mtp"


def test_local_model_command_restart_accepts_managed_server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from devflow.control_room import local_model_server

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(local_model_server, "list_local_model_server_processes", lambda include_ollama=False: [])

    result = CliRunner().invoke(local_model_app, ["restart", "ornith-9b", "--dry-run", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["server"] == "ornith-9b"
    assert payload["profile"] == "hermes-ornith-9b"
    assert payload["replace"] is True


def test_local_model_command_inventory_json_reports_profile_server_model_and_file_exists(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from devflow.control_room import local_model_server

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", tmp_path.as_posix())
    model_file = tmp_path / ".hermes" / "models" / "gguf" / "ornith-1.0-35b-q4" / "ornith-1.0-35b-Q4_K_M.gguf"
    model_file.parent.mkdir(parents=True)
    model_file.write_text("fake", encoding="utf-8")
    monkeypatch.setattr(
        local_model_server,
        "list_local_model_server_processes",
        lambda include_ollama=False: local_model_server.parse_local_model_server_processes(QWEN36_PS_OUTPUT),
    )

    result = CliRunner().invoke(local_model_app, ["inventory", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    rows = {row["server"]: row for row in payload["profiles"]}
    rows_by_profile = {row["profile"]: row for row in payload["profiles"]}
    assert payload["action"] == "inventory"
    assert rows["qwen36-27b-q5-mtp"]["profile"] == "hermes-qwen36-27b-q5-mtp"
    assert rows["qwen36-27b-q5-mtp"]["model"] == "qwen36-27b-q5-mtp"
    assert rows["qwen36-27b-q5-mtp"]["running"] is True
    assert rows["ornith-35b"]["profile"] == "hermes-ornith-35b"
    assert rows["ornith-35b"]["model"] == "ornith-35b"
    assert rows["ornith-35b"]["file_exists"] is True
    assert rows_by_profile["hermes-qwen32-latest"]["server"] is None
    assert rows_by_profile["hermes-qwen32-latest"]["model"] == "qwen32:latest"
    assert rows_by_profile["hermes-gemma12b-latest"]["server"] is None
