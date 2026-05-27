from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from devflow.control_room.paths import workspace_path, worktrees_dir


@dataclass(frozen=True)
class Workspace:
    path: Path
    kind: str
    branch_name: str | None = None


def create_workspace(root: Path, task_id: str) -> Workspace:
    worktrees_dir(root).mkdir(parents=True, exist_ok=True)
    workspace = workspace_path(root, task_id)
    branch = f"devflow/{task_id}"

    if workspace.exists():
        return Workspace(path=workspace, kind=_existing_kind(workspace), branch_name=branch)

    if _can_create_git_worktree(root):
        result = subprocess.run(
            ["git", "worktree", "add", "-b", branch, str(workspace), "HEAD"],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        if result.returncode == 0:
            return Workspace(path=workspace, kind="git_worktree", branch_name=branch)

    workspace.mkdir(parents=True, exist_ok=True)
    return Workspace(path=workspace, kind="directory", branch_name=None)


def _can_create_git_worktree(root: Path) -> bool:
    inside = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        return False

    head = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD"],
        cwd=root,
        text=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return head.returncode == 0


def _existing_kind(workspace: Path) -> str:
    git_marker = workspace / ".git"
    if git_marker.exists():
        return "git_worktree"
    return "directory"
