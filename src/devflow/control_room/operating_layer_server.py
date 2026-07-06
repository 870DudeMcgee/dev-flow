from __future__ import annotations

import json
import subprocess  # noqa: F401 - test patches operating_layer_server.subprocess
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable  # noqa: F401 - re-exported for type hints
from urllib.parse import parse_qs, urlsplit

from devflow.control_room.env_loader import load_hermes_env_file  # noqa: F401 - re-exported for CLI
from devflow.control_room.browser_action_executor import (
    ACTION_TIMEOUT_SECONDS,  # noqa: F401 - re-exported for route contract tests
    BrowserActionExecutionError,  # noqa: F401 - re-exported for route contract tests
    execute_browser_action,  # noqa: F401 - re-exported for route contract tests
)
from devflow.control_room.browser_action_policy import (  # noqa: F401 - re-exported for route contract tests
    resolve_browser_action_command,
)
from devflow.control_room.operating_layer_actions_agents_task_context_handlers import ActionsAgentsTaskContextHandlerMixin
from devflow.control_room.operating_layer_assets import APP_CSS, APP_JS, INDEX_HTML
from devflow.control_room.operating_layer_brainstorm_handlers import BrainstormHandlerMixin
from devflow.control_room.operating_layer_browse_snapshot_repo_handlers import BrowseSnapshotRepoHandlerMixin
from devflow.control_room.operating_layer_lifecycle import (  # noqa: F401 - re-exported for backward compat
    check_server_health,
    find_listening_pids,
    run_operating_layer_server,
    stop_listening_processes,
)
from devflow.control_room.operating_layer_builder_judge_handlers import BuilderJudgeHandlerMixin
from devflow.control_room.operating_layer_gates_local_model_handlers import GatesLocalModelHandlerMixin
from devflow.control_room.operating_layer_obsidian_handlers import ObsidianHandlerMixin
from devflow.control_room.operating_layer_refactor_handlers import RefactorHandlerMixin
from devflow.control_room.operating_layer_workbench_handlers import WorkbenchHandlerMixin
from devflow.control_room.project_registry import resolve_project_root


class OperatingLayerHTTPServer(ThreadingHTTPServer):
    def __init__(self, server_address: tuple[str, int], repo_root: Path) -> None:
        super().__init__(server_address, OperatingLayerRequestHandler)
        self.repo_root = repo_root.resolve()


