from __future__ import annotations

import json
import shlex
from pathlib import Path
from typing import Any

from devflow.control_room.evidence_review_detail import EvidenceReviewDetail, build_evidence_review_detail
from devflow.control_room.git_state import inspect_git_state
from devflow.control_room.git_worktree import git_worker_lane_summary
from devflow.control_room.local_worker_lane import local_worker_lane_summary
from devflow.control_room.models import TaskRecord
from devflow.control_room.patch_dry_run import latest_patch_dry_run
from devflow.control_room.patch_review import latest_patch_review
from devflow.control_room.paths import task_dir
from devflow.control_room.persistence import get_task, utc_now
from devflow.control_room.project_registry import project_task_ref
from devflow.control_room.question_resume import build_question_snapshot
from devflow.control_room.scheduler_projection import build_scheduler_snapshot
from devflow.control_room.status_projection import build_task_status_projection, list_task_status_projections
from devflow.control_room.supervisor_policy import (
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
from devflow.control_room.task_closure import read_closure


ACCEPTABLE_PATCH_REVIEW_STATUSES = {"low_risk_candidate", "review_required"}
ACCEPTABLE_PATCH_DRY_RUN_STATUSES = {"would_apply_cleanly", "would_create_files", "would_modify_with_warnings"}
NON_PROMOTABLE_CLOSE_OUTCOMES = {"rejected", "duplicate", "evidence-only", "evidence_only"}


def build_task_next_action(root: Path, task_id: str, *, project_id: str | None = None) -> dict[str, Any]:
    task = get_task(root, task_id)
    projection = build_task_status_projection(root, task_id, task=task)
    evidence = _task_evidence(root, task, projection=projection, project_id=project_id)
    policy = build_supervisor_policy()
    action = _decide_next_action(root, task, projection, evidence)
    if project_id:
        action = _scope_task_action_commands(action, project_id)
    action.update(
        {
            "schema_version": SUPERVISOR_SCHEMA_VERSION,
            "task_id": task.id,
            "task_ref": project_task_ref(task.id, project_id),
            "status": task.status,
            "evidence_considered": evidence["evidence_paths"] + evidence["missing_evidence"],
            "forbidden_commands": policy["forbidden_actions"],
        }
    )
    if project_id:
        action["project_id"] = project_id
        action["project_root"] = str(root)
    if evidence["unknowns"]:
        action["unknowns"] = sorted(set(action.get("unknowns", []) + evidence["unknowns"]))
    return action


def render_task_next_action(root: Path, task_id: str, *, json_output: bool, project_id: str | None = None) -> str:
    action = build_task_next_action(root, task_id, project_id=project_id)
    if json_output:
        return _json(action)
    lines = [
        f"task: {action['task_ref']}",
        f"status: {action['status']}",
        f"next_safe_action: {action.get('plain_language_next_safe_action') or action['next_safe_action']}",
        f"recommended_action: {action['recommended_action']}",
        f"recommended_command: {action['recommended_command'] or 'none'}",
        f"safety_class: {action['safety_class']}",
        f"reason: {action['reason']}",
        f"requires_human_approval: {'yes' if action['requires_human_approval'] else 'no'}",
    ]
    if project_id:
        lines.insert(1, f"project_root: {root}")
    if action.get("recommended_command_template"):
        lines.append(f"recommended_command_template: {action['recommended_command_template']}")
    if action.get("command_template_note"):
        lines.append(f"command_template_note: {action['command_template_note']}")
    if action["why_not_auto_runnable"]:
        lines.append(f"why_not_auto_runnable: {action['why_not_auto_runnable']}")
    if action["allowed_commands"]:
        lines.append("allowed_commands:")
        lines.extend(f"  - {command}" for command in action["allowed_commands"])
    if action["commands_requiring_human_approval"]:
        lines.append("commands_requiring_human_approval:")
        lines.extend(f"  - {command}" for command in action["commands_requiring_human_approval"])
    if action["unknowns"]:
        lines.append("unknowns:")
        lines.extend(f"  - {unknown}" for unknown in action["unknowns"])
    return "\n".join(lines) + "\n"


def build_task_review(root: Path, task_id: str, *, project_id: str | None = None) -> dict[str, Any]:
    task = get_task(root, task_id)
    projection = build_task_status_projection(root, task_id, task=task)
    evidence = _task_evidence(root, task, projection=projection, project_id=project_id)
    next_action = build_task_next_action(root, task_id, project_id=project_id)
    policy = build_supervisor_policy()
    closure = read_closure(root, task.id)
    evidence_detail = evidence["detail"]
    review = {
        "schema_version": SUPERVISOR_SCHEMA_VERSION,
        "task": {
            "id": task.id,
            "ref": project_task_ref(task.id, project_id),
            "title": task.title,
            "status": task.status,
            "active": _is_active_task(task),
            "worker": task.worker,
            "mode": _task_mode(task, evidence),
            "lane": _task_mode(task, evidence),
        },
        "current_state": {
            "display_status": projection.display_status,
            "latest_log_line": projection.latest,
            "blocked_reason": _blocked_reason(projection, evidence),
        },
        "changed_files": evidence["changed_files"],
        "patch_proposal": {
            "has_proposal_patch": evidence["has_proposal_patch"],
            "paths": evidence["proposal_patch_paths"],
        },
        "patch_review": {
            "status": _patch_review_status(evidence),
            "path": evidence["patch_review_path"],
            "risk": _string_from_mapping(evidence["patch_review"], "risk"),
        },
        "patch_dry_run": {
            "status": _patch_dry_run_status(evidence),
            "path": evidence["patch_dry_run_path"],
            "risk": _string_from_mapping(evidence["patch_dry_run"], "risk"),
        },
        "patch_application": {
            "status": "applied" if evidence["patch_application"] else "not_applied",
            "path": evidence["patch_application_path"],
        },
        "verification": {
            "status": evidence["verification_status"],
            "path": evidence["verification_path"],
            "log_path": projection.verification_log_path,
            "command": projection.verification_command,
        },
        "promotion_preview": {
            "status": evidence["promotion_preview_status"],
            "path": evidence["promotion_preview_path"],
            "promotion_readiness": evidence["promotion_readiness"],
        },
        "git": {
            "branch_name": task.branch_name,
            "workspace_path": task.workspace_path,
            "workspace_kind": task.workspace_kind,
            "workspace_commit": task.workspace_commit,
            "workspace_dirty": task.workspace_dirty,
            "facts_path": evidence["git_facts_path"],
        },
        "risks": _review_risks(projection, evidence),
        "blocked_reasons": [reason for reason in [_blocked_reason(projection, evidence)] if reason],
        "next_action": next_action,
        "commands_safe_to_run": next_action["allowed_commands"],
        "commands_requiring_human_approval": (
            next_action["commands_requiring_human_approval"] or policy["commands_requiring_human_approval"]
        ),
        "forbidden_actions": policy["forbidden_actions"],
        "evidence_paths": evidence["evidence_paths"],
        "missing_optional_artifacts": evidence["missing_evidence"],
        "evidence_detail": _evidence_detail_payload(evidence_detail),
        "closed": {
            "outcome": closure.get("outcome") if closure else task.close_outcome,
            "reason": closure.get("reason") if closure else task.close_reason,
        },
    }
    if project_id:
        review["project"] = {"id": project_id, "root": str(root)}
    return review


def render_task_review(root: Path, task_id: str, *, json_output: bool, project_id: str | None = None) -> str:
    review = build_task_review(root, task_id, project_id=project_id)
    if json_output:
        return _json(review)
    task = review["task"]
    lines = [
        f"Task: {task['ref']} - {task['title']}",
        f"Status: {task['status']}",
        f"Worker/lane: {task['worker']} / {task['lane']}",
        f"Current state: {review['current_state']['display_status']}",
        f"Next safe action: {review['next_action']['next_safe_action']}",
        "",
        "Evidence summary",
        f"- proposal.patch: {'present' if review['patch_proposal']['has_proposal_patch'] else 'missing'}",
        f"- patch review: {review['patch_review']['status']}",
        f"- patch dry-run: {review['patch_dry_run']['status']}",
        f"- patch application: {review['patch_application']['status']}",
        f"- verification: {review['verification']['status']}",
        f"- promotion preview: {review['promotion_preview']['status']}",
    ]
    if review["changed_files"]:
        lines.append("")
        lines.append("Changed files")
        lines.extend(f"- {name}" for name in review["changed_files"][:20])
    if review["risks"]:
        lines.append("")
        lines.append("Risks / blocked reasons")
        lines.extend(f"- {risk}" for risk in review["risks"])
    lines.append("")
    lines.append("Evidence paths")
    lines.extend(f"- {path}" for path in review["evidence_paths"])
    lines.append("")
    lines.append("Commands safe to run")
    if review["commands_safe_to_run"]:
        lines.extend(f"- {command}" for command in review["commands_safe_to_run"])
    else:
        lines.append("- None")
    lines.append("")
    lines.append("Commands requiring human approval")
    lines.extend(f"- {command}" for command in review["commands_requiring_human_approval"])
    lines.append("")
    lines.append("Forbidden/bypass actions")
    lines.extend(f"- {action}" for action in review["forbidden_actions"])
    return "\n".join(lines) + "\n"


def build_control_room_status(root: Path) -> dict[str, Any]:
    from devflow.control_room.operator_readiness import build_operator_readiness_snapshot

    projections = list_task_status_projections(root)
    scheduler = build_scheduler_snapshot(root)
    operator_readiness = build_operator_readiness_snapshot(root)
    questions = build_question_snapshot(root)
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
        "questions": {
            "counts": questions.counts,
            "next_safe_action": questions.next_safe_action,
        },
        "tasks": task_records,
        "generated_at": utc_now().isoformat(),
    }


