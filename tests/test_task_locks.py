from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from devflow.legacy.control_room.locks import TaskLockError, inspect_task_lock_status, task_mutation_lock
from devflow.legacy.control_room.service import apply_task_patch, create_task, promote_task, run_shell_task, verify_task


def test_task_mutation_lock_writes_owner_metadata_and_cleans_up(tmp_path: Path) -> None:
    task = create_task(tmp_path, "lock metadata")
    lock_dir = tmp_path / ".devflow" / "tasks" / task.id / ".lock"

    with task_mutation_lock(tmp_path, task.id, "test-operation"):
        owner = json.loads((lock_dir / "owner.json").read_text(encoding="utf-8"))
        assert owner["task_id"] == task.id
        assert owner["operation"] == "test-operation"
        assert owner["pid"]
        assert owner["host"]
        assert datetime.fromisoformat(owner["acquired_at"])

    assert not lock_dir.exists()


def test_active_task_lock_blocks_mutating_operations(tmp_path: Path) -> None:
    task = create_task(tmp_path, "active lock")

    with task_mutation_lock(tmp_path, task.id, "existing-run"):
        mutating_calls = [
            lambda: run_shell_task(tmp_path, task.id, ["/bin/sh", "-c", "echo locked"]),
            lambda: verify_task(tmp_path, task.id, ["/bin/sh", "-c", "true"]),
            lambda: apply_task_patch(tmp_path, task.id),
            lambda: promote_task(tmp_path, task.id),
        ]
        for call in mutating_calls:
            with pytest.raises(TaskLockError) as excinfo:
                call()
            message = str(excinfo.value)
            assert f"Task {task.id} is locked by operation 'existing-run'" in message
            assert "pid:" in message
            assert "acquired_at:" in message


def test_stale_task_lock_is_removed_before_mutation(tmp_path: Path) -> None:
    task = create_task(tmp_path, "stale lock")
    lock_dir = tmp_path / ".devflow" / "tasks" / task.id / ".lock"
    lock_dir.mkdir()
    old_time = datetime.now(timezone.utc) - timedelta(hours=2)
    (lock_dir / "owner.json").write_text(
        json.dumps(
            {
                "task_id": task.id,
                "operation": "stale-run",
                "pid": 1,
                "host": "old-host",
                "acquired_at": old_time.isoformat(),
            }
        )
        + "\n",
        encoding="utf-8",
    )

    updated = run_shell_task(tmp_path, task.id, ["/bin/sh", "-c", "echo recovered"])

    assert updated.status == "complete"
    assert "recovered" in (tmp_path / ".devflow" / "tasks" / task.id / "logs" / "worker.log").read_text(
        encoding="utf-8"
    )
    assert not lock_dir.exists()


def test_lock_cleanup_preserves_replaced_owner(tmp_path: Path) -> None:
    task = create_task(tmp_path, "replaced lock")
    lock_dir = tmp_path / ".devflow" / "tasks" / task.id / ".lock"

    with task_mutation_lock(tmp_path, task.id, "original-run"):
        (lock_dir / "owner.json").unlink()
        lock_dir.rmdir()
        lock_dir.mkdir()
        (lock_dir / "owner.json").write_text(
            json.dumps(
                {
                    "task_id": task.id,
                    "operation": "newer-run",
                    "pid": 2,
                    "host": "new-host",
                    "acquired_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            + "\n",
            encoding="utf-8",
        )

    owner = json.loads((lock_dir / "owner.json").read_text(encoding="utf-8"))
    assert owner["operation"] == "newer-run"


def test_inspect_task_lock_status_is_read_only_and_stale_does_not_delete_lock(tmp_path: Path) -> None:
    task = create_task(tmp_path, "inspect-only stale lock")
    lock_dir = tmp_path / ".devflow" / "tasks" / task.id / ".lock"
    lock_dir.mkdir()
    old_time = datetime.now(timezone.utc) - timedelta(hours=2)
    (lock_dir / "owner.json").write_text(
        json.dumps(
            {
                "task_id": task.id,
                "operation": "stale-run",
                "pid": 1,
                "host": "other-host",
                "acquired_at": old_time.isoformat(),
            }
        )
        + "\n",
        encoding="utf-8",
    )

    lock_status = inspect_task_lock_status(tmp_path, task.id)

    assert lock_status is not None
    assert lock_status["status"] == "stale"
    assert lock_status["is_stale"] is True
    assert lock_status["operation"] == "stale-run"
    assert lock_status["host"] == "other-host"
    assert lock_dir.exists()
