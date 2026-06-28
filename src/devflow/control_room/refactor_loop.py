from __future__ import annotations

import importlib.util
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any, Callable

from devflow.control_room.architecture_audit import ArchitectureAuditResult, run_architecture_audit
from devflow.control_room.browser_action_policy import ACTION_APPROVAL_PHRASE
from devflow.control_room.log_sanitizer import sanitize_log_line
from devflow.control_room.persistence import atomic_write_text


REFACTOR_APPROVAL_ACTION = "refactor-loop-start"
ALLOWED_REFACTOR_WORKERS = {"local-fast", "codex55"}
REFACTOR_RUN_SCHEMA_VERSION = 1
REFACTOR_RUN_ID_RE = re.compile(r"^refactor-[0-9TZ]+-[a-z0-9-]+$")
REFACTOR_LOOP_SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,200}$")
REFACTOR_LOG_TAIL_LINES = 80


class RefactorLoopError(ValueError):
    pass


AuditRunner = Callable[[Path], ArchitectureAuditResult]
ScorecardWriter = Callable[[Path], Path]
LoopStarter = Callable[[Path, str, int, Path, str], dict[str, Any]]


def require_refactor_approval(payload: dict[str, object]) -> None:
    worker = payload.get("worker")
    if not isinstance(worker, str) or worker not in ALLOWED_REFACTOR_WORKERS:
        allowed = ", ".join(sorted(ALLOWED_REFACTOR_WORKERS))
        raise RefactorLoopError(f"worker must be one of: {allowed}")
    if payload.get("human_approved") is not True:
        raise RefactorLoopError("refactor loop requires explicit human approval")
    if payload.get("approval_phrase") != ACTION_APPROVAL_PHRASE:
        raise RefactorLoopError("refactor loop approval phrase did not match")
    if payload.get("approved_action") != REFACTOR_APPROVAL_ACTION:
        raise RefactorLoopError("refactor loop approved_action did not match")
    if payload.get("approved_worker") != worker:
        raise RefactorLoopError("refactor loop approved_worker did not match")


def start_refactor_loop(
    root: Path,
    *,
    worker: str,
    audit_runner: AuditRunner | None = None,
    scorecard_writer: ScorecardWriter | None = None,
    loop_starter: LoopStarter | None = None,
) -> dict[str, Any]:
    if worker not in ALLOWED_REFACTOR_WORKERS:
        allowed = ", ".join(sorted(ALLOWED_REFACTOR_WORKERS))
        raise RefactorLoopError(f"worker must be one of: {allowed}")

    repo_root = root.resolve()
    audit = (audit_runner or _run_architecture_audit)(repo_root)
    audit_payload = audit.model_dump(mode="json")
    issue_count = audit.diagnostic.issue_count
    base: dict[str, Any] = {
        "executed": True,
        "exit_code": 0,
        "started": False,
        "issue_count": issue_count,
        "worker": worker,
        "goal_file": None,
        "scorecard_path": None,
        "loop_log": None,
        "loop_pid": None,
        "command": None,
        "audit": audit_payload,
        "error": None,
        "message": "",
    }
    if issue_count is None:
        return persist_refactor_run_result(
            repo_root,
            {
                **base,
                "exit_code": 1,
                "error": "Graphify diagnostic did not report issue_count.",
                "message": "Repair the architecture audit before starting a refactor loop.",
            },
        )
    if issue_count < 0:
        return persist_refactor_run_result(
            repo_root,
            {
                **base,
                "exit_code": 1,
                "error": f"Graphify diagnostic reported invalid issue_count: {issue_count}",
                "message": "Repair the architecture audit before starting a refactor loop.",
            },
        )
    if issue_count == 0:
        return persist_refactor_run_result(repo_root, {**base, "message": "No refactor issues found by Graphify."})

    scorecard_path = (scorecard_writer or _write_graphify_scorecard)(repo_root)
    candidate = _candidate_from_audit(audit, issue_count)
    loop_result = (loop_starter or _start_rehab_loop)(repo_root, worker, issue_count, scorecard_path, candidate)
    started = bool(loop_result.get("started"))
    return persist_refactor_run_result(
        repo_root,
        {
            **base,
            "exit_code": int(loop_result.get("returncode", 0 if started else 1)),
            "started": started,
            "goal_file": loop_result.get("goal_file"),
            "scorecard_path": scorecard_path.as_posix(),
            "loop_log": loop_result.get("loop_log"),
            "loop_pid": loop_result.get("loop_pid"),
            "command": loop_result.get("command"),
            "loop_slug": loop_result.get("loop_slug"),
            "profile": loop_result.get("profile"),
            "planner_profile": loop_result.get("planner_profile"),
            "planner_toolsets": loop_result.get("planner_toolsets"),
            "judge_profile": loop_result.get("judge_profile"),
            "preflight": loop_result.get("preflight"),
            "planner_preflight": loop_result.get("planner_preflight"),
            "judge_preflight": loop_result.get("judge_preflight"),
            "message": "Refactor loop started." if started else "Refactor loop did not start.",
            "error": None if started else _loop_start_error(loop_result),
        },
    )


