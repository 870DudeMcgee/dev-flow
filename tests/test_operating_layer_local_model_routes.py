from __future__ import annotations

import json
import threading
from http import HTTPStatus
from http.client import HTTPConnection
from pathlib import Path

import pytest

import devflow.control_room.operating_layer_gates_local_model_handlers as gates_local_model_handlers
from devflow.control_room.operating_layer_server import OperatingLayerHTTPServer
from tests.helpers import setup_temp_git_repo


def _serve_operating_layer(root: Path) -> tuple[OperatingLayerHTTPServer, threading.Thread, str, int]:
    server = OperatingLayerHTTPServer(("127.0.0.1", 0), root)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    return server, thread, host, port


def _post_json(host: str, port: int, path: str, payload: dict[str, object]) -> tuple[int, dict]:
    connection = HTTPConnection(host, port, timeout=5)
    connection.request(
        "POST",
        path,
        body=json.dumps(payload),
        headers={"Content-Type": "application/json"},
    )
    response = connection.getresponse()
    body = response.read().decode("utf-8")
    parsed = json.loads(body) if body else {}
    return response.status, parsed


def test_local_model_ensure_managed_qwen_profile_calls_lifecycle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    calls: list[dict[str, object]] = []

    def fake_ensure(root: Path, **kwargs: object) -> dict[str, object]:
        calls.append({"root": root, **kwargs})
        return {
            "action": "ensure",
            "status": "already_running",
            "will_manage_local_server": True,
            "profile": "qwen36-27b-q5-mtp",
            "provider": kwargs["provider"],
            "model": kwargs["model"],
            "base_url": kwargs["base_url"],
            "pid": 12345,
        }

    monkeypatch.setattr(gates_local_model_handlers, "ensure_local_model_server_for_profile", fake_ensure)
    server, thread, host, port = _serve_operating_layer(tmp_path)
    try:
        status, payload = _post_json(host, port, "/api/local-model/ensure", {"profile_id": "hermes-qwen36-27b-q5-mtp"})
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert status == HTTPStatus.OK
    assert calls == [
        {
            "root": tmp_path.resolve(),
            "provider": "qwen36-27b-q5-mtp",
            "model": "qwen36-27b-q5-mtp",
            "base_url": "http://127.0.0.1:8083/v1",
        }
    ]
    assert payload["status"] == "already_running"
    assert payload["will_manage_local_server"] is True
    assert payload["management"] == "devflow_managed_local_server"
    assert payload["lifecycle"]["pid"] == 12345


def test_local_model_ensure_canonical_hermes_local_profile_calls_lifecycle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", tmp_path.as_posix())
    hermes_profile = tmp_path / ".hermes" / "profiles" / "hermes-qwen36-27b-q5-mtp"
    hermes_profile.mkdir(parents=True)
    (hermes_profile / "config.yaml").write_text(
        """model:
  default: qwen36-27b-q5-mtp
  provider: qwen36-27b-q5-mtp
  base_url: http://127.0.0.1:8083/v1
""",
        encoding="utf-8",
    )
    calls: list[dict[str, object]] = []

    def fake_ensure(root: Path, **kwargs: object) -> dict[str, object]:
        calls.append({"root": root, **kwargs})
        return {
            "action": "ensure",
            "status": "already_running",
            "will_manage_local_server": True,
            "profile": "qwen36-27b-q5-mtp",
            "provider": kwargs["provider"],
            "model": kwargs["model"],
            "base_url": kwargs["base_url"],
            "pid": 12345,
        }

    monkeypatch.setattr(gates_local_model_handlers, "ensure_local_model_server_for_profile", fake_ensure)
    server, thread, host, port = _serve_operating_layer(tmp_path)
    try:
        status, payload = _post_json(host, port, "/api/local-model/ensure", {"profile_id": "hermes-qwen36-27b-q5-mtp"})
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert status == HTTPStatus.OK
    assert calls == [
        {
            "root": tmp_path.resolve(),
            "provider": "qwen36-27b-q5-mtp",
            "model": "qwen36-27b-q5-mtp",
            "base_url": "http://127.0.0.1:8083/v1",
        }
    ]
    assert payload["requested_profile_id"] == "hermes-qwen36-27b-q5-mtp"
    assert payload["hermes_profile"] == "hermes-qwen36-27b-q5-mtp"
    assert payload["status"] == "already_running"


def test_local_model_ensure_lifecycle_failure_keeps_action_error_shape(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from devflow.control_room.local_model_server import LocalModelServerError

    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    def fake_ensure(root: Path, **kwargs: object) -> dict[str, object]:
        raise LocalModelServerError("server boot failed")

    monkeypatch.setattr(gates_local_model_handlers, "ensure_local_model_server_for_profile", fake_ensure)
    server, thread, host, port = _serve_operating_layer(tmp_path)
    try:
        status, payload = _post_json(host, port, "/api/local-model/ensure", {"profile_id": "hermes-qwen36-27b-q5-mtp"})
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert status == HTTPStatus.CONFLICT
    assert payload["error"] == "server boot failed"
    assert payload["error_code"] == "local_model_server_error"
    assert payload["error_type"] == "LocalModelServerError"
    assert payload["retriable"] is True


def test_local_model_ensure_rejects_retired_hermes_alias(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        gates_local_model_handlers,
        "ensure_local_model_server_for_profile",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("retired alias should not boot a local server")),
    )
    server, thread, host, port = _serve_operating_layer(tmp_path)
    try:
        for profile_id in ("hermes-profile-dflocalfast", "qwen-worker"):
            status, payload = _post_json(host, port, "/api/local-model/ensure", {"profile_id": profile_id})
            assert status == HTTPStatus.NOT_FOUND
            assert f"Unknown profile_id '{profile_id}'" in payload["error"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_local_model_ensure_remote_profile_skips_server_boot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        gates_local_model_handlers,
        "ensure_local_model_server_for_profile",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("remote profile should not boot a local server")),
    )
    server, thread, host, port = _serve_operating_layer(tmp_path)
    try:
        status, payload = _post_json(host, port, "/api/local-model/ensure", {"profile_id": "hermes-qwen37plus"})
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert status == HTTPStatus.OK
    assert payload["status"] == "skipped"
    assert payload["will_manage_local_server"] is False
    assert payload["management"] == "provider_managed_remote"
    assert payload["provider"] == "openrouter"


def test_local_model_ensure_ollama_profile_reports_unmanaged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        gates_local_model_handlers,
        "ensure_local_model_server_for_profile",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("ollama profile should not boot a managed server")),
    )
    server, thread, host, port = _serve_operating_layer(tmp_path)
    try:
        status, payload = _post_json(host, port, "/api/local-model/ensure", {"profile_id": "local-gemma4-qat"})
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert status == HTTPStatus.OK
    assert payload["status"] == "unmanaged"
    assert payload["will_manage_local_server"] is False
    assert payload["management"] == "managed_by_ollama"
    assert payload["provider"] == "ollama"
    assert payload["model"] == "gemma4:12b-it-qat"


def test_local_model_ensure_unknown_profile_errors(tmp_path: Path) -> None:
    setup_temp_git_repo(tmp_path)
    server, thread, host, port = _serve_operating_layer(tmp_path)
    try:
        status, payload = _post_json(host, port, "/api/local-model/ensure", {"profile_id": "missing-profile"})
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert status == HTTPStatus.NOT_FOUND
    assert "Unknown profile_id 'missing-profile'" in payload["error"]
    assert payload["error_code"] == "missing_profile"
    assert payload["error_type"] == "KeyError"
    assert payload["retriable"] is False
