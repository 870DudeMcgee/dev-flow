from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from devflow.control_room.models import TASK_SCHEMA_VERSION
from devflow.control_room.paths import knowledge_dir, relative_path, task_dir
from devflow.control_room.persistence import atomic_write_text, get_task, utc_now


ALLOWED_KNOWLEDGE_TYPES = {
    "pattern",
    "workflow",
    "mistake",
    "prompt",
    "verification",
    "local_model",
    "cost_saving",
    "decision",
    "convention",
    "gap",
    "orchestration",
    "git_discipline",
}
ALLOWED_KNOWLEDGE_STATUSES = {"proposed", "promoted", "rejected"}


class KnowledgeFoundryError(ValueError):
    pass


def capture_from_task(root: Path, task_id: str) -> dict[str, Any]:
    task = get_task(root, task_id)
    source_paths = _existing_task_sources(root, task_id)
    if not source_paths:
        raise KnowledgeFoundryError(f"No source artifacts found for task {task_id}.")
    knowledge_type = _task_knowledge_type(task.verification_status)
    title = f"Review reusable lesson from {task_id}: {task.title}"
    note = _task_note_stub(task_id, task.title, task.status, task.verification_status, source_paths)
    return _create_knowledge(
        root,
        source_task=task_id,
        source_paths=source_paths,
        linked_artifacts=source_paths,
        knowledge_type=knowledge_type,
        tags=["task-capture", "needs-human-review", task.status],
        title=title,
        note=note,
    )


def capture_from_validation(root: Path, validation_path: Path) -> dict[str, Any]:
    path = validation_path if validation_path.is_absolute() else root / validation_path
    if not path.exists():
        raise KnowledgeFoundryError(f"Validation artifact not found: {validation_path}")
    try:
        validation = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise KnowledgeFoundryError(f"Validation artifact is malformed JSON: {exc.msg}") from exc
    if not isinstance(validation, dict):
        raise KnowledgeFoundryError("Validation artifact must be a JSON object.")
    source_task = validation.get("input_task_id") if isinstance(validation.get("input_task_id"), str) else None
    rel_path = relative_path(root, path)
    status = str(validation.get("status") or "unknown")
    errors = validation.get("errors") if isinstance(validation.get("errors"), list) else []
    knowledge_type = "mistake" if status == "failed" else "workflow"
    title = f"Review worker outcome validation: {Path(rel_path).name}"
    note_lines = [
        "# Proposed Knowledge Note",
        "",
        "This note was captured from worker outcome validation evidence.",
        "",
        f"- validation_status: {status}",
        f"- source_validation: {rel_path}",
    ]
    if errors:
        note_lines.append("- validation_errors:")
        note_lines.extend(f"  - {error}" for error in errors[:10])
    note_lines.extend(
        [
            "",
            "TODO: A human should decide whether this validation evidence represents a reusable workflow, mistake, or convention.",
        ]
    )
    return _create_knowledge(
        root,
        source_task=source_task,
        source_paths=[rel_path],
        linked_artifacts=[rel_path],
        knowledge_type=knowledge_type,
        tags=["validation-capture", "needs-human-review", status],
        title=title,
        note="\n".join(note_lines) + "\n",
    )


def list_knowledge(root: Path) -> list[dict[str, Any]]:
    items = [_read_knowledge_file(path) for path in _knowledge_record_paths(root)]
    return [item for item in items if item is not None]


def show_knowledge(root: Path, knowledge_id: str) -> tuple[dict[str, Any], str]:
    metadata = _get_knowledge(root, knowledge_id)
    note_path = _knowledge_item_dir(root, knowledge_id) / "note.md"
    note = note_path.read_text(encoding="utf-8") if note_path.exists() else ""
    return metadata, note


