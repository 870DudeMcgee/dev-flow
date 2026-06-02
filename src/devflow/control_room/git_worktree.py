from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from devflow.control_room.git_state import origin_main_sha
from devflow.control_room.models import TASK_SCHEMA_VERSION, TaskRecord
from devflow.control_room.paths import absolute_path, relative_path, task_worker_dir, worktree_path, worktrees_dir
from devflow.control_room.persistence import append_event, atomic_write_text, get_task, list_tasks, utc_now
from devflow.control_room.workspace import Workspace


DEFAULT_BASE_BRANCH = "main"
DEFAULT_WORKER_ID = "shell"
ARCHIVE_BRANCH_PREFIX = "devflow/archive/"


class GitWorktreeError(ValueError):
    pass


def create_git_worktree(root: Path, task_id: str, worker_id: str = DEFAULT_WORKER_ID) -> Workspace:
    _require_git_repo(root)
    base_ref, base_commit = _resolve_base_branch_and_commit(root)
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
        base_ref=base_ref,
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
        "base_branch": _base_branch_for_commit(root, task.workspace_commit),
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
    origin_main_head = origin_main_sha(root)
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
    origin_baseline_stale = bool(base_commit and origin_main_head and base_commit != origin_main_head)
    preview = {
        "schema_version": TASK_SCHEMA_VERSION,
        "task_id": task.id,
        "worker_id": worker_id,
        "base_commit": base_commit,
        "main_current_head": main_head,
        "origin_main_head": origin_main_head,
        "worker_branch": branch,
        "worker_branch_head": worker_head,
        "merge_base": merge_base,
        "baseline_stale": baseline_stale,
        "origin_baseline_stale": origin_baseline_stale,
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
            "origin_main_head": origin_main_head,
            "baseline_status": "changed" if baseline_stale else "unchanged" if base_commit and main_head else "unavailable",
            "origin_baseline_status": (
                "changed" if origin_baseline_stale else "unchanged" if base_commit and origin_main_head else "unavailable"
            ),
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
    origin_head = origin_main_sha(root)
    if task.workspace_commit and origin_head and task.workspace_commit != origin_head:
        errors.append(f"origin/main differs from task base commit: {origin_head}")
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


def git_branch_sharing_checks(tasks: list[TaskRecord]) -> list[tuple[str, bool, str]]:
    branch_claims: dict[str, set[str]] = {}
    for task in tasks:
        if not is_git_worktree_task(task):
            continue
        worker_id = worker_id_for_task(task)
        branch = task.branch_name or worker_branch_name(task.id, worker_id)
        branch_claims.setdefault(branch, set()).add(task.id)
    if not branch_claims:
        return []

    shared = {
        branch: sorted(task_ids)
        for branch, task_ids in sorted(branch_claims.items())
        if len(task_ids) > 1
    }
    if not shared:
        return [("strict: unique Git worker branches", True, f"{len(branch_claims)} branch claim(s) unique")]

    details = "; ".join(f"{branch} shared by {', '.join(task_ids)}" for branch, task_ids in shared.items())
    return [("strict: unique Git worker branches", False, details)]


def promote_git_worktree(root: Path, task: TaskRecord) -> dict[str, Any]:
    preview = build_git_promotion_preview(root, task)
    git_preview = preview["git"]
    if git_preview["conflict_prediction"] != "clean":
        files = git_preview.get("conflict_files") or []
        file_lines = "\n".join(f"  {name}" for name in files) if files else "  unknown"
        report_path = _write_conflict_report(root, task, git_preview, "merge conflict predicted")
        raise GitWorktreeError(
            "promotion refused: merge conflict predicted\n"
            "conflict files:\n"
            f"{file_lines}\n"
            f"conflict_report: {relative_path(root, report_path)}\n"
            "suggested next action:\n"
            f"  devflow task create \"Resolve conflict for {task.id} worker {git_preview['worker_id']}\""
        )
    branch = git_preview["worker_branch"]
    message = f"chore(devflow): promote {task.id}\n\nDev-Flow-Task: {task.id}"
    proc = _run_git(root, ["merge", "--no-ff", branch, "-m", message], check=False)
    if proc.returncode != 0:
        _run_git(root, ["merge", "--abort"], check=False)
        detail = (proc.stderr or proc.stdout or "git merge failed").strip()
        report_path = _write_conflict_report(root, task, git_preview, detail)
        raise GitWorktreeError(f"Git-native promotion failed: {detail}\nconflict_report: {relative_path(root, report_path)}")
    return preview


def list_devflow_worktrees(root: Path) -> list[dict[str, Any]]:
    _require_git_repo(root)
    tasks = {task.id: task for task in list_tasks(root)}
    entries = _git_worktree_entries(root)
    devflow_root = worktrees_dir(root).resolve()
    worktrees: list[dict[str, Any]] = []
    for entry in entries:
        path = Path(entry["path"]).resolve()
        if not _is_under(path, devflow_root):
            continue
        branch = entry.get("branch")
        task_id, worker_id = _task_worker_from_branch(branch) or _task_worker_from_worktree_path(root, path)
        status = _resource_status(root, tasks, task_id, worker_id, branch, path)
        worktrees.append(
            {
                "path": relative_path(root, path),
                "branch": branch or "",
                "task_id": task_id or "",
                "worker_id": worker_id or "",
                "status": status,
                "dirty": _worktree_dirty(path) if path.exists() else True,
            }
        )
    return sorted(worktrees, key=lambda item: (item["task_id"], item["worker_id"], item["path"]))


def list_devflow_branches(root: Path) -> list[dict[str, Any]]:
    _require_git_repo(root)
    tasks = {task.id: task for task in list_tasks(root)}
    worktree_by_branch = {item["branch"]: item for item in list_devflow_worktrees(root) if item.get("branch")}
    proc = _run_git(root, ["for-each-ref", "--format=%(refname:short)", "refs/heads/devflow"], check=False)
    if proc.returncode != 0:
        return []
    branches: list[dict[str, Any]] = []
    for branch in sorted(line.strip() for line in proc.stdout.splitlines() if line.strip()):
        parsed = _task_worker_from_branch(branch)
        if not parsed:
            continue
        task_id, worker_id = parsed
        worktree = worktree_by_branch.get(branch)
        path = absolute_path(root, worktree["path"]).resolve() if worktree else None
        status = _resource_status(root, tasks, task_id, worker_id, branch, path)
        branches.append(
            {
                "branch": branch,
                "task_id": task_id,
                "worker_id": worker_id,
                "status": status,
                "has_worktree": bool(worktree),
                "worktree_path": worktree["path"] if worktree else "",
            }
        )
    return branches


def prune_orphan_worktrees(root: Path, dry_run: bool = True, force: bool = False) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for worktree in list_devflow_worktrees(root):
        if worktree["status"] != "orphan":
            continue
        action = {
            "action": "remove_worktree",
            "path": worktree["path"],
            "branch": worktree["branch"],
            "status": worktree["status"],
            "applied": False,
        }
        if not dry_run:
            _remove_git_worktree(root, worktree["path"], force=force)
            action["applied"] = True
        actions.append(action)
    return actions


def archive_devflow_branch(root: Path, branch: str, dry_run: bool = True) -> dict[str, Any]:
    _require_git_repo(root)
    if not _task_worker_from_branch(branch):
        raise GitWorktreeError(f"Refusing to archive non-task Dev-Flow branch: {branch}")
    if not branch_exists(root, branch):
        raise GitWorktreeError(f"Dev-Flow branch does not exist: {branch}")
    target = archive_branch_name(branch)
    if branch_exists(root, target):
        raise GitWorktreeError(f"Archive branch already exists: {target}")
    active = [item for item in list_devflow_worktrees(root) if item.get("branch") == branch]
    if active and not dry_run:
        paths = ", ".join(item["path"] for item in active)
        raise GitWorktreeError(f"Refusing to archive branch with an active worktree: {paths}")
    if not dry_run:
        _git_stdout(root, ["branch", "-m", branch, target])
    return {"branch": branch, "archive_branch": target, "applied": not dry_run}


def cleanup_task_git_resources(root: Path, task_id: str, dry_run: bool = True, force: bool = False) -> list[dict[str, Any]]:
    task = get_task(root, task_id)
    if not is_git_worktree_task(task):
        raise GitWorktreeError(f"Task {task.id} is not backed by a Git worktree")
    if not dry_run and task.status not in {"promoted", "failed", "worker_failed", "verification_failed", "timed_out", "cancelled"} and not force:
        raise GitWorktreeError(f"Refusing to cleanup task {task.id} with status {task.status}; use --force after review.")
    worker_id = worker_id_for_task(task)
    branch = task.branch_name or worker_branch_name(task.id, worker_id)
    path = worktree_path(root, task.id, worker_id)
    actions: list[dict[str, Any]] = []
    if path.exists():
        action = {"action": "remove_worktree", "path": relative_path(root, path), "branch": branch, "applied": False}
        if not dry_run:
            _remove_git_worktree(root, relative_path(root, path), force=force)
            action["applied"] = True
        actions.append(action)
    if branch_exists(root, branch):
        target = archive_branch_name(branch)
        action = {"action": "archive_branch", "branch": branch, "archive_branch": target, "applied": False}
        if not dry_run:
            if branch_exists(root, target):
                raise GitWorktreeError(f"Archive branch already exists: {target}")
            _git_stdout(root, ["branch", "-m", branch, target])
            action["applied"] = True
        actions.append(action)
    if not dry_run and actions:
        append_event(
            root,
            task.id,
            "task_git_resources_cleaned",
            {
                "removed_worktrees": [item["path"] for item in actions if item["action"] == "remove_worktree" and item["applied"]],
                "archived_branches": [
                    {"from": item["branch"], "to": item["archive_branch"]}
                    for item in actions
                    if item["action"] == "archive_branch" and item["applied"]
                ],
            },
        )
    return actions


def archive_branch_name(branch: str) -> str:
    if not branch.startswith("devflow/") or branch.startswith(ARCHIVE_BRANCH_PREFIX):
        raise GitWorktreeError(f"Refusing to archive non-task Dev-Flow branch: {branch}")
    return f"{ARCHIVE_BRANCH_PREFIX}{branch.removeprefix('devflow/')}"


def branch_exists(root: Path, branch: str) -> bool:
    return _run_git(root, ["show-ref", "--verify", "--quiet", f"refs/heads/{branch}"], check=False).returncode == 0


def _resolve_base_branch_and_commit(root: Path) -> tuple[str, str]:
    origin_head = branch_head(root, "origin/main")
    if origin_head:
        return "origin/main", origin_head

    default_head = branch_head(root, DEFAULT_BASE_BRANCH)
    if default_head:
        return DEFAULT_BASE_BRANCH, default_head

    branch_proc = _run_git(root, ["branch", "--show-current"], check=False)
    current_branch = branch_proc.stdout.strip() if branch_proc.returncode == 0 else ""
    if current_branch:
        current_head = branch_head(root, current_branch)
        if current_head:
            return current_branch, current_head

    head = current_head(root)
    if head:
        return "HEAD", head

    raise GitWorktreeError("Git worktree tasks require at least one commit on the current branch.")


def _base_branch_for_commit(root: Path, commit: str | None) -> str:
    if not commit:
        return DEFAULT_BASE_BRANCH
    origin_head = branch_head(root, "origin/main")
    if origin_head == commit:
        return "origin/main"
    default_head = branch_head(root, DEFAULT_BASE_BRANCH)
    if default_head == commit:
        return DEFAULT_BASE_BRANCH

    branch_proc = _run_git(root, ["branch", "--show-current"], check=False)
    current_branch = branch_proc.stdout.strip() if branch_proc.returncode == 0 else ""
    if current_branch and branch_head(root, current_branch) == commit:
        return current_branch

    return "HEAD"


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


def _git_worktree_entries(root: Path) -> list[dict[str, str]]:
    proc = _run_git(root, ["worktree", "list", "--porcelain"], check=True)
    entries: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for line in proc.stdout.splitlines():
        if not line.strip():
            if current:
                entries.append(current)
                current = {}
            continue
        key, _, value = line.partition(" ")
        if key == "worktree":
            current["path"] = value
        elif key == "branch":
            current["branch"] = value.removeprefix("refs/heads/")
        elif key == "HEAD":
            current["head"] = value
    if current:
        entries.append(current)
    return [entry for entry in entries if entry.get("path")]


def _task_worker_from_branch(branch: str | None) -> tuple[str, str] | None:
    if not branch or not branch.startswith("devflow/") or branch.startswith(ARCHIVE_BRANCH_PREFIX):
        return None
    parts = branch.split("/", 2)
    if len(parts) < 3 or not parts[1] or not parts[2]:
        return None
    return parts[1], parts[2]


def _task_worker_from_worktree_path(root: Path, path: Path) -> tuple[str, str]:
    try:
        relative = path.resolve().relative_to(worktrees_dir(root).resolve())
    except ValueError:
        return "", ""
    parts = relative.parts
    if len(parts) < 2:
        return "", ""
    return parts[0], parts[1]


def _resource_status(
    root: Path,
    tasks: dict[str, TaskRecord],
    task_id: str | None,
    worker_id: str | None,
    branch: str | None,
    path: Path | None,
) -> str:
    if not task_id:
        return "unknown"
    task = tasks.get(task_id)
    if not task:
        return "orphan"
    expected_branch = task.branch_name or worker_branch_name(task.id, worker_id or DEFAULT_WORKER_ID)
    if branch and branch != expected_branch:
        return "mismatched"
    if path is not None and path != worktree_path(root, task.id, worker_id or worker_id_for_task(task)).resolve():
        return "mismatched"
    return "owned"


def _is_under(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _remove_git_worktree(root: Path, path: str, force: bool = False) -> None:
    absolute = absolute_path(root, path).resolve()
    expected_root = worktrees_dir(root).resolve()
    if not _is_under(absolute, expected_root):
        raise GitWorktreeError(f"Refusing to remove worktree outside .devflow/worktrees: {path}")
    if absolute.exists() and _worktree_dirty(absolute) and not force:
        raise GitWorktreeError(f"Refusing to remove dirty worktree: {path}")
    args = ["worktree", "remove"]
    if force:
        args.append("--force")
    args.append(str(absolute))
    _git_stdout(root, args)


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
    origin_head = origin_main_sha(root)
    if state.get("base_commit") and origin_head and state["base_commit"] != origin_head:
        return "not_ready"
    return "ready"


def _write_conflict_report(root: Path, task: TaskRecord, git_preview: dict[str, Any], reason: str) -> Path:
    worker_id = str(git_preview.get("worker_id") or worker_id_for_task(task))
    report_path = task_worker_dir(root, task.id, worker_id) / "conflict-report.md"
    files = git_preview.get("conflict_files") or []
    file_lines = "\n".join(f"- {name}" for name in files) if files else "- unknown"
    text = (
        f"# Promotion Conflict Report\n\n"
        f"task_id: {task.id}\n"
        f"worker_id: {worker_id}\n"
        f"worker_branch: {git_preview.get('worker_branch') or 'unknown'}\n"
        f"base_commit: {git_preview.get('base_commit') or 'unknown'}\n"
        f"main_current_head: {git_preview.get('main_current_head') or 'unknown'}\n"
        f"origin_main_head: {git_preview.get('origin_main_head') or 'unknown'}\n"
        f"reason: {reason}\n\n"
        f"## Conflict Files\n\n"
        f"{file_lines}\n\n"
        f"## Next Safe Action\n\n"
        f"Create a new task to resolve the conflict manually; Dev-Flow did not auto-resolve source conflicts.\n"
    )
    atomic_write_text(report_path, text)
    return report_path


def _merge_base_is_ancestor(root: Path, base_commit: str, branch: str) -> bool:
    return _run_git(root, ["merge-base", "--is-ancestor", base_commit, branch], check=False).returncode == 0


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}
