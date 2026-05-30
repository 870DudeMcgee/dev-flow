from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

from pydantic import BaseModel, Field

from devflow.control_room.models import TaskRecord
from devflow.control_room.paths import relative_path
from devflow.control_room.status_projection import TaskStatusProjection, build_task_status_projection

_relative = relative_path


class TaskPacketLimits(BaseModel):
    recent_events_limit: int = Field(default=20, ge=0)
    worker_log_tail_lines: int = Field(default=20, ge=0)
    verify_log_tail_lines: int = Field(default=20, ge=0)
    log_tail_bytes: int = Field(default=8192, ge=0)


class TaskPacketLog(BaseModel):
    path: str
    tail: list[str]
    line_count: int
    omitted_lines: int
    omitted_bytes: int
    truncated: bool


class TaskPacket(BaseModel):
    task_id: str
    title: str
    status: str
    adapter: str
    workspace_path: str
    worker_adapter: str
    task: dict[str, Any]
    summary: str | None
    recent_events: list[dict[str, Any]]
    verification: dict[str, Any]
    derived_summary: dict[str, Any] | None
    result_summary: str | None
    logs: dict[str, TaskPacketLog]
    constraints: list[str]
    allowed_artifacts: list[str]
    omitted_counts: dict[str, int]
    truncation_notes: list[str]


def build_task_packet(task_id: str, limits: TaskPacketLimits | None = None, *, root: Path | None = None) -> TaskPacket:
    repo_root = (root or Path.cwd()).resolve()
    packet_limits = limits or TaskPacketLimits()
    projection = build_task_status_projection(repo_root, task_id)
    task = projection.task
    task_path = projection.task_path
    notes: list[str] = []

    summary_data = _read_matching_summary(task_path / "summary.json", task, notes)
    recent_events, omitted_events, malformed_events = _read_recent_events(task_path / "events.jsonl", packet_limits.recent_events_limit, notes)
    verification = _read_verification(task_path / "verification.json", task, projection, notes)
    worker_log = _tail_log(
        repo_root,
        task_path / "logs" / "worker.log",
        "worker.log",
        packet_limits.worker_log_tail_lines,
        packet_limits.log_tail_bytes,
        notes,
    )
    verify_log = _tail_log(
        repo_root,
        task_path / "logs" / "verify.log",
        "verify.log",
        packet_limits.verify_log_tail_lines,
        packet_limits.log_tail_bytes,
        notes,
    )
    adapter = task.worker_adapter or task.worker

    # Path Virtualization Slices
    raw_workspace_path = task.workspace_path or task.workspace
    virtual_workspace_path = _virtualize_path(raw_workspace_path, repo_root, task.id)

    task_data = task.model_dump(mode="json")
    for k in ["workspace", "workspace_path", "log_path", "result_path", "verification_log_path"]:
        if k in task_data and task_data[k] is not None:
            task_data[k] = _virtualize_path(task_data[k], repo_root, task.id)

    if "log_path" in verification and verification["log_path"] is not None:
        verification["log_path"] = _virtualize_path(verification["log_path"], repo_root, task.id)

    worker_log = worker_log.model_copy(update={"path": _virtualize_path(worker_log.path, repo_root, task.id)})
    verify_log = verify_log.model_copy(update={"path": _virtualize_path(verify_log.path, repo_root, task.id)})

    allowed_artifacts = [
        _virtualize_path(p, repo_root, task.id)
        for p in _allowed_artifacts(repo_root, task_path)
    ]

    return _redact_secrets_in_value(
        TaskPacket(
            task_id=task.id,
            title=task.title,
            status=task.status,
            adapter=adapter,
            workspace_path=virtual_workspace_path,
            worker_adapter=adapter,
            task=task_data,
            summary=_packet_summary(task, summary_data),
            recent_events=recent_events,
            verification=verification,
            derived_summary=summary_data or None,
            result_summary=None,
            logs={"worker": worker_log, "verify": verify_log},
            constraints=_constraints(virtual_workspace_path or ""),
            allowed_artifacts=allowed_artifacts,
            omitted_counts={
                "events": omitted_events,
                "malformed_events": malformed_events,
                "worker_log_lines": worker_log.omitted_lines,
                "worker_log_bytes": worker_log.omitted_bytes,
                "verify_log_lines": verify_log.omitted_lines,
                "verify_log_bytes": verify_log.omitted_bytes,
            },
            truncation_notes=notes,
        )
    )