class OperatingLayerRequestHandler(ActionsAgentsTaskContextHandlerMixin, BrowseSnapshotRepoHandlerMixin, RefactorHandlerMixin, GatesLocalModelHandlerMixin, WorkbenchHandlerMixin, BuilderJudgeHandlerMixin, ObsidianHandlerMixin, BrainstormHandlerMixin, BaseHTTPRequestHandler):
    server: OperatingLayerHTTPServer

    # ── Route dispatch tables ────────────────────────────────────────
    # Maps path → method name. Query-param routes are handled in do_GET
    # via _GET_QUERY_ROUTES — the handler receives the parsed query dict.
    _GET_ROUTES: dict[str, str] = {
        "/": "_send_index",
        "/index.html": "_send_index",
        "/app.css": "_send_css",
        "/app.js": "_send_js",
        "/healthz": "_send_healthz",
        "/api/snapshot": "_handle_snapshot",
        "/api/agents": "_handle_agents_list",
        "/api/obsidian/cards": "_handle_obsidian_cards",
        "/architecture/artifact": "_handle_architecture_artifact",
        "/api/browse": "_handle_browse",
        "/api/repo/set": "_handle_repo_set",
        "/api/brainstorm/sessions": "_handle_brainstorm_sessions",
        "/api/brainstorm/transcript": "_handle_brainstorm_transcript",
        "/api/builder-judge/list": "_handle_builder_judge_list",
        "/api/builder-judge/status": "_handle_builder_judge_status",
        "/api/refactor/status": "_handle_refactor_status",
    }

    _POST_ROUTES: dict[str, str] = {
        "/api/brainstorm/message": "_handle_brainstorm_message",
        "/api/brainstorm/escalate": "_handle_brainstorm_escalation",
        "/api/brainstorm/start-from-idea": "_handle_start_from_idea",
        "/api/brainstorm/create-task": "_handle_brainstorm_create_task",
        "/api/obsidian/task-preview": "_handle_obsidian_task_preview",
        "/api/obsidian/task-create": "_handle_obsidian_task_create",
        "/api/obsidian/scout-pack-preview": "_handle_obsidian_scout_pack_preview",
        "/api/obsidian/scout-pack-create": "_handle_obsidian_scout_pack_create",
        "/api/builder-judge/start": "_handle_builder_judge_start",
        "/api/builder-judge/quality-gate": "_handle_builder_judge_quality_gate",
        "/api/workbench/project": "_handle_workbench_project",
        "/api/workbench/implement": "_handle_workbench_implement",
        "/api/gates/setup": "_handle_gates_setup",
        "/api/local-model/ensure": "_handle_local_model_ensure",
        "/api/refactor/start": "_handle_refactor_start",
        "/api/task/write-context": "_handle_task_write_context",
        "/api/repo/set": "_handle_repo_set",
        "/api/actions/run": "_handle_actions_run",
    }

    # Routes whose handlers expect a parsed query dict.
    _GET_QUERY_ROUTES: frozenset[str] = frozenset({
        "/api/snapshot",
        "/architecture/artifact",
        "/api/browse",
        "/api/brainstorm/transcript",
        "/api/builder-judge/status",
        "/api/refactor/status",
    })

    def do_HEAD(self) -> None:
        path = urlsplit(self.path).path
        if path in {"/", "/index.html"}:
            self._send_text_headers(INDEX_HTML, "text/html; charset=utf-8")
            return
        if path == "/app.css":
            self._send_text_headers(APP_CSS, "text/css; charset=utf-8")
            return
        if path == "/app.js":
            self._send_text_headers(APP_JS, "application/javascript; charset=utf-8")
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_GET(self) -> None:
        request = urlsplit(self.path)
        path = request.path
        method_name = self._GET_ROUTES.get(path)
        if method_name is None:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        handler = getattr(self, method_name)
        if path in self._GET_QUERY_ROUTES:
            handler(parse_qs(request.query))
        else:
            handler()

    def do_POST(self) -> None:
        path = urlsplit(self.path).path
        method_name = self._POST_ROUTES.get(path)
        if method_name is None:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        getattr(self, method_name)()

    # ── Static asset handlers ────────────────────────────────────────
    def _send_index(self) -> None:
        self._send_text(INDEX_HTML, "text/html; charset=utf-8")

    def _send_css(self) -> None:
        self._send_text(APP_CSS, "text/css; charset=utf-8")

    def _send_js(self) -> None:
        self._send_text(APP_JS, "application/javascript; charset=utf-8")

    def _send_healthz(self) -> None:
        self._send_text(
            json.dumps({"status": "ok"}) + "\n",
            "application/json; charset=utf-8",
        )

    def log_message(self, format: str, *args: object) -> None:
        return

    def _payload_project_root(self, payload: dict[str, object]) -> Path:
        project_id = payload.get("project")
        root = self.server.repo_root
        if isinstance(project_id, str) and project_id.strip():
            root = resolve_project_root(self.server.repo_root, project_id.strip()).root
        return root

    def _query_project_root(self, query: dict[str, list[str]]) -> Path:
        project_id = (query.get("project") or [None])[0]
        root = self.server.repo_root
        if isinstance(project_id, str) and project_id.strip():
            root = resolve_project_root(self.server.repo_root, project_id.strip()).root
        return root

    def _read_json_body(self) -> dict[str, object]:
        length_header = self.headers.get("Content-Length")
        try:
            length = int(length_header or "0")
        except ValueError as exc:
            raise ValueError("invalid Content-Length") from exc
        if length <= 0:
            raise ValueError("JSON body is required")
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError("invalid JSON body") from exc
        if not isinstance(payload, dict):
            raise ValueError("JSON object body is required")
        return payload

    def _send_text(self, body: str, content_type: str) -> None:
        encoded = body.encode("utf-8")
        self._send_text_headers(body, content_type)
        try:
            self.wfile.write(encoded)
        except (BrokenPipeError, ConnectionResetError):
            return

    def _send_text_headers(self, body: str, content_type: str) -> None:
        encoded = body.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()

    def _send_artifact(self, body: bytes, content_type: str) -> None:
        # Architecture evidence artifacts are served inline-only with strict,
        # no-sniff, no-store headers. Graphify HTML is rendered inside a
        # sandboxed iframe on the client; we never expose arbitrary path reads.
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Disposition", "inline")
        self.send_header("Content-Security-Policy", "sandbox; default-src 'none'")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            return

    def _send_json(self, payload: dict[str, object], status: HTTPStatus) -> None:
        body = json.dumps(payload) + "\n"
        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        try:
            self.wfile.write(encoded)
        except (BrokenPipeError, ConnectionResetError):
            return

    def _send_json_error(self, message: str, status: HTTPStatus) -> None:
        body = json.dumps({"error": message}) + "\n"
        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        try:
            self.wfile.write(encoded)
        except (BrokenPipeError, ConnectionResetError):
            return

    def _send_action_error(
        self,
        message: str,
        status: HTTPStatus,
        error_code: str,
        exc: Exception,
        retriable: bool = False,
    ) -> None:
        self._send_json(
            {
                "error": message,
                "error_code": error_code,
                "error_type": type(exc).__name__,
                "retriable": bool(retriable),
            },
            status,
        )


# find_listening_pids, stop_listening_processes, check_server_health, and
# run_operating_layer_server have been extracted to operating_layer_lifecycle.py
# and re-exported above via the import statement.
