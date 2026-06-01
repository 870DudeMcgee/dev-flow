from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from devflow.control_room.models import TASK_SCHEMA_VERSION, TaskRecord
from devflow.control_room.paths import absolute_path, relative_path, task_worker_dir, worktree_path, worktrees_dir
from devflow.control_room.persistence import atomic_write_text, utc_now
from devflow.control_room.workspace import Workspace


DEFAULT_BASE_BRANCH = "main"
DEFAULT_WORKER_ID = "shell"


class GitWorktreeError(ValueError):
    pass


def create_git_worktree(root: Path, task_id: str, worker_id: str = DEFAULT_WORKER_ID) -> Workspace:
    _require_git_repo(root)
    base_commit = _git_stdout(root, ["rev-parse", "--verify", f"{DEFAULT_BASE_BRANCH}^{{commit}}"])
    branch = worker_branch_name(task_id, worker_id)
    if branch_exists(root, branch):
        raise GitWorktreeError(f"Worker branch already exists: {branch}")
    path = worktree_path(root, task_id, worker_id)
    if path.exists():
        raise GitWorktreeError(f"Worker worktree already exists: {relative_path(root, path)}")
    path.parent.mkdir(parents=True, exist_ok=True)
    _git_stdout(root, ["worktree", "add", "-b", branch, str(path), base_commit])
    return Workspace(
        path=path,
        kind="git_worktree",
        branch_name=branch,
        commit_sha=base_commit,
        dirty=False,
    )


def worker_branch_name(task_id: str, worker_id: str = DEFAULT_WORKER_ID) -> str:
    safe_worker_id = worker_id.replace("/", "-")
    return f"devflow/{task_id}/{safe_worker_id}"


def worker_id_for_task(task: TaskRecord) -> str:
    if task.branch_name and task.branch_name.startswith(f"devflow/{task.id}/"):
        return task.branch_name.rsplit("/", 1)[-1]
    if task.worker and task.worker != "shell":
        return task.worker.replace("/", "-")
    return DEFAULT_WORKER_ID


def is_git_worktree_task(task: TaskRecord) -> bool:
    return task.workspace_kind == "git_worktree"


def refresh_git_worker_evidence(root: Path, task: TaskRecord, worker_id: str | None = None) -> dict[str, Any]:
    if not is_git_worktree_task(task):
        raise GitWorktreeError(f"Task {task.id} is not backed by a Git worktree")
    worker_id = worker_id or worker_id_for_task(task)
    state = git_worker_state(root, task, worker_id)
    worker_path = task_worker_dir(root, task.id, worker_id)
    worker_path.mkdir(parents=True, exist_ok=True)
    atomic_write_text(worker_path / "git.json", json.dumps(state, sort_keys=True, indent=2) + "\n")

    diff_patch = _diff_patch(root, state)
    atomic_write_text(worker_path / "diff.patch", diff_patch)

    diff_summary = _diff_summary(root, task, state)
    atomic_write_text(worker_path / "diff-summary.json", json.dumps(diff_summary, sort_keys=True, indent=2) + "\n")
    return state


def git_worker_state(root: Path, task: TaskRecord, worker_id: str | None = None) -> dict[str, Any]:
    worker_id = worker_id or worker_id_for_task(task)
    branch = task.branch_name or worker_branch_name(task.id, worker_id)
    workspace = absolute_path(root, task.workspace).resolve()
    if not workspace.is_dir():
        raise GitWorktreeError(f"Worker worktree does not exist: {workspace}")
    head = _git_stdout(workspace, ["rev-parse", "HEAD"])
    dirty = _worktree_dirty(workspace)
    return {
        "schema_version": TASK_SCHEMA_VERSION,
        "task_id": task.id,
        "worker_id": worker_id,
        "base_branch": DEFAULT_BASE_BRANCH,
        "base_commit": task.workspace_commit,
        "worker_branch": branch,
        "worktree_path": relative_path(root, workspace),
        "head_commit": head,
        "dirty": dirty,
        "updated_at": utc_now().isoformat(),
    }


