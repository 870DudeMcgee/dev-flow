from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Any

from devflow.control_room.git_worktree import create_git_worktree, refresh_git_worker_evidence
from devflow.control_room.models import TaskRecord
from devflow.control_room.paths import (
    config_path,
    devflow_dir,
    relative_path,
    system_dir,
    system_events_path,
    task_dir,
    tasks_dir,
    workspaces_dir,
)
from devflow.control_room.persistence import utc_now
from devflow.control_room.project_registry import ProjectRegistryError, load_project_metadata
from devflow.control_room.seed import initialize_seed
from devflow.control_room.task_artifacts import ensure_task_baseline_artifacts
from devflow.control_room.task_lifecycle import record_task_update
from devflow.control_room.workspace import create_workspace


def initialize_control_room(root: Path, project_seed: Any | None = None) -> None:
    devflow_dir(root).mkdir(parents=True, exist_ok=True)
    initialize_seed(root, project_seed=project_seed)
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


def create_control_room_task(
    root: Path,
    title: str,
    git_worktree: bool = False,
    worker_id: str = "shell",
    definition_of_done: str | None = None,
) -> TaskRecord:
    initialize_control_room(root)
    _require_managed_project_git_baseline(root)
    done_text = str(definition_of_done).strip() if definition_of_done is not None else None

    task_id, task_path = _create_task_directory(root)
    workspace = (
        create_git_worktree(root, task_id, worker_id=worker_id)
        if git_worktree
        else create_workspace(root, task_id)
    )

    now = utc_now()
    record = TaskRecord(
        id=task_id,
        title=title,
        definition_of_done=done_text or None,
        status="created",
        created_at=now,
        updated_at=now,
        workspace=relative_path(root, workspace.path),
        workspace_path=relative_path(root, workspace.path),
        workspace_kind=workspace.kind,
        worker="shell",
        last_event="task_created",
        verification_status="not_run",
        branch_name=workspace.branch_name,
        workspace_commit=workspace.commit_sha,
        workspace_dirty=workspace.dirty,
        git={
            "base_ref": workspace.base_ref,
            "base_commit": workspace.commit_sha,
            "branch": workspace.branch_name,
            "workspace": relative_path(root, workspace.path),
        },
    )
    _write_initial_artifacts(task_path, task_id, record.workspace)
    if git_worktree:
        refresh_git_worker_evidence(root, record, worker_id=worker_id)
    record_task_update(
        root,
        record,
        event_type="task_created",
        event_payload=_task_created_event_payload(title, record, workspace),
        event_position="before_save",
    )
    return record


def _require_managed_project_git_baseline(root: Path) -> None:
    try:
        metadata = load_project_metadata(root)
    except ProjectRegistryError:
        return
    if not metadata.source_control.local_repo:
        return

    head = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD"],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    if head.returncode == 0:
        return

    raise ValueError(
        "Project local Git baseline is missing. "
        f"Run `devflow git checkpoint --message \"chore: initialize project baseline\" --yes` from {root} "
        "before creating tasks."
    )


def _create_task_directory(root: Path) -> tuple[str, Path]:
    lock_dir = devflow_dir(root) / ".lock"
    for _ in range(200):
        try:
            lock_dir.mkdir(parents=True, exist_ok=False)
            break
        except FileExistsError:
            time.sleep(0.01)

    try:
        task_id = _next_task_id(root)
        task_path = task_dir(root, task_id)
        task_path.mkdir(parents=True, exist_ok=False)
        (task_path / "logs").mkdir(parents=True, exist_ok=True)
        return task_id, task_path
    finally:
        try:
            lock_dir.rmdir()
        except Exception:
            pass


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


def _write_initial_artifacts(task_path: Path, task_id: str, workspace_rel: str) -> None:
    ensure_task_baseline_artifacts(task_path, task_id=task_id, workspace_rel=workspace_rel)


def _task_created_event_payload(title: str, record: TaskRecord, workspace: Any) -> dict[str, Any]:
    event_payload: dict[str, Any] = {
        "title": title,
        "definition_of_done": record.definition_of_done,
        "workspace": record.workspace,
        "branch_name": workspace.branch_name,
        "workspace_commit": workspace.commit_sha,
        "workspace_dirty": workspace.dirty,
        "workspace_kind": workspace.kind,
        "git": record.git,
    }
    if workspace.skipped_symlinks:
        event_payload["skipped_symlinks"] = list(workspace.skipped_symlinks)
    return event_payload
