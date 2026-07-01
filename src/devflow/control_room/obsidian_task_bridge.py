from __future__ import annotations

import shlex
from pathlib import Path
from typing import Any

from devflow.control_room.service import create_task
from devflow.control_room.task_lifecycle import append_task_event


SCOUT_PACK_TASK_TITLES = (
    "Architecture Scout",
    "UX Scout",
    "Data Truth Scout",
    "Verification Scout",
    "Dead Code Scout",
)


def build_obsidian_task_preview(payload: dict[str, Any]) -> dict[str, Any]:
    card = _normalize_card_payload(payload)
    definition_of_done = _definition_of_done(card)
    return {
        "ok": True,
        "source": "obsidian",
        "title": card["title"],
        "definition_of_done": definition_of_done,
        "source_path": card["source_path"],
        "source_card_id": card["source_card_id"],
        "project": card["project"],
        "source_link": card["link"],
        "command": _task_create_command(card["title"], definition_of_done),
    }


def build_obsidian_scout_pack_preview(payload: dict[str, Any]) -> dict[str, Any]:
    card = _normalize_card_payload(payload)
    base_definition = _definition_of_done(card)
    tasks = [
        {
            "title": title,
            "definition_of_done": f"{title}: {base_definition}",
            "command": _task_create_command(title, f"{title}: {base_definition}"),
        }
        for title in SCOUT_PACK_TASK_TITLES
    ]

    return {
        "ok": True,
        "source": "obsidian",
        "source_path": card["source_path"],
        "source_card_id": card["source_card_id"],
        "project": card["project"],
        "source_link": card["link"],
        "task_count": len(tasks),
        "tasks": tasks,
    }


def create_task_from_obsidian_card(root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    preview = build_obsidian_task_preview(payload)
    task = create_task(root, preview["title"], definition_of_done=preview["definition_of_done"])
    append_task_event(
        root,
        task.id,
        "obsidian_card_linked",
        {
            "source": "obsidian",
            "source_path": preview["source_path"],
            "source_card_id": preview["source_card_id"],
            "project": preview["project"],
            "source_link": preview["source_link"],
            "title": preview["title"],
        },
    )
    return {
        **preview,
        "task_id": task.id,
        "event": "obsidian_card_linked",
        "status": task.status,
        "workspace": task.workspace,
        "workspace_kind": task.workspace_kind,
        "last_event": task.last_event,
        "events_path": f".devflow/tasks/{task.id}/events.jsonl",
    }


def create_tasks_from_obsidian_scout_pack(root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    preview = build_obsidian_scout_pack_preview(payload)
    created_tasks: list[dict[str, Any]] = []

    for definition in preview["tasks"]:
        task = create_task(root, definition["title"], definition_of_done=definition["definition_of_done"])
        append_task_event(
            root,
            task.id,
            "obsidian_scout_pack_linked",
            {
                "source": "obsidian",
                "source_path": preview["source_path"],
                "source_card_id": preview["source_card_id"],
                "project": preview["project"],
                "source_link": preview["source_link"],
                "title": definition["title"],
            },
        )
        created_tasks.append(
            {
                **definition,
                "task_id": task.id,
                "event": "obsidian_scout_pack_linked",
                "status": task.status,
                "workspace": task.workspace,
                "workspace_kind": task.workspace_kind,
                "last_event": task.last_event,
                "events_path": f".devflow/tasks/{task.id}/events.jsonl",
            }
        )

    return {**preview, "event": "obsidian_scout_pack_linked", "task_count": len(created_tasks), "tasks": created_tasks}


def _normalize_card_payload(payload: dict[str, Any]) -> dict[str, str | None]:
    raw_card = payload.get("card")
    card = raw_card if isinstance(raw_card, dict) else payload

    title = _clean(card.get("title")) or _clean(card.get("summary"))
    if title is None:
        raise ValueError("card title or summary is required")

    source_path = _clean(card.get("path")) or _clean(card.get("source_path")) or _clean(card.get("sourcePath"))
    source_card_id = _clean(card.get("id")) or _clean(card.get("card_id")) or _clean(card.get("source_card_id"))
    project = _clean(card.get("project"))
    if raw_card is None and project is None:
        project = _clean(card.get("card_project")) or _clean(card.get("source_project"))

    return {
        "title": title,
        "summary": _clean(card.get("summary")),
        "source_path": source_path,
        "source_card_id": source_card_id,
        "project": project,
        "link": _clean(card.get("link")),
        "next_action": _clean(card.get("next_action")) or _clean(card.get("nextAction")),
        "evidence": _clean(card.get("evidence")),
        "why": _clean(card.get("why")),
        "decision": _clean(card.get("decision")),
    }


def _definition_of_done(card: dict[str, str | None]) -> str:
    parts = []
    if card["source_path"]:
        parts.append(f"Review source note: {card['source_path']}.")
    if card["next_action"]:
        parts.append(f"Next action: {card['next_action']}.")
    if card["summary"] and card["summary"] != card["title"]:
        parts.append(f"Summary: {card['summary']}.")
    if card["evidence"]:
        parts.append(f"Evidence: {card['evidence']}.")
    elif card["why"]:
        parts.append(f"Why: {card['why']}.")
    elif card["decision"]:
        parts.append(f"Decision: {card['decision']}.")
    return " ".join(parts) if parts else "Review the Obsidian card and complete the next action."


def _task_create_command(title: str, definition_of_done: str) -> str:
    parts = ["devflow", "task", "create", "--definition-of-done", definition_of_done, title]
    return " ".join(shlex.quote(part) for part in parts)


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
