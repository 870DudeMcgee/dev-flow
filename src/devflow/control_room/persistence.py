from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from devflow.control_room.models import TASK_SCHEMA_VERSION, TaskRecord
from devflow.control_room.paths import (
    absolute_path,
    relative_path,
    system_events_path,
    task_dir,
    tasks_dir,
)
from devflow.control_room.log_sanitizer import DEFAULT_LATEST_LOG_LINE_MAX_CHARS, sanitize_log_line
from devflow.control_room.readiness import readiness_state


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def timestamp() -> str:
    return utc_now().isoformat()


def get_task(root: Path, task_id: str) -> TaskRecord:
    path = task_dir(root, task_id)
    if not (path / "task.yaml").exists():
        raise KeyError(f"Task not found: {task_id}")
    return load_task(path)


def list_tasks(root: Path) -> list[TaskRecord]:
    if not tasks_dir(root).exists():
        return []
    records = []
    for path in sorted(tasks_dir(root).iterdir()):
        if path.is_dir() and (path / "task.yaml").exists():
            records.append(load_task(path))
    return records


def save_task(task_path: Path, task: TaskRecord) -> None:
    """Write task artifacts only; lifecycle transitions belong in task_lifecycle."""
    values = {
        "schema_version": task.schema_version,
        "id": task.id,
        "title": task.title,
        "definition_of_done": task.definition_of_done,
        "status": task.status,
        "created_at": task.created_at.isoformat(),
        "updated_at": task.updated_at.isoformat(),
        "workspace": task.workspace,
        "workspace_path": task.workspace_path,
        "workspace_kind": task.workspace_kind,
        "worker": task.worker,
        "worker_adapter": task.worker_adapter,
        "last_event": task.last_event,
        "last_exit_code": task.last_exit_code,
        "verification_status": task.verification_status,
        "latest_log_line": _stored_latest_log_line(task.latest_log_line),
        "log_path": task.log_path,
        "result_path": task.result_path,
        "worker_command": task.worker_command,
        "verification_command": task.verification_command,
        "verification_exit_code": task.verification_exit_code,
        "verification_log_path": task.verification_log_path,
        "timeout_seconds": task.timeout_seconds,
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "finished_at": task.finished_at.isoformat() if task.finished_at else None,
        "branch_name": task.branch_name,
        "workspace_commit": task.workspace_commit,
        "workspace_dirty": task.workspace_dirty,
        "close_outcome": task.close_outcome,
        "close_reason": task.close_reason,
        "closed_at": task.closed_at.isoformat() if task.closed_at else None,
    }
    key_order = [
        "schema_version",
        "id",
        "title",
        "definition_of_done",
        "status",
        "created_at",
        "updated_at",
        "workspace",
        "workspace_path",
        "workspace_kind",
        "worker",
        "worker_adapter",
        "last_event",
        "last_exit_code",
        "verification_status",
        "latest_log_line",
        "log_path",
        "result_path",
        "worker_command",
        "verification_command",
        "verification_exit_code",
        "verification_log_path",
        "timeout_seconds",
        "started_at",
        "finished_at",
        "branch_name",
        "workspace_commit",
        "workspace_dirty",
        "close_outcome",
        "close_reason",
        "closed_at",
    ]
    lines = [f"{key}: {_yaml_scalar(values[key])}" for key in key_order]
    task_path.mkdir(parents=True, exist_ok=True)
    atomic_write_text(task_path / "task.yaml", "\n".join(lines) + "\n")
    _write_task_summary(task_path, task)


def atomic_write_text(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding=encoding,
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            temporary_file.write(text)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_path, path)
        _fsync_directory(path.parent)
    except Exception:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
        raise


def load_task(task_path: Path) -> TaskRecord:
    data = _read_yaml_scalars(task_path / "task.yaml")
    schema_version = data.get("schema_version", TASK_SCHEMA_VERSION)
    if schema_version != TASK_SCHEMA_VERSION:
        raise ValueError(
            f"unsupported task.yaml schema_version {schema_version}; supported: {TASK_SCHEMA_VERSION}"
        )
    data["schema_version"] = schema_version
    required = ["id", "title", "status", "created_at", "updated_at", "workspace", "worker", "verification_status"]
    missing = [key for key in required if key not in data]
    if missing:
        raise ValueError(f"missing keys in {task_path / 'task.yaml'}: {', '.join(missing)}")
    for key in ("created_at", "updated_at", "started_at", "finished_at", "closed_at"):
        if data.get(key):
            data[key] = datetime.fromisoformat(str(data[key]))
    return TaskRecord(**data)


