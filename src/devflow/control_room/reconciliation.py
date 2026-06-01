from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from devflow.control_room.locks import TASK_LOCK_STALE_AFTER_SECONDS
from devflow.control_room.models import TaskRecord
from devflow.control_room.paths import relative_path, system_events_path, task_dir, tasks_dir
from devflow.control_room.persistence import load_task, validate_event_log


RECONCILIATION_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class ParsedEvent:
    payload: dict[str, Any]
    line_number: int


def build_reconciliation_report(root: Path, task_id: str | None = None) -> dict[str, Any]:
    repo_root = root.resolve()
    findings: list[dict[str, Any]] = []
    system_events = _read_events(repo_root, system_events_path(repo_root), "system", None, findings)
    system_events_by_task = _events_by_task(system_events)

    task_paths = [task_dir(repo_root, task_id)] if task_id else _task_paths(repo_root)
    tasks_checked = 0
    for task_path in task_paths:
        if not task_path.is_dir():
            findings.append(
                _finding(
                    repo_root,
                    code="task_missing",
                    severity="error",
                    detail=f"task directory not found: {task_path.name}",
                    path=task_path,
                    task_id=task_path.name,
                    next_action="Confirm the task id or inspect .devflow/tasks for orphaned state.",
                )
            )
            continue

        tasks_checked += 1
        try:
            task = load_task(task_path)
        except Exception as exc:
            findings.append(
                _finding(
                    repo_root,
                    code="task_yaml_unreadable",
                    severity="error",
                    detail=str(exc),
                    path=task_path / "task.yaml",
                    task_id=task_path.name,
                    next_action="Inspect task.yaml and recover from durable task artifacts before running mutations.",
                )
            )
            continue

        task_events_path = task_path / "events.jsonl"
        task_events = _read_events(repo_root, task_events_path, "task", task.id, findings)
        _check_task_event_integrity(repo_root, task, task_events_path, findings)
        _check_task_system_divergence(
            repo_root,
            task,
            task_events,
            system_events_by_task.get(task.id, []),
            findings,
        )
        _check_lifecycle_consistency(repo_root, task, task_path, task_events, findings)
        _check_promotion_consistency(repo_root, task, task_path, task_events, findings)
        _check_artifacts(repo_root, task, task_path, findings)

    return {
        "schema_version": RECONCILIATION_SCHEMA_VERSION,
        "status": "issues_found" if findings else "ok",
        "tasks_checked": tasks_checked,
        "findings": findings,
    }


def _task_paths(root: Path) -> list[Path]:
    directory = tasks_dir(root)
    if not directory.exists():
        return []
    return sorted(path for path in directory.iterdir() if path.is_dir())


def _read_events(
    root: Path,
    path: Path,
    scope: str,
    task_id: str | None,
    findings: list[dict[str, Any]],
) -> list[ParsedEvent]:
    if not path.exists():
        code = "system_event_log_missing" if scope == "system" else "task_event_log_missing"
        findings.append(
            _finding(
                root,
                code=code,
                severity="error",
                detail=f"missing {path.name}",
                path=path,
                task_id=task_id,
                next_action="Inspect the control-room artifacts before running repair or mutation commands.",
            )
        )
        return []

    events: list[ParsedEvent] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw_line.strip():
            continue
        try:
            event = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            code = "partial_system_event_write" if scope == "system" else "partial_task_event_write"
            findings.append(
                _finding(
                    root,
                    code=code,
                    severity="error",
                    detail=f"line {line_number}: malformed JSON ({exc.msg})",
                    path=path,
                    task_id=task_id,
                    next_action="Treat this as crash/interruption evidence; inspect adjacent events before modifying task state.",
                )
            )
            continue
        if not isinstance(event, dict):
            code = "partial_system_event_write" if scope == "system" else "partial_task_event_write"
            findings.append(
                _finding(
                    root,
                    code=code,
                    severity="error",
                    detail=f"line {line_number}: event must be a JSON object",
                    path=path,
                    task_id=task_id,
                    next_action="Inspect the malformed event line before modifying task state.",
                )
            )
            continue
        events.append(ParsedEvent(payload=event, line_number=line_number))
    return events