def _read_matching_summary(path: Path, task: TaskRecord, notes: list[str]) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        notes.append("Ignored summary.json because it is malformed; canonical task.yaml was used.")
        return {}
    if not isinstance(data, dict):
        notes.append("Ignored summary.json because it is malformed; canonical task.yaml was used.")
        return {}

    expected_values = {
        "task_id": task.id,
        "title": task.title,
        "status": task.status,
        "workspace_path": task.workspace_path or task.workspace,
        "latest_verification_status": task.verification_status,
    }
    for key, expected in expected_values.items():
        if key in data and data[key] != expected:
            notes.append("Ignored summary.json because it conflicts with canonical task state.")
            return {}
    allowed_keys = {
        "workspace_dirty",
        "workspace_branch",
        "workspace_commit",
        "updated_at",
        "summary",
    }
    return {key: data[key] for key in sorted(allowed_keys) if key in data}


def _packet_summary(task: TaskRecord, summary_data: dict[str, Any]) -> str:
    summary = summary_data.get("summary")
    if isinstance(summary, str) and summary.strip():
        return summary.strip()
    return f"{task.id} {task.status}: {task.title}"


def _read_recent_events(path: Path, limit: int, notes: list[str]) -> tuple[list[dict[str, Any]], int, int]:
    if not path.exists():
        return [], 0, 0
    events: list[dict[str, Any]] = []
    malformed_lines = 0
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        notes.append(f"events.jsonl could not be read: {exc}")
        return [], 0, 0

    for line in lines:
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            malformed_lines += 1
            continue
        if isinstance(event, dict):
            events.append(event)
        else:
            malformed_lines += 1

    if malformed_lines:
        notes.append(f"Omitted {malformed_lines} malformed event line(s).")

    omitted_events = max(len(events) - limit, 0)
    recent_events = events[-limit:] if limit else []
    if omitted_events:
        notes.append(f"Omitted {omitted_events} older event(s); included the {len(recent_events)} most recent event(s).")
    return recent_events, omitted_events, malformed_lines


def _read_verification(
    path: Path,
    task: TaskRecord,
    projection: TaskStatusProjection,
    notes: list[str],
) -> dict[str, Any]:
    fallback = {
        "task_id": task.id,
        "status": projection.verification_status,
        "task_status": task.status,
        "exit_code": projection.verification_exit_code,
        "log_path": projection.verification_log_path,
        "command": projection.verification_command,
        "latest_log_line": task.latest_log_line,
    }
    if not path.exists():
        return fallback
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        notes.append("verification.json was unreadable; task.yaml verification fields were used.")
        return fallback
    if not isinstance(data, dict):
        notes.append("verification.json was unreadable; task.yaml verification fields were used.")
        return fallback
    if data.get("task_id") not in (None, task.id):
        notes.append("verification.json task_id did not match task.yaml; task.yaml verification fields were used.")
        return fallback
    return {**fallback, **data}


