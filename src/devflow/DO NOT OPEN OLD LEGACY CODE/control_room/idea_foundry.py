from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from devflow.legacy.control_room.models import TASK_SCHEMA_VERSION
from devflow.legacy.control_room.paths import ideas_dir
from devflow.legacy.control_room.persistence import atomic_write_text, utc_now


ALLOWED_IDEA_STATUSES = {"inbox", "classified", "promoted", "parked", "archived"}
ALLOWED_IDEA_MATURITIES = {"spark", "concept", "candidate", "goal_ready", "task_ready"}
ALLOWED_PROMOTION_TARGETS = {"goal", "task"}


class IdeaFoundryError(ValueError):
    pass


def capture_idea(
    root: Path,
    text: str,
    *,
    title: str | None = None,
    source: str = "manual",
    tags: list[str] | None = None,
) -> dict[str, Any]:
    body = text.strip()
    if not body:
        raise IdeaFoundryError("Idea text cannot be empty.")
    idea_id = _next_idea_id(root)
    now = utc_now().isoformat()
    item = {
        "schema_version": TASK_SCHEMA_VERSION,
        "id": idea_id,
        "title": (title or _derive_title(body)).strip(),
        "status": "inbox",
        "maturity": "spark",
        "tags": _clean_tags(tags or []),
        "source": source.strip() or "manual",
        "promotion_target": None,
        "created_at": now,
        "updated_at": now,
        "classified_at": None,
        "promoted_at": None,
        "archived_at": None,
        "raw_path": f".devflow/ideas/{idea_id}/raw.md",
        "classification_path": None,
        "promotion_path": None,
        "archive_reason": None,
        "parked_at": None,
        "park_reason": None,
        "created_goal_id": None,
        "created_goal_path": None,
        "created_task_id": None,
        "created_task_path": None,
        "created_from_idea_at": None,
        "creation_command": None,
    }
    item_dir = _idea_item_dir(root, idea_id)
    item_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_text(item_dir / "raw.md", body + "\n")
    _write_idea(root, item)
    _append_idea_event(root, idea_id, "created", {"created_at": now})
    return item


def list_ideas(root: Path, *, status: str | None = None) -> list[dict[str, Any]]:
    if status is not None and status not in ALLOWED_IDEA_STATUSES:
        raise IdeaFoundryError(f"Unsupported idea status: {status}")
    items = [item for item in (_read_idea_file(path) for path in _idea_record_paths(root)) if item is not None]
    if status is not None:
        items = [item for item in items if item["status"] == status]
    return items


def show_idea(root: Path, idea_id: str) -> tuple[dict[str, Any], str, str, str]:
    metadata = _get_idea(root, idea_id)
    item_dir = _idea_item_dir(root, idea_id)
    return (
        metadata,
        _read_optional_text(item_dir / "raw.md"),
        _read_optional_text(item_dir / "classification.md"),
        _read_optional_text(item_dir / "promotion.md"),
    )


def classify_idea(
    root: Path,
    idea_id: str,
    *,
    maturity: str,
    note: str = "",
    tags: list[str] | None = None,
) -> dict[str, Any]:
    if maturity not in ALLOWED_IDEA_MATURITIES:
        raise IdeaFoundryError(f"Unsupported idea maturity: {maturity}")
    metadata = _get_idea(root, idea_id)
    if metadata["status"] == "archived":
        raise IdeaFoundryError(f"Archived idea cannot be classified: {idea_id}")
    now = utc_now().isoformat()
    metadata["status"] = "classified"
    metadata["maturity"] = maturity
    metadata["tags"] = _clean_tags(tags or metadata.get("tags") or [])
    metadata["updated_at"] = now
    metadata["classified_at"] = now
    metadata["classification_path"] = f".devflow/ideas/{idea_id}/classification.md"
    atomic_write_text(_idea_item_dir(root, idea_id) / "classification.md", _classification_note(metadata, note))
    _write_idea(root, metadata)
    _append_idea_event(root, idea_id, "classified", {"classified_at": now, "maturity": maturity})
    return metadata


