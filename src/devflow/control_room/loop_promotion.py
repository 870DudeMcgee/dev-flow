from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from devflow.control_room.freshness import FreshnessReport
from devflow.control_room.git_state import inspect_git_state
from devflow.control_room.paths import task_dir
from devflow.control_room.persistence import list_tasks
from devflow.control_room.service import preview_task_promotion, promote_task


def promotion_candidates(root: Path, report: FreshnessReport) -> list[tuple[str, bool, bool]]:
    candidates: list[tuple[str, bool, bool]] = []
    seen_task_ids: set[str] = set()
    for goal in report.goal_loop:
        for lane in goal.lanes:
            if lane.lane_state != "ready_to_promote" or not lane.linked_task_ids:
                continue
            task_id = lane.linked_task_ids[-1]
            seen_task_ids.add(task_id)
            link = _goal_link(root, task_id)
            risk = str(link.get("risk") or lane.risk or "medium").lower()
            candidates.append((task_id, bool(link.get("promotion_allowed")), risk in {"high", "critical"}))
    for task in list_tasks(root):
        if task.id in seen_task_ids or task.status != "verified" or task.verification_status != "passed":
            continue
        if (task_dir(root, task.id) / "goal-link.yaml").exists():
            continue
        candidates.append((task.id, True, False))
    return candidates


def handle_promotion_candidate(
    root: Path,
    *,
    loop_id: str,
    actions: list[str],
    allow_loop_promotion: bool,
    allow_high_risk: bool,
    loop_config_path: Path,
    candidate: tuple[str, bool, bool],
    allow_promote: bool,
) -> tuple[str, str, str, dict[str, Any] | None, dict[str, Any] | None]:
    task_id, promotion_allowed, high_risk = candidate
    loop_config_action = f"Edit {loop_config_path}"
    preview_action = f"devflow task promote-preview {task_id}"

    def blocked(
        reason: str,
        next_safe_action: str,
        preview: dict[str, Any] | None = None,
        promotion: dict[str, Any] | None = None,
    ):
        return "promotion_blocked", reason, next_safe_action, preview, promotion

    if "promotion_preview" not in actions or "promote" not in actions:
        return blocked("promotion_action_not_enabled", loop_config_action)
    if not allow_loop_promotion:
        return blocked("promotion_not_allowed_by_loop_config", loop_config_action)
    if not allow_promote:
        return blocked("allow_promote_flag_required", f"devflow loop run {loop_id} --allow-promote")
    if not promotion_allowed:
        return blocked("task_promotion_not_allowed", preview_action)
    if high_risk and not allow_high_risk:
        return blocked("high_risk_promotion_blocked", preview_action)

    try:
        preview = preview_task_promotion(root, task_id)
    except Exception as exc:
        preview_result = {"task_id": task_id, "status": "failed", "reason": str(exc)}
        return "promotion_preview_failed", "promotion_preview_failed", preview_action, preview_result, None

    preview_result: dict[str, Any] = {
        "task_id": task_id,
        "status": "clean",
        "added": list(preview.get("added") or []),
        "modified": list(preview.get("modified") or []),
        "deleted": list(preview.get("deleted") or []),
    }
    refusal = promotion_preview_refusal(root, preview)
    if refusal:
        preview_result["status"] = "blocked"
        preview_result["reason"] = refusal
        return blocked(refusal, preview_action, preview_result)

    try:
        promote_task(root, task_id)
    except Exception as exc:
        return blocked(
            "promotion_failed",
            preview_action,
            preview_result,
            {"task_id": task_id, "status": "failed", "reason": str(exc)},
        )
    return (
        "completed",
        "promoted",
        "Continue loop dispatch.",
        preview_result,
        {"task_id": task_id, "status": "promoted"},
    )


def promotion_preview_refusal(root: Path, preview: dict[str, Any]) -> str | None:
    if preview.get("deleted"):
        return "promotion_preview_has_deletions"
    if preview.get("binary"):
        return "promotion_preview_has_binary_files"
    human_approval = preview.get("human_approval") or {}
    if human_approval.get("required"):
        return "human_checkpoint_required"
    git_preview = preview.get("git")
    if git_preview and git_preview.get("promotion_readiness") != "ready":
        return "git_promotion_preview_not_ready"
    baseline = preview.get("baseline") or {}
    if inspect_git_state(root).is_repo and baseline.get("baseline_status") != "unchanged":
        return "promotion_baseline_not_clean"
    return None


def _goal_link(root: Path, task_id: str) -> dict[str, Any]:
    path = task_dir(root, task_id) / "goal-link.yaml"
    if not path.exists():
        return {}
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return {}
    return payload if isinstance(payload, dict) else {}
