from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from devflow.control_room.models import TaskRecord
from devflow.control_room.paths import task_dir
from devflow.control_room.service import get_task


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
    task = get_task(repo_root, task_id)
    task_path = task_dir(repo_root, task_id)
    notes: list[str] = []

    summary_data = _read_matching_summary(task_path / "summary.json", task, notes)
    recent_events, omitted_events, malformed_events = _read_recent_events(task_path / "events.jsonl", packet_limits.recent_events_limit, notes)
    verification = _read_verification(task_path / "verification.json", task, notes)
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

    return TaskPacket(
        task_id=task.id,
        title=task.title,
        status=task.status,
        adapter=adapter,
        workspace_path=task.workspace_path or task.workspace,
        worker_adapter=adapter,
        task=task.model_dump(mode="json"),
        summary=_packet_summary(task, summary_data),
        recent_events=recent_events,
        verification=verification,
        derived_summary=summary_data or None,
        result_summary=None,
        logs={"worker": worker_log, "verify": verify_log},
        constraints=_constraints(task),
        allowed_artifacts=_allowed_artifacts(repo_root, task_path),
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
        "task_id",
        "title",
        "status",
        "workspace_path",
        "workspace_dirty",
        "workspace_branch",
        "workspace_commit",
        "latest_verification_status",
        "latest_verification_exit_code",
        "latest_verification_log_path",
        "merge_ready",
        "merge_readiness_reasons",
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


def _read_verification(path: Path, task: TaskRecord, notes: list[str]) -> dict[str, Any]:
    fallback = {
        "task_id": task.id,
        "status": task.verification_status,
        "task_status": task.status,
        "exit_code": task.verification_exit_code,
        "log_path": task.verification_log_path,
        "command": task.verification_command,
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
    return data


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

    lines = raw.decode("utf-8", errors="replace").splitlines()
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


def _constraints(task: TaskRecord) -> list[str]:
    return [
        "Task packets are derived read-only projections, not state stores.",
        "task.yaml, events.jsonl, verification.json, worker.log, and verify.log remain canonical.",
        "summary.json is derived/cache only and cannot override canonical state.",
        f"Worker execution must stay inside {task.workspace_path or task.workspace}.",
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


def _relative(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()