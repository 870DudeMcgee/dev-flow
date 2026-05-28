from __future__ import annotations

import shlex
import json
import difflib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from devflow.control_room.models import TaskRecord, WorkerInput, WorkerResult
from devflow.control_room.paths import (
    config_path,
    devflow_dir,
    system_dir,
    system_events_path,
    task_dir,
    tasks_dir,
    workspaces_dir,
)
from devflow.control_room.verification import VerificationResult, run_verification_command
from devflow.control_room.worker_adapter import get_worker_adapter
from devflow.control_room.workspace import create_workspace


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def timestamp() -> str:
    return utc_now().isoformat()


def init_control_room(root: Path) -> None:
    devflow_dir(root).mkdir(parents=True, exist_ok=True)
    system_dir(root).mkdir(parents=True, exist_ok=True)
    tasks_dir(root).mkdir(parents=True, exist_ok=True)
    workspaces_dir(root).mkdir(parents=True, exist_ok=True)
    system_events_path(root).touch(exist_ok=True)
    if not config_path(root).exists():
        config_path(root).write_text(
            "version: 1\n"
            "source_of_truth: filesystem\n"
            "tasks: .devflow/tasks\n"
            "workspaces: .devflow/workspaces\n"
            "workers:\n"
            "  shell:\n"
            "    type: shell\n",
            encoding="utf-8",
        )


def create_task(root: Path, title: str) -> TaskRecord:
    init_control_room(root)
    task_id = _next_task_id(root)
    task_path = task_dir(root, task_id)
    (task_path / "logs").mkdir(parents=True, exist_ok=True)
    workspace = create_workspace(root, task_id)

    now = utc_now()
    record = TaskRecord(
        id=task_id,
        title=title,
        status="created",
        created_at=now,
        updated_at=now,
        workspace=_relative(root, workspace.path),
        worker="shell",
        last_event="task_created",
        verification_status="not_run",
        branch_name=workspace.branch_name,
        workspace_commit=workspace.commit_sha,
        workspace_dirty=workspace.dirty,
    )
    _write_initial_artifacts(task_path, task_id, record.workspace)
    event_payload: dict[str, Any] = {
        "title": title,
        "workspace": record.workspace,
        "branch_name": workspace.branch_name,
        "workspace_commit": workspace.commit_sha,
        "workspace_dirty": workspace.dirty,
    }
    if workspace.skipped_symlinks:
        event_payload["skipped_symlinks"] = list(workspace.skipped_symlinks)
    _append_event(root, task_id, "task_created", event_payload)
    _save_task(task_path, record)
    _write_merge_readiness(root, task_path, record)
    return record


def list_tasks(root: Path) -> list[TaskRecord]:
    if not tasks_dir(root).exists():
        return []
    records = []
    for path in sorted(tasks_dir(root).iterdir()):
        if path.is_dir() and (path / "task.yaml").exists():
            records.append(_load_task(path))
    return records


def get_task(root: Path, task_id: str) -> TaskRecord:
    path = task_dir(root, task_id)
    if not (path / "task.yaml").exists():
        raise KeyError(f"Task not found: {task_id}")
    return _load_task(path)


