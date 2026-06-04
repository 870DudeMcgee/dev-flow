from __future__ import annotations

import json
import tempfile
from pathlib import Path

from devflow.control_room.service import create_task, verify_task
from devflow.control_room.agent_registry import load_agent_registry
from devflow.control_room.task_packet import TaskPacketLimits, build_agent_packet, build_task_packet, render_task_packet_text


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


def test_qwopus_docs_polish_agent_packet_includes_anti_placeholder_instruction() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        task = create_task(root, "docs/polish: tighten existing task packet docs")
        agent = load_agent_registry(root).require_agent("qwopus-implementer")

        packet = build_agent_packet(task.id, agent, root=root)
        completion_rules = "\n".join(packet.completion_rules)

        assert "For docs/polish tasks, do not invent new docs files" in completion_rules
        assert "commands already exist" in completion_rules
        assert "If a task explicitly requires a new file, creating it is allowed." in completion_rules
        assert "Prefer modifying existing relevant files over creating placeholder docs." in completion_rules


def test_docs_polish_instruction_is_not_on_generic_task_packets() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        create_task(root, "docs/polish: tighten existing task packet docs")

        packet = build_task_packet("task-0001", root=root)
        serialized = json.dumps(packet.model_dump(mode="json"))

        assert packet.agent_id is None
        assert packet.worker_adapter == "shell"
        assert "qwopus-implementer" not in serialized
        assert "do not invent new docs files" not in serialized


def test_task_packet_module_does_not_import_itself() -> None:
    import inspect
    import devflow.control_room.task_packet as task_packet_module

    source = inspect.getsource(task_packet_module)

    assert "from devflow.control_room.task_packet import" not in source
    assert "import devflow.control_room.task_packet" not in source


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


def test_task_packet_omits_code_map_excerpt_when_missing() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        create_task(root, "No map")

        packet = build_task_packet("task-0001", root=root)

        assert packet.code_map_excerpt is None


def test_task_packet_includes_bounded_code_map_excerpt() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        create_task(root, "With map")
        (root / "CODE_MAP.md").write_text(
            "# Code Map\n\n## What this repo does\n\nDev-Flow coordinates workers.\n",
            encoding="utf-8",
        )

        packet = build_task_packet("task-0001", root=root)

        assert packet.code_map_excerpt is not None
        assert packet.code_map_excerpt["path"] == "CODE_MAP.md"
        assert packet.code_map_excerpt["lines"] == [
            "# Code Map",
            "",
            "## What this repo does",
            "",
            "Dev-Flow coordinates workers.",
        ]
        assert packet.code_map_excerpt["truncated"] is False
        assert packet.code_map_excerpt["omitted_lines"] == 0


def test_task_packet_truncates_code_map_excerpt_by_limit() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        create_task(root, "Long map")
        (root / "CODE_MAP.md").write_text("\n".join(f"line {index}" for index in range(1, 6)) + "\n", encoding="utf-8")

        packet = build_task_packet("task-0001", TaskPacketLimits(code_map_excerpt_lines=2), root=root)

        assert packet.code_map_excerpt is not None
        assert packet.code_map_excerpt["lines"] == ["line 1", "line 2"]
        assert packet.code_map_excerpt["line_count"] == 5
        assert packet.code_map_excerpt["included_lines"] == 2
        assert packet.code_map_excerpt["omitted_lines"] == 3
        assert packet.code_map_excerpt["truncated"] is True
        assert "Included first 2 of 5 CODE_MAP.md line(s)." in packet.truncation_notes


def test_task_packet_text_renders_code_map_excerpt() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        create_task(root, "Render map")
        (root / "CODE_MAP.md").write_text("# Code Map\n\n## Layout\n\n- `src/`\n", encoding="utf-8")

        rendered = render_task_packet_text(build_task_packet("task-0001", root=root))

        assert "## Project Code Map" in rendered
        assert "- **Path**: CODE_MAP.md" in rendered
        assert "> # Code Map" in rendered


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


