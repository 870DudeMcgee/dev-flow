from __future__ import annotations

import json
import tempfile
from pathlib import Path

from devflow.control_room.service import create_task
from devflow.control_room.task_packet import TaskPacketLimits, build_task_packet


def test_task_packet_canonical_files_precedence_on_conflict() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        create_task(root, "Canonical title")
        task_path = root / ".devflow" / "tasks" / "task-0001"

        (task_path / "summary.json").write_text(
            json.dumps(
                {
                    "task_id": "task-0001",
                    "title": "Tampered summary title",
                    "status": "verified",
                    "workspace_path": ".devflow/workspaces/not-the-task",
                    "latest_verification_status": "passed",
                    "merge_ready": True,
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

        packet = build_task_packet("task-0001", root=root)

        assert packet.task_id == "task-0001"
        assert packet.title == "Canonical title"
        assert packet.status == "created"
        assert packet.adapter == "shell"
        assert packet.workspace_path == ".devflow/workspaces/task-0001"
        assert packet.task["title"] == "Canonical title"
        assert packet.task["status"] == "created"
        assert packet.verification["status"] == "not_run"
        assert packet.summary == "task-0001 created: Canonical title"
        assert packet.derived_summary is None
        assert any("Ignored summary.json" in note for note in packet.truncation_notes)


def test_task_packet_recent_events_limit() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        create_task(root, "Many events")
        events_path = root / ".devflow" / "tasks" / "task-0001" / "events.jsonl"
        _write_events(events_path, count=7)

        packet = build_task_packet("task-0001", TaskPacketLimits(recent_events_limit=3), root=root)

        assert [event["event"] for event in packet.recent_events] == ["event_5", "event_6", "event_7"]
        assert [event["index"] for event in packet.recent_events] == [5, 6, 7]
        assert packet.omitted_counts["events"] == 4


def test_task_packet_log_tail_truncation() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        create_task(root, "Log tails")
        logs_path = root / ".devflow" / "tasks" / "task-0001" / "logs"
        (logs_path / "worker.log").write_text("\n".join(f"worker {index}" for index in range(1, 7)) + "\n", encoding="utf-8")
        (logs_path / "verify.log").write_text("\n".join(f"verify {index}" for index in range(1, 6)) + "\n", encoding="utf-8")

        packet = build_task_packet(
            "task-0001",
            TaskPacketLimits(worker_log_tail_lines=2, verify_log_tail_lines=3),
            root=root,
        )

        assert packet.logs["worker"].tail == ["worker 5", "worker 6"]
        assert "worker 1" not in packet.logs["worker"].tail
        assert packet.logs["verify"].tail == ["verify 3", "verify 4", "verify 5"]
        assert "verify 1" not in packet.logs["verify"].tail
        assert packet.logs["worker"].omitted_lines == 4
        assert packet.logs["verify"].omitted_lines == 2
        assert "Tail-limited worker.log to last 2 of 6 line(s)." in packet.truncation_notes
        assert "Tail-limited verify.log to last 3 of 5 line(s)." in packet.truncation_notes


def test_task_packet_tracks_omitted_events_and_logs_counts() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        create_task(root, "Counts")
        task_path = root / ".devflow" / "tasks" / "task-0001"
        _write_events(task_path / "events.jsonl", count=5, malformed=True)
        logs_path = task_path / "logs"
        (logs_path / "worker.log").write_text("\n".join(f"worker {index}" for index in range(1, 6)) + "\n", encoding="utf-8")
        (logs_path / "verify.log").write_text("\n".join(f"verify {index}" for index in range(1, 5)) + "\n", encoding="utf-8")

        packet = build_task_packet(
            "task-0001",
            TaskPacketLimits(recent_events_limit=2, worker_log_tail_lines=2, verify_log_tail_lines=1),
            root=root,
        )

        assert packet.omitted_counts == {
            "events": 3,
            "malformed_events": 1,
            "worker_log_lines": 3,
            "worker_log_bytes": 0,
            "verify_log_lines": 3,
            "verify_log_bytes": 0,
        }
        assert "Omitted 1 malformed event line(s)." in packet.truncation_notes
        assert "Omitted 3 older event(s); included the 2 most recent event(s)." in packet.truncation_notes


def test_task_packet_missing_summary_json_does_not_crash() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        create_task(root, "No derived cache")
        (root / ".devflow" / "tasks" / "task-0001" / "summary.json").unlink()

        packet = build_task_packet("task-0001", root=root)

        assert packet.task_id == "task-0001"
        assert packet.status == "created"
        assert packet.summary == "task-0001 created: No derived cache"
        assert packet.derived_summary is None


def test_task_packet_malformed_summary_json_falls_back() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        create_task(root, "Malformed cache")
        task_path = root / ".devflow" / "tasks" / "task-0001"
        (task_path / "summary.json").write_text("{not json", encoding="utf-8")

        packet = build_task_packet("task-0001", root=root)

        assert packet.title == "Malformed cache"
        assert packet.status == "created"
        assert packet.workspace_path == ".devflow/workspaces/task-0001"
        assert packet.derived_summary is None
        assert any("Ignored summary.json because it is malformed" in note for note in packet.truncation_notes)


def test_task_packet_deterministic_output() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        create_task(root, "Deterministic")
        task_path = root / ".devflow" / "tasks" / "task-0001"
        _write_events(task_path / "events.jsonl", count=3)
        (task_path / "logs" / "worker.log").write_text("alpha\nbeta\n", encoding="utf-8")

        first = build_task_packet("task-0001", root=root).model_dump(mode="json")
        second = build_task_packet("task-0001", root=root).model_dump(mode="json")

        assert first == second


def test_task_packet_missing_optional_logs_do_not_crash() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        create_task(root, "Missing logs")
        logs_path = root / ".devflow" / "tasks" / "task-0001" / "logs"
        (logs_path / "worker.log").unlink()
        (logs_path / "verify.log").unlink()

        packet = build_task_packet("task-0001", root=root)

        assert packet.logs["worker"].tail == []
        assert packet.logs["worker"].line_count == 0
        assert packet.logs["worker"].omitted_lines == 0
        assert packet.logs["verify"].tail == []
        assert packet.logs["verify"].line_count == 0
        assert packet.logs["verify"].omitted_lines == 0


def test_task_packet_ignores_stale_authoritative_summary_fields() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        create_task(root, "Stale fields test")
        task_path = root / ".devflow" / "tasks" / "task-0001"

        # Write a summary.json that has matching metadata (identity/title/status/workspace/verification_status)
        # but also contains stale verification/merge-readiness/authority fields.
        (task_path / "summary.json").write_text(
            json.dumps(
                {
                    "task_id": "task-0001",
                    "title": "Stale fields test",
                    "status": "created",
                    "workspace_path": ".devflow/workspaces/task-0001",
                    "latest_verification_status": "not_run",
                    "latest_verification_exit_code": 127,
                    "latest_verification_log_path": ".devflow/tasks/task-0001/logs/stale.log",
                    "merge_ready": True,
                    "merge_readiness_reasons": ["stale reason"],
                    "summary": "harmless worker summary",
                    "workspace_dirty": True,
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

        packet = build_task_packet("task-0001", root=root)

        # The packet building succeeded and summary.json was NOT ignored since metadata matched
        assert "Ignored summary.json" not in "".join(packet.truncation_notes)

        # Harmless non-authoritative fields appear in the derived_summary
        assert packet.derived_summary is not None
        assert packet.derived_summary["summary"] == "harmless worker summary"
        assert packet.derived_summary["workspace_dirty"] is True

        # Authoritative and stale fields are filtered out and do NOT appear in derived_summary
        prohibited_keys = {
            "task_id",
            "title",
            "status",
            "workspace_path",
            "latest_verification_status",
            "latest_verification_exit_code",
            "latest_verification_log_path",
            "merge_ready",
            "merge_readiness_reasons",
        }
        for key in prohibited_keys:
            assert key not in packet.derived_summary

        # These stale fields did not influence the packet metadata or status
        assert packet.status == "created"
        assert packet.title == "Stale fields test"
        assert packet.workspace_path == ".devflow/workspaces/task-0001"
        assert packet.verification["status"] == "not_run"


def _write_events(path: Path, *, count: int, malformed: bool = False) -> None:
    lines = [
        json.dumps(
            {
                "timestamp": f"2026-05-28T00:00:{index:02d}+00:00",
                "task_id": "task-0001",
                "event": f"event_{index}",
                "index": index,
            },
            sort_keys=True,
        )
        for index in range(1, count + 1)
    ]
    if malformed:
        lines.insert(1, "{not json")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")