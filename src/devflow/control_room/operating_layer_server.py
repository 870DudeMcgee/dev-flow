from __future__ import annotations

import json
import subprocess  # noqa: F401 - test patches operating_layer_server.subprocess
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable  # noqa: F401 - re-exported for type hints
from urllib.parse import parse_qs, urlsplit

from devflow.control_room.architecture_evidence import (
    ArtifactResolutionError,
    resolve_architecture_artifact,
)
from devflow.control_room.env_loader import load_hermes_env_file  # noqa: F401 - re-exported for CLI
from devflow.control_room.browser_action_executor import (
    ACTION_TIMEOUT_SECONDS,  # noqa: F401 - re-exported for route contract tests
    BrowserActionExecutionError,
    execute_browser_action,
)
from devflow.control_room.browser_action_policy import (
    resolve_browser_action_command,
)
from devflow.control_room.browse_projection import BrowsePathError, build_browse_payload
from devflow.control_room.agent_registry import (
    AgentRegistryError,
)
from devflow.control_room.local_model_ensure import (
    ensure_local_model_profile,
)
from devflow.control_room.local_model_server import (
    LocalModelServerError,
    ensure_local_model_server_for_profile,
)
from devflow.control_room.operating_layer_assets import APP_CSS, APP_JS, INDEX_HTML
from devflow.control_room.operating_layer import render_operating_layer_snapshot_json
from devflow.control_room.operating_layer_brainstorm_handlers import BrainstormHandlerMixin
from devflow.control_room.operating_layer_lifecycle import (  # noqa: F401 - re-exported for backward compat
    check_server_health,
    find_listening_pids,
    run_operating_layer_server,
    stop_listening_processes,
)
from devflow.control_room.operating_layer_builder_judge_handlers import BuilderJudgeHandlerMixin
from devflow.control_room.operating_layer_obsidian_handlers import ObsidianHandlerMixin
from devflow.control_room.operating_layer_workbench_handlers import WorkbenchHandlerMixin
from devflow.control_room.project_registry import ProjectRegistryError, resolve_project_root
from devflow.control_room.refactor_loop import (
    RefactorLoopError,
    load_refactor_run_status,
    require_refactor_approval,
    start_refactor_loop,
)
from devflow.control_room.unified_workbench import (
    WorkbenchError,
    setup_gate,
)

BROWSE_MAX_DIRECTORY_ENTRIES = 120
BROWSE_MAX_FILE_BYTES = 64 * 1024


class OperatingLayerHTTPServer(ThreadingHTTPServer):
    def __init__(self, server_address: tuple[str, int], repo_root: Path) -> None:
        super().__init__(server_address, OperatingLayerRequestHandler)
        self.repo_root = repo_root.resolve()


