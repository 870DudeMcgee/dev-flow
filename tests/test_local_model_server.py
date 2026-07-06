from __future__ import annotations

import json
import signal
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from devflow.cli import app


QWEN36_PS_OUTPUT = """
24842 1 S 123456 /opt/homebrew/bin/llama-server -m /Users/test/.hermes/models/gguf/qwen3.6-27b-mtp-q5/Qwen3.6-27B-Q5_K_M.gguf --alias qwen36-27b-q5-mtp --host 127.0.0.1 --port 8083 --ctx-size 65536 --no-webui
"""

OTHER_LLAMA_PS_OUTPUT = """
26001 1 S 654321 /opt/homebrew/bin/llama-server --hf-repo example/Other-Model-GGUF:Q4_K_M --alias other-local-model --host 127.0.0.1 --port 8080 --ctx-size 32768 --no-webui
"""

ORNITH9B_PS_OUTPUT = """
27001 1 S 789012 /opt/homebrew/bin/llama-server -m /Users/test/.hermes/models/gguf/ornith-1.0-9b-q4/ornith-1.0-9b-Q4_K_M.gguf --alias ornith-9b --host 127.0.0.1 --port 8085 --ctx-size 131072 --no-webui
"""

OLLAMA_PS_OUTPUT = """
28001 1 S 345678 /Applications/Ollama.app/Contents/Resources/ollama serve
"""


def _retired_qwen_server() -> str:
    return "legacy-qwen-mtp"


def test_list_local_model_server_processes_detects_qwen36_llama_server() -> None:
    from devflow.control_room.local_model_server import parse_local_model_server_processes

    processes = parse_local_model_server_processes(QWEN36_PS_OUTPUT)

    assert len(processes) == 1
    process = processes[0]
    assert process.pid == 24842
    assert process.kind == "llama-server"
    assert process.provider == "qwen36-27b-q5-mtp"
    assert process.model == "qwen36-27b-q5-mtp"
    assert process.port == 8083
    assert process.managed_by_default is True


def test_known_local_model_server_profiles_are_manifest_backed() -> None:
    from devflow.control_room.local_model_server import known_local_model_server_profiles

    profiles = known_local_model_server_profiles()

    assert sorted(profiles) == ["ornith-35b", "ornith-9b", "qwen36-27b-q5-mtp"]
    qwen = profiles["qwen36-27b-q5-mtp"]
    assert qwen.server_id == "qwen36-27b-q5-mtp"
    assert qwen.profile_id == "hermes-qwen36-27b-q5-mtp"
    assert qwen.provider == "qwen36-27b-q5-mtp"
    assert qwen.model == "qwen36-27b-q5-mtp"
    assert qwen.base_url == "http://127.0.0.1:8083/v1"
    assert qwen.command[:2] == ["llama-server", "-m"]
    assert qwen.command[qwen.command.index("--alias") + 1] == "qwen36-27b-q5-mtp"
    assert qwen.command[qwen.command.index("--spec-type") + 1] == "draft-mtp"

    ornith9b = profiles["ornith-9b"]
    assert ornith9b.profile_id == "hermes-ornith-9b"
    assert ornith9b.provider == "ornith-9b"
    assert ornith9b.model == "ornith-9b"
    assert ornith9b.base_url == "http://127.0.0.1:8085/v1"
    assert ornith9b.port == 8085
    assert ornith9b.command[ornith9b.command.index("--ctx-size") + 1] == "131072"
    assert ornith9b.command[ornith9b.command.index("--chat-template") + 1] == "chatml"

    ornith35b = profiles["ornith-35b"]
    assert ornith35b.profile_id == "hermes-ornith-35b"
    assert ornith35b.provider == "ornith-35b"
    assert ornith35b.model == "ornith-35b"
    assert ornith35b.base_url == "http://127.0.0.1:8084/v1"
    assert ornith35b.port == 8084
    assert ornith35b.command[ornith35b.command.index("--ctx-size") + 1] == "65536"
    assert ornith35b.command[ornith35b.command.index("--chat-template") + 1] == "chatml"


def test_resolve_local_model_server_profile_rejects_retired_aliases() -> None:
    from devflow.control_room.local_model_server import LocalModelServerError, resolve_local_model_server_profile

    for profile in ["fast_local", "dflocalfast", _retired_qwen_server(), "ornith9b", "hermes-ornith-9b"]:
        with pytest.raises(LocalModelServerError) as exc:
            resolve_local_model_server_profile(profile)
        assert f"Unknown local model server '{profile}'" in str(exc.value)
        assert "ornith-9b" in str(exc.value)
        assert "qwen36-27b-q5-mtp" in str(exc.value)