def persist_refactor_run_result(root: Path, result: dict[str, Any]) -> dict[str, Any]:
    repo_root = root.resolve()
    runs_dir = _refactor_runs_dir(repo_root)
    runs_dir.mkdir(parents=True, exist_ok=True)
    enriched = dict(result)
    run_id = _string_or_none(enriched.get("run_id")) or _new_run_id(enriched)
    _validate_run_id(run_id)
    run_path = runs_dir / f"{run_id}.json"
    now = _now()
    enriched.update(
        {
            "schema_version": REFACTOR_RUN_SCHEMA_VERSION,
            "run_id": run_id,
            "run_path": _relative_or_absolute(repo_root, run_path),
            "recorded_at": _string_or_none(enriched.get("recorded_at")) or now,
            "updated_at": now,
        }
    )
    atomic_write_text(run_path, json.dumps(enriched, indent=2, sort_keys=True) + "\n")
    atomic_write_text(runs_dir / "latest.json", json.dumps(enriched, indent=2, sort_keys=True) + "\n")
    return enriched


def load_refactor_run_status(
    root: Path,
    *,
    run_id: str | None = None,
    loop_slug: str | None = None,
) -> dict[str, Any]:
    repo_root = root.resolve()
    record = _load_refactor_run_record(repo_root, run_id=run_id, loop_slug=loop_slug)
    if record is None:
        raise RefactorLoopError("refactor run not found")
    return _project_refactor_run_status(repo_root, record)


def _project_refactor_run_status(root: Path, record: dict[str, Any]) -> dict[str, Any]:
    log_path = _safe_path_from_record(root, record.get("loop_log"), allow_hermes_logs=True)
    pid_path = _safe_path_from_record(root, record.get("loop_pid"), allow_hermes_logs=True)
    log_tail = _read_log_tail(log_path)
    latest_line = log_tail[-1] if log_tail else ""
    pid_state = _pid_state(pid_path)
    status = _refactor_status(record, latest_line, pid_state)
    artifacts = _refactor_artifacts(root, record)
    return {
        **record,
        "status": status,
        "status_label": _status_label(status),
        "pid_state": pid_state,
        "log_tail": log_tail,
        "latest_log_line": latest_line,
        "artifacts": artifacts,
        "phases": _refactor_phases(record, status, artifacts, log_tail),
        "next_safe_action": _next_safe_action(record, status),
    }


def _run_architecture_audit(root: Path) -> ArchitectureAuditResult:
    return run_architecture_audit(root, install_graphify=False, write_doc=False)


def _write_graphify_scorecard(root: Path) -> Path:
    module = _load_rehab_script(root, "graphify_rehab_score.py")
    card = module.compute_scorecard(root)
    return Path(module.write_scorecard(card))


def _start_rehab_loop(root: Path, worker: str, max_iterations: int, scorecard_path: Path, candidate: str) -> dict[str, Any]:
    module = _load_rehab_script(root, "start_rehab_loop.py")
    return dict(
        module.prepare_rehab_loop(
            root,
            candidate=candidate,
            scorecard=scorecard_path,
            max_iterations=max_iterations,
            worker=worker,
            background=True,
            dry_run=False,
        )
    )


