from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from http import HTTPStatus
from pathlib import Path
from typing import Callable

from devflow.legacy.control_room.browser_action_policy import (
    BrowserActionCommand,
    promotion_task_id_from_command,
    resolve_browser_action_command,
)
from devflow.legacy.control_room.project_registry import ProjectRegistryError, resolve_project_root
from devflow.legacy.control_room.supervisor_surface import classify_supervisor_command


ACTION_TIMEOUT_SECONDS = 20
ACTION_OUTPUT_LIMIT = 12000


@dataclass(frozen=True)
class BrowserActionResponse:
    status: HTTPStatus
    payload: dict[str, object]


class BrowserActionExecutionError(Exception):
    def __init__(
        self,
        message: str,
        status: HTTPStatus,
        error_code: str,
        cause: Exception,
        *,
        retriable: bool = False,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status = status
        self.error_code = error_code
        self.cause = cause
        self.retriable = retriable


Resolver = Callable[[dict[str, object], str, dict[str, object]], BrowserActionCommand | None]


def execute_browser_action(
    payload: dict[str, object],
    repo_root: Path,
    *,
    resolve_command: Resolver = resolve_browser_action_command,
) -> BrowserActionResponse:
    command = str(payload["command"])
    classification = classify_supervisor_command(command)
    try:
        browser_action = resolve_command(payload, command, classification)
    except ValueError as exc:
        raise BrowserActionExecutionError(
            str(exc),
            HTTPStatus.BAD_REQUEST,
            "resolver_failure",
            exc,
        ) from exc

    if browser_action is None:
        return BrowserActionResponse(
            status=HTTPStatus.CONFLICT,
            payload={
                "executed": False,
                "requires_human_approval": bool(classification["requires_human_approval"]),
                "classification": classification,
                "message": classification["why_not_auto_runnable"]
                or "command is not supervisor-safe for browser execution",
            },
        )

    try:
        root = repo_root
        project_id = payload.get("project")
        if isinstance(project_id, str) and project_id.strip():
            root = resolve_project_root(repo_root, project_id.strip()).root
        context_path = _write_promotion_context(root, command, payload) if browser_action.writes_promotion_context else None
    except (ProjectRegistryError, OSError, ValueError) as exc:
        raise BrowserActionExecutionError(
            str(exc),
            HTTPStatus.BAD_REQUEST,
            "resolver_failure",
            exc,
        ) from exc

    try:
        completed = subprocess.run(
            browser_action.args,
            cwd=root,
            env=_devflow_subprocess_env(),
            text=True,
            input="y\n" if browser_action.writes_promotion_context else None,
            capture_output=True,
            timeout=ACTION_TIMEOUT_SECONDS,
            check=False,
        )
    except FileNotFoundError as exc:
        raise BrowserActionExecutionError(
            f"failed to execute command: {exc}",
            HTTPStatus.INTERNAL_SERVER_ERROR,
            "command_execution_failed",
            exc,
            retriable=True,
        ) from exc
    except OSError as exc:
        raise BrowserActionExecutionError(
            f"failed to execute command: {exc}",
            HTTPStatus.INTERNAL_SERVER_ERROR,
            "command_execution_failed",
            exc,
            retriable=True,
        ) from exc
    except subprocess.TimeoutExpired as exc:
        timeout_message = f"command timed out after {ACTION_TIMEOUT_SECONDS}s"
        return BrowserActionResponse(
            status=HTTPStatus.REQUEST_TIMEOUT,
            payload={
                "error": timeout_message,
                "error_code": "command_timed_out",
                "error_type": type(exc).__name__,
                "retriable": True,
                "executed": True,
                "timed_out": True,
                "exit_code": None,
                "classification": classification,
                "stdout": _truncate_text(exc.stdout or ""),
                "stderr": _truncate_text(exc.stderr or timeout_message),
                "output_truncated": _output_was_truncated(exc.stdout or "", exc.stderr or ""),
            },
        )

    stdout = completed.stdout or ""
    stderr = completed.stderr or ""
    return BrowserActionResponse(
        status=HTTPStatus.OK,
        payload={
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
    )


def _write_promotion_context(root: Path, command: str, payload: dict[str, object]) -> str | None:
    note = payload.get("context_note")
    if not isinstance(note, str) or not note.strip():
        return None
    task_id = promotion_task_id_from_command(command)
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