def _check_task_event_integrity(
    root: Path,
    task: TaskRecord,
    events_path: Path,
    findings: list[dict[str, Any]],
) -> None:
    ok, detail = validate_event_log(events_path)
    if ok:
        return
    findings.append(
        _finding(
            root,
            code="task_event_log_invalid",
            severity="error",
            detail=detail,
            path=events_path,
            task_id=task.id,
            next_action="Inspect the task event log before trusting derived status or running repair.",
        )
    )


def _check_task_system_divergence(
    root: Path,
    task: TaskRecord,
    task_events: list[ParsedEvent],
    system_events: list[ParsedEvent],
    findings: list[dict[str, Any]],
) -> None:
    system_signatures = {_event_signature(event.payload) for event in system_events}
    task_signatures = {_event_signature(event.payload) for event in task_events}

    for task_event in task_events:
        if _event_signature(task_event.payload) in system_signatures:
            continue
        findings.append(
            _finding(
                root,
                code="task_event_missing_from_system",
                severity="error",
                detail=_event_detail(task_event, "task event is absent from system events"),
                path=task_dir(root, task.id) / "events.jsonl",
                task_id=task.id,
                next_action="Compare task and system logs before replaying or repairing event state.",
            )
        )

    for system_event in system_events:
        if _event_signature(system_event.payload) in task_signatures:
            continue
        findings.append(
            _finding(
                root,
                code="system_event_missing_from_task",
                severity="error",
                detail=_event_detail(system_event, "system event is absent from task events"),
                path=system_events_path(root),
                task_id=task.id,
                next_action="Compare task and system logs before replaying or repairing event state.",
            )
        )


def _check_lifecycle_consistency(
    root: Path,
    task: TaskRecord,
    task_path: Path,
    events: list[ParsedEvent],
    findings: list[dict[str, Any]],
) -> None:
    last_event = events[-1] if events else None
    if task.last_event and last_event is not None and task.last_event != last_event.payload.get("event"):
        findings.append(
            _finding(
                root,
                code="task_last_event_mismatch",
                severity="warning",
                detail=f"task.yaml last_event is {task.last_event!r}, latest event is {last_event.payload.get('event')!r}",
                path=task_path / "task.yaml",
                task_id=task.id,
                next_action="Use task.yaml as current state but inspect events before reconciling history.",
            )
        )

    if _last_index(events, "worker_started") > _last_index(events, "worker_finished"):
        findings.append(
            _finding(
                root,
                code="worker_interrupted",
                severity="error",
                detail="worker_started has no later worker_finished event",
                path=task_path / "events.jsonl",
                task_id=task.id,
                next_action="Inspect worker.log and the task lock before deciding whether to rerun the task.",
            )
        )

    if _last_index(events, "verification_started") > _last_index(events, "verification_finished"):
        findings.append(
            _finding(
                root,
                code="verification_interrupted",
                severity="error",
                detail="verification_started has no later verification_finished event",
                path=task_path / "events.jsonl",
                task_id=task.id,
                next_action="Inspect verify.log before deciding whether to rerun verification.",
            )
        )

    if task.started_at is not None and task.finished_at is None and task.status not in {"running", "created"}:
        findings.append(
            _finding(
                root,
                code="task_timestamps_inconsistent",
                severity="warning",
                detail=f"status {task.status!r} has started_at but no finished_at",
                path=task_path / "task.yaml",
                task_id=task.id,
                next_action="Inspect task.yaml and event history before trusting terminal status.",
            )
        )


