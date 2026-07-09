from __future__ import annotations

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from devflow.legacy.control_room.freshness import run_freshness_loop
from devflow.legacy.control_room.goal_loop import GoalWorkerBatch, GoalWorkerItem
from devflow.legacy.control_room.paths import devflow_dir, relative_path
from devflow.legacy.control_room.persistence import atomic_write_text
from devflow.legacy.control_room.service import run_shell_task


ParallelWorkerStatus = Literal["passed", "failed", "no_commands"]


class ParallelWorkerTaskResult(BaseModel):
    task_id: str
    lane_ids: list[str] = Field(default_factory=list)
    commands: list[str] = Field(default_factory=list)
    combined_command: str
    status: str
    exit_code: int | None = None
    worker_log_path: str | None = None
    started_at: str
    finished_at: str
    error: str | None = None


class ParallelWorkerRun(BaseModel):
    schema_version: int = 1
    run_id: str
    batch_id: str
    status: ParallelWorkerStatus
    max_parallel: int
    task_count: int
    command_count: int
    started_at: str
    finished_at: str
    results: list[ParallelWorkerTaskResult] = Field(default_factory=list)
    report_path: str | None = None


class WorkerBatchSelectionError(ValueError):
    pass


def run_projected_worker_batch(
    root: Path,
    goal_id: str,
    batch_id: str,
    *,
    max_parallel: int = 4,
    timeout_seconds: int = 120,
) -> ParallelWorkerRun:
    """Run one currently projected worker batch through shell task isolation."""
    from devflow.legacy.control_room.freshness_runner import only_loop_artifact_changes

    report = run_freshness_loop(root, write_snapshot=True)
    if report.status == "needs_human_decision":
        raise WorkerBatchSelectionError(
            "Freshness loop needs a human decision before worker dispatch. "
            f"Next action: {report.next_action}"
        )
    if report.loop_start_git.recommended_action != "continue_loop" and not only_loop_artifact_changes(root):
        raise WorkerBatchSelectionError(
            "Git action is required before worker dispatch. "
            f"Next action: {report.loop_start_git.command or report.loop_start_git.reason}"
        )

    for goal in report.goal_loop:
        if goal.goal_id != goal_id:
            continue
        for batch in goal.worker_batches:
            if batch.batch_id == batch_id:
                return run_parallel_worker_batch(
                    root,
                    batch,
                    max_parallel=max_parallel,
                    timeout_seconds=timeout_seconds,
                )
        available = ", ".join(batch.batch_id for batch in goal.worker_batches) or "none"
        raise WorkerBatchSelectionError(
            f"Worker batch {batch_id!r} is not projected for goal {goal_id!r}. Available batches: {available}."
        )

    available_goals = ", ".join(goal.goal_id for goal in report.goal_loop) or "none"
    raise WorkerBatchSelectionError(
        f"Goal {goal_id!r} is not projected by the freshness loop. Available goals: {available_goals}."
    )


def run_parallel_worker_batch(
    root: Path,
    batch: GoalWorkerBatch,
    *,
    max_parallel: int = 4,
    timeout_seconds: int = 120,
    write_report: bool = True,
) -> ParallelWorkerRun:
    """Run one projected worker batch with task-grained parallelism."""
    if max_parallel < 1:
        raise ValueError("max_parallel must be at least 1.")

    started_at = _now()
    grouped = _group_items_by_task(batch.items)
    if not grouped:
        run = ParallelWorkerRun(
            run_id=_run_id(started_at, batch.batch_id),
            batch_id=batch.batch_id,
            status="no_commands",
            max_parallel=max_parallel,
            task_count=0,
            command_count=0,
            started_at=started_at,
            finished_at=_now(),
        )
        return _write_report(root, run) if write_report else run

    worker_count = min(max_parallel, len(grouped))
    results: list[ParallelWorkerTaskResult] = []
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {
            executor.submit(_run_task_group, root, task_id, items, timeout_seconds): task_id
            for task_id, items in grouped.items()
        }
        for future in as_completed(futures):
            results.append(future.result())

    results.sort(key=lambda item: item.task_id)
    run = ParallelWorkerRun(
        run_id=_run_id(started_at, batch.batch_id),
        batch_id=batch.batch_id,
        status="passed" if all(item.status == "complete" for item in results) else "failed",
        max_parallel=worker_count,
        task_count=len(grouped),
        command_count=sum(len(item.commands) for item in results),
        started_at=started_at,
        finished_at=_now(),
        results=results,
    )
    return _write_report(root, run) if write_report else run


def render_parallel_worker_run(run: ParallelWorkerRun) -> str:
    lines = [
        f"Worker batch: {run.batch_id}",
        f"Status: {run.status}",
        f"Max parallel: {run.max_parallel}",
        f"Tasks: {run.task_count}",
        f"Commands: {run.command_count}",
    ]
    if run.report_path:
        lines.append(f"Report: {run.report_path}")
    lines.append("")
    for result in run.results:
        exit_code = "unknown" if result.exit_code is None else str(result.exit_code)
        lines.append(f"- {result.task_id}: {result.status} (exit {exit_code})")
        if result.worker_log_path:
            lines.append(f"  log: {result.worker_log_path}")
        if result.error:
            lines.append(f"  error: {result.error}")
    return "\n".join(lines) + "\n"


def _group_items_by_task(items: list[GoalWorkerItem]) -> dict[str, list[GoalWorkerItem]]:
    grouped: dict[str, list[GoalWorkerItem]] = defaultdict(list)
    for item in items:
        if item.task_id and item.command.strip():
            grouped[item.task_id].append(item)
    return dict(grouped)


def _run_task_group(
    root: Path,
    task_id: str,
    items: list[GoalWorkerItem],
    timeout_seconds: int,
) -> ParallelWorkerTaskResult:
    started_at = _now()
    commands = [item.command for item in items]
    combined_command = _combined_shell_command(commands)
    try:
        task = run_shell_task(
            root,
            task_id,
            ["/bin/sh", "-c", combined_command],
            timeout_seconds=timeout_seconds,
            worker_adapter="shell",
        )
        return ParallelWorkerTaskResult(
            task_id=task_id,
            lane_ids=_dedupe([item.lane_id for item in items]),
            commands=commands,
            combined_command=combined_command,
            status=task.status,
            exit_code=task.last_exit_code,
            worker_log_path=task.log_path,
            started_at=started_at,
            finished_at=_now(),
        )
    except Exception as exc:
        return ParallelWorkerTaskResult(
            task_id=task_id,
            lane_ids=_dedupe([item.lane_id for item in items]),
            commands=commands,
            combined_command=combined_command,
            status="error",
            started_at=started_at,
            finished_at=_now(),
            error=str(exc),
        )


def _combined_shell_command(commands: list[str]) -> str:
    if len(commands) == 1:
        return commands[0]
    lines = ["set -e"]
    lines.extend(f"({command})" for command in commands)
    return "\n".join(lines)


def _write_report(root: Path, run: ParallelWorkerRun) -> ParallelWorkerRun:
    report_path = devflow_dir(root) / "freshness" / "worker-runs" / f"{run.run_id}.json"
    updated = run.model_copy(update={"report_path": relative_path(root, report_path)})
    atomic_write_text(report_path, updated.model_dump_json(indent=2) + "\n")
    return updated


def _run_id(timestamp: str, batch_id: str) -> str:
    compact = timestamp.replace("-", "").replace(":", "").replace(".", "").replace("+", "Z")
    return f"parallel-worker-{batch_id.lower()}-{compact}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result
