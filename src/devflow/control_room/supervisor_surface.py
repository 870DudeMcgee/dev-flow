from __future__ import annotations

from pathlib import Path
from typing import Any

from devflow.control_room.git_state import inspect_git_state
from devflow.control_room.git_worktree import git_worker_lane_summary
from devflow.control_room.local_worker_lane import local_worker_lane_summary
from devflow.control_room.models import TaskRecord
from devflow.control_room.persistence import utc_now
from devflow.control_room.question_resume import build_question_snapshot
from devflow.control_room.scheduler_projection import build_scheduler_snapshot
from devflow.control_room.status_projection import list_task_status_projections
from devflow.control_room.supervisor_policy import (  # noqa: F401
    APPROVAL_REQUIRED_EVIDENCE_WRITING,
    APPROVAL_REQUIRED_EVIDENCE_WRITING_COMMANDS,
    APPROVAL_REQUIRED_GIT,
    APPROVAL_REQUIRED_GIT_COMMANDS,
    APPROVAL_REQUIRED_TASK_STATE,
    APPROVAL_REQUIRED_TASK_STATE_COMMANDS,
    APPROVAL_REQUIRED_WORKER_RUNTIME,
    APPROVAL_REQUIRED_WORKER_RUNTIME_COMMANDS,
    FORBIDDEN_FOR_SUPERVISOR,
    FORBIDDEN_SUPERVISOR_ACTIONS,
    JOSH_CANONICAL_CHECKOUT,
    PROHIBITED_CHECKOUT_PATHS,
    PURE_READ_ONLY,
    PURE_READ_ONLY_COMMANDS,
    SAFETY_CLASS_REASONS,
    SUPERVISOR_SCHEMA_VERSION,
    build_supervisor_policy,
    classify_supervisor_command,
    render_supervisor_command_classification,
    render_supervisor_policy,
)
from devflow.control_room import supervisor_task_review as _tr

build_task_next_action, render_task_next_action = _tr.build_task_next_action, _tr.render_task_next_action
build_task_review, render_task_review = _tr.build_task_review, _tr.render_task_review


def build_control_room_status(root: Path, *, live_discovery: bool = True) -> dict[str, Any]:
    from devflow.control_room.agent_catalog import build_agent_catalog
    from devflow.control_room.local_model_inventory import build_local_model_inventory
    from devflow.control_room.local_model_readiness import build_local_model_readiness_plan
    from devflow.control_room.operator_readiness import build_operator_readiness_snapshot

    projections = list_task_status_projections(root)
    scheduler = build_scheduler_snapshot(root)
    operator_readiness = build_operator_readiness_snapshot(root)
    questions = build_question_snapshot(root)
    agent_catalog = build_agent_catalog(root, live_discovery=live_discovery)
    local_model_inventory = build_local_model_inventory(agent_catalog)
    local_model_readiness = build_local_model_readiness_plan(
        root,
        agent_catalog=agent_catalog,
        inventory=local_model_inventory,
    )
    task_records = [_compact_task_record(root, projection.task, projection) for projection in projections]
    active_tasks = [record for record in task_records if record["active"]]
    closed_tasks = [record for record in task_records if record["status"] == "closed"]
    review_ready = [
        record
        for record in active_tasks
        if str(record["recommended_command"] or "").startswith("devflow task review-patch")
    ]
    failed_verification = [
        record
        for record in active_tasks
        if record["verification_status"] == "failed" or record["status"] == "verification_failed"
    ]
    promotion_ready = [record for record in task_records if record["active"] and record["promotion_readiness"] == "ready"]
    stale_or_conflicted = [record for record in active_tasks if record["stale_or_conflicted"]]
    return {
        "schema_version": SUPERVISOR_SCHEMA_VERSION,
        "repo_root": str(root.resolve()),
        "git_status_summary": _git_status_summary(root),
        "doctor_summary": {
            "status": "unknown",
            "reason": "not run by read-only status; run devflow doctor for fresh diagnostics",
        },
        "active_task_count": len(active_tasks),
        "closed_task_count": len(closed_tasks),
        "review_ready_task_count": len(review_ready),
        "blocked_task_count": len([record for record in active_tasks if record["blocked_reason"]]),
        "verification_failed_task_count": len(failed_verification),
        "promotion_ready_task_count": len(promotion_ready),
        "stale_or_conflicted_task_count": len(stale_or_conflicted),
        "scheduler": {
            "status": scheduler.status,
            "counts": scheduler.counts,
            "next_safe_action": scheduler.next_safe_action,
            "max_parallel_recommendation": scheduler.max_parallel_recommendation,
        },
        "operator_readiness": operator_readiness.model_dump(mode="json"),
        "local_model_inventory": local_model_inventory,
        "local_model_readiness": local_model_readiness,
        "questions": {
            "counts": questions.counts,
            "next_safe_action": questions.next_safe_action,
        },
        "tasks": task_records,
        "generated_at": utc_now().isoformat(),
    }


