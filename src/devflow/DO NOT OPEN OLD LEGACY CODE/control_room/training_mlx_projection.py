from __future__ import annotations

from pathlib import Path

from devflow.legacy.control_room.paths import relative_path
from devflow.legacy.control_room.persistence import get_task, utc_now
from devflow.legacy.control_room.task_lifecycle import record_task_update


def attach_training_run_to_task(root: Path, task_id: str, run_id: str) -> dict[str, object]:
    repo_root = root.resolve()
    task = get_task(repo_root, task_id)
    run_dir = repo_root / ".devflow" / "training" / run_id
    result_path = run_dir / "result.md"
    warnings: list[str] = []

    if not result_path.exists():
        warnings.append(f"missing training result: {relative_path(repo_root, result_path)}")
        return {
            "task_id": task_id,
            "run_id": run_id,
            "result_path": relative_path(repo_root, result_path),
            "log_path": None,
            "attached": False,
            "warnings": warnings,
        }

    task.result_path = relative_path(repo_root, result_path)
    smoke_log = _first_existing_smoke_log(run_dir)
    task.log_path = relative_path(repo_root, smoke_log) if smoke_log is not None else None

    record_task_update(
        repo_root,
        task,
        event_type="training_mlx_attached",
        event_payload={
            "run_id": run_id,
            "result_path": task.result_path,
            "log_path": task.log_path,
        },
        updated_at=utc_now(),
    )
    return {
        "task_id": task_id,
        "run_id": run_id,
        "result_path": task.result_path,
        "log_path": task.log_path,
        "attached": True,
        "warnings": warnings,
    }


def _first_existing_smoke_log(run_dir: Path) -> Path | None:
    for pattern in (
        "**/*-smoke-reload.log",
        "**/lora-smoke.log",
        "**/load-smoke.log",
        "**/*-smoke.log",
    ):
        matches = sorted(run_dir.glob(pattern))
        if matches:
            parent_dirs = {match.parent for match in matches}
            if len(parent_dirs) == 1:
                return matches[0]
            return None
    return None