def _tail_log(repo_root: Path, path: Path, label: str, line_limit: int, byte_limit: int, notes: list[str]) -> TaskPacketLog:
    if not path.exists():
        return TaskPacketLog(
            path=_relative(repo_root, path),
            tail=[],
            line_count=0,
            omitted_lines=0,
            omitted_bytes=0,
            truncated=False,
        )
    try:
        raw = path.read_bytes()
    except OSError as exc:
        notes.append(f"{label} could not be read: {exc}")
        return TaskPacketLog(
            path=_relative(repo_root, path),
            tail=[],
            line_count=0,
            omitted_lines=0,
            omitted_bytes=0,
            truncated=False,
        )

    decoded = raw.decode("utf-8", errors="replace")
    decoded = _redact_string(decoded)
    lines = decoded.splitlines()
    omitted_lines = max(len(lines) - line_limit, 0)
    tail = lines[-line_limit:] if line_limit else []
    omitted_bytes = 0
    if byte_limit:
        tail_text = "\n".join(tail)
        tail_bytes = tail_text.encode("utf-8")
        omitted_bytes = max(len(tail_bytes) - byte_limit, 0)
        if omitted_bytes:
            tail = tail_bytes[-byte_limit:].decode("utf-8", errors="replace").splitlines()
    elif tail:
        omitted_bytes = len("\n".join(tail).encode("utf-8"))
        tail = []

    if omitted_lines:
        notes.append(f"Tail-limited {label} to last {len(tail)} of {len(lines)} line(s).")
    if omitted_bytes:
        notes.append(f"Tail-limited {label} to last {byte_limit} byte(s) of selected log text.")
    return TaskPacketLog(
        path=_relative(repo_root, path),
        tail=tail,
        line_count=len(lines),
        omitted_lines=omitted_lines,
        omitted_bytes=omitted_bytes,
        truncated=omitted_lines > 0 or omitted_bytes > 0,
    )


def _constraints(virtual_workspace_path: str) -> list[str]:
    return [
        "Task packets are derived read-only projections, not state stores.",
        "task.yaml, events.jsonl, verification.json, worker.log, and verify.log remain canonical.",
        "summary.json is derived/cache only and cannot override canonical state.",
        f"Worker execution must stay inside {virtual_workspace_path}.",
        "Dev-Flow owns verification, merge readiness, and human approval gates.",
    ]


def _allowed_artifacts(repo_root: Path, task_path: Path) -> list[str]:
    candidates = [
        task_path / "task.yaml",
        task_path / "events.jsonl",
        task_path / "verification.json",
        task_path / "logs" / "worker.log",
        task_path / "logs" / "verify.log",
    ]
    return [_relative(repo_root, path) for path in candidates if path.exists()]





def _normalize_to_posix(path_str: str) -> str:
    if path_str.startswith("file://"):
        path_str = path_str[7:]

    # Check for Windows path start (e.g. C:\... or similar) or backslashes
    if "\\" in path_str or (len(path_str) > 1 and path_str[1] == ":" and path_str[0].isalpha()):
        from pathlib import PureWindowsPath
        pure = PureWindowsPath(path_str)
        parts = list(pure.parts)
        if parts and len(parts[0]) > 1 and parts[0][1] == ":" and parts[0][0].isalpha():
            parts[0] = "/"
        path_str = "/".join(parts)
        import re
        path_str = re.sub(r'/+', '/', path_str)
    else:
        path_str = path_str.replace("\\", "/")
    return path_str


