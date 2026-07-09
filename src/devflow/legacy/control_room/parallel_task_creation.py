from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from devflow.legacy.control_room.freshness import run_freshness_loop
from devflow.legacy.control_room.goal_loop import GoalParallelBatch
from devflow.legacy.control_room.goal_tasks import create_task_from_goal_slice
from devflow.legacy.control_room.paths import devflow_dir, relative_path
from devflow.legacy.control_room.persistence import atomic_write_text


ParallelTaskCreationStatus = Literal["created", "no_lanes"]


class ParallelTaskCreationItem(BaseModel):
    lane_id: str
    task_id: str
    task_path: str
    status: str


class ParallelTaskCreationRun(BaseModel):
    schema_version: int = 1
    run_id: str
    goal_id: str
    batch_id: str
    status: ParallelTaskCreationStatus
    lane_count: int
    created_task_count: int
    started_at: str
    finished_at: str
    results: list[ParallelTaskCreationItem] = Field(default_factory=list)
    report_path: str | None = None


class ParallelTaskCreationSelectionError(ValueError):
    pass


def run_projected_task_creation_batch(
    root: Path,
    goal_id: str,
    batch_id: str,
    *,
    write_report: bool = True,
) -> ParallelTaskCreationRun:
    """Create tasks for one currently projected conflict-safe parallel batch."""
    from devflow.legacy.control_room.freshness_runner import only_loop_artifact_changes

    report = run_freshness_loop(root, write_snapshot=True)
    if report.status == "needs_human_decision":
        raise ParallelTaskCreationSelectionError(
            "Freshness loop needs a human decision before task creation dispatch. "
            f"Next action: {report.next_action}"
        )
    if report.loop_start_git.recommended_action != "continue_loop" and not only_loop_artifact_changes(root):
        raise ParallelTaskCreationSelectionError(
            "Git action is required before task creation dispatch. "
            f"Next action: {report.loop_start_git.command or report.loop_start_git.reason}"
        )

    for goal in report.goal_loop:
        if goal.goal_id != goal_id:
            continue
        for batch in goal.parallel_batches:
            if batch.batch_id == batch_id:
                return run_parallel_task_creation_batch(root, goal_id, batch, write_report=write_report)
        available = ", ".join(batch.batch_id for batch in goal.parallel_batches) or "none"
        raise ParallelTaskCreationSelectionError(
            f"Parallel task batch {batch_id!r} is not projected for goal {goal_id!r}. Available batches: {available}."
        )

    available_goals = ", ".join(goal.goal_id for goal in report.goal_loop) or "none"
    raise ParallelTaskCreationSelectionError(
        f"Goal {goal_id!r} is not projected by the freshness loop. Available goals: {available_goals}."
    )


def run_parallel_task_creation_batch(
    root: Path,
    goal_id: str,
    batch: GoalParallelBatch,
    *,
    write_report: bool = True,
) -> ParallelTaskCreationRun:
    started_at = _now()
    results: list[ParallelTaskCreationItem] = []
    for lane_id in batch.lane_ids:
        created = create_task_from_goal_slice(root, goal_id, lane_id)
        results.append(
            ParallelTaskCreationItem(
                lane_id=lane_id,
                task_id=created.task_id,
                task_path=created.task_path,
                status="created",
            )
        )

    run = ParallelTaskCreationRun(
        run_id=_run_id(started_at, batch.batch_id),
        goal_id=goal_id,
        batch_id=batch.batch_id,
        status="created" if results else "no_lanes",
        lane_count=len(batch.lane_ids),
        created_task_count=len(results),
        started_at=started_at,
        finished_at=_now(),
        results=results,
    )
    return _write_report(root, run) if write_report else run


def render_parallel_task_creation_run(run: ParallelTaskCreationRun) -> str:
    lines = [
        f"Parallel task batch: {run.batch_id}",
        f"Goal: {run.goal_id}",
        f"Status: {run.status}",
        f"Lanes: {run.lane_count}",
        f"Created tasks: {run.created_task_count}",
    ]
    if run.report_path:
        lines.append(f"Report: {run.report_path}")
    lines.append("")
    for result in run.results:
        lines.append(f"- {result.lane_id}: {result.task_id} ({result.task_path})")
    return "\n".join(lines) + "\n"


def _write_report(root: Path, run: ParallelTaskCreationRun) -> ParallelTaskCreationRun:
    report_path = devflow_dir(root) / "freshness" / "task-batch-runs" / f"{run.run_id}.json"
    updated = run.model_copy(update={"report_path": relative_path(root, report_path)})
    atomic_write_text(report_path, updated.model_dump_json(indent=2) + "\n")
    return updated


def _run_id(timestamp: str, batch_id: str) -> str:
    compact = timestamp.replace("-", "").replace(":", "").replace(".", "").replace("+", "Z")
    return f"parallel-task-{batch_id.lower()}-{compact}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
