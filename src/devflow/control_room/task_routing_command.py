from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from devflow.control_room.project_registry import project_task_ref
from devflow.control_room.router import route_task, save_routing_decision


class TaskRoutingCommandError(ValueError):
    """User-facing task routing command error."""


@dataclass(frozen=True)
class _TaskRoutingCommandResult:
    root: Path
    task_id: str
    task_ref: str
    project_id: str | None
    artifact_path: str
    routing_decision: dict[str, Any]


def build_task_routing_result(
    root: Path,
    task_id: str,
    project_id: str | None = None,
) -> _TaskRoutingCommandResult:
    try:
        decision_data = route_task(root, task_id, project_id=project_id)
        save_routing_decision(root, task_id, decision_data)
        routing_decision = decision_data["routing_decision"]
    except Exception as exc:
        raise TaskRoutingCommandError(str(exc)) from exc

    return _TaskRoutingCommandResult(
        root=root,
        task_id=task_id,
        task_ref=project_task_ref(task_id, project_id),
        project_id=project_id,
        artifact_path=f".devflow/tasks/{task_id}/routing-decision.yaml",
        routing_decision=routing_decision,
    )


def render_task_routing_lines(result: _TaskRoutingCommandResult) -> tuple[str, ...]:
    lines: list[str] = [
        f"Executed routing mapping for task: {result.task_ref}",
        "-" * 50,
    ]

    rd = result.routing_decision
    lines.append(f"Policy Version:              {rd.get('policy_version')}")

    lines.append("")
    lines.append("Selected Agent Assignments:")
    selected = rd.get("selected", {})
    for key in sorted(selected.keys()):
        lines.append(f"  {key:<12}: {selected[key]}")
    if not selected:
        lines.append("  - none")

    lines.append("")
    lines.append("Recorded Reasons:")
    for reason in rd.get("reason", []):
        lines.append(f"  - {reason}")

    lines.append("")
    lines.append("Rejected Agents:")
    rejected = rd.get("rejected", [])
    if not rejected:
        lines.append("  - none")
    else:
        for rej in rejected:
            lines.append(f"  - agent:  {rej.get('agent', 'unknown')}")
            lines.append(f"    reason: {rej.get('reason', 'unspecified')}")

    lines.append("")
    lines.append("Blocked Candidates:")
    blocked = rd.get("blocked", [])
    if not blocked:
        lines.append("  - none")
    else:
        for item in blocked:
            lines.append(f"  - role:   {item.get('role', 'unknown')}")
            lines.append(f"    agent:  {item.get('agent', 'unknown')}")
            lines.append(f"    status: {item.get('status', 'unknown')}")
            lines.append(f"    reason: {item.get('reason', 'unspecified')}")

    lines.append("")
    lines.append("Unresolved Decisions:")
    unresolved = rd.get("unresolved", [])
    if not unresolved:
        lines.append("  - none")
    else:
        for item in unresolved:
            lines.append(f"  - role:   {item.get('role', 'unknown')}")
            lines.append(f"    status: {item.get('status', 'unknown')}")
            lines.append(f"    reason: {item.get('reason', 'unspecified')}")
            if item.get("next_command"):
                lines.append(f"    next:   {item['next_command']}")

    lines.append("")
    lines.append("Recommended Next Commands:")
    recommended_next_commands = rd.get("recommended_next_commands", {})
    if not recommended_next_commands:
        lines.append("  - none")
    else:
        for role in sorted(recommended_next_commands.keys()):
            lines.append(f"  {role:<12}: {recommended_next_commands[role]}")

    lines.append("-" * 50)
    lines.append(f"Wrote routing-decision.yaml under .devflow/tasks/{result.task_id}/")
    return tuple(lines)


def render_task_routing_json(result: _TaskRoutingCommandResult) -> str:
    payload = {
        "artifact_path": result.artifact_path,
        "routing_decision": result.routing_decision,
        "task_id": result.task_id,
    }
    return json.dumps(payload, indent=2, sort_keys=True)