def render_control_room_status(root: Path) -> str:
    return _tr._json(build_control_room_status(root))


def build_supervisor_packet(root: Path, *, live_discovery: bool = True) -> dict[str, Any]:
    status = build_control_room_status(root, live_discovery=live_discovery)
    policy = build_supervisor_policy()
    scheduler = build_scheduler_snapshot(root)
    operator_readiness = status["operator_readiness"]
    questions = build_question_snapshot(root)
    tasks = [
        _compact_task_record(root, projection.task, projection, include_evidence_paths=True)
        for projection in list_task_status_projections(root)
    ]
    needing_review = [
        task
        for task in tasks
        if str(task["recommended_command"] or "").startswith("devflow task review-patch")
        and task["active"]
    ]
    blocked = [
        task
        for task in tasks
        if task["active"]
        and (task["blocked_reason"] or task["verification_status"] == "failed" or task["status"] == "verification_failed")
    ]
    promotion_ready = [task for task in tasks if task["active"] and task["promotion_readiness"] == "ready"]
    ready_for_preview = [
        task
        for task in tasks
        if task["active"] and str(task["recommended_command"] or "").startswith("devflow task promote-preview")
    ]
    stale_or_conflicted = [task for task in tasks if task["active"] and task["stale_or_conflicted"]]
    next_actions = _packet_next_actions(tasks)
    evidence_paths = _tr._dedupe_preserve_order(
        [path for task in tasks for path in task["evidence_paths"]] + scheduler.evidence_paths + questions.evidence_paths
    )
    return {
        "schema_version": SUPERVISOR_SCHEMA_VERSION,
        "project": {
            "identity": "Dev-Flow local control room",
            "repo_root": status["repo_root"],
            "current_branch": status["git_status_summary"].get("branch"),
            "git_cleanliness": status["git_status_summary"].get("dirty_state"),
        },
        "repo": {
            "root": status["repo_root"],
            "current_branch": status["git_status_summary"].get("branch"),
            "git_cleanliness": status["git_status_summary"].get("dirty_state"),
            "head_sha": status["git_status_summary"].get("head_sha"),
            "origin_main_sha": status["git_status_summary"].get("origin_main_sha"),
        },
        "counts": {
            "active_tasks": status["active_task_count"],
            "closed_tasks": status["closed_task_count"],
            "review_ready_tasks": status["review_ready_task_count"],
            "blocked_tasks": status["blocked_task_count"],
            "verification_failed_tasks": status["verification_failed_task_count"],
            "promotion_ready_tasks": status["promotion_ready_task_count"],
            "stale_or_conflicted_tasks": status["stale_or_conflicted_task_count"],
        },
        "active_tasks": [task for task in tasks if task["active"]],
        "active_task_count": status["active_task_count"],
        "tasks": tasks,
        "review_queue": needing_review,
        "tasks_needing_review": needing_review,
        "tasks_blocked": blocked,
        "tasks_stale_or_conflicted": stale_or_conflicted,
        "tasks_ready_for_preview": ready_for_preview,
        "tasks_promotion_ready": promotion_ready,
        "scheduler": {
            "status": scheduler.status,
            "counts": scheduler.counts,
            "next_safe_action": scheduler.next_safe_action,
            "max_parallel_recommendation": scheduler.max_parallel_recommendation,
        },
        "operator_readiness": operator_readiness,
        "questions": {
            "counts": questions.counts,
            "next_safe_action": questions.next_safe_action,
        },
        "next_safe_action": next_actions[0]["next_safe_action"] if next_actions else "no active task action inferred",
        "next_recommended_actions": next_actions,
        "policy": {
            "schema_version": policy["schema_version"],
            "policy_id": policy["policy_id"],
            "pure_read_only": policy["pure_read_only"],
            "allowed_commands": policy["allowed_commands"],
        },
        "policy_summary": {
            "policy_id": policy["policy_id"],
            "hermes_role": policy["operator_layer"]["hermes_role"],
            "read_only_default": policy["operator_layer"]["read_only_default"],
            "devflow_is_source_of_truth_for": policy["operator_layer"]["devflow_source_of_truth_for"],
            "unrecognized_command_default": policy["unrecognized_command_default"],
        },
        "path_authority": policy["path_authority"],
        "commands_requiring_human_approval": policy["commands_requiring_human_approval"],
        "suggested_read_only_commands": policy["pure_read_only"],
        "suggested_approval_required_commands": policy["commands_requiring_human_approval"],
        "forbidden_actions": policy["forbidden_actions"],
        "evidence_paths": evidence_paths,
        "warnings": _packet_warnings(status, tasks),
        "timestamp": utc_now().isoformat(),
    }


