from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from devflow.control_room.control_room_doctor import run_control_room_doctor
from devflow.control_room.task_creation import create_control_room_task


def _failed_checks(checks: list[tuple[str, bool, str]]) -> dict[str, str]:
    return {name: detail for name, ok, detail in checks if not ok}


def test_run_control_room_doctor_reports_non_strict_baseline_checks(tmp_path: Path) -> None:
    task = create_control_room_task(tmp_path, "baseline doctor")

    checks = run_control_room_doctor(tmp_path)
    names = [name for name, _, _ in checks]

    assert names[:6] == [
        "runtime directory",
        "config",
        "system directory",
        "system events",
        "tasks directory",
        "workspaces directory",
    ]
    assert "seed contract" in names
    assert f"{task.id} task.yaml" in names
    assert f"{task.id} baseline artifacts" in names
    assert not any(name.startswith("strict:") for name in names)


def test_run_control_room_doctor_reports_strict_task_artifact_failures(tmp_path: Path) -> None:
    task = create_control_room_task(tmp_path, "strict artifact gaps")
    task_path = tmp_path / ".devflow" / "tasks" / task.id
    task_yaml = task_path / "task.yaml"
    task_yaml.write_text(
        task_yaml.read_text(encoding="utf-8").replace(
            f'workspace: ".devflow/workspaces/{task.id}"',
            f'workspace: "{tmp_path.as_posix()}"',
        ),
        encoding="utf-8",
    )
    (task_path / "summary.json").write_text('{"task_id":"wrong-task","status":"created"}\n', encoding="utf-8")
    (task_path / "merge-readiness.json").write_text("not json\n", encoding="utf-8")
    (task_path / "logs" / "verify.log").unlink()

    lock_dir = task_path / ".lock"
    lock_dir.mkdir()
    acquired_at = datetime.now(timezone.utc) - timedelta(hours=2)
    (lock_dir / "owner.json").write_text(
        json.dumps(
            {
                "task_id": task.id,
                "operation": "verify",
                "pid": 1,
                "host": "old-host",
                "acquired_at": acquired_at.isoformat(),
            }
        )
        + "\n",
        encoding="utf-8",
    )

    failed = _failed_checks(run_control_room_doctor(tmp_path, strict=True))

    assert failed[f"strict: {task.id} workspace path"] == f"expected .devflow/workspaces/{task.id}"
    assert "task_id does not match" in failed[f"strict: {task.id} summary.json"]
    assert "invalid JSON" in failed[f"strict: {task.id} merge-readiness.json"]
    assert failed[f"strict: {task.id} verify.log"] == str(task_path / "logs" / "verify.log")
    assert "stale lock" in failed[f"strict: {task.id} task lock"]


def test_run_control_room_doctor_reports_strict_manual_agent_evidence_failures(tmp_path: Path) -> None:
    task = create_control_room_task(tmp_path, "manual evidence gaps")
    task_path = tmp_path / ".devflow" / "tasks" / task.id
    agent_id = "devflow-manual-codex-worker"
    agent_dir = task_path / "agents" / agent_id
    agent_dir.mkdir(parents=True)
    (agent_dir / "worker_failed.json").write_text("not json\n", encoding="utf-8")
    (agent_dir / "questions.jsonl").write_text("{bad json}\n", encoding="utf-8")

    failed = _failed_checks(run_control_room_doctor(tmp_path, strict=True))

    assert "invalid JSON" in failed[f"strict: {task.id} {agent_id} worker_failed.json"]
    assert "line 1: invalid JSON" in failed[f"strict: {task.id} {agent_id} questions.jsonl"]


def test_run_control_room_doctor_reports_promoted_task_consistency(tmp_path: Path) -> None:
    task = create_control_room_task(tmp_path, "promoted consistency")
    task_path = tmp_path / ".devflow" / "tasks" / task.id
    task_yaml = task_path / "task.yaml"
    task_yaml.write_text(
        task_yaml.read_text(encoding="utf-8").replace('status: "created"', 'status: "promoted"'),
        encoding="utf-8",
    )

    failed = _failed_checks(run_control_room_doctor(tmp_path, strict=True))

    assert failed[f"strict: {task.id} promoted consistency"] == "missing task_promoted event"