def test_list_local_model_server_processes_detects_manifest_backed_ornith_server() -> None:
    from devflow.control_room.local_model_server import parse_local_model_server_processes

    processes = parse_local_model_server_processes(ORNITH9B_PS_OUTPUT)

    assert len(processes) == 1
    process = processes[0]
    assert process.pid == 27001
    assert process.kind == "llama-server"
    assert process.provider == "ornith-9b"
    assert process.model == "ornith-9b"
    assert process.alias == "ornith-9b"
    assert process.port == 8085
    assert process.managed_by_default is True


def test_stop_local_model_servers_terminates_before_kill() -> None:
    from devflow.control_room.local_model_server import parse_local_model_server_processes, stop_local_model_servers

    killed: list[tuple[int, int]] = []
    processes = parse_local_model_server_processes(QWEN36_PS_OUTPUT)
    active_pids = {24842}

    def fake_kill(pid: int, sig: int) -> None:
        killed.append((pid, sig))
        if sig == signal.SIGTERM:
            active_pids.discard(pid)

    result = stop_local_model_servers(
        Path.cwd(),
        process_lister=lambda: processes,
        kill_func=fake_kill,
        is_process_active=lambda pid: pid in active_pids,
        sleeper=lambda seconds: None,
    )

    assert result["status"] == "stopped"
    assert result["stopped_pids"] == [24842]
    assert killed == [(24842, signal.SIGTERM)]


def test_start_local_model_server_refuses_when_existing_server_is_running(tmp_path: Path) -> None:
    from devflow.control_room.local_model_server import (
        LocalModelServerError,
        parse_local_model_server_processes,
        start_local_model_server,
    )

    processes = parse_local_model_server_processes(QWEN36_PS_OUTPUT)

    with pytest.raises(LocalModelServerError) as exc:
        start_local_model_server(
            tmp_path,
            "qwen36-27b-q5-mtp",
            process_lister=lambda: processes,
            popen_factory=lambda *args, **kwargs: None,
        )

    assert "already running" in str(exc.value)
    assert "--replace" in str(exc.value)


def test_start_local_model_server_replace_stops_then_launches(tmp_path: Path) -> None:
    from devflow.control_room.local_model_server import parse_local_model_server_processes, start_local_model_server

    processes = parse_local_model_server_processes(QWEN36_PS_OUTPUT)
    killed: list[tuple[int, int]] = []
    launched: list[list[str]] = []

    class FakePopen:
        pid = 33333

    def fake_popen(command: list[str], **kwargs: Any) -> FakePopen:
        launched.append(command)
        return FakePopen()

    result = start_local_model_server(
        tmp_path,
        "qwen36-27b-q5-mtp",
        replace=True,
        process_lister=lambda: processes,
        kill_func=lambda pid, sig: killed.append((pid, sig)),
        is_process_active=lambda pid: False,
        sleeper=lambda seconds: None,
        popen_factory=fake_popen,
        wait_for_ready=False,
    )

    assert killed == [(24842, signal.SIGTERM)]
    command = launched[0]
    assert command[:2] == ["llama-server", "-m"]
    assert command[command.index("--alias") + 1] == "qwen36-27b-q5-mtp"
    assert result["status"] == "started"
    assert result["server"] == "qwen36-27b-q5-mtp"
    assert result["profile"] == "hermes-qwen36-27b-q5-mtp"
    manifest = json.loads(
        (tmp_path / ".devflow" / "local-model-servers" / "qwen36-27b-q5-mtp" / "server.json").read_text()
    )
    assert manifest["pid"] == 33333
    assert manifest["server"] == "qwen36-27b-q5-mtp"
    assert manifest["profile"] == "hermes-qwen36-27b-q5-mtp"
    assert manifest["provider"] == "qwen36-27b-q5-mtp"
    assert manifest["model"] == "qwen36-27b-q5-mtp"


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
            "server": profile,
            "replace": kwargs.get("replace"),
            "pid": 33333,
        }

    result = ensure_local_model_server_for_profile(
        tmp_path,
        provider="qwen36-27b-q5-mtp",
        model="qwen36-27b-q5-mtp",
        base_url="http://127.0.0.1:8083/v1",
        process_lister=lambda: parse_local_model_server_processes(OTHER_LLAMA_PS_OUTPUT),
        start_profile=fake_start,
    )

    assert result["status"] == "started"
    assert result["will_manage_local_server"] is True
    assert starts[0]["profile"] == "qwen36-27b-q5-mtp"
    assert starts[0]["replace"] is True


def test_ensure_local_model_server_for_profile_keeps_matching_server(tmp_path: Path) -> None:
    from devflow.control_room.local_model_server import (
        ensure_local_model_server_for_profile,
        parse_local_model_server_processes,
    )

    result = ensure_local_model_server_for_profile(
        tmp_path,
        provider="qwen36-27b-q5-mtp",
        model="qwen36-27b-q5-mtp",
        base_url="http://127.0.0.1:8083/v1",
        process_lister=lambda: parse_local_model_server_processes(QWEN36_PS_OUTPUT),
        start_profile=lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not restart matching server")),
    )

    assert result["status"] == "already_running"
    assert result["server"] == "qwen36-27b-q5-mtp"
    assert result["profile"] == "hermes-qwen36-27b-q5-mtp"
    assert result["pid"] == 24842