def render_control_room_status(root: Path) -> str:
    return _json(build_control_room_status(root))


def build_supervisor_packet(root: Path) -> dict[str, Any]:
    status = build_control_room_status(root)
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
    evidence_paths = _dedupe_preserve_order(
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
        return _json(packet)
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
    evidence = _task_evidence(root, task, projection=projection)
    worker_lane = git_worker_lane_summary(root, task)
    local_worker_lane = local_worker_lane_summary(root, task)
    next_action = build_task_next_action(root, task.id)
    active = _is_active_task(task)
    blocked_reason = _blocked_reason(projection, evidence) if active else None
    record = {
        "id": task.id,
        "title": task.title,
        "status": task.status,
        "active": active,
        "mode": _task_mode(task, evidence),
        "lane": _task_mode(task, evidence),
        "worker": task.worker,
        "has_proposal_patch": evidence["has_proposal_patch"],
        "patch_review_status": _patch_review_status(evidence),
        "patch_dry_run_status": _patch_dry_run_status(evidence),
        "verification_status": projection.verification_status,
        "promotion_preview_status": evidence["promotion_preview_status"],
        "promotion_readiness": _status_promotion_readiness(task, projection, evidence),
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
        record["evidence_paths"] = _dedupe_preserve_order(
            evidence["evidence_paths"] + lane_evidence + local_lane_evidence
        )
    return record


def _decide_next_action(root: Path, task: TaskRecord, projection: Any, evidence: dict[str, Any]) -> dict[str, Any]:
    task_id = task.id
    unknowns = evidence["unknowns"][:]
    if task.status == "closed":
        outcome = (task.close_outcome or "").strip()
        reason = "task is closed"
        if outcome in NON_PROMOTABLE_CLOSE_OUTCOMES:
            reason = f"task is closed with non-promotable outcome '{outcome}'"
        return _action(
            "no action; task is closed or non-promotable",
            reason,
            [],
            [],
            False,
            "high",
            unknowns,
        )
    if task.status == "promoted":
        return _action(
            "no action; task is already promoted",
            "task has already been promoted to the main checkout",
            [],
            [],
            False,
            "high",
            unknowns,
        )
    if projection.verification_status == "failed" or task.status == "verification_failed":
        return _action(
            "inspect verification evidence and fix task branch/workspace",
            "verification failed and must be repaired before further gates",
            [f"devflow task review {task_id}", f"devflow task log {task_id} --verify --tail 80"],
            [],
            False,
            "high",
            unknowns,
            recommended_command=f"devflow task review {task_id}",
        )
    if evidence["stale_or_conflicted"]:
        return _action(
            "refresh/rebase/resolve according to existing Git-native promotion mechanics",
            "promotion evidence reports a stale baseline or possible conflict",
            [f"devflow task review {task_id}"],
            [f"devflow task promote-preview {task_id}"],
            False,
            "medium",
            unknowns,
            recommended_command=f"devflow task promote-preview {task_id}",
        )
    if _promotion_preview_ready(evidence):
        return _action(
            f"human approval required before devflow task promote {task_id}",
            "promotion preview says the task is ready; promotion still requires a human gate",
            [f"devflow task review {task_id}"],
            [f"devflow task promote {task_id}"],
            True,
            "high",
            unknowns,
            recommended_command=f"devflow task promote {task_id}",
        )
    if (task.status == "verified" or projection.verification_status == "passed") and evidence["promotion_preview_status"] == "unknown":
        return _action(
            f"run devflow task promote-preview {task_id}",
            "verification passed and no promotion preview evidence is available",
            [],
            [f"devflow task promote-preview {task_id}"],
            False,
            "high",
            unknowns,
            recommended_command=f"devflow task promote-preview {task_id}",
        )
    if evidence["patch_application"] and projection.verification_status != "passed":
        return _action(
            f"run devflow task verify {task_id}",
            "patch has been applied to the isolated workspace but verification has not passed",
            [],
            [f"devflow task verify {task_id} --shell \"<command>\""],
            False,
            "high",
            unknowns,
            recommended_command=f"devflow task verify {task_id} --shell \"<command>\"",
        )
    if evidence["has_proposal_patch"] and not evidence["patch_application"]:
        review_status = _patch_review_status(evidence)
        if review_status not in ACCEPTABLE_PATCH_REVIEW_STATUSES:
            command = _patch_review_command(task_id, evidence)
            return _action(
                f"run {command}",
                "proposal.patch exists but acceptable patch-review evidence is missing",
                [],
                [command],
                False,
                "high",
                unknowns,
                recommended_command=command,
            )
        dry_run_status = _patch_dry_run_status(evidence)
        if dry_run_status not in ACCEPTABLE_PATCH_DRY_RUN_STATUSES:
            command = f"devflow task patch-dry-run {task_id}"
            return _action(
                f"run {command}",
                "patch review is acceptable but dry-run evidence is missing or not acceptable",
                [],
                [command],
                False,
                "high",
                unknowns,
                recommended_command=command,
            )
        return _action(
            f"human approval required before devflow task apply-patch {task_id}",
            "reviewed dry-run evidence is ready; applying the patch mutates the isolated workspace",
            [f"devflow task review {task_id}"],
            [f"devflow task apply-patch {task_id}"],
            True,
            "high",
            unknowns,
            recommended_command=f"devflow task apply-patch {task_id}",
        )
    if task.status == "complete" or projection.manual_agent_state == "result_present":
        return _action(
            f"run devflow task verify {task_id}",
            "worker output exists but verification has not passed",
            [],
            [f"devflow task verify {task_id} --shell \"<command>\""],
            False,
            "high",
            unknowns,
            recommended_command=f"devflow task verify {task_id} --shell \"<command>\"",
        )
    if task.status == "created":
        return _action(
            "run worker or provide patch evidence",
            "task exists but no worker or proposal evidence is available",
            [],
            [f"devflow task run {task_id} --worker shell -- <command>"],
            False,
            "high",
            unknowns,
            recommended_command=f"devflow task run {task_id} --worker shell -- <command>",
        )
    if task.status == "running":
        return _action(
            f"inspect task {task_id}",
            "task is in progress",
            [f"devflow task show {task_id}", f"devflow task log {task_id} --tail 80"],
            [],
            False,
            "medium",
            unknowns,
            recommended_command=f"devflow task show {task_id}",
        )
    return _action(
        f"inspect task {task_id}",
        "no more specific safe action could be inferred from available evidence",
        [f"devflow task review {task_id}", f"devflow task show {task_id}"],
        [],
        False,
        "low",
        unknowns,
        recommended_command=f"devflow task review {task_id}",
    )


def _action(
    next_safe_action: str,
    reason: str,
    allowed_commands: list[str],
    commands_requiring_human_approval: list[str],
    requires_human_approval: bool,
    confidence: str,
    unknowns: list[str],
    *,
    recommended_command: str | None = None,
) -> dict[str, Any]:
    recommended_action = next_safe_action
    pure_read_only_commands: list[str] = []
    approval_commands = commands_requiring_human_approval[:]
    for command in allowed_commands:
        classification = classify_supervisor_command(command)
        if classification["safety_class"] == PURE_READ_ONLY:
            pure_read_only_commands.append(command)
        else:
            approval_commands.append(command)

    recommended_classification = (
        classify_supervisor_command(recommended_command) if recommended_command else None
    )
    safety_class = recommended_classification["safety_class"] if recommended_classification else PURE_READ_ONLY
    why_not_auto_runnable = (
        recommended_classification["why_not_auto_runnable"] if recommended_classification else None
    )
    if recommended_classification and safety_class != PURE_READ_ONLY:
        requires_human_approval = True
        approval_commands.append(recommended_command)
        next_safe_action = _human_approval_next_action(recommended_command, safety_class)

    approval_commands = _dedupe_preserve_order(approval_commands)
    return {
        "next_safe_action": next_safe_action,
        **_plain_language_command_help(recommended_command),
        "recommended_action": recommended_action,
        "recommended_command": recommended_command,
        "safety_class": safety_class,
        "reason": reason,
        "allowed_commands": pure_read_only_commands,
        "pure_read_only_commands": pure_read_only_commands,
        "requires_human_approval": requires_human_approval,
        "why_not_auto_runnable": why_not_auto_runnable,
        "commands_requiring_human_approval": approval_commands,
        "approval_required_commands": [_approval_required_command(command) for command in approval_commands],
        "confidence": confidence,
        "unknowns": sorted(set(unknowns)),
    }


def _human_approval_next_action(command: str, safety_class: str) -> str:
    if safety_class == FORBIDDEN_FOR_SUPERVISOR:
        return f"do not run {command}; inspect policy or ask a human for an approved Dev-Flow command"
    return f"request human approval before running {command}"


def _plain_language_command_help(command: str | None) -> dict[str, str]:
    if not command:
        return {}
    if " task run " in command and "-- <command>" in command:
        return {
            "plain_language_next_safe_action": (
                "Choose the exact shell command the worker should run in this task workspace."
            ),
            "recommended_command_template": command.replace("<command>", "<your-command>"),
            "command_template_note": "Replace <your-command> with the real command you approve.",
        }
    return {}


def _scope_task_action_commands(action: dict[str, Any], project_id: str) -> dict[str, Any]:
    scoped = dict(action)
    replacements: dict[str, str] = {}

    recommended = scoped.get("recommended_command")
    if isinstance(recommended, str):
        scoped_recommended = _scope_task_command(recommended, project_id)
        replacements[recommended] = scoped_recommended
        scoped["recommended_command"] = scoped_recommended
        template = scoped.get("recommended_command_template")
        if isinstance(template, str):
            scoped["recommended_command_template"] = _scope_task_command(template, project_id)
        classification = classify_supervisor_command(scoped_recommended)
        scoped["safety_class"] = classification["safety_class"]
        scoped["why_not_auto_runnable"] = classification["why_not_auto_runnable"]

    for key in ("allowed_commands", "pure_read_only_commands", "commands_requiring_human_approval"):
        commands = scoped.get(key)
        if isinstance(commands, list):
            scoped_commands = []
            for command in commands:
                if isinstance(command, str):
                    scoped_command = _scope_task_command(command, project_id)
                    replacements[command] = scoped_command
                    scoped_commands.append(scoped_command)
                else:
                    scoped_commands.append(command)
            scoped[key] = _dedupe_preserve_order(scoped_commands)

    for key in ("next_safe_action", "recommended_action"):
        text = scoped.get(key)
        if isinstance(text, str):
            for original, replacement in replacements.items():
                text = text.replace(original, replacement)
            scoped[key] = text

    approval_commands = scoped.get("commands_requiring_human_approval")
    if isinstance(approval_commands, list):
        scoped["approval_required_commands"] = [
            _approval_required_command(command) for command in approval_commands if isinstance(command, str)
        ]

    return scoped


def _scope_task_command(command: str, project_id: str) -> str:
    parts = command.split()
    if len(parts) < 4 or parts[0] != "devflow" or parts[1] != "task":
        return command
    if "--project" in parts:
        return command
    quoted_project = shlex.quote(project_id)
    return " ".join([*parts[:4], "--project", quoted_project, *parts[4:]])


def _approval_required_command(command: str) -> dict[str, Any]:
    classification = classify_supervisor_command(command)
    return {
        "command": command,
        "safety_class": classification["safety_class"],
        "requires_human_approval": True,
        "why_not_auto_runnable": classification["why_not_auto_runnable"],
    }


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _evidence_detail_payload(detail: EvidenceReviewDetail) -> dict[str, Any]:
    return {
        "schema_version": detail.schema_version,
        "review_state": detail.review_state,
        "review_reason": detail.review_reason,
        "operator_summary": detail.operator_summary,
        "artifacts": [artifact.model_dump(mode="json") for artifact in detail.artifacts],
        "changed_files": detail.changed_files,
        "changed_file_preview": detail.changed_file_preview,
        "agent_evidence_summary": detail.agent_evidence_summary,
        "notes": detail.notes,
    }


def _read_display_json(root: Path, display_path: str | None) -> dict[str, Any] | None:
    if not display_path:
        return None
    path = Path(display_path)
    candidate = path if path.is_absolute() else root / path
    return _read_json(candidate)


def _task_evidence(
    root: Path,
    task: TaskRecord,
    *,
    projection: Any | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    projection = projection or build_task_status_projection(root, task.id, task=task)
    detail = build_evidence_review_detail(root, projection, project_id=project_id)
    path = task_dir(root, task.id)
    verification = _read_json(path / "verification.json")
    patch_review = latest_patch_review(root, task.id)
    patch_dry_run = latest_patch_dry_run(root, task.id)
    patch_application = _read_display_json(root, detail.patch_application_path)
    promotion_preview = _read_display_json(root, detail.promotion_preview_path)
    promotion_status = "available" if promotion_preview else "unknown"
    verification_status = _artifact_status(verification, "status")
    stale_or_conflicted = _stale_or_conflicted(promotion_preview)
    verification_path = detail.verification_path if verification else None
    return {
        "detail": detail,
        "evidence_paths": detail.evidence_paths,
        "missing_evidence": detail.missing_evidence,
        "unknowns": sorted({f"missing {path}" for path in detail.missing_evidence}),
        "has_proposal_patch": bool(detail.proposal_patch_paths),
        "proposal_patch_paths": detail.proposal_patch_paths,
        "patch_review": patch_review,
        "patch_review_path": detail.patch_review_path,
        "patch_dry_run": patch_dry_run,
        "patch_dry_run_path": detail.patch_dry_run_path,
        "patch_application": patch_application,
        "patch_application_path": detail.patch_application_path,
        "verification": verification,
        "verification_status": verification_status,
        "verification_path": verification_path,
        "promotion_preview": promotion_preview,
        "promotion_preview_path": detail.promotion_preview_path,
        "promotion_preview_status": promotion_status,
        "promotion_readiness": _promotion_readiness_value(promotion_preview),
        "stale_or_conflicted": stale_or_conflicted,
        "changed_files": detail.changed_files,
        "git_facts_path": detail.git_facts_path,
    }


def _patch_review_command(task_id: str, evidence: dict[str, Any]) -> str:
    for path in evidence["proposal_patch_paths"]:
        parts = Path(path).parts
        if "agents" in parts:
            index = parts.index("agents")
            if len(parts) > index + 1:
                return f"devflow task review-patch {task_id} --agent {parts[index + 1]}"
    return f"devflow task review-patch {task_id}"


def _status_promotion_readiness(task: TaskRecord, projection: Any, evidence: dict[str, Any]) -> str:
    if task.status == "promoted":
        return "promoted"
    if _promotion_preview_ready(evidence):
        return "ready"
    if evidence["promotion_readiness"] != "unknown":
        return evidence["promotion_readiness"]
    if (task.status == "verified" or projection.verification_status == "passed") and projection.promotion_ready:
        return "ready"
    if projection.promotion_blockers:
        return "not_ready"
    return "unknown"


def _promotion_preview_ready(evidence: dict[str, Any]) -> bool:
    return evidence["promotion_readiness"] == "ready"


def _promotion_readiness_value(preview: dict[str, Any] | None) -> str:
    if not preview:
        return "unknown"
    readiness = preview.get("promotion_readiness")
    if isinstance(readiness, str):
        return readiness
    ready = preview.get("ready")
    if isinstance(ready, bool):
        return "ready" if ready else "not_ready"
    return "unknown"


def _stale_or_conflicted(preview: dict[str, Any] | None) -> bool:
    if not preview:
        return False
    conflict = str(preview.get("conflict_prediction") or "")
    return bool(preview.get("baseline_stale") or preview.get("origin_baseline_stale") or conflict not in {"", "clean"})


def _review_risks(projection: Any, evidence: dict[str, Any]) -> list[str]:
    risks: list[str] = []
    if projection.failed_verification:
        risks.append("verification failed")
    if evidence["stale_or_conflicted"]:
        risks.append("promotion preview reports stale baseline or conflict risk")
    if evidence["missing_evidence"]:
        risks.append("some optional evidence artifacts are missing")
    if projection.promotion_blockers:
        risks.extend(projection.promotion_blockers)
    return sorted(set(risks))


def _blocked_reason(projection: Any, evidence: dict[str, Any]) -> str | None:
    if projection.manual_agent_question:
        return projection.manual_agent_question
    if projection.failed_verification:
        return "verification failed"
    if projection.is_blocked:
        return "task is blocked"
    if evidence["stale_or_conflicted"]:
        return "stale baseline or conflict risk"
    return None


def _task_mode(task: TaskRecord, evidence: dict[str, Any]) -> str:
    if task.workspace_kind == "git_worktree":
        return "git-worktree"
    if evidence["has_proposal_patch"]:
        return "patch-proposal"
    if task.worker in {"qwen-planner", "gemma-reviewer"} or "local" in (task.worker or ""):
        return "advisory"
    if task.workspace_kind in {"copy_workspace", "copy-workspace"} or ".devflow/workspaces/" in task.workspace:
        return "copy-workspace"
    return "unknown"


def _is_active_task(task: TaskRecord) -> bool:
    return task.status not in {"closed", "promoted"}


def _patch_review_status(evidence: dict[str, Any]) -> str:
    return _artifact_status(evidence["patch_review"], "review_status")


def _patch_dry_run_status(evidence: dict[str, Any]) -> str:
    return _artifact_status(evidence["patch_dry_run"], "dry_run_status")


def _artifact_status(payload: dict[str, Any] | None, key: str) -> str:
    if not payload:
        return "unknown"
    value = payload.get(key)
    return str(value) if value else "unknown"


def _string_from_mapping(payload: dict[str, Any] | None, key: str) -> str | None:
    if not payload:
        return None
    value = payload.get(key)
    return str(value) if value is not None else None


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


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


def _json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, indent=2) + "\n"
