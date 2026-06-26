"""Telegram to DevFlow pipeline: intent parsing, goal creation, task decomposition, worker dispatch, and status reporting."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from devflow.control_room.goals import next_goal_id, create_goal_from_markdown
from devflow.control_room.intent_scaffold import build_scaffold_pending_action
from devflow.control_room.persistence import get_task
from devflow.control_room.service import create_task
from devflow.control_room.task_lifecycle import record_task_update


# ── Intent Schema (what the LLM returns) ──
@dataclass
class DevFlowIntent:
    goal_title: str
    brief_description: str
    priority: str  # "high" | "medium" | "low"
    estimated_effort: str  # "scaffold" | "small" | "medium" | "large"
    affected_areas: list[str]
    suggested_roles: list[str]
    dependencies: list[str]
    acceptance_criteria: list[str]
    context_needed: list[str]
    is_clear: bool  # can we proceed without more questions?


# ── 1. Intent Parser (uses qwopus-devflow model) ──
def parse_telegram_intent(raw_message: str, repo_path: Path) -> DevFlowIntent:
    """
    Parse a raw Telegram message into a structured DevFlow intent.
    Uses qwopus-devflow model via the existing model_gateway.
    
    Simplified version that doesn't require the full model gateway -
    parses the intent directly from the message for now.
    """
    message = raw_message.strip()
    lower = message.lower()
    
    # Extract key signals
    priority = "medium"
    if any(w in lower for w in ["urgent", "asap", "critical", "blocker"]):
        priority = "high"
    elif not any(w in lower for w in ["feature", "enhancement", "improve", "add", "build", "create", "fix", "implement"]):
        priority = "low"  # informational/brainstorm
    
    effort = "medium"
    if any(w in lower for w in ["tiny", "quick", "scaffold", "boilerplate"]):
        effort = "small"
    elif any(w in lower for w in ["large", "full", "complete", "comprehensive", "enterprise"]):
        effort = "large"
    
    # Extract areas from context clues
    areas = _extract_affected_areas(message)
    suggested_roles = _extract_roles(lower)
    
    return DevFlowIntent(
        goal_title=_normalize_goal_title(message),
        brief_description=message,
        priority=priority,
        estimated_effort=effort,
        affected_areas=areas,
        suggested_roles=suggested_roles,
        dependencies=[],
        acceptance_criteria=[f"Goal '{message[:50]}...' completed successfully"],
        context_needed=[".devflow/project/project.yaml", ".devflow/project/current-state.md"],
        is_clear=True,
    )


def _normalize_goal_title(message: str) -> str:
    """Extract or generate a clean goal title from the message."""
    # If it starts with a title-like pattern, use it
    title_match = re.search(r"^(?:['\"`]?(.+?)['\"`]?)\s*[.:]?\s*$", message, re.IGNORECASE)
    if title_match and len(title_match.group(1)) < 80:
        return title_match.group(1).strip()
    
    # Otherwise extract the first meaningful clause
    if "I want" in message.lower():
        rest = message.lower().replace("i want", "").replace("i'd like", "").strip()
        return rest.replace("to", "").strip().capitalize()[:60] or message[:60]
    
    return message[:60]


def _extract_affected_areas(message: str) -> list[str]:
    """Identify what areas of the codebase are affected."""
    areas = []
    area_keywords = {
        "gateway": ["gateway", "telegram", "discord", "slack", "platform"],
        "control_room": ["control", "orchestration", "supervisor", "lifecycle"],
        "task_management": ["task", "slice", "goa", "milestone"],
        "verification": ["verify", "verify", "validation", "test", "test"],
        "worker": ["worker", "implementer", "coder", "shell"],
        "routing": ["rout", "intent", "message", "command"],
        "config": ["config", "yaml", "settings", "env"],
        "cli": ["cli", "command line", "slash"],
        "memory": ["memory", "memorY", "context"],
        "plugin": ["plugin", "skill", "extension"],
        "model_routing": ["model", "route", "provider", "llm"],
    }
    lower = message.lower()
    for area, keywords in area_keywords.items():
        if any(kw in lower for kw in keywords):
            areas.append(area)
    return areas or ["general"]


def _extract_roles(lower: str) -> list[str]:
    """Extract relevant worker roles from the message."""
    roles = []
    role_map = {
        "planner": ["plan", "design", "think", "architecture"],
        "implementer": ["implement", "build", "code", "create", "fix", "refactor"],
        "reviewer": ["review", "audit", "check"],
        "verifier": ["verify", "validate", "test", "dogfood"],
        "scout": ["scout", "research", "explore", "find"],
    }
    for role, keywords in role_map.items():
        if any(kw in lower for kw in keywords):
            roles.append(role)
    return roles or ["planner", "implementer"]


# ── 2. Goal Scaffolding ──
def scaffold_goal_from_intent(intent: DevFlowIntent, repo_path: Path | str) -> tuple[str, Path]:
    """
    Create a new goal (G-XXXX) in the DevFlow filesystem.
    Returns (goal_id, goal_dir_path).
    """
    repo_path = Path(repo_path)
    goal_id = next_goal_id(repo_path)
    
    # Create brief for the goal
    g_dir = repo_path / ".devflow" / "goals" / goal_id
    brief_dir = repo_path / ".devflow" / "goals"
    brief_path = brief_dir / f"{goal_id}-brief.md"
    brief_path.parent.mkdir(parents=True, exist_ok=True)
    
    brief_content = f"""# Intent Brief