def test_task_packet_verification_uses_projection_fallbacks() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        create_task(root, "Projection-backed verification")
        verify_task(root, "task-0001", ["echo", "ok"])
        task_path = root / ".devflow" / "tasks" / "task-0001"

        (task_path / "verification.json").write_text(
            json.dumps(
                {
                    "task_id": "task-0001",
                    "status": "passed",
                    "note": "preserve packet-specific fields",
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

        packet = build_task_packet("task-0001", root=root)

        assert packet.verification["status"] == "passed"
        assert packet.verification["task_status"] == "verified"
        assert packet.verification["exit_code"] == 0
        assert packet.verification["log_path"] == "<task>/logs/verify.log"
        assert packet.verification["command"] == "echo ok"
        assert packet.verification["note"] == "preserve packet-specific fields"


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


def test_task_packet_constraints_signature() -> None:
    from devflow.control_room.task_packet import _constraints
    import inspect

    sig = inspect.signature(_constraints)
    assert len(sig.parameters) == 1
    assert "virtual_workspace_path" in sig.parameters

    res = _constraints("<workspace>/my-task")
    assert any("Worker execution must stay inside <workspace>/my-task" in c for c in res)


def test_task_packet_redaction_regression() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        # Create a task
        create_task(root, "Redaction test")
        task_path = root / ".devflow" / "tasks" / "task-0001"

        # Now, write a custom canonical task.yaml containing secret values in fields
        task_yaml_content = (
            "id: task-0001\n"
            "title: \"Task with API_KEY=super-secret-123\"\n"
            "status: running\n"
            "created_at: 2026-05-28T00:00:00+00:00\n"
            "updated_at: 2026-05-28T00:00:00+00:00\n"
            f"workspace: \"{root}/.devflow/workspaces/task-0001\"\n"
            f"workspace_path: \"{root}/.devflow/workspaces/task-0001\"\n"
            "worker: shell\n"
            "verification_status: not_run\n"
            "latest_log_line: \"Authorization: Bearer ghp_secretgithubtoken123\"\n"
        )
        (task_path / "task.yaml").write_text(task_yaml_content, encoding="utf-8")

        # Also write verification.json containing potential secrets
        (task_path / "verification.json").write_text(
            json.dumps({
                "task_id": "task-0001",
                "status": "not_run",
                "task_status": "running",
                "exit_code": None,
                "latest_log_line": "sk-proj-openai1234567890abcdef1234567890",
                "command": "API_KEY=\"another-secret-here\" pytest",
            }, indent=2) + "\n",
            encoding="utf-8",
        )

        # Also write events.jsonl with secret values
        events_path = task_path / "events.jsonl"
        events_path.write_text(
            json.dumps({
                "timestamp": "2026-05-28T00:00:01+00:00",
                "task_id": "task-0001",
                "event": "started",
                "data": {
                    "token": "ghp_anothergithubtoken36charsabcdefgh",
                    "password": "my-secret-password-123",
                }
            }) + "\n",
            encoding="utf-8",
        )

        # Also write logs with secrets and private key block
        logs_path = task_path / "logs"
        private_key = (
            "-----BEGIN RSA PRIVATE KEY-----\n"
            "MIIEowIBAAKCAQEA0Y3...\n"
            "-----END RSA PRIVATE KEY-----\n"
        )
        (logs_path / "worker.log").write_text(
            f"Failed with Bearer token_abc123\n{private_key}",
            encoding="utf-8",
        )
        (logs_path / "verify.log").write_text(
            "Authorization: Basic admin:secretpass\n",
            encoding="utf-8",
        )

        # Build packet
        packet = build_task_packet("task-0001", root=root)

        # Serialize packet to check for leaks
        serialized = json.dumps(packet.model_dump(mode="json"))

        # Assert no secrets in serialized output
        assert "super-secret-123" not in serialized
        assert "ghp_secretgithubtoken123" not in serialized
        assert "sk-proj-openai" not in serialized
        assert "another-secret-here" not in serialized
        assert "ghp_anothergithubtoken" not in serialized
        assert "my-secret-password-123" not in serialized
        assert "MIIEowIBAAKCAQEA0Y3" not in serialized
        assert "token_abc123" not in serialized
        assert "admin:secretpass" not in serialized

        # Assert redacted versions are present to preserve context
        assert packet.task["title"] == "Task with API_KEY=[REDACTED]"
        assert packet.verification["command"] == 'API_KEY="[REDACTED]" pytest'
        assert packet.recent_events[0]["data"]["password"] == "[REDACTED]"
        assert packet.recent_events[0]["data"]["token"] == "[REDACTED]"
        assert "Bearer [REDACTED]" in packet.logs["worker"].tail[0]
        assert "Authorization: [REDACTED]" in packet.logs["verify"].tail[0]
        assert packet.logs["worker"].tail[1] == "[REDACTED PRIVATE KEY]"


def test_task_packet_ordinary_words_not_redacted() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        create_task(root, "Ordinary words test")
        task_path = root / ".devflow" / "tasks" / "task-0001"

        # Write task containing words like monkey, keyboard, keynote, keyframe
        task_yaml_content = (
            "id: task-0001\n"
            "title: \"Ordinary words test with monkey and keyboard\"\n"
            "status: running\n"
            "created_at: 2026-05-28T00:00:00+00:00\n"
            "updated_at: 2026-05-28T00:00:00+00:00\n"
            f"workspace: \"{root}/.devflow/workspaces/task-0001\"\n"
            f"workspace_path: \"{root}/.devflow/workspaces/task-0001\"\n"
            "worker: shell\n"
            "verification_status: not_run\n"
            "latest_log_line: \"ordinary keynote and keyframe\"\n"
        )
        (task_path / "task.yaml").write_text(task_yaml_content, encoding="utf-8")

        # Build packet
        packet = build_task_packet("task-0001", root=root)

        # Assert ordinary words are NOT redacted
        assert "monkey" in packet.title
        assert "keyboard" in packet.title
        assert "keynote" in packet.task["latest_log_line"]
        assert "keyframe" in packet.task["latest_log_line"]


def test_task_packet_nested_secrets_redacted() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        create_task(root, "Nested secrets test")
        task_path = root / ".devflow" / "tasks" / "task-0001"

        task_yaml_content = (
            "id: task-0001\n"
            "title: \"Nested secrets test\"\n"
            "status: running\n"
            "created_at: 2026-05-28T00:00:00+00:00\n"
            "updated_at: 2026-05-28T00:00:00+00:00\n"
            f"workspace: \"{root}/.devflow/workspaces/task-0001\"\n"
            f"workspace_path: \"{root}/.devflow/workspaces/task-0001\"\n"
            "worker: shell\n"
            "verification_status: not_run\n"
        )
        (task_path / "task.yaml").write_text(task_yaml_content, encoding="utf-8")

        # Also write verification.json containing potential secrets
        # under a sensitive dict
        (task_path / "verification.json").write_text(
            json.dumps({
                "task_id": "task-0001",
                "status": "not_run",
                "task_status": "running",
                "exit_code": None,
                # Add custom nested secrets under sensitive keys
                "api_key": ["plain-secret-value", {"value": "nested-secret-value"}],
                "secret": {"value": "wrapped-secret-value"},
            }, indent=2) + "\n",
            encoding="utf-8",
        )

        # Build packet
        packet = build_task_packet("task-0001", root=root)

        # Serialize packet to check for leaks
        serialized = json.dumps(packet.model_dump(mode="json"))

        # Assert nested secrets are fully redacted in serialized output
        assert "plain-secret-value" not in serialized
        assert "nested-secret-value" not in serialized
        assert "wrapped-secret-value" not in serialized

        # Check values directly in the Pydantic packet object
        assert packet.verification["api_key"] == ["[REDACTED]", {"value": "[REDACTED]"}]
        assert packet.verification["secret"] == {"value": "[REDACTED]"}


def test_task_packet_cli_command() -> None:
    import os
    from typer.testing import CliRunner
    from devflow.cli import app

    runner = CliRunner()
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            root = Path(tmp)
            os.chdir(tmp)

            # Create a task
            create_result = runner.invoke(app, ["task", "create", "CLI packet preview test"])
            assert create_result.exit_code == 0, create_result.output

            # Add a secret value to log to verify redaction and virtualization
            task_path = root / ".devflow" / "tasks" / "task-0001"
            (task_path / "logs" / "worker.log").write_text("Failed with Bearer token_abc123\n", encoding="utf-8")

            # Check files before CLI invoke to track mutation safety
            task_yaml_before = (task_path / "task.yaml").read_text(encoding="utf-8")
            events_before = (task_path / "events.jsonl").read_text(encoding="utf-8")

            # Invoke the CLI preview command
            result = runner.invoke(app, ["task", "packet", "task-0001"])
            assert result.exit_code == 0, result.output

            # 1. Verify valid JSON output
            data = json.loads(result.output)
            assert isinstance(data, dict)

            # 2. Verify expected TaskPacket fields are present
            assert data["task_id"] == "task-0001"
            assert data["title"] == "CLI packet preview test"
            assert data["status"] == "created"
            assert data["worker_adapter"] == "shell"
            assert "logs" in data
            assert "constraints" in data
            assert "allowed_artifacts" in data

            # 3. Verify that redaction is preserved
            # Bearer token in logs should be redacted
            worker_log_tail = data["logs"]["worker"]["tail"]
            assert len(worker_log_tail) == 1
            assert "Bearer [REDACTED]" in worker_log_tail[0]
            assert "token_abc123" not in result.output

            # 4. Verify path virtualization is preserved
            assert data["workspace_path"] == "<workspace>"

            # 5. Verify mutation safety (canonical files were not changed)
            task_yaml_before_check = (task_path / "task.yaml").read_text(encoding="utf-8")
            events_before_check = (task_path / "events.jsonl").read_text(encoding="utf-8")
            assert task_yaml_before == task_yaml_before_check
            assert events_before == events_before_check
        finally:
            os.chdir(old_cwd)


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


def test_qwopus_packet_workspace_resolution_and_mismatch_behavior() -> None:
    import pytest
    from devflow.control_room.context_pack import build_context_pack
    from devflow.control_room.patch_applier import apply_patch_files, parse_unified_diff, PatchApplicationError

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        
        # 1. Create a task with a docs/polish title
        create_task(root, "Polish README.md and clean up docs")
        task_id = "task-0001"
        
        task_path = root / ".devflow" / "tasks" / task_id
        workspace_dir = root / ".devflow" / "workspaces" / task_id
        workspace_dir.mkdir(parents=True, exist_ok=True)
        
        # Write main repository README.md (simulating what RepoScout might find in the root checkout)
        main_readme = root / "README.md"
        main_readme.write_text("# Dev-Flow\nSome legacy text here.\n", encoding="utf-8")
        
        # Write task workspace README.md (the actual target workspace file)
        workspace_readme = workspace_dir / "README.md"
        workspace_readme.write_text("# DevFlow Workspace\nSome actual task text here.\n", encoding="utf-8")
        
        # 2. Build context pack for worker
        pack_data = build_context_pack(root, task_id, "worker")
        cp = pack_data.get("context_pack", {})
        
        # Find README.md in sources_metadata
        readme_entry = None
        for item in cp.get("sources_metadata", []):
            if item.get("path") == "README.md":
                readme_entry = item
                break
                
        # Assert that the README excerpt is successfully included and matches the workspace content, not the root content!
        assert readme_entry is not None
        assert readme_entry["mode"] == "full"
        assert readme_entry["content"] == "# DevFlow Workspace\nSome actual task text here.\n"
        
        # 3. Verify that a Qwopus patch based on mismatched README content fails safely on apply-patch
        mismatched_diff = (
            "--- a/README.md\n"
            "+++ b/README.md\n"
            "@@ -1,2 +1,2 @@\n"
            "-# Dev-Flow\n"
            "+# Dev-Flow Modified\n"
            " Some legacy text here.\n"
        )
        parsed_patches = parse_unified_diff(mismatched_diff)
        
        # Should raise PatchApplicationError due to mismatch
        with pytest.raises(PatchApplicationError) as exc_info:
            apply_patch_files(workspace_dir, parsed_patches)
            
        assert "mismatch" in str(exc_info.value)
        assert "Found:    '# DevFlow Workspace'" in str(exc_info.value)
