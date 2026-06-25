from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from devflow.control_room.patch_applier import PatchError
from devflow.control_room.project_registry import project_task_ref
from devflow.control_room.service import apply_task_patch


class TaskApplyPatchCommandError(ValueError):
    """User-facing task apply-patch command error."""


@dataclass(frozen=True)
class TaskApplyPatchResult:
    root: Path
    task_id: str
    task_ref: str
    project_id: str | None
    agent_id: str
    run_id: str | None
    patch_hash: str
    patch_review_path: str | None
    patch_dry_run_path: str | None
    patch_evidence_path: str | None
    changed_files: tuple[dict[str, Any], ...]


def build_task_apply_patch_result(
    root: Path,
    task_id: str,
    agent_id: str | None = None,
    run_id: str | None = None,
    project_id: str | None = None,
) -> TaskApplyPatchResult:
    try:
        task = apply_task_patch(root, task_id, agent_id=agent_id, run_id=run_id)
        event = _latest_patch_applied_event(root, task.id) or {}
    except (PatchError, ValueError, KeyError) as exc:
        raise TaskApplyPatchCommandError(str(exc)) from exc

    applied_agent_id = _optional_str(event.get("agent_id")) or agent_id or "default"
    applied_run_id = _optional_str(event.get("run_id")) if "run_id" in event else run_id
    changed_files = event.get("changed_files", [])

    return TaskApplyPatchResult(
        root=root,
        task_id=task.id,
        task_ref=project_task_ref(task.id, project_id),
        project_id=project_id,
        agent_id=applied_agent_id,
        run_id=applied_run_id,
        patch_hash=_optional_str(event.get("patch_hash")) or "unknown",
        patch_review_path=_optional_str(event.get("patch_review_path")),
        patch_dry_run_path=_optional_str(event.get("patch_dry_run_path")),
        patch_evidence_path=_optional_str(event.get("patch_evidence_path")),
        changed_files=_changed_file_items(changed_files),
    )


def render_task_apply_patch_result(result: TaskApplyPatchResult) -> tuple[str, ...]:
    lines = [
        f"Successfully applied patch from agent '{result.agent_id}' "
        f"to task workspace '{result.task_ref}'.",
    ]
    if result.project_id:
        lines.append(f"project_root: {result.root}")
    lines.append(f"Workspace: .devflow/workspaces/{result.task_id}")
    if result.run_id:
        lines.append(f"Run ID: {result.run_id}")
    lines.append(f"Patch Hash: {result.patch_hash}")
    if result.patch_review_path:
        lines.append(f"Patch Review: {result.patch_review_path}")
    if result.patch_dry_run_path:
        lines.append(f"Patch Dry-run: {result.patch_dry_run_path}")
    if result.patch_evidence_path:
        lines.append(f"Patch Evidence: {result.patch_evidence_path}")
    lines.append("")
    lines.append("Modified files:")
    lines.extend(f"  - {item['path']} ({item['operation']})" for item in result.changed_files)
    lines.append("")
    lines.append("Next:")
    if result.project_id:
        lines.append(
            f"  devflow task verify {result.task_id} "
            f"--project {result.project_id} --shell \"<command>\""
        )
    else:
        lines.append(f"  devflow task verify {result.task_id} --shell \"<command>\"")
    return tuple(lines)


def _latest_patch_applied_event(root: Path, task_id: str) -> dict[str, Any] | None:
    events_file = root / ".devflow" / "tasks" / task_id / "events.jsonl"
    if not events_file.exists():
        return None

    latest: dict[str, Any] | None = None
    for line in events_file.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict) and event.get("event") == "patch_applied":
            latest = event
    return latest


def _changed_file_items(value: Any) -> tuple[dict[str, Any], ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, dict) and "path" in item and "operation" in item)


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)
