from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

import yaml

from devflow.control_room.goals import create_goal_from_markdown, next_goal_id
from devflow.control_room.idea_foundry import IdeaFoundryError, record_idea_creation, show_idea
from devflow.control_room.paths import goal_dir, ideas_dir, tasks_dir
from devflow.control_room.persistence import atomic_write_text
from devflow.control_room.service import create_task


class IdeaExecutionBridgeError(ValueError):
    pass


@dataclass(frozen=True)
class IdeaBridgePreview:
    idea_id: str
    target: str
    title: str
    would_create: bool
    created_id: str
    created_path: str
    link_path: str
    next_command: str
    git_worktree: bool = False


@dataclass(frozen=True)
class IdeaBridgeResult:
    idea_id: str
    target: str
    title: str
    created_id: str
    created_path: str
    link_path: str
    next_command: str
    git_worktree: bool = False


def preview_goal_from_idea(
    root: Path,
    idea_id: str,
    *,
    title: str | None = None,
    goal_id: str | None = None,
) -> IdeaBridgePreview:
    metadata, _, _, _ = _require_promoted_idea(root, idea_id, "goal")
    scaffold = _read_goal_scaffold(root, idea_id)
    resolved_id = goal_id or next_goal_id(root)
    if goal_dir(root, resolved_id).exists():
        raise IdeaExecutionBridgeError(f"Goal already exists: {resolved_id}")
    resolved_title = (title or (scaffold or {}).get("proposed_goal", {}).get("title") or metadata["title"]).strip()
    return IdeaBridgePreview(
        idea_id=idea_id,
        target="goal",
        title=resolved_title,
        would_create=True,
        created_id=resolved_id,
        created_path=f".devflow/goals/{resolved_id}",
        link_path=f".devflow/goals/{resolved_id}/idea-link.yaml",
        next_command=f"devflow goal show {resolved_id}",
    )


def preview_task_from_idea(
    root: Path,
    idea_id: str,
    *,
    title: str | None = None,
    git_worktree: bool = False,
) -> IdeaBridgePreview:
    metadata, _, _, _ = _require_promoted_idea(root, idea_id, "task")
    resolved_id = _next_task_id_preview(root)
    resolved_title = (title or metadata["title"]).strip()
    return IdeaBridgePreview(
        idea_id=idea_id,
        target="task",
        title=resolved_title,
        would_create=True,
        created_id=resolved_id,
        created_path=f".devflow/tasks/{resolved_id}",
        link_path=f".devflow/tasks/{resolved_id}/idea-link.yaml",
        next_command=f"devflow task show {resolved_id}",
        git_worktree=git_worktree,
    )


def create_goal_from_idea(
    root: Path,
    idea_id: str,
    *,
    title: str | None = None,
    goal_id: str | None = None,
) -> IdeaBridgeResult:
    metadata, raw, classification, promotion = _require_promoted_idea(root, idea_id, "goal")
    scaffold = _read_goal_scaffold(root, idea_id)
    preview = preview_goal_from_idea(root, idea_id, title=title, goal_id=goal_id)
    brief_path = ideas_dir(root) / idea_id / "goal-brief.md"
    atomic_write_text(brief_path, _goal_brief(metadata, raw, classification, promotion, preview.title, scaffold=scaffold))
    record = create_goal_from_markdown(root, brief_path, goal_id=preview.created_id)
    if scaffold:
        _write_scaffold_goal_artifacts(root, record.id, scaffold)
    link_path = root / ".devflow" / "goals" / record.id / "idea-link.yaml"
    atomic_write_text(
        link_path,
        yaml.safe_dump(_idea_link(metadata, "goal", has_scaffold=bool(scaffold)), sort_keys=False),
    )
    command = f"devflow idea create-goal {idea_id}"
    record_idea_creation(
        root,
        idea_id,
        target="goal",
        created_id=record.id,
        created_path=preview.created_path,
        command=command,
    )
    return IdeaBridgeResult(
        idea_id=idea_id,
        target="goal",
        title=preview.title,
        created_id=record.id,
        created_path=preview.created_path,
        link_path=preview.link_path,
        next_command=preview.next_command,
    )