def run_shell_task(root: Path, task_id: str, command: list[str], timeout_seconds: int = 60, worker_adapter: str = "shell") -> TaskRecord:
    adapter = get_worker_adapter(worker_adapter)
    if not command:
        raise ValueError("Shell worker requires a command after '--'.")
    if _looks_destructive(command):
        task = get_task(root, task_id)
        task.status = "blocked"
        task.updated_at = utc_now()
        task.last_event = "command_refused"
        _save_task(task_dir(root, task_id), task)
        _append_event(root, task_id, "command_refused", {"command": command})
        raise ValueError("Refusing obviously destructive command for MVP shell worker.")

    task = get_task(root, task_id)
    task_path = task_dir(root, task_id)
    workspace = _resolve_task_workspace(root, task)
    worker_input = WorkerInput(
        task_id=task_id,
        repo_root=root,
        workspace_path=workspace,
        task_file=task_path / "task.yaml",
        context_file=task_path / "events.jsonl",
        status_file=task_path / "task.yaml",
        questions_file=task_path / "questions.jsonl",
        result_file=task_path / "result.md",
        log_file=task_path / "logs" / "worker.log",
        command=command,
        timeout_seconds=timeout_seconds,
    )

    task.status = "running"
    task.worker = adapter.name
    task.timeout_seconds = timeout_seconds
    task.worker_command = shlex.join(command)
    task.started_at = utc_now()
    task.updated_at = task.started_at
    task.last_event = "worker_started"
    _save_task(task_path, task)
    _append_event(root, task_id, "worker_started", {"command": command, "cwd": task.workspace})

    # Generate packet.json immediately before worker execution
    from devflow.control_room.task_packet import build_task_packet
    packet = build_task_packet(task_id, root=root)
    packet_json = json.dumps(packet.model_dump(mode="json"), sort_keys=True, indent=2) + "\n"
    (task_path / "packet.json").write_text(packet_json, encoding="utf-8")

    result = adapter.run(worker_input)
    _write_result(task_path, task_id, command, result)

    task.status = result.status
    task.last_exit_code = result.exit_code
    task.latest_log_line = result.latest_log_line
    task.log_path = _relative(root, result.log_file)
    task.result_path = _relative(root, result.result_file)
    task.finished_at = utc_now()
    task.updated_at = task.finished_at
    task.last_event = "worker_finished"
    _save_task(task_path, task)
    _write_merge_readiness(root, task_path, task)
    _append_event(
        root,
        task_id,
        "worker_finished",
        {"status": result.status, "exit_code": result.exit_code, "log_path": task.log_path},
    )
    return task


def verify_task(root: Path, task_id: str, command: list[str], timeout_seconds: int = 120) -> TaskRecord:
    if not command:
        raise ValueError("Verification requires a command after '--'.")
    task = get_task(root, task_id)
    if _looks_destructive(command):
        _append_event(root, task_id, "verification_refused", {"command": command})
        raise ValueError("Refusing obviously destructive verification command.")

    task_path = task_dir(root, task_id)
    workspace = _resolve_task_workspace(root, task)
    verify_log = task_path / "logs" / "verify.log"

    _append_event(root, task_id, "verification_started", {"command": command, "cwd": task.workspace})
    result = run_verification_command(workspace, command, verify_log, timeout_seconds=timeout_seconds)

    task.status = "verified" if result.status == "passed" else "verification_failed"
    task.verification_status = result.status
    task.verification_command = shlex.join(command)
    task.verification_exit_code = result.exit_code
    task.verification_log_path = _relative(root, result.log_file)
    task.latest_log_line = result.latest_log_line
    task.updated_at = utc_now()
    task.last_event = "verification_finished"
    _write_verification_json(root, task_path, task, result)
    _write_verification_report(task_path, task, result)
    _save_task(task_path, task)
    _write_merge_readiness(root, task_path, task)
    _append_event(
        root,
        task_id,
        "verification_finished",
        {"status": result.status, "exit_code": result.exit_code, "log_path": task.verification_log_path},
    )
    return task


def doctor(root: Path) -> list[tuple[str, bool, str]]:
    checks = [
        ("runtime directory", devflow_dir(root).exists(), str(devflow_dir(root))),
        ("config", config_path(root).exists(), str(config_path(root))),
        ("system directory", system_dir(root).exists(), str(system_dir(root))),
        ("system events", system_events_path(root).exists(), str(system_events_path(root))),
        ("tasks directory", tasks_dir(root).exists(), str(tasks_dir(root))),
        ("workspaces directory", workspaces_dir(root).exists(), str(workspaces_dir(root))),
    ]
    if tasks_dir(root).exists():
        for path in sorted(tasks_dir(root).iterdir()):
            if not path.is_dir():
                continue
            yaml_path = path / "task.yaml"
            checks.append((f"{path.name} task.yaml", yaml_path.exists(), str(yaml_path)))
            if yaml_path.exists():
                try:
                    task = _load_task(path)
                except ValueError as exc:
                    checks.append((f"{path.name} task.yaml valid", False, str(exc)))
                    continue
                checks.append((f"{path.name} workspace", _absolute(root, task.workspace).is_dir(), task.workspace))
                for name in ("events.jsonl", "questions.jsonl", "result.md", "verification.json"):
                    checks.append((f"{path.name} {name}", (path / name).exists(), str(path / name)))
    return checks