def _check_promotion_consistency(
    root: Path,
    task: TaskRecord,
    task_path: Path,
    events: list[ParsedEvent],
    findings: list[dict[str, Any]],
) -> None:
    promoted_events = [event for event in events if event.payload.get("event") == "task_promoted"]
    if task.status == "promoted" and not promoted_events:
        findings.append(
            _finding(
                root,
                code="promotion_status_missing_event",
                severity="error",
                detail="task.yaml status is promoted but events.jsonl has no task_promoted event",
                path=task_path / "events.jsonl",
                task_id=task.id,
                next_action="Inspect main checkout changes and promotion evidence before treating the task as fully promoted.",
            )
        )
    if promoted_events and task.status != "promoted":
        findings.append(
            _finding(
                root,
                code="promotion_event_status_mismatch",
                severity="error",
                detail=f"events.jsonl contains task_promoted but task.yaml status is {task.status!r}",
                path=task_path / "task.yaml",
                task_id=task.id,
                next_action="Inspect promotion output and task.yaml before running further mutation commands.",
            )
        )
    if task.status == "promoted" and task.verification_status != "passed":
        findings.append(
            _finding(
                root,
                code="promotion_verification_inconsistent",
                severity="error",
                detail=f"promoted task verification_status is {task.verification_status!r}, expected 'passed'",
                path=task_path / "task.yaml",
                task_id=task.id,
                next_action="Inspect verification.json and promotion history before relying on promoted state.",
            )
        )

    lock_owner = task_path / ".lock" / "owner.json"
    if not lock_owner.exists():
        return
    payload, detail = _read_json_object(lock_owner)
    if payload is None:
        findings.append(
            _finding(
                root,
                code="task_lock_unreadable",
                severity="error",
                detail=detail,
                path=lock_owner,
                task_id=task.id,
                next_action="Inspect the lock owner before running task mutations.",
            )
        )
        return
    if payload.get("operation") == "promote":
        findings.append(
            _finding(
                root,
                code="promotion_interrupted_lock",
                severity="error",
                detail=_lock_detail(payload),
                path=lock_owner,
                task_id=task.id,
                next_action="Inspect copied files and promotion output before removing the lock or retrying promotion.",
            )
        )


def _check_artifacts(root: Path, task: TaskRecord, task_path: Path, findings: list[dict[str, Any]]) -> None:
    _check_summary_json(root, task, task_path, findings)
    _check_verification_json(root, task, task_path, findings)
    _check_merge_readiness_json(root, task, task_path, findings)
    _check_declared_file(root, task, task_path, task.log_path, "log_path", findings)
    _check_declared_file(root, task, task_path, task.result_path, "result_path", findings)
    _check_declared_file(root, task, task_path, task.verification_log_path, "verification_log_path", findings)


def _check_summary_json(root: Path, task: TaskRecord, task_path: Path, findings: list[dict[str, Any]]) -> None:
    path = task_path / "summary.json"
    if not path.exists():
        return
    payload, detail = _read_json_object(path)
    if payload is None:
        _add_artifact_finding(root, task, path, detail, findings)
        return
    if payload.get("task_id") not in (None, task.id):
        _add_artifact_finding(root, task, path, "task_id does not match task.yaml", findings)
    if payload.get("status") not in (None, task.status):
        _add_artifact_finding(root, task, path, "status does not match task.yaml", findings)


def _check_verification_json(root: Path, task: TaskRecord, task_path: Path, findings: list[dict[str, Any]]) -> None:
    path = task_path / "verification.json"
    if not path.exists():
        findings.append(
            _finding(
                root,
                code="artifact_missing",
                severity="error",
                detail="verification.json is missing",
                path=path,
                task_id=task.id,
                next_action="Inspect task artifacts before relying on verification state.",
            )
        )
        return
    payload, detail = _read_json_object(path)
    if payload is None:
        _add_artifact_finding(root, task, path, detail, findings)
        return
    if payload.get("task_id") not in (None, task.id):
        _add_artifact_finding(root, task, path, "task_id does not match task.yaml", findings)

    verification_task_status = payload.get("task_status")
    if _verification_task_status_should_match(task):
        expected_statuses = {task.status}
        if task.status == "promoted":
            expected_statuses.add("verified")
        if verification_task_status not in expected_statuses:
            _add_artifact_finding(root, task, path, "task_status does not match task.yaml", findings)
    if task.verification_status != "not_run" and payload.get("status") not in (None, task.verification_status):
        _add_artifact_finding(root, task, path, "status does not match task.yaml verification_status", findings)


