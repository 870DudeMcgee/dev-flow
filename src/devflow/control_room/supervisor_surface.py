from __future__ import annotations

import json
import shlex
from pathlib import Path
from typing import Any

from devflow.control_room.git_state import inspect_git_state
from devflow.control_room.git_worktree import git_worker_lane_summary, is_git_worktree_task, worker_id_for_task
from devflow.control_room.local_worker_lane import local_worker_lane_summary
from devflow.control_room.models import TASK_SCHEMA_VERSION, TaskRecord
from devflow.control_room.patch_dry_run import latest_patch_dry_run
from devflow.control_room.patch_review import latest_patch_review
from devflow.control_room.paths import relative_path, task_dir, task_worker_dir
from devflow.control_room.persistence import get_task, list_tasks, utc_now
from devflow.control_room.project_registry import project_task_ref
from devflow.control_room.question_resume import build_question_snapshot
from devflow.control_room.qwopus_evidence import read_qwopus_evidence
from devflow.control_room.scheduler_projection import build_scheduler_snapshot
from devflow.control_room.status_projection import build_task_status_projection, list_task_status_projections
from devflow.control_room.task_closure import read_closure


SUPERVISOR_SCHEMA_VERSION = 1
ACCEPTABLE_PATCH_REVIEW_STATUSES = {"low_risk_candidate", "review_required"}
ACCEPTABLE_PATCH_DRY_RUN_STATUSES = {"would_apply_cleanly", "would_create_files", "would_modify_with_warnings"}
NON_PROMOTABLE_CLOSE_OUTCOMES = {"rejected", "duplicate", "evidence-only", "evidence_only"}
PURE_READ_ONLY = "pure_read_only"
APPROVAL_REQUIRED_EVIDENCE_WRITING = "approval_required_evidence_writing"
APPROVAL_REQUIRED_TASK_STATE = "approval_required_task_state"
APPROVAL_REQUIRED_WORKER_RUNTIME = "approval_required_worker_runtime"
APPROVAL_REQUIRED_GIT = "approval_required_git"
FORBIDDEN_FOR_SUPERVISOR = "forbidden_for_supervisor"
JOSH_CANONICAL_CHECKOUT = "<repo-root>"
PROHIBITED_CHECKOUT_PATHS = ["/Users/jewelbait/Desktop/DevFlow"]

PURE_READ_ONLY_COMMANDS = [
    "devflow doctor",
    "devflow doctor --strict",
    "devflow reconcile",
    "devflow dashboard",
    "devflow dashboard --json",
    "devflow scheduler status",
    "devflow scheduler status --json",
    "devflow question list",
    "devflow question list --json",
    "devflow question show",
    "devflow question show --json",
    "devflow status --json",
    "devflow next",
    "devflow supervisor policy",
    "devflow supervisor policy --json",
    "devflow supervisor packet",
    "devflow supervisor packet --json",
    "devflow supervisor route-message",
    "devflow supervisor route-message --json",
    "devflow hermes imessage-check",
    "devflow hermes imessage-check --json",
    "devflow git status",
    "devflow goal list",
    "devflow goal show",
    "devflow goal status",
    "devflow goal next",
    "devflow goal slices",
    "devflow project list",
    "devflow project show",
    "devflow project status",
    "devflow project doctor",
    "devflow task list",
    "devflow task show",
    "devflow task review",
    "devflow task review --json",
    "devflow task next-action",
    "devflow task next-action --json",
    "devflow task log",
    "devflow task history",
    "devflow task capsule",
    "devflow task packet",
    "devflow task promote-preview",
    "devflow task cleanup --dry-run",
    "devflow worktree list",
    "devflow worktree prune",
    "devflow branch list",
    "devflow agent list",
    "devflow agent list --json",
    "devflow agent show",
    "devflow agent show --json",
    "devflow agent policy",
    "devflow agent policy --json",
    "devflow agent catalog",
    "devflow agent catalog --json",
    "devflow agent run --dry-run",
    "devflow agent run --dry-run --json",
    "devflow agent advise --dry-run",
    "devflow agent advise --dry-run --json",
    "devflow agent add-provider --dry-run",
    "devflow agent add-provider --dry-run --json",
    "devflow agent add-model --dry-run",
    "devflow agent add-model --dry-run --json",
    "devflow agent packet",
    "devflow knowledge list",
    "devflow knowledge show",
    "devflow knowledge search",
    "devflow idea list",
    "devflow idea show",
    "devflow idea create-goal --dry-run",
    "devflow idea create-task --dry-run",
    "devflow idea scaffold-goal --dry-run",
    "devflow dogfood list",
    "devflow dogfood show",
]

