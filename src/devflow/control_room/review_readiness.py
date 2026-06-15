from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from devflow.control_room.git_worktree import git_worker_lane_summary, is_git_worktree_task, worker_id_for_task
from devflow.control_room.local_worker_lane import local_worker_lane_summary
from devflow.control_room.models import TaskRecord
from devflow.control_room.paths import relative_path, task_dir, task_worker_dir
from devflow.control_room.persistence import get_task, list_tasks
from devflow.control_room.status_projection import TaskStatusProjection, build_task_status_projection


ReviewState = Literal[
    "ready_for_review",
    "needs_verification",
    "verification_failed",
    "needs_promotion_preview",
    "blocked",
    "worker_failed",
    "running",
    "not_ready",
]

REVIEW_STATES: tuple[ReviewState, ...] = (
    "ready_for_review",
    "needs_verification",
    "verification_failed",
    "needs_promotion_preview",
    "blocked",
    "worker_failed",
    "running",
    "not_ready",
)

DEFAULT_PROMOTION_PREVIEW_KEYS = frozenset(
    {"baseline", "added", "modified", "deleted", "diffs", "human_approval"}
)


class ReviewReadinessProjection(BaseModel):
    task_id: str
    title: str
    status: str
    display_status: str
    verification_status: str
    review_state: ReviewState
    score: int
    blockers: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    next_command: str
    promotion_preview_path: str | None = None
    worker_lane: str | None = None
    worker_branch: str | None = None
    worktree_path: str | None = None
    lane_readiness: str | None = None
    lane_next_action: str | None = None
    local_worker_lane: str | None = None
    local_worker: str | None = None
    local_worker_readiness: str | None = None
    local_worker_next_action: str | None = None


class ReviewReadinessSummary(BaseModel):
    schema_version: int = 1
    total_tasks: int
    ready_for_review_count: int
    needs_verification_count: int
    review_blocked_count: int
    counts: dict[str, int] = Field(default_factory=dict)
    tasks: list[ReviewReadinessProjection] = Field(default_factory=list)


def build_review_readiness_projection(
    root: Path,
    task_id: str,
    *,
    task: TaskRecord | None = None,
    status_projection: TaskStatusProjection | None = None,
    project_id: str | None = None,
) -> ReviewReadinessProjection:
    record = task or get_task(root, task_id)
    projection = status_projection or build_task_status_projection(root, record.id, task=record)
    preview = _promotion_preview_state(root, record)
    evidence = _evidence_paths(root, projection, preview.path)
    lane = git_worker_lane_summary(root, record)
    if lane:
        evidence = _dedupe(evidence + list(lane.get("evidence_paths") or []))
    local_lane = local_worker_lane_summary(root, record)
    if local_lane:
        evidence = _dedupe(evidence + list(local_lane.get("evidence_paths") or []))
    state, score, blockers, next_command = _classify_review_readiness(
        projection,
        preview,
        project_id=project_id,
    )

    return ReviewReadinessProjection(
        task_id=record.id,
        title=record.title,
        status=record.status,
        display_status=projection.display_status,
        verification_status=projection.verification_status,
        review_state=state,
        score=score,
        blockers=blockers,
        evidence=evidence,
        next_command=next_command,
        promotion_preview_path=preview.path,
        worker_lane=lane.get("workspace_mode") if lane else None,
        worker_branch=lane.get("worker_branch") if lane else None,
        worktree_path=lane.get("worktree_path") if lane else None,
        lane_readiness=lane.get("readiness_status") if lane else None,
        lane_next_action=lane.get("next_safe_action") if lane else None,
        local_worker_lane=local_lane.get("lane_type") if local_lane else None,
        local_worker=local_lane.get("worker_id") if local_lane else None,
        local_worker_readiness=local_lane.get("readiness_status") if local_lane else None,
        local_worker_next_action=local_lane.get("next_safe_action") if local_lane else None,
    )


def list_review_readiness_projections(root: Path, *, project_id: str | None = None) -> list[ReviewReadinessProjection]:
    projections = [
        build_review_readiness_projection(root, task.id, task=task, project_id=project_id)
        for task in list_tasks(root)
        if task.status not in {"closed", "promoted"}
    ]
    return sorted(projections, key=lambda item: (-item.score, item.task_id))


def summarize_review_readiness(root: Path, *, project_id: str | None = None) -> ReviewReadinessSummary:
    tasks = list_review_readiness_projections(root, project_id=project_id)
    counts: dict[str, int] = {state: 0 for state in REVIEW_STATES}
    for task in tasks:
        counts[task.review_state] = counts.get(task.review_state, 0) + 1
    review_blocked_count = (
        counts.get("blocked", 0)
        + counts.get("worker_failed", 0)
        + counts.get("verification_failed", 0)
    )

    return ReviewReadinessSummary(
        total_tasks=len(tasks),
        ready_for_review_count=counts.get("ready_for_review", 0),
        needs_verification_count=counts.get("needs_verification", 0),
        review_blocked_count=review_blocked_count,
        counts=counts,
        tasks=tasks,
    )