def create_task_from_idea(
    root: Path,
    idea_id: str,
    *,
    title: str | None = None,
    git_worktree: bool = False,
) -> IdeaBridgeResult:
    metadata, raw, classification, promotion = _require_promoted_idea(root, idea_id, "task")
    preview = preview_task_from_idea(root, idea_id, title=title, git_worktree=git_worktree)
    task = create_task(root, preview.title, git_worktree=git_worktree)
    task_path = root / ".devflow" / "tasks" / task.id
    brief = _task_brief(metadata, raw, classification, promotion, preview.title)
    atomic_write_text(ideas_dir(root) / idea_id / "task-brief.md", brief)
    atomic_write_text(task_path / "idea.md", brief)
    atomic_write_text(task_path / "idea-link.yaml", yaml.safe_dump(_idea_link(metadata, "task"), sort_keys=False))
    command = f"devflow idea create-task {idea_id}"
    record_idea_creation(
        root,
        idea_id,
        target="task",
        created_id=task.id,
        created_path=f".devflow/tasks/{task.id}",
        command=command,
    )
    return IdeaBridgeResult(
        idea_id=idea_id,
        target="task",
        title=preview.title,
        created_id=task.id,
        created_path=f".devflow/tasks/{task.id}",
        link_path=f".devflow/tasks/{task.id}/idea-link.yaml",
        next_command=f"devflow task show {task.id}",
        git_worktree=git_worktree,
    )


def _require_promoted_idea(root: Path, idea_id: str, target: str) -> tuple[dict[str, Any], str, str, str]:
    try:
        metadata, raw, classification, promotion = show_idea(root, idea_id)
    except IdeaFoundryError as exc:
        raise IdeaExecutionBridgeError(str(exc)) from exc
    if metadata["status"] == "archived":
        raise IdeaExecutionBridgeError("Archived idea cannot create a goal or task.")
    if metadata["status"] != "promoted":
        raise IdeaExecutionBridgeError(f"Idea must be promoted to {target} before creation.")
    if metadata.get("promotion_target") != target:
        raise IdeaExecutionBridgeError(f"Idea promotion target is {metadata.get('promotion_target')}, not {target}.")
    required_maturity = "goal_ready" if target == "goal" else "task_ready"
    if metadata.get("maturity") != required_maturity:
        raise IdeaExecutionBridgeError(f"Creation requires maturity {required_maturity}.")
    if target == "goal" and metadata.get("created_goal_id"):
        raise IdeaExecutionBridgeError(f"Idea already created goal {metadata['created_goal_id']}.")
    if target == "task" and metadata.get("created_task_id"):
        raise IdeaExecutionBridgeError(f"Idea already created task {metadata['created_task_id']}.")
    return metadata, raw, classification, promotion


def _idea_link(metadata: dict[str, Any], target: str, *, has_scaffold: bool = False) -> dict[str, Any]:
    idea_id = metadata["id"]
    link = {
        "schema_version": 1,
        "idea_id": idea_id,
        "idea_path": f".devflow/ideas/{idea_id}",
        "promotion_target": target,
        "maturity": metadata["maturity"],
        "source_raw_path": f".devflow/ideas/{idea_id}/raw.md",
        "source_classification_path": f".devflow/ideas/{idea_id}/classification.md",
        "source_promotion_path": f".devflow/ideas/{idea_id}/promotion.md",
        "created_from_idea": True,
    }
    if has_scaffold:
        link["source_scaffold_path"] = f".devflow/ideas/{idea_id}/scaffold-goal.json"
    brainstorm_session_id = str(metadata.get("latest_brainstorm_session_id") or "").strip()
    brainstorm_session_path = str(metadata.get("latest_brainstorm_session_path") or "").strip()
    if brainstorm_session_id:
        link["source_brainstorm_session_id"] = brainstorm_session_id
    if brainstorm_session_path:
        link["source_brainstorm_session_path"] = brainstorm_session_path
    sessions = metadata.get("brainstorm_session_ids")
    if isinstance(sessions, list) and sessions:
        link["brainstorm_session_ids"] = [str(item) for item in sessions if str(item).strip()]
    return link


