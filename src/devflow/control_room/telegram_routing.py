from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from devflow.control_room.git_state import inspect_git_state
from devflow.control_room.persistence import get_task


TELEGRAM_ROUTING_SCHEMA_VERSION = 1
DEFAULT_TELEGRAM_MODEL = "gemma4:latest"
PLANNING_MODEL = "qwen3.6:latest"
DEEP_REVIEW_MODEL = "qwopus:latest"

SIMPLE_CHAT = "simple_chat"
DEVFLOW_READ = "devflow_read"
PLAN = "plan"
DEEP_REVIEW = "deep_review"
IMPLEMENTATION = "implementation"

ANSWER = "answer"
RUN_SAFE_COMMAND = "run_safe_command"
CREATE_TASK = "create_task"
CREATE_CODEX_GOAL = "create_codex_goal"

PURE_READ_ONLY = "pure_read_only"

IMPLEMENTATION_STATUSES_WITHOUT_FRESH_VERIFICATION = {
    "created",
    "running",
    "complete",
    "worker_failed",
    "verification_failed",
    "timeout",
    "blocked",
}


def route_telegram_message(root: Path, raw_message: str) -> dict[str, Any]:
    """Classify a Telegram/Hermes message without running commands or mutating state."""

    message = raw_message.strip()
    lower = message.lower()
    tokens = set(re.findall(r"[a-z0-9][a-z0-9_-]*", lower))
    repo_state = _repo_state(root)
    task_state = _mentioned_task_state(root, message)
    command = _extract_devflow_command(message)

    if command:
        decision = _route_explicit_command(
            command,
            repo_state=repo_state,
            task_state=task_state,
        )
        return _apply_repo_aware_overrides(decision)

    if _looks_like_devflow_read(lower, tokens):
        recommended_command = _recommended_read_command(message, lower, tokens)
        command_classification = _classify_supervisor_command(recommended_command)
        decision = _decision(
            route=DEVFLOW_READ,
            model=DEFAULT_TELEGRAM_MODEL,
            action=RUN_SAFE_COMMAND,
            reason="DevFlow read-only status/list/next-action request; use the fast local default model.",
            requested_action="devflow_read",
            risk_level="low",
            repo_state=repo_state,
            task_state=task_state,
            recommended_command=recommended_command,
            command_classification=command_classification,
        )
        return _apply_repo_aware_overrides(decision)

    if _looks_like_deep_review(lower, tokens):
        decision = _decision(
            route=DEEP_REVIEW,
            model=DEEP_REVIEW_MODEL,
            action=ANSWER,
            reason="Deep architecture or hard reasoning request; route to Qwopus.",
            requested_action="deep_review",
            risk_level="high",
            repo_state=repo_state,
            task_state=task_state,
        )
        return _apply_repo_aware_overrides(decision)

    if _looks_like_plan(lower, tokens):
        decision = _decision(
            route=PLAN,
            model=PLANNING_MODEL,
            action=ANSWER,
            reason="Planning, review, design, or risk-analysis request; route to Qwen.",
            requested_action="plan",
            risk_level="medium",
            repo_state=repo_state,
            task_state=task_state,
        )
        return _apply_repo_aware_overrides(decision)

    if _looks_like_implementation(lower, tokens):
        action = CREATE_CODEX_GOAL if "codex" in tokens or "goal" in tokens else CREATE_TASK
        decision = _decision(
            route=IMPLEMENTATION,
            model=None,
            action=action,
            reason="Implementation request; DevFlow should create a task or Codex goal instead of routing to chat.",
            requested_action=action,
            risk_level="high",
            repo_state=repo_state,
            task_state=task_state,
        )
        return _apply_repo_aware_overrides(decision)

    decision = _decision(
        route=SIMPLE_CHAT,
        model=DEFAULT_TELEGRAM_MODEL,
        action=ANSWER,
        reason="Default Telegram/simple chat request; use Gemma for the fastest local response.",
        requested_action="chat",
        risk_level="low",
        repo_state=repo_state,
        task_state=task_state,
    )
    return _apply_repo_aware_overrides(decision)


def render_telegram_route(root: Path, raw_message: str, *, json_output: bool) -> str:
    decision = route_telegram_message(root, raw_message)
    if json_output:
        return json.dumps(decision, sort_keys=True, indent=2) + "\n"
    lines = [
        f"route: {decision['route']}",
        f"model: {_model_for_footer(decision['model'])}",
        f"action: {decision['action']}",
        f"reason: {decision['reason']}",
    ]
    if decision.get("recommended_command"):
        lines.append(f"recommended_command: {decision['recommended_command']}")
    if decision.get("overrides"):
        lines.append("overrides:")
        lines.extend(f"  - {override}" for override in decision["overrides"])
    lines.extend(["", decision["routing_footer"]])
    return "\n".join(lines) + "\n"


