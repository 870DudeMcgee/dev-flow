from __future__ import annotations

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from devflow.control_room.goal_loop import GoalVerificationBatch, GoalVerificationItem
from devflow.control_room.paths import devflow_dir, relative_path
from devflow.control_room.persistence import atomic_write_text
from devflow.control_room.service import verify_task


ParallelVerificationStatus = Literal["passed", "failed", "no_commands"]


class ParallelVerificationTaskResult(BaseModel):
    task_id: str
    lane_ids: list[str] = Field(default_factory=list)
    commands: list[str] = Field(default_factory=list)
    combined_command: str
    status: str
    exit_code: int | None = None
    verification_log_path: str | None = None
    started_at: str
    finished_at: str
    error: str | None = None


class ParallelVerificationRun(BaseModel):
    schema_version: int = 1
    run_id: str
    batch_id: str
    status: ParallelVerificationStatus
    max_parallel: int
    task_count: int
    command_count: int
    started_at: str
    finished_at: str
    results: list[ParallelVerificationTaskResult] = Field(default_factory=list)
    report_path: str | None = None


def run_parallel_verification_batch(
    root: Path,
    batch: GoalVerificationBatch,
    *,
    max_parallel: int = 4,
    timeout_seconds: int = 120,
    write_report: bool = True,
) -> ParallelVerificationRun:
    """Run one projected verification batch with task-grained parallelism."""
    if max_parallel < 1:
        raise ValueError("max_parallel must be at least 1.")

    started_at = _now()
    grouped = _group_items_by_task(batch.items)
    if not grouped:
        run = ParallelVerificationRun(
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
    results: list[ParallelVerificationTaskResult] = []
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {
            executor.submit(_run_task_group, root, task_id, items, timeout_seconds): task_id
            for task_id, items in grouped.items()
        }
        for future in as_completed(futures):
            results.append(future.result())

    results.sort(key=lambda item: item.task_id)
    finished_at = _now()
    run = ParallelVerificationRun(
        run_id=_run_id(started_at, batch.batch_id),
        batch_id=batch.batch_id,
        status="passed" if all(item.status == "passed" for item in results) else "failed",
        max_parallel=worker_count,
        task_count=len(grouped),
        command_count=sum(len(item.commands) for item in results),
        started_at=started_at,
        finished_at=finished_at,
        results=results,
    )
    return _write_report(root, run) if write_report else run


def _group_items_by_task(items: list[GoalVerificationItem]) -> dict[str, list[GoalVerificationItem]]:
    grouped: dict[str, list[GoalVerificationItem]] = defaultdict(list)
    for item in items:
        if item.task_id and item.command.strip():
            grouped[item.task_id].append(item)
    return dict(grouped)


def _run_task_group(
    root: Path,
    task_id: str,
    items: list[GoalVerificationItem],
    timeout_seconds: int,
) -> ParallelVerificationTaskResult:
    started_at = _now()
    commands = [item.command for item in items]
    combined_command = _combined_shell_command(commands)
    try:
        task = verify_task(
            root,
            task_id,
            ["/bin/sh", "-c", combined_command],
            timeout_seconds=timeout_seconds,
        )
        return ParallelVerificationTaskResult(
            task_id=task_id,
            lane_ids=_dedupe([item.lane_id for item in items]),
            commands=commands,
            combined_command=combined_command,
            status=task.verification_status,
            exit_code=task.verification_exit_code,
            verification_log_path=task.verification_log_path,
            started_at=started_at,
            finished_at=_now(),
        )
    except Exception as exc:
        return ParallelVerificationTaskResult(
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


def _write_report(root: Path, run: ParallelVerificationRun) -> ParallelVerificationRun:
    report_path = _report_path(root, run.run_id)
    updated = run.model_copy(update={"report_path": relative_path(root, report_path)})
    atomic_write_text(report_path, updated.model_dump_json(indent=2) + "\n")
    return updated


def _report_path(root: Path, run_id: str) -> Path:
    return devflow_dir(root) / "freshness" / "verification-runs" / f"{run_id}.json"


def _run_id(timestamp: str, batch_id: str) -> str:
    compact = timestamp.replace("-", "").replace(":", "").replace(".", "").replace("+", "Z")
    return f"parallel-verify-{batch_id.lower()}-{compact}"


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
