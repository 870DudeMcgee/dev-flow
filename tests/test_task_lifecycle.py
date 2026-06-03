from __future__ import annotations

import json
from pathlib import Path

from devflow.control_room.persistence import get_task, utc_now
from devflow.control_room.service import create_task, verify_task
from devflow.control_room.task_lifecycle import (
    invalidate_verification_after_workspace_mutation,
    record_task_update,
)


def _events(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_lifecycle_update_writes_task_event_summary_and_readiness(tmp_path: Path) -> None:
    task = create_task(tmp_path, "lifecycle state")

    record_task_update(
        tmp_path,
        task,
        event_type="worker_finished",
        event_payload={"status": "complete", "exit_code": 0, "log_path": ".devflow/tasks/task-0001/logs/worker.log"},
        status="complete",
        updated_at=utc_now(),
    )

    task_path = tmp_path / ".devflow/tasks" / task.id
    loaded = get_task(tmp_path, task.id)
    events = _events(task_path / "events.jsonl")
    summary = json.loads((task_path / "summary.json").read_text(encoding="utf-8"))
    readiness = json.loads((task_path / "merge-readiness.json").read_text(encoding="utf-8"))

    assert loaded.status == "complete"
    assert events[-1]["event"] == "worker_finished"
    assert summary["status"] == "complete"
    assert summary["merge_ready"] is False
    assert readiness["ready"] is False
    assert readiness["verification_status"] == "not_run"
    assert "verification status is 'not_run', expected 'passed'" in readiness["reasons"]


def test_lifecycle_patch_invalidation_resets_verification_and_readiness(tmp_path: Path) -> None:
    task = create_task(tmp_path, "lifecycle patch invalidation")
    task = verify_task(tmp_path, task.id, ["/bin/sh", "-c", "true"])
    assert task.status == "verified"
    assert task.verification_status == "passed"

    task_path = tmp_path / ".devflow/tasks" / task.id
    patch_application = {"patch_hash": "abc123", "applied_at": "2026-06-02T00:00:00+00:00"}

    updated = invalidate_verification_after_workspace_mutation(tmp_path, task, patch_application=patch_application)
    verification = json.loads((task_path / "verification.json").read_text(encoding="utf-8"))
    readiness = json.loads((task_path / "merge-readiness.json").read_text(encoding="utf-8"))

    assert updated.status == "complete"
    assert updated.verification_status == "not_run"
    assert updated.verification_exit_code is None
    assert verification["status"] == "not_run"
    assert verification["task_status"] == "complete"
    assert verification["invalidated_by_patch_hash"] == "abc123"
    assert readiness["ready"] is False
    assert "verification status is 'not_run', expected 'passed'" in readiness["reasons"]
