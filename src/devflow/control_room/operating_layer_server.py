from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import threading
import webbrowser
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, urlsplit

from devflow.control_room.operating_layer_assets import APP_CSS, APP_JS, INDEX_HTML
from devflow.control_room.operating_layer import render_operating_layer_snapshot_json
from devflow.control_room.project_registry import ProjectRegistryError, resolve_project_root
from devflow.control_room.supervisor_surface import (
    APPROVAL_REQUIRED_EVIDENCE_WRITING,
    APPROVAL_REQUIRED_GIT,
    APPROVAL_REQUIRED_TASK_STATE,
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
                render_operating_layer_snapshot_json(root, project_id=project_id),
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
        approved_idea_capture = False
        approved_task_creation = False
        approved_shell_worker_run = False
        approved_verification = False
        approved_promotion = False
        approved_agent_add_provider = False
        approved_agent_add_model = False
        approved_agent_run = False
        approved_agent_advise = False
        approved_agent_propose_patch = False
        if classification["safety_class"] != PURE_READ_ONLY:
            try:
                approved_idea_capture = _is_approved_idea_capture(payload, command, classification)
                approved_task_creation = _is_approved_task_creation(payload, command, classification)
                approved_shell_worker_run = _is_approved_shell_worker_run(payload, command, classification)
                approved_verification = _is_approved_task_verification(payload, command, classification)
                approved_promotion = _is_approved_task_promotion(payload, command, classification)
                approved_agent_add_provider = _is_approved_agent_add_provider(payload, command, classification)
                approved_agent_add_model = _is_approved_agent_add_model(payload, command, classification)
                approved_agent_run = _is_approved_agent_run(payload, command, classification)
                approved_agent_advise = _is_approved_agent_advise(payload, command, classification)
                approved_agent_propose_patch = _is_approved_agent_propose_patch(payload, command, classification)
            except ValueError as exc:
                self._send_json_error(str(exc), HTTPStatus.BAD_REQUEST)
                return
        if classification["safety_class"] != PURE_READ_ONLY and not (
            approved_idea_capture
            or approved_task_creation
            or approved_shell_worker_run
            or approved_verification
            or approved_promotion
            or approved_agent_add_provider
            or approved_agent_add_model
            or approved_agent_run
            or approved_agent_advise
            or approved_agent_propose_patch
        ):
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
            if approved_idea_capture:
                args = _approved_idea_capture_command_args(command)
            elif approved_task_creation:
                args = _approved_task_creation_command_args(command)
            elif approved_agent_add_provider:
                args = _approved_agent_add_provider_command_args(command)
            elif approved_agent_add_model:
                args = _approved_agent_add_model_command_args(command)
            elif approved_agent_run:
                args = _approved_agent_run_command_args(command)
            elif approved_agent_advise:
                args = _approved_agent_advise_command_args(command)
            elif approved_agent_propose_patch:
                args = _approved_agent_propose_patch_command_args(command)
            elif approved_shell_worker_run:
                args = _approved_shell_worker_run_command_args(command)
            elif approved_verification:
                args = _approved_task_verification_command_args(command)
            elif approved_promotion:
                args = _approved_task_promotion_command_args(command)
            else:
                args = _supervisor_read_only_command_args(command)
            context_path = _write_promotion_context(root, command, payload) if approved_promotion else None
        except (ProjectRegistryError, OSError, ValueError) as exc:
            self._send_json_error(str(exc), HTTPStatus.BAD_REQUEST)
            return

        env = _devflow_subprocess_env()
        try:
            completed = subprocess.run(
                args,
                cwd=root,
                env=env,
                text=True,
                input="y\n" if approved_promotion else None,
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
                "context_path": context_path,
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


def _approved_idea_capture_command_args(command: str) -> list[str]:
    tokens = shlex.split(command)
    normalized = _normalize_devflow_command_tokens(tokens)
    if len(normalized) < 4 or normalized[1:3] != ["idea", "capture"]:
        raise ValueError("only approved idea capture may run from the operating layer")
    allowed_value_options = {"--title", "--source", "--tag"}
    index = 3
    idea_texts: list[str] = []
    while index < len(normalized):
        token = normalized[index]
        if token in allowed_value_options:
            if index + 1 >= len(normalized) or normalized[index + 1].startswith("-"):
                raise ValueError(f"approved browser idea capture requires a value after {token}")
            if token == "--title" and _is_placeholder_text(normalized[index + 1], field="title"):
                raise ValueError("approved browser idea capture requires a concrete title when --title is used")
            index += 2
            continue
        if token.startswith("-"):
            raise ValueError("approved browser idea capture allows only --title, --source, and --tag")
        idea_texts.append(token)
        index += 1
    if len(idea_texts) != 1:
        raise ValueError("approved browser idea capture requires one quoted idea body")
    if _is_placeholder_text(idea_texts[0], field="idea"):
        raise ValueError("approved browser idea capture requires concrete brainstorm text")
    return _devflow_command_args_from_tokens(tokens)


def _approved_task_creation_command_args(command: str) -> list[str]:
    tokens = shlex.split(command)
    normalized = _normalize_devflow_command_tokens(tokens)
    if len(normalized) < 4 or normalized[1:3] != ["task", "create"]:
        raise ValueError("only approved task creation may run from the operating layer")
    allowed_flags = {"--git-worktree"}
    allowed_value_options = {"--project"}
    index = 3
    titles: list[str] = []
    while index < len(normalized):
        token = normalized[index]
        if token in allowed_flags:
            index += 1
            continue
        if token in allowed_value_options:
            if index + 1 >= len(normalized) or normalized[index + 1].startswith("-"):
                raise ValueError("approved browser task creation requires a project id after --project")
            index += 2
            continue
        if token.startswith("-"):
            raise ValueError("approved browser task creation allows only --project and --git-worktree")
        titles.append(token)
        index += 1
    if len(titles) != 1:
        raise ValueError("approved browser task creation requires one quoted task title")
    if _is_placeholder_text(titles[0], field="title"):
        raise ValueError("approved browser task creation requires a concrete task title")
    return _devflow_command_args_from_tokens(tokens)


def _approved_shell_worker_run_command_args(command: str) -> list[str]:
    tokens = shlex.split(command)
    normalized = _normalize_devflow_command_tokens(tokens)
    if len(normalized) < 6 or normalized[1:3] != ["task", "run"]:
        raise ValueError("only approved shell worker runs may run from the operating layer")
    task_id = normalized[3]
    if not task_id or task_id.startswith("-"):
        raise ValueError("shell worker run requires a task id")
    if "--" not in normalized:
        raise ValueError("approved browser shell worker run requires a command after '--'")
    separator = normalized.index("--")
    options = normalized[4:separator]
    command_tokens = normalized[separator + 1 :]
    worker = None
    index = 0
    while index < len(options):
        token = options[index]
        if token == "--worker":
            if index + 1 >= len(options):
                raise ValueError("approved browser shell worker run requires --worker shell")
            worker = options[index + 1]
            index += 2
            continue
        if token == "--project":
            if index + 1 >= len(options) or options[index + 1].startswith("-"):
                raise ValueError("approved browser shell worker run requires a project id after --project")
            index += 2
            continue
        if token == "--timeout-seconds":
            if index + 1 >= len(options) or not options[index + 1].isdigit():
                raise ValueError("approved browser shell worker run requires a numeric --timeout-seconds value")
            index += 2
            continue
        raise ValueError("approved browser shell worker run allows only --project, --worker shell, and --timeout-seconds")
    if worker != "shell":
        raise ValueError("browser worker execution is limited to --worker shell")
    shell_command = " ".join(command_tokens).strip()
    if _is_placeholder_text(shell_command, field="command"):
        raise ValueError("approved browser shell worker run requires a concrete command")
    if _looks_like_provider_or_local_model_command(command_tokens):
        raise ValueError("provider and local-model commands cannot run from the browser shell-worker path")
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


def _approved_task_promotion_command_args(command: str) -> list[str]:
    tokens = shlex.split(command)
    normalized = _normalize_devflow_command_tokens(tokens)
    if len(normalized) < 4 or normalized[1:3] != ["task", "promote"]:
        raise ValueError("only approved task promotion may run from the operating layer")
    task_id = normalized[3]
    if not task_id or task_id.startswith("-"):
        raise ValueError("task promotion command requires a task id")
    allowed_options = {"--project"}
    index = 4
    while index < len(normalized):
        token = normalized[index]
        if token not in allowed_options:
            raise ValueError("approved browser promotion allows only the optional --project flag")
        if token == "--project":
            if index + 1 >= len(normalized) or normalized[index + 1].startswith("-"):
                raise ValueError("approved browser promotion requires a project id after --project")
            index += 2
            continue
        index += 1
    return _devflow_command_args_from_tokens(tokens)


def _approved_agent_add_provider_command_args(command: str) -> list[str]:
    tokens = shlex.split(command)
    normalized = _normalize_devflow_command_tokens(tokens)
    if len(normalized) < 4 or normalized[1:3] != ["agent", "add-provider"]:
        raise ValueError("only approved agent add-provider may run from the operating layer")
    provider_id = normalized[3]
    if _is_placeholder_text(provider_id, field="provider"):
        raise ValueError("approved provider onboarding requires a concrete provider id")
    values = _parse_exact_options(
        normalized[4:],
        value_options={"--adapter", "--base-url", "--api-key-env", "--timeout-seconds"},
        flags={"--json"},
        command_label="approved provider onboarding",
    )
    if "--adapter" not in values or "--base-url" not in values:
        raise ValueError("approved provider onboarding requires --adapter and --base-url")
    if _is_placeholder_text(values["--adapter"], field="adapter"):
        raise ValueError("approved provider onboarding requires a concrete adapter")
    if _is_placeholder_text(values["--base-url"], field="url"):
        raise ValueError("approved provider onboarding requires a concrete base URL")
    if "--timeout-seconds" in values and not values["--timeout-seconds"].isdigit():
        raise ValueError("approved provider onboarding requires a numeric --timeout-seconds value")
    return _devflow_command_args_from_tokens(tokens)


def _approved_agent_add_model_command_args(command: str) -> list[str]:
    tokens = shlex.split(command)
    normalized = _normalize_devflow_command_tokens(tokens)
    if len(normalized) < 3 or normalized[1:3] != ["agent", "add-model"]:
        raise ValueError("only approved agent add-model may run from the operating layer")
    values = _parse_exact_options(
        normalized[3:],
        value_options={"--provider", "--model", "--authority", "--role", "--profile-id"},
        flags={"--json"},
        command_label="approved model onboarding",
    )
    for option in ("--provider", "--model", "--authority", "--role"):
        if option not in values:
            raise ValueError(f"approved model onboarding requires {option}")
    if values["--authority"] not in {"read-only", "advisory", "patch-proposer", "disabled"}:
        raise ValueError("approved model onboarding authority must be read-only, advisory, patch-proposer, or disabled")
    for option, field in (("--provider", "provider"), ("--model", "model"), ("--role", "role")):
        if _is_placeholder_text(values[option], field=field):
            raise ValueError(f"approved model onboarding requires a concrete {field}")
    return _devflow_command_args_from_tokens(tokens)


def _approved_agent_run_command_args(command: str) -> list[str]:
    tokens = shlex.split(command)
    normalized = _normalize_devflow_command_tokens(tokens)
    if len(normalized) < 3 or normalized[1:3] != ["agent", "run"]:
        raise ValueError("only approved agent run may run from the operating layer")
    values = _parse_exact_options(
        normalized[3:],
        value_options={"--task", "--profile"},
        flags={"--json"},
        command_label="approved model run",
    )
    if "--task" not in values or "--profile" not in values:
        raise ValueError("approved model run requires --task and --profile")
    if _is_placeholder_text(values["--task"], field="task-id") or _is_placeholder_text(values["--profile"], field="profile"):
        raise ValueError("approved model run requires concrete task and profile ids")
    return _devflow_command_args_from_tokens(tokens)


def _approved_agent_advise_command_args(command: str) -> list[str]:
    tokens = shlex.split(command)
    normalized = _normalize_devflow_command_tokens(tokens)
    if len(normalized) < 3 or normalized[1:3] != ["agent", "advise"]:
        raise ValueError("only approved agent advise may run from the operating layer")
    values = _parse_exact_options(
        normalized[3:],
        value_options={"--profile", "--job", "--task"},
        flags={"--json"},
        command_label="approved advisory model run",
    )
    if "--profile" not in values or "--job" not in values:
        raise ValueError("approved advisory model run requires --profile and --job")
    if values["--job"] not in {"gap-analysis", "review", "status"}:
        raise ValueError("approved advisory job must be gap-analysis, review, or status")
    if _is_placeholder_text(values["--profile"], field="profile"):
        raise ValueError("approved advisory model run requires a concrete profile id")
    return _devflow_command_args_from_tokens(tokens)


def _approved_agent_propose_patch_command_args(command: str) -> list[str]:
    tokens = shlex.split(command)
    normalized = _normalize_devflow_command_tokens(tokens)
    if len(normalized) < 3 or normalized[1:3] != ["agent", "propose-patch"]:
        raise ValueError("only approved agent propose-patch may run from the operating layer")
    values = _parse_exact_options(
        normalized[3:],
        value_options={"--task", "--profile"},
        flags={"--json"},
        command_label="approved patch-proposal model run",
    )
    if "--task" not in values or "--profile" not in values:
        raise ValueError("approved patch proposal requires --task and --profile")
    if _is_placeholder_text(values["--task"], field="task-id") or _is_placeholder_text(values["--profile"], field="profile"):
        raise ValueError("approved patch proposal requires concrete task and profile ids")
    return _devflow_command_args_from_tokens(tokens)


def _parse_exact_options(
    tokens: list[str],
    *,
    value_options: set[str],
    flags: set[str],
    command_label: str,
) -> dict[str, str]:
    values: dict[str, str] = {}
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token in flags:
            index += 1
            continue
        if token in value_options:
            if index + 1 >= len(tokens) or tokens[index + 1].startswith("-"):
                raise ValueError(f"{command_label} requires a value after {token}")
            values[token] = tokens[index + 1]
            index += 2
            continue
        if token.startswith("-"):
            allowed = ", ".join(sorted(value_options | flags))
            raise ValueError(f"{command_label} allows only {allowed}")
        raise ValueError(f"{command_label} does not allow positional value '{token}'")
    return values


def _write_promotion_context(root: Path, command: str, payload: dict[str, object]) -> str | None:
    note = payload.get("context_note")
    if not isinstance(note, str) or not note.strip():
        return None
    _approved_task_promotion_command_args(command)
    task_id = _promotion_task_id(command)
    task_path = root / ".devflow" / "tasks" / task_id
    if not task_path.is_dir():
        raise ValueError(f"task not found for promotion context: {task_id}")
    cleaned = note.strip()
    if len(cleaned) > 4000:
        cleaned = cleaned[:4000].rstrip() + "\n\n[truncated]"
    context_path = task_path / "promotion-context.md"
    timestamp = datetime.now(timezone.utc).isoformat()
    entry = (
        f"\n## {timestamp}\n\n"
        f"- command: `{command}`\n"
        f"- source: operating-layer approval\n\n"
        f"{cleaned}\n"
    )
    if context_path.exists():
        with context_path.open("a", encoding="utf-8") as handle:
            handle.write(entry)
    else:
        context_path.write_text("# Human Promotion Context\n" + entry, encoding="utf-8")
    return context_path.relative_to(root).as_posix()


def _promotion_task_id(command: str) -> str:
    normalized = _normalize_devflow_command_tokens(shlex.split(command))
    if len(normalized) < 4:
        raise ValueError("task promotion command requires a task id")
    return normalized[3]


def _is_approved_idea_capture(payload: dict[str, object], command: str, classification: dict[str, object]) -> bool:
    if classification["safety_class"] != APPROVAL_REQUIRED_EVIDENCE_WRITING:
        return False
    try:
        _approved_idea_capture_command_args(command)
    except ValueError:
        return False
    return _approval_payload_matches(payload, command)


def _is_approved_task_creation(payload: dict[str, object], command: str, classification: dict[str, object]) -> bool:
    if classification["safety_class"] != APPROVAL_REQUIRED_TASK_STATE:
        return False
    try:
        _approved_task_creation_command_args(command)
    except ValueError:
        return False
    return _approval_payload_matches(payload, command)


def _is_approved_shell_worker_run(payload: dict[str, object], command: str, classification: dict[str, object]) -> bool:
    if classification["safety_class"] != APPROVAL_REQUIRED_WORKER_RUNTIME:
        return False
    try:
        _approved_shell_worker_run_command_args(command)
    except ValueError:
        return False
    return _approval_payload_matches(payload, command)


def _is_approved_task_verification(payload: dict[str, object], command: str, classification: dict[str, object]) -> bool:
    if classification["safety_class"] != APPROVAL_REQUIRED_WORKER_RUNTIME:
        return False
    try:
        _approved_task_verification_command_args(command)
    except ValueError:
        return False
    return _approval_payload_matches(payload, command)


def _is_approved_task_promotion(payload: dict[str, object], command: str, classification: dict[str, object]) -> bool:
    if classification["safety_class"] != APPROVAL_REQUIRED_GIT:
        return False
    try:
        _approved_task_promotion_command_args(command)
    except ValueError:
        return False
    return _approval_payload_matches(payload, command)


def _is_approved_agent_add_provider(payload: dict[str, object], command: str, classification: dict[str, object]) -> bool:
    if classification["safety_class"] != APPROVAL_REQUIRED_TASK_STATE:
        return False
    try:
        _approved_agent_add_provider_command_args(command)
    except ValueError:
        return False
    return _approval_payload_matches(payload, command)


def _is_approved_agent_add_model(payload: dict[str, object], command: str, classification: dict[str, object]) -> bool:
    if classification["safety_class"] != APPROVAL_REQUIRED_TASK_STATE:
        return False
    try:
        _approved_agent_add_model_command_args(command)
    except ValueError:
        return False
    return _approval_payload_matches(payload, command)


def _is_approved_agent_run(payload: dict[str, object], command: str, classification: dict[str, object]) -> bool:
    if classification["safety_class"] != APPROVAL_REQUIRED_WORKER_RUNTIME:
        return False
    try:
        _approved_agent_run_command_args(command)
    except ValueError:
        return False
    return _approval_payload_matches(payload, command)


def _is_approved_agent_advise(payload: dict[str, object], command: str, classification: dict[str, object]) -> bool:
    if classification["safety_class"] != APPROVAL_REQUIRED_WORKER_RUNTIME:
        return False
    try:
        _approved_agent_advise_command_args(command)
    except ValueError:
        return False
    return _approval_payload_matches(payload, command)


def _is_approved_agent_propose_patch(payload: dict[str, object], command: str, classification: dict[str, object]) -> bool:
    if classification["safety_class"] != APPROVAL_REQUIRED_WORKER_RUNTIME:
        return False
    try:
        _approved_agent_propose_patch_command_args(command)
    except ValueError:
        return False
    return _approval_payload_matches(payload, command)


def _approval_payload_matches(payload: dict[str, object], command: str) -> bool:
    if payload.get("human_approved") is not True:
        return False
    if payload.get("approval_phrase") != ACTION_APPROVAL_PHRASE:
        return False
    if payload.get("approved_command") != command:
        return False
    return True


def _is_placeholder_text(value: str, *, field: str) -> bool:
    normalized = " ".join(value.strip().lower().split())
    placeholders = {
        "",
        "...",
        "todo",
        "tbd",
        "placeholder",
        f"<{field}>",
        field,
    }
    if field == "command":
        placeholders.update({"your command", "run command", "shell command"})
    if field == "idea":
        placeholders.update({"your idea", "rough idea", "brainstorm", "brainstorm here"})
    if field == "title":
        placeholders.update({"task title", "untitled", "new task"})
    if field in {"provider", "model", "profile", "task-id", "adapter", "url", "role"}:
        placeholders.update({
            f"<{field}>",
            field.replace("-", " "),
            f"your {field}",
            f"{field} id",
            f"{field}-id",
        })
    return normalized in placeholders


def _looks_like_provider_or_local_model_command(command_tokens: list[str]) -> bool:
    if not command_tokens:
        return False
    lowered = [token.lower() for token in command_tokens]
    joined = " ".join(lowered)
    if lowered[:3] == ["devflow", "task", "local"]:
        return True
    if lowered[:3] == ["devflow", "agent", "run"]:
        return True
    if lowered[:3] == ["devflow", "agent", "advise"]:
        return True
    if lowered[:3] == ["devflow", "agent", "propose-patch"]:
        return True
    if lowered[:3] == ["devflow", "agent", "add-model"]:
        return True
    if lowered[:3] == ["devflow", "agent", "add-provider"]:
        return True
    provider_markers = (
        "ollama",
        "openai",
        "anthropic",
        "gemini",
        "claude",
        "aider",
        "opencode",
        "qwen",
        "qwopus",
        "gemma",
    )
    return any(marker in joined for marker in provider_markers)


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
