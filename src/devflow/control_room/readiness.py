from __future__ import annotations

import json
from pathlib import Path

from devflow.control_room.models import TaskRecord


def promotion_readiness_errors(task: TaskRecord, task_path: Path | None = None) -> list[str]:
    errors = []
    if task.status != "verified":
        errors.append(f"status is '{task.status}', expected 'verified'")
    if task.verification_status != "passed":
        errors.append(f"verification status is '{task.verification_status}', expected 'passed'")
    if task.verification_exit_code != 0:
        if task.verification_exit_code is None:
            errors.append("verification exit code is missing")
        else:
            errors.append(f"verification exit code is {task.verification_exit_code}, expected 0")
    if task_path is not None:
        errors.extend(_verification_json_readiness_errors(task, task_path / "verification.json"))
        if task.workspace_kind == "git_worktree":
            from devflow.control_room.git_worktree import git_worktree_readiness_errors

            errors.extend(git_worktree_readiness_errors(task_path.parents[2], task))
    return errors


def format_promotion_refusal(task: TaskRecord, task_path: Path | None = None) -> str:
    return f"Refusing to promote task '{task.id}': {'; '.join(promotion_readiness_errors(task, task_path))}."


def readiness_state(task: TaskRecord, task_path: Path) -> tuple[bool, list[str]]:
    errors = promotion_readiness_errors(task, task_path)
    ready = not errors
    reasons = list(errors) if errors else ["Verification passed successfully"]
    if task.workspace_dirty:
        reasons.append("Warning: Workspace was created from a dirty worktree (uncommitted changes)")
    return ready, reasons


def _verification_json_readiness_errors(task: TaskRecord, verification_path: Path) -> list[str]:
    if not verification_path.exists():
        return ["verification.json is missing"]
    try:
        payload = json.loads(verification_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"verification.json is invalid JSON: {exc.msg}"]

    errors = []
    if payload.get("task_id") != task.id:
        errors.append(f"verification.json task_id is '{payload.get('task_id')}', expected '{task.id}'")
    if payload.get("status") != "passed":
        errors.append(f"verification.json status is '{payload.get('status')}', expected 'passed'")
    if payload.get("task_status") != "verified":
        errors.append(f"verification.json task_status is '{payload.get('task_status')}', expected 'verified'")
    if payload.get("exit_code") != 0:
        exit_code = payload.get("exit_code")
        if exit_code is None:
            errors.append("verification.json exit code is missing")
        else:
            errors.append(f"verification.json exit code is {exit_code}, expected 0")
    return errors
