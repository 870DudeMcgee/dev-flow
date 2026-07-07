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
from devflow.control_room.operating_layer_assets import APP_CSS, APP_JS, INDEX_HTML
from devflow.control_room.operating_layer_actions_agents_task_context_handlers import ActionsAgentsTaskContextHandlerMixin
from devflow.control_room.operating_layer_brainstorm_handlers import BrainstormHandlerMixin
from devflow.control_room.operating_layer_browse_snapshot_repo_handlers import BrowseSnapshotRepoHandlerMixin
from devflow.control_room.operating_layer_infrastructure_handlers import HttpInfrastructureMixin
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


class OperatingLayerHTTPServer(ThreadingHTTPServer):
    def __init__(self, server_address: tuple[str, int], repo_root: Path) -> None:
        super().__init__(server_address, OperatingLayerRequestHandler)
        self.repo_root = repo_root.resolve()


class OperatingLayerRequestHandler(ActionsAgentsTaskContextHandlerMixin, BrowseSnapshotRepoHandlerMixin, RefactorHandlerMixin, GatesLocalModelHandlerMixin, WorkbenchHandlerMixin, BuilderJudgeHandlerMixin, ObsidianHandlerMixin, BrainstormHandlerMixin, HttpInfrastructureMixin, BaseHTTPRequestHandler):
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
        "/api/brainstorm/classify": "_handle_brainstorm_classify",
        "/api/brainstorm/intent-summary": "_handle_brainstorm_intent_summary",
        "/api/obsidian/task-preview": "_handle_obsidian_task_preview",
        "/api/obsidian/task-create": "_handle_obsidian_task_create",
        "/api/obsidian/scout-pack-preview": "_handle_obsidian_scout_pack_preview",
        "/api/obsidian/scout-pack-create": "_handle_obsidian_scout_pack_create",
        "/api/pipeline/intake": "_handle_pipeline_intake",
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


# find_listening_pids, stop_listening_processes, check_server_health, and
# run_operating_layer_server have been extracted to operating_layer_lifecycle.py
# and re-exported above via the import statement.