APPROVAL_REQUIRED_EVIDENCE_WRITING_COMMANDS = [
    "devflow task review-patch",
    "devflow task patch-dry-run",
    "devflow task packet --save",
    "devflow task normalize-proposal",
    "devflow task orchestrate --plan-only",
    "devflow task escalation-packet",
    "devflow task capsule --export-md",
    "devflow worker validate-outcome",
    "devflow scheduler retry",
    "devflow question answer",
    "devflow question resolve",
    "devflow knowledge capture",
    "devflow idea capture",
    "devflow idea classify",
    "devflow idea promote",
    "devflow idea scaffold-goal",
    "devflow idea park",
    "devflow idea archive",
]

APPROVAL_REQUIRED_TASK_STATE_COMMANDS = [
    "devflow init",
    "devflow goal init",
    "devflow goal create-task",
    "devflow goal activate",
    "devflow goal pause",
    "devflow goal block",
    "devflow goal complete",
    "devflow goal archive",
    "devflow project create",
    "devflow project import",
    "devflow project archive",
    "devflow project remove",
    "devflow agent add-provider",
    "devflow agent add-model",
    "devflow task create",
    "devflow task close",
    "devflow task finalize",
    "devflow task cleanup",
    "devflow task cleanup --preview",
    "devflow task cleanup --apply",
    "devflow task prune-closed --preview",
    "devflow task prune-closed --apply",
    "devflow task apply-patch",
    "devflow knowledge promote",
    "devflow knowledge reject",
    "devflow idea create-goal",
    "devflow idea create-task",
]

APPROVAL_REQUIRED_WORKER_RUNTIME_COMMANDS = [
    "devflow supervise",
    "devflow task run",
    "devflow task local",
    "devflow task local-review",
    "devflow agent run",
    "devflow agent advise",
    "devflow agent propose-patch",
    "devflow task verify",
    "devflow dogfood run",
]

APPROVAL_REQUIRED_GIT_COMMANDS = [
    "devflow sync-main",
    "devflow push-main",
    "devflow project connect-github",
    "devflow task promote",
    "devflow task finalize --commit",
    "devflow worktree prune --apply",
    "devflow branch archive",
]

FORBIDDEN_SUPERVISOR_ACTIONS = [
    "using quarantined or stale hardcoded checkout paths for current work",
    "direct source edits outside a Dev-Flow task workspace/worktree",
    "direct source edits by Hermes",
    "direct edits to .devflow state files",
    "direct edits to the main checkout",
    "direct mutation of task.yaml/events.jsonl/verification.json by hand",
    "direct git mutation outside Dev-Flow commands",
    "bypassing patch review or dry-run",
    "bypassing verification",
    "bypassing approval gates",
    "promoting without human approval",
    "running hidden background schedulers against Dev-Flow",
    "creating a second source of truth",
    "storing canonical state outside .devflow",
    "treating Hermes memory as canonical Dev-Flow state",
    "spawning unbounded parallel workers",
    "letting multiple writer agents edit one task/worktree",
    "mixing personal/factory/iMessage automation authority with Dev-Flow repo authority",
    "exposing secrets or message contents unnecessarily in logs",
    "autonomous provider routing",
    "remote provider task-run execution unless explicitly promoted into the stable contract",
    "any command not recognized by the supervisor policy",
]