def _route_explicit_command(
    command: str,
    *,
    repo_state: dict[str, Any],
    task_state: dict[str, Any] | None,
) -> dict[str, Any]:
    command_classification = _classify_supervisor_command(command)
    if command_classification["safety_class"] == PURE_READ_ONLY:
        return _decision(
            route=DEVFLOW_READ,
            model=DEFAULT_TELEGRAM_MODEL,
            action=RUN_SAFE_COMMAND,
            reason="Recognized supervisor-safe read-only DevFlow command.",
            requested_action="run_safe_command",
            risk_level="low",
            repo_state=repo_state,
            task_state=task_state,
            recommended_command=command,
            command_classification=command_classification,
        )

    return _decision(
        route=IMPLEMENTATION,
        model=None,
        action=ANSWER,
        reason="Recognized DevFlow command requires human approval; do not auto-run it from Telegram.",
        requested_action="approval_required_command",
        risk_level="high",
        repo_state=repo_state,
        task_state=task_state,
        recommended_command=command,
        command_classification=command_classification,
    )


def _apply_repo_aware_overrides(decision: dict[str, Any]) -> dict[str, Any]:
    if decision["route"] != IMPLEMENTATION:
        return _with_footer(decision)

    repo_state = decision["repo_state"]
    if repo_state.get("git_repo") and repo_state.get("dirty_state") == "dirty":
        return _with_footer(
            {
                **decision,
                "route": DEVFLOW_READ,
                "model": DEFAULT_TELEGRAM_MODEL,
                "action": ANSWER,
                "reason": "Dirty git tree blocks implementation routing; inspect status before creating or running work.",
                "requested_action": "inspect_dirty_repo",
                "risk_level": "medium",
                "overrides": sorted(set(decision["overrides"] + ["dirty_git_tree_no_implementation"])),
            }
        )

    task_state = decision.get("task_state")
    if task_state and task_state.get("status") in IMPLEMENTATION_STATUSES_WITHOUT_FRESH_VERIFICATION:
        return _with_footer(
            {
                **decision,
                "route": DEVFLOW_READ,
                "model": DEFAULT_TELEGRAM_MODEL,
                "action": ANSWER,
                "reason": "Mentioned task is not verified; route to review/status before implementation.",
                "requested_action": "inspect_unverified_task",
                "risk_level": "medium",
                "overrides": sorted(set(decision["overrides"] + ["unverified_task_no_implementation"])),
            }
        )

    return _with_footer(decision)


