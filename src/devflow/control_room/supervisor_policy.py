from __future__ import annotations

import json
import shlex
from typing import Any

from devflow.control_room.browser_action_policy import (
    get_browser_allowed_mutations,
    get_browser_blocked_mutations,
)
from devflow.control_room.machine_capability import local_model_concurrency_policy
from devflow.control_room.telegram_routing import (
    DEFAULT_TELEGRAM_MODEL,
    DEFAULT_TELEGRAM_PROVIDER_ID,
    DEEP_REVIEW_MODEL,
    PLANNING_MODEL,
)


SUPERVISOR_SCHEMA_VERSION = 1
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
    "devflow agent serial-packet",
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
    "devflow architecture audit --install-graphify --write-doc",
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
    "devflow agent hermes-run",
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
                "serial local-agent packet creation",
                "broad mutation",
            ],
            "browser_allowed_mutations": get_browser_allowed_mutations(),
            "browser_blocked_mutations": get_browser_blocked_mutations(),
            "hermes_runtime_boundary": {
                "browser_allowed_after_approval": "packet creation through devflow agent serial-packet writes bounded evidence only",
                "packet_creation_proof": "serial-packet output must retain model_launch: false, worker_ran: no, git_mutation: false, and did not launch Hermes",
                "browser_blocked_runtime_launch": "non-dry-run devflow agent hermes-run is a worker runtime launch and is not executable from the browser in this milestone",
                "dry_run_preview": "devflow agent hermes-run --dry-run is read-only because it only returns an argv-list command preview",
                "final_proof": "completion-verifier.py, focused tests, and allowlist checks are final proof; Hermes worker self-report is not proof",
                "local_model_concurrency": local_model_concurrency_policy(),
            },
        },
        "telegram_routing": {
            "provider": None,
            "provider_id": DEFAULT_TELEGRAM_PROVIDER_ID,
            "default_model": DEFAULT_TELEGRAM_MODEL,
            "route_message_command": 'devflow supervisor route-message "<raw Telegram text>" --json',
            "footer_required": True,
            "routes": {
                "simple_chat": {"model": DEFAULT_TELEGRAM_MODEL, "action": "answer"},
                "devflow_read": {"model": DEFAULT_TELEGRAM_MODEL, "action": "run_safe_command"},
                "plan": {"model": PLANNING_MODEL, "action": "answer"},
                "deep_review": {"model": DEEP_REVIEW_MODEL, "action": "answer"},
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
        if subcommand == "serial-packet":
            return APPROVAL_REQUIRED_EVIDENCE_WRITING
        if subcommand == "hermes-run":
            return PURE_READ_ONLY if "--dry-run" in tokens else APPROVAL_REQUIRED_WORKER_RUNTIME
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
    if command_group == "architecture":
        if subcommand == "audit":
            if "--install-graphify" in tokens or "--write-doc" in tokens:
                return APPROVAL_REQUIRED_EVIDENCE_WRITING
            return PURE_READ_ONLY
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


def render_supervisor_command_classification(command: str, *, json_output: bool) -> str:
    """Return the full classification result as a JSON string."""
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