def render_review_readiness(projection_or_summary: ReviewReadinessProjection | ReviewReadinessSummary) -> str:
    if isinstance(projection_or_summary, ReviewReadinessSummary):
        lines = [
            "Review Readiness",
            f"  Total active tasks: {projection_or_summary.total_tasks}",
            f"  Ready for review: {projection_or_summary.ready_for_review_count}",
            f"  Needs verification: {projection_or_summary.needs_verification_count}",
            f"  Review blocked: {projection_or_summary.review_blocked_count}",
            "",
            "Tasks",
        ]
        if not projection_or_summary.tasks:
            lines.append("  None")
        for task in projection_or_summary.tasks:
            lines.append(f"  - {task.task_id}: {task.review_state} (score={task.score})")
            lines.append(f"    next: {task.next_command}")
            if task.worker_lane:
                lines.append(f"    worker_lane: {task.worker_lane}")
                lines.append(f"    lane_readiness: {task.lane_readiness or 'unknown'}")
            if task.local_worker_lane:
                lines.append(f"    local_worker_lane: {task.local_worker_lane}")
                lines.append(f"    local_worker_readiness: {task.local_worker_readiness or 'unknown'}")
            if task.blockers:
                lines.append(f"    blockers: {'; '.join(task.blockers)}")
        return "\n".join(lines) + "\n"

    lines = [
        f"task: {projection_or_summary.task_id}",
        f"title: {projection_or_summary.title}",
        f"status: {projection_or_summary.status}",
        f"display_status: {projection_or_summary.display_status}",
        f"verification_status: {projection_or_summary.verification_status}",
        f"review_state: {projection_or_summary.review_state}",
        f"score: {projection_or_summary.score}",
        f"next_command: {projection_or_summary.next_command}",
    ]
    if projection_or_summary.worker_lane:
        lines.extend(
            [
                f"worker_lane: {projection_or_summary.worker_lane}",
                f"worker_branch: {projection_or_summary.worker_branch or ''}",
                f"worktree_path: {projection_or_summary.worktree_path or ''}",
                f"lane_readiness: {projection_or_summary.lane_readiness or 'unknown'}",
                f"lane_next_action: {projection_or_summary.lane_next_action or ''}",
            ]
        )
    if projection_or_summary.local_worker_lane:
        lines.extend(
            [
                f"local_worker_lane: {projection_or_summary.local_worker_lane}",
                f"local_worker: {projection_or_summary.local_worker or ''}",
                f"local_worker_readiness: {projection_or_summary.local_worker_readiness or 'unknown'}",
                f"local_worker_next_action: {projection_or_summary.local_worker_next_action or ''}",
            ]
        )
    lines.append("blockers:")
    if projection_or_summary.blockers:
        lines.extend(f"  - {blocker}" for blocker in projection_or_summary.blockers)
    else:
        lines.append("  - none")
    lines.append("evidence:")
    if projection_or_summary.evidence:
        lines.extend(f"  - {path}" for path in projection_or_summary.evidence)
    else:
        lines.append("  - none")
    return "\n".join(lines) + "\n"


class _PromotionPreviewState(BaseModel):
    available: bool
    path: str | None = None
    blocker: str | None = None


def _classify_review_readiness(
    projection: TaskStatusProjection,
    preview: _PromotionPreviewState,
    *,
    project_id: str | None,
) -> tuple[ReviewState, int, list[str], str]:
    task_id = projection.task.id
    if not projection.is_active:
        return "not_ready", 0, ["task is not active"], _task_command("show", task_id, project_id)
    if projection.is_worker_failed or projection.is_timeout:
        return (
            "worker_failed",
            20,
            ["worker failed before reviewable output"],
            _task_command("log", task_id, project_id),
        )
    if projection.is_blocked:
        blocker = projection.manual_agent_question or "task is blocked or awaiting human input"
        return "blocked", 30, [blocker], _task_command("show", task_id, project_id)
    if projection.task.status == "running":
        return "running", 35, ["task is still running"], _task_command("show", task_id, project_id)
    if projection.failed_verification:
        return (
            "verification_failed",
            40,
            ["verification failed"],
            _task_command("log", task_id, project_id, suffix="--verify --tail 80"),
        )
    if projection.needs_verification:
        command = projection.dashboard_next_action.command or _task_command(
            "verify",
            task_id,
            project_id,
            suffix='--shell "<command>"',
        )
        return "needs_verification", 60, ["verification has not passed"], _scope_task_command(command, project_id)
    if projection.is_verified:
        if projection.promotion_blockers:
            if _promotion_blockers_require_verification(projection.promotion_blockers):
                return (
                    "needs_verification",
                    60,
                    projection.promotion_blockers,
                    _task_command("verify", task_id, project_id, suffix='--shell "<command>"'),
                )
            return (
                "needs_promotion_preview",
                80,
                projection.promotion_blockers,
                _task_command("promote-preview", task_id, project_id),
            )
        if preview.available:
            return "ready_for_review", 100, [], _task_command("capsule", task_id, project_id)
        return (
            "needs_promotion_preview",
            80,
            [preview.blocker or "promotion preview is missing"],
            _task_command("promote-preview", task_id, project_id),
        )
    return "not_ready", 10, ["no reviewable task output was found"], _task_command("show", task_id, project_id)


