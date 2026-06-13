from __future__ import annotations

from dataclasses import dataclass
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
    resolved_id = goal_id or next_goal_id(root)
    if goal_dir(root, resolved_id).exists():
        raise IdeaExecutionBridgeError(f"Goal already exists: {resolved_id}")
    resolved_title = (title or metadata["title"]).strip()
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
    preview = preview_goal_from_idea(root, idea_id, title=title, goal_id=goal_id)
    brief_path = ideas_dir(root) / idea_id / "goal-brief.md"
    atomic_write_text(brief_path, _goal_brief(metadata, raw, classification, promotion, preview.title))
    record = create_goal_from_markdown(root, brief_path, goal_id=preview.created_id)
    link_path = root / ".devflow" / "goals" / record.id / "idea-link.yaml"
    atomic_write_text(link_path, yaml.safe_dump(_idea_link(metadata, "goal"), sort_keys=False))
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


def _idea_link(metadata: dict[str, Any], target: str) -> dict[str, Any]:
    idea_id = metadata["id"]
    return {
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


def _goal_brief(metadata: dict[str, Any], raw: str, classification: str, promotion: str, title: str) -> str:
    return _source_brief("Goal", metadata, raw, classification, promotion, title)


def _task_brief(metadata: dict[str, Any], raw: str, classification: str, promotion: str, title: str) -> str:
    return _source_brief("Task", metadata, raw, classification, promotion, title)


def _source_brief(kind: str, metadata: dict[str, Any], raw: str, classification: str, promotion: str, title: str) -> str:
    return "\n".join(
        [
            f"# {kind} From Idea: {title}",
            "",
            f"- idea_id: {metadata['id']}",
            f"- maturity: {metadata['maturity']}",
            f"- promotion_target: {metadata.get('promotion_target')}",
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
