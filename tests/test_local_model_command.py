from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from devflow.control_room.local_model_command import local_model_app


QWEN_PS_OUTPUT = """
24842 1 S 123456 /opt/homebrew/bin/llama-server --hf-repo unsloth/Qwen3.5-9B-MTP-GGUF:UD-Q4_K_XL --no-mmproj --alias qwen35-9b-mtp --host 127.0.0.1 --port 8080 --ctx-size 65536 --no-webui
"""


def test_local_model_command_status_json_reports_running_process(monkeypatch: pytest.MonkeyPatch) -> None:
    from devflow.control_room import local_model_server

    monkeypatch.setattr(
        local_model_server,
        "list_local_model_server_processes",
        lambda include_ollama=False: local_model_server.parse_local_model_server_processes(QWEN_PS_OUTPUT),
    )

    result = CliRunner().invoke(local_model_app, ["status", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["action"] == "status"
    assert payload["running_count"] == 1
    assert payload["processes"][0]["pid"] == 24842
    assert payload["processes"][0]["model"] == "qwen35-9b-mtp"


def test_local_model_command_stop_dry_run_accepts_no_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from devflow.control_room import local_model_server

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        local_model_server,
        "list_local_model_server_processes",
        lambda include_ollama=False: local_model_server.parse_local_model_server_processes(QWEN_PS_OUTPUT),
    )

    result = CliRunner().invoke(local_model_app, ["stop", "--dry-run", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "would_stop"
    assert payload["processes"][0]["pid"] == 24842