def _goal_brief(
    metadata: dict[str, Any],
    raw: str,
    classification: str,
    promotion: str,
    title: str,
    *,
    scaffold: dict[str, Any] | None = None,
) -> str:
    brief = _source_brief("Goal", metadata, raw, classification, promotion, title)
    if not scaffold:
        return brief
    goal = scaffold.get("proposed_goal") or {}
    criteria = goal.get("acceptance_criteria") or []
    slices = scaffold.get("task_slices") or []
    lines = [
        brief.rstrip(),
        "",
        "## Scaffold Acceptance Criteria",
        "",
        *(f"- {item}" for item in criteria),
        "",
        "## Scaffold Task Slices",
        "",
        *(f"- {item.get('id')}: {item.get('title')}" for item in slices),
        "",
    ]
    return "\n".join(lines)


def _task_brief(metadata: dict[str, Any], raw: str, classification: str, promotion: str, title: str) -> str:
    return _source_brief("Task", metadata, raw, classification, promotion, title)


def _source_brief(kind: str, metadata: dict[str, Any], raw: str, classification: str, promotion: str, title: str) -> str:
    header = [
        f"# {kind} From Idea: {title}",
        "",
        f"- idea_id: {metadata['id']}",
        f"- maturity: {metadata['maturity']}",
        f"- promotion_target: {metadata.get('promotion_target')}",
    ]
    brainstorm_session_id = str(metadata.get("latest_brainstorm_session_id") or "").strip()
    if brainstorm_session_id:
        header.append(f"- source_brainstorm_session_id: {brainstorm_session_id}")
    header.extend(
        [
            "",
            "## Raw Idea",
            "",
            raw.strip(),
            "",
            "## Classification",
            "",
            classification.strip() or "No classification note supplied.",
            "",
            "## Promotion Decision",
            "",
            promotion.strip() or "No promotion note supplied.",
            "",
        ]
    )
    return "\n".join(header)


def _read_goal_scaffold(root: Path, idea_id: str) -> dict[str, Any] | None:
    path = ideas_dir(root) / idea_id / "scaffold-goal.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise IdeaExecutionBridgeError(f"Scaffold evidence is malformed for {idea_id}: {exc}") from exc
    if not isinstance(data, dict):
        raise IdeaExecutionBridgeError(f"Scaffold evidence must be a JSON object for {idea_id}.")
    if data.get("status") != "ready_for_review":
        raise IdeaExecutionBridgeError(f"Scaffold evidence is not ready for review for {idea_id}.")
    return data


def _write_scaffold_goal_artifacts(root: Path, goal_id: str, scaffold: dict[str, Any]) -> None:
    g_dir = goal_dir(root, goal_id)
    goal = scaffold.get("proposed_goal") or {}
    title = goal.get("title") or scaffold.get("normalized_intent", {}).get("title") or goal_id
    criteria = list(goal.get("acceptance_criteria") or [])
    warnings = list(scaffold.get("warnings") or [])
    questions = list(scaffold.get("questions") or [])
    slices = list(scaffold.get("task_slices") or [])
    context = _scaffold_context(scaffold)

    atomic_write_text(g_dir / "prd.md", _render_scaffold_prd(title, scaffold, criteria, warnings))
    atomic_write_text(
        g_dir / "open-questions.yaml",
        yaml.safe_dump(
            {"questions": questions, "implementation_blocked": bool(questions)},
            sort_keys=False,
        ),
    )
    atomic_write_text(
        g_dir / "context-pointers.yaml",
        yaml.safe_dump(
            {
                "context_budget": {
                    "estimated_tokens": None,
                    "risk": "medium",
                    "strategy": "focused_task_packet",
                },
                "required_context": context,
                "optional_context": [],
                "forbidden_context": [
                    "archived_docs",
                    "previous_failed_attempts_unless_explicitly_relevant",
                    "unrelated_brainstorming",
                ],
                "stale_or_archived_context": [],
                "warnings": warnings,
                "useful_context_summary": scaffold.get("normalized_intent", {}).get("summary") or "",
            },
            sort_keys=False,
        ),
    )
    atomic_write_text(
        g_dir / "task-slices.yaml",
        yaml.safe_dump({"task_slices": [_goal_slice_from_scaffold(item) for item in slices]}, sort_keys=False),
    )
    atomic_write_text(g_dir / "risks.md", _render_scaffold_risks(warnings))
    atomic_write_text(g_dir / "handoff.md", _render_scaffold_handoff(goal_id, title, slices))


