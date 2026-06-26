"""Tests for operating-layer server lifecycle helpers and the restart/health CLI.

Covers find_listening_pids / stop_listening_processes / check_server_health and
the `devflow operating-layer health` + `restart` commands. No network egress:
servers bind to 127.0.0.1 on an ephemeral port.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest

from devflow.control_room.operating_layer_server import (
    check_server_health,
    find_listening_pids,
    run_operating_layer_server,
    stop_listening_processes,
)


def _init_repo(root: Path) -> None:
    from devflow.control_room.service import init_control_room

    init_control_room(root)


class _ServerHandle:
    def __init__(self) -> None:
        self.server = None
        self.thread: threading.Thread | None = None
        self.port = 0

    def start(self, root: Path) -> int:
        ready = threading.Event()

        def _ready(server: object) -> None:
            self.server = server
            self.port = getattr(server, "server_address")[1]
            ready.set()

        def _run() -> None:
            run_operating_layer_server(
                root, host="127.0.0.1", port=0, open_browser=False, ready_callback=_ready
            )

        self.thread = threading.Thread(target=_run, daemon=True)
        self.thread.start()
        assert ready.wait(timeout=10), "server did not become ready"
        # Give serve_forever a beat to start accepting.
        time.sleep(0.2)
        return self.port

    def stop(self) -> None:
        if self.server is not None:
            self.server.shutdown()
        if self.thread is not None:
            self.thread.join(timeout=5)


@pytest.fixture
def running_server(tmp_path: Path):
    _init_repo(tmp_path)
    handle = _ServerHandle()
    handle.start(tmp_path)
    try:
        yield handle
    finally:
        handle.stop()


def test_find_listening_pids_empty_for_free_port() -> None:
    # An unbound high port should have no listeners.
    assert find_listening_pids(59999) == []


def test_check_server_health_reports_ok_for_live_server(running_server) -> None:
    health = check_server_health("127.0.0.1", running_server.port)
    assert health["healthz_ok"] is True
    assert health["snapshot_ok"] is True
    assert health["snapshot_bytes"] > 0
    assert health["overall_ok"] is True
    # Snapshot must be real JSON.
    import urllib.request

    with urllib.request.urlopen(
        f"http://127.0.0.1:{running_server.port}/api/snapshot", timeout=5
    ) as resp:
        json.loads(resp.read())


def test_check_server_health_reports_fail_when_unreachable() -> None:
    health = check_server_health("127.0.0.1", 59998)
    assert health["healthz_ok"] is False
    assert health["overall_ok"] is False
    assert "not reachable" in health["detail"]


def test_stop_listening_processes_noop_when_nothing_listening() -> None:
    assert stop_listening_processes(59997) == []


def test_health_cli_succeeds_for_live_server(running_server) -> None:
    from typer.testing import CliRunner

    from devflow.cli import app

    runner = CliRunner()
    result = runner.invoke(
        app, ["operating-layer", "health", "--port", str(running_server.port)]
    )
    assert result.exit_code == 0, result.output
    assert "healthz: ok" in result.output
    assert "snapshot: ok" in result.output


def test_health_cli_fails_for_dead_server() -> None:
    from typer.testing import CliRunner

    from devflow.cli import app

    runner = CliRunner()
    result = runner.invoke(app, ["operating-layer", "health", "--port", "59996"])
    assert result.exit_code == 1
    assert "FAIL" in result.output
