from __future__ import annotations

from pathlib import Path

from devflow.control_room.git_worktree import is_git_worktree_task, worker_id_for_task
from devflow.control_room.models import TaskRecord
from devflow.control_room.paths import workspaces_dir, worktree_path


def runtime_workspace_path(root: Path, task: TaskRecord) -> Path:
    """Return the Dev-Flow-owned runtime workspace for a task."""
    if is_git_worktree_task(task):
        return worktree_path(root, task.id, worker_id_for_task(task)).resolve()
    return (workspaces_dir(root) / task.id).resolve()
