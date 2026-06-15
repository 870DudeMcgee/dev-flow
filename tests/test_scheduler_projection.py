from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

from typer.testing import CliRunner

from devflow.cli import app
from devflow.control_room.persistence import get_task, save_task, utc_now
from devflow.control_room.scheduler_projection import (
    build_scheduler_snapshot,
    request_scheduler_retry,
)
from tests.helpers import setup_temp_git_repo


runner = CliRunner()


def _init_goal(tmp_path: Path, monkeypatch) -> None:
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    brief = tmp_path / "goal.md"
    brief.write_text("## Goal Brief\nCoordinate parallel work.\n", encoding="utf-8")
    result = runner.invoke(app, ["goal", "init", "--from", str(brief)])
    assert result.exit_code == 0, result.output


def _write_slices(root: Path, text: str) -> None:
    path = root / ".devflow" / "goals" / "G-0001" / "task-slices.yaml"
    path.write_text(text.lstrip(), encoding="utf-8")


def _task(root: Path, task_id: str):
    return get_task(root, task_id)


def test_scheduler_snapshot_projects_ready_batches_and_dependency_blockers(tmp_path: Path, monkeypatch) -> None:
    _init_goal(tmp_path, monkeypatch)
    _write_slices(
        tmp_path,
        """
        task_slices:
          - task_id: TS-0001
            title: First ready lane
            parallel_safe: true
            shared_files: [src/a.py]
            risk: low
            execution_mode: AFK
          - task_id: TS-0002
            title: Second ready lane
            parallel_safe: true
            shared_files: [src/b.py]
            risk: low
            execution_mode: AFK
          - task_id: TS-0003
            title: Blocked lane
            blocked_by: [TS-0001]
            parallel_safe: true
            shared_files: [src/c.py]
            risk: medium
            execution_mode: HITL
        """,
    )

    snapshot = build_scheduler_snapshot(tmp_path)
    payload = snapshot.model_dump(mode="json")

    assert payload["counts"]["ready"] == 2
    assert payload["counts"]["blocked"] == 1
    assert payload["status"] == "ready"
    assert payload["batches"][0]["batch_type"] == "task_creation"
    assert payload["batches"][0]["batch_id"] == "PB-0001"
    assert payload["batches"][0]["lane_ids"] == ["TS-0001", "TS-0002"]
    assert payload["blocked_dependencies"][0]["lane_id"] == "TS-0003"
    assert payload["blocked_dependencies"][0]["blocked_by"] == ["TS-0001"]
    assert payload["next_safe_action"] == "devflow freshness create-batch G-0001 PB-0001"


def test_scheduler_snapshot_marks_running_task_stale_from_passive_timestamp(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _init_goal(tmp_path, monkeypatch)
    create = runner.invoke(app, ["task", "create", "stale runner"])
    assert create.exit_code == 0, create.output

    task = _task(tmp_path, "task-0001")
    now = utc_now()
    task.status = "running"
    task.started_at = now - timedelta(seconds=900)
    task.updated_at = task.started_at
    task.timeout_seconds = 60
    save_task(tmp_path / ".devflow" / "tasks" / task.id, task)

    snapshot = build_scheduler_snapshot(tmp_path)
    stale = [item for item in snapshot.tasks if item.task_id == "task-0001"][0]

    assert stale.scheduler_state == "stale"
    assert stale.stale is True
    assert stale.next_safe_action == "devflow task show task-0001"
    assert snapshot.counts["stale"] == 1
    assert "task-0001" in snapshot.stale_tasks


def test_scheduler_retry_writes_request_without_clearing_evidence(tmp_path: Path, monkeypatch) -> None:
    _init_goal(tmp_path, monkeypatch)
    create = runner.invoke(app, ["task", "create", "needs retry"])
    assert create.exit_code == 0, create.output

    task = _task(tmp_path, "task-0001")
    task.status = "verification_failed"
    task.verification_status = "failed"
    task.verification_command = "pytest tests/test_retry.py"
    save_task(tmp_path / ".devflow" / "tasks" / task.id, task)

    request = request_scheduler_retry(tmp_path, "task-0001", reason="rerun focused test after repair")

    path = tmp_path / request.retry_request_path
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["task_id"] == "task-0001"
    assert payload["reason"] == "rerun focused test after repair"
    assert payload["previous_status"] == "verification_failed"
    assert payload["previous_verification_status"] == "failed"
    assert payload["recommended_next_command"] == "devflow task next-action task-0001"

    unchanged = _task(tmp_path, "task-0001")
    assert unchanged.status == "verification_failed"
    assert unchanged.verification_status == "failed"
    assert unchanged.verification_command == "pytest tests/test_retry.py"
    events = (tmp_path / ".devflow/tasks/task-0001/events.jsonl").read_text(encoding="utf-8")
    assert "retry_requested" in events


def test_scheduler_cli_status_and_retry_json(tmp_path: Path, monkeypatch) -> None:
    _init_goal(tmp_path, monkeypatch)
    create = runner.invoke(app, ["task", "create", "cli retry"])
    assert create.exit_code == 0, create.output
    task = _task(tmp_path, "task-0001")
    task.status = "worker_failed"
    save_task(tmp_path / ".devflow" / "tasks" / task.id, task)

    status = runner.invoke(app, ["scheduler", "status", "--json"])
    assert status.exit_code == 0, status.output
    status_payload = json.loads(status.output)
    assert status_payload["counts"]["needs_retry"] == 1

    retry = runner.invoke(app, ["scheduler", "retry", "task-0001", "--reason", "worker failed", "--json"])
    assert retry.exit_code == 0, retry.output
    retry_payload = json.loads(retry.output)
    assert retry_payload["task_id"] == "task-0001"
    assert retry_payload["retry_request_path"] == ".devflow/tasks/task-0001/retry-request.json"
