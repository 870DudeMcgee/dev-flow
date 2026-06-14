from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from devflow.control_room.models import TaskRecord


def promotion_readiness_errors(
    task: TaskRecord,
    task_path: Path | None = None,
    *,
    allow_stale_baseline: bool = False,
) -> list[str]:
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
        errors.extend(_patch_application_readiness_errors(task, task_path))
        if task.workspace_kind == "git_worktree":
            from devflow.control_room.git_worktree import git_worktree_readiness_errors

            errors.extend(
                git_worktree_readiness_errors(
                    task_path.parents[2],
                    task,
                    allow_stale_baseline=allow_stale_baseline,
                )
            )
    return errors


def format_promotion_refusal(
    task: TaskRecord,
    task_path: Path | None = None,
    *,
    allow_stale_baseline: bool = False,
) -> str:
    errors = promotion_readiness_errors(task, task_path, allow_stale_baseline=allow_stale_baseline)
    message = f"Refusing to promote task '{task.id}': {'; '.join(errors)}."
    if task_path is not None and task.workspace_kind == "git_worktree":
        from devflow.control_room.git_worktree import git_worker_lane_summary

        lane = git_worker_lane_summary(task_path.parents[2], task)
        if lane and lane.get("next_safe_action"):
            message = f"{message}\nnext_safe_action: {lane['next_safe_action']}"
    return message


def human_promotion_gate(task_path: Path) -> dict[str, Any]:
    goal_link = _read_goal_link(task_path)
    if goal_link is None:
        return {"required": False}

    checkpoint_required = bool(goal_link.get("human_checkpoint_required"))
    promotion_allowed = bool(goal_link.get("promotion_allowed"))
    required = checkpoint_required and not promotion_allowed
    if not required:
        return {"required": False}

    goal_id = str(goal_link.get("goal_id") or "unknown-goal")
    slice_id = str(goal_link.get("slice_id") or "unknown-slice")
    reason = str(goal_link.get("checkpoint_reason") or "Human checkpoint required.")
    return {
        "required": True,
        "goal_id": goal_id,
        "slice_id": slice_id,
        "reason": reason,
        "prompt": f"Review HITL goal {goal_id} / {slice_id} before promotion.",
    }


def readiness_state(task: TaskRecord, task_path: Path) -> tuple[bool, list[str]]:
    errors = promotion_readiness_errors(task, task_path)
    ready = not errors
    reasons = list(errors) if errors else ["Verification passed successfully"]
    if task.workspace_dirty:
        reasons.append("Warning: Workspace was created from a dirty worktree (uncommitted changes)")
    return ready, reasons


def _read_goal_link(task_path: Path) -> dict[str, Any] | None:
    goal_link_path = task_path / "goal-link.yaml"
    if not goal_link_path.exists():
        return None
    try:
        payload = yaml.safe_load(goal_link_path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return None
    return payload if isinstance(payload, dict) else None


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


def _patch_application_readiness_errors(task: TaskRecord, task_path: Path) -> list[str]:
    patch_path = task_path / "patch-application.json"
    if not patch_path.exists():
        return []
    try:
        patch_application = json.loads(patch_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"patch-application.json is invalid JSON: {exc.msg}"]
    if not isinstance(patch_application, dict):
        return ["patch-application.json is malformed"]

    patch_hash = patch_application.get("patch_hash")
    errors: list[str] = []
    if not patch_hash:
        errors.append("patch-application.json patch_hash is missing")

    verification_path = task_path / "verification.json"
    try:
        verification = json.loads(verification_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return errors
    if not isinstance(verification, dict) or verification.get("status") != "passed":
        return errors

    verified_hash = verification.get("verified_patch_hash")
    if patch_hash and verified_hash != patch_hash:
        if verified_hash is None:
            errors.append("verification.json verified_patch_hash is missing for latest patch application")
        else:
            errors.append(
                f"verification.json verified_patch_hash is '{verified_hash}', expected latest patch hash '{patch_hash}'"
            )

    expected_application_path = f".devflow/tasks/{task.id}/patch-application.json"
    verified_application_path = verification.get("verified_patch_application_path")
    if verified_application_path != expected_application_path:
        if verified_application_path is None:
            errors.append("verification.json verified_patch_application_path is missing for latest patch application")
        else:
            errors.append(
                "verification.json verified_patch_application_path is "
                f"'{verified_application_path}', expected '{expected_application_path}'"
            )
    return errors