def promote_idea(
    root: Path,
    idea_id: str,
    *,
    target: str,
    rationale: str,
    title: str | None = None,
) -> dict[str, Any]:
    if target not in ALLOWED_PROMOTION_TARGETS:
        raise IdeaFoundryError(f"Unsupported promotion target: {target}")
    metadata = _get_idea(root, idea_id)
    if metadata["status"] == "archived":
        raise IdeaFoundryError(f"Archived idea cannot be promoted: {idea_id}")
    required_maturity = "goal_ready" if target == "goal" else "task_ready"
    if metadata["maturity"] != required_maturity:
        raise IdeaFoundryError(f"Promotion to {target} requires maturity {required_maturity}.")
    decision = rationale.strip()
    if not decision:
        raise IdeaFoundryError("Promotion rationale cannot be empty.")
    now = utc_now().isoformat()
    metadata["status"] = "promoted"
    metadata["promotion_target"] = target
    metadata["updated_at"] = now
    metadata["promoted_at"] = now
    metadata["promotion_path"] = f".devflow/ideas/{idea_id}/promotion.md"
    atomic_write_text(
        _idea_item_dir(root, idea_id) / "promotion.md",
        _promotion_note(metadata, target=target, rationale=decision, title=title),
    )
    _write_idea(root, metadata)
    _append_idea_event(root, idea_id, "promoted", {"promoted_at": now, "target": target})
    return metadata


def archive_idea(root: Path, idea_id: str, *, reason: str) -> dict[str, Any]:
    metadata = _get_idea(root, idea_id)
    now = utc_now().isoformat()
    metadata["status"] = "archived"
    metadata["updated_at"] = now
    metadata["archived_at"] = now
    metadata["archive_reason"] = reason.strip() or "No reason supplied."
    _write_idea(root, metadata)
    _append_idea_event(root, idea_id, "archived", {"archived_at": now, "reason": metadata["archive_reason"]})
    return metadata


def park_idea(root: Path, idea_id: str, *, reason: str) -> dict[str, Any]:
    metadata = _get_idea(root, idea_id)
    if metadata["status"] == "archived":
        raise IdeaFoundryError(f"Archived idea cannot be parked: {idea_id}")
    now = utc_now().isoformat()
    metadata["status"] = "parked"
    metadata["updated_at"] = now
    metadata["parked_at"] = now
    metadata["park_reason"] = reason.strip() or "No reason supplied."
    _write_idea(root, metadata)
    _append_idea_event(root, idea_id, "parked", {"parked_at": now, "reason": metadata["park_reason"]})
    return metadata


def record_idea_creation(
    root: Path,
    idea_id: str,
    *,
    target: str,
    created_id: str,
    created_path: str,
    command: str,
) -> dict[str, Any]:
    if target not in ALLOWED_PROMOTION_TARGETS:
        raise IdeaFoundryError(f"Unsupported creation target: {target}")
    metadata = _get_idea(root, idea_id)
    now = utc_now().isoformat()
    if target == "goal":
        metadata["created_goal_id"] = created_id
        metadata["created_goal_path"] = created_path
    else:
        metadata["created_task_id"] = created_id
        metadata["created_task_path"] = created_path
    metadata["created_from_idea_at"] = now
    metadata["creation_command"] = command
    metadata["updated_at"] = now
    _write_idea(root, metadata)
    _append_idea_event(
        root,
        idea_id,
        f"{target}_created",
        {"created_at": now, "created_id": created_id, "created_path": created_path},
    )
    return metadata


def render_idea_list(items: list[dict[str, Any]]) -> str:
    if not items:
        return "No ideas found.\n"
    lines = [f"{'ID':<8} {'Status':<11} {'Maturity':<11} Title", "-" * 84]
    for item in items:
        lines.append(f"{item['id']:<8} {item['status']:<11} {item['maturity']:<11} {item['title']}")
    return "\n".join(lines) + "\n"


def render_idea_show(metadata: dict[str, Any], raw: str, classification: str, promotion: str) -> str:
    lines = [
        f"id: {metadata['id']}",
        f"status: {metadata['status']}",
        f"maturity: {metadata['maturity']}",
        f"title: {metadata['title']}",
        f"source: {metadata['source']}",
        f"promotion_target: {metadata.get('promotion_target') or ''}",
        f"created_goal_id: {metadata.get('created_goal_id') or ''}",
        f"created_task_id: {metadata.get('created_task_id') or ''}",
        f"created_at: {metadata['created_at']}",
        f"updated_at: {metadata['updated_at']}",
        "tags:",
    ]
    for tag in metadata.get("tags") or []:
        lines.append(f"  - {tag}")
    lines.extend(["", "raw:", raw.rstrip() or "(empty)"])
    lines.extend(["", "classification:", classification.rstrip() or "(empty)"])
    lines.extend(["", "promotion:", promotion.rstrip() or "(empty)"])
    return "\n".join(lines) + "\n"


