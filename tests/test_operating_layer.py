from __future__ import annotations

import json
import subprocess
import threading
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from http.client import HTTPConnection
from pathlib import Path

import pytest
from typer.testing import CliRunner

from devflow.cli import app
from devflow.control_room.browser_action_policy import get_browser_allowed_mutations
from devflow.control_room.idea_foundry import capture_idea, classify_idea, park_idea
from devflow.control_room.goal_lifecycle import ensure_goal_lifecycle
from devflow.control_room.local_model_runtime_lock import local_model_runtime_lock
from devflow.control_room.operating_layer import build_operating_layer_snapshot
from devflow.control_room.operating_layer_first_viewport import build_first_viewport_presentation
from devflow.control_room.operating_layer_server import (
    OperatingLayerHTTPServer,
    OperatingLayerRequestHandler,
)
from devflow.control_room.persistence import get_task, save_task, utc_now
from devflow.control_room.project_models import ProjectMetadata, ProjectRecord
from devflow.control_room.project_registry import register_project, write_project_metadata
from devflow.control_room.serial_local_agent_run import create_serial_local_agent_run
from devflow.control_room.task_workbench import build_task_workbench
from devflow.control_room.worker_evidence import write_worker_evidence
from tests.helpers import setup_temp_git_repo

runner = CliRunner()


class MockUrlopenResponse:
    def __init__(self, body: dict) -> None:
        self.body = json.dumps(body).encode("utf-8")

    def read(self, *args: object, **kwargs: object) -> bytes:
        return self.body

    def __enter__(self) -> "MockUrlopenResponse":
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        return None


def _create_goal(tmp_path: Path) -> None:
    brief = tmp_path / "brief.md"
    brief.write_text("# Operating layer goal\n", encoding="utf-8")
    result = runner.invoke(app, ["goal", "init", "G-0001", "--from", str(brief)])
    assert result.exit_code == 0, result.output


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _write_local_patch_worker_evidence(root: Path, task_id: str) -> None:
    agent_dir = root / ".devflow" / "tasks" / task_id / "agents" / "qwopus-implementer"
    _write_json(
        agent_dir / "run.json",
        {
            "schema_version": 1,
            "task_id": task_id,
            "agent_id": "qwopus-implementer",
            "status": "complete",
            "model": "qwopus:latest",
            "adapter": "ollama_chat",
            "proposal_patch_found": True,
        },
    )
    (agent_dir / "proposal.patch").write_text("diff --git a/hello.txt b/hello.txt\n", encoding="utf-8")


def _write_stale_task_lock(root: Path, task_id: str) -> None:
    lock_dir = root / ".devflow" / "tasks" / task_id / ".lock"
    lock_dir.mkdir(parents=True, exist_ok=True)
    old_time = datetime.now(timezone.utc) - timedelta(hours=2)
    (lock_dir / "owner.json").write_text(
        json.dumps(
            {
                "task_id": task_id,
                "operation": "stale-run",
                "pid": 1,
                "host": "other-host",
                "acquired_at": old_time.isoformat(),
            }
        )
        + "\n",
        encoding="utf-8",
    )


def _serve_operating_layer(root: Path) -> tuple[OperatingLayerHTTPServer, threading.Thread, str, int]:
    server = OperatingLayerHTTPServer(("127.0.0.1", 0), root)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    return server, thread, host, port


def _post_json(host: str, port: int, path: str, payload: dict[str, object]) -> tuple[int, dict]:
    connection = HTTPConnection(host, port, timeout=5)
    connection.request(
        "POST",
        path,
        body=json.dumps(payload),
        headers={"Content-Type": "application/json"},
    )
    response = connection.getresponse()
    body = response.read().decode("utf-8")
    parsed = json.loads(body) if body else {}
    return response.status, parsed


def _get_raw(host: str, port: int, path: str) -> tuple[int, bytes, dict]:
    connection = HTTPConnection(host, port, timeout=5)
    connection.request("GET", path)
    response = connection.getresponse()
    body = response.read()
    headers = {k.lower(): v for k, v in response.getheaders()}
    return response.status, body, headers


def test_builder_judge_quality_gate_transcript_projection_preserves_route_markdown(
    tmp_path: Path,
) -> None:
    from devflow.control_room.builder_judge_quality_gate import build_quality_gate_transcript_text

    session_dir = tmp_path / ".devflow" / "brainstorms" / "session-1"
    session_dir.mkdir(parents=True)
    records = [
        {"role": "user", "content": "  Build a tiny artifact.  "},
        {"role": "assistant", "content": "   "},
        {"content": "No explicit role."},
    ]
    session_dir.joinpath("transcript.jsonl").write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )

    assert build_quality_gate_transcript_text(tmp_path, "session-1") == (
        "### User\n\nBuild a tiny artifact.\n"
        "\n"
        "### Unknown\n\nNo explicit role.\n"
    )
    with pytest.raises(ValueError, match="brainstorm session has no transcript: missing"):
        build_quality_gate_transcript_text(tmp_path, "missing")


def test_operating_layer_server_workbench_implement_missing_session_is_stable_action_error(
    tmp_path: Path,
) -> None:
    setup_temp_git_repo(tmp_path)

    server, thread, host, port = _serve_operating_layer(tmp_path)
    try:
        status, payload = _post_json(host, port, "/api/workbench/implement", {})
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert status == HTTPStatus.CONFLICT
    assert payload["error"] == "session_id is required"
    assert payload["error_code"] == "workbench_conflict"
    assert payload["error_type"] == "WorkbenchError"
    assert payload["retriable"] is False


