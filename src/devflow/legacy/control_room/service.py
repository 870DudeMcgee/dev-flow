from __future__ import annotations

from pathlib import Path
from typing import Any

from devflow.legacy.control_room.models import TaskRecord
from devflow.legacy.control_room.locks import task_mutation_lock
from devflow.legacy.control_room.control_room_doctor import run_control_room_doctor
from devflow.legacy.control_room.paths import (
    absolute_path,
    relative_path,
)
from devflow.legacy.control_room.git_worktree import (
    GitWorktreeError,
    build_git_promotion_preview,
    git_worktree_readiness_errors,
)
from devflow.legacy.control_room.persistence import (
    get_task,
    list_tasks,
    load_task,
    timestamp,
    utc_now,
)
from devflow.legacy.control_room.promotion import (
    _get_relative_files,
    format_stale_baseline_refusal,
    main_checkout_has_uncommitted_changes,
    promotion_baseline,
)
from devflow.legacy.control_room.readiness import format_promotion_refusal, promotion_readiness_errors
from devflow.legacy.control_room.task_creation import (
    create_control_room_task,
    initialize_control_room,
)
from devflow.legacy.control_room.task_lifecycle import (
    append_task_event,
    record_task_update,
)
from devflow.legacy.control_room.task_artifacts import ensure_task_baseline_artifacts
from devflow.legacy.control_room.task_patch_application import apply_task_patch_command
from devflow.legacy.control_room.task_verification import verify_task_command
from devflow.legacy.control_room.task_local_worker_run import run_task_local_worker
from devflow.legacy.control_room.task_worker_run import run_task_worker
from devflow.legacy.control_room.local_ollama_worker import LocalOllamaRunResult

# Dynamic compatibility shims and mappings
_load_task = load_task
_append_event = append_task_event
_relative = relative_path
_absolute = absolute_path


def preview_task_promotion(root: Path, task_id: str) -> dict[str, Any]:
    import devflow.legacy.control_room.promotion as promotion
    # Forward monkeypatch if service._get_relative_files was overridden in a test
    if _get_relative_files is not promotion._get_relative_files:
        promotion._get_relative_files = _get_relative_files
    return promotion.preview_task_promotion(root, task_id)


def promote_task(
    root: Path,
    task_id: str,
    force: bool = False,
    apply_deletions: bool = False,
    force_stale_baseline: bool = False,
) -> TaskRecord:
    import devflow.legacy.control_room.promotion as promotion
    # Forward monkeypatch if service._get_relative_files was overridden in a test
    if _get_relative_files is not promotion._get_relative_files:
        promotion._get_relative_files = _get_relative_files
    with task_mutation_lock(root, task_id, "promote"):
        return promotion.promote_task(
            root,
            task_id,
            force=force,
            apply_deletions=apply_deletions,
            force_stale_baseline=force_stale_baseline,
        )



def init_control_room(root: Path, project_seed: Any | None = None) -> None:
    initialize_control_room(root, project_seed=project_seed)


def create_task(
    root: Path,
    title: str,
    git_worktree: bool = False,
    worker_id: str = "shell",
    definition_of_done: str | None = None,
) -> TaskRecord:
    return create_control_room_task(
        root,
        title,
        git_worktree=git_worktree,
        worker_id=worker_id,
        definition_of_done=definition_of_done,
    )



def run_shell_task(
    root: Path,
    task_id: str,
    command: list[str],
    timeout_seconds: int = 60,
    worker_adapter: str = "shell",
    env: dict[str, str] | None = None,
) -> TaskRecord:
    return run_task_worker(
        root,
        task_id,
        command,
        timeout_seconds=timeout_seconds,
        worker_adapter=worker_adapter,
        env=env,
    )


def run_local_model_task(
    root: Path,
    task_id: str,
    worker_name: str,
    *,
    input_worker: str | None = None,
    timeout_seconds: int | None = None,
) -> LocalOllamaRunResult:
    return run_task_local_worker(
        root,
        task_id,
        worker_name,
        input_worker=input_worker,
        timeout_seconds=timeout_seconds,
    )


def verify_task(root: Path, task_id: str, command: list[str], timeout_seconds: int = 120) -> TaskRecord:
    return verify_task_command(root, task_id, command, timeout_seconds=timeout_seconds)


def doctor(root: Path, strict: bool = False) -> list[tuple[str, bool, str]]:
    return run_control_room_doctor(root, strict=strict)


def apply_task_patch(
    root: Path,
    task_id: str,
    agent_id: str | None = None,
    run_id: str | None = None,
) -> TaskRecord:
    return apply_task_patch_command(root, task_id, agent_id=agent_id, run_id=run_id)
