from __future__ import annotations

import json
import subprocess
import hashlib
from pathlib import Path
from datetime import datetime, timezone
from typing import Any

from devflow.control_room.models import TaskRecord
from devflow.control_room.paths import absolute_path, relative_path, task_dir
from devflow.control_room.persistence import get_task, utc_now, atomic_write_text, save_task
from devflow.control_room.git_worktree import (
    is_git_worktree_task,
    git_worker_state,
    _diff_summary,
    branch_head,
    _worktree_dirty
)
from devflow.control_room.scout import RepoScout


class FinalizationError(ValueError):
    pass


def is_ignored_evidence(path_str: str) -> bool:
    normalized = path_str.replace("\\", "/").lower()
    parts = normalized.split("/")
    if any(p.startswith(".venv") or p in {".git", ".devflow", "__pycache__", ".pytest_cache", ".mypy_cache"} for p in parts):
        return True
    if normalized.endswith(".log") or "/logs/" in normalized:
        return True
    return False


def run_git_in_dir(cwd: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=30)


def finalize_task(root: Path, task_id: str, commit: bool = False) -> dict[str, Any]:
    task = get_task(root, task_id)
    task_path = task_dir(root, task_id)

    # 1. Refuse non-worktree tasks
    if not is_git_worktree_task(task):
        suggested = f"git add <files> && git commit -m \"chore(devflow): finalize {task_id}\""
        raise FinalizationError(
            f"Finalization is only supported for Git-worktree tasks. Task {task_id} is a shell/non-worktree task.\n"
            f"To finalize manually, run:\n"
            f"  {suggested}"
        )

    workspace = absolute_path(root, task.workspace).resolve()
    if not workspace.is_dir():
        raise FinalizationError(f"Workspace directory is missing: {workspace}")

    # 2. Check for unrelated dirty files in the main checkout root
    scout = RepoScout(root)
    unrelated_dirty = []
    for f in scout.get_changed_files():
        if f.startswith(".devflow/"):
            continue
        unrelated_dirty.append(f)

    if unrelated_dirty:
        raise FinalizationError(
            f"Refusing to finalize task {task_id} because unrelated dirty changes exist in the main checkout:\n"
            + "\n".join(f"  - {f}" for f in unrelated_dirty)
            + "\n\nPlease commit, stash, or discard these changes before finalization."
        )

    # 3. Load verification and validate status/staleness
    verification_json_path = task_path / "verification.json"
    v_data = {}
    if verification_json_path.exists():
        try:
            v_data = json.loads(verification_json_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    current_head_commit = branch_head(root, task.branch_name) if task.branch_name else None
    
    # We require verification to have passed on the current HEAD, and that no files were modified after verification
    verified_commit = v_data.get("verified_commit")
    
    verification_status = "missing"
    if v_data.get("status") == "passed" and task.verification_status == "passed":
        if verified_commit and current_head_commit == verified_commit:
            finished_at_str = v_data.get("finished_at")
            stale_by_mtime = False
            if finished_at_str:
                try:
                    finished_dt = datetime.fromisoformat(finished_at_str.replace("Z", "+00:00"))
                    
                    state = git_worker_state(root, task)
                    diff_sum = _diff_summary(root, task, state)
                    added_files = diff_sum.get("added_files") or []
                    modified_files = diff_sum.get("modified_files") or []
                    untracked_files = diff_sum.get("untracked_files") or []
                    
                    all_candidates = sorted(list(set(added_files + modified_files + untracked_files)))
                    for f in all_candidates:
                        f_path = workspace / f
                        if f_path.exists():
                            file_dt = datetime.fromtimestamp(f_path.stat().st_mtime, tz=timezone.utc)
                            # Give a tiny 1-second grace window for filesystem clock precision
                            if file_dt > finished_dt:
                                stale_by_mtime = True
                                break
                except Exception:
                    stale_by_mtime = True
            else:
                stale_by_mtime = True

            if stale_by_mtime:
                verification_status = "stale"
            else:
                verification_status = "passed"
        else:
            verification_status = "stale"
    elif v_data.get("status") == "failed" or task.verification_status == "failed":
        verification_status = "failed"

    if verification_status != "passed":
        suggested_cmd = task.verification_command or "pytest"
        raise FinalizationError(
            f"Verification is {verification_status} for task {task_id}.\n"
            f"Please run verification on the latest workspace changes first:\n"
            f"  devflow task verify {task_id} --shell \"{suggested_cmd}\""
        )


    # 4. Identify candidate changed files inside the worktree
    state = git_worker_state(root, task)
    diff_sum = _diff_summary(root, task, state)
    
    added_files = diff_sum.get("added_files") or []
    modified_files = diff_sum.get("modified_files") or []
    deleted_files = diff_sum.get("deleted_files") or []
    untracked_files = diff_sum.get("untracked_files") or []
    
    all_candidates = sorted(list(set(added_files + modified_files + deleted_files + untracked_files)))
    
    staged_candidates = []
    ignored_evidence = []
    
    for f in all_candidates:
        if is_ignored_evidence(f):
            ignored_evidence.append(f)
        else:
            staged_candidates.append(f)

    # 5. Handle staging and focused commit creation
    commit_hash = None
    main_head_at_finalize = None
    main_head_proc = run_git_in_dir(root, ["rev-parse", "HEAD"])
    if main_head_proc.returncode == 0:
        main_head_at_finalize = main_head_proc.stdout.strip()
    if commit:
        # Stage only task-owned source/doc/test changes
        for f in staged_candidates:
            run_git_in_dir(workspace, ["add", f])
            
        # Create deterministic commit message
        commit_title = task.title
        if not any(commit_title.startswith(prefix) for prefix in ["fix:", "feat:", "refactor:", "chore:", "docs:", "test:", "style:", "ci:"]):
            commit_title = f"chore(devflow): {commit_title.lower()}"
        commit_msg = f"{commit_title}\n\nDev-Flow-Task: {task.id}"
        
        commit_proc = run_git_in_dir(workspace, ["commit", "-m", commit_msg])
        if commit_proc.returncode != 0:
            raise FinalizationError(f"Git commit failed inside worktree: {commit_proc.stderr or commit_proc.stdout}")
            
        head_proc = run_git_in_dir(workspace, ["rev-parse", "HEAD"])
        if head_proc.returncode == 0:
            commit_hash = head_proc.stdout.strip()
            
            task.workspace_dirty = False
            task.updated_at = utc_now()
            save_task(task_path, task)
            
            if verification_json_path.exists():
                try:
                    v_data = json.loads(verification_json_path.read_text(encoding="utf-8"))
                    v_data["verified_commit"] = commit_hash
                    v_data["dirty_at_verification"] = False
                    atomic_write_text(verification_json_path, json.dumps(v_data, indent=2) + "\n")
                except Exception:
                    pass

    # 6. Record finalization evidence
    next_action = f"devflow task promote-preview {task_id}" if commit else f"devflow task finalize {task_id} --commit"
    
    evidence = {
        "task_id": task_id,
        "timestamp": utc_now().isoformat(),
        "candidate_files": all_candidates,
        "staged_files": staged_candidates,
        "refused_files": [],
        "ignored_evidence_files": ignored_evidence,
        "verification_status": verification_status,
        "commit_hash": commit_hash,
        "commit_location": "task worker branch" if commit_hash else "dry-run",
        "worker_branch": task.branch_name,
        "worker_branch_commit": commit_hash or current_head_commit,
        "main_head_at_finalize": main_head_at_finalize,
        "main_changed": False,
        "next_suggested_action": next_action,
    }
    
    evidence_path = task_path / "finalization.json"
    atomic_write_text(evidence_path, json.dumps(evidence, indent=2, sort_keys=True) + "\n")

    return evidence