SAFETY_CLASS_REASONS = {
    PURE_READ_ONLY: "command inspects or previews Dev-Flow state and must not mutate source files, task state, Git index, branches, remotes, or promotion state",
    APPROVAL_REQUIRED_EVIDENCE_WRITING: "command writes derived evidence, packets, reviews, dry-runs, knowledge, or logs",
    APPROVAL_REQUIRED_TASK_STATE: "command creates, closes, finalizes, cleans up, applies patches, or changes Dev-Flow state",
    APPROVAL_REQUIRED_WORKER_RUNTIME: "command runs workers, local agents, verification, tests, model calls, or supervisor loops",
    APPROVAL_REQUIRED_GIT: "command can affect branches, commits, pushes, promotion, archives, worktrees, merge state, or main",
    FORBIDDEN_FOR_SUPERVISOR: "command is not recognized by the supervisor policy or bypasses Dev-Flow approval/safety gates",
}


def build_supervisor_policy() -> dict[str, Any]:
    commands_requiring_human_approval = (
        APPROVAL_REQUIRED_EVIDENCE_WRITING_COMMANDS
        + APPROVAL_REQUIRED_TASK_STATE_COMMANDS
        + APPROVAL_REQUIRED_WORKER_RUNTIME_COMMANDS
        + APPROVAL_REQUIRED_GIT_COMMANDS
    )
    return {
        "schema_version": SUPERVISOR_SCHEMA_VERSION,
        "policy_id": "devflow-supervisor-policy",
        "pure_read_only": PURE_READ_ONLY_COMMANDS,
        "allowed_commands": PURE_READ_ONLY_COMMANDS,
        "approval_required_evidence_writing": APPROVAL_REQUIRED_EVIDENCE_WRITING_COMMANDS,
        "approval_required_task_state": APPROVAL_REQUIRED_TASK_STATE_COMMANDS,
        "approval_required_worker_runtime": APPROVAL_REQUIRED_WORKER_RUNTIME_COMMANDS,
        "approval_required_git": APPROVAL_REQUIRED_GIT_COMMANDS,
        "approval_required_commands_by_class": {
            APPROVAL_REQUIRED_EVIDENCE_WRITING: APPROVAL_REQUIRED_EVIDENCE_WRITING_COMMANDS,
            APPROVAL_REQUIRED_TASK_STATE: APPROVAL_REQUIRED_TASK_STATE_COMMANDS,
            APPROVAL_REQUIRED_WORKER_RUNTIME: APPROVAL_REQUIRED_WORKER_RUNTIME_COMMANDS,
            APPROVAL_REQUIRED_GIT: APPROVAL_REQUIRED_GIT_COMMANDS,
        },
        "commands_requiring_human_approval": commands_requiring_human_approval,
        "forbidden_for_supervisor": FORBIDDEN_SUPERVISOR_ACTIONS,
        "forbidden_actions": FORBIDDEN_SUPERVISOR_ACTIONS,
        "unrecognized_command_default": FORBIDDEN_FOR_SUPERVISOR,
        "safety_class_reasons": SAFETY_CLASS_REASONS,
        "operator_layer": {
            "hermes_role": "external operator/chat/scheduling layer",
            "read_only_default": True,
            "devflow_source_of_truth_for": [
                "task state",
                "evidence",
                "worker isolation",
                "verification",
                "git readiness",
                "cleanup",
                "promotion",
            ],
            "may": [
                "summarize Dev-Flow artifacts",
                "recommend next safe actions",
                "packetize supervisor-safe evidence",
                "notify a human operator",
                "scheduled read-only briefs",
                "prepare Codex prompts",
                "capture approved ideas through Dev-Flow commands",
            ],
            "must_not": [
                "directly edit .devflow",
                "directly edit source files",
                "directly mutate git index, branches, remotes, or promotion state",
                "create a hidden state layer",
                "treat Hermes memory as canonical Dev-Flow state",
                "spawn unbounded parallel workers",
                "allow multiple writer agents on one task/worktree",
                "log secrets or message contents unnecessarily",
            ],
            "human_approval_required_for": [
                "task creation",
                "knowledge capture",
                "idea capture and review",
                "bounded worker proposal/review flows",
                "promotion",
                "merge",
                "push",
                "cleanup apply",
                "closed evidence pruning apply",
                "worker execution",
                "verification runs",
                "broad mutation",
            ],
            "browser_allowed_mutations": [
                "idea capture",
                "task creation",
                "shell worker execution",
                "model/provider onboarding",
                "task verification",
                "task promotion",
            ],
            "browser_blocked_mutations": [
                "non-shell worker execution",
                "local/provider model execution",
                "patch application",
                "cleanup apply",
                "sync",
                "push",
                "project publication",
                "autonomous routing",
                "broad mutation",
            ],
        },
        "telegram_routing": {
            "provider": "local",
            "default_model": "gemma4:latest",
            "route_message_command": 'devflow supervisor route-message "<raw Telegram text>" --json',
            "footer_required": True,
            "routes": {
                "simple_chat": {"model": "gemma4:latest", "action": "answer"},
                "devflow_read": {"model": "gemma4:latest", "action": "run_safe_command"},
                "plan": {"model": "qwen3.6:latest", "action": "answer"},
                "deep_review": {"model": "qwopus:latest", "action": "answer"},
                "implementation": {"model": None, "action": "create_task_or_create_codex_goal"},
            },
        },
        "path_authority": {
            "josh_canonical_checkout": JOSH_CANONICAL_CHECKOUT,
            "prohibited_checkout_paths": PROHIBITED_CHECKOUT_PATHS,
            "portable_guidance": "Use the actual repo root in context. In this checkout, docs and examples refer to the local folder as DevFlow; do not hardcode Mac Studio paths into portable Hermes policy.",
        },
    }


