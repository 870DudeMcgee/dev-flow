from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from devflow.control_room.git_worktree import is_git_worktree_task, worker_id_for_task
from devflow.control_room.models import TaskRecord
from devflow.control_room.paths import (
    absolute_path,
    relative_path,
    task_dir,
    task_worker_dir,
    workspaces_dir,
    worktree_path,
)
from devflow.control_room.persistence import atomic_write_text, get_task


INLINE_TEXT_LIMIT_BYTES = 4096
_BINARY_SNIFF_BYTES = 2048
_IGNORED_FILE_PARTS = {".devflow", ".git", ".venv", "__pycache__", ".pytest_cache"}


@dataclass(frozen=True)
class _ChangedFile:
    path: str
    status: str
    binary_hint: bool = False


def render_review_capsule(
    root: Path,
    task_id: str,
    *,
    promotion_preview: dict[str, Any] | None = None,
) -> str:
    task = get_task(root, task_id)
    task_path = task_dir(root, task.id)
    worker_id = worker_id_for_task(task) if is_git_worktree_task(task) else task.worker
    workspace, workspace_note = _resolved_task_workspace(root, task)

    verification, verification_path, verification_note = _load_verification(task_path)
    preview, preview_path, preview_note = _load_promotion_preview(root, task, promotion_preview=promotion_preview)
    diff_summary = _load_diff_summary(root, task)
    changed_files = _changed_files(root, task, workspace, workspace_note, preview, diff_summary)

    verification_text = _verification_text(task, verification, verification_note)
    promotion_readiness = _promotion_readiness_text(preview, preview_note)
    promotion_preview_text = _promotion_preview_text(preview, preview_note)
    decision, actions = _decision_and_actions(task, verification, verification_note, preview, preview_note)
    latest_commit = _latest_commit(root, task, verification, preview, diff_summary)

    lines = [
        f"REVIEW CAPSULE - {task.id}",
        "",
        "Decision needed:",
        decision,
        "",
        "Task title:",
        task.title or "missing",
        "",
        "Status:",
        task.status,
        "",
        "Worker:",
        worker_id or "missing",
        "",
        "Workspace:",
        _display_workspace(root, task),
    ]
    if workspace_note:
        lines.extend(["Workspace note:", workspace_note])
    if is_git_worktree_task(task):
        lines.extend(["", "Branch:", task.branch_name or "missing"])
        lines.extend(["", "Latest commit:", latest_commit or "unavailable"])
    lines.extend(
        [
            "",
            "Verification:",
            verification_text,
            "",
            "Promotion readiness:",
            promotion_readiness,
            "",
            "Promotion preview:",
            promotion_preview_text,
            "",
            "Changed files:",
        ]
    )
    lines.extend(_render_changed_files(workspace, workspace_note, changed_files))
    lines.extend(
        [
            "",
            "Canonical evidence:",
            f"- task: {relative_path(root, task_path / 'task.yaml')}",
            f"- events: {relative_path(root, task_path / 'events.jsonl')}",
            f"- verification: {relative_path(root, verification_path) if verification_path else 'missing'}",
            f"- promotion preview: {relative_path(root, preview_path) if preview_path else preview_note}",
            "",
            "Rendered review output:",
            "read-only view; not canonical evidence",
            "",
            "Safe next actions:",
        ]
    )
    lines.extend(f"- {action}" for action in actions)
    return "\n".join(lines) + "\n"


def export_review_capsule_markdown(root: Path, task_id: str, text: str | None = None) -> Path:
    task_path = task_dir(root, task_id)
    output_path = task_path / "review-capsule.md"
    atomic_write_text(output_path, text if text is not None else render_review_capsule(root, task_id))
    return output_path


def _resolved_task_workspace(root: Path, task: TaskRecord) -> tuple[Path, str | None]:
    workspace = absolute_path(root, task.workspace).resolve()
    if is_git_worktree_task(task):
        expected = worktree_path(root, task.id, worker_id_for_task(task)).resolve()
    else:
        expected = (workspaces_dir(root) / task.id).resolve()
    if workspace != expected:
        return workspace, f"unsafe workspace path: {relative_path(root, workspace)} (expected {relative_path(root, expected)})"
    if not workspace.is_dir():
        return workspace, f"workspace missing: {relative_path(root, workspace)}"
    return workspace, None


