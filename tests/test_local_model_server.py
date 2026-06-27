from __future__ import annotations

import json
import signal
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from devflow.cli import app


QWEN_PS_OUTPUT = """
24842 1 S 123456 /opt/homebrew/bin/llama-server --hf-repo unsloth/Qwen3.5-9B-MTP-GGUF:UD-Q4_K_XL --no-mmproj --alias qwen35-9b-mtp --host 127.0.0.1 --port 8080 --ctx-size 65536 --no-webui
"""

OTHER_LLAMA_PS_OUTPUT = """
26001 1 S 654321 /opt/homebrew/bin/llama-server --hf-repo example/Other-Model-GGUF:Q4_K_M --alias other-local-model --host 127.0.0.1 --port 8080 --ctx-size 32768 --no-webui
"""


def test_list_local_model_server_processes_detects_qwen35_llama_server() -> None:
    from devflow.control_room.local_model_server import parse_local_model_server_processes

    processes = parse_local_model_server_processes(QWEN_PS_OUTPUT)

    assert len(processes) == 1
    process = processes[0]
    assert process.pid == 24842
    assert process.kind == "llama-server"
    assert process.provider == "qwen35-mtp"
    assert process.model == "qwen35-9b-mtp"
    assert process.port == 8080
    assert process.managed_by_default is True


def test_stop_local_model_servers_terminates_before_kill(monkeypatch: pytest.MonkeyPatch) -> None:
    from devflow.control_room.local_model_server import parse_local_model_server_processes, stop_local_model_servers

    killed: list[tuple[int, int]] = []
    processes = parse_local_model_server_processes(QWEN_PS_OUTPUT)
    active_pids = {24842}

    def fake_kill(pid: int, sig: int) -> None:
        killed.append((pid, sig))
        if sig == signal.SIGTERM:
            active_pids.discard(pid)

    def fake_is_active(pid: int) -> bool:
        return pid in active_pids

    result = stop_local_model_servers(
        Path.cwd(),
        process_lister=lambda: processes,
        kill_func=fake_kill,
        is_process_active=fake_is_active,
        sleeper=lambda seconds: None,
    )

    assert result["status"] == "stopped"
    assert result["stopped_pids"] == [24842]
    assert killed == [(24842, signal.SIGTERM)]


def test_stop_local_model_servers_escalates_after_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    from devflow.control_room.local_model_server import parse_local_model_server_processes, stop_local_model_servers

    killed: list[tuple[int, int]] = []
    processes = parse_local_model_server_processes(QWEN_PS_OUTPUT)

    def fake_kill(pid: int, sig: int) -> None:
        killed.append((pid, sig))

    result = stop_local_model_servers(
        Path.cwd(),
        process_lister=lambda: processes,
        kill_func=fake_kill,
        is_process_active=lambda pid: True,
        sleeper=lambda seconds: None,
        timeout_seconds=0,
    )

    assert result["status"] == "stopped"
    assert result["stopped_pids"] == [24842]
    assert killed == [(24842, signal.SIGTERM), (24842, signal.SIGKILL)]


def test_start_local_model_server_refuses_when_existing_server_is_running(tmp_path: Path) -> None:
    from devflow.control_room.local_model_server import (
        LocalModelServerError,
        parse_local_model_server_processes,
        start_local_model_server,
    )

    processes = parse_local_model_server_processes(QWEN_PS_OUTPUT)

    with pytest.raises(LocalModelServerError) as exc:
        start_local_model_server(
            tmp_path,
            "qwen35-mtp",
            process_lister=lambda: processes,
            popen_factory=lambda *args, **kwargs: None,
        )

    assert "already running" in str(exc.value)
    assert "--replace" in str(exc.value)