**Source:** Telegram message
**Priority:** {intent.priority.upper()}
**Estimated Effort:** {intent.estimated_effort}
**Suggested Roles:** {", ".join(intent.suggested_roles)}

## Title
{intent.goal_title}

## Description
{intent.brief_description}

## Affected Areas
{chr(10).join(f"- {area}" for area in intent.affected_areas)}

## Acceptance Criteria
{chr(10).join(f"- {criterion}" for criterion in intent.acceptance_criteria)}

## Context
Dev-Flow local-first control room parallel coding workers.
"""
    brief_path.write_text(brief_content, encoding="utf-8")
    
    # Scaffold the full goal with all 10 artifacts
    record = create_goal_from_markdown(repo_path, brief_path, goal_id)
    
    # Add priority metadata to the goal
    (g_dir / "intent-metadata.yaml").write_text(
        f"id: {goal_id}\n"
        f"title: {intent.goal_title}\n"
        f"priority: {intent.priority}\n"
        f"effort: {intent.estimated_effort}\n"
        f"affected_areas: {intent.affected_areas}\n"
        f"suggested_roles: {intent.suggested_roles}\n"
        f"source_intent: {intent.brief_description[:100]}\n"
        f"created_by: telegram-bridge\n",
        encoding="utf-8"
    )
    
    return record.id, g_dir


# ── 3. Task Decomposition ──
def decompose_goal_into_tasks(goal_id: str, goal_dir: Path, repo_path: Path) -> list[str]:
    """
    Break a goal into 1-4 parallel task slices.
    Returns list of task_ids (task-XXXX format).
    """
    goal_intent_path = goal_dir / "intent-metadata.yaml"
    priority = "medium"
    effort = "medium"
    roles = ["planner", "implementer"]
    
    if goal_intent_path.exists():
        content = goal_intent_path.read_text(encoding="utf-8")
        for line in content.splitlines():
            if line.startswith("priority:"):
                priority = line.split(":", 1)[1].strip().lower()
            elif line.startswith("effort:"):
                effort = line.split(":", 1)[1].strip().lower()
            elif line.startswith("suggested_roles:"):
                raw_roles = line.split(":", 1)[1].strip()
                roles = [r.strip().strip("[]'\"") for r in raw_roles.split(",") if r.strip()]
    
    # Determine number of task slices
    if effort == "small":
        num_slices = 1
    elif effort == "medium":
        num_slices = 2
    else:
        num_slices = 3
    
    task_ids = []

    # Use DevFlow's task creation API so task.yaml stays compatible with the
    # scalar-only persistence reader and workspaces are actually created.
    for i in range(num_slices):
        role_for_slice = roles[i] if i < len(roles) else roles[-1]
        task = create_task(repo_path, f"{goal_id} • Slice {i + 1}")
        task.verification_command = f"test -f .devflow/goals/{goal_id}/success.json"
        record_task_update(
            repo_path,
            task,
            event_type="telegram_bridge_task_linked",
            event_payload={
                "source": "telegram-bridge",
                "parent_goal": goal_id,
                "slice_index": i + 1,
                "total_slices": num_slices,
                "suggested_role": role_for_slice,
                "serving_context": f".devflow/goals/{goal_id}/goal.md",
                "context_required": [
                    f".devflow/goals/{goal_id}/prd.md",
                    f".devflow/goals/{goal_id}/task-slices.yaml",
                ],
                "verification_requirements": [
                    "code_compiles",
                    "tests_pass",
                    "no_regressions",
                ],
            },
        )
        task_ids.append(task.id)
    
    return task_ids


def _generate_task_ids(repo_path: Path, count: int) -> list[str]:
    """Generate unused task IDs for the next slices."""
    existing_ids = set()
    tasks_dir = repo_path / ".devflow" / "tasks"
    if tasks_dir.exists():
        for d in tasks_dir.iterdir():
            if d.is_dir() and re.match(r"^task-\d+$", d.name):
                try:
                    existing_ids.add(int(d.name.split("-")[1]))
                except ValueError:
                    pass
    
    # Find next available numbers
    next_num = 2
    while next_num in existing_ids:
        next_num += 1
    
    ids = []
    for _ in range(count):
        while next_num in existing_ids:
            next_num += 1
        ids.append(f"task-{next_num:04d}")
        existing_ids.add(next_num)
        next_num += 1
    
    return ids


# ── 4. Worker Dispatch ──
def dispatch_workers(task_ids: list[str], repo_path: Path) -> dict[str, dict[str, Any]]:
    """
    Return task preparation status without launching workers.

    The Telegram bridge currently creates goals, tasks, and workspaces. It does
    not start worker commands; that must go through a separate explicit approval
    path because task execution mutates workspaces and can be long-running.
    """
    report = {}
    
    for task_id in task_ids:
        task = get_task(repo_path, task_id)
        
        report[task_id] = {
            "status": task.status,
            "worker": task.worker,
            "workspace": task.workspace,
            "prepared_at": datetime.now(timezone.utc).isoformat(),
        }
    
    return report


# ── 5. Telegram Status Reporter ──
def format_telegram_response(
    intent: DevFlowIntent,
    goal_id: str,
    task_ids: list[str],
    dispatch_report: dict[str, dict[str, Any]],
    repo_path: Path,
) -> str:
    """Format a Telegram-friendly response about the DevFlow pipeline progress."""
    
    lines = [
        "🚀 **DevFlow Intent Received**",
        "",
        f"Goal: {goal_id}",
        f"Title: {intent.goal_title}",
        f"Priority: {intent.priority.upper()}",
        f"Effort: {intent.estimated_effort.title()}",
        "",
        "🎯 **Acceptedance Criteria**",
    ]
    
    for i, criterion in enumerate(intent.acceptance_criteria, 1):
        lines.append(f"{i}. {criterion}")
    
    lines.extend(["", "📋 **Task Slices**"])
    
    for task_id in task_ids:
        status = dispatch_report.get(task_id, {}).get("status", "pending")
        worker = dispatch_report.get(task_id, {}).get("worker", "qwopus-implementer")
        lines.append(f"  - **{task_id}** — {status} ({worker})")
        workspace = dispatch_report.get(task_id, {}).get("workspace", "")
        if workspace:
            lines.append(f"    Workspace: {workspace}")
    
    lines.extend([
        "",
        "📊 **Goal Artifacts Created**",
    ])
    
    goal_dir = repo_path / ".devflow" / "goals" / goal_id
    if goal_dir.exists():
        for f in sorted(goal_dir.iterdir()):
            if f.is_file():
                lines.append(f"  - {f.name} (✅)")
    
    lines.extend(["", "⏳ **Next Steps**"])
    status_file = repo_path / ".devflow" / "goals" / goal_id / "status.json"
    lines.append(f"• Goal status updated in {goal_id}/status.json")
    lines.append("• Task slices are created with workspaces")
    lines.append("• Workers are not running yet; start them through an approved execution command")
    lines.append("• Monitor via: `devflow status --json`")
    
    return "\n".join(lines)


# ── 6. Main Pipeline ──
def run_telegram_to_devflow_pipeline(message: str, repo_path: Path | str) -> dict[str, Any]:
    """
    Return approval-gated intent scaffold guidance without mutating Dev-Flow state.
    """
    repo_path = Path(repo_path)
    pending_action = build_scaffold_pending_action(message, source="telegram")
    return {
        "raw_message": message,
        "status": "pending_approval",
        "pipeline_step": "intent_scaffold_pending",
        "pending_action": pending_action,
        "goal_id": None,
        "task_ids": [],
        "telegram_response": _format_pending_scaffold_response(pending_action),
    }


def _format_pending_scaffold_response(pending_action: dict[str, Any]) -> str:
    proposal = pending_action["proposal"]
    title = proposal["normalized_intent"]["title"]
    lines = [
        "DevFlow intent scaffold is pending approval.",
        f"Title: {title}",
        f"Status: {proposal['status']}",
        "No goals, tasks, workers, verification, promotion, or git actions ran.",
        "Approval commands:",
    ]
    lines.extend(f"- {command}" for command in pending_action["approval_commands"])
    return "\n".join(lines)
