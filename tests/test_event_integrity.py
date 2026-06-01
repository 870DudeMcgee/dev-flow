from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from typer.testing import CliRunner

from devflow.cli import app
from devflow.control_room.persistence import event_content_hash, validate_event_log


runner = CliRunner()


def test_task_events_are_hash_chained() -> None:
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)

            created = runner.invoke(app, ["task", "create", "hash chain task"])
            assert created.exit_code == 0, created.output

            run = runner.invoke(app, ["task", "run", "task-0001", "--shell", "echo ok > result.txt"])
            assert run.exit_code == 0, run.output

            verify = runner.invoke(app, ["task", "verify", "task-0001", "--shell", "test -f result.txt"])
            assert verify.exit_code == 0, verify.output

            events_path = Path(".devflow/tasks/task-0001/events.jsonl")
            events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines()]

            assert [event["event_index"] for event in events] == list(range(len(events)))
            assert events[0]["previous_event_hash"] is None
            for index, event in enumerate(events):
                assert event["event_hash"] == event_content_hash(event)
                if index:
                    assert event["previous_event_hash"] == events[index - 1]["event_hash"]

            ok, detail = validate_event_log(events_path)
            assert ok, detail
            assert "hash chain valid" in detail
        finally:
            os.chdir(old_cwd)


def test_doctor_reports_tampered_task_event_hash_chain() -> None:
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)

            created = runner.invoke(app, ["task", "create", "tamper task"])
            assert created.exit_code == 0, created.output

            events_path = Path(".devflow/tasks/task-0001/events.jsonl")
            events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines()]
            events[0]["title"] = "edited after append"
            events_path.write_text(json.dumps(events[0], sort_keys=True) + "\n", encoding="utf-8")

            result = runner.invoke(app, ["doctor"])
            assert result.exit_code == 1, result.output
            assert "task-0001 events integrity" in result.output
            assert "event_hash mismatch" in result.output
        finally:
            os.chdir(old_cwd)