def _promotion_blockers_require_verification(blockers: list[str]) -> bool:
    verification_terms = (
        "verification status",
        "verification exit code",
        "verification.json",
        "verified_patch",
        "patch-application.json",
    )
    return any(any(term in blocker for term in verification_terms) for blocker in blockers)


def _promotion_preview_state(root: Path, task: TaskRecord) -> _PromotionPreviewState:
    for path in _promotion_preview_candidates(root, task):
        if not path.exists():
            continue
        display_path = relative_path(root, path)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            return _PromotionPreviewState(
                available=False,
                path=display_path,
                blocker=f"promotion-preview.json is invalid JSON: {exc.msg}",
            )
        except OSError as exc:
            return _PromotionPreviewState(
                available=False,
                path=display_path,
                blocker=f"promotion-preview.json is unreadable: {exc}",
            )
        if not isinstance(payload, dict):
            return _PromotionPreviewState(
                available=False,
                path=display_path,
                blocker="promotion-preview.json is not an object",
            )
        preview_task_id = payload.get("task_id")
        if preview_task_id is not None and preview_task_id != task.id:
            return _PromotionPreviewState(
                available=False,
                path=display_path,
                blocker=f"promotion-preview.json task_id is {preview_task_id!r}, expected {task.id!r}",
            )
        if "promotion_readiness" in payload:
            promotion_readiness = payload.get("promotion_readiness")
            if promotion_readiness != "ready":
                return _PromotionPreviewState(
                    available=False,
                    path=display_path,
                    blocker=f"promotion preview is not ready: {promotion_readiness}",
                )
            return _PromotionPreviewState(available=True, path=display_path)
        if not DEFAULT_PROMOTION_PREVIEW_KEYS.issubset(payload):
            return _PromotionPreviewState(
                available=False,
                path=display_path,
                blocker="promotion-preview.json promotion_readiness is missing",
            )
        return _PromotionPreviewState(available=True, path=display_path)
    return _PromotionPreviewState(available=False, blocker="promotion-preview.json is missing")


def _promotion_preview_candidates(root: Path, task: TaskRecord) -> list[Path]:
    candidates: list[Path] = []
    if is_git_worktree_task(task):
        candidates.append(task_worker_dir(root, task.id, worker_id_for_task(task)) / "promotion-preview.json")
    candidates.append(task_dir(root, task.id) / "promotion-preview.json")
    return candidates


def _evidence_paths(root: Path, projection: TaskStatusProjection, preview_path: str | None) -> list[str]:
    task_path = projection.task_path
    paths = [
        relative_path(root, task_path / "task.yaml"),
        relative_path(root, task_path / "events.jsonl"),
    ]
    verification_path = task_path / "verification.json"
    if verification_path.exists():
        paths.append(relative_path(root, verification_path))
    if preview_path:
        paths.append(preview_path)
    for value in (
        projection.task.log_path,
        projection.task.result_path,
        projection.verification_log_path,
        projection.manual_agent_handoff_path,
        projection.manual_agent_result_path,
    ):
        if value:
            paths.append(_display_path(root, value))
    return _dedupe(paths)


def _display_path(root: Path, value: str) -> str:
    path = Path(value)
    if path.is_absolute():
        return relative_path(root, path)
    return value


def _task_command(action: str, task_id: str, project_id: str | None, *, suffix: str | None = None) -> str:
    command = f"devflow task {action} {task_id}"
    if project_id:
        command = f"{command} --project {project_id}"
    if suffix:
        command = f"{command} {suffix}"
    return command


def _scope_task_command(command: str, project_id: str | None) -> str:
    if not project_id or " --project " in command or not command.startswith("devflow task "):
        return command
    before_separator, separator, after_separator = command.partition(" -- ")
    parts = before_separator.split(maxsplit=4)
    if len(parts) < 4:
        scoped = f"{before_separator} --project {project_id}"
    else:
        prefix = " ".join(parts[:4])
        rest = parts[4] if len(parts) == 5 else ""
        scoped = f"{prefix} --project {project_id}"
        if rest:
            scoped = f"{scoped} {rest}"
    if separator:
        return f"{scoped}{separator}{after_separator}"
    return scoped


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result
