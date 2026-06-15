from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from devflow.control_room.paths import devflow_dir, relative_path, task_dir
from devflow.control_room.persistence import list_tasks
from devflow.control_room.task_artifacts import (
    ensure_task_baseline_artifacts,
    missing_task_baseline_artifacts,
)


MaintenanceMode = Literal["preview", "apply"]


class MaintenanceError(ValueError):
    pass


@dataclass(frozen=True)
class MaintenanceResult:
    mode: MaintenanceMode
    removed: list[str]
    would_remove: list[str]
    repaired: list[str]
    would_repair: list[str]
    refused: list[str]


DOGFOOD_RUNTIME_DIRS: tuple[str, ...] = ("dogfood",)
DISPOSABLE_TEST_TITLE_MARKERS: tuple[str, ...] = ("dogfood", "smoke")


def reset_dogfood_state(root: Path, *, apply: bool) -> MaintenanceResult:
    candidates = _reset_candidates(root)
    return _remove_candidates(root, candidates, apply=apply)


def reset_test_state(root: Path, *, apply: bool) -> MaintenanceResult:
    candidates = _reset_test_candidates(root)
    return _remove_candidates(root, candidates, apply=apply)


def _remove_candidates(root: Path, candidates: list[Path], *, apply: bool) -> MaintenanceResult:
    refused = [_refusal_detail(root, path) for path in candidates if not _safe_devflow_runtime_path(root, path)]
    if refused:
        return MaintenanceResult(
            mode="apply" if apply else "preview",
            removed=[],
            would_remove=[] if apply else [_display_path(root, path) for path in candidates],
            repaired=[],
            would_repair=[],
            refused=refused,
        )

    if not apply:
        return MaintenanceResult(
            mode="preview",
            removed=[],
            would_remove=[_display_path(root, path) for path in candidates],
            repaired=[],
            would_repair=[],
            refused=[],
        )

    removed: list[str] = []
    removed_worktree_runtime = False
    for path in candidates:
        rel = _display_path(root, path)
        if path.is_symlink() or path.is_file():
            path.unlink()
        else:
            shutil.rmtree(path)
        if rel.startswith(".devflow/worktrees/"):
            removed_worktree_runtime = True
        removed.append(rel)
    if removed_worktree_runtime:
        _prune_git_worktree_metadata(root)
    return MaintenanceResult(
        mode="apply",
        removed=removed,
        would_remove=[],
        repaired=[],
        would_repair=[],
        refused=[],
    )


def _prune_git_worktree_metadata(root: Path) -> None:
    subprocess.run(
        ["git", "worktree", "prune"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )


def repair_state(root: Path, *, apply: bool) -> MaintenanceResult:
    would_repair: list[str] = []
    repaired: list[str] = []
    for task in list_tasks(root):
        path = task_dir(root, task.id)
        missing = [name for name in missing_task_baseline_artifacts(path) if name != "task.yaml"]
        would_repair.extend(relative_path(root, path / name) for name in missing)
        if apply and missing:
            created = ensure_task_baseline_artifacts(
                path,
                task_id=task.id,
                workspace_rel=task.workspace,
                task=task,
            )
            repaired.extend(relative_path(root, path / name) for name in created)
    return MaintenanceResult(
        mode="apply" if apply else "preview",
        removed=[],
        would_remove=[],
        repaired=repaired,
        would_repair=[] if apply else would_repair,
        refused=[],
    )


def _reset_test_candidates(root: Path) -> list[Path]:
    base = devflow_dir(root)
    candidates: list[Path] = []
    for parent_name in ("tasks", "workspaces", "worktrees"):
        parent = base / parent_name
        if parent.exists():
            candidates.extend(sorted(parent.glob("task-*")))
    for name in DOGFOOD_RUNTIME_DIRS:
        path = base / name
        if path.exists():
            candidates.append(path)
    return _dedupe_existing(candidates)


def _reset_candidates(root: Path) -> list[Path]:
    base = devflow_dir(root)
    candidates: list[Path] = []
    for task_id in _disposable_testing_task_ids(root):
        for parent_name in ("tasks", "workspaces", "worktrees"):
            path = base / parent_name / task_id
            if path.exists() or path.is_symlink():
                candidates.append(path)
    candidates.extend(_unsafe_runtime_symlink_candidates(root))
    for name in DOGFOOD_RUNTIME_DIRS:
        path = base / name
        if path.exists():
            candidates.append(path)
    return _dedupe_existing(candidates)


def _unsafe_runtime_symlink_candidates(root: Path) -> list[Path]:
    base = devflow_dir(root)
    candidates: list[Path] = []
    for parent_name in ("tasks", "workspaces", "worktrees"):
        parent = base / parent_name
        if not parent.exists():
            continue
        for path in sorted(parent.glob("task-*")):
            if path.is_symlink() and not _safe_devflow_runtime_path(root, path):
                candidates.append(path)
    return candidates


def _disposable_testing_task_ids(root: Path) -> list[str]:
    task_ids: list[str] = []
    for task in list_tasks(root):
        if not _is_disposable_testing_task(task):
            continue
        task_ids.append(task.id)
    return sorted(task_ids)


def _is_disposable_testing_task(task: object) -> bool:
    status = str(getattr(task, "status", ""))
    close_outcome = str(getattr(task, "close_outcome", "") or "")
    title = str(getattr(task, "title", "") or "").lower()
    close_reason = str(getattr(task, "close_reason", "") or "").lower()
    if status == "promoted":
        return False
    if status == "closed" and close_outcome == "evidence-only" and "dogfood" in close_reason:
        return True
    return any(marker in title for marker in DISPOSABLE_TEST_TITLE_MARKERS)


def _dedupe_existing(paths: list[Path]) -> list[Path]:
    seen: set[Path] = set()
    result: list[Path] = []
    for path in paths:
        if not path.exists() and not path.is_symlink():
            continue
        key = path.absolute()
        if key in seen:
            continue
        seen.add(key)
        result.append(path)
    return result


def _safe_devflow_runtime_path(root: Path, path: Path) -> bool:
    base = devflow_dir(root).resolve()
    if path.is_symlink():
        try:
            path.resolve(strict=True).relative_to(base)
        except (FileNotFoundError, ValueError):
            return False
        return True
    try:
        resolved = path.resolve(strict=True)
    except FileNotFoundError:
        return False
    try:
        resolved.relative_to(base)
    except ValueError:
        return False
    rel = resolved.relative_to(base).as_posix()
    if rel in DOGFOOD_RUNTIME_DIRS:
        return True
    for parent in ("tasks", "workspaces", "worktrees"):
        if rel.startswith(f"{parent}/task-"):
            return True
    return False


def _refusal_detail(root: Path, path: Path) -> str:
    rel = _display_path(root, path)
    try:
        path.resolve(strict=True).relative_to(devflow_dir(root).resolve())
    except (FileNotFoundError, ValueError):
        return f"{rel} escapes .devflow"
    return f"{rel} is not an allowlisted runtime artifact"


def _display_path(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()