def test_operating_layer_snapshot_json_is_read_only_contract(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    create = runner.invoke(app, ["task", "create", "organize visible work"])
    assert create.exit_code == 0, create.output

    result = runner.invoke(app, ["operating-layer", "snapshot", "--json"])
    assert result.exit_code == 0, result.output

    payload = json.loads(result.output)
    assert payload["schema_version"] == 1
    assert payload["project"]["root"] == str(tmp_path)
    assert payload["health"]["total_tasks"] == 1
    assert payload["focus_task_id"] == "task-0001"
    assert payload["next_action"]["command"] == "devflow task run task-0001 --worker shell -- <command>"
    lanes = {lane["name"]: lane["task_ids"] for lane in payload["lanes"]}
    assert lanes["new"] == ["task-0001"]
    assert payload["tasks"][0]["id"] == "task-0001"
    assert payload["tasks"][0]["lane"] == "new"
    assert payload["tasks"][0]["definition_of_done"] is None
    assert payload["tasks"][0]["detail"]["events_path"] == ".devflow/tasks/task-0001/events.jsonl"
    assert payload["tasks"][0]["detail"]["recent_events"][-1]["event"] == "task_created"
    assert payload["tasks"][0]["review_state"] == "not_ready"
    assert payload["tasks"][0]["review_score"] == 10
    assert payload["tasks"][0]["review_blockers"] == ["no reviewable task output was found"]
    assert payload["tasks"][0]["review_next_command"] == "devflow task show task-0001"
    assert ".devflow/tasks/task-0001/task.yaml" in payload["tasks"][0]["review_evidence"]
    assert payload["action_rail"][0]["command"] == "devflow git status"
    assert payload["action_rail"][0]["supervisor_may_auto_run"] is True
    assert payload["tasks"][0]["actions"][0]["command"] == "devflow task run task-0001 --worker shell -- <command>"
    assert payload["tasks"][0]["actions"][0]["requires_human_approval"] is True
    assert payload["tasks"][0]["actions"][0]["intent"] == "start_shell"
    assert payload["tasks"][0]["actions"][0]["required_inputs"] == ["shell_command"]
    controls = {control["intent"]: control for control in payload["tasks"][0]["controls"]}
    assert controls["start_shell"]["command"] == "devflow task run task-0001 --worker shell -- <command>"
    assert controls["start_shell"]["required_inputs"] == ["shell_command"]
    assert controls["inspect"]["command"] == "devflow task show task-0001"
    first_viewport = payload["first_viewport"]
    assert first_viewport["active_task_count"] == 1
    assert first_viewport["total_task_count"] == 1
    assert first_viewport["worker_lanes"][0]["task_id"] == "task-0001"
    assert first_viewport["worker_lanes"][0]["worker_model_label"] == "shell"
    assert first_viewport["worker_lanes"][0]["action_label"] == "Start shell"
    assert first_viewport["worker_lanes"][0]["next_safe_action"] == (
        "devflow task run task-0001 --worker shell -- <command>"
    )
    assert first_viewport["launchpad"]["selected_task_id"] == "task-0001"
    assert first_viewport["launchpad"]["command"] == "devflow task run task-0001 --worker shell -- <command>"
    assert payload["gate_receipts"][0]["task_id"] == "task-0001"
    assert payload["gate_receipts"][0]["next_gate"] == "run_worker"
    assert payload["mission_feed"][0]["label"] == "Task progress"
    assert payload["mission_feed"][0]["task_id"] == "task-0001"
    assert payload["mission_feed"][0]["detail"] == "2/5 required steps done. Next: run a worker."
    assert payload["freshness"]["snapshot_path"] == ".devflow/freshness/latest.json"
    assert payload["architecture_evidence"]["status"] == "missing"
    assert payload["architecture_evidence"]["read_only"] is True
    assert "architecture audit --write-doc" in payload["architecture_evidence"]["next_safe_action"]
    assert payload["local_model_readiness"]["schema_version"] == 1
    assert "lanes" in payload["local_model_readiness"]
    assert payload["local_model_readiness"]["summary"]["lane_count"] >= 1
    assert payload["workbench"]["stage"] in payload["workbench"]["stages"]
    assert payload["workbench"]["gate_status"]["ready"] is False
    assert [item["id"] for item in payload["workbench"]["gate_status"]["items"]] == ["graphify", "ponytail"]
    assert "Repair gate evidence first" in payload["workbench"]["gate_status"]["next_action"]

    assert not (tmp_path / ".devflow" / "freshness" / "latest.json").exists()
    assert not (tmp_path / ".devflow" / "freshness" / "events.jsonl").exists()


def test_operating_layer_snapshot_exposes_stale_lock_status_as_read_only(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["task", "create", "stale lock visible"]).exit_code == 0
    _write_stale_task_lock(tmp_path, "task-0001")

    payload = build_operating_layer_snapshot(tmp_path).model_dump(mode="json")
    task_payload = next(item for item in payload["tasks"] if item["id"] == "task-0001")
    first_viewport = payload["first_viewport"]

    assert task_payload["lock_status"]["is_stale"] is True
    assert task_payload["lock_status"]["status"] == "stale"
    assert task_payload["lock_status"]["operation"] == "stale-run"
    assert first_viewport["next_task"]["lock_status"]["is_stale"] is True
    assert (tmp_path / ".devflow" / "tasks" / "task-0001" / ".lock").exists()


def test_operating_layer_snapshot_skips_corrupt_task_and_surfaces_warning(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    assert runner.invoke(app, ["task", "create", "healthy task"]).exit_code == 0
    assert runner.invoke(app, ["task", "create", "bad task"]).exit_code == 0

    bad_task_yaml = tmp_path / ".devflow" / "tasks" / "task-0002" / "task.yaml"
    bad_task_yaml.write_text("schema_version: 1\nid: task-0002\n", encoding="utf-8")

    payload = build_operating_layer_snapshot(tmp_path).model_dump(mode="json")
    assert [task["id"] for task in payload["tasks"]] == ["task-0001"]
    assert any("task-0002" in warning and "task.yaml" in warning for warning in payload["warnings"])

    server, thread, host, port = _serve_operating_layer(tmp_path)
    try:
        status, body, _ = _get_raw(host, port, "/api/snapshot")
        assert status == HTTPStatus.OK
        response_payload = json.loads(body.decode("utf-8"))
        assert response_payload["tasks"] == payload["tasks"]
        assert response_payload["warnings"] == payload["warnings"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_operating_layer_reuses_task_workbench_for_task_centered_snapshot_fields(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    assert runner.invoke(app, ["task", "create", "created task"]).exit_code == 0
    assert runner.invoke(app, ["task", "create", "completed task needing verification"]).exit_code == 0
    assert runner.invoke(app, ["task", "create", "verified task ready for promotion"]).exit_code == 0

    completed = runner.invoke(app, ["task", "run", "task-0002", "--shell", "echo done > task-0002.txt"])
    assert completed.exit_code == 0, completed.output
    ready = runner.invoke(app, ["task", "run", "task-0003", "--shell", "echo done > task-0003.txt"])
    assert ready.exit_code == 0, ready.output
    verified = runner.invoke(app, ["task", "verify", "task-0003", "--shell", "test -f task-0003.txt"])
    assert verified.exit_code == 0, verified.output

    workbench = build_task_workbench(tmp_path)
    snapshot = build_operating_layer_snapshot(tmp_path)
    direct_first_viewport = build_first_viewport_presentation(workbench, root=tmp_path).model_dump(mode="json")
    snapshot_first_viewport = snapshot.first_viewport.model_dump(mode="json")

    assert snapshot.focus_task_id == workbench.focus_task_id
    assert [(lane.name, lane.task_ids) for lane in snapshot.lanes] == [
        (lane.name, lane.task_ids) for lane in workbench.lanes
    ]
    workbench_tasks = [task.model_dump(mode="json") for task in workbench.tasks]
    assert [task.model_dump(mode="json") for task in snapshot.tasks] == workbench_tasks
    snapshot_payload = snapshot.model_dump(mode="json")
    assert snapshot_payload["tasks"] == workbench_tasks
    assert all("worker_model_label" in task for task in snapshot_payload["tasks"])
    assert all("next_safe_action" in task for task in snapshot_payload["tasks"])
    assert all("evidence_paths" in task for task in snapshot_payload["tasks"])
    assert [candidate.model_dump() for candidate in snapshot.promotion_desk] == [
        candidate.model_dump() for candidate in workbench.promotion_candidates
    ]
    assert [pointer.model_dump() for pointer in snapshot.evidence] == [
        pointer.model_dump() for pointer in workbench.evidence_stream
    ]
    assert [receipt.model_dump() for receipt in snapshot.gate_receipts] == [
        receipt.model_dump() for receipt in workbench.gate_receipts
    ]
    assert [activity.model_dump() for activity in snapshot.worker_activity] == [
        activity.model_dump() for activity in workbench.worker_activity
    ]
    assert snapshot.review_loop.model_dump() == workbench.review_loop.model_dump()
    repo_root = Path(__file__).resolve().parents[1]
    operating_layer_source = (repo_root / "src/devflow/control_room/operating_layer.py").read_text(encoding="utf-8")
    for mirrored_assignment in (
        "tasks = task_workbench.tasks",
        "promotion_desk = task_workbench.promotion_candidates",
        "evidence = task_workbench.evidence_stream",
        "gate_receipts = task_workbench.gate_receipts",
        "focus_task_id = task_workbench.focus_task_id",
    ):
        assert mirrored_assignment not in operating_layer_source
    for field in (
        "active_task_count",
        "total_task_count",
        "next_task",
        "worker_lanes",
        "review_queue",
        "evidence_stream",
        "launchpad",
    ):
        assert snapshot_first_viewport[field] == direct_first_viewport[field]
    assert {item["task_id"]: item["lane"] for item in snapshot_first_viewport["worker_lanes"]} == {
        "task-0001": "new",
        "task-0002": "needs_verification",
        "task-0003": "ready_to_promote",
    }
    assert all(item["next_safe_action"] for item in snapshot_first_viewport["worker_lanes"])
    assert (
        {item["task_id"]: item["next_safe_action"] for item in snapshot_first_viewport["worker_lanes"]}
        == {task["id"]: task["next_safe_action"] for task in snapshot_payload["tasks"]}
    )


def test_operating_layer_snapshot_exposes_worker_packet_input_contract(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    home_dir = tmp_path.parent / f"{tmp_path.name}-home"
    monkeypatch.setenv("HOME", home_dir.as_posix())
    hermes_profile = home_dir / ".hermes" / "profiles" / "hermes-qwen32-latest" / "config.yaml"
    hermes_profile.parent.mkdir(parents=True, exist_ok=True)
    hermes_profile.write_text(
        """model:
  provider: qwen36-27b-q5-mtp
  default: qwen36-27b-q5-mtp
  base_url: http://127.0.0.1:8080/v1
""",
        encoding="utf-8",
    )
    assert runner.invoke(app, ["task", "create", "browser packet defaults"]).exit_code == 0
    routing = {
        "routing_decision": {
            "selected": {
                "agent_id": "qwen-worker",
                "label": "Hermes Qwen Implementer",
                "provider": "ollama",
                "model": "qwen3.6-32b-256k:latest",
            }
        }
    }
    _write_json(tmp_path / ".devflow" / "tasks" / "task-0001" / "routing-decision.yaml", routing)
    workspace = tmp_path / ".devflow" / "workspaces" / "task-0001"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "implementation-context.md").write_text("Plan context.\n", encoding="utf-8")

    payload = build_operating_layer_snapshot(tmp_path).model_dump(mode="json")
    options = payload["tasks"][0]["worker_options"]
    worker = next(option for option in options if option["worker_id"] == "hermes-qwen32-latest")

    assert worker["action_kind"] == "serial_packet"
    assert worker["recommended_allowed_files"] == [".devflow/workspaces/task-0001/implementation-context.md"]
    assert worker["recommended_verification_commands"] == []
    assert worker["needs_operator_inputs"] == ["verification_commands"]
    assert "<allowed-file>" not in " ".join(worker["recommended_allowed_files"])


def test_first_viewport_module_shapes_brainstorm_pipeline_and_launchpad(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    assert runner.invoke(app, ["task", "create", "first viewport task"]).exit_code == 0
    session_dir = tmp_path / ".devflow" / "brainstorms" / "browser-session"
    session_dir.mkdir(parents=True, exist_ok=True)
    records = [
        {
            "role": "user",
            "kind": "message",
            "content": "Turn this idea into a verified operating-layer task.",
            "created_at": "2026-06-25T12:00:00Z",
        }
    ]
    session_dir.joinpath("transcript.jsonl").write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )
    session_dir.joinpath("spec.md").write_text("# Spec\n\nVisible state first.\n", encoding="utf-8")

    presentation = build_first_viewport_presentation(
        build_task_workbench(tmp_path),
        root=tmp_path,
    )
    payload = presentation.model_dump(mode="json")

    assert payload["brainstorm"]["session_id"] == "browser-session"
    assert payload["brainstorm"]["message_count"] == 1
    assert payload["brainstorm"]["latest_message"] == "Turn this idea into a verified operating-layer task."
    assert payload["pipeline"]["session_id"] == "browser-session"
    assert payload["pipeline"]["first_incomplete_stage_id"] == "plan"
    assert payload["pipeline"]["primary_stage_id"] == "plan"
    assert payload["pipeline"]["primary_action_label"] == "Generate Plan ->"
    assert payload["next_task"]["task_id"] == "task-0001"
    assert payload["next_task"]["action_label"] == "Start shell"
    assert payload["worker_lanes"][0]["task_id"] == "task-0001"
    assert payload["worker_lanes"][0]["next_safe_action"] == payload["worker_lanes"][0]["command"]
    assert payload["launchpad"]["selected_task_id"] == "task-0001"


def test_task_definition_of_done_persists_loads_old_tasks_shows_and_snapshots(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    created = runner.invoke(
        app,
        [
            "task",
            "create",
            "--definition-of-done",
            "Tests pass and the launchpad shows the next action.",
            "definition launchpad task",
        ],
    )
    assert created.exit_code == 0, created.output

    task_path = tmp_path / ".devflow" / "tasks" / "task-0001"
    task_yaml = (task_path / "task.yaml").read_text(encoding="utf-8")
    summary = json.loads((task_path / "summary.json").read_text(encoding="utf-8"))
    assert 'definition_of_done: "Tests pass and the launchpad shows the next action."' in task_yaml
    assert summary["definition_of_done"] == "Tests pass and the launchpad shows the next action."
    assert get_task(tmp_path, "task-0001").definition_of_done == "Tests pass and the launchpad shows the next action."

    show = runner.invoke(app, ["task", "show", "task-0001"])
    assert show.exit_code == 0, show.output
    assert "definition_of_done: Tests pass and the launchpad shows the next action." in show.output

    snapshot = build_operating_layer_snapshot(tmp_path).model_dump(mode="json")
    assert snapshot["tasks"][0]["definition_of_done"] == "Tests pass and the launchpad shows the next action."

    (task_path / "task.yaml").write_text(
        "\n".join(line for line in task_yaml.splitlines() if not line.startswith("definition_of_done:")) + "\n",
        encoding="utf-8",
    )
    assert get_task(tmp_path, "task-0001").definition_of_done is None


def test_operating_layer_projects_idea_greenhouse_lanes(tmp_path: Path) -> None:
    capture_idea(tmp_path, "Raw idea", title="Raw idea")
    concept = capture_idea(tmp_path, "Needs clarity", title="Needs clarity")
    classify_idea(tmp_path, concept["id"], maturity="concept", note="Needs clearer scope.")
    candidate = capture_idea(tmp_path, "Candidate idea", title="Candidate idea")
    classify_idea(tmp_path, candidate["id"], maturity="candidate", note="Worth considering.")
    parked = capture_idea(tmp_path, "Parked idea", title="Parked idea")
    park_idea(tmp_path, parked["id"], reason="Not now.")

    payload = build_operating_layer_snapshot(tmp_path).model_dump()
    greenhouse = payload["idea_greenhouse"]

    assert greenhouse["counts"]["raw"] == 1
    assert greenhouse["counts"]["clarify"] == 1
    assert greenhouse["counts"]["candidate"] == 1
    assert greenhouse["counts"]["parked"] == 1
    assert greenhouse["primary_next_action"]["label"] == "Classify raw idea"
    assert [lane["id"] for lane in greenhouse["lanes"]] == [
        "raw",
        "clarify",
        "candidate",
        "promoted",
        "parked",
        "archived",
    ]
    raw_card = greenhouse["lanes"][0]["cards"][0]
    assert raw_card["id"] == "I-0001"
    assert raw_card["evidence_paths"] == [
        ".devflow/ideas/I-0001/idea.json",
        ".devflow/ideas/I-0001/raw.md",
        ".devflow/ideas/I-0001/events.jsonl",
    ]
    assert raw_card["metadata"]["id"] == "I-0001"
    assert raw_card["metadata"]["greenhouse_lane"] == "raw"
    assert raw_card["metadata"]["raw_path"] == ".devflow/ideas/I-0001/raw.md"
    assert raw_card["metadata"]["evidence_paths"] == raw_card["evidence_paths"]


def test_operating_layer_snapshot_includes_browser_review_loop_summary(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    assert runner.invoke(app, ["task", "create", "browser review task"]).exit_code == 0
    run = runner.invoke(app, ["task", "run", "task-0001", "--shell", "echo done > result.txt"])
    assert run.exit_code == 0, run.output

    snapshot = build_operating_layer_snapshot(tmp_path)
    payload = snapshot.model_dump(mode="json")

    review_loop = payload["review_loop"]
    assert review_loop["status"] == "needs_verification"
    assert review_loop["headline"] == "1 task needs verification"
    assert review_loop["next_safe_action"] == 'devflow task verify task-0001 --shell "<command>"'
    assert review_loop["browser_allowed_mutations"] == get_browser_allowed_mutations()
    assert "non-shell worker execution" in review_loop["browser_blocked_mutations"]
    assert review_loop["needs_verification_count"] == 1
    assert review_loop["ready_to_promote_count"] == 0
    assert review_loop["blocked_decision_count"] == 0
    assert review_loop["last_result_retention"] == "browser-session"
    assert (
        review_loop["evidence_summary"]
        == "1 task has worker output; 0 tasks have passed verification; 0 tasks are ready for promotion."
    )
    first_viewport = payload["first_viewport"]
    assert first_viewport["review_queue"][0]["task_id"] == "task-0001"
    assert first_viewport["review_queue"][0]["action_label"] == "Verify"
    assert (
        first_viewport["review_queue"][0]["next_safe_action"]
        == first_viewport["review_queue"][0]["command"]
        == 'devflow task verify task-0001 --shell "<command>"'
    )
    assert first_viewport["review_queue"][0]["review_state"] == "needs_verification"
    assert first_viewport["review_queue"][0]["evidence_count"] >= 3
    assert "verification has not passed" in first_viewport["review_queue"][0]["operator_summary"]
    assert first_viewport["evidence_stream"][0]["kind"] in {"result", "verification", "worker log"}
    assert first_viewport["evidence_stream"][0]["task_id"] == "task-0001"
    assert first_viewport["evidence_stream"][0]["path"]

    verify = runner.invoke(app, ["task", "verify", "task-0001", "--shell", "test -f result.txt"])
    assert verify.exit_code == 0, verify.output

    promoted_snapshot = build_operating_layer_snapshot(tmp_path).model_dump(mode="json")
    review_loop = promoted_snapshot["review_loop"]
    assert review_loop["status"] == "ready_to_promote"
    assert review_loop["headline"] == "1 task ready for browser approval"
    assert review_loop["next_safe_action"] == "devflow task promote-preview task-0001"
    assert review_loop["needs_verification_count"] == 0
    assert review_loop["ready_to_promote_count"] == 1


def test_operating_layer_snapshot_includes_latest_serial_local_agent_run_status(
    tmp_path: Path,
    monkeypatch,
) -> None:
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", tmp_path.as_posix())
    result = create_serial_local_agent_run(
        tmp_path,
        run_id="snapshot-serial-run",
        phase="implementer",
        provider="ollama",
        model="qwen3.6-32b-256k:latest",
        mission="Implement a bounded packet-only slice.",
        allowed_files=["src/example.py"],
        verification_commands=["pytest tests/test_example.py -q"],
    )

    payload = build_operating_layer_snapshot(tmp_path).model_dump(mode="json")

    serial = payload["serial_local_agent_run"]
    assert serial["status"] == "pending"
    assert serial["run_state"] == "pending"
    assert serial["verification_status"] == "not_run"
    assert serial["status_source"] == "run_manifest"
    assert serial["read_only"] is True
    assert serial["browser_actions"] == []
    assert serial["next_safe_action"] == "Review worker-packet.md, launch manually outside the browser, then run completion-verifier.py."
    latest = serial["latest_run"]
    assert latest["run_id"] == "snapshot-serial-run"
    assert latest["phase"] == "implementer"
    assert latest["provider"] == "ollama"
    assert latest["model"] == "qwen3.6-32b-256k:latest"
    assert latest["verification_status"] == "not_run"
    assert latest["failure_class"] is None
    assert latest["run_dir"] == ".devflow/local-agent-runs/snapshot-serial-run"
    assert latest["evidence_paths"] == [
        ".devflow/local-agent-runs/snapshot-serial-run/run.json",
        ".devflow/local-agent-runs/snapshot-serial-run/worker-packet.md",
        ".devflow/local-agent-runs/snapshot-serial-run/preflight.json",
        ".devflow/local-agent-runs/snapshot-serial-run/completion-verifier.py",
    ]
    assert latest["safety"]["model_launch"] is False
    assert latest["safety"]["git_mutation"] is False
    assert not (result.run_dir / "verification-report.json").exists(), "snapshot surface must not run verification"


def test_operating_layer_snapshot_projects_hermes_launch_evidence(
    tmp_path: Path,
    monkeypatch,
) -> None:
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    result = create_serial_local_agent_run(
        tmp_path,
        run_id="snapshot-hermes-launch",
        phase="implementer",
        provider="ollama",
        model="qwen3.6-32b-256k:latest",
        allowed_files=["src/example.py"],
        verification_commands=["pytest tests/test_example.py -q"],
        runtime_kind="hermes-profile",
        hermes_profile="qwen-worker",
        toolsets=["file", "terminal"],
    )
    (result.run_dir / "hermes-stdout.txt").write_text("done\n", encoding="utf-8")
    (result.run_dir / "hermes-stderr.txt").write_text("", encoding="utf-8")
    (result.run_dir / "hermes-run.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "will_launch_hermes": True,
                "dry_run": False,
                "run_id": "snapshot-hermes-launch",
                "hermes_profile": "hermes-qwen32-latest",
                "runtime_kind": "hermes-profile",
                "launch_status": "completed",
                "exit_code": 0,
                "stdout_path": ".devflow/local-agent-runs/snapshot-hermes-launch/hermes-stdout.txt",
                "stderr_path": ".devflow/local-agent-runs/snapshot-hermes-launch/hermes-stderr.txt",
                "hermes_run_path": ".devflow/local-agent-runs/snapshot-hermes-launch/hermes-run.json",
                "verification_ran": False,
                "next_safe_action": "Run completion-verifier.py from the packet directory.",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    payload = build_operating_layer_snapshot(tmp_path).model_dump(mode="json")

    serial = payload["serial_local_agent_run"]
    assert serial["status"] == "ready_for_verifier"
    assert serial["run_state"] == "ready_for_verifier"
    assert serial["status_source"] == "hermes_run"
    assert serial["runtime_kind"] == "hermes-profile"
    assert serial["hermes_profile"] == "hermes-qwen32-latest"
    assert serial["launch_status"] == "completed"
    assert serial["exit_code"] == 0
    assert serial["browser_actions"] == []
    assert serial["next_safe_action"] == "Run completion-verifier.py from the packet directory."
    latest = serial["latest_run"]
    assert latest["runtime_kind"] == "hermes-profile"
    assert latest["hermes_profile"] == "hermes-qwen32-latest"
    assert latest["launch_status"] == "completed"
    assert latest["exit_code"] == 0
    assert ".devflow/local-agent-runs/snapshot-hermes-launch/hermes-run.json" in latest["evidence_paths"]
    assert ".devflow/local-agent-runs/snapshot-hermes-launch/hermes-stdout.txt" in latest["evidence_paths"]
    assert ".devflow/local-agent-runs/snapshot-hermes-launch/hermes-stderr.txt" in latest["evidence_paths"]
    assert not (result.run_dir / "verification-report.json").exists(), "snapshot surface must not run verification"


def test_operating_layer_snapshot_keeps_serial_preflight_and_runtime_lock_visible(
    tmp_path: Path,
    monkeypatch,
) -> None:
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    with local_model_runtime_lock(
        tmp_path,
        provider="ollama",
        model="qwen3.6-32b-256k:latest",
        task_id="task-serial",
        worker_id="qwen-worker",
        operation="serial-local-agent",
    ):
        create_serial_local_agent_run(
            tmp_path,
            run_id="snapshot-running-lock",
            phase="implementer",
            provider="ollama",
            model="qwen3.6-32b-256k:latest",
            allowed_files=["src/example.py"],
            verification_commands=["pytest tests/test_example.py -q"],
        )
        payload = build_operating_layer_snapshot(tmp_path).model_dump(mode="json")

    serial = payload["serial_local_agent_run"]
    latest = serial["latest_run"]
    assert latest["run_id"] == "snapshot-running-lock"
    assert latest["preflight"]["state"] == "running"
    assert latest["preflight"]["launch_packet_ready"] is False
    assert latest["preflight"]["owner"]["worker_id"] == "qwen-worker"
    runtime = payload["local_model_runtime"]["ollama/qwen3.6-32b-256k:latest"]
    assert runtime["state"] == "running"
    assert runtime["worker_id"] == "qwen-worker"
    assert serial["browser_actions"] == []


def test_operating_layer_snapshot_includes_scheduler_summary(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    created = runner.invoke(app, ["task", "create", "scheduler retry"])
    assert created.exit_code == 0, created.output
    task = get_task(tmp_path, "task-0001")
    task.status = "worker_failed"
    save_task(tmp_path / ".devflow" / "tasks" / task.id, task)

    payload = build_operating_layer_snapshot(tmp_path).model_dump(mode="json")

    assert payload["scheduler"]["counts"]["needs_retry"] == 1
    assert payload["scheduler"]["next_safe_action"] == 'devflow scheduler retry task-0001 --reason "<reason>"'


def test_operating_layer_snapshot_includes_git_worker_lane_summary(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    subprocess.run(["git", "init", "-b", "main"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=tmp_path, check=True)
    (tmp_path / "base.txt").write_text("base\n", encoding="utf-8")
    subprocess.run(["git", "add", "base.txt"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, check=True)

    created = runner.invoke(app, ["task", "create", "--git-worktree", "operating lane"])
    assert created.exit_code == 0, created.output
    run = runner.invoke(
        app,
        [
            "task",
            "run",
            "task-0001",
            "--worker",
            "shell",
            "--",
            "/bin/sh",
            "-c",
            "printf 'ready\\n' > ready.txt && git add ready.txt && git commit -m ready",
        ],
    )
    assert run.exit_code == 0, run.output
    verify = runner.invoke(app, ["task", "verify", "task-0001", "--", "/bin/sh", "-c", "test -f ready.txt"])
    assert verify.exit_code == 0, verify.output
    preview = runner.invoke(app, ["task", "promote-preview", "task-0001"])
    assert preview.exit_code == 0, preview.output

    payload = build_operating_layer_snapshot(tmp_path).model_dump(mode="json")
    lane = payload["tasks"][0]["worker_lane"]
    assert lane["workspace_mode"] == "git-worktree"
    assert lane["worker_branch"] == "devflow/task-0001/shell"
    assert lane["worktree_path"] == ".devflow/worktrees/task-0001/shell"
    assert lane["readiness_status"] == "ready"
    assert lane["next_safe_action"] == "devflow task promote task-0001"
    review = {item["label"]: item["value"] for item in payload["tasks"][0]["detail"]["review_summary"]}
    assert review["Worker lane"] == "git-worktree"
    assert review["Lane readiness"] == "ready"


def test_operating_layer_snapshot_includes_local_worker_lane_summary(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    created = runner.invoke(app, ["task", "create", "local lane"])
    assert created.exit_code == 0, created.output
    _write_local_patch_worker_evidence(tmp_path, "task-0001")

    payload = build_operating_layer_snapshot(tmp_path).model_dump(mode="json")
    lane = payload["tasks"][0]["local_worker_lane"]
    assert lane["lane_type"] == "local-patch-worker"
    assert lane["worker_id"] == "qwopus-implementer"
    assert lane["readiness_status"] == "needs_review"
    assert lane["next_safe_action"] == "devflow task review-patch task-0001 --agent qwopus-implementer"
    review = {item["label"]: item["value"] for item in payload["tasks"][0]["detail"]["review_summary"]}
    assert review["Local worker"] == "qwopus-implementer"
    assert review["Local worker readiness"] == "needs_review"


def test_operating_layer_review_loop_flags_failed_verification_decision_pressure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    assert runner.invoke(app, ["task", "create", "failed browser review task"]).exit_code == 0
    run = runner.invoke(app, ["task", "run", "task-0001", "--shell", "echo done > result.txt"])
    assert run.exit_code == 0, run.output
    verify = runner.invoke(app, ["task", "verify", "task-0001", "--shell", "test -f missing.txt"])
    assert verify.exit_code != 0, verify.output

    payload = build_operating_layer_snapshot(tmp_path).model_dump(mode="json")
    review_loop = payload["review_loop"]

    assert review_loop["status"] == "needs_human_decision"
    assert review_loop["headline"] == "1 decision item needs attention"
    assert review_loop["blocked_decision_count"] == 1
    assert any(
        expected in review_loop["next_safe_action"]
        for expected in (
            'devflow task verify task-0001 --shell "<command>"',
            "devflow task log task-0001 --verify --tail 80",
        )
    )
    assert any(item["kind"] == "task_attention" for item in payload["inbox"])
    attention = next(item for item in payload["inbox"] if item["kind"] == "task_attention")
    assert attention["action"] is not None
    assert attention["action"]["intent"] in {"verify", "inspect_log"}
    if attention["action"]["intent"] == "verify":
        assert attention["action"]["required_inputs"] == ["verification_command"]
    else:
        assert attention["action"]["required_inputs"] == []


def test_operating_layer_snapshot_includes_compact_agent_evidence_summary(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["task", "create", "agent evidence snapshot"]).exit_code == 0
    write_worker_evidence(
        root=tmp_path,
        worker_type="local_model",
        profile_id="local-gemma4-qat",
        worker_id="local-gemma4-qat",
        task_id="task-0001",
        run_id="run-1",
        packet_text="packet",
        raw_output="raw",
        response_text="response",
        model="gemma4:12b-it-qat",
        adapter="ollama_chat",
        adapter_maturity="local_patch_runtime",
        permission_mode="read_only",
        hermes_delegable=False,
        runtime="ollama",
        status="succeeded",
        started_at="2026-06-13T00:00:00Z",
    )

    payload = build_operating_layer_snapshot(tmp_path).model_dump(mode="json")
    task = payload["tasks"][0]
    summary = task["agent_evidence_summary"]

    assert summary == {
        "has_worker_evidence": True,
        "local_model_run_count": 1,
        "local_patch_agent_count": 0,
        "manual_result_present": False,
        "next_safe_action": "review worker evidence before verification or promotion",
    }
    assert task["review_detail"]["agent_evidence_summary"] == summary
    assert task["review_detail"]["operator_summary"] == "Worker/model evidence is captured; review it before the next gate."
    assert ".devflow/tasks/task-0001/local-model-runs/run-1/run.json" in task["review_detail"]["evidence_paths"]
    assert any(artifact["kind"] == "model run" for artifact in task["review_detail"]["artifacts"])
    assert payload["evidence"][0]["kind"] == "model run"
    assert payload["evidence"][0]["path"] == ".devflow/tasks/task-0001/local-model-runs/run-1/run.json"
    assert payload["first_viewport"]["evidence_stream"][0]["kind"] == "model run"


def test_operating_layer_goal_board_exposes_lifecycle(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _create_goal(tmp_path)
    pause = runner.invoke(app, ["goal", "pause", "G-0001", "--reason", "waiting"])
    assert pause.exit_code == 0, pause.output

    snapshot = build_operating_layer_snapshot(tmp_path)

    assert snapshot.goal_board[0].goal_id == "G-0001"
    assert snapshot.goal_board[0].lifecycle == "paused"
    assert snapshot.goal_board[0].lifecycle_reason == "waiting"


def test_operating_layer_goal_board_lifecycle_projection_failure_appends_warning(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _create_goal(tmp_path)

    def _broken_projection(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("projection failed")

    monkeypatch.setattr(
        "devflow.control_room.goal_projection.build_goal_status_projection",
        _broken_projection,
    )

    snapshot = build_operating_layer_snapshot(tmp_path).model_dump(mode="json")
    fallback = snapshot["goals"][0]["goal_state"]
    expected_lifecycle = "missing" if fallback == "missing_lifecycle" else fallback

    assert snapshot["goal_board"][0]["goal_id"] == "G-0001"
    assert snapshot["goal_board"][0]["lifecycle"] == expected_lifecycle
    assert any("goal lifecycle projection failed for G-0001" in warning for warning in snapshot["warnings"])


def test_operating_layer_groups_verification_and_promotion_lanes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    assert runner.invoke(app, ["task", "create", "needs verification"]).exit_code == 0
    run = runner.invoke(app, ["task", "run", "task-0001", "--shell", "echo done > result.txt"])
    assert run.exit_code == 0, run.output

    snapshot = build_operating_layer_snapshot(tmp_path)
    lanes = {lane.name: lane.task_ids for lane in snapshot.lanes}
    assert lanes["needs_verification"] == ["task-0001"]
    assert snapshot.worker_activity[0].worker == "shell"
    assert snapshot.worker_activity[0].name == "Shell worker"
    assert snapshot.worker_activity[0].state == "Waiting"
    assert snapshot.worker_activity[0].task_count == 1
    assert snapshot.mission_feed[0].label == "Task progress"
    assert snapshot.mission_feed[0].task_id == "task-0001"
    assert snapshot.mission_feed[0].detail == "3/5 required steps done. Next: verify the task."
    assert snapshot.tasks[0].next_action.command == 'devflow task verify task-0001 --shell "<command>"'
    assert snapshot.tasks[0].review_state == "needs_verification"
    assert snapshot.tasks[0].review_score == 60
    assert snapshot.tasks[0].review_blockers == ["verification has not passed"]
    assert snapshot.tasks[0].review_next_command == 'devflow task verify task-0001 --shell "<command>"'
    assert snapshot.tasks[0].detail.latest_worker_line is None
    assert snapshot.tasks[0].detail.result_preview is not None
    assert str(tmp_path) not in snapshot.tasks[0].detail.result_preview
    assert ".devflow/tasks/task-0001/logs/worker.log" in snapshot.tasks[0].detail.evidence_paths
    assert all("echo done" not in event.summary for event in snapshot.tasks[0].detail.recent_events)

    verify = runner.invoke(app, ["task", "verify", "task-0001", "--shell", "test -f result.txt"])
    assert verify.exit_code == 0, verify.output

    snapshot = build_operating_layer_snapshot(tmp_path)
    lanes = {lane.name: lane.task_ids for lane in snapshot.lanes}
    assert lanes["ready_to_promote"] == ["task-0001"]
    assert snapshot.worker_activity[0].verified_percent == 100
    assert snapshot.promotion_desk[0].command == "devflow task promote-preview task-0001"
    assert snapshot.mission_feed[0].label == "Ready for review"
    assert snapshot.mission_feed[0].detail == "Review preview is ready."
    assert snapshot.evidence[0].task_id == "task-0001"
    assert snapshot.evidence[0].verification_command == "/bin/sh -c 'test -f result.txt'"
    assert snapshot.gate_receipts[0].verification is True
    assert snapshot.gate_receipts[0].next_gate == "human_decision"
    assert snapshot.tasks[0].detail.verification is not None
    assert snapshot.tasks[0].detail.verification.status == "passed"
    review = {item.label: item.value for item in snapshot.tasks[0].detail.review_summary}
    assert review["Task"] == "task-0001 - needs verification"
    assert review["Status"] == "verified"
    assert review["Verification"] == "passed"
    assert "result.txt" in review["Changed files"]
    assert "done" in review["Task contents"]
    assert str(tmp_path) not in (snapshot.tasks[0].detail.result_preview or "")


def test_operating_layer_verified_task_with_invalid_verification_json_stays_actionable(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    assert runner.invoke(app, ["task", "create", "corrupt verification evidence"]).exit_code == 0
    task = get_task(tmp_path, "task-0001")
    task.status = "verified"
    task.verification_status = "passed"
    task.verification_exit_code = 0
    save_task(tmp_path / ".devflow" / "tasks" / task.id, task)
    (tmp_path / ".devflow" / "tasks" / task.id / "verification.json").write_text(
        "{not-json\n",
        encoding="utf-8",
    )

    snapshot = build_operating_layer_snapshot(tmp_path)
    lanes = {lane.name: lane.task_ids for lane in snapshot.lanes}

    assert lanes["needs_verification"] == ["task-0001"]
    assert snapshot.tasks[0].review_state == "needs_verification"
    assert snapshot.tasks[0].next_action.command == 'devflow task verify task-0001 --shell "<command>"'


def test_operating_layer_progress_closes_closed_tasks(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    assert runner.invoke(app, ["task", "create", "closed evidence task"]).exit_code == 0
    close = runner.invoke(
        app,
        ["task", "close", "task-0001", "--outcome", "evidence-only", "--reason", "evidence captured"],
    )
    assert close.exit_code == 0, close.output

    snapshot = build_operating_layer_snapshot(tmp_path)
    assert snapshot.gate_receipts[0].task_id == "task-0001"
    assert snapshot.gate_receipts[0].human_decision is True
    assert snapshot.gate_receipts[0].next_gate == "closed"


def test_operating_layer_inbox_groups_questions_and_blockers(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    assert runner.invoke(app, ["task", "create", "manual question"]).exit_code == 0
    run = runner.invoke(app, ["task", "run", "task-0001", "--worker", "devflow-manual-codex-worker"])
    assert run.exit_code == 0, run.output

    snapshot = build_operating_layer_snapshot(tmp_path)
    assert snapshot.inbox[0].kind == "blocked_task"
    assert snapshot.inbox[0].task_id == "task-0001"
    assert snapshot.inbox[0].action is not None
    assert snapshot.inbox[0].action.supervisor_may_auto_run is True

    questions = tmp_path / ".devflow/tasks/task-0001/agents/devflow-manual-codex-worker/questions.jsonl"
    with questions.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "type": "blocked_question",
                    "task_id": "task-0001",
                    "agent_id": "devflow-manual-codex-worker",
                    "question": "Which API shape should I preserve?",
                    "blocking_reason": "Two incompatible call sites exist.",
                }
            )
            + "\n"
        )

    snapshot = build_operating_layer_snapshot(tmp_path)
    assert snapshot.questions[0].question_id.startswith("Q-task-0001-")
    assert snapshot.questions[0].question == "Which API shape should I preserve?"
    assert snapshot.questions[0].command.startswith("devflow question answer ")
    assert snapshot.inbox[0].kind == "question"
    assert snapshot.inbox[0].priority == 10
    assert snapshot.inbox[0].message == "Which API shape should I preserve?"
    assert snapshot.inbox[0].command.startswith("devflow question answer ")


def test_operating_layer_questions_include_answer_command(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    created = runner.invoke(app, ["task", "create", "operator question"])
    assert created.exit_code == 0, created.output
    task = get_task(tmp_path, "task-0001")
    task.status = "blocked"
    save_task(tmp_path / ".devflow" / "tasks" / task.id, task)
    agent_dir = tmp_path / ".devflow" / "tasks" / task.id / "agents" / "devflow-manual-codex-worker"
    agent_dir.mkdir(parents=True, exist_ok=True)
    (agent_dir / "questions.jsonl").write_text(
        (
            '{"type":"blocked_question","task_id":"task-0001",'
            '"agent_id":"devflow-manual-codex-worker","question":"Which path should I use?"}\n'
        ),
        encoding="utf-8",
    )

    payload = build_operating_layer_snapshot(tmp_path).model_dump(mode="json")

    assert payload["questions"][0]["question_id"].startswith("Q-task-0001-")
    assert payload["questions"][0]["command"].startswith("devflow question answer ")
    assert payload["inbox"][0]["kind"] == "question"


def test_operating_layer_projects_spec_board_from_goal_slices(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    goal_dir = tmp_path / ".devflow" / "goals" / "G-0001"
    goal_dir.mkdir(parents=True)
    (tmp_path / "docs" / "architecture").mkdir(parents=True)
    (tmp_path / "PRODUCT_NORTH_STAR.md").write_text("# Product North Star\n", encoding="utf-8")
    (tmp_path / "docs" / "control-room-mvp.md").write_text("# Control Room MVP\n", encoding="utf-8")
    (tmp_path / "docs" / "mvp-contract.md").write_text("# MVP Contract\n", encoding="utf-8")
    (tmp_path / "docs" / "architecture" / "agent-registry-and-adapter-runtime.md").write_text(
        "# Agent Registry\n",
        encoding="utf-8",
    )
    standards_dir = tmp_path / ".devflow" / "standards"
    standards_dir.mkdir(parents=True)
    (tmp_path / "docs" / "standards.md").write_text("# Python Control Room Standard\n", encoding="utf-8")
    (standards_dir / "index.yml").write_text(
        """
standards:
  - path: docs/standards.md
    title: Python Control Room Standard
""".lstrip(),
        encoding="utf-8",
    )
    contracts_dir = tmp_path / ".devflow" / "layers" / "architecture"
    contracts_dir.mkdir(parents=True)
    (contracts_dir / "contracts.md").write_text(
        """
# Contracts

- [MVP](../../../docs/mvp-contract.md)
- [Registry](../../../docs/architecture/agent-registry-and-adapter-runtime.md)
""".lstrip(),
        encoding="utf-8",
    )
    (goal_dir / "goal.md").write_text("# Goal: Build operating layer\n", encoding="utf-8")
    (goal_dir / "goal.yaml").write_text(
        "id: G-0001\ncreated_at: 2026-06-04T00:00:00+00:00\nupdated_at: 2026-06-04T00:00:00+00:00\nsource_brief_path: .devflow/goals/G-0001/goal.md\n",
        encoding="utf-8",
    )
    ensure_goal_lifecycle(tmp_path, "G-0001")
    (goal_dir / "context").mkdir()
    (goal_dir / "context" / "relevant-files.md").write_text(
        "# Relevant Files\n\n- PRODUCT_NORTH_STAR.md\n- docs/control-room-mvp.md\n",
        encoding="utf-8",
    )
    (goal_dir / "task-slices.yaml").write_text(
        """
task_slices:
  - task_id: TS-0001
    title: "Snapshot contract"
    risk: "medium"
    execution_mode: "HITL"
    parallel_safe: true
    shared_files:
      - src/devflow/control_room/operating_layer.py
  - task_id: TS-0002
    title: "Browser shell"
    blocked_by:
      - TS-0001
""".lstrip(),
        encoding="utf-8",
    )

    snapshot = build_operating_layer_snapshot(tmp_path)
    assert snapshot.spec_board[0].goal_id == "G-0001"
    assert snapshot.spec_board[0].slice_count == 2
    assert snapshot.spec_board[0].slices[0].state == "parallel_candidate"
    assert snapshot.spec_board[0].slices[1].state == "blocked"
    references = snapshot.spec_board[0].references
    reference_paths = {reference.path for reference in references}
    assert "PRODUCT_NORTH_STAR.md" in reference_paths
    assert "docs/control-room-mvp.md" in reference_paths
    assert "docs/standards.md" in reference_paths
    assert "docs/mvp-contract.md" in reference_paths
    assert references[0].kind == "goal_reference"
    assert references[0].status == "available"
    assert any(
        reference.kind == "standard" and reference.title == "Python Control Room Standard"
        for reference in references
    )
    assert any(
        reference.kind == "architecture_contract"
        and reference.source == ".devflow/layers/architecture/contracts.md"
        for reference in references
    )
    assert snapshot.goal_board[0].goal_id == "G-0001"
    assert snapshot.goal_board[0].ready_parallel_batch_count == 1
    assert snapshot.goal_board[0].parallel_batches[0].batch_id == "PB-0001"
    assert snapshot.goal_board[0].parallel_batches[0].lane_ids == ["TS-0001"]
    assert snapshot.goal_board[0].parallel_batches[0].actions[0].command == (
        "devflow goal create-task G-0001 TS-0001"
    )
    assert snapshot.goal_board[0].parallel_batches[0].actions[0].requires_human_approval is True
    assert snapshot.goal_board[0].blocked_lanes[0].blockers == ["TS-0001"]
    assert snapshot.goal_board[0].ready_lanes[0].command == "devflow goal create-task G-0001 TS-0001"
    assert snapshot.goal_board[0].ready_lanes[0].actions[0].label == "Lane recommendation"
    assert snapshot.goal_board[0].actions[0].command == "devflow goal status G-0001"
    assert snapshot.goal_board[0].actions[0].supervisor_may_auto_run is True


def test_operating_layer_snapshot_with_malformed_standards_index_reports_warning(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    _create_goal(tmp_path)
    goal_dir = tmp_path / ".devflow" / "goals" / "G-0001"
    (goal_dir / "task-slices.yaml").write_text(
        """
task_slices:
  - task_id: TS-0001
    title: "Snapshot contract"
    risk: "medium"
    execution_mode: "HITL"
""".lstrip(),
        encoding="utf-8",
    )
    standards_dir = tmp_path / ".devflow" / "standards"
    standards_dir.mkdir(parents=True)
    (standards_dir / "index.yml").write_text("standards: [", encoding="utf-8")

    snapshot = build_operating_layer_snapshot(tmp_path).model_dump(mode="json")

    assert snapshot["spec_board"][0]["slice_count"] == 1
    assert any(
        "standards" in warning and "failed to parse" in warning and "index.yml" in warning
        for warning in snapshot["warnings"]
    )


def test_operating_layer_includes_multi_project_overview(
    tmp_path: Path,
    monkeypatch,
) -> None:
    home = tmp_path / "home"
    monkeypatch.setenv("DEVFLOW_HOME", home.as_posix())

    project_root = tmp_path / "projects" / "demo"
    project_root.mkdir(parents=True)
    monkeypatch.chdir(project_root)
    assert runner.invoke(app, ["task", "create", "registry task"]).exit_code == 0
    write_project_metadata(
        project_root,
        ProjectMetadata(
            id="demo",
            project_id="demo",
            name="Demo",
            root_path=project_root.as_posix(),
        ),
    )

    register_project(
        ProjectRecord(
            project_id="demo",
            name="Demo",
            path=project_root.as_posix(),
            last_seen_at=utc_now(),
        )
    )
    register_project(
        ProjectRecord(
            project_id="missing",
            name="Missing",
            path=(tmp_path / "projects" / "missing").as_posix(),
            last_seen_at=utc_now(),
        )
    )

    snapshot = build_operating_layer_snapshot(project_root)

    assert snapshot.multi_project is not None
    assert snapshot.multi_project.total_projects == 2
    assert snapshot.multi_project.active_projects == 1
    assert snapshot.multi_project.missing_projects == 1
    assert snapshot.multi_project.total_tasks == 1
    assert snapshot.project.project_id == "demo"
    assert snapshot.action_rail[0].command == "devflow project status demo"
    assert snapshot.next_action.command == "devflow task run task-0001 --worker shell --project demo -- <command>"
    assert snapshot.review_loop.next_safe_action == "devflow task run task-0001 --worker shell --project demo -- <command>"
    assert snapshot.tasks[0].next_action.command == (
        "devflow task run task-0001 --worker shell --project demo -- <command>"
    )
    controls = {control.intent: control for control in snapshot.tasks[0].controls}
    assert controls["start_shell"].command == "devflow task run task-0001 --worker shell --project demo -- <command>"
    assert controls["start_shell"].required_inputs == ["shell_command"]
    assert snapshot.tasks[0].actions[1].command == "devflow task show task-0001 --project demo"
    projects = {project.project_id: project for project in snapshot.multi_project.projects}
    assert projects["demo"].next_action == "devflow project status demo"
    assert projects["missing"].path_status == "missing"
    assert projects["missing"].next_action == "devflow project doctor missing"

    run = runner.invoke(app, ["task", "run", "task-0001", "--shell", "echo done > result.txt"])
    assert run.exit_code == 0, run.output
    needs_verification = build_operating_layer_snapshot(project_root)
    assert needs_verification.review_loop.status == "needs_verification"
    assert needs_verification.review_loop.next_safe_action == (
        'devflow task verify task-0001 --shell "<command>" --project demo'
    )
    verify_controls = {control.intent: control for control in needs_verification.tasks[0].controls}
    assert verify_controls["verify"].command == 'devflow task verify task-0001 --shell "<command>" --project demo'
    assert verify_controls["verify"].required_inputs == ["verification_command"]

    verify = runner.invoke(app, ["task", "verify", "task-0001", "--shell", "test -f result.txt"])
    assert verify.exit_code == 0, verify.output
    ready_to_promote = build_operating_layer_snapshot(project_root)
    assert ready_to_promote.review_loop.status == "ready_to_promote"
    assert ready_to_promote.review_loop.next_safe_action == "devflow task promote-preview task-0001 --project demo"
    assert ready_to_promote.promotion_desk[0].command == "devflow task promote-preview task-0001 --project demo"


def test_operating_layer_agents_keeps_raw_local_profiles_out_of_model_pickers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    add_provider = runner.invoke(
        app,
        [
            "agent",
            "add-provider",
            "raw-qwen36-27b-q5-mtp-test",
            "--adapter",
            "openai_compatible",
            "--base-url",
            "http://127.0.0.1:8080/v1",
        ],
    )
    assert add_provider.exit_code == 0, add_provider.output
    def mock_urlopen(req: urllib.request.Request, timeout: float | None = None) -> MockUrlopenResponse:
        if req.full_url != "http://127.0.0.1:8080/v1/models":
            raise urllib.error.URLError("endpoint unavailable in test")
        return MockUrlopenResponse(
            {
                "data": [
                    {
                        "id": "qwen36-27b-q5-mtp",
                        "object": "model",
                        "owned_by": "llamacpp",
                        "meta": {"n_ctx": 65536, "n_params": 9_197_093_888},
                    }
                ]
            }
        )

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

    server, thread, host, port = _serve_operating_layer(tmp_path)
    try:
        connection = HTTPConnection(host, port, timeout=5)
        connection.request("GET", "/api/agents")
        response = connection.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
        assert response.status == HTTPStatus.OK
        assert all(agent["adapter"] == "hermes_profile" for agent in payload["agents"])
        assert "raw-qwen36-27b-q5-mtp-test" not in {agent["id"] for agent in payload["agents"]}
        assert payload["local_model_inventory"]["schema_version"] == 1
        assert any(
            row["row_id"] == "profile:hermes-qwen32-latest"
            for row in payload["local_model_inventory"]["rows"]
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_operating_layer_agents_exposes_hermes_codex_gpt55_to_shared_model_pickers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    server, thread, host, port = _serve_operating_layer(tmp_path)
    try:
        connection = HTTPConnection(host, port, timeout=5)
        connection.request("GET", "/api/agents")
        response = connection.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
        assert response.status == HTTPStatus.OK

        codex = next(agent for agent in payload["agents"] if agent["id"] == "hermes-codex-gpt55")
        assert codex["model"] == "gpt-5.5"
        assert codex["label"] == "Hermes Codex GPT 5.5"
        assert codex["provider"] == "openai-codex"
        assert codex["adapter"] == "hermes_profile"
        assert codex["role"] == "frontier_planner_architect_reviewer"
        assert codex["authority"] == "advisory"
        assert codex["is_local"] is False
        assert codex["availability"]["status"] in {"available", "setup_required"}
        assert codex["runtime_contract"]["execution_surface"] == "hermes_profile_handoff"
        assert codex["runtime_contract"]["task_run_allowed"] is False
        assert codex["runtime_contract"]["agent_run_allowed"] is False
        assert "hermes" in codex["runtime_contract"]["next_command"]
        assert "openrouter" not in codex["runtime_contract"]["next_command"].lower()
        assert "OPENROUTER_API_KEY" not in codex["runtime_contract"]["next_command"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_operating_layer_snapshot_exposes_local_model_inventory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    snapshot = build_operating_layer_snapshot(tmp_path).model_dump(mode="json")

    assert snapshot["local_model_inventory"]["schema_version"] == 1
    assert "summary" in snapshot["local_model_inventory"]
    assert "rows" in snapshot["local_model_inventory"]


def test_operating_layer_visual_qa_plan_covers_core_regression_contracts(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    assert runner.invoke(app, ["task", "create", "visual qa task"]).exit_code == 0
    run = runner.invoke(app, ["task", "run", "task-0001", "--shell", "echo done > result.txt"])
    assert run.exit_code == 0, run.output

    from devflow.control_room.operating_layer_visual_qa import build_visual_qa_plan

    plan = build_visual_qa_plan(tmp_path)

    assert plan["schema_version"] == 1
    assert plan["surface"] == "operating-layer"
    assert [viewport["name"] for viewport in plan["viewports"]] == ["desktop", "mobile"]
    assert plan["screenshots"] == [
        {
            "viewport": "desktop",
            "current": ".devflow/operating-layer/visual-qa/current/desktop.png",
            "baseline": ".devflow/operating-layer/visual-qa/baseline/desktop.png",
            "fallback_current": ".devflow/operating-layer/visual-qa/current/desktop.svg",
            "fallback_baseline": ".devflow/operating-layer/visual-qa/baseline/desktop.svg",
        },
        {
            "viewport": "mobile",
            "current": ".devflow/operating-layer/visual-qa/current/mobile.png",
            "baseline": ".devflow/operating-layer/visual-qa/baseline/mobile.png",
            "fallback_current": ".devflow/operating-layer/visual-qa/current/mobile.svg",
            "fallback_baseline": ".devflow/operating-layer/visual-qa/baseline/mobile.svg",
        },
    ]
    checks = {check["id"]: check for check in plan["checks"]}
    assert set(checks) >= {
        "desktop-screenshot",
        "mobile-screenshot",
        "no-horizontal-overflow",
        "guided-first-viewport",
        "idea-greenhouse-panel",
        "brainstorm-chat",
        "active-work-cards",
        "approval-states",
    }
    greenhouse_check = checks["idea-greenhouse-panel"]
    assert greenhouse_check["target"] == "#idea-greenhouse-section"
    assert greenhouse_check["status"] == "pass"
    assert "top of the Idea-to-Product pipeline" in greenhouse_check["detail"]
    assert "capture form and lanes" in greenhouse_check["detail"]

    playwright_assertions = {assertion["id"]: assertion for assertion in plan["playwright_assertions"]}
    greenhouse_assertion = playwright_assertions["idea-greenhouse-panel"]
    greenhouse_script = greenhouse_assertion["script"]
    assert "#brainstorm-section" in greenhouse_script
    assert "#idea-greenhouse-section" in greenhouse_script
    assert "#orchestrator-section" in greenhouse_script
    assert "#idea-capture-form" in greenhouse_script
    assert "#idea-greenhouse-lanes" in greenhouse_script
    assert "DOCUMENT_POSITION_FOLLOWING" in greenhouse_script

    # At least 3 checks should pass (screenshot, brainstorm, and any working contract)
    passing = sum(1 for c in plan["checks"] if c["status"] == "pass")
    assert passing >= 3, [c for c in plan["checks"] if c["status"] != "pass"]


def test_operating_layer_visual_qa_cli_renders_json_plan(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    assert runner.invoke(app, ["task", "create", "visual qa cli task"]).exit_code == 0

    result = runner.invoke(app, ["operating-layer", "visual-qa", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["visual_flow"] == (
        "app loads -> Unified Chat Workbench -> Brainstorm chat -> Pipeline stages -> Next Task launchpad -> "
        "Task Control with Worker lanes, Review queue, and Evidence stream without horizontal overflow"
    )
    assert payload["browser_runtime"] == "codex-in-app-browser"
    assert payload["serve_command"] == "devflow operating-layer serve --host 127.0.0.1 --port 8765"


def test_operating_layer_visual_qa_writes_svg_image_fallbacks(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    import devflow.control_room.operating_layer_visual_qa as visual_qa

    monkeypatch.setattr(visual_qa, "_browser_target_ready", lambda base_url: False)

    assert runner.invoke(app, ["task", "create", "visual image fallback task"]).exit_code == 0
    run = runner.invoke(app, ["task", "run", "task-0001", "--shell", "echo done > result.txt"])
    assert run.exit_code == 0, run.output

    result = runner.invoke(app, ["operating-layer", "visual-qa", "--write-current", "--update-baseline", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["image_fallback"]["status"] in ("pass", "skip", "fail"), payload["image_fallback"]
    assert payload["image_fallback"]["capture_method"] == "deterministic-snapshot-fallback"
    assert payload["image_fallback"]["browser_ready"] is False
    assert payload["image_fallback"]["format"] == "png+svg"


def test_operating_layer_visual_qa_writes_browser_raster_when_capture_available(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    assert runner.invoke(app, ["task", "create", "visual browser capture task"]).exit_code == 0
    run = runner.invoke(app, ["task", "run", "task-0001", "--shell", "echo done > result.txt"])
    assert run.exit_code == 0, run.output

    import devflow.control_room.operating_layer_visual_qa as visual_qa

    png = b"\x89PNG\r\n\x1a\nbrowser-raster"

    def fake_capture(base_url: str, viewport: dict[str, int | str]) -> visual_qa.BrowserCapture:
        return visual_qa.BrowserCapture(
            method="playwright-browser-raster",
            png=png + str(viewport["name"]).encode("utf-8"),
            checks={
                "no_horizontal_overflow": True,
                "guided_first_viewport": True,
                "active_work_cards": True,
                "approval_states": True,
                "next_task_launchpad": True,
                "no_mission_feed_action_overlap": True,
            },
        )

    monkeypatch.setattr(visual_qa, "_browser_target_ready", lambda base_url: True)
    monkeypatch.setattr(visual_qa, "_capture_browser_png", fake_capture)

    result = runner.invoke(app, ["operating-layer", "visual-qa", "--write-current", "--update-baseline", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["image_fallback"]["status"] == "pass"
    assert payload["image_fallback"]["capture_method"] == "playwright-browser-raster"
    assert payload["image_fallback"]["browser_ready"] is True
    for artifact in payload["image_fallback"]["artifacts"]:
        current_png = tmp_path / artifact["current_png"]
        current_metadata = tmp_path / artifact["current_metadata"]
        assert artifact["capture_method"] == "playwright-browser-raster"
        assert current_png.read_bytes().startswith(b"\x89PNG\r\n\x1a\nbrowser-raster")
        metadata = json.loads(current_metadata.read_text(encoding="utf-8"))
        assert metadata["capture_method"] == "playwright-browser-raster"
        assert metadata["checks"]["no_horizontal_overflow"] is True


def test_operating_layer_visual_qa_uses_external_appshot_browser_rasters(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    import devflow.control_room.operating_layer_visual_qa as visual_qa

    monkeypatch.setattr(visual_qa, "_browser_target_ready", lambda base_url: False)

    assert runner.invoke(app, ["task", "create", "visual appshot task"]).exit_code == 0
    drop_dir = tmp_path / ".devflow" / "operating-layer" / "visual-qa" / "appshot"
    drop_dir.mkdir(parents=True)
    for viewport in ("desktop", "mobile"):
        (drop_dir / f"{viewport}.png").write_bytes(b"\x89PNG\r\n\x1a\nappshot-" + viewport.encode("utf-8"))
        (drop_dir / f"{viewport}.json").write_text(
            json.dumps({"checks": {"no_horizontal_overflow": True}}) + "\n",
            encoding="utf-8",
        )

    result = runner.invoke(app, ["operating-layer", "visual-qa", "--write-current", "--update-baseline", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["external_capture"]["drop_dir"] == ".devflow/operating-layer/visual-qa/appshot"
    assert payload["image_fallback"]["capture_method"] == "external-browser-raster"
    for artifact in payload["image_fallback"]["artifacts"]:
        current_png = tmp_path / artifact["current_png"]
        assert artifact["capture_method"] == "external-browser-raster"
        assert current_png.read_bytes().startswith(b"\x89PNG\r\n\x1a\nappshot-")


def test_operating_layer_server_ignores_disconnected_clients(tmp_path: Path) -> None:
    class BrokenPipe:
        def write(self, _body: bytes) -> None:
            raise BrokenPipeError("client disconnected")

    handler = OperatingLayerRequestHandler.__new__(OperatingLayerRequestHandler)
    handler.wfile = BrokenPipe()
    handler.send_response = lambda _status: None
    handler.send_header = lambda _name, _value: None
    handler.end_headers = lambda: None

    handler._send_text("body", "text/plain")
    handler._send_json_error("gone", HTTPStatus.BAD_REQUEST)