def promote_knowledge(root: Path, knowledge_id: str) -> dict[str, Any]:
    metadata = _get_knowledge(root, knowledge_id)
    now = utc_now().isoformat()
    metadata["status"] = "promoted"
    metadata["promoted_at"] = now
    metadata["rejected_at"] = None
    _write_knowledge(root, metadata)
    _append_knowledge_event(root, knowledge_id, "promoted", {"promoted_at": now})
    return metadata


def reject_knowledge(root: Path, knowledge_id: str) -> dict[str, Any]:
    metadata = _get_knowledge(root, knowledge_id)
    now = utc_now().isoformat()
    metadata["status"] = "rejected"
    metadata["rejected_at"] = now
    metadata["promoted_at"] = None
    _write_knowledge(root, metadata)
    _append_knowledge_event(root, knowledge_id, "rejected", {"rejected_at": now})
    return metadata


def search_knowledge(root: Path, query: str) -> list[dict[str, Any]]:
    needle = query.strip().lower()
    if not needle:
        return []
    matches: list[dict[str, Any]] = []
    for item in list_knowledge(root):
        note_path = _knowledge_item_dir(root, item["id"]) / "note.md"
        note = note_path.read_text(encoding="utf-8") if note_path.exists() else ""
        haystack = " ".join(
            [
                str(item.get("title") or ""),
                " ".join(str(tag) for tag in item.get("tags") or []),
                note,
            ]
        ).lower()
        if needle in haystack:
            matches.append(item)
    return matches


def render_knowledge_list(items: list[dict[str, Any]]) -> str:
    if not items:
        return "No knowledge items found.\n"
    lines = [f"{'ID':<10} {'Status':<10} {'Type':<14} Title", "-" * 84]
    for item in items:
        lines.append(
            f"{item['id']:<10} {item['status']:<10} {item['type']:<14} {item['title']}"
        )
    return "\n".join(lines) + "\n"


def render_knowledge_show(metadata: dict[str, Any], note: str) -> str:
    lines = [
        f"id: {metadata['id']}",
        f"status: {metadata['status']}",
        f"type: {metadata['type']}",
        f"title: {metadata['title']}",
        f"source_task: {metadata.get('source_task') or ''}",
        f"created_at: {metadata['created_at']}",
        f"promoted_at: {metadata.get('promoted_at') or ''}",
        f"rejected_at: {metadata.get('rejected_at') or ''}",
        "source_paths:",
    ]
    for path in metadata.get("source_paths") or []:
        lines.append(f"  - {path}")
    lines.append("tags:")
    for tag in metadata.get("tags") or []:
        lines.append(f"  - {tag}")
    lines.extend(["", "note:", note.rstrip() or "(empty)"])
    return "\n".join(lines) + "\n"


def _create_knowledge(
    root: Path,
    *,
    source_task: str | None,
    source_paths: list[str],
    linked_artifacts: list[str],
    knowledge_type: str,
    tags: list[str],
    title: str,
    note: str,
) -> dict[str, Any]:
    if knowledge_type not in ALLOWED_KNOWLEDGE_TYPES:
        raise KnowledgeFoundryError(f"Unsupported knowledge type: {knowledge_type}")
    knowledge_id = _next_knowledge_id(root)
    now = utc_now().isoformat()
    metadata = {
        "schema_version": TASK_SCHEMA_VERSION,
        "id": knowledge_id,
        "status": "proposed",
        "source_task": source_task,
        "source_paths": source_paths,
        "linked_artifacts": linked_artifacts,
        "linked_memories": [],
        "type": knowledge_type,
        "tags": tags,
        "title": title,
        "created_at": now,
        "promoted_at": None,
        "rejected_at": None,
    }
    item_dir = _knowledge_item_dir(root, knowledge_id)
    item_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_text(item_dir / "note.md", note)
    _write_knowledge(root, metadata)
    _append_knowledge_event(root, knowledge_id, "created", {"created_at": now})
    return metadata