def _scaffold_context(scaffold: dict[str, Any]) -> list[str]:
    seen: list[str] = []
    goal = scaffold.get("proposed_goal") or {}
    for value in goal.get("context_pointers") or []:
        if value not in seen:
            seen.append(value)
    for item in scaffold.get("task_slices") or []:
        for value in item.get("context_pointers") or []:
            if value not in seen:
                seen.append(value)
    return seen


def _goal_slice_from_scaffold(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_id": item.get("id"),
        "title": item.get("title"),
        "summary": item.get("description") or item.get("title"),
        "slice_type": "implementation",
        "acceptance_criteria": list(item.get("acceptance_criteria") or []),
        "required_artifacts": ["goal.md", "prd.md", "task-slices.yaml"],
        "blocked_by": list(item.get("dependencies") or []),
        "blocks": [],
        "parallel_safe": not bool(item.get("dependencies")),
        "shared_files": list(item.get("shared_files") or []),
        "workspace_isolation_required": True,
        "promotion_requires": "passing tests",
        "risk": item.get("risk") or "medium",
        "execution_mode": "HITL",
        "context_budget": {
            "estimated_tokens": None,
            "risk": item.get("risk") or "medium",
            "strategy": "focused_task_packet",
        },
        "verification_policy": item.get("verification_policy") or {},
        "human_checkpoint_required": True,
        "checkpoint_reason": "Review scaffold slice before worker execution",
        "promotion_allowed": False,
    }


def _render_scaffold_prd(
    title: str,
    scaffold: dict[str, Any],
    criteria: list[str],
    warnings: list[str],
) -> str:
    summary = scaffold.get("normalized_intent", {}).get("summary") or title
    affected = scaffold.get("affected_areas") or []
    lines = [
        "# Product Requirement Document (PRD)",
        "",
        "## Problem",
        summary,
        "",
        "## Desired Behavior",
        f"{title} is represented as reviewable Dev-Flow goal and task-slice evidence before execution.",
        "",
        "## Non-Goals",
        "- No worker execution from scaffold creation",
        "- No verification execution from scaffold creation",
        "- No promotion, commit, push, pull request, provider call, database, memory, RAG, embeddings, or training",
        "",
        "## Architectural Constraints",
        "- Local-first control room architecture",
        "- Idea Foundry remains the raw intake authority",
        "- Canonical goal/task state requires explicit human approval",
        "",
        "## Affected DevFlow Concepts",
    ]
    lines.extend(f"- {item}" for item in affected)
    lines.extend(["", "## Acceptance Criteria"])
    lines.extend(f"- {item}" for item in criteria)
    lines.extend(["", "## Verification Expectations"])
    for item in scaffold.get("task_slices") or []:
        policy = item.get("verification_policy") or {}
        for command in policy.get("commands") or []:
            lines.append(f"- {command}")
    lines.extend(["", "## Risks"])
    lines.extend(f"- {item}" for item in warnings)
    return "\n".join(lines) + "\n"


def _render_scaffold_risks(warnings: list[str]) -> str:
    lines = [
        "# Goal Risks",
        "",
        "## Scaffold Review Risks",
    ]
    lines.extend(f"- {item}" for item in warnings)
    lines.extend(
        [
            "",
            "## Promotion Risks",
            "- Humans retain manual check/merge promotion.",
        ]
    )
    return "\n".join(lines) + "\n"


def _render_scaffold_handoff(goal_id: str, title: str, slices: list[dict[str, Any]]) -> str:
    first_slice = (slices[0] or {}).get("id") if slices else "TS-0001"
    return "\n".join(
        [
            f"# Handoff: Goal {goal_id}",
            "",
            "## Current Goal",
            f"- {title}",
            "",
            "## Purpose Of Next Session",
            "- Review the scaffolded task slices and create the first approved task.",
            "",
            "## Relevant Files",
            f"- `.devflow/goals/{goal_id}/goal.md`",
            f"- `.devflow/goals/{goal_id}/task-slices.yaml`",
            "",
            "## Suggested Next Action",
            f"- `devflow goal create-task {goal_id} {first_slice}`",
            "",
        ]
    )


def _next_task_id_preview(root: Path) -> str:
    existing: list[int] = []
    base = tasks_dir(root)
    if base.exists():
        for path in base.iterdir():
            if path.is_dir() and path.name.startswith("task-"):
                try:
                    existing.append(int(path.name.removeprefix("task-")))
                except ValueError:
                    continue
    return f"task-{(max(existing) if existing else 0) + 1:04d}"