def classify_supervisor_command(command: str) -> dict[str, Any]:
    safety_class = _classify_supervisor_command(command)
    why_not_auto_runnable = None if safety_class == PURE_READ_ONLY else SAFETY_CLASS_REASONS[safety_class]
    return {
        "command": command,
        "safety_class": safety_class,
        "requires_human_approval": safety_class != PURE_READ_ONLY,
        "supervisor_may_auto_run": safety_class == PURE_READ_ONLY,
        "why_not_auto_runnable": why_not_auto_runnable,
    }


def _classify_supervisor_command(command: str) -> str:
    tokens = _command_tokens(command)
    if not tokens:
        return FORBIDDEN_FOR_SUPERVISOR
    if tokens[0] == "run":
        tokens = tokens[1:]
    if not tokens:
        return FORBIDDEN_FOR_SUPERVISOR
    if "--help" in tokens or "-h" in tokens:
        return PURE_READ_ONLY
    if len(tokens) >= 4 and tokens[1:3] == ["-m", "devflow.cli"]:
        tokens = ["devflow", *tokens[3:]]
    if tokens[0] != "devflow":
        return FORBIDDEN_FOR_SUPERVISOR
    if len(tokens) == 1:
        return PURE_READ_ONLY

    command_group = tokens[1]
    subcommand = tokens[2] if len(tokens) > 2 else ""

    if command_group in {"doctor", "reconcile", "dashboard", "status", "next"}:
        return PURE_READ_ONLY
    if command_group in {"sync-main", "push-main"}:
        return APPROVAL_REQUIRED_GIT
    if command_group == "init":
        return APPROVAL_REQUIRED_TASK_STATE
    if command_group == "supervise":
        return APPROVAL_REQUIRED_WORKER_RUNTIME
    if command_group == "supervisor":
        return PURE_READ_ONLY if subcommand in {"policy", "packet", "route-message"} else FORBIDDEN_FOR_SUPERVISOR
    if command_group == "hermes":
        return PURE_READ_ONLY if subcommand == "imessage-check" else FORBIDDEN_FOR_SUPERVISOR
    if command_group == "scheduler":
        if subcommand == "status":
            return PURE_READ_ONLY
        if subcommand == "retry":
            return APPROVAL_REQUIRED_EVIDENCE_WRITING
        return FORBIDDEN_FOR_SUPERVISOR
    if command_group == "question":
        if subcommand in {"list", "show"}:
            return PURE_READ_ONLY
        if subcommand in {"answer", "resolve"}:
            return APPROVAL_REQUIRED_EVIDENCE_WRITING
        return FORBIDDEN_FOR_SUPERVISOR
    if command_group == "git":
        return PURE_READ_ONLY if subcommand == "status" else FORBIDDEN_FOR_SUPERVISOR
    if command_group == "goal":
        if subcommand in {"list", "show", "status", "next", "slices"}:
            return PURE_READ_ONLY
        if subcommand in {"init", "create-task", "activate", "pause", "block", "complete", "archive"}:
            return APPROVAL_REQUIRED_TASK_STATE
        return FORBIDDEN_FOR_SUPERVISOR
    if command_group == "project":
        if subcommand in {"list", "show", "status", "doctor"}:
            return PURE_READ_ONLY
        if subcommand in {"create", "import", "archive", "remove"}:
            return APPROVAL_REQUIRED_TASK_STATE
        if subcommand == "connect-github":
            return APPROVAL_REQUIRED_GIT
        return FORBIDDEN_FOR_SUPERVISOR
    if command_group == "agent":
        if subcommand in {"list", "show", "policy", "packet", "catalog"}:
            return PURE_READ_ONLY
        if subcommand == "run":
            return PURE_READ_ONLY if "--dry-run" in tokens else APPROVAL_REQUIRED_WORKER_RUNTIME
        if subcommand == "advise":
            return PURE_READ_ONLY if "--dry-run" in tokens else APPROVAL_REQUIRED_WORKER_RUNTIME
        if subcommand in {"add-provider", "add-model"}:
            return PURE_READ_ONLY if "--dry-run" in tokens else APPROVAL_REQUIRED_TASK_STATE
        if subcommand == "propose-patch":
            return APPROVAL_REQUIRED_WORKER_RUNTIME
        return FORBIDDEN_FOR_SUPERVISOR
    if command_group == "worker":
        return APPROVAL_REQUIRED_EVIDENCE_WRITING if subcommand == "validate-outcome" else FORBIDDEN_FOR_SUPERVISOR
    if command_group == "knowledge":
        if subcommand in {"list", "show", "search"}:
            return PURE_READ_ONLY
        if subcommand == "capture":
            return APPROVAL_REQUIRED_EVIDENCE_WRITING
        if subcommand in {"promote", "reject"}:
            return APPROVAL_REQUIRED_TASK_STATE
        return FORBIDDEN_FOR_SUPERVISOR
    if command_group == "idea":
        if subcommand in {"list", "show"}:
            return PURE_READ_ONLY
        if subcommand in {"create-goal", "create-task", "scaffold-goal"} and "--dry-run" in tokens:
            return PURE_READ_ONLY
        if subcommand in {"capture", "classify", "promote", "scaffold-goal", "park", "archive"}:
            return APPROVAL_REQUIRED_EVIDENCE_WRITING
        if subcommand in {"create-goal", "create-task"}:
            return APPROVAL_REQUIRED_TASK_STATE
        return FORBIDDEN_FOR_SUPERVISOR
    if command_group == "dogfood":
        if subcommand in {"list", "show"}:
            return PURE_READ_ONLY
        if subcommand == "run":
            return APPROVAL_REQUIRED_WORKER_RUNTIME
        if subcommand in {"score", "report"}:
            return APPROVAL_REQUIRED_EVIDENCE_WRITING
        return FORBIDDEN_FOR_SUPERVISOR
    if command_group == "worktree":
        if subcommand == "list":
            return PURE_READ_ONLY
        if subcommand == "prune":
            return APPROVAL_REQUIRED_GIT if "--apply" in tokens else PURE_READ_ONLY
        return FORBIDDEN_FOR_SUPERVISOR
    if command_group == "branch":
        if subcommand == "list":
            return PURE_READ_ONLY
        if subcommand == "archive":
            return APPROVAL_REQUIRED_GIT
        return FORBIDDEN_FOR_SUPERVISOR
    if command_group != "task":
        return FORBIDDEN_FOR_SUPERVISOR

    if subcommand in {"list", "show", "review", "next-action", "log", "history", "evidence", "open"}:
        return PURE_READ_ONLY
    if subcommand == "capsule":
        return APPROVAL_REQUIRED_EVIDENCE_WRITING if "--export-md" in tokens else PURE_READ_ONLY
    if subcommand == "packet":
        return APPROVAL_REQUIRED_EVIDENCE_WRITING if "--save" in tokens else PURE_READ_ONLY
    if subcommand == "cleanup":
        return PURE_READ_ONLY if "--dry-run" in tokens and "--apply" not in tokens else APPROVAL_REQUIRED_TASK_STATE
    if subcommand == "prune-closed":
        return APPROVAL_REQUIRED_TASK_STATE
    if subcommand == "promote-preview":
        return PURE_READ_ONLY
    if subcommand in {"review-patch", "patch-dry-run", "normalize-proposal", "orchestrate", "escalation-packet"}:
        return APPROVAL_REQUIRED_EVIDENCE_WRITING
    if subcommand in {"create", "close", "finalize", "apply-patch"}:
        if subcommand == "finalize" and "--commit" in tokens:
            return APPROVAL_REQUIRED_GIT
        return APPROVAL_REQUIRED_TASK_STATE
    if subcommand in {"run", "local", "local-review", "verify"}:
        return APPROVAL_REQUIRED_WORKER_RUNTIME
    if subcommand == "promote":
        return APPROVAL_REQUIRED_GIT
    return FORBIDDEN_FOR_SUPERVISOR


