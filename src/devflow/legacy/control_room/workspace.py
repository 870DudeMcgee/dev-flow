from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

import subprocess
from devflow.legacy.control_room.paths import workspace_path, workspaces_dir


@dataclass(frozen=True)
class Workspace:
    path: Path
    kind: str
    base_ref: str | None = None
    branch_name: str | None = None
    commit_sha: str | None = None
    dirty: bool = False
    skipped_symlinks: tuple[str, ...] = ()


def create_workspace(root: Path, task_id: str) -> Workspace:
    workspaces_dir(root).mkdir(parents=True, exist_ok=True)
    workspace = workspace_path(root, task_id)

    is_git = False
    branch_name = None
    commit_sha = None
    dirty = False

    try:
        inside = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if inside.returncode == 0 and inside.stdout.strip() == "true":
            is_git = True
    except (OSError, subprocess.SubprocessError):
        pass

    if is_git:
        try:
            branch_proc = subprocess.run(
                ["git", "branch", "--show-current"],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if branch_proc.returncode == 0 and branch_proc.stdout.strip():
                branch_name = branch_proc.stdout.strip()
            else:
                head_proc = subprocess.run(
                    ["git", "rev-parse", "--short", "HEAD"],
                    cwd=root,
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if head_proc.returncode == 0:
                    branch_name = f"detached:{head_proc.stdout.strip()}"

            commit_proc = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if commit_proc.returncode == 0:
                commit_sha = commit_proc.stdout.strip()

            status_proc = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if status_proc.returncode == 0:
                dirty_lines = []
                for line in status_proc.stdout.splitlines():
                    stripped = line.strip()
                    if not stripped:
                        continue
                    # XY PATH format
                    path_part = stripped[3:].strip() if len(stripped) > 3 else stripped
                    if path_part.startswith(".devflow") or path_part.startswith('".devflow'):
                        continue
                    dirty_lines.append(line)
                if dirty_lines:
                    dirty = True
        except (OSError, subprocess.SubprocessError):
            pass

    if workspace.exists():
        return Workspace(
            path=workspace,
            kind="directory",
            base_ref=branch_name,
            branch_name=branch_name,
            commit_sha=commit_sha,
            dirty=dirty,
        )

    workspace.mkdir(parents=True, exist_ok=True)
    skipped_symlinks = _copy_scratchpad(root, workspace)
    return Workspace(
        path=workspace,
        kind="directory",
        base_ref=branch_name,
        branch_name=branch_name,
        commit_sha=commit_sha,
        dirty=dirty,
        skipped_symlinks=skipped_symlinks,
    )


def _copy_scratchpad(root: Path, workspace: Path) -> tuple[str, ...]:
    exclusions = {
        ".git",
        ".devflow",
        "node_modules",
        "dist",
        "build",
        "coverage",
        ".venv",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
    }
    skipped_symlinks: list[str] = []
    for child in root.iterdir():
        if child.name in exclusions or child.name.startswith(".venv"):
            continue
        if child.is_symlink():
            skipped_symlinks.append(child.name)
            continue
        destination = workspace / child.name
        if child.is_dir():
            shutil.copytree(child, destination, ignore=_copy_ignore(root, exclusions, skipped_symlinks))
        elif child.is_file():
            shutil.copy2(child, destination)
    return tuple(skipped_symlinks)


def _copy_ignore(root: Path, exclusions: set[str], skipped_symlinks: list[str]):
    def ignore(directory: str, names: list[str]) -> set[str]:
        ignored = set()
        directory_path = Path(directory)
        for name in names:
            candidate = directory_path / name
            if name in exclusions or name.startswith(".venv"):
                ignored.add(name)
            elif candidate.is_symlink():
                ignored.add(name)
                skipped_symlinks.append(str(candidate.relative_to(root)))
        return ignored

    return ignore