def _load_rehab_script(root: Path, name: str) -> ModuleType:
    path = root / "skills" / "improve-codebase-architecture" / "scripts" / name
    if not path.exists():
        raise RefactorLoopError(f"Architecture rehab script not found: {path.relative_to(root).as_posix()}")
    spec = importlib.util.spec_from_file_location(f"devflow_rehab_{path.stem}", path)
    if spec is None or spec.loader is None:
        raise RefactorLoopError(f"Could not load architecture rehab script: {path.relative_to(root).as_posix()}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _candidate_from_audit(audit: ArchitectureAuditResult, issue_count: int) -> str:
    target = audit.recommended_cleanup_targets[0] if audit.recommended_cleanup_targets else "the highest-risk hotspot"
    plural = "issue" if issue_count == 1 else "issues"
    return f"Use Graphify and Ponytail gates to resolve {issue_count} architecture {plural}, starting at {target}"


def _loop_start_error(loop_result: dict[str, Any]) -> str:
    for key in ("judge_preflight", "planner_preflight", "preflight"):
        value = loop_result.get(key)
        if isinstance(value, dict) and value.get("reason"):
            return str(value["reason"])
    return "Loop-Goal-Script start command returned a non-zero status."


def _refactor_runs_dir(root: Path) -> Path:
    return root / ".devflow" / "architecture-rehab" / "runs"


def _load_refactor_run_record(root: Path, *, run_id: str | None, loop_slug: str | None) -> dict[str, Any] | None:
    runs_dir = _refactor_runs_dir(root)
    if run_id:
        _validate_run_id(run_id)
        return _read_json_object(runs_dir / f"{run_id}.json")
    if loop_slug:
        _validate_loop_slug(loop_slug)
        for path in _run_files_newest_first(runs_dir):
            record = _read_json_object(path)
            if record and record.get("loop_slug") == loop_slug:
                return record
        return None
    return _read_json_object(runs_dir / "latest.json")


def _run_files_newest_first(runs_dir: Path) -> list[Path]:
    if not runs_dir.exists():
        return []
    return sorted(
        [path for path in runs_dir.glob("refactor-*.json") if path.is_file()],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )


def _read_json_object(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _new_run_id(result: dict[str, Any]) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    suffix = _slug(result.get("loop_slug") or result.get("worker") or "run")
    return f"refactor-{stamp}-{suffix}"


def _validate_run_id(run_id: str) -> None:
    if not REFACTOR_RUN_ID_RE.match(run_id):
        raise RefactorLoopError("run_id may contain only a generated refactor run id")


def _validate_loop_slug(loop_slug: str) -> None:
    if not REFACTOR_LOOP_SLUG_RE.match(loop_slug):
        raise RefactorLoopError("loop_slug may contain only letters, numbers, dots, underscores, and hyphens")


def _slug(value: object) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", str(value or "run").lower()).strip("-")
    return (text[:64].strip("-") or "run")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _string_or_none(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _relative_or_absolute(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _safe_path_from_record(root: Path, raw_path: object, *, allow_hermes_logs: bool = False) -> Path | None:
    if not isinstance(raw_path, str) or not raw_path.strip():
        return None
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = root / path
    try:
        resolved = path.resolve()
    except OSError:
        return None
    allowed_roots = [root.resolve()]
    if allow_hermes_logs:
        allowed_roots.append((Path.home() / ".hermes" / "logs").resolve())
    if any(_is_relative_to(resolved, allowed) for allowed in allowed_roots):
        return resolved
    return None


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _read_log_tail(path: Path | None, *, limit: int = REFACTOR_LOG_TAIL_LINES) -> list[str]:
    if path is None or not path.exists() or not path.is_file():
        return []
    try:
        raw_lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    visible = [line for line in (sanitize_log_line(line) for line in raw_lines[-limit * 2 :]) if line]
    return visible[-limit:]


def _pid_state(path: Path | None) -> str:
    if path is None:
        return "missing"
    if not path.exists():
        return "missing"
    try:
        raw_pid = path.read_text(encoding="utf-8").strip()
        pid = int(raw_pid)
    except (OSError, ValueError):
        return "unreadable"
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return "stale"
    except PermissionError:
        return "running"
    return "running"


def _refactor_status(record: dict[str, Any], latest_line: str, pid_state: str) -> str:
    if record.get("error"):
        return "blocked"
    if record.get("issue_count") == 0:
        return "idle"
    if not record.get("started"):
        return "blocked"
    if pid_state == "running":
        return "running"
    line = latest_line.lower()
    if any(marker in line for marker in ("completed", "complete", "handoff", "next safe action")):
        return "completed"
    if any(marker in line for marker in ("failed", "traceback", "error")):
        return "failed"
    return "unknown"


def _status_label(status: str) -> str:
    return {
        "blocked": "Blocked",
        "completed": "Completed",
        "failed": "Failed",
        "idle": "Idle",
        "running": "Running",
        "unknown": "Unknown",
    }.get(status, status.title())


def _refactor_artifacts(root: Path, record: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for label, key, kind in (
        ("Goal file", "goal_file", "goal"),
        ("Scorecard", "scorecard_path", "scorecard"),
        ("Loop log", "loop_log", "log"),
        ("PID file", "loop_pid", "pid"),
        ("Run record", "run_path", "run"),
    ):
        raw = record.get(key)
        if not isinstance(raw, str) or not raw.strip():
            continue
        path = _safe_path_from_record(root, raw, allow_hermes_logs=key in {"loop_log", "loop_pid"})
        rows.append(
            {
                "label": label,
                "kind": kind,
                "path": raw,
                "exists": bool(path and path.exists()),
            }
        )
    rows.extend(_discovered_architecture_artifacts(root, rows))
    return rows


def _discovered_architecture_artifacts(root: Path, existing_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    base = root / ".devflow" / "architecture-rehab"
    if not base.exists():
        return []
    seen = {str(row.get("path")) for row in existing_rows}
    candidates = [
        path
        for path in base.rglob("*")
        if path.is_file() and path.suffix.lower() in {".md", ".json", ".log"} and "runs" not in path.parts
    ]
    candidates.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    rows: list[dict[str, Any]] = []
    for path in candidates[:12]:
        rel = path.relative_to(root).as_posix()
        if rel in seen or path.as_posix() in seen:
            continue
        rows.append({"label": _artifact_label(path), "kind": _artifact_kind(path), "path": rel, "exists": True})
    return rows


def _artifact_label(path: Path) -> str:
    stem = path.stem.replace("-", " ").replace("_", " ").strip()
    return stem.title() if stem else path.name


def _artifact_kind(path: Path) -> str:
    name = path.name.lower()
    if "scorecard" in name or path.suffix == ".json":
        return "scorecard"
    if "handoff" in name or path.suffix == ".md":
        return "handoff"
    if path.suffix == ".log":
        return "log"
    return "artifact"


def _refactor_phases(
    record: dict[str, Any],
    status: str,
    artifacts: list[dict[str, Any]],
    log_tail: list[str],
) -> list[dict[str, str]]:
    artifact_kinds = {str(item.get("kind")) for item in artifacts if item.get("exists")}
    log_text = "\n".join(log_tail).lower()
    return [
        _phase("Graphify audit", "done" if record.get("audit") else "pending", "Graphify diagnostic captured."),
        _phase("Scorecard", "done" if "scorecard" in artifact_kinds else "pending", "Before scorecard is linked."),
        _phase("Goal file", "done" if "goal" in artifact_kinds else "pending", "Loop goal file is linked."),
        _phase("Planner", _phase_state(bool(record.get("planner_profile")), "planner" in log_text), "Planner profile and plan evidence."),
        _phase("Worker", _phase_state(bool(record.get("profile") or record.get("worker")), "worker" in log_text), "Worker output evidence."),
        _phase("Judge", _phase_state(bool(record.get("judge_profile")), "judge" in log_text), "Judge feedback evidence."),
        _phase("Handoff", "done" if status == "completed" else "pending", "Handoff and next safe action."),
    ]


def _phase(name: str, state: str, detail: str) -> dict[str, str]:
    return {"name": name, "state": state, "detail": detail}


def _phase_state(configured: bool, seen_in_log: bool) -> str:
    if seen_in_log:
        return "done"
    if configured:
        return "active"
    return "pending"


def _next_safe_action(record: dict[str, Any], status: str) -> str:
    if status == "completed":
        return "Review the handoff, focused tests, and graph delta evidence before deciding the next slice."
    if status == "running":
        return "Let the refactor loop continue; inspect the log and judge feedback for blockers."
    if status == "idle":
        return "No refactor loop is needed until Graphify reports issues."
    if status == "blocked":
        return str(record.get("message") or record.get("error") or "Fix the blocked preflight or audit result, then retry.")
    return "Refresh the work view and inspect the log path for the latest loop state."


__all__ = [
    "ALLOWED_REFACTOR_WORKERS",
    "REFACTOR_APPROVAL_ACTION",
    "RefactorLoopError",
    "load_refactor_run_status",
    "persist_refactor_run_result",
    "require_refactor_approval",
    "start_refactor_loop",
]
