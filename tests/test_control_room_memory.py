from __future__ import annotations

import http.client
import json
import threading
from pathlib import Path

from devflow.control_room import system_memory
from devflow.control_room.server import StatusServer


VM_STAT_SAMPLE = """Mach Virtual Memory Statistics: (page size of 16384 bytes)
Pages free:                               100000.
Pages active:                            1800000.
Pages inactive:                           500000.
Pages speculative:                         50000.
Pages wired down:                         300000.
Pages purgeable:                           25000.
Pages occupied by compressor:             100000.
"""


class _Completed:
    def __init__(self, stdout: str) -> None:
        self.stdout = stdout


def test_memory_pressure_snapshot_uses_vm_stat_headroom(monkeypatch) -> None:
    monkeypatch.setattr(system_memory.platform, "system", lambda: "Darwin")

    def fake_run(command, check, capture_output, text, timeout):  # noqa: ANN001
        assert check is True
        assert capture_output is True
        assert text is True
        if command == ["vm_stat"]:
            return _Completed(VM_STAT_SAMPLE)
        if command == ["sysctl", "-n", "hw.memsize"]:
            return _Completed(str(64 * 1024**3))
        raise AssertionError(command)

    monkeypatch.setattr(system_memory.subprocess, "run", fake_run)

    payload = system_memory.memory_pressure_snapshot()

    assert payload["available"] is True
    assert payload["status"] in {"ok", "warn", "critical"}
    assert payload["available_gib"] > 0
    assert 0 <= payload["pressure"] <= 1
    assert payload["total_gib"] == 64.0


def test_memory_pressure_endpoint_returns_probe_payload(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "devflow.control_room.server.memory_pressure_snapshot",
        lambda: {"available": True, "status": "ok", "pressure": 0.42, "available_gib": 24.0},
    )
    server = StatusServer(("127.0.0.1", 0), tmp_path)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        conn.request("GET", "/api/memory")
        resp = conn.getresponse()
        body = resp.read().decode("utf-8")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert resp.status == 200
    assert json.loads(body) == {"available": True, "status": "ok", "pressure": 0.42, "available_gib": 24.0}


def test_run_server_reports_the_bound_ephemeral_port(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(StatusServer, "serve_forever", lambda self: None)

    from devflow.control_room.server import run_server

    run_server(tmp_path, port=0)

    assert ":0\n" not in capsys.readouterr().out
