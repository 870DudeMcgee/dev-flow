"""Server lifecycle utilities extracted from operating_layer_server.

These functions manage operating-layer server process discovery, shutdown,
and health probing. They have zero coupling to the request handler class
and were extracted to reduce operating_layer_server.py's line count.
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
import webbrowser
from pathlib import Path
from typing import Any, Callable


def find_listening_pids(port: int) -> list[int]:
    """Return PIDs of processes listening on ``port`` (TCP). macOS/Linux via lsof.

    Returns an empty list if lsof is unavailable or nothing is listening.
    """
    try:
        result = subprocess.run(
            ["lsof", "-ti", f"tcp:{port}", "-sTCP:LISTEN"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return []
    pids: list[int] = []
    for line in result.stdout.split():
        try:
            pids.append(int(line.strip()))
        except ValueError:
            continue
    # Never report our own process as a stale listener.
    return [pid for pid in dict.fromkeys(pids) if pid != os.getpid()]


def stop_listening_processes(port: int, *, timeout_seconds: float = 5.0) -> list[int]:
    """Terminate processes listening on ``port``. Sends SIGTERM, then SIGKILL if
    a process does not exit within ``timeout_seconds``. Returns the PIDs acted on.

    This is intentionally scoped to the single TCP port, so it only ever touches a
    stale operating-layer server, never unrelated processes.
    """
    import signal
    import time

    pids = find_listening_pids(port)
    if not pids:
        return []
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if not find_listening_pids(port):
            return pids
        time.sleep(0.2)
    # Escalate to SIGKILL for anything still holding the port.
    for pid in find_listening_pids(port):
        try:
            os.kill(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    return pids


def check_server_health(host: str, port: int, *, timeout_seconds: float = 5.0) -> dict[str, Any]:
    """Probe a running operating-layer server. Unlike ``/healthz`` (a static
    'ok'), this also fetches ``/api/snapshot`` and confirms it returns parseable,
    non-empty JSON — the data path the browser UI actually depends on.

    Returns a dict with ``healthz_ok``, ``snapshot_ok``, ``snapshot_bytes``,
    ``overall_ok``, and ``detail``.
    """
    import urllib.error
    import urllib.request

    base = f"http://{host}:{port}"
    result: dict[str, Any] = {
        "healthz_ok": False,
        "snapshot_ok": False,
        "snapshot_bytes": 0,
        "overall_ok": False,
        "detail": "",
    }

    def _get(path: str) -> tuple[int, bytes]:
        req = urllib.request.Request(base + path, method="GET")
        with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
            return resp.status, resp.read()

    try:
        status, body = _get("/healthz")
        result["healthz_ok"] = status == 200 and b"ok" in body
    except (urllib.error.URLError, OSError) as exc:
        result["detail"] = f"server not reachable on {base}: {exc}"
        return result

    try:
        status, body = _get("/api/snapshot")
        result["snapshot_bytes"] = len(body)
        if status != 200:
            result["detail"] = f"/api/snapshot returned HTTP {status}"
        elif not body.strip():
            result["detail"] = "/api/snapshot returned an empty body (stale or crashed server)"
        else:
            try:
                json.loads(body)
                result["snapshot_ok"] = True
            except json.JSONDecodeError as exc:
                result["detail"] = f"/api/snapshot returned non-JSON: {exc}"
    except (urllib.error.URLError, OSError) as exc:
        result["detail"] = f"/api/snapshot request failed: {exc}"

    result["overall_ok"] = bool(result["healthz_ok"] and result["snapshot_ok"])
    if result["overall_ok"] and not result["detail"]:
        result["detail"] = f"healthz ok, snapshot ok ({result['snapshot_bytes']} bytes)"
    return result


def run_operating_layer_server(
    repo_root: Path,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    open_browser: bool = False,
    ready_callback: Callable[..., None] | None = None,
) -> None:
    """Start the operating-layer HTTP server.

    This imports OperatingLayerHTTPServer lazily to avoid a circular import:
    operating_layer_server imports this module for the re-export, and this
    function needs OperatingLayerHTTPServer at call time (not import time).
    """
    from devflow.control_room.env_loader import load_hermes_env_file
    from devflow.control_room.operating_layer_server import OperatingLayerHTTPServer

    load_hermes_env_file()
    server = OperatingLayerHTTPServer((host, port), repo_root)
    if ready_callback:
        ready_callback(server)
    url = f"http://{server.server_address[0]}:{server.server_address[1]}"
    if open_browser:
        threading.Timer(0.1, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    finally:
        server.server_close()