def append_event(root: Path, task_id: str, event_type: str, payload: dict[str, Any]) -> None:
    task_events = task_dir(root, task_id) / "events.jsonl"
    previous_hash, next_index = _event_chain_tail(task_events)
    event = {
        "timestamp": timestamp(),
        "task_id": task_id,
        "event": event_type,
        "event_index": next_index,
        "previous_event_hash": previous_hash,
        **payload,
    }
    event["event_hash"] = event_content_hash(event)
    line = json.dumps(event, sort_keys=True) + "\n"
    task_events.parent.mkdir(parents=True, exist_ok=True)
    with task_events.open("a", encoding="utf-8") as handle:
        handle.write(line)
        handle.flush()
        try:
            os.fsync(handle.fileno())
        except OSError:
            pass
    _fsync_directory(task_events.parent)

    system_events_path(root).parent.mkdir(parents=True, exist_ok=True)
    with system_events_path(root).open("a", encoding="utf-8") as handle:
        handle.write(line)
        handle.flush()
        try:
            os.fsync(handle.fileno())
        except OSError:
            pass
    _fsync_directory(system_events_path(root).parent)


def event_content_hash(event: dict[str, Any]) -> str:
    canonical_event = {key: value for key, value in event.items() if key != "event_hash"}
    payload = json.dumps(canonical_event, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def validate_event_log(path: Path) -> tuple[bool, str]:
    if not path.exists():
        return False, "missing events.jsonl"

    previous_hash: str | None = None
    expected_index = 0
    legacy_events = 0
    hash_chain_started = False

    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw_line.strip():
            continue
        try:
            event = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            return False, f"line {line_number}: malformed JSON ({exc.msg})"
        if not isinstance(event, dict):
            return False, f"line {line_number}: event must be a JSON object"

        event_hash = event.get("event_hash")
        if event_hash is None:
            if hash_chain_started:
                return False, f"line {line_number}: unhashed event after hash chain started"
            legacy_events += 1
            previous_hash = event_content_hash(event)
            expected_index += 1
            continue

        hash_chain_started = True
        if event.get("event_index") != expected_index:
            return False, f"line {line_number}: event_index {event.get('event_index')} != expected {expected_index}"
        if event.get("previous_event_hash") != previous_hash:
            return False, f"line {line_number}: previous_event_hash does not match prior event"
        expected_hash = event_content_hash(event)
        if event_hash != expected_hash:
            return False, f"line {line_number}: event_hash mismatch"

        previous_hash = event_hash
        expected_index += 1

    if expected_index == 0:
        return True, "empty event log"
    if legacy_events:
        return True, f"{expected_index} event(s), {legacy_events} legacy unhashed, hash chain valid"
    return True, f"{expected_index} event(s), hash chain valid"


def _event_chain_tail(path: Path) -> tuple[str | None, int]:
    if not path.exists():
        return None, 0

    previous_hash: str | None = None
    next_index = 0
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        if not raw_line.strip():
            continue
        try:
            event = json.loads(raw_line)
        except json.JSONDecodeError:
            break
        if not isinstance(event, dict):
            break
        previous_hash = event.get("event_hash") or event_content_hash(event)
        next_index += 1
    return previous_hash, next_index


def _write_task_summary(task_path: Path, task: TaskRecord) -> None:
    ready, reasons = readiness_state(task, task_path)

    payload = {
        "schema_version": TASK_SCHEMA_VERSION,
        "task_id": task.id,
        "title": task.title,
        "definition_of_done": task.definition_of_done,
        "status": task.status,
        "workspace_path": task.workspace_path,
        "workspace_dirty": task.workspace_dirty if task.workspace_dirty is not None else False,
        "workspace_branch": task.branch_name,
        "workspace_commit": task.workspace_commit,
        "latest_verification_status": task.verification_status,
        "latest_verification_exit_code": task.verification_exit_code,
        "latest_verification_log_path": task.verification_log_path,
        "merge_ready": ready,
        "merge_readiness_reasons": reasons,
        "updated_at": task.updated_at.isoformat(),
    }
    atomic_write_text(task_path / "summary.json", json.dumps(payload, indent=2) + "\n")


def _fsync_directory(directory: Path) -> None:
    try:
        directory_fd = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(directory_fd)
    except OSError:
        pass
    finally:
        try:
            os.close(directory_fd)
        except OSError:
            pass


def _read_yaml_scalars(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            raise ValueError(f"invalid task.yaml line: {line}")
        key, value = line.split(":", 1)
        data[key.strip()] = _parse_yaml_scalar(value.strip())
    return data


def _yaml_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    return json.dumps(str(value))


def _stored_latest_log_line(value: str | None) -> str | None:
    if value is None:
        return None
    sanitized = sanitize_log_line(value, max_chars=DEFAULT_LATEST_LOG_LINE_MAX_CHARS)
    return sanitized or None


def _parse_yaml_scalar(value: str) -> Any:
    if value == "null":
        return None
    if value == "true":
        return True
    if value == "false":
        return False
    if value.startswith('"'):
        return json.loads(value)
    try:
        return int(value)
    except ValueError:
        return value
