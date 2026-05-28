from __future__ import annotations

import json
import tempfile
from pathlib import Path

from devflow.control_room.service import create_task
from devflow.control_room.task_packet import TaskPacketLimits, build_task_packet


def test_task_packet_uses_canonical_state_over_summary_json() -> None:
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
                }
            )
            + "\n",
            encoding="utf-8",
        )

        packet = build_task_packet("task-0001", TaskPacketLimits(), root=root)

        assert packet.task_id == "task-0001"
        assert packet.title == "Canonical title"
        assert packet.status == "created"
        assert packet.workspace_path == ".devflow/workspaces/task-0001"
        assert packet.verification["status"] == "not_run"
        assert packet.summary == "task-0001 created: Canonical title"
        assert any("Ignored summary.json" in note for note in packet.truncation_notes)


def test_task_packet_bounds_recent_events_and_reports_omissions() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        create_task(root, "Many events")
        events_path = root / ".devflow" / "tasks" / "task-0001" / "events.jsonl"
        events_path.write_text(
            "".join(
                json.dumps(
                    {
                        "timestamp": f"2026-05-28T00:00:0{index}+00:00",
                        "task_id": "task-0001",
                        "event": f"event_{index}",
                        "index": index,
                    },
                    sort_keys=True,
                )
                + "\n"
                for index in range(1, 7)
            ),
            encoding="utf-8",
        )

        packet = build_task_packet("task-0001", TaskPacketLimits(max_recent_events=2), root=root)

        assert [event["event"] for event in packet.recent_events] == ["event_5", "event_6"]
        assert packet.omitted_counts["events"] == 4
        assert "Omitted 4 older event(s); included the 2 most recent event(s)." in packet.truncation_notes


def test_task_packet_tail_limits_logs_and_reports_truncation() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        create_task(root, "Log tails")
        logs_path = root / ".devflow" / "tasks" / "task-0001" / "logs"
        (logs_path / "worker.log").write_text("\n".join(f"worker {index}" for index in range(1, 6)) + "\n", encoding="utf-8")
        (logs_path / "verify.log").write_text("\n".join(f"verify {index}" for index in range(1, 5)) + "\n", encoding="utf-8")

        packet = build_task_packet("task-0001", TaskPacketLimits(log_tail_lines=2), root=root)

        assert packet.logs["worker"].tail == ["worker 4", "worker 5"]
        assert packet.logs["verify"].tail == ["verify 3", "verify 4"]
        assert packet.omitted_counts["worker_log_lines"] == 3
        assert packet.omitted_counts["verify_log_lines"] == 2
        assert "Tail-limited worker.log to last 2 of 5 line(s)." in packet.truncation_notes
        assert "Tail-limited verify.log to last 2 of 4 line(s)." in packet.truncation_notes


def test_task_packet_missing_optional_summary_json_does_not_crash() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        create_task(root, "No derived cache")
        (root / ".devflow" / "tasks" / "task-0001" / "summary.json").unlink()

        packet = build_task_packet("task-0001", TaskPacketLimits(), root=root)

        assert packet.task_id == "task-0001"
        assert packet.status == "created"
        assert packet.summary == "task-0001 created: No derived cache"


def test_task_packet_malformed_summary_json_does_not_override_canonical_state() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        create_task(root, "Malformed cache")
        task_path = root / ".devflow" / "tasks" / "task-0001"
        (task_path / "summary.json").write_text("{not json", encoding="utf-8")

        packet = build_task_packet("task-0001", TaskPacketLimits(), root=root)

        assert packet.title == "Malformed cache"
        assert packet.status == "created"
        assert packet.workspace_path == ".devflow/workspaces/task-0001"
        assert any("Ignored summary.json because it is malformed" in note for note in packet.truncation_notes)