def _check_merge_readiness_json(root: Path, task: TaskRecord, task_path: Path, findings: list[dict[str, Any]]) -> None:
    path = task_path / "merge-readiness.json"
    if not path.exists():
        return
    payload, detail = _read_json_object(path)
    if payload is None:
        _add_artifact_finding(root, task, path, detail, findings)
        return
    if payload.get("task_id") not in (None, task.id):
        _add_artifact_finding(root, task, path, "task_id does not match task.yaml", findings)
    if not isinstance(payload.get("ready"), bool):
        _add_artifact_finding(root, task, path, "ready must be boolean", findings)


def _check_declared_file(
    root: Path,
    task: TaskRecord,
    task_path: Path,
    path_text: str | None,
    field_name: str,
    findings: list[dict[str, Any]],
) -> None:
    if not path_text:
        return
    declared_path = root / path_text
    if declared_path.exists():
        return
    findings.append(
        _finding(
            root,
            code="artifact_missing",
            severity="warning",
            detail=f"task.yaml {field_name} points to a missing file",
            path=task_path / "task.yaml",
            task_id=task.id,
            next_action="Inspect task.yaml and artifact paths before relying on this status projection.",
        )
    )


def _events_by_task(events: list[ParsedEvent]) -> dict[str, list[ParsedEvent]]:
    by_task: dict[str, list[ParsedEvent]] = {}
    for event in events:
        task_id = event.payload.get("task_id")
        if isinstance(task_id, str) and task_id:
            by_task.setdefault(task_id, []).append(event)
    return by_task


def _event_signature(event: dict[str, Any]) -> str:
    event_hash = event.get("event_hash")
    if isinstance(event_hash, str) and event_hash:
        return f"hash:{event_hash}"
    return "json:" + json.dumps(event, sort_keys=True, separators=(",", ":"), default=str)


def _event_detail(event: ParsedEvent, suffix: str) -> str:
    event_name = event.payload.get("event") or "unknown"
    event_index = event.payload.get("event_index")
    if event_index is None:
        return f"line {event.line_number}: {event_name}: {suffix}"
    return f"line {event.line_number}: {event_name} index {event_index}: {suffix}"


def _last_index(events: list[ParsedEvent], event_name: str) -> int:
    for index in range(len(events) - 1, -1, -1):
        if events[index].payload.get("event") == event_name:
            return index
    return -1


def _verification_task_status_should_match(task: TaskRecord) -> bool:
    return task.status in {"verified", "verification_failed", "promoted"} or task.verification_status != "not_run"


def _read_json_object(path: Path) -> tuple[dict[str, Any] | None, str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON: {exc.msg}"
    except OSError as exc:
        return None, f"unreadable: {exc}"
    if not isinstance(payload, dict):
        return None, "invalid JSON: expected object"
    return payload, str(path)


def _add_artifact_finding(
    root: Path,
    task: TaskRecord,
    path: Path,
    detail: str,
    findings: list[dict[str, Any]],
) -> None:
    findings.append(
        _finding(
            root,
            code="artifact_inconsistent",
            severity="error",
            detail=f"{path.name}: {detail}",
            path=path,
            task_id=task.id,
            next_action="Treat task.yaml as canonical, then inspect the stale or malformed derived artifact.",
        )
    )


def _lock_detail(payload: dict[str, Any]) -> str:
    acquired_at_text = str(payload.get("acquired_at") or "unknown")
    state = "age unknown"
    try:
        acquired_at = datetime.fromisoformat(acquired_at_text)
        if acquired_at.tzinfo is None:
            acquired_at = acquired_at.replace(tzinfo=timezone.utc)
        age_seconds = (datetime.now(timezone.utc) - acquired_at).total_seconds()
        state = "stale" if age_seconds > TASK_LOCK_STALE_AFTER_SECONDS else "active"
    except ValueError:
        pass
    return f"promote lock is {state}; acquired_at {acquired_at_text}"


def _finding(
    root: Path,
    *,
    code: str,
    severity: str,
    detail: str,
    path: Path,
    task_id: str | None,
    next_action: str,
) -> dict[str, Any]:
    finding: dict[str, Any] = {
        "severity": severity,
        "code": code,
        "path": relative_path(root, path),
        "detail": detail,
        "next_action": next_action,
    }
    if task_id:
        finding["task_id"] = task_id
    return finding