def render_supervisor_packet(root: Path, *, json_output: bool) -> str:
    packet = build_supervisor_packet(root)
    if json_output:
        return _tr._json(packet)
    lines = [
        "Dev-Flow Supervisor Packet",
        f"repo_root: {packet['project']['repo_root']}",
        f"current_branch: {packet['project']['current_branch'] or 'unknown'}",
        f"git_cleanliness: {packet['project']['git_cleanliness'] or 'unknown'}",
        "",
        "Next recommended actions",
    ]
    if packet["next_recommended_actions"]:
        for action in packet["next_recommended_actions"]:
            suffix = ""
            if action["requires_human_approval"]:
                suffix = f" ({action['safety_class']}; human approval required)"
            lines.append(f"- {action['task_id']}: {action['next_safe_action']}{suffix}")
    else:
        lines.append("- None")
    lines.append("")
    lines.append("Commands requiring human approval")
    lines.extend(f"- {command}" for command in packet["commands_requiring_human_approval"])
    lines.append("")
    lines.append("Forbidden actions")
    lines.extend(f"- {action}" for action in packet["forbidden_actions"])
    return "\n".join(lines) + "\n"


def _compact_task_record(
    root: Path,
    task: TaskRecord,
    projection: Any,
    *,
    include_evidence_paths: bool = False,
) -> dict[str, Any]:
    evidence = _tr._task_evidence(root, task, projection=projection)
    worker_lane = git_worker_lane_summary(root, task)
    local_worker_lane = local_worker_lane_summary(root, task)
    next_action = build_task_next_action(root, task.id)
    active = _tr._is_active_task(task)
    blocked_reason = _tr._blocked_reason(projection, evidence) if active else None
    record = {
        "id": task.id,
        "title": task.title,
        "status": task.status,
        "active": active,
        "mode": _tr._task_mode(task, evidence),
        "lane": _tr._task_mode(task, evidence),
        "worker": task.worker,
        "has_proposal_patch": evidence["has_proposal_patch"],
        "patch_review_status": _tr._patch_review_status(evidence),
        "patch_dry_run_status": _tr._patch_dry_run_status(evidence),
        "verification_status": projection.verification_status,
        "promotion_preview_status": evidence["promotion_preview_status"],
        "promotion_readiness": _tr._status_promotion_readiness(task, projection, evidence),
        "blocked_reason": blocked_reason,
        "stale_or_conflicted": evidence["stale_or_conflicted"],
        "next_safe_action": next_action["next_safe_action"],
        "recommended_action": next_action["recommended_action"],
        "recommended_command": next_action["recommended_command"],
        "safety_class": next_action["safety_class"],
        "requires_human_approval": next_action["requires_human_approval"],
        "why_not_auto_runnable": next_action["why_not_auto_runnable"],
        "allowed_commands": next_action["allowed_commands"],
        "commands_requiring_human_approval": next_action["commands_requiring_human_approval"],
        "approval_required_commands": next_action["approval_required_commands"],
    }
    if worker_lane:
        record["worker_lane"] = worker_lane
    if local_worker_lane:
        record["local_worker_lane"] = {
            "lane_type": local_worker_lane["lane_type"],
            "worker_id": local_worker_lane["worker_id"],
            "readiness_status": local_worker_lane["readiness_status"],
            "next_safe_action": local_worker_lane["next_safe_action"],
            "evidence_paths": local_worker_lane.get("evidence_paths") or [],
        }
    if include_evidence_paths:
        lane_evidence = list(worker_lane.get("evidence_paths") or []) if worker_lane else []
        local_lane_evidence = list(local_worker_lane.get("evidence_paths") or []) if local_worker_lane else []
        record["evidence_paths"] = _tr._dedupe_preserve_order(
            evidence["evidence_paths"] + lane_evidence + local_lane_evidence
        )
    return record