def _virtualize_path(path_str: str | None, repo_root: Path, task_id: str, workspace_path: Path | None = None) -> str | None:
    if path_str is None:
        return None
    if not isinstance(path_str, str) or not path_str.strip():
        return path_str

    if path_str.startswith("<workspace>") or path_str.startswith("<task>") or path_str.startswith("<devflow>"):
        return path_str

    normalized = _normalize_to_posix(path_str)

    try:
        p = Path(normalized)
        if not p.is_absolute():
            abs_p = (repo_root / p).resolve()
        else:
            abs_p = p.resolve()
    except Exception:
        abs_p = None

    resolved_repo = repo_root.resolve()
    resolved_task = (resolved_repo / ".devflow" / "tasks" / task_id).resolve()
    resolved_workspace = (workspace_path or (resolved_repo / ".devflow" / "workspaces" / task_id)).resolve()
    resolved_devflow = (resolved_repo / ".devflow").resolve()

    if abs_p is not None:
        try:
            rel = abs_p.relative_to(resolved_task)
            return f"<task>/{rel.as_posix()}"
        except ValueError:
            pass

        try:
            rel = abs_p.relative_to(resolved_workspace)
            return f"<workspace>/{rel.as_posix()}" if rel.as_posix() != "." else "<workspace>"
        except ValueError:
            pass

        try:
            rel = abs_p.relative_to(resolved_devflow)
            return f"<devflow>/{rel.as_posix()}" if rel.as_posix() != "." else "<devflow>"
        except ValueError:
            pass

        try:
            rel = abs_p.relative_to(resolved_repo)
            return rel.as_posix()
        except ValueError:
            pass

    task_rel_prefix = f".devflow/tasks/{task_id}"
    workspace_rel_prefix = f".devflow/workspaces/{task_id}"
    devflow_rel_prefix = ".devflow"

    clean_norm = normalized.lstrip("/")
    if clean_norm.startswith("./"):
        clean_norm = clean_norm[2:]

    if clean_norm == task_rel_prefix:
        return "<task>"
    elif clean_norm.startswith(task_rel_prefix + "/"):
        return f"<task>/{clean_norm[len(task_rel_prefix)+1:]}"
    elif clean_norm == workspace_rel_prefix:
        return "<workspace>"
    elif clean_norm.startswith(workspace_rel_prefix + "/"):
        return f"<workspace>/{clean_norm[len(workspace_rel_prefix)+1:]}"
    elif clean_norm == devflow_rel_prefix:
        return "<devflow>"
    elif clean_norm.startswith(devflow_rel_prefix + "/"):
        return f"<devflow>/{clean_norm[len(devflow_rel_prefix)+1:]}"

    # Scrub potential absolute OS secrets/user paths
    import re
    scrubbed = normalized
    scrubbed = re.sub(r'^[a-zA-Z]:/', '', scrubbed)
    scrubbed = re.sub(r'^/Users/[^/]+', '<home>', scrubbed)
    scrubbed = re.sub(r'^/home/[^/]+', '<home>', scrubbed)
    scrubbed = re.sub(r'^/tmp', '<temp>', scrubbed)
    scrubbed = re.sub(r'^/private/var/folders/[^/]+/[^/]+/[^/]+', '<temp>', scrubbed)
    scrubbed = re.sub(r'^/var/folders/[^/]+/[^/]+/[^/]+', '<temp>', scrubbed)

    scrubbed = re.sub(r'/+', '/', scrubbed)
    if scrubbed.startswith('/'):
        scrubbed = scrubbed.lstrip('/')
    return scrubbed


def _is_sensitive_key(key: str) -> bool:
    if not isinstance(key, str):
        return False
    # Tight matching to avoid false positives on words like monkey, keyboard, keynote, etc.
    # Matches:
    # 1. Standalone secret words: key, token, secret, password, passwd, authorization, apikey
    # 2. Key names ending with _key, _token, _secret, _password, _passwd
    # 3. Key names starting with key_, token_, secret_, password_, passwd_
    # 4. Standalone combinations: api_key, access_key, secret_key, access_token, refresh_token, auth_token
    pattern = r'(?i)^_*(?:key|token|secret|password|passwd|authorization|apikey|api_?key|access_?key|secret_?key|access_?token|refresh_?token|auth_?token|\w+(?:_key|_token|_secret|_password|_passwd)|(?:key|token|secret|password|passwd)_\w+)_*$'
    return bool(re.match(pattern, key))


