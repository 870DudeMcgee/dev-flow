from __future__ import annotations

import datetime
import json
import os
import re
import shutil
import subprocess
from typing import Any, Dict, List

from devflow.manager import parse_task_file


INDEX_PATH = os.path.join(".devflow", "worktrees", "index.json")


def _utc_now() -> str:
    return datetime.datetime.now(datetime.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip()).strip("-")
    return slug or "worktree"


def _run_git(args: List[str], root_dir: str) -> tuple[int, str, str]:
    proc = subprocess.run(
        ["git", *args],
        cwd=root_dir,
        text=True,
        capture_output=True,
    )
    return proc.returncode, proc.stdout, proc.stderr


def _ensure_index(root_dir: str) -> str:
    index_path = os.path.join(root_dir, INDEX_PATH)
    os.makedirs(os.path.dirname(index_path), exist_ok=True)
    if not os.path.exists(index_path):
        with open(index_path, "w", encoding="utf-8") as handle:
            json.dump({"version": 1, "worktrees": []}, handle, indent=2)
            handle.write("\n")
    return index_path


def _read_index(root_dir: str) -> Dict[str, Any]:
    index_path = _ensure_index(root_dir)
    with open(index_path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data.get("worktrees"), list):
        data["worktrees"] = []
    return data


def _write_index(root_dir: str, data: Dict[str, Any]) -> None:
    index_path = _ensure_index(root_dir)
    with open(index_path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=True)
        handle.write("\n")


def _read_task(task_file: str) -> tuple[str, Dict[str, Any]]:
    if not os.path.exists(task_file):
        raise FileNotFoundError(f"task file does not exist: {task_file}")
    with open(task_file, "r", encoding="utf-8") as handle:
        content = handle.read()
    return content, parse_task_file(content)


def _default_branch(task: Dict[str, Any], agent: str) -> str:
    task_id = str(task.get("task_id", "000"))
    owner = _slugify(agent)
    return f"devflow/worktree-{task_id}-{owner}"


def _default_path(task: Dict[str, Any], agent: str) -> str:
    task_id = str(task.get("task_id", "000"))
    owner = _slugify(agent)
    return os.path.join(".devflow", "worktrees", f"{task_id}-{owner}")


def _branch_exists(branch: str, root_dir: str) -> bool:
    code, _, _ = _run_git(["rev-parse", "--verify", f"refs/heads/{branch}"], root_dir)
    return code == 0


def _git_worktree_paths(root_dir: str) -> set[str]:
    code, out, _ = _run_git(["worktree", "list", "--porcelain"], root_dir)
    if code != 0:
        return set()
    paths: set[str] = set()
    for line in out.splitlines():
        if line.startswith("worktree "):
            paths.add(os.path.abspath(line.split(" ", 1)[1].strip()))
    return paths


def create_worktree(task_file: str, agent: str, root_dir: str = ".") -> Dict[str, Any]:
    """Create an isolated git worktree for a task and record metadata."""
    root_dir = os.path.abspath(root_dir)
    _, task = _read_task(task_file)
    task_id = str(task.get("task_id", "000"))
    branch = str(task.get("branch") or "").strip() or _default_branch(task, agent)
    relative_path = _default_path(task, agent)
    absolute_path = os.path.join(root_dir, relative_path)

    index = _read_index(root_dir)
    for record in index["worktrees"]:
        if record.get("task_file") == task_file and record.get("status") == "active":
            raise ValueError(f"active worktree already exists for task {task_id}: {record.get('path')}")

    if os.path.exists(absolute_path):
        raise FileExistsError(f"worktree path already exists: {relative_path}")

    code, base_sha, err = _run_git(["rev-parse", "HEAD"], root_dir)
    if code != 0:
        raise RuntimeError(f"could not resolve base sha: {err.strip()}")
    base_sha = base_sha.strip()

    os.makedirs(os.path.dirname(absolute_path), exist_ok=True)
    if _branch_exists(branch, root_dir):
        add_args = ["worktree", "add", relative_path, branch]
    else:
        add_args = ["worktree", "add", "-b", branch, relative_path, base_sha]
    add_code, _, add_err = _run_git(add_args, root_dir)
    if add_code != 0:
        raise RuntimeError(f"could not create worktree: {add_err.strip()}")

    record = {
        "task_id": task_id,
        "task_file": task_file,
        "title": task.get("title", ""),
        "owner": agent,
        "branch": branch,
        "path": relative_path,
        "base_sha": base_sha,
        "status": "active",
        "created_at": _utc_now(),
        "removed_at": "",
    }
    index["worktrees"].append(record)
    _write_index(root_dir, index)
    return record


def list_worktrees(root_dir: str = ".") -> List[Dict[str, Any]]:
    """Return recorded worktrees with live/missing path status refreshed."""
    root_dir = os.path.abspath(root_dir)
    index = _read_index(root_dir)
    active_paths = _git_worktree_paths(root_dir)
    records: List[Dict[str, Any]] = []
    changed = False
    for record in index["worktrees"]:
        copy = dict(record)
        if copy.get("status") == "active":
            absolute_path = os.path.abspath(os.path.join(root_dir, str(copy.get("path", ""))))
            if absolute_path not in active_paths or not os.path.exists(absolute_path):
                copy["status"] = "missing"
                record["status"] = "missing"
                changed = True
        records.append(copy)
    if changed:
        _write_index(root_dir, index)
    return sorted(records, key=lambda item: (str(item.get("task_id", "")), str(item.get("created_at", ""))))


def remove_worktree(task_file: str, keep_artifacts: bool = False, root_dir: str = ".") -> Dict[str, Any]:
    """Remove the active worktree for a task and update metadata."""
    root_dir = os.path.abspath(root_dir)
    _, task = _read_task(task_file)
    task_id = str(task.get("task_id", "000"))
    index = _read_index(root_dir)

    selected: Dict[str, Any] | None = None
    for record in reversed(index["worktrees"]):
        if record.get("task_file") == task_file and record.get("status") in {"active", "missing"}:
            selected = record
            break
    if selected is None:
        raise ValueError(f"no active worktree recorded for task {task_id}")

    relative_path = str(selected.get("path", ""))
    absolute_path = os.path.abspath(os.path.join(root_dir, relative_path))
    if os.path.exists(absolute_path):
        code, _, err = _run_git(["worktree", "remove", "--force", relative_path], root_dir)
        if code != 0:
            raise RuntimeError(f"could not remove worktree: {err.strip()}")

    if not keep_artifacts:
        artifact_dir = os.path.join(root_dir, ".devflow", "artifacts", task_id)
        if os.path.isdir(artifact_dir):
            shutil.rmtree(artifact_dir)

    selected["status"] = "removed"
    selected["removed_at"] = _utc_now()
    _write_index(root_dir, index)
    return dict(selected)