def _load_verification(task_path: Path) -> tuple[dict[str, Any] | None, Path | None, str]:
    path = task_path / "verification.json"
    payload, note = _read_json_object(path)
    if payload is None:
        return None, path if path.exists() else None, note
    return payload, path, "available"


def _load_promotion_preview(
    root: Path,
    task: TaskRecord,
    *,
    promotion_preview: dict[str, Any] | None = None,
) -> tuple[dict[str, Any] | None, Path | None, str]:
    if promotion_preview is not None:
        nested_git_preview = promotion_preview.get("git")
        if isinstance(nested_git_preview, dict):
            return nested_git_preview, None, "current command output"
        return promotion_preview, None, "current command output"
    task_path = task_dir(root, task.id)
    candidates: list[Path] = []
    if is_git_worktree_task(task):
        candidates.append(task_worker_dir(root, task.id, worker_id_for_task(task)) / "promotion-preview.json")
    candidates.append(task_path / "promotion-preview.json")
    for path in candidates:
        payload, note = _read_json_object(path)
        if payload is not None:
            return payload, path, "available"
        if path.exists():
            return None, path, note
    return None, None, f"missing (run devflow task promote-preview {task.id})"


def _load_diff_summary(root: Path, task: TaskRecord) -> dict[str, Any] | None:
    if not is_git_worktree_task(task):
        return None
    path = task_worker_dir(root, task.id, worker_id_for_task(task)) / "diff-summary.json"
    payload, _note = _read_json_object(path)
    return payload


def _read_json_object(path: Path) -> tuple[dict[str, Any] | None, str]:
    if not path.exists():
        return None, f"missing ({path.name} not found)"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON ({exc.msg})"
    except OSError as exc:
        return None, f"unreadable ({exc})"
    if not isinstance(payload, dict):
        return None, "invalid JSON (expected object)"
    return payload, "available"


def _changed_files(
    root: Path,
    task: TaskRecord,
    workspace: Path,
    workspace_note: str | None,
    preview: dict[str, Any] | None,
    diff_summary: dict[str, Any] | None,
) -> list[_ChangedFile]:
    if preview is not None:
        return _entries_from_preview(preview)
    if diff_summary is not None:
        return _entries_from_diff_summary(diff_summary)
    if workspace_note is not None:
        return []
    if is_git_worktree_task(task):
        return []
    return _copy_workspace_changes(root, workspace)


def _entries_from_preview(preview: dict[str, Any]) -> list[_ChangedFile]:
    binary_paths = set(_string_list(preview.get("binary")))
    entries = [
        _ChangedFile(path, "added", path in binary_paths)
        for path in _string_list(preview.get("added"))
    ]
    entries.extend(
        _ChangedFile(path, "modified", path in binary_paths)
        for path in _string_list(preview.get("modified"))
    )
    entries.extend(_ChangedFile(path, "deleted", path in binary_paths) for path in _string_list(preview.get("deleted")))
    entries.extend(_ChangedFile(path, "untracked", path in binary_paths) for path in _string_list(preview.get("untracked")))
    for item in preview.get("renamed") or []:
        if isinstance(item, dict) and isinstance(item.get("to"), str):
            old = item.get("from") if isinstance(item.get("from"), str) else "unknown"
            path = item["to"]
            entries.append(_ChangedFile(path, f"renamed from {old}", path in binary_paths))
    for path in sorted(binary_paths):
        if path not in {entry.path for entry in entries}:
            entries.append(_ChangedFile(path, "binary", True))
    return _sorted_unique_entries(entries)


def _entries_from_diff_summary(summary: dict[str, Any]) -> list[_ChangedFile]:
    binary_paths = set(_string_list(summary.get("binary_files")))
    entries = [
        _ChangedFile(path, "added", path in binary_paths)
        for path in _string_list(summary.get("added_files"))
    ]
    entries.extend(
        _ChangedFile(path, "modified", path in binary_paths)
        for path in _string_list(summary.get("modified_files"))
    )
    entries.extend(_ChangedFile(path, "deleted", path in binary_paths) for path in _string_list(summary.get("deleted_files")))
    entries.extend(_ChangedFile(path, "untracked", path in binary_paths) for path in _string_list(summary.get("untracked_files")))
    for item in summary.get("renamed_files") or []:
        if isinstance(item, dict) and isinstance(item.get("to"), str):
            old = item.get("from") if isinstance(item.get("from"), str) else "unknown"
            path = item["to"]
            entries.append(_ChangedFile(path, f"renamed from {old}", path in binary_paths))
    for path in sorted(binary_paths):
        if path not in {entry.path for entry in entries}:
            entries.append(_ChangedFile(path, "binary", True))
    return _sorted_unique_entries(entries)