def _command_tokens(command: str) -> list[str]:
    try:
        return shlex.split(command)
    except ValueError:
        return []


def render_supervisor_policy(*, json_output: bool) -> str:
    policy = build_supervisor_policy()
    if json_output:
        return _json(policy)
    return _render_policy(policy)


def build_task_next_action(root: Path, task_id: str, *, project_id: str | None = None) -> dict[str, Any]:
    task = get_task(root, task_id)
    projection = build_task_status_projection(root, task_id, task=task)
    evidence = _task_evidence(root, task)
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
        f"next_safe_action: {action['next_safe_action']}",
        f"recommended_action: {action['recommended_action']}",
        f"recommended_command: {action['recommended_command'] or 'none'}",
        f"safety_class: {action['safety_class']}",
        f"reason: {action['reason']}",
        f"requires_human_approval: {'yes' if action['requires_human_approval'] else 'no'}",
    ]
    if project_id:
        lines.insert(1, f"project_root: {root}")
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
    evidence = _task_evidence(root, task)
    next_action = build_task_next_action(root, task_id, project_id=project_id)
    policy = build_supervisor_policy()
    closure = read_closure(root, task.id)
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


def render_supervisor_command_classification(command: str, *, json_output: bool) -> str:
    """Return the full classification result as a JSON string.

    The supervisor classifier is the only authoritative guardrail for
    deciding whether Hermes may auto-run a command.
    """
    result = classify_supervisor_command(command)
    if json_output:
        return _json(result)
    return (
        f"command: {command}\n"
        f"safety_class: {result['safety_class']}\n"
        f"requires_human_approval: {'yes' if result['requires_human_approval'] else 'no'}\n"
        f"supervisor_may_auto_run: {'yes' if result['supervisor_may_auto_run'] else 'no'}\n"
        f"why_not_auto_runnable: {result['why_not_auto_runnable'] or 'none'}\n"
    )


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
    evidence = _task_evidence(root, task)
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


