from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from devflow.control_room.git_worktree import is_git_worktree_task, worker_id_for_task
from devflow.control_room.models import TASK_SCHEMA_VERSION, TaskRecord
from devflow.control_room.paths import absolute_path, relative_path, task_dir, workspaces_dir, worktrees_dir
from devflow.control_room.persistence import append_event, atomic_write_text, get_task, save_task, utc_now


VALID_CLOSE_OUTCOMES = {"promoted", "rejected", "duplicate", "superseded", "abandoned", "evidence-only"}


class TaskClosureError(ValueError):
    pass


def close_task(root: Path, task_id: str, *, outcome: str, reason: str) -> dict[str, Any]:
    if outcome not in VALID_CLOSE_OUTCOMES:
        allowed = ", ".join(sorted(VALID_CLOSE_OUTCOMES))
        raise TaskClosureError(f"Unsupported outcome {outcome!r}; expected one of: {allowed}.")
    if not reason.strip():
        raise TaskClosureError("Closing a task requires --reason.")

    task = get_task(root, task_id)
    previous_status = task.status
    now = utc_now()
    closure = _closure_evidence(root, task, outcome=outcome, reason=reason.strip(), previous_status=previous_status, closed_at=now)
    task_path = task_dir(root, task.id)
    atomic_write_text(task_path / "closure.json", json.dumps(closure, indent=2, sort_keys=True) + "\n")

    task.status = "closed"
    task.close_outcome = outcome
    task.close_reason = reason.strip()
    task.closed_at = now
    task.updated_at = now
    task.last_event = "task_closed"
    save_task(task_path, task)
    append_event(
        root,
        task.id,
        "task_closed",
        {
            "outcome": outcome,
            "reason": reason.strip(),
            "previous_status": previous_status,
            "closure_path": relative_path(root, task_path / "closure.json"),
        },
    )
    return closure


def read_closure(root: Path, task_id: str) -> dict[str, Any] | None:
    path = task_dir(root, task_id) / "closure.json"
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def cleanup_task(root: Path, task_id: str, *, apply: bool) -> dict[str, Any]:
    task = get_task(root, task_id)
    if task.status != "closed":
        raise TaskClosureError(f"Refusing cleanup for unclosed task {task.id}. Close the task first.")

    candidate = _cleanup_candidate(root, task)
    retained = _retained_evidence(root, task.id)
    removed: list[str] = []
    if apply and candidate is not None:
        _remove_candidate(root, task, candidate)
        removed.append(relative_path(root, candidate))

    result = {
        "schema_version": TASK_SCHEMA_VERSION,
        "task_id": task.id,
        "applied": apply,
        "mode": "apply" if apply else "preview",
        "removed": removed,
        "would_remove": [relative_path(root, candidate)] if candidate is not None and not apply else [],
        "retained": retained,
        "generated_at": utc_now().isoformat(),
    }
    append_event(
        root,
        task.id,
        "task_cleanup_applied" if apply else "task_cleanup_previewed",
        {"removed": removed, "retained": retained},
    )
    if apply:
        atomic_write_text(task_dir(root, task.id) / "cleanup.json", json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def _closure_evidence(
    root: Path,
    task: TaskRecord,
    *,
    outcome: str,
    reason: str,
    previous_status: str,
    closed_at: Any,
) -> dict[str, Any]:
    workspace = absolute_path(root, task.workspace).resolve()
    next_action = f"devflow task cleanup {task.id} --preview" if workspace.exists() else "none"
    return {
        "schema_version": TASK_SCHEMA_VERSION,
        "task_id": task.id,
        "closed_at": closed_at.isoformat(),
        "outcome": outcome,
        "reason": reason,
        "previous_status": previous_status,
        "worker": task.worker,
        "workspace": task.workspace,
        "workspace_path": task.workspace_path,
        "workspace_kind": task.workspace_kind,
        "branch_name": task.branch_name,
        "workspace_commit": task.workspace_commit,
        "worktree_exists": workspace.exists(),
        "agent_evidence_exists": _agent_evidence_exists(root, task.id),
        "verification_exists": (task_dir(root, task.id) / "verification.json").exists(),
        "promotion_evidence_exists": _promotion_evidence_exists(root, task.id),
        "next_suggested_action": next_action,
    }


def _cleanup_candidate(root: Path, task: TaskRecord) -> Path | None:
    workspace = absolute_path(root, task.workspace).resolve()
    devflow_root = (root / ".devflow").resolve()
    if not _is_under(workspace, devflow_root):
        raise TaskClosureError(f"Refusing cleanup because workspace escapes .devflow: {relative_path(root, workspace)}")

    if is_git_worktree_task(task):
        expected = (worktrees_dir(root) / task.id / worker_id_for_task(task)).resolve()
    else:
        expected = (workspaces_dir(root) / task.id).resolve()
    if workspace != expected:
        raise TaskClosureError(
            f"Refusing cleanup because workspace escapes .devflow task ownership: {relative_path(root, workspace)}"
        )
    return workspace if workspace.exists() else None


def _remove_candidate(root: Path, task: TaskRecord, candidate: Path) -> None:
    candidate = candidate.resolve()
    if not _is_under(candidate, (root / ".devflow").resolve()):
        raise TaskClosureError(f"Refusing cleanup because path escapes .devflow: {relative_path(root, candidate)}")
    if is_git_worktree_task(task):
        proc = subprocess.run(
            ["git", "worktree", "remove", "--force", str(candidate)],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if proc.returncode != 0 and candidate.exists():
            detail = (proc.stderr or proc.stdout or "git worktree remove failed").strip()
            raise TaskClosureError(detail)
        return
    shutil.rmtree(candidate)


def _retained_evidence(root: Path, task_id: str) -> list[str]:
    base = task_dir(root, task_id)
    names = [
        "task.yaml",
        "events.jsonl",
        "closure.json",
        "verification.json",
        "finalization.json",
        "promotion.json",
        "patch-application.json",
        "summary.json",
        "merge-readiness.json",
        "result.md",
        "logs",
        "agents",
        "patches",
    ]
    return [relative_path(root, base / name) for name in names if (base / name).exists()]


def _agent_evidence_exists(root: Path, task_id: str) -> bool:
    base = task_dir(root, task_id)
    return (base / "agents").exists() or (workspaces_dir(root) / task_id / "local-workers").exists()


def _promotion_evidence_exists(root: Path, task_id: str) -> bool:
    base = task_dir(root, task_id)
    return any((base / name).exists() for name in ("promotion.json", "finalization.json", "merge-readiness.json"))


def _is_under(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False