def build_git_promotion_preview(root: Path, task: TaskRecord) -> dict[str, Any]:
    worker_id = worker_id_for_task(task)
    state = refresh_git_worker_evidence(root, task, worker_id)
    branch = state["worker_branch"]
    base_commit = state["base_commit"]
    main_head = current_head(root)
    worker_head = branch_head(root, branch)
    merge_base = merge_base_commit(root, branch)
    conflict_prediction, conflict_files = predict_conflicts(root, branch)
    summary = _diff_summary(root, task, state)
    worker_path = task_worker_dir(root, task.id, worker_id)
    diff_patch_path = worker_path / "diff.patch"
    diff_text = diff_patch_path.read_text(encoding="utf-8") if diff_patch_path.exists() else ""
    verification_status = task.verification_status
    readiness = _git_preview_readiness(root, task, state, worker_head, conflict_prediction)
    baseline_stale = bool(base_commit and main_head and base_commit != main_head)
    preview = {
        "schema_version": TASK_SCHEMA_VERSION,
        "task_id": task.id,
        "worker_id": worker_id,
        "base_commit": base_commit,
        "main_current_head": main_head,
        "worker_branch": branch,
        "worker_branch_head": worker_head,
        "merge_base": merge_base,
        "baseline_stale": baseline_stale,
        "changed_files": summary["changed_files"],
        "added": summary["added_files"],
        "modified": summary["modified_files"],
        "deleted": summary["deleted_files"],
        "renamed": summary["renamed_files"],
        "untracked": summary["untracked_files"],
        "binary": summary["binary_files"],
        "conflict_prediction": conflict_prediction,
        "conflict_files": conflict_files,
        "verification_status": verification_status,
        "promotion_readiness": readiness,
        "generated_at": utc_now().isoformat(),
    }
    atomic_write_text(worker_path / "promotion-preview.json", json.dumps(preview, sort_keys=True, indent=2) + "\n")
    return {
        "mode": "git_worktree",
        "task_id": task.id,
        "baseline": {
            "task_baseline_commit": base_commit,
            "current_main_head": main_head,
            "baseline_status": "changed" if baseline_stale else "unchanged" if base_commit and main_head else "unavailable",
        },
        "added": preview["added"],
        "modified": preview["modified"],
        "deleted": preview["deleted"],
        "renamed": preview["renamed"],
        "untracked": preview["untracked"],
        "binary": preview["binary"],
        "diffs": {"git-diff": diff_text} if diff_text else {},
        "git": preview,
    }


def git_worktree_readiness_errors(root: Path, task: TaskRecord) -> list[str]:
    if not is_git_worktree_task(task):
        return []
    errors: list[str] = []
    worker_id = worker_id_for_task(task)
    branch = task.branch_name or worker_branch_name(task.id, worker_id)
    workspace = absolute_path(root, task.workspace).resolve()
    expected = worktree_path(root, task.id, worker_id).resolve()
    if workspace != expected:
        errors.append(f"worker worktree path is '{relative_path(root, workspace)}', expected '{relative_path(root, expected)}'")
    if not workspace.is_dir():
        errors.append(f"worker worktree is missing: {relative_path(root, expected)}")
    if not branch_exists(root, branch):
        errors.append(f"worker branch is missing: {branch}")
        return errors
    if task.workspace_commit and not commit_exists(root, task.workspace_commit):
        errors.append(f"base commit does not exist: {task.workspace_commit}")
    if task.workspace_commit and commit_exists(root, task.workspace_commit):
        if not _merge_base_is_ancestor(root, task.workspace_commit, branch):
            errors.append(f"worker branch does not descend from base commit: {task.workspace_commit}")
    verification_path = root / ".devflow" / "tasks" / task.id / "verification.json"
    verification = _read_json_object(verification_path)
    verified_commit = verification.get("verified_commit") if verification else None
    if task.verification_status == "passed":
        if not isinstance(verified_commit, str) or not verified_commit:
            errors.append("verified commit is missing from verification.json")
        else:
            head = branch_head(root, branch)
            if head and head != verified_commit:
                errors.append("worker HEAD differs from verified commit")
        if workspace.is_dir() and _worktree_dirty(workspace):
            errors.append("worker worktree is dirty after verification")
    return errors


