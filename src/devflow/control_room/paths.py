from __future__ import annotations

from pathlib import Path


def repo_root(path: Path | None = None) -> Path:
    return (path or Path.cwd()).resolve()


def devflow_dir(root: Path) -> Path:
    return root / ".devflow"


def system_dir(root: Path) -> Path:
    return devflow_dir(root) / "system"


def goals_dir(root: Path) -> Path:
    return devflow_dir(root) / "goals"


def goal_dir(root: Path, goal_id: str) -> Path:
    return goals_dir(root) / goal_id


def system_events_path(root: Path) -> Path:
    return system_dir(root) / "events.jsonl"


def config_path(root: Path) -> Path:
    return devflow_dir(root) / "config.yaml"


def tasks_dir(root: Path) -> Path:
    return devflow_dir(root) / "tasks"


def task_dir(root: Path, task_id: str) -> Path:
    return tasks_dir(root) / task_id


def workspaces_dir(root: Path) -> Path:
    return devflow_dir(root) / "workspaces"


def workspace_path(root: Path, task_id: str) -> Path:
    return workspaces_dir(root) / task_id


def worktrees_dir(root: Path) -> Path:
    return devflow_dir(root) / "worktrees"


def knowledge_dir(root: Path) -> Path:
    return devflow_dir(root) / "knowledge"


def outcome_validations_dir(root: Path) -> Path:
    return devflow_dir(root) / "outcome-validations"


def worktree_path(root: Path, task_id: str, worker_id: str) -> Path:
    return worktrees_dir(root) / task_id / worker_id


def task_workers_dir(root: Path, task_id: str) -> Path:
    return task_dir(root, task_id) / "workers"


def task_worker_dir(root: Path, task_id: str, worker_id: str) -> Path:
    return task_workers_dir(root, task_id) / worker_id


def relative_path(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def absolute_path(root: Path, path: str) -> Path:
    value = Path(path)
    return value if value.is_absolute() else root / value
