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

ORNITH9B_PS_OUTPUT = """
27001 1 S 789012 /opt/homebrew/bin/llama-server -m /Users/test/.hermes/models/gguf/ornith-1.0-9b-q4/ornith-1.0-9b-Q4_K_M.gguf --alias ornith-1.0-9b-q4 --host 127.0.0.1 --port 8084 --ctx-size 131072 --no-webui
"""

OLLAMA_PS_OUTPUT = """
28001 1 S 345678 /Applications/Ollama.app/Contents/Resources/ollama serve
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


def test_known_local_model_server_profiles_are_manifest_backed() -> None:
    from devflow.control_room.local_model_server import known_local_model_server_profiles

    profiles = known_local_model_server_profiles()

    qwen = profiles["hermes-qwen32"]
    assert profiles["hermes-qwen32"] is qwen
    assert qwen.base_url == "http://127.0.0.1:8080/v1"
    assert qwen.command[:3] == ["llama-server", "--hf-repo", "unsloth/Qwen3.5-9B-MTP-GGUF:UD-Q4_K_XL"]
    assert "--spec-type" in qwen.command
    assert "draft-mtp" in qwen.command

    ornith9b = profiles["hermes-ornith9b"]
    assert profiles["hermes-ornith9b"] is ornith9b
    assert ornith9b.provider == "local-ornith-9b"
    assert ornith9b.model == "ornith-1.0-9b-q4"
    assert ornith9b.base_url == "http://127.0.0.1:8084/v1"
    assert ornith9b.port == 8084
    assert ornith9b.command[:2] == ["llama-server", "-m"]
    assert ornith9b.command[2] == (Path.home() / ".hermes/models/gguf/ornith-1.0-9b-q4/ornith-1.0-9b-Q4_K_M.gguf").as_posix()
    assert ornith9b.command[ornith9b.command.index("--ctx-size") + 1] == "131072"

    ornith35b = profiles["hermes-ornith35b"]
    assert profiles["hermes-ornith35b"] is ornith35b
    assert ornith35b.provider == "local-ornith-35b"
    assert ornith35b.model == "ornith-1.0-35b-q4"
    assert ornith35b.base_url == "http://127.0.0.1:8085/v1"
    assert ornith35b.port == 8085
    assert ornith35b.command[ornith35b.command.index("--ctx-size") + 1] == "65536"

    assert "qwen35-mtp" not in profiles
    assert "local-qwen35-mtp" not in profiles
    assert "dflocalfast" not in profiles
    assert "df-local-fast" not in profiles
    assert "ornith9b" not in profiles
    assert "hermes-ornith9b" in profiles
    assert "local-ornith-9b" not in profiles
    assert "ornith35b" not in profiles
    assert "local-ornith-35b" not in profiles
    assert "hermes-ornith35b" in profiles
    assert "local-gemma4-qat" not in profiles
    assert "local-qwen25-coder-14b" not in profiles


@pytest.mark.parametrize(
    "profile",
    [
        "fast_local",
        "long_local",
        "code_local",
        "dflocalfast",
        "dflocallong",
        "dflocalcode",
        "df-local-fast",
        "local-qwen35-mtp",
        "qwen35-mtp",
        "qwen-worker",
        "ornith9b",
        "ornith35b",
    ],
)
def test_resolve_local_model_server_profile_rejects_retired_aliases(profile: str) -> None:
    from devflow.control_room.local_model_server import LocalModelServerError, resolve_local_model_server_profile

    with pytest.raises(LocalModelServerError) as exc:
        resolve_local_model_server_profile(profile)

    assert f"Unknown local model server profile '{profile}'" in str(exc.value)
    assert "hermes-qwen32" in str(exc.value)
    assert "hermes-ornith9b" in str(exc.value)
    assert "hermes-ornith35b" in str(exc.value)


def test_resolve_local_model_server_profile_rejects_unmanaged_or_unknown_profile() -> None:
    from devflow.control_room.local_model_server import LocalModelServerError, resolve_local_model_server_profile

    with pytest.raises(LocalModelServerError) as exc:
        resolve_local_model_server_profile("local-gemma4-qat")

    assert "Unknown local model server profile 'local-gemma4-qat'" in str(exc.value)
    assert "hermes-ornith9b" in str(exc.value)
    assert "hermes-ornith35b" in str(exc.value)


def test_list_local_model_server_processes_detects_manifest_backed_ornith_server() -> None:
    from devflow.control_room.local_model_server import parse_local_model_server_processes

    processes = parse_local_model_server_processes(ORNITH9B_PS_OUTPUT)

    assert len(processes) == 1
    process = processes[0]
    assert process.pid == 27001
    assert process.kind == "llama-server"
    assert process.provider == "local-ornith-9b"
    assert process.model == "ornith-1.0-9b-q4"
    assert process.alias == "ornith-1.0-9b-q4"
    assert process.port == 8084
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
            "hermes-qwen32",
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
        "hermes-qwen32",
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
    manifest = json.loads((tmp_path / ".devflow" / "local-model-servers" / "hermes-qwen32" / "server.json").read_text())
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
        "hermes-qwen32",
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
    assert starts[0]["profile"] == "hermes-qwen32"
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


def test_ensure_local_model_server_for_profile_keeps_matching_ornith_server(tmp_path: Path) -> None:
    from devflow.control_room.local_model_server import (
        ensure_local_model_server_for_profile,
        parse_local_model_server_processes,
    )

    result = ensure_local_model_server_for_profile(
        tmp_path,
        provider="local-ornith-9b",
        model="ornith-1.0-9b-q4",
        base_url="http://127.0.0.1:8084/v1",
        process_lister=lambda: parse_local_model_server_processes(ORNITH9B_PS_OUTPUT),
        start_profile=lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not restart matching server")),
    )

    assert result["status"] == "already_running"
    assert result["profile"] == "hermes-ornith9b"
    assert result["pid"] == 27001
    assert result["port"] == 8084


def test_ensure_local_model_server_for_profile_treats_ollama_as_unmanaged(tmp_path: Path) -> None:
    from devflow.control_room.local_model_server import ensure_local_model_server_for_profile

    result = ensure_local_model_server_for_profile(
        tmp_path,
        provider="ollama",
        model="gemma4:12b-it-qat",
        base_url="http://127.0.0.1:11434",
        process_lister=lambda: (_ for _ in ()).throw(AssertionError("should not inspect unmanaged ollama lane")),
        start_profile=lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not start unmanaged ollama lane")),
    )

    assert result == {
        "action": "ensure",
        "status": "unmanaged",
        "will_manage_local_server": False,
        "provider": "ollama",
        "model": "gemma4:12b-it-qat",
        "base_url": "http://127.0.0.1:11434",
        "reason": "no managed local model server profile matches this provider/model",
    }


def test_ollama_processes_are_visible_only_when_requested_and_unmanaged() -> None:
    from devflow.control_room.local_model_server import parse_local_model_server_processes

    assert parse_local_model_server_processes(OLLAMA_PS_OUTPUT) == []

    processes = parse_local_model_server_processes(OLLAMA_PS_OUTPUT, include_ollama=True)

    assert len(processes) == 1
    assert processes[0].kind == "ollama"
    assert processes[0].managed_by_default is False


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