def _scope_task_action_commands(action: dict[str, Any], project_id: str) -> dict[str, Any]:
    scoped = dict(action)
    replacements: dict[str, str] = {}

    recommended = scoped.get("recommended_command")
    if isinstance(recommended, str):
        scoped_recommended = _scope_task_command(recommended, project_id)
        replacements[recommended] = scoped_recommended
        scoped["recommended_command"] = scoped_recommended
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


def _task_evidence(root: Path, task: TaskRecord) -> dict[str, Any]:
    path = task_dir(root, task.id)
    evidence_paths: list[str] = []
    missing_evidence: list[str] = []
    unknowns: list[str] = []
    for required in ("task.yaml", "events.jsonl"):
        _record_path(root, path / required, evidence_paths, missing_evidence, unknowns)

    verification = _read_json(path / "verification.json")
    verification_path = _record_path(root, path / "verification.json", evidence_paths, missing_evidence, unknowns)
    patch_review = latest_patch_review(root, task.id)
    patch_dry_run = latest_patch_dry_run(root, task.id)
    patch_application = _read_json(path / "patch-application.json")
    patch_application_path = _optional_path(root, path / "patch-application.json", evidence_paths)
    proposal_paths = _proposal_patch_paths(root, task)
    evidence_paths.extend(proposal_paths)
    review_path = _latest_evidence_path(patch_review, "_review_path", evidence_paths)
    dry_run_path = _latest_evidence_path(patch_dry_run, "_dry_run_path", evidence_paths)
    promotion_preview, promotion_preview_path = _promotion_preview(root, task)
    if promotion_preview_path:
        evidence_paths.append(promotion_preview_path)
    git_facts_path = _git_facts_path(root, task)
    if git_facts_path:
        evidence_paths.append(git_facts_path)

    changed_files = _changed_files(patch_review, patch_dry_run, promotion_preview)
    promotion_status = "available" if promotion_preview else "unknown"
    verification_status = _artifact_status(verification, "status")
    stale_or_conflicted = _stale_or_conflicted(promotion_preview)
    return {
        "evidence_paths": sorted(set(evidence_paths)),
        "missing_evidence": sorted(set(missing_evidence)),
        "unknowns": sorted(set(unknowns)),
        "has_proposal_patch": bool(proposal_paths),
        "proposal_patch_paths": proposal_paths,
        "patch_review": patch_review,
        "patch_review_path": review_path,
        "patch_dry_run": patch_dry_run,
        "patch_dry_run_path": dry_run_path,
        "patch_application": patch_application,
        "patch_application_path": patch_application_path,
        "verification": verification,
        "verification_status": verification_status,
        "verification_path": verification_path,
        "promotion_preview": promotion_preview,
        "promotion_preview_path": promotion_preview_path,
        "promotion_preview_status": promotion_status,
        "promotion_readiness": _promotion_readiness_value(promotion_preview),
        "stale_or_conflicted": stale_or_conflicted,
        "changed_files": changed_files,
        "git_facts_path": git_facts_path,
    }


