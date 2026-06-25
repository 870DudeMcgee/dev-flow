from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from devflow.control_room.git_state import inspect_git_state
from devflow.control_room.git_worktree import current_head, git_worker_lane_summary
from devflow.control_room.project_registry import project_task_ref
from devflow.control_room.service import (
    format_promotion_refusal,
    format_stale_baseline_refusal,
    get_task,
    main_checkout_has_uncommitted_changes,
    preview_task_promotion,
    promote_task,
    promotion_baseline,
    promotion_readiness_errors,
)


class TaskPromotionCommandError(ValueError):
    """User-facing task promotion command error."""


@dataclass(frozen=True)
class TaskPromotionPreviewView:
    lines: tuple[str, ...]
    promotion_preview: dict[str, Any]


@dataclass(frozen=True)
class TaskPromotionRunView:
    lines: tuple[str, ...]
    promotion_preview: dict[str, Any]
    requires_confirmation: bool
    no_changes: bool


@dataclass(frozen=True)
class TaskPromotionResultView:
    lines: tuple[str, ...]


def build_task_promotion_preview_view(
    root: Path,
    task_id: str,
    project_id: str | None = None,
) -> TaskPromotionPreviewView:
    try:
        promotion_preview = preview_task_promotion(root, task_id)
        lines = _preview_lines(root, task_id, promotion_preview, project_id=project_id)
    except (KeyError, ValueError) as exc:
        raise TaskPromotionCommandError(str(exc)) from exc
    return TaskPromotionPreviewView(lines=tuple(lines), promotion_preview=promotion_preview)


def build_task_promotion_run_view(
    root: Path,
    task_id: str,
    *,
    force: bool = False,
    force_stale_baseline: bool = False,
    apply_deletions: bool = False,
    project_id: str | None = None,
) -> TaskPromotionRunView:
    try:
        prefix_lines = _promotion_guard_lines(
            root,
            task_id,
            force=force,
            force_stale_baseline=force_stale_baseline,
        )
        promotion_preview = preview_task_promotion(root, task_id)
        lines = [
            *prefix_lines,
            *_run_preview_lines(root, task_id, promotion_preview, project_id=project_id),
        ]
    except (KeyError, ValueError) as exc:
        raise TaskPromotionCommandError(str(exc)) from exc

    no_changes = _has_no_changes(promotion_preview)
    requires_confirmation = bool((apply_deletions or promotion_preview.get("git")) and not no_changes)
    return TaskPromotionRunView(
        lines=tuple(lines),
        promotion_preview=promotion_preview,
        requires_confirmation=requires_confirmation,
        no_changes=no_changes,
    )


def execute_task_promotion_run(
    root: Path,
    task_id: str,
    *,
    force: bool = False,
    force_stale_baseline: bool = False,
    apply_deletions: bool = False,
) -> TaskPromotionResultView:
    try:
        promotion_preview = preview_task_promotion(root, task_id)
        if _has_no_changes(promotion_preview):
            return TaskPromotionResultView(lines=("No changes to promote",))

        before_main_head = current_head(root)
        promote_task(
            root,
            task_id,
            force=force,
            apply_deletions=apply_deletions,
            force_stale_baseline=force_stale_baseline,
        )
        after_main_head = current_head(root)
    except Exception as exc:
        raise TaskPromotionCommandError(f"Error executing promotion: {exc}") from exc

    lines = ["Promotion complete."]
    if promotion_preview.get("git"):
        main_changed = bool(before_main_head and after_main_head and before_main_head != after_main_head)
        lines.append(f"main_changed: {'yes' if main_changed else 'no'}")
        lines.append("staged_changes_left: no")

    deleted = promotion_preview["deleted"]
    if deleted:
        if apply_deletions:
            lines.append(f"Applied deletions: {len(deleted)} file(s) removed.")
        else:
            lines.append(
                "Warning: Deletions are preview-only and were not applied "
                "(deletions are deferred). Use --apply-deletions to apply them."
            )
    return TaskPromotionResultView(lines=tuple(lines))


def _promotion_guard_lines(
    root: Path,
    task_id: str,
    *,
    force: bool,
    force_stale_baseline: bool,
) -> list[str]:
    lines: list[str] = []
    git_state = inspect_git_state(root)
    if git_state.is_repo:
        dirty = main_checkout_has_uncommitted_changes(root)
        if dirty:
            if not force:
                raise ValueError(
                    "Error: Main checkout has uncommitted changes. "
                    "Please commit or stash them first, or use --force to bypass."
                )
            lines.append("Warning: Bypassing safety check for uncommitted changes in main checkout.")

    task = get_task(root, task_id)
    task_path = root / ".devflow" / "tasks" / task.id
    readiness_errors = promotion_readiness_errors(
        task,
        task_path,
        allow_stale_baseline=force_stale_baseline,
    )
    if readiness_errors:
        raise ValueError(
            format_promotion_refusal(
                task,
                task_path,
                allow_stale_baseline=force_stale_baseline,
            )
        )

    baseline = promotion_baseline(root, task)
    if git_state.is_repo:
        if baseline["baseline_status"] == "unavailable":
            raise ValueError(format_stale_baseline_refusal(root, task))
        if baseline["baseline_status"] == "changed":
            if not force_stale_baseline:
                raise ValueError(format_stale_baseline_refusal(root, task))
            lines.append("Warning: Forcing promotion with stale task baseline.")
            lines.append(f"task_baseline_commit: {baseline['task_baseline_commit'] or 'unavailable'}")
            lines.append(f"current_main_head: {baseline['current_main_head'] or 'unavailable'}")
    return lines


