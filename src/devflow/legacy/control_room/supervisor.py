from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from time import sleep

from devflow.legacy.control_room.models import TaskRecord
from devflow.legacy.control_room.paths import relative_path, task_dir, workspace_path
from devflow.legacy.control_room.persistence import get_task, list_tasks
from devflow.legacy.control_room.service import run_shell_task


RUNNABLE_STATUSES = {"created"}
DEFAULT_WORKER_COMMAND = "scripts/run-ollama-task"


@dataclass(frozen=True)
class SupervisorCommand:
    task_id: str
    command: list[str]
    env: dict[str, str]


@dataclass(frozen=True)
class SupervisorPollIteration:
    iteration: int
    tasks: list[TaskRecord]


def is_runnable_status(status: str) -> bool:
    return status in RUNNABLE_STATUSES


def select_runnable_tasks(root: Path, task_id: str | None = None) -> list[TaskRecord]:
    tasks = list_tasks(root)
    if task_id is not None:
        tasks = [task for task in tasks if task.id == task_id]
    return [task for task in tasks if is_runnable_status(task.status)]


def build_supervisor_command(
    root: Path,
    task_id: str,
    worker_command: str | Sequence[str] = DEFAULT_WORKER_COMMAND,
) -> SupervisorCommand:
    task = get_task(root, task_id)
    return SupervisorCommand(
        task_id=task.id,
        command=_normalize_worker_command(worker_command),
        env={
            "DEVFLOW_TASK_ID": task.id,
            "DEVFLOW_REPO_ROOT": str(root.resolve()),
            "DEVFLOW_TASK_DIR": relative_path(root, task_dir(root, task.id)),
            "DEVFLOW_WORKSPACE": relative_path(root, workspace_path(root, task.id)),
        },
    )


def supervise_once(
    root: Path,
    task_id: str | None = None,
    worker_command: str | Sequence[str] = DEFAULT_WORKER_COMMAND,
    timeout_seconds: int = 60,
) -> list[TaskRecord]:
    ran_tasks = []
    for task in select_runnable_tasks(root, task_id=task_id):
        supervisor_command = build_supervisor_command(root, task.id, worker_command=worker_command)
        ran_tasks.append(
            run_shell_task(
                root,
                task.id,
                supervisor_command.command,
                timeout_seconds=timeout_seconds,
                env=supervisor_command.env,
            )
        )
    return ran_tasks


def supervise_poll(
    root: Path,
    task_id: str | None = None,
    worker_command: str | Sequence[str] = DEFAULT_WORKER_COMMAND,
    timeout_seconds: int = 60,
    interval_seconds: int = 5,
    max_iterations: int = 12,
) -> list[SupervisorPollIteration]:
    if interval_seconds < 0:
        raise ValueError("Supervisor poll interval cannot be negative.")
    if max_iterations < 1:
        raise ValueError("Supervisor poll max iterations must be at least 1.")

    iterations = []
    for iteration in range(1, max_iterations + 1):
        tasks = supervise_once(
            root,
            task_id=task_id,
            worker_command=worker_command,
            timeout_seconds=timeout_seconds,
        )
        iterations.append(SupervisorPollIteration(iteration=iteration, tasks=tasks))
        if any(task.status != "complete" for task in tasks):
            break
        if iteration < max_iterations and interval_seconds:
            sleep(interval_seconds)
    return iterations


def _normalize_worker_command(worker_command: str | Sequence[str]) -> list[str]:
    if isinstance(worker_command, str):
        command = [worker_command]
    else:
        command = list(worker_command)
    if not command or any(not part for part in command):
        raise ValueError("Supervisor worker command cannot be empty.")
    return command