def _write_initial_artifacts(task_path: Path, task_id: str, workspace_rel: str) -> None:
    (task_path / "events.jsonl").touch(exist_ok=True)
    (task_path / "questions.jsonl").touch(exist_ok=True)
    (task_path / "result.md").write_text(f"# Result: {task_id}\n\nNot run yet.\n", encoding="utf-8")
    (task_path / "verification.json").write_text(
        json.dumps({
            "task_id": task_id,
            "workspace": workspace_rel,
            "command": None,
            "status": "not_run",
            "task_status": "created",
            "exit_code": None,
            "latest_log_line": None,
            "log_path": f".devflow/tasks/{task_id}/logs/verify.log",
            "finished_at": None,
        }, indent=2) + "\n",
        encoding="utf-8",
    )
    (task_path / "logs" / "worker.log").touch(exist_ok=True)
    (task_path / "logs" / "verify.log").touch(exist_ok=True)


def _write_result(task_path: Path, task_id: str, command: list[str], result: WorkerResult) -> None:
    command_text = " ".join(command)
    body = (
        f"# Result: {task_id}\n\n"
        f"## Summary\n\n{result.summary}\n\n"
        f"## Status\n\n{result.status}\n\n"
        f"## Command\n\n```bash\n{command_text}\n```\n\n"
        f"## Exit Code\n\n{result.exit_code if result.exit_code is not None else 'none'}\n\n"
        f"## Log\n\n{result.log_file}\n"
    )
    result.result_file.write_text(body, encoding="utf-8")