def test_ensure_local_model_server_for_profile_keeps_matching_ornith_server(tmp_path: Path) -> None:
    from devflow.control_room.local_model_server import (
        ensure_local_model_server_for_profile,
        parse_local_model_server_processes,
    )

    result = ensure_local_model_server_for_profile(
        tmp_path,
        provider="ornith-9b",
        model="ornith-9b",
        base_url="http://127.0.0.1:8085/v1",
        process_lister=lambda: parse_local_model_server_processes(ORNITH9B_PS_OUTPUT),
        start_profile=lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not restart matching server")),
    )

    assert result["status"] == "already_running"
    assert result["server"] == "ornith-9b"
    assert result["profile"] == "hermes-ornith-9b"
    assert result["pid"] == 27001
    assert result["port"] == 8085


def test_local_model_server_inventory_reports_profiles_servers_and_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from devflow.control_room.local_model_server import (
        build_local_model_server_inventory,
        parse_local_model_server_processes,
    )

    monkeypatch.setenv("HOME", tmp_path.as_posix())
    model_file = tmp_path / ".hermes" / "models" / "gguf" / "ornith-1.0-35b-q4" / "ornith-1.0-35b-Q4_K_M.gguf"
    model_file.parent.mkdir(parents=True)
    model_file.write_text("fake", encoding="utf-8")

    inventory = build_local_model_server_inventory(
        process_lister=lambda: parse_local_model_server_processes(QWEN36_PS_OUTPUT)
    )
    rows = {row["server"]: row for row in inventory["profiles"]}
    rows_by_profile = {row["profile"]: row for row in inventory["profiles"]}

    assert rows["qwen36-27b-q5-mtp"]["profile"] == "hermes-qwen36-27b-q5-mtp"
    assert rows["qwen36-27b-q5-mtp"]["model"] == "qwen36-27b-q5-mtp"
    assert rows["qwen36-27b-q5-mtp"]["running"] is True
    assert rows["ornith-35b"]["profile"] == "hermes-ornith-35b"
    assert rows["ornith-35b"]["model"] == "ornith-35b"
    assert rows["ornith-35b"]["file_exists"] is True
    assert rows_by_profile["hermes-qwen32-latest"]["server"] is None
    assert rows_by_profile["hermes-qwen32-latest"]["model"] == "qwen32:latest"
    assert rows_by_profile["hermes-qwen32-latest"]["backend_kind"] == "ollama"
    assert rows_by_profile["hermes-gemma12b-latest"]["server"] is None
    assert rows_by_profile["hermes-qwopus-35b"]["server"] is None

    ollama_processes = parse_local_model_server_processes(QWEN36_PS_OUTPUT + OLLAMA_PS_OUTPUT, include_ollama=True)
    with_ollama = build_local_model_server_inventory(
        include_ollama=True,
        process_lister=lambda: ollama_processes,
    )
    ollama_profiles = {row["profile"]: row for row in with_ollama["profiles"]}
    assert ollama_profiles["hermes-qwen32-latest"]["running"] is True
    ollama = next(row for row in with_ollama["profiles"] if row["backend_kind"] == "ollama")
    assert ollama["server"] is None
    assert ollama["running"] is True


def test_ensure_local_model_server_for_profile_treats_ollama_as_unmanaged(tmp_path: Path) -> None:
    from devflow.control_room.local_model_server import ensure_local_model_server_for_profile

    result = ensure_local_model_server_for_profile(
        tmp_path,
        provider="ollama",
        model="gemma12b:latest",
        base_url="http://127.0.0.1:11434",
        process_lister=lambda: (_ for _ in ()).throw(AssertionError("should not inspect unmanaged ollama lane")),
        start_profile=lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not start unmanaged ollama lane")),
    )

    assert result == {
        "action": "ensure",
        "status": "unmanaged",
        "will_manage_local_server": False,
        "provider": "ollama",
        "model": "gemma12b:latest",
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
        lambda include_ollama=False: local_model_server.parse_local_model_server_processes(QWEN36_PS_OUTPUT),
    )

    result = CliRunner().invoke(app, ["local-model", "status", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["running_count"] == 1
    assert payload["processes"][0]["model"] == "qwen36-27b-q5-mtp"


def test_local_model_start_cli_rejects_retired_server_name() -> None:
    result = CliRunner().invoke(app, ["local-model", "start", _retired_qwen_server(), "--dry-run"])

    assert result.exit_code == 1
    assert "Unknown local model server" in result.output


def test_local_model_server_stop_cli_accepts_no_profile_dry_run(
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

    result = CliRunner().invoke(app, ["local-model", "stop", "--dry-run", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "would_stop"
    assert payload["processes"][0]["pid"] == 24842