class OperatingLayerRequestHandler(WorkbenchHandlerMixin, BuilderJudgeHandlerMixin, ObsidianHandlerMixin, BrainstormHandlerMixin, BaseHTTPRequestHandler):
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

    # ── Snapshot handler (extracted from inline do_GET) ─────────────
    def _handle_snapshot(self, query: dict[str, list[str]]) -> None:
        project_id = (query.get("project") or [None])[0]
        try:
            root = self.server.repo_root
            if project_id:
                root = resolve_project_root(self.server.repo_root, project_id).root
        except ProjectRegistryError as exc:
            self._send_json_error(str(exc), HTTPStatus.BAD_REQUEST)
            return
        self._send_text(
            render_operating_layer_snapshot_json(root, project_id=project_id),
            "application/json; charset=utf-8",
        )

    # ── Actions run handler (extracted from inline do_POST) ─────────
    def _handle_actions_run(self) -> None:
        try:
            payload = self._read_json_body()
        except ValueError as exc:
            self._send_action_error(str(exc), HTTPStatus.BAD_REQUEST, "invalid_json", exc)
            return

        command = payload.get("command")
        if not isinstance(command, str) or not command.strip():
            self._send_action_error("command is required", HTTPStatus.BAD_REQUEST, "missing_command", ValueError("command is required"))
            return

        try:
            response = execute_browser_action(
                payload,
                self.server.repo_root,
                resolve_command=resolve_browser_action_command,
            )
        except BrowserActionExecutionError as exc:
            self._send_action_error(
                exc.message,
                exc.status,
                exc.error_code,
                exc.cause,
                retriable=exc.retriable,
            )
            return

        self._send_json(response.payload, response.status)

    def log_message(self, format: str, *args: object) -> None:
        return

    def _handle_browse(self, query: dict[str, list[str]]) -> None:
        try:
            raw_path = (query.get("path") or [None])[0]
            payload = build_browse_payload(
                raw_path,
                max_file_bytes=BROWSE_MAX_FILE_BYTES,
                max_directory_entries=BROWSE_MAX_DIRECTORY_ENTRIES,
            )
            self._send_json(payload, HTTPStatus.OK)
        except BrowsePathError as exc:
            self._send_json_error(str(exc), HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            self._send_json_error(str(exc), HTTPStatus.INTERNAL_SERVER_ERROR)

    def _handle_repo_set(self) -> None:
        try:
            payload = self._read_json_body()
            raw_path = payload.get("path")
            if not isinstance(raw_path, str) or not raw_path.strip():
                self._send_json_error("path is required", HTTPStatus.BAD_REQUEST)
                return
            new_root = Path(raw_path).expanduser().resolve()
            if not new_root.is_dir():
                self._send_json_error(f"Directory does not exist: {new_root}", HTTPStatus.BAD_REQUEST)
                return
            self.server.repo_root = new_root
            has_devflow = (new_root / ".devflow").is_dir()
            self._send_json({
                "path": str(new_root),
                "name": new_root.name,
                "has_devflow": has_devflow,
            }, HTTPStatus.OK)
        except (OSError, ValueError) as exc:
            self._send_json_error(str(exc), HTTPStatus.BAD_REQUEST)
            return

    def _handle_agents_list(self) -> None:
        try:
            root = self.server.repo_root
            from devflow.control_room.agent_catalog import build_agent_catalog
            from devflow.control_room.local_model_inventory import build_local_model_inventory
            from devflow.control_room.local_model_readiness import build_local_model_readiness_plan

            catalog = build_agent_catalog(root)
            inventory = build_local_model_inventory(catalog)
            agents = [
                agent
                for agent in catalog.get("hermes_agents", [])
                if isinstance(agent, dict) and agent.get("id")
            ]
            self._send_json(
                {
                    "agents": agents,
                    "local_model_inventory": inventory,
                    "local_model_readiness": build_local_model_readiness_plan(
                        root,
                        agent_catalog=catalog,
                        inventory=inventory,
                    ),
                },
                HTTPStatus.OK,
            )
        except Exception as exc:
            self._send_json_error(str(exc), HTTPStatus.INTERNAL_SERVER_ERROR)

    def _handle_architecture_artifact(self, query: dict[str, list[str]]) -> None:
        artifact_id = (query.get("id") or [None])[0]
        project_id = (query.get("project") or [None])[0]
        try:
            root = self.server.repo_root
            if project_id:
                root = resolve_project_root(self.server.repo_root, project_id).root
        except ProjectRegistryError as exc:
            self._send_json_error(str(exc), HTTPStatus.BAD_REQUEST)
            return
        try:
            resolved = resolve_architecture_artifact(root, artifact_id or "")
        except ArtifactResolutionError as exc:
            self._send_json_error(str(exc), HTTPStatus(exc.status))
            return
        try:
            body = Path(resolved.absolute_path).read_bytes()
        except OSError:
            self._send_json_error("artifact is unavailable", HTTPStatus.NOT_FOUND)
            return
        self._send_artifact(body, resolved.content_type)

    def _handle_gates_setup(self) -> None:
        try:
            payload = self._read_json_body()
            root = self._payload_project_root(payload)
            result = setup_gate(root, payload)
        except (WorkbenchError, ProjectRegistryError, OSError, ValueError) as exc:
            self._send_json_error(str(exc), HTTPStatus.BAD_REQUEST)
            return
        except Exception as exc:
            self._send_json_error(f"Gate setup failed: {exc}", HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        self._send_json(result, HTTPStatus.OK)

    def _handle_local_model_ensure(self) -> None:
        try:
            payload = self._read_json_body()
            root = self._payload_project_root(payload)
            profile_id = payload.get("profile_id")
            if not isinstance(profile_id, str) or not profile_id.strip():
                self._send_action_error("profile_id is required", HTTPStatus.BAD_REQUEST, "validation_error", ValueError("profile_id is required"))
                return
            result = ensure_local_model_profile(
                root,
                profile_id.strip(),
                ensure_server=ensure_local_model_server_for_profile,
            )
        except KeyError as exc:
            message = str(exc.args[0]) if exc.args else str(exc)
            self._send_action_error(message, HTTPStatus.NOT_FOUND, "missing_profile", exc, retriable=False)
            return
        except LocalModelServerError as exc:
            self._send_action_error(str(exc), HTTPStatus.CONFLICT, "local_model_server_error", exc, retriable=True)
            return
        except (ProjectRegistryError, ValueError, AgentRegistryError) as exc:
            self._send_action_error(str(exc), HTTPStatus.BAD_REQUEST, "validation_error", exc)
            return
        except OSError as exc:
            self._send_action_error(str(exc), HTTPStatus.INTERNAL_SERVER_ERROR, "os_error", exc, retriable=True)
            return
        except Exception as exc:
            self._send_action_error(f"Local model ensure failed: {exc}", HTTPStatus.INTERNAL_SERVER_ERROR, "internal_error", exc, retriable=True)
            return

        self._send_json(result, HTTPStatus.OK)

    def _handle_refactor_start(self) -> None:
        try:
            payload = self._read_json_body()
            require_refactor_approval(payload)
            root = self._payload_project_root(payload)
            worker = str(payload["worker"])
            result = start_refactor_loop(root, worker=worker)
        except (RefactorLoopError, ProjectRegistryError, OSError, ValueError) as exc:
            self._send_json_error(str(exc), HTTPStatus.BAD_REQUEST)
            return
        except Exception as exc:
            self._send_json_error(f"Refactor loop failed: {exc}", HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        self._send_json(result, HTTPStatus.OK)

    def _handle_refactor_status(self, query: dict[str, list[str]]) -> None:
        try:
            root = self._query_project_root(query)
            run_id = (query.get("run_id") or [None])[0]
            loop_slug = (query.get("loop_slug") or [None])[0]
            payload = load_refactor_run_status(root, run_id=run_id, loop_slug=loop_slug)
        except RefactorLoopError as exc:
            status = HTTPStatus.NOT_FOUND if "not found" in str(exc) else HTTPStatus.BAD_REQUEST
            self._send_json_error(str(exc), status)
            return
        except (ProjectRegistryError, OSError, ValueError) as exc:
            self._send_json_error(str(exc), HTTPStatus.BAD_REQUEST)
            return
        self._send_json(payload, HTTPStatus.OK)

    def _handle_task_write_context(self) -> None:
        """Write implementation context markdown into a task workspace."""
        try:
            payload = self._read_json_body()
            task_id = payload.get("task_id")
            if not isinstance(task_id, str) or not task_id.strip():
                raise ValueError("task_id is required")
            context = payload.get("context")
            if not isinstance(context, str) or not context.strip():
                raise ValueError("context is required")
            root = self._payload_project_root(payload)
            workspace = root / ".devflow" / "workspaces" / task_id
            workspace.mkdir(parents=True, exist_ok=True)
            context_path = workspace / "implementation-context.md"
            context_path.write_text(context, encoding="utf-8")
        except (OSError, ValueError) as exc:
            self._send_json_error(str(exc), HTTPStatus.BAD_REQUEST)
            return
        self._send_json({"status": "ok", "path": str(context_path)}, HTTPStatus.OK)

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