def _git_status_summary(root: Path) -> dict[str, Any]:
    state = inspect_git_state(root)
    return {
        "git_repo": state.is_repo,
        "repo_root": state.repo_root,
        "branch": state.branch,
        "head_sha": state.head_sha,
        "origin_main_sha": state.origin_main_sha,
        "dirty_state": "dirty" if state.dirty else "clean",
        "staged_count": state.counts.staged,
        "unstaged_count": state.counts.unstaged,
        "untracked_count": state.counts.untracked,
        "operation_in_progress": state.operation_in_progress,
        "safe_for_worker_writes": state.safe_for_worker_writes,
        "safe_for_promotion": state.safe_for_promotion,
        "safe_for_push": state.safe_for_push,
        "conflicted_files": list(state.conflicted_files),
    }


def _packet_next_actions(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    active = [task for task in tasks if task["active"]]
    priority = {
        "inspect verification evidence and fix task branch/workspace": 0,
        "refresh/rebase/resolve according to existing Git-native promotion mechanics": 1,
    }
    return sorted(
        [
            {
                "task_id": task["id"],
                "title": task["title"],
                "next_safe_action": task["next_safe_action"],
                "recommended_action": task["recommended_action"],
                "recommended_command": task["recommended_command"],
                "safety_class": task["safety_class"],
                "requires_human_approval": task["requires_human_approval"],
                "why_not_auto_runnable": task["why_not_auto_runnable"],
                "allowed_commands": task["allowed_commands"],
                "commands_requiring_human_approval": task["commands_requiring_human_approval"],
                "approval_required_commands": task["approval_required_commands"],
            }
            for task in active
        ],
        key=lambda item: (priority.get(item["next_safe_action"], 10), item["task_id"]),
    )[:10]


def _packet_warnings(status: dict[str, Any], tasks: list[dict[str, Any]]) -> list[str]:
    warnings: list[str] = []
    git = status["git_status_summary"]
    repo_root = str(status.get("repo_root") or "")
    if repo_root in PROHIBITED_CHECKOUT_PATHS:
        warnings.append(f"current repo root is prohibited/quarantined for active work: {repo_root}")
    if git.get("dirty_state") == "dirty":
        warnings.append("main checkout has uncommitted changes")
    if status["stale_or_conflicted_task_count"]:
        warnings.append("one or more tasks have stale/conflicted promotion evidence")
    if any(task["verification_status"] == "failed" for task in tasks):
        warnings.append("one or more tasks have failed verification")
    return warnings