def test_start_local_model_server_replace_stops_then_launches(tmp_path: Path) -> None:
    from devflow.control_room.local_model_server import (
        parse_local_model_server_processes,
        start_local_model_server,
    )

    processes = parse_local_model_server_processes(QWEN_PS_OUTPUT)
    killed: list[tuple[int, int]] = []
    launched: list[list[str]] = []

    class FakePopen:
        pid = 33333

    def fake_popen(command: list[str], **kwargs: Any) -> FakePopen:
        launched.append(command)
        return FakePopen()

    result = start_local_model_server(
        tmp_path,
        "qwen35-mtp",
        replace=True,
        process_lister=lambda: processes,
        kill_func=lambda pid, sig: killed.append((pid, sig)),
        is_process_active=lambda pid: False,
        sleeper=lambda seconds: None,
        popen_factory=fake_popen,
        wait_for_ready=False,
    )

    assert killed == [(24842, signal.SIGTERM)]
    assert launched
    command = launched[0]
    assert command[:2] == ["llama-server", "--hf-repo"]
    assert "unsloth/Qwen3.5-9B-MTP-GGUF:UD-Q4_K_XL" in command
    assert "--alias" in command
    assert "qwen35-9b-mtp" in command
    assert result["status"] == "started"
    assert result["pid"] == 33333
    manifest = json.loads((tmp_path / ".devflow" / "local-model-servers" / "qwen35-mtp" / "server.json").read_text())
    assert manifest["pid"] == 33333
    assert manifest["provider"] == "qwen35-mtp"
    assert manifest["model"] == "qwen35-9b-mtp"


def test_start_local_model_server_replace_dry_run_does_not_stop_or_launch(tmp_path: Path) -> None:
    from devflow.control_room.local_model_server import (
        parse_local_model_server_processes,
        start_local_model_server,
    )

    processes = parse_local_model_server_processes(QWEN_PS_OUTPUT)
    killed: list[tuple[int, int]] = []
    launched: list[list[str]] = []

    result = start_local_model_server(
        tmp_path,
        "qwen35-mtp",
        replace=True,
        dry_run=True,
        process_lister=lambda: processes,
        kill_func=lambda pid, sig: killed.append((pid, sig)),
        popen_factory=lambda command, **kwargs: launched.append(command),
    )

    assert result["status"] == "would_start"
    assert result["stop_result"]["status"] == "would_stop"
    assert killed == []
    assert launched == []


def test_ensure_local_model_server_for_profile_replaces_mismatched_server(tmp_path: Path) -> None:
    from devflow.control_room.local_model_server import (
        ensure_local_model_server_for_profile,
        parse_local_model_server_processes,
    )

    starts: list[dict[str, Any]] = []

    def fake_start(root: Path, profile: str, **kwargs: Any) -> dict[str, Any]:
        starts.append({"root": root, "profile": profile, **kwargs})
        return {
            "action": "start",
            "status": "started",
            "profile": profile,
            "replace": kwargs.get("replace"),
            "pid": 33333,
        }

    result = ensure_local_model_server_for_profile(
        tmp_path,
        provider="qwen35-mtp",
        model="qwen35-9b-mtp",
        base_url="http://127.0.0.1:8080/v1",
        process_lister=lambda: parse_local_model_server_processes(OTHER_LLAMA_PS_OUTPUT),
        start_profile=fake_start,
    )

    assert result["status"] == "started"
    assert result["will_manage_local_server"] is True
    assert result["reason"] == "managed local model server was absent or mismatched"
    assert starts[0]["profile"] == "qwen35-mtp"
    assert starts[0]["replace"] is True


def test_ensure_local_model_server_for_profile_keeps_matching_server(tmp_path: Path) -> None:
    from devflow.control_room.local_model_server import (
        ensure_local_model_server_for_profile,
        parse_local_model_server_processes,
    )

    result = ensure_local_model_server_for_profile(
        tmp_path,
        provider="qwen35-mtp",
        model="qwen35-9b-mtp",
        base_url="http://127.0.0.1:8080/v1",
        process_lister=lambda: parse_local_model_server_processes(QWEN_PS_OUTPUT),
        start_profile=lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not restart matching server")),
    )

    assert result["status"] == "already_running"
    assert result["pid"] == 24842


def test_local_model_server_status_cli_reports_json(monkeypatch: pytest.MonkeyPatch) -> None:
    from devflow.control_room import local_model_server

    monkeypatch.setattr(
        local_model_server,
        "list_local_model_server_processes",
        lambda include_ollama=False: local_model_server.parse_local_model_server_processes(QWEN_PS_OUTPUT),
    )

    result = CliRunner().invoke(app, ["local-model", "status", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["running_count"] == 1
    assert payload["processes"][0]["model"] == "qwen35-9b-mtp"


def test_local_model_server_stop_cli_accepts_no_profile_dry_run(
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

    result = CliRunner().invoke(app, ["local-model", "stop", "--dry-run", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "would_stop"
    assert payload["processes"][0]["pid"] == 24842
