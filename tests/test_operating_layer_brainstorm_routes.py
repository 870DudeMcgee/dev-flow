from __future__ import annotations

import json
import threading
from http import HTTPStatus
from http.client import HTTPConnection
from pathlib import Path

import pytest

from devflow.control_room.idea_foundry import capture_idea
from devflow.control_room.operating_layer_server import OperatingLayerHTTPServer
from tests.helpers import setup_temp_git_repo


def _serve_operating_layer(root: Path) -> tuple[OperatingLayerHTTPServer, threading.Thread, str, int]:
    server = OperatingLayerHTTPServer(("127.0.0.1", 0), root)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    return server, thread, host, port


def test_operating_layer_start_brainstorm_from_idea_endpoint(tmp_path: Path) -> None:
    setup_temp_git_repo(tmp_path)
    idea = capture_idea(tmp_path, "Seed this into brainstorm.", title="Seeded idea")
    server, thread, host, port = _serve_operating_layer(tmp_path)
    try:
        connection = HTTPConnection(host, port, timeout=5)
        connection.request(
            "POST",
            "/api/brainstorm/start-from-idea",
            body=json.dumps({"idea_id": idea["id"]}),
            headers={"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        payload = json.loads(response.read().decode("utf-8"))

        assert response.status == HTTPStatus.OK
        assert payload["source_idea_id"] == idea["id"]
        assert payload["session_id"].startswith("brainstorm-")
        transcript = tmp_path / ".devflow" / "brainstorms" / payload["session_id"] / "transcript.jsonl"
        records = [json.loads(line) for line in transcript.read_text(encoding="utf-8").splitlines()]
        assert records[0]["kind"] == "brainstorm_start"
        assert records[0]["metadata"]["source_idea_id"] == idea["id"]
        assert records[0]["content"] == "Seed this into brainstorm."
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_brainstorm_message_failure_still_exposes_same_session_pipeline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup_temp_git_repo(tmp_path)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    import devflow.control_room.env_loader as env_loader_mod

    monkeypatch.setattr(env_loader_mod, "_HERMES_ENV_PATH", tmp_path / "missing.env")
    server, thread, host, port = _serve_operating_layer(tmp_path)
    session_id = "browser-contract"
    try:
        connection = HTTPConnection(host, port, timeout=5)
        connection.request(
            "POST",
            "/api/brainstorm/message",
            body=json.dumps({"session_id": session_id, "message": "Make a browser-proof pipeline."}),
            headers={"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        payload = json.loads(response.read().decode("utf-8"))

        assert response.status == HTTPStatus.OK
        assert payload["status"] == "failed"
        assert payload["session_id"] == session_id
        assert "OPENROUTER_API_KEY" in payload["error"]

        connection = HTTPConnection(host, port, timeout=5)
        connection.request("GET", f"/api/brainstorm/transcript?session_id={session_id}")
        transcript_response = connection.getresponse()
        transcript = json.loads(transcript_response.read().decode("utf-8"))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert transcript_response.status == HTTPStatus.OK
    assert transcript["session_id"] == session_id
    assert transcript["pipeline"]["session_id"] == session_id
    assert transcript["pipeline"]["has_transcript"] is True
    stages = {stage["id"]: stage for stage in transcript["pipeline"]["stages"]}
    assert stages["brainstorm"]["status"] == "complete"
    assert stages["spec"]["status"] == "pending"
    assert transcript["pipeline"]["next_step_label"] == "Escalate to spec"


def test_operating_layer_server_exposes_brainstorm_message_and_escalation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    import devflow.control_room.env_loader as env_loader_mod

    monkeypatch.setattr(env_loader_mod, "_HERMES_ENV_PATH", tmp_path / "nonexistent.env")
    server, thread, host, port = _serve_operating_layer(tmp_path)
    try:
        connection = HTTPConnection(host, port, timeout=5)
        connection.request(
            "POST",
            "/api/brainstorm/message",
            body=json.dumps({"session_id": "browser-session", "message": "Make the UI a real chat."}),
            headers={"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
        assert response.status == 200
        assert payload["status"] == "failed"
        assert "OPENROUTER_API_KEY" in payload["error"]
        assert (tmp_path / payload["transcript_path"]).exists()

        connection.request(
            "POST",
            "/api/brainstorm/escalate",
            body=json.dumps(
                {
                    "session_id": "browser-session",
                    "stage": "implementation",
                    "title": "Build brainstorm workbench",
                    "definition_of_done": "Launchpad shows the created task and start composer.",
                }
            ),
            headers={"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
        assert response.status == 200
        assert payload["status"] == "ready"
        assert payload["action"]["command"] == (
            "devflow task create --definition-of-done "
            "'Launchpad shows the created task and start composer.' 'Build brainstorm workbench'"
        )
        assert payload["action"]["safety_class"] == "approval_required_task_state"
        assert payload["pipeline_detail"]["task_action"] == payload["action"]
        assert payload["pipeline_detail"]["task_action"]["command"] == payload["action"]["command"]
        assert payload["pipeline_detail"]["implementation_context"]["target_path_template"] == (
            ".devflow/workspaces/{task_id}/implementation-context.md"
        )

        connection.request("GET", "/api/brainstorm/transcript?session_id=browser-session")
        response = connection.getresponse()
        transcript_payload = json.loads(response.read().decode("utf-8"))
        assert response.status == 200
        assert transcript_payload["implementation"].startswith("# Implementation Task")
        assert transcript_payload["pipeline"]["has_implementation"] is True
        assert transcript_payload["pipeline"]["task_action"] == payload["pipeline_detail"]["task_action"]
        assert transcript_payload["pipeline"]["task_action"]["command"] == payload["action"]["command"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
