from __future__ import annotations

import difflib
import shutil
import subprocess
from pathlib import Path
from typing import Any

from devflow.control_room.models import TaskRecord
from devflow.control_room.paths import (
    absolute_path,
    relative_path,
    task_dir,
    workspaces_dir,
)
from devflow.control_room.persistence import (
    get_task,
    utc_now,
)
from devflow.control_room.git_state import inspect_git_state
from devflow.control_room.readiness import format_promotion_refusal, promotion_readiness_errors
from devflow.control_room.git_worktree import build_git_promotion_preview, is_git_worktree_task, promote_git_worktree
from devflow.control_room.task_lifecycle import record_task_update


def preview_task_promotion(root: Path, task_id: str) -> dict[str, Any]:
    git_state = inspect_git_state(root)
    if git_state.operation_in_progress:
        raise ValueError(f"Refusing promotion preview: Git {git_state.operation_in_progress} is in progress.")
    task = get_task(root, task_id)
    if is_git_worktree_task(task):
        return build_git_promotion_preview(root, task)
    baseline = promotion_baseline(root, task)
    workspace = absolute_path(root, task.workspace).resolve()
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
        "baseline": baseline,
        "added": added_files,
        "modified": modified_files,
        "deleted": deleted_files,
        "diffs": diffs,
    }


def current_main_head(root: Path) -> str | None:
    try:
        inside = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if inside.returncode != 0 or inside.stdout.strip() != "true":
            return None
        head_proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if head_proc.returncode != 0:
            return None
    except (OSError, subprocess.SubprocessError):
        return None
    return head_proc.stdout.strip() or None


def promotion_baseline(root: Path, task: TaskRecord) -> dict[str, str | None]:
    task_baseline = task.workspace_commit
    current_head = current_main_head(root)
    if task_baseline and current_head:
        status = "unchanged" if task_baseline == current_head else "changed"
    else:
        status = "unavailable"
    return {
        "task_baseline_commit": task_baseline,
        "current_main_head": current_head,
        "baseline_status": status,
    }


def format_stale_baseline_refusal(root: Path, task: TaskRecord) -> str | None:
    baseline = promotion_baseline(root, task)
    task_baseline = baseline["task_baseline_commit"]
    current_head = baseline["current_main_head"]
    status = baseline["baseline_status"]
    if status == "unchanged":
        return None
    if status == "changed":
        title = "Refusing promotion: task baseline is stale."
        reason = "Current main checkout HEAD differs from the task baseline commit."
    else:
        title = "Refusing promotion: task baseline cannot be verified."
        reason = "Task baseline commit or current main checkout HEAD is unavailable."
    return "\n".join(
        [
            title,
            f"task_id: {task.id}",
            f"task_baseline_commit: {_display_commit(task_baseline)}",
            f"current_main_head: {_display_commit(current_head)}",
            f"reason: {reason}",
            "next_safe_action: Review promote-preview, re-run or rebase the task from current main, or use --force-stale-baseline only after manual conflict review.",
        ]
    )


def main_checkout_has_uncommitted_changes(root: Path) -> bool:
    try:
        inside = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if inside.returncode != 0 or inside.stdout.strip() != "true":
            raise ValueError("Error: Repository root is not a git repository.")
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError("Error: Repository root is not a git repository.") from exc

    try:
        status_proc = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if status_proc.returncode != 0:
            raise ValueError("Error: Git status command failed.")
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError("Error: Git status command failed.") from exc

    dirty = False
    for line in status_proc.stdout.splitlines():
        if not line.strip():
            continue
        path_part = line[3:].strip()
        if path_part.startswith('"') and path_part.endswith('"'):
            path_part = path_part[1:-1]
        if path_part.startswith(".devflow/") or path_part == ".devflow":
            continue
        dirty = True
        break

    return dirty


def promote_task(
    root: Path,
    task_id: str,
    force: bool = False,
    apply_deletions: bool = False,
    force_stale_baseline: bool = False,
) -> TaskRecord:
    git_state = inspect_git_state(root)
    if git_state.operation_in_progress:
        raise ValueError(f"Refusing promotion: Git {git_state.operation_in_progress} is in progress.")
    task = get_task(root, task_id)
    task_path = task_dir(root, task_id)
    if promotion_readiness_errors(task, task_path):
        raise ValueError(format_promotion_refusal(task, task_path))

    baseline = promotion_baseline(root, task)
    if baseline["baseline_status"] == "unavailable":
        refusal = format_stale_baseline_refusal(root, task)
        raise ValueError(refusal or "Refusing promotion: task baseline cannot be verified.")
    if baseline["baseline_status"] == "changed" and not force_stale_baseline:
        refusal = format_stale_baseline_refusal(root, task)
        raise ValueError(refusal or "Refusing promotion: task baseline is stale.")

    # Double check dirty repository status to ensure safety
    if not force and main_checkout_has_uncommitted_changes(root):
        raise ValueError("Error: Main checkout has uncommitted changes. Please commit or stash them first, or use --force to bypass.")

    if is_git_worktree_task(task):
        preview = promote_git_worktree(root, task)
        record_task_update(
            root,
            task,
            event_type="task_promoted",
            event_payload={
                "mode": "git_worktree",
                "worker_id": preview["git"]["worker_id"],
                "worker_branch": preview["git"]["worker_branch"],
                "verified_commit": preview["git"]["worker_branch_head"],
                "added": preview["added"],
                "modified": preview["modified"],
                "deleted": preview["deleted"],
                "renamed": preview.get("renamed", []),
            },
            status="promoted",
            updated_at=utc_now(),
            write_readiness=False,
        )
        return task

    workspace = absolute_path(root, task.workspace).resolve()
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

    # Safety checks for all destination paths before copying
    for name in added_files + modified_files:
        dst_path = (root / name).resolve()
        try:
            dst_path.relative_to(root.resolve())
        except ValueError:
            raise ValueError(f"Refusing unsafe promotion: destination path escapes repository root: {name}")

        if _is_ignored_path(dst_path, root):
            raise ValueError(f"Refusing unsafe promotion: destination path is in an ignored/control directory: {name}")

    # Copy added and modified files
    for name in added_files + modified_files:
        src_path = workspace / name
        dst_path = root / name
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_path, dst_path)

    # Delete removed files if explicitly requested and safe
    deleted_applied = []
    if apply_deletions:
        for name in deleted_files:
            dst_path = root / name
            if dst_path.exists():
                try:
                    dst_path.resolve().relative_to(root.resolve())
                except ValueError:
                    continue  # Skip files outside root boundary

                if _is_ignored_path(dst_path, root):
                    continue  # Skip ignored/control paths

                if dst_path.is_file() and not dst_path.is_symlink():
                    dst_path.unlink()
                    deleted_applied.append(name)

    # Update canonical task record and event log
    record_task_update(
        root,
        task,
        event_type="task_promoted",
        event_payload={
            "added": added_files,
            "modified": modified_files,
            "deleted_applied": deleted_applied,
        },
        status="promoted",
        updated_at=utc_now(),
        write_readiness=False,
    )

    return task


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


def _display_commit(commit: str | None) -> str:
    return commit if commit else "unavailable"


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