def _task_note_stub(
    task_id: str,
    title: str,
    status: str,
    verification_status: str,
    source_paths: list[str],
) -> str:
    lines = [
        "# Proposed Knowledge Note",
        "",
        "This is a human-review stub captured from existing task evidence.",
        "",
        f"- task_id: {task_id}",
        f"- title: {title}",
        f"- task_status: {status}",
        f"- verification_status: {verification_status}",
        "- source_paths:",
    ]
    lines.extend(f"  - {path}" for path in source_paths)
    lines.extend(
        [
            "",
            "TODO: A human should write the reusable lesson before promotion. No lesson was inferred automatically.",
        ]
    )
    return "\n".join(lines) + "\n"


def _task_knowledge_type(verification_status: str) -> str:
    if verification_status == "passed":
        return "verification"
    if verification_status == "failed":
        return "mistake"
    return "gap"


def _existing_task_sources(root: Path, task_id: str) -> list[str]:
    base = task_dir(root, task_id)
    candidates = [
        base / "task.yaml",
        base / "events.jsonl",
        base / "result.md",
        base / "verification.json",
        base / "merge-readiness.json",
        base / "closure.json",
        base / "cleanup.json",
        base / "logs" / "worker.log",
        base / "logs" / "verify.log",
        base / "orchestration-plan.yaml",
        base / "worker-outcome-validation.json",
    ]
    paths = [relative_path(root, path) for path in candidates if path.exists()]
    agents_dir = base / "agents"
    if agents_dir.exists():
        for path in sorted(agents_dir.rglob("*")):
            if path.is_file():
                paths.append(relative_path(root, path))
    return paths


def _next_knowledge_id(root: Path) -> str:
    existing: list[int] = []
    for path in _knowledge_record_paths(root):
        match = re.match(r"K-(\d{4})$", path.parent.name)
        if match:
            existing.append(int(match.group(1)))
    return f"K-{(max(existing) if existing else 0) + 1:04d}"


def _knowledge_record_paths(root: Path) -> list[Path]:
    base = knowledge_dir(root)
    if not base.exists():
        return []
    return sorted(path / "knowledge.json" for path in base.iterdir() if path.is_dir() and (path / "knowledge.json").exists())


def _knowledge_item_dir(root: Path, knowledge_id: str) -> Path:
    if not re.match(r"^K-\d{4}$", knowledge_id):
        raise KnowledgeFoundryError(f"Invalid knowledge id: {knowledge_id}")
    return knowledge_dir(root) / knowledge_id


def _get_knowledge(root: Path, knowledge_id: str) -> dict[str, Any]:
    path = _knowledge_item_dir(root, knowledge_id) / "knowledge.json"
    if not path.exists():
        raise KnowledgeFoundryError(f"Knowledge item not found: {knowledge_id}")
    item = _read_knowledge_file(path)
    if item is None:
        raise KnowledgeFoundryError(f"Knowledge item is malformed: {knowledge_id}")
    return item


def _read_knowledge_file(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    if data.get("schema_version") != 1:
        return None
    if data.get("status") not in ALLOWED_KNOWLEDGE_STATUSES:
        return None
    if data.get("type") not in ALLOWED_KNOWLEDGE_TYPES:
        return None
    return data


def _write_knowledge(root: Path, metadata: dict[str, Any]) -> None:
    item_dir = _knowledge_item_dir(root, metadata["id"])
    item_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_text(item_dir / "knowledge.json", json.dumps(metadata, indent=2, sort_keys=True) + "\n")


def _append_knowledge_event(root: Path, knowledge_id: str, event: str, payload: dict[str, Any]) -> None:
    item_dir = _knowledge_item_dir(root, knowledge_id)
    event_payload = {
        "timestamp": utc_now().isoformat(),
        "knowledge_id": knowledge_id,
        "event": event,
        **payload,
    }
    events_path = item_dir / "events.jsonl"
    events_path.parent.mkdir(parents=True, exist_ok=True)
    with events_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event_payload, sort_keys=True) + "\n")