def _copy_workspace_changes(root: Path, workspace: Path) -> list[_ChangedFile]:
    workspace_files = _relative_files(workspace)
    main_files = _relative_files(root)
    entries: list[_ChangedFile] = []
    for path in workspace_files - main_files:
        entries.append(_ChangedFile(path, "added", _looks_binary(workspace / path)))
    for path in main_files - workspace_files:
        entries.append(_ChangedFile(path, "deleted"))
    for path in workspace_files & main_files:
        workspace_file = workspace / path
        main_file = root / path
        try:
            changed = workspace_file.read_bytes() != main_file.read_bytes()
        except OSError:
            changed = True
        if changed:
            entries.append(_ChangedFile(path, "modified", _looks_binary(workspace_file)))
    return _sorted_unique_entries(entries)


def _relative_files(base: Path) -> set[str]:
    files: set[str] = set()
    if not base.is_dir():
        return files
    for path in base.rglob("*"):
        if not path.is_file() or path.is_symlink() or _ignored(path, base):
            continue
        try:
            files.add(path.relative_to(base).as_posix())
        except ValueError:
            continue
    return files


def _ignored(path: Path, base: Path) -> bool:
    try:
        rel = path.relative_to(base)
    except ValueError:
        return True
    return any(part in _IGNORED_FILE_PARTS for part in rel.parts)


def _sorted_unique_entries(entries: list[_ChangedFile]) -> list[_ChangedFile]:
    unique: dict[str, _ChangedFile] = {}
    for entry in entries:
        unique.setdefault(entry.path, entry)
    return [unique[path] for path in sorted(unique)]


def _render_changed_files(workspace: Path, workspace_note: str | None, entries: list[_ChangedFile]) -> list[str]:
    if workspace_note is not None:
        return [f"(workspace unavailable: {workspace_note})"]
    if not entries:
        return ["(none)"]
    lines: list[str] = []
    for index, entry in enumerate(entries, start=1):
        lines.append(f"{index}. {entry.path}")
        lines.append(f"   status: {entry.status}")
        preview = _file_preview(workspace, entry)
        if preview.startswith("contents:\n"):
            lines.append("   contents:")
            lines.extend(f"   {line}" if line else "   " for line in preview.removeprefix("contents:\n").splitlines())
        else:
            lines.append(f"   contents: {preview}")
    return lines


def _file_preview(workspace: Path, entry: _ChangedFile) -> str:
    if entry.status == "deleted":
        return "[file deleted]"
    unsafe = _unsafe_path_reason(entry.path)
    if unsafe:
        return f"[rejected unsafe path: {unsafe}]"
    path = (workspace / entry.path).resolve()
    workspace_root = workspace.resolve()
    try:
        path.relative_to(workspace_root)
    except ValueError:
        return "[rejected unsafe path: resolved path escapes workspace]"
    if entry.binary_hint:
        return "[binary file not shown]"
    if not path.exists():
        return "[file missing from workspace]"
    if path.is_symlink():
        return "[symlink not shown]"
    if not path.is_file():
        return "[not a regular file]"
    if _looks_binary(path):
        return "[binary file not shown]"
    try:
        with path.open("rb") as file_obj:
            data = file_obj.read(INLINE_TEXT_LIMIT_BYTES + 1)
    except OSError as exc:
        return f"[unreadable: {exc}]"
    truncated = len(data) > INLINE_TEXT_LIMIT_BYTES
    text_bytes = data[:INLINE_TEXT_LIMIT_BYTES]
    try:
        text = text_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return "[binary or non-UTF-8 file not shown]"
    if truncated:
        text = text.rstrip("\n") + f"\n... truncated after {INLINE_TEXT_LIMIT_BYTES} bytes ..."
    if not text:
        text = "[empty file]"
    return "contents:\n" + text


