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

        assert packet.workspace_path == "<workspace>"
        assert packet.task["workspace_path"] == "<workspace>"
        assert packet.task["workspace"] == "<workspace>"
        assert "<task>/task.yaml" in packet.allowed_artifacts
        assert packet.logs["worker"].path == "<task>/logs/worker.log"
        assert packet.task["log_path"] is None
        assert packet.task["verification_log_path"] is None
        assert packet.task["result_path"] is None
        assert packet.task_id == "task-0001"
        assert packet.title == "Canonical title"
        assert packet.status == "created"
        assert packet.adapter == "shell"
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
        assert packet.logs["worker"].path == "<task>/logs/worker.log"
        assert packet.logs["verify"].path == "<task>/logs/verify.log"
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
        assert packet.workspace_path == "<workspace>"
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
        assert packet.workspace_path == "<workspace>"
        assert packet.verification["status"] == "not_run"


def test_task_packet_path_virtualization() -> None:
    from devflow.control_room.task_packet import _virtualize_path
    repo_root = Path("/Users/developer/project")
    task_id = "task-0001"

    # 1. Absolute POSIX path under task
    path1 = "/Users/developer/project/.devflow/tasks/task-0001/logs/worker.log"
    assert _virtualize_path(path1, repo_root, task_id) == "<task>/logs/worker.log"

    # 2. Absolute POSIX path under workspace
    path2 = "/Users/developer/project/.devflow/workspaces/task-0001/src/main.py"
    assert _virtualize_path(path2, repo_root, task_id) == "<workspace>/src/main.py"

    # 3. file:// absolute path
    path3 = "file:///Users/developer/project/.devflow/tasks/task-0001/logs/verify.log"
    assert _virtualize_path(path3, repo_root, task_id) == "<task>/logs/verify.log"

    # 4. Windows absolute path with backslashes
    path4 = "C:\\Users\\developer\\project\\.devflow\\workspaces\\task-0001\\tests\\test_core.py"
    assert _virtualize_path(path4, repo_root, task_id) == "<workspace>/tests/test_core.py"

    # 5. Outside absolute paths scrubbed
    path5 = "/Users/developer/some-other-folder/secret.py"
    virtualized = _virtualize_path(path5, repo_root, task_id)
    assert "/Users/" not in virtualized
    assert "secret.py" in virtualized


def test_task_packet_full_packet_path_leak_regression() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        # Create a task
        create_task(root, "Regression leak test")
        task_path = root / ".devflow" / "tasks" / "task-0001"

        # Now, write a custom canonical task.yaml containing absolute paths
        # that could leak if not virtualized, including /Users/, /tmp/, Windows drives C:\, backslashes, file://
        task_yaml_content = (
            "id: task-0001\n"
            "title: \"Regression leak test\"\n"
            "status: running\n"
            "created_at: 2026-05-28T00:00:00+00:00\n"
            "updated_at: 2026-05-28T00:00:00+00:00\n"
            f"workspace: \"{root}/.devflow/workspaces/task-0001\"\n"
            "worker: shell\n"
            "verification_status: not_run\n"
            f"workspace_path: \"{root}/.devflow/workspaces/task-0001\"\n"
            "log_path: \"/Users/developer/project/.devflow/tasks/task-0001/logs/worker.log\"\n"
            "result_path: \"/tmp/task-0001/result.md\"\n"
            "verification_log_path: \"C:\\\\Users\\\\developer\\\\project\\\\.devflow\\\\tasks\\\\task-0001\\\\logs\\\\verify.log\"\n"
            "verification_command: \"pytest\"\n"
            "latest_log_line: \"Finished\"\n"
        )
        (task_path / "task.yaml").write_text(task_yaml_content, encoding="utf-8")

        # Also write verification.json containing potential leaks in path fields
        (task_path / "verification.json").write_text(
            json.dumps({
                "task_id": "task-0001",
                "workspace": f"{root}/.devflow/workspaces/task-0001",
                "command": ["pytest"],
                "status": "not_run",
                "task_status": "running",
                "exit_code": None,
                "latest_log_line": "Finished",
                "log_path": "file:///Users/developer/project/.devflow/tasks/task-0001/logs/verify.log",
                "finished_at": None,
            }, indent=2) + "\n",
            encoding="utf-8",
        )

        # Also write summary.json with some matching metadata and workspace paths
        (task_path / "summary.json").write_text(
            json.dumps({
                "task_id": "task-0001",
                "title": "Regression leak test",
                "status": "running",
                "workspace_path": f"{root}/.devflow/workspaces/task-0001",
                "latest_verification_status": "not_run",
                "summary": "harmless summary with no local path",
                "workspace_dirty": False,
            }) + "\n",
            encoding="utf-8",
        )

        # Let's generate a task packet
        packet = build_task_packet("task-0001", root=root)

        # Serialize the entire packet output
        serialized = json.dumps(packet.model_dump(mode="json"))

        # Verify that the constraint actually contains the virtualized path
        assert any("<workspace>" in c for c in packet.constraints)

        # Verify that no absolute OS-specific paths leaked anywhere in the serialized packet
        # 1. Assert no "/Users/"
        assert "/Users/" not in serialized
        # 2. Assert no "/tmp/"
        assert "/tmp/" not in serialized
        # 3. Assert no "file://"
        assert "file://" not in serialized
        # 4. Assert no Windows drive paths like "C:\"
        assert "C:\\" not in serialized
        assert "C:/" not in serialized
        # 5. Assert no backslash-heavy Windows paths
        assert "\\Users\\" not in serialized
        assert "C:\\Users" not in serialized


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