def greenhouse_lane_for_idea(metadata: dict[str, Any]) -> str:
    status = metadata.get("status")
    maturity = metadata.get("maturity")
    if status == "parked":
        return "parked"
    if status == "archived":
        return "archived"
    if status == "promoted":
        return "promoted"
    if status == "inbox":
        return "raw"
    if status == "classified" and maturity in {"spark", "concept"}:
        return "clarify"
    if status == "classified" and maturity in {"candidate", "goal_ready", "task_ready"}:
        return "candidate"
    return "raw"


def _derive_title(text: str) -> str:
    first_line = text.splitlines()[0].strip()
    return first_line[:72] if first_line else "Untitled idea"


def _clean_tags(tags: list[str]) -> list[str]:
    cleaned: list[str] = []
    for tag in tags:
        value = tag.strip()
        if value and value not in cleaned:
            cleaned.append(value)
    return cleaned


def _classification_note(metadata: dict[str, Any], note: str) -> str:
    lines = [
        "# Idea Classification",
        "",
        f"- idea_id: {metadata['id']}",
        f"- maturity: {metadata['maturity']}",
        "- tags:",
    ]
    lines.extend(f"  - {tag}" for tag in metadata.get("tags") or [])
    lines.extend(["", "## Note", "", note.strip() or "No classification note supplied."])
    return "\n".join(lines) + "\n"


def _promotion_note(metadata: dict[str, Any], *, target: str, rationale: str, title: str | None) -> str:
    suggested_title = (title or metadata["title"]).strip()
    next_command = (
        f'devflow goal init "{suggested_title}"'
        if target == "goal"
        else f'devflow task create "{suggested_title}"'
    )
    lines = [
        "# Idea Promotion Decision",
        "",
        f"- idea_id: {metadata['id']}",
        f"- target: {target}",
        f"- title: {suggested_title}",
        "- created_goal: no",
        "- created_task: no",
        "",
        "## Rationale",
        "",
        rationale,
        "",
        "## Suggested Next Manual Command",
        "",
        f"`{next_command}`",
    ]
    return "\n".join(lines) + "\n"


def _next_idea_id(root: Path) -> str:
    existing: list[int] = []
    for path in _idea_record_paths(root):
        match = re.match(r"I-(\d{4})$", path.parent.name)
        if match:
            existing.append(int(match.group(1)))
    return f"I-{(max(existing) if existing else 0) + 1:04d}"


def _idea_record_paths(root: Path) -> list[Path]:
    base = ideas_dir(root)
    if not base.exists():
        return []
    return sorted(path / "idea.json" for path in base.iterdir() if path.is_dir() and (path / "idea.json").exists())


def _idea_item_dir(root: Path, idea_id: str) -> Path:
    if not re.match(r"^I-\d{4}$", idea_id):
        raise IdeaFoundryError(f"Invalid idea id: {idea_id}")
    return ideas_dir(root) / idea_id


def _get_idea(root: Path, idea_id: str) -> dict[str, Any]:
    path = _idea_item_dir(root, idea_id) / "idea.json"
    if not path.exists():
        raise IdeaFoundryError(f"Idea not found: {idea_id}")
    item = _read_idea_file(path)
    if item is None:
        raise IdeaFoundryError(f"Idea item is malformed: {idea_id}")
    return item


def _read_idea_file(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    if data.get("schema_version") != TASK_SCHEMA_VERSION:
        return None
    if data.get("status") not in ALLOWED_IDEA_STATUSES:
        return None
    if data.get("maturity") not in ALLOWED_IDEA_MATURITIES:
        return None
    return data


def _write_idea(root: Path, metadata: dict[str, Any]) -> None:
    item_dir = _idea_item_dir(root, metadata["id"])
    item_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_text(item_dir / "idea.json", json.dumps(metadata, indent=2, sort_keys=True) + "\n")


def _append_idea_event(root: Path, idea_id: str, event: str, payload: dict[str, Any]) -> None:
    item_dir = _idea_item_dir(root, idea_id)
    event_payload = {
        "timestamp": utc_now().isoformat(),
        "idea_id": idea_id,
        "event": event,
        **payload,
    }
    events_path = item_dir / "events.jsonl"
    events_path.parent.mkdir(parents=True, exist_ok=True)
    with events_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event_payload, sort_keys=True) + "\n")


def _read_optional_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""
