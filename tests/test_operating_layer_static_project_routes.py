from __future__ import annotations

import json
import threading
from http import HTTPStatus
from http.client import HTTPConnection
from pathlib import Path

from typer.testing import CliRunner

from devflow.cli import app
from devflow.control_room.operating_layer_assets import INDEX_HTML
from devflow.control_room.operating_layer_server import OperatingLayerHTTPServer
from devflow.control_room.persistence import utc_now
from devflow.control_room.project_models import ProjectRecord
from devflow.control_room.project_registry import register_project

runner = CliRunner()


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


def _head_raw(host: str, port: int, path: str) -> tuple[int, bytes, dict]:
    connection = HTTPConnection(host, port, timeout=5)
    connection.request("HEAD", path)
    response = connection.getresponse()
    body = response.read()
    headers = {k.lower(): v for k, v in response.getheaders()}
    return response.status, body, headers


def _write_graphify_fixture(root: Path) -> None:
    graphify_dir = root / "graphify-out"
    graphify_dir.mkdir(parents=True, exist_ok=True)
    (graphify_dir / "GRAPH_REPORT.md").write_text(
        "# Graph Report - X  (2026-06-28)\n## Summary\n- 10 nodes\n## Graph Freshness\n- Built from commit: `9fb51f5b`\n",
        encoding="utf-8",
    )
    (graphify_dir / "graph.json").write_text('{"ok": true}', encoding="utf-8")
    (graphify_dir / "GRAPH_TREE.html").write_text("<html>tree</html>", encoding="utf-8")
    (graphify_dir / "Local-AI-Dev-Team-callflow.html").write_text("<html>callflow</html>", encoding="utf-8")
    (graphify_dir / "dev-flow-callflow.html").write_text("<html>callflow</html>", encoding="utf-8")


