"""Slice 2 — Atomic BrainstormTaskBridge tests."""

from __future__ import annotations

import json
from http.client import HTTPConnection
from pathlib import Path
import re
import threading
import time

import pytest

from devflow.control_room.brainstorm_task_bridge import create_task_from_brainstorm
from devflow.control_room.operating_layer_script import APP_JS
from devflow.control_room.operating_layer_server import OperatingLayerHTTPServer
from devflow.control_room.persistence import get_task
from tests.helpers import setup_temp_git_repo


def _serve_operating_layer(root: Path) -> tuple[OperatingLayerHTTPServer, threading.Thread, str, int]:
    server = OperatingLayerHTTPServer(("127.0.0.1", 0), root)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    # wait for the server socket to be bound
    time.sleep(0.15)
    host, port = server.server_address
    return server, thread, host, port


class _TestHttpClient:
    """Simple helper for POST requests against a running server."""

    def __init__(self, host: str, port: int, timeout: float = 5) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout

    def post(self, path: str, data: dict) -> tuple[int, dict]:
        conn = HTTPConnection(self.host, self.port, timeout=self.timeout)
        body = json.dumps(data)
        conn.request("POST", path, body=body, headers={"Content-Type": "application/json"})
        response = conn.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
        status = response.status
        conn.close()
        return status, payload


def _make_brainstorm_implementation(tmp_path: Path, session_id: str, title: str) -> None:
    """Manually build a brainstorm session with an implementation.md artifact."""
    import json as _json

    # Create transcript
    session_dir = tmp_path / ".devflow" / "brainstorms" / session_id
    session_dir.mkdir(parents=True)
    transcript_lines = [
        _json.dumps({"role": "user", "kind": "message", "content": f"Idea: {title}", "created_at": "2026-01-01T00:00:00Z"}),
        _json.dumps({"role": "assistant", "kind": "message", "content": "Sounds good. Let's implement it.", "created_at": "2026-01-01T00:01:00Z"}),
    ]
    (session_dir / "transcript.jsonl").write_text("\n".join(transcript_lines) + "\n", encoding="utf-8")

    # Create implementation.md
    impl_path = session_dir / "implementation.md"
    impl_content = f"# Implementation for {title}\n\nSteps:\n1. Do thing A\n2. Do thing B\n"
    impl_path.write_text(impl_content, encoding="utf-8")
    return session_dir


def test_operating_layer_js_uses_active_brainstorm_session_for_atomic_bridge() -> None:
    """Regression: the browser bridge must use the active session variable."""
    assert re.search(r"createTaskFromBrainstorm\(\s*brainstormSessionId,", APP_JS)
    assert not re.search(r"createTaskFromBrainstorm\(\s*session_id,", APP_JS)
    assert "Brainstorm task bridge did not return a task id" in APP_JS
    assert "Implementation context target:" in APP_JS
    assert "Legacy Brainstorm payload fallback" in APP_JS
    assert "if (detail.task_action) return detail.task_action;" in APP_JS
    assert APP_JS.index("if (detail.task_action) return detail.task_action;") < APP_JS.index("return payload?.action || null;")
    assert "createTaskFromAcceptedImplementation" in APP_JS
    assert "Implementation artifact is ready. Use Create Task after builder-judge acceptance." in APP_JS
    assert "implContext?.text && implContext.text.trim()" not in APP_JS


def test_brainstorm_create_task_bridge_writes_context_and_lineage(tmp_path: Path) -> None:
    """When called with a valid brainstorm session, the bridge creates a task
    and writes context in a single call."""
    setup_temp_git_repo(tmp_path)
    session_dir = _make_brainstorm_implementation(
        tmp_path, "sess-001", "Bridge test feature"
    )

    result = create_task_from_brainstorm(
        root=tmp_path,
        session_id="sess-001",
        stage="implementation",
        title="Bridge test feature",
    )

    assert result["status"] == "created"
    assert result["task_id"].startswith("task-")
    task = get_task(tmp_path, result["task_id"])
    assert task.title == "Bridge test feature"
    assert task.status == "created"

    # Context file exists in workspace
    context_file = tmp_path / result["context_path"]
    assert context_file.exists()
    context_text = context_file.read_text(encoding="utf-8")
    # build_implementation_context falls back to transcript when spec/plan are missing
    assert "Bridge test feature" in context_text

    # Lineage present
    assert "lineage" in result
    assert result["lineage"]["brainstorm_session_id"] == "sess-001"
    assert result["lineage"]["created_task_id"] == result["task_id"]
    assert result["post_create_action"]["command"] == (
        f"devflow task run {result['task_id']} --worker shell -- <command>"
    )
    assert result["launchpad"]["selected_task_id"] == result["task_id"]
    assert result["pipeline_detail"]["launchpad_selection"]["selected_task_id"] == result["task_id"]
    assert result["context_path"] in result["evidence_paths"]

    # Pipeline updated with created_task_ids
    pipeline_path = session_dir / "pipeline.json"
    if pipeline_path.exists():
        pipeline_data = json.loads(pipeline_path.read_text(encoding="utf-8"))
        assert result["task_id"] in pipeline_data.get("created_task_ids", [])

    # Actions returned
    actions = result.get("actions", [])
    action_labels = [a["label"] for a in actions]
    assert "Inspect" in action_labels
    assert "Verify" in action_labels


