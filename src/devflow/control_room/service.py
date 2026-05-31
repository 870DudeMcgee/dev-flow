from __future__ import annotations

import shlex
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from devflow.control_room.models import TaskRecord, WorkerInput, WorkerResult
from devflow.control_room.paths import (
    absolute_path,
    relative_path,
    config_path,
    devflow_dir,
    system_dir,
    system_events_path,
    task_dir,
    tasks_dir,
    workspaces_dir,
)
from devflow.control_room.persistence import (
    append_event,
    get_task,
    list_tasks,
    load_task,
    save_task,
    timestamp,
    utc_now,
)
from devflow.control_room.promotion import (
    _get_relative_files,
    main_checkout_has_uncommitted_changes,
)
from devflow.control_room.readiness import format_promotion_refusal, promotion_readiness_errors, readiness_state
from devflow.control_room.seed import initialize_seed, validate_seed_contract
from devflow.control_room.verification import VerificationResult, run_verification_command
from devflow.control_room.worker_adapter import get_worker_adapter
from devflow.control_room.workspace import create_workspace


# Dynamic compatibility shims and mappings
_save_task = save_task
_load_task = load_task
_append_event = append_event
_relative = relative_path
_absolute = absolute_path


def preview_task_promotion(root: Path, task_id: str) -> dict[str, Any]:
    import devflow.control_room.promotion as promotion
    # Forward monkeypatch if service._get_relative_files was overridden in a test
    if _get_relative_files is not promotion._get_relative_files:
        promotion._get_relative_files = _get_relative_files
    return promotion.preview_task_promotion(root, task_id)


def promote_task(root: Path, task_id: str, force: bool = False, apply_deletions: bool = False) -> TaskRecord:
    import devflow.control_room.promotion as promotion
    # Forward monkeypatch if service._get_relative_files was overridden in a test
    if _get_relative_files is not promotion._get_relative_files:
        promotion._get_relative_files = _get_relative_files
    return promotion.promote_task(root, task_id, force=force, apply_deletions=apply_deletions)



def init_control_room(root: Path) -> None:
    devflow_dir(root).mkdir(parents=True, exist_ok=True)
    initialize_seed(root)
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



def run_shell_task(
    root: Path,
    task_id: str,
    command: list[str],
    timeout_seconds: int = 60,
    worker_adapter: str = "shell",
    env: dict[str, str] | None = None,
) -> TaskRecord:
    from devflow.control_room.agent_registry import load_agent_registry
    registry = load_agent_registry(root)

    agent = None
    resolved_adapter_name = worker_adapter

    if worker_adapter in registry.agents:
        agent = registry.require_agent(worker_adapter)
        if not agent.enabled:
            raise ValueError(f"Agent '{worker_adapter}' is disabled.")
        resolved_adapter_name = agent.adapter

    adapter = get_worker_adapter(resolved_adapter_name)
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

    log_file = task_path / "logs" / "worker.log"
    result_file = task_path / "result.md"

    if agent is not None:
        agent_dir = task_path / "agents" / agent.id
        agent_dir.mkdir(parents=True, exist_ok=True)
        (agent_dir / "logs").mkdir(parents=True, exist_ok=True)
        log_file = agent_dir / "logs" / "worker.log"
        result_file = agent_dir / "result.md"

    worker_input = WorkerInput(
        task_id=task_id,
        repo_root=root,
        workspace_path=workspace,
        task_file=task_path / "task.yaml",
        context_file=task_path / "events.jsonl",
        status_file=task_path / "task.yaml",
        questions_file=task_path / "questions.jsonl",
        result_file=result_file,
        log_file=log_file,
        command=command,
        env=env or {},
        timeout_seconds=timeout_seconds,
    )

    task.status = "running"
    task.worker = worker_adapter
    task.timeout_seconds = timeout_seconds
    task.worker_command = shlex.join(command)
    task.started_at = utc_now()
    task.updated_at = task.started_at
    task.last_event = "worker_started"
    _save_task(task_path, task)
    _append_event(root, task_id, "worker_started", {"command": command, "cwd": task.workspace})

    if agent is not None:
        from devflow.control_room.task_packet import build_agent_packet
        agent_packet = build_agent_packet(task_id, agent, root=root)
        agent_packet_json = json.dumps(agent_packet.model_dump(mode="json"), sort_keys=True, indent=2) + "\n"
        (task_path / "agents" / agent.id / "packet.json").write_text(agent_packet_json, encoding="utf-8")
        (task_path / "packet.json").write_text(agent_packet_json, encoding="utf-8")
    else:
        from devflow.control_room.task_packet import build_task_packet
        packet = build_task_packet(task_id, root=root)
        packet_json = json.dumps(packet.model_dump(mode="json"), sort_keys=True, indent=2) + "\n"
        (task_path / "packet.json").write_text(packet_json, encoding="utf-8")

    result = adapter.run(worker_input)
    _write_result(task_path if agent is None else (task_path / "agents" / agent.id), task_id, command, result)
    if agent is not None:
        compat_log = task_path / "logs" / "worker.log"
        compat_log.write_text(log_file.read_text(encoding="utf-8"), encoding="utf-8")
        _write_result(task_path, task_id, command, result)

    task.status = result.status
    task.last_exit_code = result.exit_code
    task.latest_log_line = result.latest_log_line
    task.log_path = _relative(root, log_file)
    task.result_path = _relative(root, result_file)
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
    seed_errors = validate_seed_contract(root)
    checks = [
        ("runtime directory", devflow_dir(root).exists(), str(devflow_dir(root))),
        ("config", config_path(root).exists(), str(config_path(root))),
        ("system directory", system_dir(root).exists(), str(system_dir(root))),
        ("system events", system_events_path(root).exists(), str(system_events_path(root))),
        ("tasks directory", tasks_dir(root).exists(), str(tasks_dir(root))),
        ("workspaces directory", workspaces_dir(root).exists(), str(workspaces_dir(root))),
    ]
    if seed_errors:
        checks.append(("seed contract", False, "; ".join(seed_errors)))
    elif devflow_dir(root).exists():
        checks.append(("seed contract", True, ".devflow seed contract"))
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

    ready, reasons = readiness_state(task, task_path)

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