def _proposal_patch_paths(root: Path, task: TaskRecord) -> list[str]:
    paths: list[Path] = []
    qwopus = read_qwopus_evidence(root, task.id)
    if qwopus and qwopus.has_proposal_patch:
        paths.append(qwopus.proposal_patch_path)
    agents_dir = task_dir(root, task.id) / "agents"
    if agents_dir.exists():
        paths.extend(path for path in agents_dir.glob("*/proposal.patch") if path.exists() and path.stat().st_size > 0)
    runs_dir = task_dir(root, task.id) / "local-model-runs"
    if runs_dir.exists():
        paths.extend(path for path in runs_dir.glob("*/proposal.patch") if path.exists() and path.stat().st_size > 0)
    return sorted({relative_path(root, path) for path in paths})


def _patch_review_command(task_id: str, evidence: dict[str, Any]) -> str:
    for path in evidence["proposal_patch_paths"]:
        parts = Path(path).parts
        if "agents" in parts:
            index = parts.index("agents")
            if len(parts) > index + 1:
                return f"devflow task review-patch {task_id} --agent {parts[index + 1]}"
    return f"devflow task review-patch {task_id}"


def _promotion_preview(root: Path, task: TaskRecord) -> tuple[dict[str, Any] | None, str | None]:
    candidates: list[Path] = []
    if is_git_worktree_task(task):
        candidates.append(task_worker_dir(root, task.id, worker_id_for_task(task)) / "promotion-preview.json")
    candidates.append(task_dir(root, task.id) / "promotion-preview.json")
    for path in candidates:
        payload = _read_json(path)
        if payload:
            return payload, relative_path(root, path)
    return None, None


