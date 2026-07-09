from __future__ import annotations

from pathlib import Path

from devflow.legacy.control_room.git_worktree import (
    is_git_worktree_task,
    refresh_git_worker_evidence,
    worker_id_for_task,
)
from devflow.legacy.control_room.local_ollama_worker import (
    LocalOllamaRunResult,
    get_local_worker_definition,
    run_local_ollama_worker,
)
from devflow.legacy.control_room.locks import task_mutation_lock
from devflow.legacy.control_room.log_sanitizer import DEFAULT_LATEST_LOG_LINE_MAX_CHARS, latest_visible_log_line
from devflow.legacy.control_room.paths import relative_path, task_dir
from devflow.legacy.control_room.persistence import get_task
from devflow.legacy.control_room.task_lifecycle import (
    append_task_event,
    apply_lifecycle_metadata,
    write_task_state,
)
from devflow.legacy.control_room.task_workspace import validated_task_workspace


def run_task_local_worker(
    root: Path,
    task_id: str,
    worker_name: str,
    input_worker: str | None = None,
    timeout_seconds: int | None = None,
) -> LocalOllamaRunResult:
    definition = get_local_worker_definition(worker_name)
    timeout = definition.default_timeout_seconds if timeout_seconds is None else timeout_seconds
    if timeout <= 0:
        raise ValueError("Local worker timeout must be greater than zero.")

    task = get_task(root, task_id)
    task_path = task_dir(root, task_id)
    workspace = validated_task_workspace(root, task)
    task_yaml_text = (task_path / "task.yaml").read_text(encoding="utf-8")

    result = run_local_ollama_worker(
        root,
        task_id,
        workspace,
        worker_name,
        input_worker=input_worker,
        timeout_seconds=timeout,
        task_yaml_text=task_yaml_text,
    )

    with task_mutation_lock(root, task_id, "local-worker"):
        task = get_task(root, task_id)
        task.last_exit_code = result.exit_code
        task.latest_log_line = _local_worker_latest_line(result)
        task.log_path = relative_path(root, result.stderr_path)
        task.result_path = relative_path(root, result.response_path)
        task.finished_at = result.finished_at
        if is_git_worktree_task(task):
            state = refresh_git_worker_evidence(root, task, worker_id=worker_id_for_task(task))
            task.workspace_dirty = bool(state["dirty"])
        apply_lifecycle_metadata(
            task,
            event_type="local_worker_finished",
            status=result.task_status,
            updated_at=task.finished_at,
        )

        append_task_event(
            root,
            task_id,
            "local_worker_started",
            {
                "worker_name": worker_name,
                "model": definition.model,
                "artifact_dir": relative_path(root, result.artifact_dir),
                "input_worker": input_worker or definition.default_input_worker,
                "run_id": result.run_id,
            },
        )
        append_task_event(
            root,
            task_id,
            "local_worker_finished",
            {
                "worker_name": worker_name,
                "model": definition.model,
                "status": result.status,
                "exit_code": result.exit_code,
                "run_id": result.run_id,
                "run_json_path": relative_path(root, result.run_json_path),
                "response_path": relative_path(root, result.response_path),
                "stderr_path": relative_path(root, result.stderr_path),
            },
        )

        write_task_state(root, task)

    return result


def _local_worker_latest_line(result: LocalOllamaRunResult) -> str | None:
    if result.error_message:
        return result.error_message
    if not result.stderr_path.exists():
        return None
    latest = latest_visible_log_line(result.stderr_path, max_chars=DEFAULT_LATEST_LOG_LINE_MAX_CHARS)
    return latest or None