def _write_verification_json(root: Path, task_path: Path, task: TaskRecord, result: VerificationResult) -> None:
    payload = {
        "task_id": task.id,
        "workspace": task.workspace,
        "command": result.command,
        "status": result.status,
        "task_status": task.status,
        "exit_code": result.exit_code,
        "latest_log_line": result.latest_log_line,
        "log_path": _relative(root, result.log_file),
        "finished_at": utc_now().isoformat(),
    }
    (task_path / "verification.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _write_merge_readiness(root: Path, task_path: Path, task: TaskRecord) -> None:
    finished_at = None
    verification_json_path = task_path / "verification.json"
    if verification_json_path.exists():
        try:
            v_data = json.loads(verification_json_path.read_text(encoding="utf-8"))
            finished_at = v_data.get("finished_at")
        except Exception:
            pass

    ready = False
    reasons = []

    if task.status != "verified":
        reasons.append(f"Task status is '{task.status}', expected 'verified'")
    if task.verification_status != "passed":
        reasons.append(f"Verification status is '{task.verification_status}', expected 'passed'")
    if task.verification_exit_code != 0:
        if task.verification_exit_code is None:
            reasons.append("Verification exit code is missing")
        else:
            reasons.append(f"Verification exit code is {task.verification_exit_code}, expected 0")

    if not reasons:
        ready = True
        reasons.append("Verification passed successfully")

    if task.workspace_dirty:
        reasons.append("Warning: Workspace was created from a dirty worktree (uncommitted changes)")

    payload = {
        "task_id": task.id,
        "ready": ready,
        "reasons": reasons,
        "verification_status": task.verification_status,
        "verification_exit_code": task.verification_exit_code,
        "verification_finished_at": finished_at,
        "verification_log_path": task.verification_log_path,
        "workspace_dirty": task.workspace_dirty,
        "workspace_branch": task.branch_name,
        "workspace_commit": task.workspace_commit,
        "generated_at": utc_now().isoformat(),
    }
    (task_path / "merge-readiness.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _write_verification_report(task_path: Path, task: TaskRecord, result: VerificationResult) -> None:
    existing = (task_path / "result.md").read_text(encoding="utf-8") if (task_path / "result.md").exists() else ""
    if "\n## Verification\n" in existing:
        existing = existing.split("\n## Verification\n", 1)[0]
    verification = (
        "\n## Verification\n\n"
        f"Status: {result.status}\n\n"
        f"Task Status: {task.status}\n\n"
        f"Command:\n\n```bash\n{' '.join(result.command)}\n```\n\n"
        f"Exit Code: {result.exit_code if result.exit_code is not None else 'none'}\n\n"
        f"Log: {result.log_file}\n"
    )
    (task_path / "result.md").write_text(existing.rstrip() + verification, encoding="utf-8")


def _next_task_id(root: Path) -> str:
    existing = []
    if tasks_dir(root).exists():
        for path in tasks_dir(root).iterdir():
            if path.is_dir() and path.name.startswith("task-"):
                try:
                    existing.append(int(path.name.removeprefix("task-")))
                except ValueError:
                    continue
    return f"task-{(max(existing) if existing else 0) + 1:04d}"


def _append_event(root: Path, task_id: str, event_type: str, payload: dict[str, Any]) -> None:
    event = {"timestamp": timestamp(), "task_id": task_id, "event": event_type, **payload}
    line = json.dumps(event, sort_keys=True) + "\n"
    task_events = task_dir(root, task_id) / "events.jsonl"
    task_events.parent.mkdir(parents=True, exist_ok=True)
    with task_events.open("a", encoding="utf-8") as handle:
        handle.write(line)
    system_events_path(root).parent.mkdir(parents=True, exist_ok=True)
    with system_events_path(root).open("a", encoding="utf-8") as handle:
        handle.write(line)


def _write_task_summary(task_path: Path, task: TaskRecord) -> None:
    ready = False
    reasons = []

    if task.status != "verified":
        reasons.append(f"Task status is '{task.status}', expected 'verified'")
    if task.verification_status != "passed":
        reasons.append(f"Verification status is '{task.verification_status}', expected 'passed'")
    if task.verification_exit_code != 0:
        if task.verification_exit_code is None:
            reasons.append("Verification exit code is missing")
        else:
            reasons.append(f"Verification exit code is {task.verification_exit_code}, expected 0")

    if not reasons:
        ready = True
        reasons.append("Verification passed successfully")

    if task.workspace_dirty:
        reasons.append("Warning: Workspace was created from a dirty worktree (uncommitted changes)")

    payload = {
        "task_id": task.id,
        "title": task.title,
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
    (task_path / "summary.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _save_task(task_path: Path, task: TaskRecord) -> None:
    values = {
        "id": task.id,
        "title": task.title,
        "status": task.status,
        "created_at": task.created_at.isoformat(),
        "updated_at": task.updated_at.isoformat(),
        "workspace": task.workspace,
        "worker": task.worker,
        "last_event": task.last_event,
        "last_exit_code": task.last_exit_code,
        "verification_status": task.verification_status,
        "latest_log_line": task.latest_log_line,
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
    }
    lines = [f"{key}: {_yaml_scalar(value)}" for key, value in values.items()]
    task_path.mkdir(parents=True, exist_ok=True)
    (task_path / "task.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")
    _write_task_summary(task_path, task)


def _load_task(task_path: Path) -> TaskRecord:
    data = _read_yaml_scalars(task_path / "task.yaml")
    required = ["id", "title", "status", "created_at", "updated_at", "workspace", "worker", "verification_status"]
    missing = [key for key in required if key not in data]
    if missing:
        raise ValueError(f"missing keys in {task_path / 'task.yaml'}: {', '.join(missing)}")
    for key in ("created_at", "updated_at", "started_at", "finished_at"):
        if data.get(key):
            data[key] = datetime.fromisoformat(str(data[key]))
    return TaskRecord(**data)


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


def _relative(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _absolute(root: Path, path: str) -> Path:
    value = Path(path)
    return value if value.is_absolute() else root / value


def _resolve_task_workspace(root: Path, task: TaskRecord) -> Path:
    workspace = _absolute(root, task.workspace).resolve()
    expected = (workspaces_dir(root) / task.id).resolve()
    if workspace != expected:
        _refuse_workspace(root, task, workspace, expected)
    if not workspace.is_dir():
        _refuse_workspace(root, task, workspace, expected)
    return workspace


def _refuse_workspace(root: Path, task: TaskRecord, workspace: Path, expected: Path) -> None:
    task.status = "blocked"
    task.updated_at = utc_now()
    task.last_event = "workspace_refused"
    _save_task(task_dir(root, task.id), task)
    _append_event(
        root,
        task.id,
        "workspace_refused",
        {"workspace": str(workspace), "expected_workspace": str(expected)},
    )
    raise ValueError(f"Refusing unsafe task workspace: {workspace} (expected {expected})")


def _looks_destructive(command: list[str]) -> bool:
    text = " ".join(command).lower()
    blocked_fragments = ("rm -rf /", "rm -fr /", "mkfs", "diskutil erase", ":(){", "dd if=")
    return any(fragment in text for fragment in blocked_fragments)


def _is_ignored_path(path: Path, base_dir: Path) -> bool:
    try:
        rel = path.relative_to(base_dir)
    except ValueError:
        return True
    ignored_names = {".git", ".devflow", ".venv", "__pycache__", ".pytest_cache"}
    for part in rel.parts:
        if part in ignored_names:
            return True
    return False


def _get_relative_files(base_dir: Path) -> set[str]:
    rel_files = set()
    if not base_dir.is_dir():
        return rel_files
    for p in base_dir.rglob("*"):
        if p.is_file() and not p.is_symlink() and not _is_ignored_path(p, base_dir):
            try:
                rel = p.relative_to(base_dir)
                rel_files.add(rel.as_posix())
            except ValueError:
                pass
    return rel_files


def _is_binary_file(path: Path | None) -> bool:
    if not path or not path.exists():
        return False
    try:
        with path.open("rb") as f:
            chunk = f.read(1024)
            return b"\0" in chunk
    except OSError:
        return True


def _generate_file_diff(name: str, path_a: Path | None, path_b: Path | None) -> str:
    is_a_binary = _is_binary_file(path_a)
    is_b_binary = _is_binary_file(path_b)
    if is_a_binary or is_b_binary:
        return f"Binary files a/{name} and b/{name} differ\n"

    try:
        lines_a = path_a.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True) if path_a else []
        lines_b = path_b.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True) if path_b else []
        diff = difflib.unified_diff(
            lines_a,
            lines_b,
            fromfile=f"a/{name}",
            tofile=f"b/{name}",
        )
        return "".join(diff)
    except Exception as exc:
        return f"Error generating diff for {name}: {exc}\n"


def preview_task_promotion(root: Path, task_id: str) -> dict[str, Any]:
    task = get_task(root, task_id)
    workspace = _absolute(root, task.workspace).resolve()
    expected = (workspaces_dir(root) / task.id).resolve()
    if workspace != expected:
        raise ValueError(f"Refusing unsafe task workspace: {workspace} (expected {expected})")
    if not workspace.is_dir():
        raise ValueError(f"Workspace directory does not exist: {workspace}")

    workspace_files = _get_relative_files(workspace)
    main_files = _get_relative_files(root)

    added_files = sorted(list(workspace_files - main_files))
    deleted_files = sorted(list(main_files - workspace_files))
    common_files = workspace_files & main_files

    modified_files = []
    for name in sorted(list(common_files)):
        workspace_file = workspace / name
        main_file = root / name
        try:
            if workspace_file.read_bytes() != main_file.read_bytes():
                modified_files.append(name)
        except OSError:
            modified_files.append(name)

    diffs: dict[str, str] = {}
    for name in added_files:
        diffs[name] = _generate_file_diff(name, None, workspace / name)
    for name in modified_files:
        diffs[name] = _generate_file_diff(name, root / name, workspace / name)
    for name in deleted_files:
        diffs[name] = _generate_file_diff(name, root / name, None)

    return {
        "task_id": task.id,
        "added": added_files,
        "modified": modified_files,
        "deleted": deleted_files,
        "diffs": diffs,
    }
