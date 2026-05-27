from __future__ import annotations

import sys


def worktree_create_command(task_file: str, agent: str) -> None:
    from devflow.worktrees import create_worktree

    try:
        record = create_worktree(task_file, agent=agent)
    except Exception as exc:
        print(f"Error: {exc}")
        sys.exit(1)

    print("Worktree created")
    print(f"task_id: {record.get('task_id')}")
    print(f"owner: {record.get('owner')}")
    print(f"branch: {record.get('branch')}")
    print(f"path: {record.get('path')}")
    print(f"base_sha: {record.get('base_sha')}")


def worktree_status_command() -> None:
    from devflow.worktrees import list_worktrees

    records = list_worktrees()
    if not records:
        print("No devflow worktrees recorded.")
        return

    print(f"{'Task':<8} {'Owner':<14} {'Status':<10} {'Branch':<32} Path")
    print("-" * 92)
    for record in records:
        print(
            f"{record.get('task_id', ''):<8} "
            f"{record.get('owner', ''):<14} "
            f"{record.get('status', ''):<10} "
            f"{record.get('branch', ''):<32} "
            f"{record.get('path', '')}"
        )


def worktree_remove_command(task_file: str, keep_artifacts: bool = False) -> None:
    from devflow.worktrees import remove_worktree

    try:
        record = remove_worktree(task_file, keep_artifacts=keep_artifacts)
    except Exception as exc:
        print(f"Error: {exc}")
        sys.exit(1)

    print("Worktree removed")
    print(f"task_id: {record.get('task_id')}")
    print(f"owner: {record.get('owner')}")
    print(f"branch: {record.get('branch')}")
    print(f"path: {record.get('path')}")
    print(f"artifacts: {'kept' if keep_artifacts else 'removed'}")