def _preview_lines(
    root: Path,
    task_id: str,
    promotion_preview: dict[str, Any],
    *,
    project_id: str | None,
) -> list[str]:
    baseline = promotion_preview["baseline"]
    git_preview = promotion_preview.get("git")
    lane_summary = None
    if git_preview:
        lane_summary = git_worker_lane_summary(root, get_task(root, task_id))

    human_approval = promotion_preview.get("human_approval") or {}
    human_approval_required = bool(human_approval.get("required"))
    if project_id:
        next_action = (
            f"Review this preview, then run 'devflow task promote {task_id}' "
            f"from the project_root above."
        )
    elif human_approval_required:
        next_action = (
            f"Human approval required; review this preview, then run "
            f"'devflow task promote {task_id}'."
        )
    else:
        next_action = f"devflow task promote {task_id}"
    if lane_summary and lane_summary.get("readiness_status") != "ready":
        next_action = str(lane_summary.get("next_safe_action") or next_action)

    lines = [
        "preview_only: yes",
        "main_changed: no",
        f"task: {project_task_ref(task_id, project_id)}",
    ]
    if project_id:
        lines.append(f"project_root: {root}")
    lines.extend(
        [
            f"next_action: {next_action}",
            f"task_baseline_commit: {baseline['task_baseline_commit'] or 'unavailable'}",
            f"current_main_head: {baseline['current_main_head'] or 'unavailable'}",
        ]
    )
    if "origin_main_head" in baseline:
        lines.append(f"origin_main_head: {baseline['origin_main_head'] or 'unavailable'}")
    lines.append(f"baseline_status: {baseline['baseline_status']}")
    if "origin_baseline_status" in baseline:
        lines.append(f"origin_baseline_status: {baseline['origin_baseline_status']}")

    if human_approval_required:
        lines.append("human_approval_required: yes")
        if human_approval.get("reason"):
            lines.append(f"human_approval_reason: {human_approval['reason']}")
        if human_approval.get("prompt"):
            lines.append(f"human_approval_prompt: {human_approval['prompt']}")

    if git_preview:
        lines.extend(
            [
                f"task_id: {git_preview['task_id']}",
                f"worker_id: {git_preview['worker_id']}",
                f"base_commit: {git_preview['base_commit'] or 'unavailable'}",
                f"main_current_head: {git_preview['main_current_head'] or 'unavailable'}",
                f"origin_main_head: {git_preview['origin_main_head'] or 'unavailable'}",
                f"worker_branch: {git_preview['worker_branch']}",
                f"worker_branch_head: {git_preview['worker_branch_head'] or 'unavailable'}",
                f"merge_base: {git_preview['merge_base'] or 'unavailable'}",
                f"baseline_stale: {'yes' if git_preview['baseline_stale'] else 'no'}",
                f"origin_baseline_stale: {'yes' if git_preview['origin_baseline_stale'] else 'no'}",
                f"conflict_prediction: {git_preview['conflict_prediction']}",
                f"verification_status: {git_preview['verification_status']}",
                f"promotion_readiness: {git_preview['promotion_readiness']}",
            ]
        )
        if lane_summary:
            lines.append(f"lane_readiness: {lane_summary['readiness_status']}")
            lines.append(f"next_safe_action: {lane_summary['next_safe_action']}")

    _append_changes_and_diffs(lines, promotion_preview)
    return lines


def _run_preview_lines(
    root: Path,
    task_id: str,
    promotion_preview: dict[str, Any],
    *,
    project_id: str | None,
) -> list[str]:
    lines = [f"task: {project_task_ref(task_id, project_id)}"]
    if project_id:
        lines.append(f"project_root: {root}")
    _append_changes_and_diffs(lines, promotion_preview)
    return lines


def _append_changes_and_diffs(lines: list[str], promotion_preview: dict[str, Any]) -> None:
    if _has_no_changes(promotion_preview):
        lines.append("No changes to promote")
        return

    _append_name_section(lines, "Added files:", promotion_preview["added"])
    _append_name_section(lines, "Modified files:", promotion_preview["modified"])
    _append_name_section(lines, "Deleted files:", promotion_preview["deleted"])
    _append_rename_section(lines, promotion_preview.get("renamed", []))
    _append_name_section(lines, "Untracked files:", promotion_preview.get("untracked", []))
    _append_name_section(lines, "Binary files:", promotion_preview.get("binary", []))

    lines.append("--- Diffs ---")
    for name in sorted(promotion_preview["diffs"].keys()):
        diff_text = promotion_preview["diffs"][name]
        if diff_text:
            lines.extend(diff_text.splitlines())


def _append_name_section(lines: list[str], heading: str, names: list[str]) -> None:
    if not names:
        return
    lines.append(heading)
    for name in names:
        lines.append(f"  - {name}")
    lines.append("")


def _append_rename_section(lines: list[str], renamed: list[dict[str, Any]]) -> None:
    if not renamed:
        return
    lines.append("Renamed files:")
    for item in renamed:
        lines.append(f"  - {item['from']} -> {item['to']}")
    lines.append("")


def _has_no_changes(promotion_preview: dict[str, Any]) -> bool:
    return not (
        promotion_preview["added"]
        or promotion_preview["modified"]
        or promotion_preview["deleted"]
        or promotion_preview.get("renamed", [])
        or promotion_preview.get("untracked", [])
        or promotion_preview.get("binary", [])
    )


__all__ = [
    "TaskPromotionCommandError",
    "TaskPromotionPreviewView",
    "TaskPromotionRunView",
    "TaskPromotionResultView",
    "build_task_promotion_preview_view",
    "build_task_promotion_run_view",
    "execute_task_promotion_run",
]
