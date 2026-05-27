from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from devflow.control_room.db import connect
from devflow.control_room.models import TaskRecord, WorkerInput, WorkerResult
from devflow.control_room.paths import config_path, devflow_dir, task_dir, tasks_dir, workspace_path, worktrees_dir
from devflow.control_room.shell_worker import ShellWorkerAdapter
from devflow.control_room.verification import VerificationResult, run_verification_command
from devflow.control_room.workspace import Workspace, create_workspace


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def timestamp() -> str:
    return utc_now().isoformat()


def init_control_room(root: Path) -> None:
    devflow_dir(root).mkdir(parents=True, exist_ok=True)
    tasks_dir(root).mkdir(parents=True, exist_ok=True)
    worktrees_dir(root).mkdir(parents=True, exist_ok=True)
    connect(root).close()
    if not config_path(root).exists():
        config_path(root).write_text(
            "version: 1\n"
            "control_room:\n"
            "  host: 127.0.0.1\n"
            "  port: 8765\n"
            "workers:\n"
            "  shell:\n"
            "    type: shell\n",
            encoding="utf-8",
        )


def create_task(root: Path, title: str) -> TaskRecord:
    init_control_room(root)
    conn = connect(root)
    next_number = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] + 1
    task_id = f"task-{next_number:04d}"
    while conn.execute("SELECT 1 FROM tasks WHERE id = ?", (task_id,)).fetchone():
        next_number += 1
        task_id = f"task-{next_number:04d}"

    now = timestamp()
    task_path = task_dir(root, task_id)
    logs = task_path / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    workspace = create_workspace(root, task_id)

    _write_initial_artifacts(task_path, task_id, title, workspace)

    conn.execute(
        """
        INSERT INTO tasks (
            id, title, status, workspace_path, workspace_kind, branch_name, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (task_id, title, "draft", str(workspace.path), workspace.kind, workspace.branch_name, now, now),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    conn.close()
    return _record_from_row(row)


def list_tasks(root: Path) -> list[TaskRecord]:
    init_control_room(root)
    conn = connect(root)
    rows = conn.execute("SELECT * FROM tasks ORDER BY created_at, id").fetchall()
    conn.close()
    return [_record_from_row(row) for row in rows]


def get_task(root: Path, task_id: str) -> TaskRecord:
    init_control_room(root)
    conn = connect(root)
    row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    conn.close()
    if row is None:
        raise KeyError(f"Task not found: {task_id}")
    return _record_from_row(row)


def run_shell_task(root: Path, task_id: str, command: list[str], timeout_seconds: int = 60) -> TaskRecord:
    if not command:
        raise ValueError("Shell worker requires a command after '--'.")

    task = get_task(root, task_id)
    task_path = task_dir(root, task_id)
    workspace = Path(task.workspace_path or workspace_path(root, task_id))
    worker_input = WorkerInput(
        task_id=task_id,
        repo_root=root,
        workspace_path=workspace,
        task_file=task_path / "task.md",
        context_file=task_path / "context.md",
        status_file=task_path / "task.yaml",
        questions_file=task_path / "questions.md",
        result_file=task_path / "result.md",
        log_file=task_path / "logs" / "worker.log",
        command=command,
        timeout_seconds=timeout_seconds,
    )

    now = timestamp()
    conn = connect(root)
    conn.execute(
        """
        UPDATE tasks
        SET status = ?, worker_adapter = ?, timeout_seconds = ?, started_at = ?, updated_at = ?
        WHERE id = ?
        """,
        ("running", "shell", timeout_seconds, now, now, task_id),
    )
    conn.commit()
    conn.close()

    result = ShellWorkerAdapter().run(worker_input)
    _write_result(task_path, task_id, command, result)
    _update_task_yaml(task_path, task, result, workspace)

    finished = timestamp()
    conn = connect(root)
    conn.execute(
        """
        UPDATE tasks
        SET status = ?, worker_adapter = ?, latest_log_line = ?, log_path = ?, result_path = ?,
            exit_code = ?, timeout_seconds = ?, finished_at = ?, updated_at = ?
        WHERE id = ?
        """,
        (
            result.status,
            "shell",
            result.latest_log_line,
            str(result.log_file),
            str(result.result_file),
            result.exit_code,
            timeout_seconds,
            finished,
            finished,
            task_id,
        ),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    conn.close()
    return _record_from_row(row)


def verify_task(root: Path, task_id: str, command: list[str], timeout_seconds: int = 120) -> TaskRecord:
    if not command:
        raise ValueError("Verification requires a command after '--'.")

    task = get_task(root, task_id)
    workspace = Path(task.workspace_path or workspace_path(root, task_id))
    verify_log = task_dir(root, task_id) / "logs" / "verify.log"
    result = run_verification_command(workspace, command, verify_log, timeout_seconds=timeout_seconds)
    merge_ready = task.status == "complete" and result.status == "passed"

    _write_verification_report(task_dir(root, task_id), task, result, merge_ready)

    now = timestamp()
    conn = connect(root)
    conn.execute(
        """
        UPDATE tasks
        SET verification_status = ?, verification_command = ?, verification_exit_code = ?,
            verification_log_path = ?, latest_log_line = ?, merge_ready = ?, updated_at = ?
        WHERE id = ?
        """,
        (
            result.status,
            " ".join(command),
            result.exit_code,
            str(result.log_file),
            result.latest_log_line,
            1 if merge_ready else 0,
            now,
            task_id,
        ),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    conn.close()
    return _record_from_row(row)


def doctor(root: Path) -> list[tuple[str, bool, str]]:
    checks = [
        ("runtime directory", devflow_dir(root).exists(), str(devflow_dir(root))),
        ("sqlite database", (devflow_dir(root) / "devflow.db").exists(), str(devflow_dir(root) / "devflow.db")),
        ("config", config_path(root).exists(), str(config_path(root))),
        ("tasks directory", tasks_dir(root).exists(), str(tasks_dir(root))),
        ("worktrees directory", worktrees_dir(root).exists(), str(worktrees_dir(root))),
    ]
    return checks


def _write_initial_artifacts(task_path: Path, task_id: str, title: str, workspace: Workspace) -> None:
    (task_path / "task.yaml").write_text(
        f"id: {task_id}\n"
        f"title: {title}\n"
        "status: draft\n"
        "worker: null\n"
        f"workspace_path: {workspace.path}\n"
        f"workspace_kind: {workspace.kind}\n"
        f"branch_name: {workspace.branch_name or ''}\n",
        encoding="utf-8",
    )
    (task_path / "task.md").write_text(f"# {title}\n\nStatus: draft\n", encoding="utf-8")
    (task_path / "context.md").write_text(f"# Context: {task_id}\n\n", encoding="utf-8")
    (task_path / "questions.md").write_text(f"# Questions: {task_id}\n\n", encoding="utf-8")
    (task_path / "result.md").write_text(f"# Result: {task_id}\n\nNot run yet.\n", encoding="utf-8")
    (task_path / "report.md").write_text(f"# Report: {task_id}\n\nNot run yet.\n", encoding="utf-8")
    (task_path / "logs" / "verify.log").write_text("", encoding="utf-8")


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
    (task_path / "report.md").write_text(body, encoding="utf-8")


def _write_verification_report(
    task_path: Path,
    task: TaskRecord,
    result: VerificationResult,
    merge_ready: bool,
) -> None:
    command_text = " ".join(result.command)
    existing = (task_path / "report.md").read_text(encoding="utf-8") if (task_path / "report.md").exists() else ""
    verification = (
        "\n## Verification\n\n"
        f"Status: {result.status}\n\n"
        f"Command:\n\n```bash\n{command_text}\n```\n\n"
        f"Exit Code: {result.exit_code if result.exit_code is not None else 'none'}\n\n"
        f"Log: {result.log_file}\n\n"
        f"Merge Ready: {'yes' if merge_ready else 'no'}\n"
    )
    if "\n## Verification\n" in existing:
        existing = existing.split("\n## Verification\n", 1)[0]
    (task_path / "report.md").write_text(existing.rstrip() + verification, encoding="utf-8")
    _update_task_yaml_for_verification(task_path, task, result, merge_ready)


def _update_task_yaml_for_verification(
    task_path: Path,
    task: TaskRecord,
    result: VerificationResult,
    merge_ready: bool,
) -> None:
    yaml_path = task_path / "task.yaml"
    existing = yaml_path.read_text(encoding="utf-8") if yaml_path.exists() else ""
    kept_lines = [
        line for line in existing.splitlines()
        if not line.startswith(("verification_status:", "verification_command:", "verification_log_path:", "merge_ready:"))
    ]
    kept_lines.extend([
        f"verification_status: {result.status}",
        f"verification_command: {' '.join(result.command)}",
        f"verification_log_path: {result.log_file}",
        f"merge_ready: {'true' if merge_ready else 'false'}",
    ])
    yaml_path.write_text("\n".join(kept_lines).rstrip() + "\n", encoding="utf-8")


def _update_task_yaml(task_path: Path, task: TaskRecord, result: WorkerResult, workspace: Path) -> None:
    (task_path / "task.yaml").write_text(
        f"id: {task.id}\n"
        f"title: {task.title}\n"
        f"status: {result.status}\n"
        "worker: shell\n"
        f"workspace_path: {workspace}\n"
        f"workspace_kind: {task.workspace_kind or ''}\n"
        f"branch_name: {task.branch_name or ''}\n"
        f"log_path: {result.log_file}\n"
        f"result_path: {result.result_file}\n"
        f"latest_log_line: {result.latest_log_line or ''}\n",
        encoding="utf-8",
    )


def _record_from_row(row) -> TaskRecord:
    data = dict(row)
    for key in ("created_at", "updated_at", "started_at", "finished_at"):
        if data.get(key):
            data[key] = datetime.fromisoformat(data[key])
    return TaskRecord(**data)
