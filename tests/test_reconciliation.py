from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from typer.testing import CliRunner

from devflow.cli import app
from devflow.control_room.paths import system_events_path, task_dir
from devflow.control_room.service import create_task


runner = CliRunner()


def _finding_codes(report: dict) -> set[str]:
    return {finding["code"] for finding in report["findings"]}


def test_reconciliation_report_surfaces_partial_event_write_and_system_divergence(tmp_path: Path) -> None:
    task = create_task(tmp_path, "interrupted event write")
    task_path = task_dir(tmp_path, task.id)

    system_events_path(tmp_path).write_text("", encoding="utf-8")
    with (task_path / "events.jsonl").open("a", encoding="utf-8") as handle:
        handle.write('{"event": "worker_started"')

    from devflow.control_room.reconciliation import build_reconciliation_report

    report = build_reconciliation_report(tmp_path)

    assert report["status"] == "issues_found"
    assert report["tasks_checked"] == 1
    codes = _finding_codes(report)
    assert "partial_task_event_write" in codes
    assert "task_event_log_invalid" in codes
    assert "task_event_missing_from_system" in codes


def test_reconciliation_report_surfaces_interrupted_promotion_and_artifact_inconsistency(tmp_path: Path) -> None:
    task = create_task(tmp_path, "interrupted promotion")
    task_path = task_dir(tmp_path, task.id)
    task_yaml = task_path / "task.yaml"
    task_yaml.write_text(
        task_yaml.read_text(encoding="utf-8").replace('status: "created"', 'status: "promoted"'),
        encoding="utf-8",
    )

    lock_dir = task_path / ".lock"
    lock_dir.mkdir()
    old_time = datetime.now(timezone.utc) - timedelta(hours=2)
    (lock_dir / "owner.json").write_text(
        json.dumps(
            {
                "task_id": task.id,
                "operation": "promote",
                "pid": 1,
                "host": "old-host",
                "acquired_at": old_time.isoformat(),
            }
        )
        + "\n",
        encoding="utf-8",
    )

    (task_path / "summary.json").write_text(
        json.dumps({"task_id": task.id, "status": "complete"}) + "\n",
        encoding="utf-8",
    )
    (task_path / "verification.json").write_text(
        json.dumps({"task_id": "wrong-task", "status": "passed", "task_status": "verified"}) + "\n",
        encoding="utf-8",
    )

    from devflow.control_room.reconciliation import build_reconciliation_report

    report = build_reconciliation_report(tmp_path)

    codes = _finding_codes(report)
    assert "promotion_interrupted_lock" in codes
    assert "promotion_status_missing_event" in codes
    assert "promotion_verification_inconsistent" in codes
    assert "artifact_inconsistent" in codes


def test_reconcile_cli_prints_json_and_does_not_mutate_artifacts() -> None:
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            created = runner.invoke(app, ["task", "create", "readonly reconcile"])
            assert created.exit_code == 0, created.output

            Path(".devflow/system/events.jsonl").write_text("", encoding="utf-8")
            before = {path: path.read_bytes() for path in Path(".devflow").glob("**/*") if path.is_file()}

            result = runner.invoke(app, ["reconcile", "--json"])

            assert result.exit_code == 1, result.output
            report = json.loads(result.output)
            assert report["status"] == "issues_found"
            assert "task_event_missing_from_system" in _finding_codes(report)

            after = {path: path.read_bytes() for path in Path(".devflow").glob("**/*") if path.is_file()}
            assert after == before
        finally:
            os.chdir(old_cwd)