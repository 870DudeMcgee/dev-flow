from __future__ import annotations

import fnmatch
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from devflow.control_room.paths import workspaces_dir
from devflow.control_room.persistence import get_task


class TaskArtifactOpenError(ValueError):
    pass


@dataclass(frozen=True)
class TaskOpenCandidate:
    path: Path
    relative_path: Path
    sort_key: tuple[int, int, str]


@dataclass(frozen=True)
class TaskOpenSelection:
    root: Path
    task_id: str
    workspace: Path
    candidates: tuple[TaskOpenCandidate, ...]
    selected: TaskOpenCandidate | None


def select_task_open_artifact(
    root: Path,
    task_id: str,
    worker: str | None = None,
    raw: bool = False,
) -> TaskOpenSelection:
    try:
        get_task(root, task_id)
    except KeyError as exc:
        raise TaskArtifactOpenError(f"Task '{task_id}' not found.") from exc

    workspace = (workspaces_dir(root) / task_id).resolve()
    if not workspace.exists() or not workspace.is_dir():
        raise TaskArtifactOpenError(f"Task workspace not found at {workspace}")

    all_candidate_files: list[Path] = []
    for path in workspace.rglob("*"):
        if not path.is_file():
            continue
        try:
            path.resolve().relative_to(workspace)
        except ValueError:
            continue
        all_candidate_files.append(path)

    sorted_files = sorted(
        all_candidate_files,
        key=lambda path: _sort_key(path, workspace=workspace, worker=worker, raw=raw),
    )
    candidates = tuple(
        TaskOpenCandidate(
            path=path,
            relative_path=path.relative_to(workspace),
            sort_key=_sort_key(path, workspace=workspace, worker=worker, raw=raw),
        )
        for path in sorted_files
        if _sort_key(path, workspace=workspace, worker=worker, raw=raw)[1] < 9
    )

    return TaskOpenSelection(
        root=root,
        task_id=task_id,
        workspace=workspace,
        candidates=candidates,
        selected=candidates[0] if candidates else None,
    )


def render_task_open_candidates(selection: TaskOpenSelection) -> list[str]:
    if not selection.candidates:
        return ["No candidate files found."]
    lines = ["Candidate output files in priority order:"]
    lines.extend(
        f"{index}. {candidate.relative_path}"
        for index, candidate in enumerate(selection.candidates, start=1)
    )
    return lines


def open_task_artifact(path: Path) -> bool:
    try:
        if sys.platform == "darwin":
            subprocess.run(["open", str(path)], check=True)
            return True
        if sys.platform.startswith("linux"):
            subprocess.run(["xdg-open", str(path)], check=True)
            return True
        if sys.platform == "win32" and hasattr(os, "startfile"):
            os.startfile(str(path))  # type: ignore[attr-defined]
            return True
    except Exception:
        return False
    return False


def _sort_key(path: Path, *, workspace: Path, worker: str | None, raw: bool) -> tuple[int, int, str]:
    rel_path = path.relative_to(workspace).as_posix()
    rel_path_lower = rel_path.lower()
    name = path.name.lower()
    parts = rel_path_lower.split("/")

    primary_rank = 3
    if worker:
        worker_lower = worker.lower()
        if len(parts) >= 3 and parts[0] == "local-workers" and parts[1] == worker_lower:
            if name == "response.raw.md":
                primary_rank = 0 if raw else 1
            elif name == "response.md":
                primary_rank = 1 if raw else 0
            else:
                primary_rank = 2

    if raw:
        patterns = [
            "local-workers/*/response.raw.md",
            "local-workers/*/response.md",
            "*response.raw.md",
            "*response*.md",
            "*review*.md",
            "*.log",
            "*.md",
            "*.txt",
        ]
    else:
        patterns = [
            "local-workers/*/response.md",
            "local-workers/*/response.raw.md",
            "*response.md",
            "*review.md",
            "*.md",
            "*.txt",
            "logs/*.log",
            "*.log",
        ]

    secondary_rank = len(patterns) + 1
    for index, pattern in enumerate(patterns):
        if fnmatch.fnmatch(rel_path_lower, pattern) or fnmatch.fnmatch(name, pattern):
            secondary_rank = index
            break

    return (primary_rank, secondary_rank, rel_path_lower)