def _git_facts_path(root: Path, task: TaskRecord) -> str | None:
    if not is_git_worktree_task(task):
        return None
    path = task_worker_dir(root, task.id, worker_id_for_task(task)) / "git.json"
    return relative_path(root, path) if path.exists() else None


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


def _changed_files(
    patch_review: dict[str, Any] | None,
    patch_dry_run: dict[str, Any] | None,
    promotion_preview: dict[str, Any] | None,
) -> list[str]:
    files: list[str] = []
    if promotion_preview:
        for key in ("changed_files", "added", "modified", "deleted", "untracked", "binary"):
            value = promotion_preview.get(key)
            if isinstance(value, list):
                files.extend(str(item) for item in value)
        renamed = promotion_preview.get("renamed")
        if isinstance(renamed, list):
            for item in renamed:
                if isinstance(item, dict):
                    files.append(str(item.get("to") or item.get("path") or item))
                else:
                    files.append(str(item))
    if patch_review and isinstance(patch_review.get("files_touched"), list):
        files.extend(str(item) for item in patch_review["files_touched"])
    if patch_dry_run:
        for key in ("files_checked", "files_would_create", "files_would_modify", "files_would_delete"):
            value = patch_dry_run.get(key)
            if isinstance(value, list):
                files.extend(str(item) for item in value)
    return sorted(set(files))


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


def _record_path(
    root: Path,
    path: Path,
    evidence_paths: list[str],
    missing_evidence: list[str],
    unknowns: list[str],
) -> str | None:
    rel = relative_path(root, path)
    if path.exists():
        evidence_paths.append(rel)
        return rel
    missing_evidence.append(rel)
    unknowns.append(f"missing {rel}")
    return None


def _optional_path(root: Path, path: Path, evidence_paths: list[str]) -> str | None:
    if not path.exists():
        return None
    rel = relative_path(root, path)
    evidence_paths.append(rel)
    return rel


def _latest_evidence_path(payload: dict[str, Any] | None, key: str, evidence_paths: list[str]) -> str | None:
    if not payload:
        return None
    path = payload.get(key)
    if isinstance(path, str) and path:
        evidence_paths.append(path)
        return path
    return None


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


def _render_policy(policy: dict[str, Any]) -> str:
    lines = [
        f"policy_id: {policy['policy_id']}",
        f"schema_version: {policy['schema_version']}",
        "",
        "Pure read-only commands",
    ]
    lines.extend(f"- {command}" for command in policy["pure_read_only"])
    for label, field in (
        ("Approval required: evidence writing", "approval_required_evidence_writing"),
        ("Approval required: task state", "approval_required_task_state"),
        ("Approval required: worker/runtime", "approval_required_worker_runtime"),
        ("Approval required: git/promotion", "approval_required_git"),
    ):
        lines.append("")
        lines.append(label)
        lines.extend(f"- {command}" for command in policy[field])
    lines.append("")
    lines.append("Forbidden for supervisor")
    lines.extend(f"- {action}" for action in policy["forbidden_for_supervisor"])
    return "\n".join(lines) + "\n"


def _json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, indent=2) + "\n"
