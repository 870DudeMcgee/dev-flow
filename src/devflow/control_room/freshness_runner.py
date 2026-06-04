from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import subprocess
from typing import Literal

from pydantic import BaseModel, Field

from devflow.control_room.freshness import FreshnessReport, run_freshness_loop
from devflow.control_room.goal_loop import GoalParallelBatch
from devflow.control_room.parallel_task_creation import ParallelTaskCreationRun, run_parallel_task_creation_batch
from devflow.control_room.parallel_verification import ParallelVerificationRun, run_parallel_verification_batch
from devflow.control_room.parallel_worker import ParallelWorkerRun, run_parallel_worker_batch
from devflow.control_room.paths import devflow_dir, relative_path
from devflow.control_room.persistence import atomic_write_text


BoundedFreshnessRunStatus = Literal[
    "stable",
    "max_iterations_reached",
    "git_action_required",
    "needs_human_decision",
    "worker_failed",
    "verification_failed",
]


class BoundedFreshnessIteration(BaseModel):
    iteration: int
    status: str
    state_hash: str
    loop_start_git_action: str
    next_action: str
    task_creation_run: ParallelTaskCreationRun | None = None
    worker_run: ParallelWorkerRun | None = None
    verification_run: ParallelVerificationRun | None = None


class BoundedFreshnessRun(BaseModel):
    schema_version: int = 1
    run_id: str
    status: BoundedFreshnessRunStatus
    max_iterations: int
    create_tasks: bool
    execute_workers: bool
    execute_verification: bool
    max_parallel: int
    started_at: str
    finished_at: str
    iterations: list[BoundedFreshnessIteration] = Field(default_factory=list)
    report_path: str | None = None
    next_action: str


def run_bounded_freshness_control(
    root: Path,
    *,
    max_iterations: int = 3,
    create_tasks: bool = False,
    execute_workers: bool = False,
    execute_verification: bool = False,
    max_parallel: int = 4,
    timeout_seconds: int = 120,
    write_report: bool = True,
) -> BoundedFreshnessRun:
    """Run bounded PLC-style freshness iterations, dispatching verification only when requested."""
    if max_iterations < 1:
        raise ValueError("max_iterations must be at least 1.")
    if max_parallel < 1:
        raise ValueError("max_parallel must be at least 1.")

    started_at = _now()
    previous_hash: str | None = None
    iterations: list[BoundedFreshnessIteration] = []
    status: BoundedFreshnessRunStatus = "max_iterations_reached"
    next_action = "Re-run the bounded control loop or inspect the latest freshness snapshot."

    for index in range(1, max_iterations + 1):
        report = run_freshness_loop(root, write_snapshot=True)
        verification_run = None
        iteration = BoundedFreshnessIteration(
            iteration=index,
            status=report.status,
            state_hash=report.state_hash,
            loop_start_git_action=report.loop_start_git.recommended_action,
            next_action=report.next_action,
        )

        if report.status == "needs_human_decision":
            iterations.append(iteration)
            status = "needs_human_decision"
            next_action = report.next_action
            break

        if report.loop_start_git.recommended_action != "continue_loop" and not _only_loop_artifact_changes(root):
            iterations.append(iteration)
            status = "git_action_required"
            next_action = report.loop_start_git.command or report.loop_start_git.reason
            break

        if create_tasks:
            task_batch = _first_parallel_batch(report)
            if task_batch is not None:
                task_creation_run = run_parallel_task_creation_batch(root, task_batch.goal_id, task_batch.batch, write_report=True)
                iteration = iteration.model_copy(update={"task_creation_run": task_creation_run})
                iterations.append(iteration)
                previous_hash = None
                continue

        if execute_workers:
            worker_batch = _first_worker_batch(report)
            if worker_batch is not None:
                worker_run = run_parallel_worker_batch(
                    root,
                    worker_batch,
                    max_parallel=max_parallel,
                    timeout_seconds=timeout_seconds,
                )
                iteration = iteration.model_copy(update={"worker_run": worker_run})
                iterations.append(iteration)
                if worker_run.status == "failed":
                    status = "worker_failed"
                    next_action = "Inspect failed task worker logs and rerun the relevant projected worker batch after repair."
                    break
                previous_hash = None
                continue

        if execute_verification:
            batch = _first_verification_batch(report)
            if batch is not None:
                verification_run = run_parallel_verification_batch(
                    root,
                    batch,
                    max_parallel=max_parallel,
                    timeout_seconds=timeout_seconds,
                )
                iteration = iteration.model_copy(update={"verification_run": verification_run})
                iterations.append(iteration)
                if verification_run.status == "failed":
                    status = "verification_failed"
                    next_action = "Inspect failed task verification logs and rerun the relevant projected batch after repair."
                    break
                previous_hash = None
                continue

        iterations.append(iteration)
        if previous_hash == report.state_hash:
            status = "stable"
            next_action = report.next_action
            break
        previous_hash = report.state_hash

    finished_at = _now()
    run = BoundedFreshnessRun(
        run_id=_run_id(started_at),
        status=status,
        max_iterations=max_iterations,
        create_tasks=create_tasks,
        execute_workers=execute_workers,
        execute_verification=execute_verification,
        max_parallel=max_parallel,
        started_at=started_at,
        finished_at=finished_at,
        iterations=iterations,
        next_action=next_action,
    )
    return _write_report(root, run) if write_report else run


