from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from devflow.control_room.models import TaskRecord
from devflow.control_room.paths import task_dir
from devflow.control_room.service import get_task


class TaskPacketLimits(BaseModel):
    max_recent_events: int = Field(default=10, ge=0)
    log_tail_lines: int = Field(default=40, ge=0)


class TaskPacketLog(BaseModel):
    path: str
    tail: list[str]
    line_count: int
    omitted_lines: int
    truncated: bool


class TaskPacket(BaseModel):
    task_id: str
    title: str
    status: str
    workspace_path: str
    worker_adapter: str
    summary: str | None
    recent_events: list[dict[str, Any]]
    verification: dict[str, Any]
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
    recent_events, omitted_events = _read_recent_events(task_path / "events.jsonl", packet_limits.max_recent_events, notes)
    verification = _read_verification(task_path / "verification.json", task, notes)
    worker_log, omitted_worker_lines = _tail_log(repo_root, task_path / "logs" / "worker.log", "worker.log", packet_limits.log_tail_lines, notes)
    verify_log, omitted_verify_lines = _tail_log(repo_root, task_path / "logs" / "verify.log", "verify.log", packet_limits.log_tail_lines, notes)

    return TaskPacket(
        task_id=task.id,
        title=task.title,
        status=task.status,
        workspace_path=task.workspace_path or task.workspace,
        worker_adapter=task.worker_adapter or task.worker,
        summary=_packet_summary(task, summary_data),
        recent_events=recent_events,
        verification=verification,
        result_summary=None,
        logs={"worker": worker_log, "verify": verify_log},
        constraints=_constraints(task),
        allowed_artifacts=_allowed_artifacts(repo_root, task_path),
        omitted_counts={
            "events": omitted_events,
            "worker_log_lines": omitted_worker_lines,
            "verify_log_lines": omitted_verify_lines,
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
    return data


def _packet_summary(task: TaskRecord, summary_data: dict[str, Any]) -> str:
    summary = summary_data.get("summary")
    if isinstance(summary, str) and summary.strip():
        return summary.strip()
    return f"{task.id} {task.status}: {task.title}"


def _read_recent_events(path: Path, limit: int, notes: list[str]) -> tuple[list[dict[str, Any]], int]:
    if not path.exists():
        return [], 0
    events: list[dict[str, Any]] = []
    malformed_lines = 0
    for line in path.read_text(encoding="utf-8").splitlines():
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
    return recent_events, omitted_events


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


def _tail_log(repo_root: Path, path: Path, label: str, limit: int, notes: list[str]) -> tuple[TaskPacketLog, int]:
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    omitted_lines = max(len(lines) - limit, 0)
    tail = lines[-limit:] if limit else []
    if omitted_lines:
        notes.append(f"Tail-limited {label} to last {len(tail)} of {len(lines)} line(s).")
    return (
        TaskPacketLog(
            path=_relative(repo_root, path),
            tail=tail,
            line_count=len(lines),
            omitted_lines=omitted_lines,
            truncated=omitted_lines > 0,
        ),
        omitted_lines,
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