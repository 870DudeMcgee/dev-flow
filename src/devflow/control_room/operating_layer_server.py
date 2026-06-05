from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, urlsplit

from devflow.control_room.operating_layer_assets import APP_CSS, APP_JS, INDEX_HTML
from devflow.control_room.operating_layer import render_operating_layer_snapshot_json
from devflow.control_room.project_registry import ProjectRegistryError, resolve_project_root
from devflow.control_room.supervisor_surface import (
    APPROVAL_REQUIRED_WORKER_RUNTIME,
    PURE_READ_ONLY,
    classify_supervisor_command,
)


ACTION_TIMEOUT_SECONDS = 20
ACTION_OUTPUT_LIMIT = 12000
ACTION_APPROVAL_PHRASE = "I approve this exact Dev-Flow command"


class OperatingLayerHTTPServer(ThreadingHTTPServer):
    def __init__(self, server_address: tuple[str, int], repo_root: Path) -> None:
        super().__init__(server_address, OperatingLayerRequestHandler)
        self.repo_root = repo_root.resolve()


class OperatingLayerRequestHandler(BaseHTTPRequestHandler):
    server: OperatingLayerHTTPServer

    def do_GET(self) -> None:
        request = urlsplit(self.path)
        path = request.path
        if path in {"/", "/index.html"}:
            self._send_text(INDEX_HTML, "text/html; charset=utf-8")
            return
        if path == "/app.css":
            self._send_text(APP_CSS, "text/css; charset=utf-8")
            return
        if path == "/app.js":
            self._send_text(APP_JS, "application/javascript; charset=utf-8")
            return
        if path == "/api/snapshot":
            query = parse_qs(request.query)
            project_id = (query.get("project") or [None])[0]
            try:
                root = self.server.repo_root
                if project_id:
                    root = resolve_project_root(self.server.repo_root, project_id).root
            except ProjectRegistryError as exc:
                self._send_json_error(str(exc), HTTPStatus.BAD_REQUEST)
                return
            self._send_text(
                render_operating_layer_snapshot_json(root),
                "application/json; charset=utf-8",
            )
            return
        if path == "/healthz":
            self._send_text(json.dumps({"status": "ok"}) + "\n", "application/json; charset=utf-8")
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        request = urlsplit(self.path)
        if request.path != "/api/actions/run":
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        try:
            payload = self._read_json_body()
        except ValueError as exc:
            self._send_json_error(str(exc), HTTPStatus.BAD_REQUEST)
            return

        command = payload.get("command")
        if not isinstance(command, str) or not command.strip():
            self._send_json_error("command is required", HTTPStatus.BAD_REQUEST)
            return

        classification = classify_supervisor_command(command)
        approved_mutation = False
        if classification["safety_class"] != PURE_READ_ONLY:
            try:
                approved_mutation = _is_approved_task_verification(payload, command, classification)
            except ValueError as exc:
                self._send_json_error(str(exc), HTTPStatus.BAD_REQUEST)
                return
        if classification["safety_class"] != PURE_READ_ONLY and not approved_mutation:
            self._send_json(
                {
                    "executed": False,
                    "requires_human_approval": bool(classification["requires_human_approval"]),
                    "classification": classification,
                    "message": classification["why_not_auto_runnable"]
                    or "command is not supervisor-safe for browser execution",
                },
                HTTPStatus.CONFLICT,
            )
            return

        project_id = payload.get("project")
        try:
            root = self.server.repo_root
            if isinstance(project_id, str) and project_id.strip():
                root = resolve_project_root(self.server.repo_root, project_id.strip()).root
            args = (
                _approved_task_verification_command_args(command)
                if approved_mutation
                else _supervisor_read_only_command_args(command)
            )
        except (ProjectRegistryError, ValueError) as exc:
            self._send_json_error(str(exc), HTTPStatus.BAD_REQUEST)
            return

        env = _devflow_subprocess_env()
        try:
            completed = subprocess.run(
                args,
                cwd=root,
                env=env,
                text=True,
                capture_output=True,
                timeout=ACTION_TIMEOUT_SECONDS,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            self._send_json(
                {
                    "executed": True,
                    "timed_out": True,
                    "exit_code": None,
                    "classification": classification,
                    "stdout": _truncate_text(exc.stdout or ""),
                    "stderr": _truncate_text(exc.stderr or f"Command timed out after {ACTION_TIMEOUT_SECONDS}s"),
                    "output_truncated": _output_was_truncated(exc.stdout or "", exc.stderr or ""),
                },
                HTTPStatus.REQUEST_TIMEOUT,
            )
            return

        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
        self._send_json(
            {
                "executed": True,
                "timed_out": False,
                "exit_code": completed.returncode,
                "requires_human_approval": bool(classification["requires_human_approval"]),
                "classification": classification,
                "stdout": _truncate_text(stdout),
                "stderr": _truncate_text(stderr),
                "output_truncated": _output_was_truncated(stdout, stderr),
            },
            HTTPStatus.OK,
        )

    def log_message(self, format: str, *args: object) -> None:
        return

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
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        try:
            self.wfile.write(encoded)
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


def run_operating_layer_server(
    repo_root: Path,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    open_browser: bool = False,
    ready_callback: Callable[[OperatingLayerHTTPServer], None] | None = None,
) -> None:
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


def _supervisor_read_only_command_args(command: str) -> list[str]:
    tokens = shlex.split(command)
    return _devflow_command_args_from_tokens(tokens)


def _approved_task_verification_command_args(command: str) -> list[str]:
    tokens = shlex.split(command)
    normalized = _normalize_devflow_command_tokens(tokens)
    if len(normalized) < 5 or normalized[1:3] != ["task", "verify"]:
        raise ValueError("only approved task verification may run from the operating layer")
    task_id = normalized[3]
    if not task_id or task_id.startswith("-"):
        raise ValueError("task verification command requires a task id")
    if "--shell" not in normalized:
        raise ValueError('approved browser verification requires --shell "<command>"')
    shell_index = normalized.index("--shell")
    if shell_index + 1 >= len(normalized):
        raise ValueError('approved browser verification requires --shell "<command>"')
    shell_command = normalized[shell_index + 1].strip()
    if not shell_command or shell_command == "<command>":
        raise ValueError("approved browser verification requires a concrete shell command")
    return _devflow_command_args_from_tokens(tokens)


def _is_approved_task_verification(payload: dict[str, object], command: str, classification: dict[str, object]) -> bool:
    if classification["safety_class"] != APPROVAL_REQUIRED_WORKER_RUNTIME:
        return False
    try:
        _approved_task_verification_command_args(command)
    except ValueError:
        return False
    if payload.get("human_approved") is not True:
        return False
    if payload.get("approval_phrase") != ACTION_APPROVAL_PHRASE:
        return False
    if payload.get("approved_command") != command:
        return False
    return True


def _devflow_command_args_from_tokens(tokens: list[str]) -> list[str]:
    normalized = _normalize_devflow_command_tokens(tokens)
    if not normalized:
        raise ValueError("command is required")
    if normalized[0] == "devflow":
        return [sys.executable, "-m", "devflow", *normalized[1:]]
    raise ValueError("only devflow commands may run from the operating layer")


def _normalize_devflow_command_tokens(tokens: list[str]) -> list[str]:
    if tokens and tokens[0] == "run":
        tokens = tokens[1:]
    if not tokens:
        return []
    if len(tokens) >= 4 and tokens[1:3] == ["-m", "devflow.cli"]:
        return ["devflow", *tokens[3:]]
    return tokens


def _devflow_subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    src_root = Path(__file__).resolve().parents[2]
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = f"{src_root}{os.pathsep}{existing}" if existing else src_root.as_posix()
    return env


def _truncate_text(value: str) -> str:
    if len(value) <= ACTION_OUTPUT_LIMIT:
        return value
    return value[:ACTION_OUTPUT_LIMIT] + "\n...[truncated]"


def _output_was_truncated(stdout: str, stderr: str) -> bool:
    return len(stdout) > ACTION_OUTPUT_LIMIT or len(stderr) > ACTION_OUTPUT_LIMIT