def render_bounded_freshness_run(run: BoundedFreshnessRun) -> str:
    lines = [
        "Bounded Freshness Control Run",
        "",
        f"Status: {run.status}",
        f"Iterations: {len(run.iterations)}/{run.max_iterations}",
        f"Create tasks: {'yes' if run.create_tasks else 'no'}",
        f"Execute workers: {'yes' if run.execute_workers else 'no'}",
        f"Execute verification: {'yes' if run.execute_verification else 'no'}",
        f"Max parallel: {run.max_parallel}",
    ]
    if run.report_path:
        lines.append(f"Report: {run.report_path}")
    lines.extend(["", "Iterations"])
    for iteration in run.iterations:
        lines.append(
            f"  - {iteration.iteration}: {iteration.status}, git={iteration.loop_start_git_action}, "
            f"hash={iteration.state_hash}"
        )
        if iteration.verification_run is not None:
            lines.append(
                f"    verification: {iteration.verification_run.batch_id} "
                f"{iteration.verification_run.status} ({iteration.verification_run.task_count} tasks)"
            )
        if iteration.task_creation_run is not None:
            lines.append(
                f"    task creation: {iteration.task_creation_run.batch_id} "
                f"{iteration.task_creation_run.status} ({iteration.task_creation_run.created_task_count} tasks)"
            )
        if iteration.worker_run is not None:
            lines.append(
                f"    worker: {iteration.worker_run.batch_id} "
                f"{iteration.worker_run.status} ({iteration.worker_run.task_count} tasks)"
            )
    lines.extend(["", "Next Action", f"  {run.next_action}"])
    return "\n".join(lines) + "\n"


def _first_verification_batch(report: FreshnessReport):
    for goal in report.goal_loop:
        if goal.verification_batches:
            return goal.verification_batches[0]
    return None


def _first_worker_batch(report: FreshnessReport):
    for goal in report.goal_loop:
        if goal.worker_batches:
            return goal.worker_batches[0]
    return None


class _SelectedParallelBatch(BaseModel):
    goal_id: str
    batch: GoalParallelBatch


def _first_parallel_batch(report: FreshnessReport) -> _SelectedParallelBatch | None:
    for goal in report.goal_loop:
        if goal.parallel_batches:
            return _SelectedParallelBatch(goal_id=goal.goal_id, batch=goal.parallel_batches[0])
    return None


def _write_report(root: Path, run: BoundedFreshnessRun) -> BoundedFreshnessRun:
    report_path = devflow_dir(root) / "freshness" / "control-runs" / f"{run.run_id}.json"
    updated = run.model_copy(update={"report_path": relative_path(root, report_path)})
    atomic_write_text(report_path, updated.model_dump_json(indent=2) + "\n")
    return updated


def only_loop_artifact_changes(root: Path) -> bool:
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain=v1"],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError:
        return False
    if result.returncode != 0:
        return False

    changed_paths = [
        line[3:].strip()
        for line in result.stdout.splitlines()
        if len(line) >= 4 and line[3:].strip()
    ]
    return bool(changed_paths) and all(_is_loop_artifact_path(path) for path in changed_paths)


def _only_loop_artifact_changes(root: Path) -> bool:
    return only_loop_artifact_changes(root)


def _is_loop_artifact_path(path: str) -> bool:
    normalized = path.strip('"')
    return normalized.startswith(".devflow/freshness/") or (
        normalized.startswith(".devflow/goals/") and normalized.endswith("/loop-state.json")
    )


def _run_id(timestamp: str) -> str:
    compact = timestamp.replace("-", "").replace(":", "").replace(".", "").replace("+", "Z")
    return f"freshness-control-{compact}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