def git_doctor_checks(root: Path, task: TaskRecord) -> list[tuple[str, bool, str]]:
    if not is_git_worktree_task(task):
        return []
    worker_id = worker_id_for_task(task)
    branch = task.branch_name or worker_branch_name(task.id, worker_id)
    workspace = absolute_path(root, task.workspace).resolve()
    expected = worktree_path(root, task.id, worker_id).resolve()
    checks: list[tuple[str, bool, str]] = []
    checks.append((
        f"strict: {task.id} worker branch",
        branch_exists(root, branch),
        branch if branch_exists(root, branch) else f"missing branch {branch}",
    ))
    worktree_ok = workspace.is_dir() and workspace == expected
    checks.append((
        f"strict: {task.id} worker worktree",
        worktree_ok,
        relative_path(root, workspace) if worktree_ok else f"expected {relative_path(root, expected)}",
    ))
    under_worktrees = False
    try:
        workspace.relative_to(worktrees_dir(root).resolve())
        under_worktrees = True
    except ValueError:
        under_worktrees = False
    checks.append((
        f"strict: {task.id} worktree path under .devflow/worktrees",
        under_worktrees,
        relative_path(root, workspace),
    ))
    if task.workspace_commit:
        checks.append((
            f"strict: {task.id} base commit exists",
            commit_exists(root, task.workspace_commit),
            task.workspace_commit,
        ))
    if branch_exists(root, branch) and task.workspace_commit and commit_exists(root, task.workspace_commit):
        checks.append((
            f"strict: {task.id} branch descends from base",
            _merge_base_is_ancestor(root, task.workspace_commit, branch),
            task.workspace_commit,
        ))
    if task.verification_status == "passed" and branch_exists(root, branch):
        verification = _read_json_object(root / ".devflow" / "tasks" / task.id / "verification.json")
        verified_commit = verification.get("verified_commit") if verification else None
        head = branch_head(root, branch)
        checks.append((
            f"strict: {task.id} verified commit matches worker HEAD",
            bool(verified_commit and head and verified_commit == head),
            f"verified={verified_commit or 'missing'} head={head or 'missing'}",
        ))
        if workspace.is_dir():
            dirty = _worktree_dirty(workspace)
            checks.append((
                f"strict: {task.id} verified worktree clean",
                not dirty,
                "clean" if not dirty else "dirty after verification",
            ))
    return checks


def promote_git_worktree(root: Path, task: TaskRecord) -> dict[str, Any]:
    preview = build_git_promotion_preview(root, task)
    git_preview = preview["git"]
    if git_preview["conflict_prediction"] != "clean":
        files = git_preview.get("conflict_files") or []
        file_lines = "\n".join(f"  {name}" for name in files) if files else "  unknown"
        raise GitWorktreeError(
            "promotion refused: merge conflict predicted\n"
            "conflict files:\n"
            f"{file_lines}\n"
            "suggested next action:\n"
            f"  devflow task create \"Resolve conflict for {task.id} worker {git_preview['worker_id']}\""
        )
    branch = git_preview["worker_branch"]
    proc = _run_git(root, ["merge", "--no-ff", "--no-commit", branch], check=False)
    if proc.returncode != 0:
        _run_git(root, ["merge", "--abort"], check=False)
        detail = (proc.stderr or proc.stdout or "git merge failed").strip()
        raise GitWorktreeError(f"Git-native promotion failed: {detail}")
    return preview


def branch_exists(root: Path, branch: str) -> bool:
    return _run_git(root, ["show-ref", "--verify", "--quiet", f"refs/heads/{branch}"], check=False).returncode == 0


def branch_head(root: Path, branch: str) -> str | None:
    proc = _run_git(root, ["rev-parse", "--verify", f"{branch}^{{commit}}"], check=False)
    return proc.stdout.strip() if proc.returncode == 0 and proc.stdout.strip() else None


def current_head(root: Path) -> str | None:
    proc = _run_git(root, ["rev-parse", "HEAD"], check=False)
    return proc.stdout.strip() if proc.returncode == 0 and proc.stdout.strip() else None


def merge_base_commit(root: Path, branch: str) -> str | None:
    proc = _run_git(root, ["merge-base", "HEAD", branch], check=False)
    return proc.stdout.strip() if proc.returncode == 0 and proc.stdout.strip() else None


def commit_exists(root: Path, commit: str) -> bool:
    return _run_git(root, ["cat-file", "-e", f"{commit}^{{commit}}"], check=False).returncode == 0


def predict_conflicts(root: Path, branch: str) -> tuple[str, list[str]]:
    proc = _run_git(root, ["merge-tree", "--write-tree", "--messages", "HEAD", branch], check=False)
    if proc.returncode == 0:
        return "clean", []
    files: set[str] = set()
    for line in (proc.stdout + "\n" + proc.stderr).splitlines():
        if "CONFLICT" in line and " in " in line:
            files.add(line.rsplit(" in ", 1)[-1].strip())
        elif "\t" in line:
            parts = line.split("\t")
            if parts[-1]:
                files.add(parts[-1].strip())
    return "conflict", sorted(files)