def _decision(
    *,
    route: str,
    model: str | None,
    action: str,
    reason: str,
    requested_action: str,
    risk_level: str,
    repo_state: dict[str, Any],
    task_state: dict[str, Any] | None,
    recommended_command: str | None = None,
    command_classification: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return _with_footer(
        {
            "schema_version": TELEGRAM_ROUTING_SCHEMA_VERSION,
            "route": route,
            "model": model,
            "action": action,
            "reason": reason,
            "requested_action": requested_action,
            "risk_level": risk_level,
            "repo_state": repo_state,
            "task_state": task_state,
            "recommended_command": recommended_command,
            "command_classification": command_classification,
            "overrides": [],
        }
    )


def _with_footer(decision: dict[str, Any]) -> dict[str, Any]:
    decision["routing_footer"] = (
        f"route: {decision['route']}\n"
        f"model: {_model_for_footer(decision['model'])}\n"
        f"action: {decision['action']}"
    )
    decision["operator_plan"] = _operator_plan(decision)
    return decision


def _model_for_footer(model: str | None) -> str:
    return model or "none"


def _operator_plan(decision: dict[str, Any]) -> dict[str, Any]:
    classification = decision.get("command_classification") or {}
    recommended_command = decision.get("recommended_command")
    may_auto_run_command = bool(classification.get("supervisor_may_auto_run"))
    approval_required = bool(classification.get("requires_human_approval"))

    if decision["action"] == RUN_SAFE_COMMAND and may_auto_run_command:
        next_step = "run_recommended_command"
    elif decision["action"] in {CREATE_TASK, CREATE_CODEX_GOAL}:
        next_step = "request_human_approval"
        approval_required = True
    elif recommended_command and not may_auto_run_command:
        next_step = "request_human_approval"
        approval_required = True
    elif decision["model"]:
        next_step = "answer_with_model"
    else:
        next_step = "request_human_approval"
        approval_required = True

    return {
        "next_step": next_step,
        "telegram_reply_style": "short_summary_with_footer",
        "include_routing_footer": True,
        "routing_footer": decision["routing_footer"],
        "model": decision["model"],
        "recommended_command": recommended_command,
        "may_auto_run_command": may_auto_run_command,
        "approval_required": approval_required,
        "approval_prompt_hint": _approval_prompt_hint(decision),
        "max_summary_lines": 8,
    }


def _approval_prompt_hint(decision: dict[str, Any]) -> str | None:
    command = decision.get("recommended_command")
    if command:
        return (
            "I approve this exact Dev-Flow command after reviewing the cited readiness evidence:\n"
            f"{command}"
        )
    if decision["action"] == CREATE_CODEX_GOAL:
        return "Ask for explicit approval before creating a Codex goal from this Telegram request."
    if decision["action"] == CREATE_TASK:
        return "Ask for explicit approval before creating a DevFlow task, then use devflow task create."
    return None


def _classify_supervisor_command(command: str) -> dict[str, Any]:
    from devflow.control_room.supervisor_surface import classify_supervisor_command

    return classify_supervisor_command(command)


def _repo_state(root: Path) -> dict[str, Any]:
    try:
        state = inspect_git_state(root)
    except Exception as exc:
        return {
            "git_repo": False,
            "dirty_state": "unknown",
            "safe_for_worker_writes": False,
            "error": str(exc),
        }
    return {
        "git_repo": state.is_repo,
        "repo_root": state.repo_root,
        "branch": state.branch,
        "dirty_state": "dirty" if state.dirty else "clean",
        "safe_for_worker_writes": state.safe_for_worker_writes,
        "safe_for_promotion": state.safe_for_promotion,
        "safe_for_push": state.safe_for_push,
        "operation_in_progress": state.operation_in_progress,
        "conflicted_files": list(state.conflicted_files),
    }


def _mentioned_task_state(root: Path, message: str) -> dict[str, Any] | None:
    match = re.search(r"\btask-\d+\b", message)
    if not match:
        return None
    task_id = match.group(0)
    try:
        task = get_task(root, task_id)
    except Exception:
        return {"task_id": task_id, "status": "unknown", "verification_status": "unknown"}
    return {
        "task_id": task.id,
        "title": task.title,
        "status": task.status,
        "verification_status": task.verification_status,
        "worker": task.worker,
    }


def _extract_devflow_command(message: str) -> str | None:
    match = re.search(r"\bdevflow\b[^\n`]*", message)
    if not match:
        return None
    command = match.group(0).strip().strip("`'\" ")
    while command and command[-1] in ".,;":
        command = command[:-1].rstrip()
    return command or None


def _looks_like_devflow_read(lower: str, tokens: set[str]) -> bool:
    if _looks_like_implementation(lower, tokens) and not (
        "status" in tokens
        or "list" in tokens
        or "show" in tokens
        or "log" in tokens
        or "next action" in lower
        or "next safe action" in lower
        or "review queue" in lower
    ):
        return False
    if "devflow" in tokens:
        return True
    if "next action" in lower or "next safe action" in lower or "review queue" in lower:
        return True
    return bool(
        tokens
        & {
            "status",
            "list",
            "dashboard",
            "blocked",
            "queue",
            "tasks",
            "task",
            "show",
            "log",
        }
    )


def _looks_like_deep_review(lower: str, tokens: set[str]) -> bool:
    if "big decision" in lower or "system design" in lower:
        return True
    return bool(tokens & {"deep", "architecture", "architectural", "hard"})


def _looks_like_plan(_lower: str, tokens: set[str]) -> bool:
    return bool(tokens & {"think", "plan", "review", "design", "risk", "analysis", "analyze"})


def _looks_like_implementation(_lower: str, tokens: set[str]) -> bool:
    return bool(tokens & {"implement", "code", "fix", "refactor", "build", "change", "update"})


def _recommended_read_command(message: str, lower: str, tokens: set[str]) -> str:
    task_match = re.search(r"\btask-\d+\b", message)
    task_id = task_match.group(0) if task_match else None
    if task_id and ("next action" in lower or "next" in tokens):
        return f"devflow task next-action {task_id} --json"
    if task_id and ("review" in tokens or "show" in tokens):
        return f"devflow task review {task_id} --json"
    if task_id:
        return f"devflow task show {task_id}"
    if "dashboard" in tokens:
        return "devflow dashboard --json"
    if "list" in tokens or "tasks" in tokens or "queue" in tokens:
        return "devflow task list"
    return "devflow status --json"