def _redact_string(text: str) -> str:
    if not isinstance(text, str):
        return text

    # 1. Bearer <token>
    text = re.sub(r'(?i)\bbearer\s+\S+', 'Bearer [REDACTED]', text)

    # 2. Authorization: <token>
    text = re.sub(r'(?i)\bauthorization\s*:\s*(?!\s*bearer\b)[^\r\n]+', 'Authorization: [REDACTED]', text)

    # 3. .env and JSON/YAML style: KEY="value" or "KEY": "value"
    def repl_quoted(match):
        key = match.group(2)
        if _is_sensitive_key(key):
            return f"{match.group(1)}{match.group(2)}{match.group(1)}{match.group(3)}{match.group(4)}{match.group(5)}[REDACTED]{match.group(5)}"
        return match.group(0)

    text = re.sub(
        r'(?i)(["\']?)\b(\w+)\1\s*([=:])(\s*)(["\'])(.*?)\5',
        repl_quoted,
        text
    )

    # 4. .env style: KEY=value or "KEY": value
    def repl_unquoted(match):
        key = match.group(2)
        val = match.group(5)
        if _is_sensitive_key(key) and val != "[REDACTED]":
            return f"{match.group(1)}{match.group(2)}{match.group(1)}{match.group(3)}{match.group(4)}[REDACTED]"
        return match.group(0)

    text = re.sub(
        r'(?i)(["\']?)\b(\w+)\1\s*([=:])(\s*)([^\s"\'`]+)',
        repl_unquoted,
        text
    )

    # 5. OpenAI sk-... keys
    text = re.sub(r'\bsk-(?:proj-)?[a-zA-Z0-9_-]{12,}\b', '[REDACTED]', text)

    # 6. GitHub ghp_... and other tokens
    text = re.sub(r'\b(?:gh[pousr]_[a-zA-Z0-9]{20,}|github_pat_[a-zA-Z0-9_]{20,})\b', '[REDACTED]', text)

    # 7. Private key blocks
    text = re.sub(
        r'(?s)-----BEGIN\s+(?:[A-Z0-9\s_-]+\s+)?PRIVATE\s+KEY-----.*?-----END\s+(?:[A-Z0-9\s_-]+\s+)?PRIVATE\s+KEY-----',
        '[REDACTED PRIVATE KEY]',
        text
    )
    text = re.sub(r'-----BEGIN\s+(?:[A-Z0-9\s_-]+\s+)?PRIVATE\s+KEY-----', '[REDACTED PRIVATE KEY HEADER]', text)
    text = re.sub(r'-----END\s+(?:[A-Z0-9\s_-]+\s+)?PRIVATE\s+KEY-----', '[REDACTED PRIVATE KEY FOOTER]', text)

    return text


def _redact_secrets_in_value(val: Any, is_under_sensitive_key: bool = False) -> Any:
    if isinstance(val, str):
        if is_under_sensitive_key:
            return "[REDACTED]"
        return _redact_string(val)
    elif isinstance(val, list):
        return [_redact_secrets_in_value(item, is_under_sensitive_key) for item in val]
    elif isinstance(val, dict):
        updated = {}
        for k, v in val.items():
            sensitive_child = is_under_sensitive_key or _is_sensitive_key(k)
            if sensitive_child:
                if isinstance(v, str):
                    updated[k] = "[REDACTED]"
                else:
                    updated[k] = _redact_secrets_in_value(v, is_under_sensitive_key=True)
            else:
                updated[k] = _redact_secrets_in_value(v, is_under_sensitive_key=False)
        return updated
    elif isinstance(val, BaseModel):
        updated = {}
        for field_name in type(val).model_fields:
            field_val = getattr(val, field_name)
            sensitive_child = is_under_sensitive_key or _is_sensitive_key(field_name)
            if sensitive_child:
                if isinstance(field_val, str):
                    updated[field_name] = "[REDACTED]"
                else:
                    updated[field_name] = _redact_secrets_in_value(field_val, is_under_sensitive_key=True)
            else:
                updated[field_name] = _redact_secrets_in_value(field_val, is_under_sensitive_key=False)
        return val.model_copy(update=updated)
    return val
