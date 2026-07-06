from __future__ import annotations

import json
import threading
from http import HTTPStatus
from http.client import HTTPConnection
from pathlib import Path

import pytest

import devflow.control_room.operating_layer_browse_snapshot_repo_handlers as browse_snapshot_repo_handlers
from devflow.control_room.operating_layer_server import OperatingLayerHTTPServer


def _serve_operating_layer(root: Path) -> tuple[OperatingLayerHTTPServer, threading.Thread, str, int]:
    server = OperatingLayerHTTPServer(("127.0.0.1", 0), root)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    return server, thread, host, port


def _get_raw(host: str, port: int, path: str) -> tuple[int, bytes, dict]:
    connection = HTTPConnection(host, port, timeout=5)
    connection.request("GET", path)
    response = connection.getresponse()
    body = response.read()
    headers = {k.lower(): v for k, v in response.getheaders()}
    return response.status, body, headers


def test_operating_layer_server_browse_directory_is_bounded_with_truncation_signal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server, thread, host, port = _serve_operating_layer(tmp_path)
    monkeypatch.setattr(browse_snapshot_repo_handlers, "BROWSE_MAX_DIRECTORY_ENTRIES", 2)
    try:
        for name in (".hidden", "alpha", "beta", "gamma", "delta"):
            if name.startswith("."):
                (tmp_path / name).mkdir()
            else:
                (tmp_path / name).mkdir()
        status, body, _headers = _get_raw(host, port, "/api/browse?path=" + str(tmp_path))
        assert status == HTTPStatus.OK
        payload = json.loads(body.decode("utf-8"))
        assert payload["entries_truncated"] is True
        assert payload["entry_limit"] == 2
        assert len(payload["entries"]) == 2
        assert all(not entry["name"].startswith(".") for entry in payload["entries"])
        assert payload["current_path"] == str(tmp_path)
        assert payload["parent_path"] == str(tmp_path.parent)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_operating_layer_server_browse_file_is_bounded_with_truncation_signal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "big.txt"
    target.write_text("0123456789", encoding="utf-8")
    server, thread, host, port = _serve_operating_layer(tmp_path)
    monkeypatch.setattr(browse_snapshot_repo_handlers, "BROWSE_MAX_FILE_BYTES", 4)
    try:
        status, body, _headers = _get_raw(host, port, f"/api/browse?path={target}")
        assert status == HTTPStatus.OK
        payload = json.loads(body.decode("utf-8"))
        assert payload["is_file"] is True
        assert payload["content"] == "0123"
        assert payload["content_size"] == 10
        assert payload["returned_bytes"] == 4
        assert payload["content_limit"] == 4
        assert payload["content_truncated"] is True
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