def test_architecture_artifact_route_serves_projected_artifacts(tmp_path: Path) -> None:
    _write_graphify_fixture(tmp_path)
    server, thread, host, port = _serve_operating_layer(tmp_path)
    try:
        status, body, headers = _get_raw(host, port, "/architecture/artifact?id=graph-report")
        assert status == 200
        assert headers["content-type"] == "text/markdown"
        assert headers.get("x-content-type-options") == "nosniff"
        assert headers.get("cache-control") == "no-store"
        assert b"Graph Report" in body

        status, body, headers = _get_raw(host, port, "/architecture/artifact?id=graph-json")
        assert status == 200
        assert headers["content-type"] == "application/json"

        status, body, headers = _get_raw(host, port, "/architecture/artifact?id=callflow-dev-flow-callflow")
        assert status == 200
        assert headers["content-type"] == "text/html"
        assert b"callflow" in body
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_architecture_artifact_route_rejects_unsafe_requests(tmp_path: Path) -> None:
    _write_graphify_fixture(tmp_path)
    server, thread, host, port = _serve_operating_layer(tmp_path)
    try:
        for path, expected in [
            ("/architecture/artifact?id=unknown-id", 404),
            ("/architecture/artifact?id=../etc/passwd", 404),
            ("/architecture/artifact?id=/etc/passwd", 404),
            ("/architecture/artifact", 400),
            ("/architecture/artifact?path=graphify-out/GRAPH_REPORT.md", 400),
        ]:
            status, _body, _headers = _get_raw(host, port, path)
            assert status == expected, (path, status)
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_operating_layer_server_serves_head_for_static_assets(tmp_path: Path) -> None:
    server, thread, host, port = _serve_operating_layer(tmp_path)
    try:
        for path, content_type in (
            ("/", "text/html; charset=utf-8"),
            ("/app.css", "text/css; charset=utf-8"),
            ("/app.js", "application/javascript; charset=utf-8"),
        ):
            status, body, headers = _head_raw(host, port, path)
            assert status == HTTPStatus.OK
            assert body == b""
            assert headers["content-type"] == content_type
            assert int(headers["content-length"]) > 0
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_operating_layer_server_serves_app_and_snapshot(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    assert runner.invoke(app, ["task", "create", "ui shell task"]).exit_code == 0

    server, thread, host, port = _serve_operating_layer(tmp_path)
    try:
        connection = HTTPConnection(host, port, timeout=5)
        connection.request("GET", "/")
        response = connection.getresponse()
        body = response.read().decode("utf-8")
        assert response.status == 200
        assert "Dev-Flow Operating Layer" in body
        assert "Brainstorm" in body
        assert "DeepSeek V4 Flash Free" in body
        assert "pipeline-stages-container" in body
        assert "Unified Chat Workbench" in body
        assert "idea-capture-form" in body
        assert "idea-greenhouse-lanes" in body
        assert "Local evidence only" in body
        assert "Worker lanes" in body
        assert "Review queue" in body
        assert "Evidence stream" in body
        assert "Task Control" in body
        assert "Product / Review" not in body
        assert "Next Task" in body
        assert "Definition of Done" in body
        assert "focus-overlay" in body
        assert "focus-panel" in body
        assert "Next Safe Action" in body
        assert "Work Feed" in body
        assert "topbar-health" in body
        assert "System Health" not in body
        assert "repo-name" in body
        assert "branch-name" in body
        assert "Control Room" in body
        assert "/api/snapshot" in body or "/app.js" in body

        connection.request("GET", "/api/snapshot")
        response = connection.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
        assert response.status == 200
        assert payload["tasks"][0]["id"] == "task-0001"

        connection.request("GET", "/app.css")
        response = connection.getresponse()
        css = response.read().decode("utf-8")
        assert response.status == 200
        assert "brainstorm-section" in INDEX_HTML
        assert "pipeline-section" in INDEX_HTML
        assert "pipeline-spine" in INDEX_HTML
        assert "product-review-section" in INDEX_HTML
        assert "task-control-grid" in css
        assert "bottom-dock" not in css
        assert ".idea-greenhouse-lanes" in css
        assert ".idea-card" in css
        assert "worker-lanes-list" in css
        assert "worker-card" in css
        assert "review-queue-list" in css
        assert "focus-overlay" in css
        assert "focus-panel" in css
        assert "focus-overlay" in css
        assert "topbar-health" in css
        assert "health-section" not in css
        assert "next-task-meta" in css
        assert "definition-editor" in css
        assert "pipeline-stages" in css
        assert "agent-row" in css
        assert "feed-item" in css
        assert "evidence-item" in css
        assert "topbar" in css

        connection.request("GET", "/app.js")
        response = connection.getresponse()
        js = response.read().decode("utf-8")
        assert response.status == 200
        assert "sendBrainstormMessage" in js
        assert "escalateBrainstormStage" in js
        assert "pipeline_detail" in js
        assert "taskActionFromPipelinePayload" in js
        assert "Legacy Brainstorm payload fallback" in js
        assert "createTaskFromAcceptedImplementation" in js
        assert "Implementation artifact is ready. Use Create Task after builder-judge acceptance." in js
        assert "implContext?.text && implContext.text.trim()" not in js
        assert "renderBrainstormTranscript" in js
        assert "renderWorkerLanes" in js
        assert "renderIdeaGreenhouse" in js
        assert "idea-greenhouse-lanes" in js
        assert "renderReviewQueue" in js
        assert "renderEvidenceStream" in js
        assert "renderMissionFeed" in js
        assert "renderPipeline" in js
        assert "renderOrchestrator" in js
        assert "selectTaskInLaunchpad" in js
        assert "data-task-run-shell" in js
        assert "data-task-verify" in js
        assert "definition_of_done" in js
        assert "openFocus" in js
        assert "closeFocus" in js
        assert "loadSnapshot" in js
        assert "executeAction" in js
        assert "rememberApprovedActionResult" not in js
        assert "refreshSnapshotAfterApprovedAction" not in js
        assert "setActiveNav" in js
        assert "aria-label" in INDEX_HTML
        assert "keydown" in js
        assert "Escape" in js
        assert "shortTime" in js
        assert "esc" in js
        assert "ago" in js
        assert "render" in js
        assert "loadSnapshot" in js
        assert "executeAction" in js
        assert "renderMissionFeed" in js
        assert "renderWorkerLanes" in js
        assert "renderPipeline" in js
        assert "shortTime" in js
        assert "esc" in js
        assert "ago" in js
        assert "snapshot" in js
        assert "setupRepoSelector" in js
        assert "setupBrainstormForm" in js
        assert "openFocus" in js
        assert "closeFocus" in js
        assert "sendBrainstormMessage" in js
        assert "escalateBrainstormStage" in js
        assert "loadSnapshot" in js
        assert "render" in js
        assert "renderOrchestrator" in js
        assert "renderMissionFeed" in js
        assert "renderWorkerLanes" in js
        assert "renderPipeline" in js
        assert "renderReviewQueue" in js
        assert "renderEvidenceStream" in js
        assert "/api/snapshot?project=" in js
        assert "/api/brainstorm/message" in js
        assert "/api/brainstorm/escalate" in js
        assert "refresh-button" in INDEX_HTML
        assert "/api/actions/run" in js
        assert "executeAction" in js
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_operating_layer_server_serves_registered_project_snapshot(
    tmp_path: Path,
    monkeypatch,
) -> None:
    home = tmp_path / "home"
    monkeypatch.setenv("DEVFLOW_HOME", home.as_posix())

    host_root = tmp_path / "host"
    host_root.mkdir()
    project_root = tmp_path / "projects" / "demo"
    project_root.mkdir(parents=True)

    monkeypatch.chdir(project_root)
    assert runner.invoke(app, ["task", "create", "project drilldown task"]).exit_code == 0
    register_project(
        ProjectRecord(
            project_id="demo",
            name="Demo",
            path=project_root.as_posix(),
            last_seen_at=utc_now(),
        )
    )

    server = OperatingLayerHTTPServer(("127.0.0.1", 0), host_root)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        connection = HTTPConnection(host, port, timeout=5)
        connection.request("GET", "/api/snapshot?project=demo")
        response = connection.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
        assert response.status == 200
        assert payload["project"]["root"] == project_root.as_posix()
        assert payload["tasks"][0]["title"] == "project drilldown task"

        connection.request("GET", "/api/snapshot?project=missing")
        response = connection.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
        assert response.status == 400
        assert "Project not found" in payload["error"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
