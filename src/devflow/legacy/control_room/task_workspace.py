from __future__ import annotations

from pathlib import Path

from devflow.legacy.control_room.git_worktree import is_git_worktree_task, worker_id_for_task
from devflow.legacy.control_room.models import TaskRecord
from devflow.legacy.control_room.paths import absolute_path, workspaces_dir, worktree_path
from devflow.legacy.control_room.persistence import utc_now
from devflow.legacy.control_room.task_lifecycle import record_task_update


def runtime_workspace_path(root: Path, task: TaskRecord) -> Path:
    """Return the Dev-Flow-owned runtime workspace for a task."""
    if is_git_worktree_task(task):
        return worktree_path(root, task.id, worker_id_for_task(task)).resolve()
    return (workspaces_dir(root) / task.id).resolve()


def validated_task_workspace(root: Path, task: TaskRecord) -> Path:
    workspace = absolute_path(root, task.workspace).resolve()
    expected = runtime_workspace_path(root, task)
    if workspace != expected:
        _refuse_workspace(root, task, workspace, expected)
    if not workspace.is_dir():
        _refuse_workspace(root, task, workspace, expected)
    return workspace


def _refuse_workspace(root: Path, task: TaskRecord, workspace: Path, expected: Path) -> None:
    record_task_update(
        root,
        task,
        event_type="workspace_refused",
        event_payload={"workspace": str(workspace), "expected_workspace": str(expected)},
        status="blocked",
        updated_at=utc_now(),
        write_readiness=False,
    )
    raise ValueError(f"Refusing unsafe task workspace: {workspace} (expected {expected})")