def _require_git_repo(root: Path) -> None:
    proc = _run_git(root, ["rev-parse", "--is-inside-work-tree"], check=False)
    if proc.returncode != 0 or proc.stdout.strip() != "true":
        raise GitWorktreeError("Git worktree tasks require a git repository.")


def _git_stdout(cwd: Path, args: list[str]) -> str:
    proc = _run_git(cwd, args, check=True)
    return proc.stdout.strip()


def _run_git(cwd: Path, args: list[str], check: bool) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=30)
    if check and proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "git command failed").strip()
        raise GitWorktreeError(detail)
    return proc


def _worktree_dirty(workspace: Path) -> bool:
    proc = _run_git(workspace, ["status", "--porcelain"], check=False)
    return bool(proc.stdout.strip()) if proc.returncode == 0 else True


def _diff_patch(root: Path, state: dict[str, Any]) -> str:
    workspace = absolute_path(root, state["worktree_path"])
    base_commit = state.get("base_commit")
    if not base_commit:
        return ""
    proc = _run_git(workspace, ["diff", "--binary", f"{base_commit}..HEAD"], check=False)
    committed = proc.stdout if proc.returncode == 0 else ""
    dirty_proc = _run_git(workspace, ["diff", "--binary", "HEAD"], check=False)
    dirty = dirty_proc.stdout if dirty_proc.returncode == 0 else ""
    return committed + dirty


def _diff_summary(root: Path, task: TaskRecord, state: dict[str, Any]) -> dict[str, Any]:
    workspace = absolute_path(root, state["worktree_path"])
    base_commit = state.get("base_commit")
    added: list[str] = []
    modified: list[str] = []
    deleted: list[str] = []
    renamed: list[dict[str, str]] = []
    binary: list[str] = []
    if base_commit:
        proc = _run_git(workspace, ["diff", "--name-status", "--find-renames", f"{base_commit}..HEAD"], check=False)
        if proc.returncode == 0:
            for raw_line in proc.stdout.splitlines():
                parts = raw_line.split("\t")
                if not parts:
                    continue
                status = parts[0]
                if status == "A" and len(parts) >= 2:
                    added.append(parts[1])
                elif status in {"M", "T"} and len(parts) >= 2:
                    modified.append(parts[1])
                elif status == "D" and len(parts) >= 2:
                    deleted.append(parts[1])
                elif status.startswith("R") and len(parts) >= 3:
                    renamed.append({"from": parts[1], "to": parts[2]})
        numstat = _run_git(workspace, ["diff", "--numstat", f"{base_commit}..HEAD"], check=False)
        if numstat.returncode == 0:
            for raw_line in numstat.stdout.splitlines():
                parts = raw_line.split("\t")
                if len(parts) >= 3 and parts[0] == "-" and parts[1] == "-":
                    binary.append(parts[-1])
    status = _run_git(workspace, ["status", "--porcelain"], check=False)
    untracked = []
    if status.returncode == 0:
        for raw_line in status.stdout.splitlines():
            if raw_line.startswith("?? "):
                untracked.append(raw_line[3:])
    changed = sorted(set(added + modified + [item["to"] for item in renamed]))
    return {
        "schema_version": TASK_SCHEMA_VERSION,
        "task_id": task.id,
        "worker_id": state["worker_id"],
        "base_commit": base_commit,
        "worker_branch": state["worker_branch"],
        "head_commit": state["head_commit"],
        "changed_files": changed,
        "added_files": sorted(added),
        "modified_files": sorted(modified),
        "deleted_files": sorted(deleted),
        "renamed_files": renamed,
        "untracked_files": sorted(untracked),
        "binary_files": sorted(binary),
        "dirty": state["dirty"],
        "generated_at": utc_now().isoformat(),
    }


def _git_preview_readiness(
    root: Path,
    task: TaskRecord,
    state: dict[str, Any],
    worker_head: str | None,
    conflict_prediction: str,
) -> str:
    if task.status != "verified" or task.verification_status != "passed" or task.verification_exit_code != 0:
        return "not_ready"
    if state["dirty"]:
        return "not_ready"
    verification = _read_json_object(root / ".devflow" / "tasks" / task.id / "verification.json")
    verified_commit = verification.get("verified_commit") if verification else None
    if not verified_commit:
        return "not_ready"
    if worker_head and verified_commit != worker_head:
        return "not_ready"
    if conflict_prediction != "clean":
        return "not_ready"
    return "ready"


def _merge_base_is_ancestor(root: Path, base_commit: str, branch: str) -> bool:
    return _run_git(root, ["merge-base", "--is-ancestor", base_commit, branch], check=False).returncode == 0


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}