def _unsafe_path_reason(path: str) -> str | None:
    value = Path(path)
    if value.is_absolute():
        return "absolute paths are not allowed"
    if any(part == ".." for part in value.parts):
        return "path traversal is not allowed"
    if path in {"", "."}:
        return "empty paths are not allowed"
    return None


def _looks_binary(path: Path) -> bool:
    try:
        with path.open("rb") as file_obj:
            return b"\0" in file_obj.read(_BINARY_SNIFF_BYTES)
    except OSError:
        return False


def _verification_text(task: TaskRecord, payload: dict[str, Any] | None, note: str) -> str:
    if payload is None:
        return "missing (no verification.json)" if note.startswith("missing") else note
    status = payload.get("status") or task.verification_status
    exit_code = payload.get("exit_code")
    if status == "passed":
        return "PASS"
    if status == "failed":
        return f"FAIL (exit code {exit_code})" if exit_code is not None else "FAIL"
    if status == "not_run":
        return "NOT RUN"
    return str(status or "unknown")


def _promotion_readiness_text(payload: dict[str, Any] | None, note: str) -> str:
    if payload is None:
        return note
    readiness = payload.get("promotion_readiness")
    if isinstance(readiness, str) and readiness:
        if readiness == "ready" and payload.get("human_approval_required") is True:
            return "ready (human approval required)"
        return readiness
    return "available"


def _promotion_preview_text(payload: dict[str, Any] | None, note: str) -> str:
    if payload is None:
        return note
    readiness = payload.get("promotion_readiness")
    if readiness == "ready" and payload.get("human_approval_required") is True:
        return "PASS (human approval required)"
    if readiness == "ready":
        return "PASS"
    if isinstance(readiness, str) and readiness:
        return f"not ready ({readiness})"
    return "available"


def _decision_and_actions(
    task: TaskRecord,
    verification: dict[str, Any] | None,
    verification_note: str,
    preview: dict[str, Any] | None,
    preview_note: str,
) -> tuple[str, list[str]]:
    verification_status = (verification or {}).get("status") or task.verification_status
    if verification is None or verification_status == "not_run":
        return (
            "Run verification for this task.",
            [f"run verification {task.id}", f"reject/close {task.id}"],
        )
    if verification_status != "passed":
        return (
            "Needs changes before promotion.",
            [f"needs changes {task.id}", f"reject/close {task.id}"],
        )
    if preview is None:
        return (
            "Run promotion preview before promoting.",
            [f"run promotion preview {task.id}", f"reject/close {task.id}"],
        )
    if preview.get("promotion_readiness") == "ready" and preview.get("human_approval_required") is True:
        return (
            "Human approval required before promotion.",
            [f"review preview and approve {task.id}", f"reject/close {task.id}"],
        )
    if preview.get("promotion_readiness") == "ready":
        return (
            "Promote or reject this task.",
            [f"promote {task.id}", f"reject/close {task.id}"],
        )
    if preview_note == "current command output":
        return (
            "Review promotion preview and decide whether this needs changes.",
            [f"needs changes {task.id}", f"reject/close {task.id}"],
        )
    return (
        "Needs changes before promotion.",
        [f"needs changes {task.id}", f"reject/close {task.id}"],
    )


def _latest_commit(
    root: Path,
    task: TaskRecord,
    verification: dict[str, Any] | None,
    preview: dict[str, Any] | None,
    diff_summary: dict[str, Any] | None,
) -> str | None:
    for payload, key in (
        (preview, "worker_branch_head"),
        (diff_summary, "head_commit"),
        (verification, "verified_commit"),
    ):
        value = payload.get(key) if payload else None
        if isinstance(value, str) and value:
            return value
    if is_git_worktree_task(task):
        git_json, _note = _read_json_object(task_worker_dir(root, task.id, worker_id_for_task(task)) / "git.json")
        value = git_json.get("head_commit") if git_json else None
        if isinstance(value, str) and value:
            return value
    return None


def _display_workspace(root: Path, task: TaskRecord) -> str:
    workspace = task.workspace_path or task.workspace
    if not workspace:
        return "missing"
    return relative_path(root, absolute_path(root, workspace))


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]