def test_brainstorm_create_task_bridge_refuses_missing_implementation_stage(tmp_path: Path) -> None:
    """Bridge must refuse if implementation.md is absent."""
    setup_temp_git_repo(tmp_path)
    session_dir = tmp_path / ".devflow" / "brainstorms" / "sess-noimpl"
    session_dir.mkdir(parents=True)
    (session_dir / "transcript.jsonl").write_text(
        json.dumps({"role": "user", "kind": "message", "content": "hi"}) + "\n", encoding="utf-8"
    )

    with pytest.raises(ValueError, match="implementation.md missing"):
        create_task_from_brainstorm(
            root=tmp_path,
            session_id="sess-noimpl",
            stage="implementation",
            title="Should fail",
        )


def test_brainstorm_create_task_bridge_refuses_non_implementation_stage(tmp_path: Path) -> None:
    """Bridge only supports stage='implementation'."""
    setup_temp_git_repo(tmp_path)

    with pytest.raises(ValueError, match="only supports stage=implementation"):
        create_task_from_brainstorm(
            root=tmp_path,
            session_id="sess-any",
            stage="spec",
            title="Should fail",
        )


def test_brainstorm_create_task_bridge_refuses_missing_session(tmp_path: Path) -> None:
    """Bridge must refuse if transcript.jsonl is missing."""
    session_dir = tmp_path / ".devflow" / "brainstorms" / "sess-missing"
    session_dir.mkdir(parents=True)

    with pytest.raises(ValueError, match="has no transcript"):
        create_task_from_brainstorm(
            root=tmp_path,
            session_id="sess-missing",
            stage="implementation",
            title="Should fail",
        )


# ---------------------------------------------------------------------------
# Server-level tests — POST /api/brainstorm/create-task
# ---------------------------------------------------------------------------

def test_operating_layer_brainstorm_implementation_escalation_exposes_task_action(tmp_path: Path) -> None:
    """The bridge endpoint returns a structured packet when called. We verify both the
    standalone function output and the server HTTP path."""
    setup_temp_git_repo(tmp_path)
    _make_brainstorm_implementation(
        tmp_path, "sess-010", "Bridge escalation feature"
    )

    # First verify via function directly
    result = create_task_from_brainstorm(
        root=tmp_path,
        session_id="sess-010",
        stage="implementation",
        title="Bridge escalation feature",
    )
    assert result["status"] == "created"
    assert result["task_id"].startswith("task-")

    # Now verify via the server HTTP route on a SECOND brainstorm session
    _make_brainstorm_implementation(
        tmp_path, "sess-http-011", "Bridge HTTP feature"
    )
    server, thread, host, port = _serve_operating_layer(tmp_path)
    try:
        client = _TestHttpClient(host, port)
        status, payload = client.post(
            "/api/brainstorm/create-task",
            {
                "session_id": "sess-http-011",
                "title": "Bridge HTTP feature",
            },
        )
        assert status == 200, f"create-task returned {status}: {payload}"
        assert payload["task_id"].startswith("task-")
        assert payload["context_path"]
        assert payload["context_path"] in payload["evidence_paths"]
        assert payload["post_create_action"]["task_id"] == payload["task_id"]
        assert payload["post_create_action"]["command"] == (
            f"devflow task run {payload['task_id']} --worker shell -- <command>"
        )
        assert payload["launchpad"]["selected_task_id"] == payload["task_id"]
        assert payload["pipeline_detail"]["launchpad_selection"] == payload["launchpad"]
        assert len(payload.get("actions", [])) >= 1

        # Task exists in the persistence store
        task = get_task(tmp_path, payload["task_id"])
        assert task.title == "Bridge HTTP feature"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_operating_layer_brainstorm_create_task_refuses_missing_implementation_from_server(
    tmp_path: Path,
) -> None:
    """Server-side validation also rejects sessions without implementation.md."""
    setup_temp_git_repo(tmp_path)
    session_dir = tmp_path / ".devflow" / "brainstorms" / "sess-nofail"
    session_dir.mkdir(parents=True)
    (session_dir / "transcript.jsonl").write_text(
        json.dumps({"role": "user", "kind": "message", "content": "no implementation here"}) + "\n", encoding="utf-8"
    )

    server, thread, host, port = _serve_operating_layer(tmp_path)
    try:
        client = _TestHttpClient(host, port)
        status, payload = client.post(
            "/api/brainstorm/create-task",
            {"session_id": "sess-nofail", "title": "Should fail"},
        )
        assert status == 400, f"Expected 400, got {status}: {payload}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_brainstorm_create_task_bridge_with_definition_of_done(tmp_path: Path) -> None:
    """Bridge passes definition_of_done through to the task."""
    setup_temp_git_repo(tmp_path)
    _make_brainstorm_implementation(
        tmp_path, "sess-dod", "DOD Feature"
    )

    result = create_task_from_brainstorm(
        root=tmp_path,
        session_id="sess-dod",
        stage="implementation",
        title="DOD Feature",
        definition_of_done="All tests pass and the UI is clean.",
    )

    assert result["status"] == "created"
    task = get_task(tmp_path, result["task_id"])
    assert task.definition_of_done == "All tests pass and the UI is clean."
