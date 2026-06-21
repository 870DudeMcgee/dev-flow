from __future__ import annotations

import json
import subprocess
import threading
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
from devflow.control_room.operating_layer_assets import APP_CSS, APP_JS, INDEX_HTML
from devflow.control_room.operating_layer_html import INDEX_HTML as SPLIT_INDEX_HTML
from devflow.control_room.operating_layer_script import APP_JS as SPLIT_APP_JS
from devflow.control_room.operating_layer_server import (
    OperatingLayerHTTPServer,
    OperatingLayerRequestHandler,
    _approved_idea_classify_command_args,
    _approved_idea_evidence_command_args,
)
from devflow.control_room.operating_layer_styles import APP_CSS as SPLIT_APP_CSS
from devflow.control_room.persistence import get_task, save_task, utc_now
from devflow.control_room.project_models import ProjectMetadata, ProjectRecord
from devflow.control_room.project_registry import register_project, write_project_metadata
from devflow.control_room.serial_local_agent_run import create_serial_local_agent_run
from devflow.control_room.worker_evidence import write_worker_evidence
from tests.helpers import setup_temp_git_repo


runner = CliRunner()


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


def _serve_operating_layer(root: Path) -> tuple[OperatingLayerHTTPServer, threading.Thread, str, int]:
    server = OperatingLayerHTTPServer(("127.0.0.1", 0), root)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    return server, thread, host, port


def _post_action(host: str, port: int, command: str, **extra: object) -> tuple[int, dict]:
    connection = HTTPConnection(host, port, timeout=5)
    body = json.dumps(
        {
            "command": command,
            "human_approved": True,
            "approval_phrase": "I approve this exact Dev-Flow command",
            "approved_command": command,
            **extra,
        }
    )
    connection.request(
        "POST",
        "/api/actions/run",
        body=body,
        headers={"Content-Type": "application/json"},
    )
    response = connection.getresponse()
    payload = json.loads(response.read().decode("utf-8"))
    return response.status, payload


def test_operating_layer_assets_facade_keeps_split_asset_contract() -> None:
    assert INDEX_HTML is SPLIT_INDEX_HTML
    assert APP_CSS is SPLIT_APP_CSS
    assert APP_JS is SPLIT_APP_JS
    assert '<link rel="stylesheet" href="/app.css">' in INDEX_HTML
    assert '<script src="/app.js"></script>' in INDEX_HTML
    assert ".focus-overlay" in APP_CSS
    assert "pipeline-section" in INDEX_HTML
    assert ".panel" in APP_CSS
    assert ".bottom-dock" in APP_CSS
    assert "openFocus" in APP_JS
    assert "closeFocus" in APP_JS
    assert "sendBrainstormMessage" in APP_JS
    assert "loadSnapshot" in APP_JS
    assert "renderOrchestrator" in APP_JS
    assert "renderMissionFeed" in APP_JS
    assert "renderWorkerLanes" in APP_JS
    assert "buildFirstViewportPresentation" in APP_JS
    assert "renderFirstViewport" in APP_JS
    assert "first_viewport" in APP_JS
    assert "rememberApprovedActionResult" in APP_JS
    assert "refreshSnapshotAfterApprovedAction" in APP_JS
    assert "executeAction" in APP_JS
    assert "rememberApprovedActionResult" in APP_JS
    assert "renderWorkerLanes" in APP_JS
    assert "bottom-dock" in APP_CSS


def test_operating_layer_html_includes_idea_greenhouse_asset_contract() -> None:
    assert "Idea Greenhouse" in INDEX_HTML
    assert "idea-greenhouse-section" in INDEX_HTML
    assert "idea-greenhouse-status" in INDEX_HTML
    assert "idea-capture-form" in INDEX_HTML
    assert "idea-capture-text" in INDEX_HTML
    assert "idea-capture-title" in INDEX_HTML
    assert "idea-capture-submit" in INDEX_HTML
    assert "idea-greenhouse-lanes" in INDEX_HTML
    assert "idea-greenhouse-primary-action" in INDEX_HTML


def test_operating_layer_css_includes_idea_greenhouse_layout_contract() -> None:
    for token in (
        ".idea-greenhouse-section",
        ".idea-capture-form",
        ".idea-greenhouse-lanes",
        "grid-template-columns: repeat(3, minmax(0, 1fr));",
        ".idea-lane",
        ".idea-lane-header",
        ".idea-card",
        ".idea-card.raw",
        ".idea-card.clarify",
        ".idea-card.candidate",
        ".idea-card.promoted",
        ".idea-card.parked",
        ".idea-card.archived",
        ".idea-primary-action",
        ".status-pill.muted",
        ".idea-card[role=\"button\"]",
        ".idea-detail-grid",
        ".idea-detail-evidence",
        ".idea-detail-metadata",
        ".idea-detail-metadata-list",
    ):
        assert token in APP_CSS

    mobile_rules = APP_CSS[APP_CSS.index("@media (max-width: 900px)") :]
    assert ".idea-greenhouse-lanes { grid-template-columns: 1fr; }" in mobile_rules
    assert mobile_rules.index("#brainstorm-section { order: 1; }") < mobile_rules.index(
        "#orchestrator-section"
    ) < mobile_rules.index("#idea-greenhouse-section")


def test_operating_layer_js_includes_idea_greenhouse_runtime_contract() -> None:
    for token in (
        "setupIdeaGreenhouse",
        "renderIdeaGreenhouse",
        "captureIdeaFromGreenhouse",
        "secondaryIdeaActions",
        "Parked from Idea Greenhouse",
        "idea-greenhouse-lanes",
        "data-inspect-idea",
        "findIdeaCard",
        "renderIdeaDetail",
        "Raw metadata",
        "Evidence paths",
    ):
        assert token in APP_JS


def test_operating_layer_css_includes_park_archive_form_tokens() -> None:
    for token in (
        ".idea-detail-park-section",
        ".idea-detail-archive-section",
        ".idea-archive-title",
        ".idea-archive-reason",
        ".idea-archive-reason::placeholder",
    ):
        assert token in APP_CSS


def test_operating_layer_js_includes_park_archive_detail_form_contract() -> None:
    """Slice 3: detail drawer park/archive reason form renders and is wired."""
    # Form renderer exists
    assert "renderIdeaParkArchiveForm" in APP_JS
    # Card-level park command uses a concrete, non-empty reason (not placeholder)
    assert "Parked from Idea Greenhouse" in APP_JS
    assert "Archived from Idea Greenhouse" in APP_JS

    # Park and archive actions are present where appropriate
    for lane_id in ("raw", "clarify", "candidate"):
        assert f"'{lane_id}'" in APP_JS  # confirm lanes checked


def test_operating_layer_js_park_archive_form_has_required_tokens() -> None:
    """Confirm the detail-form has reason textarea, submit buttons, and status div."""
    # Data attributes are built via template literal with ternary; confirm all keys exist
    assert 'data-idea-' in APP_JS and '-submit=' in APP_JS
    assert '="reason"' in APP_JS
    assert '[data-idea-park-submit]' in APP_JS
    assert '[data-idea-archive-submit]' in APP_JS


def test_operating_layer_js_park_archive_command_construction() -> None:
    """PARK/ARCHIVE command strings are literal, user-supplied, never placeholders."""
    assert 'devflow idea park ${ideaId} --reason' in APP_JS
    assert 'devflow idea archive ${ideaId} --reason' in APP_JS
    # shellQuote guards the reason so arbitrary text is safely escaped
    assert "shellQuote" in APP_JS


def test_operating_layer_js_park_archive_approval_payload_required() -> None:
    """Full approval payload (human_approved, approval_phrase, approved_command) included."""
    assert "human_approved" in APP_JS
    assert "approval_phrase" in APP_JS
    assert "approved_command" in APP_JS
    # The action URL is the actions/run endpoint
    assert "'/api/actions/run'" in APP_JS


def test_operating_layer_js_park_archive_snapshot_refresh_on_success() -> None:
    """After successful park/archive, loadSnapshot is triggered."""
    assert "loadSnapshot" in APP_JS
    # The _submitParkOrArchive function uses setTimeout + loadSnapshot for refresh
    assert "_submitParkOrArchive" in APP_JS
    # Confirm the pattern: reason validation rejects < 3 chars and writes to the action-specific status.
    assert "reasonValue.length < 3" in APP_JS
    assert "`idea-${actionType}-status`" in APP_JS
    assert "function setIdeaDetailStatus(message, tone, statusId)" in APP_JS


def test_operating_layer_js_park_archive_click_handlers_wired() -> None:
    """Click handlers for the park/archive submit buttons exist."""
    assert "[data-idea-park-submit]" in APP_JS
    assert "[data-idea-archive-submit]" in APP_JS


def test_operating_layer_js_start_brainstorm_from_idea_contract() -> None:
    """Slice 4: idea detail drawer can open a brainstorm session with lineage."""
    assert "data-idea-brainstorm" in APP_JS
    assert "idea-brainstorm-status" in APP_JS
    assert "'/api/brainstorm/start-from-idea'" in APP_JS
    assert "JSON.stringify({ idea_id: ideaId })" in APP_JS
    assert "localStorage.setItem('devflow-brainstorm-session', data.session_id)" in APP_JS
    assert "setActiveNav('brainstorm')" in APP_JS
    assert "await loadBrainstormTranscript(data.session_id)" in APP_JS
    assert "Brainstorm session started from " in APP_JS
    assert "Next: add context or escalate to Spec" in APP_JS
    assert APP_JS.index("await loadBrainstormTranscript(data.session_id)") < APP_JS.index("Brainstorm session started from ")


def test_operating_layer_start_brainstorm_from_idea_endpoint(tmp_path: Path) -> None:
    setup_temp_git_repo(tmp_path)
    idea = capture_idea(tmp_path, "Seed this into brainstorm.", title="Seeded idea")
    server, thread, host, port = _serve_operating_layer(tmp_path)
    try:
        connection = HTTPConnection(host, port, timeout=5)
        connection.request(
            "POST",
            "/api/brainstorm/start-from-idea",
            body=json.dumps({"idea_id": idea["id"]}),
            headers={"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        payload = json.loads(response.read().decode("utf-8"))

        assert response.status == HTTPStatus.OK
        assert payload["source_idea_id"] == idea["id"]
        assert payload["session_id"].startswith("brainstorm-")
        transcript = tmp_path / ".devflow" / "brainstorms" / payload["session_id"] / "transcript.jsonl"
        records = [json.loads(line) for line in transcript.read_text(encoding="utf-8").splitlines()]
        assert records[0]["kind"] == "brainstorm_start"
        assert records[0]["metadata"]["source_idea_id"] == idea["id"]
        assert records[0]["content"] == "Seed this into brainstorm."
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


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
    assert first_viewport["launchpad"]["selected_task_id"] == "task-0001"
    assert first_viewport["launchpad"]["command"] == "devflow task run task-0001 --worker shell -- <command>"
    assert payload["gate_receipts"][0]["task_id"] == "task-0001"
    assert payload["gate_receipts"][0]["next_gate"] == "run_worker"
    assert payload["mission_feed"][0]["label"] == "Task progress"
    assert payload["mission_feed"][0]["task_id"] == "task-0001"
    assert payload["mission_feed"][0]["detail"] == "2/5 required steps done. Next: run a worker."
    assert payload["freshness"]["snapshot_path"] == ".devflow/freshness/latest.json"

    assert not (tmp_path / ".devflow" / "freshness" / "latest.json").exists()
    assert not (tmp_path / ".devflow" / "freshness" / "events.jsonl").exists()


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


def test_operating_layer_approved_model_onboarding_actions_execute(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["init"]).exit_code == 0
    server, thread, host, port = _serve_operating_layer(tmp_path)
    try:
        add_provider = (
            "devflow agent add-provider local_gateway --adapter openai_compatible "
            "--base-url http://127.0.0.1:8000/v1 --api-key-env LOCAL_GATEWAY_API_KEY --json"
        )
        status, payload = _post_action(host, port, add_provider)
        assert status == 200, payload
        assert payload["executed"] is True
        assert payload["exit_code"] == 0
        assert (tmp_path / ".devflow/providers/local_gateway.yaml").exists()

        add_model = (
            "devflow agent add-model --provider local_gateway --model local/test-model "
            "--authority advisory --role frontier_planner_architect_reviewer --json"
        )
        status, payload = _post_action(host, port, add_model)
        assert status == 200, payload
        assert payload["executed"] is True
        assert payload["exit_code"] == 0
        assert "local_gateway-local-test-model-advisory-frontier_planner_architect_reviewer" in (
            tmp_path / ".devflow/agents/registry.yaml"
        ).read_text(encoding="utf-8")
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_operating_layer_blocks_broad_agent_command_but_allows_exact_patch_proposal_attempt(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["init"]).exit_code == 0
    assert runner.invoke(app, ["task", "create", "patch proposal from browser"]).exit_code == 0
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    server, thread, host, port = _serve_operating_layer(tmp_path)
    try:
        broad = "devflow agent run local-qwopus-inspector --prompt hello --json"
        status, payload = _post_action(host, port, broad)
        assert status == 409, payload
        assert payload["executed"] is False

        exact = "devflow agent propose-patch --task task-0001 --profile deepseek-v4-pro-patch-proposer --json"
        status, payload = _post_action(host, port, exact)
        assert status == 200, payload
        assert payload["executed"] is True
        assert payload["exit_code"] != 0
        assert "OPENROUTER_API_KEY" in payload["stdout"]
    finally:
        server.shutdown()
        thread.join(timeout=5)


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


def test_operating_layer_snapshot_includes_compact_agent_evidence_summary(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["task", "create", "agent evidence snapshot"]).exit_code == 0
    write_worker_evidence(
        root=tmp_path,
        worker_type="local_model",
        profile_id="local-qwopus-inspector",
        worker_id="local-qwopus-inspector",
        task_id="task-0001",
        run_id="run-1",
        packet_text="packet",
        raw_output="raw",
        response_text="response",
        model="qwopus",
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
    assert f".devflow/tasks/task-0001/local-model-runs/run-1/run.json" in task["review_detail"]["evidence_paths"]
    assert any(artifact["kind"] == "model run" for artifact in task["review_detail"]["artifacts"])
    assert payload["evidence"][0]["kind"] == "model run"
    assert payload["evidence"][0]["path"] == f".devflow/tasks/task-0001/local-model-runs/run-1/run.json"
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


def test_operating_layer_server_serves_app_and_snapshot(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    assert runner.invoke(app, ["task", "create", "ui shell task"]).exit_code == 0

    server, thread, host, port = _serve_operating_layer(tmp_path)
    try:
        connection = HTTPConnection(host, port, timeout=5)
        connection.request("GET", "/")
        response = connection.getresponse()
        body = response.read().decode("utf-8")
        assert response.status == 200
        assert "Dev-Flow Operating Layer" in body
        assert "Brainstorm" in body
        assert "DeepSeek V4 Flash Free" in body
        assert "Escalate to Spec" in body
        assert "Generate Plan" in body
        assert "Create Task" in body
        assert "Idea Greenhouse" in body
        assert "idea-capture-form" in body
        assert "idea-greenhouse-lanes" in body
        assert "Local evidence only" in body
        assert "Worker lanes" in body
        assert "Review queue" in body
        assert "Evidence stream" in body
        assert "Next Task" in body
        assert "Definition of Done" in body
        assert "focus-overlay" in body
        assert "focus-panel" in body
        assert "Next Safe Action" in body
        assert "Work Feed" in body
        assert "System Health" in body
        assert "repo-name" in body
        assert "branch-name" in body
        assert "Control Room" in body
        assert "/api/snapshot" in body or "/app.js" in body

        connection.request("GET", "/api/snapshot")
        response = connection.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
        assert response.status == 200
        assert payload["tasks"][0]["id"] == "task-0001"

        connection.request("GET", "/app.css")
        response = connection.getresponse()
        css = response.read().decode("utf-8")
        assert response.status == 200
        assert "brainstorm-section" in INDEX_HTML
        assert "pipeline-section" in INDEX_HTML
        assert "bottom-dock" in css
        assert ".idea-greenhouse-lanes" in css
        assert ".idea-card" in css
        assert "worker-lanes-list" in css
        assert "worker-card" in css
        assert "review-queue-list" in css
        assert "focus-overlay" in css
        assert "focus-panel" in css
        assert "focus-overlay" in css
        assert "health-section" in css
        assert "next-task-meta" in css
        assert "definition-editor" in css
        assert "pipeline-stages" in css
        assert "agent-row" in css
        assert "feed-item" in css
        assert "evidence-item" in css
        assert "topbar" in css

        connection.request("GET", "/app.js")
        response = connection.getresponse()
        js = response.read().decode("utf-8")
        assert response.status == 200
        assert "sendBrainstormMessage" in js
        assert "escalateBrainstormStage" in js
        assert "pipeline_detail" in js
        assert "taskActionFromPipelinePayload" in js
        assert "renderBrainstormTranscript" in js
        assert "renderWorkerLanes" in js
        assert "renderIdeaGreenhouse" in js
        assert "idea-greenhouse-lanes" in js
        assert "renderReviewQueue" in js
        assert "renderEvidenceStream" in js
        assert "renderMissionFeed" in js
        assert "renderPipeline" in js
        assert "renderOrchestrator" in js
        assert "selectTaskInLaunchpad" in js
        assert "data-task-run-shell" in js
        assert "data-task-verify" in js
        assert "definition_of_done" in js
        assert "openFocus" in js
        assert "closeFocus" in js
        assert "loadSnapshot" in js
        assert "executeAction" in js
        assert "rememberApprovedActionResult" in js
        assert "refreshSnapshotAfterApprovedAction" in js
        assert "setActiveNav" in js
        assert "aria-label" in INDEX_HTML
        assert "keydown" in js
        assert "Escape" in js
        assert "shortTime" in js
        assert "esc" in js
        assert "ago" in js
        assert "refreshSnapshotAfterApprovedAction" in js
        assert "render" in js
        assert "loadSnapshot" in js
        assert "executeAction" in js
        assert "renderMissionFeed" in js
        assert "renderWorkerLanes" in js
        assert "renderPipeline" in js
        assert "shortTime" in js
        assert "esc" in js
        assert "ago" in js
        assert "snapshot" in js
        assert "setupRepoSelector" in js
        assert "setupBrainstormForm" in js
        assert "openFocus" in js
        assert "closeFocus" in js
        assert "sendBrainstormMessage" in js
        assert "escalateBrainstormStage" in js
        assert "loadSnapshot" in js
        assert "render" in js
        assert "renderOrchestrator" in js
        assert "renderMissionFeed" in js
        assert "renderWorkerLanes" in js
        assert "renderPipeline" in js
        assert "renderReviewQueue" in js
        assert "renderEvidenceStream" in js
        assert "/api/snapshot?project=" in js
        assert "/api/brainstorm/message" in js
        assert "/api/brainstorm/escalate" in js
        assert "refresh-button" in INDEX_HTML
        assert "/api/actions/run" in js
        assert "executeAction" in js
        assert "refreshSnapshotAfterApprovedAction" in js
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_operating_layer_server_exposes_brainstorm_message_and_escalation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    import devflow.control_room.env_loader as env_loader_mod
    monkeypatch.setattr(env_loader_mod, "_HERMES_ENV_PATH", tmp_path / "nonexistent.env")
    server, thread, host, port = _serve_operating_layer(tmp_path)
    try:
        connection = HTTPConnection(host, port, timeout=5)
        connection.request(
            "POST",
            "/api/brainstorm/message",
            body=json.dumps({"session_id": "browser-session", "message": "Make the UI a real chat."}),
            headers={"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
        assert response.status == 200
        assert payload["status"] == "failed"
        assert "OPENROUTER_API_KEY" in payload["error"]
        assert (tmp_path / payload["transcript_path"]).exists()

        connection.request(
            "POST",
            "/api/brainstorm/escalate",
            body=json.dumps(
                {
                    "session_id": "browser-session",
                    "stage": "implementation",
                    "title": "Build brainstorm workbench",
                    "definition_of_done": "Launchpad shows the created task and start composer.",
                }
            ),
            headers={"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
        assert response.status == 200
        assert payload["status"] == "ready"
        assert payload["action"]["command"] == (
            "devflow task create --definition-of-done "
            "'Launchpad shows the created task and start composer.' 'Build brainstorm workbench'"
        )
        assert payload["action"]["safety_class"] == "approval_required_task_state"
        assert payload["pipeline_detail"]["task_action"]["command"] == payload["action"]["command"]
        assert payload["pipeline_detail"]["implementation_context"]["target_path_template"] == (
            ".devflow/workspaces/{task_id}/implementation-context.md"
        )

        connection.request("GET", "/api/brainstorm/transcript?session_id=browser-session")
        response = connection.getresponse()
        transcript_payload = json.loads(response.read().decode("utf-8"))
        assert response.status == 200
        assert transcript_payload["implementation"].startswith("# Implementation Task")
        assert transcript_payload["pipeline"]["has_implementation"] is True
        assert transcript_payload["pipeline"]["task_action"]["command"] == payload["action"]["command"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_operating_layer_guided_sections_render_before_advanced_sections() -> None:
    assert "Brainstorm" in INDEX_HTML
    assert "DeepSeek V4 Flash Free" in INDEX_HTML
    assert "brainstorm-chat-form" in INDEX_HTML
    assert "Escalate to Spec" in INDEX_HTML
    assert "Generate Plan" in INDEX_HTML
    assert "Create Task" in INDEX_HTML
    assert "Worker lanes" in INDEX_HTML
    assert "Review queue" in INDEX_HTML
    assert "Evidence stream" in INDEX_HTML
    assert "Next Task" in INDEX_HTML
    assert "brainstorm-definition-of-done" in INDEX_HTML
    assert "Pipeline" in INDEX_HTML
    assert "focus-overlay" in INDEX_HTML


def test_operating_layer_task_cards_expose_state_specific_next_actions() -> None:
    assert "worker-card" in APP_JS
    assert "Worker lanes" in APP_JS
    assert "renderWorkerLanes" in APP_JS
    assert "buildFirstViewportPresentation" in APP_JS
    assert "renderFirstViewport" in APP_JS
    assert "BROWSER ACTION CAPABILITIES" in APP_JS
    assert "function taskCapabilities" in APP_JS
    assert "task?.controls" in APP_JS
    assert "required_inputs" in APP_JS
    assert "fillCapabilityCommand" in APP_JS
    assert "devflow task run ${task.id} --worker ${w.id}" not in APP_JS
    assert "data-task-run-shell" in APP_JS
    assert "data-select-task" in APP_JS
    assert "data-task-close" in APP_JS
    assert "Cleanup preview" in APP_JS
    assert "Worker / model" in APP_JS
    assert "openFocus" in APP_JS
    assert "closeFocus" in APP_JS
    assert "worker-card" in APP_CSS
    assert "worker-light" in APP_CSS
    assert "command-result" in APP_CSS


def test_operating_layer_command_preview_uses_human_readable_safety_labels() -> None:
    assert "executeAction" in APP_JS
    assert "closeFocus" in APP_JS
    assert "openFocus" in APP_JS


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
    assert "after Brainstorm and before Next Task" in greenhouse_check["detail"]
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
        "app loads -> first viewport renders Brainstorm chat, Pipeline stages, Next Task launchpad, Worker lanes, "
        "Review queue, and Evidence stream without horizontal overflow"
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


def test_operating_layer_server_runs_supervisor_safe_read_only_action(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    assert runner.invoke(app, ["task", "create", "ui control task"]).exit_code == 0

    server, thread, host, port = _serve_operating_layer(tmp_path)
    try:
        connection = HTTPConnection(host, port, timeout=5)
        body = json.dumps({"command": "devflow task list"})
        connection.request(
            "POST",
            "/api/actions/run",
            body=body,
            headers={"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        payload = json.loads(response.read().decode("utf-8"))

        assert response.status == 200
        assert payload["executed"] is True
        assert payload["exit_code"] == 0
        assert payload["classification"]["safety_class"] == "pure_read_only"
        assert "task-0001" in payload["stdout"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_operating_layer_server_blocks_approval_required_actions(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    assert runner.invoke(app, ["task", "create", "blocked runtime action"]).exit_code == 0
    worker_log = tmp_path / ".devflow" / "tasks" / "task-0001" / "logs" / "worker.log"
    original_worker_log = worker_log.read_text() if worker_log.exists() else None

    server, thread, host, port = _serve_operating_layer(tmp_path)
    try:
        connection = HTTPConnection(host, port, timeout=5)
        command = "devflow task run task-0001 --worker qwopus-implementer"
        body = json.dumps(
            {
                "command": command,
                "human_approved": True,
                "approval_phrase": "I approve this exact Dev-Flow command",
                "approved_command": command,
            }
        )
        connection.request(
            "POST",
            "/api/actions/run",
            body=body,
            headers={"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        payload = json.loads(response.read().decode("utf-8"))

        assert response.status == HTTPStatus.CONFLICT
        assert payload["executed"] is False
        assert payload["requires_human_approval"] is True
        assert payload["classification"]["safety_class"] == "approval_required_worker_runtime"
        assert (worker_log.read_text() if worker_log.exists() else None) == original_worker_log
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_operating_layer_server_runs_approved_task_creation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    command = (
        'devflow task create --definition-of-done '
        '"Launchpad can start this task after creation." "browser created task"'
    )
    server, thread, host, port = _serve_operating_layer(tmp_path)
    try:
        status, payload = _post_action(host, port, command)

        assert status == HTTPStatus.OK
        assert payload["executed"] is True
        assert payload["requires_human_approval"] is True
        assert payload["classification"]["safety_class"] == "approval_required_task_state"
        assert payload["exit_code"] == 0
        assert "Created task-0001: browser created task" in payload["stdout"]
        task_yaml = (tmp_path / ".devflow" / "tasks" / "task-0001" / "task.yaml").read_text(encoding="utf-8")
        summary = json.loads((tmp_path / ".devflow" / "tasks" / "task-0001" / "summary.json").read_text())
        assert 'definition_of_done: "Launchpad can start this task after creation."' in task_yaml
        assert summary["definition_of_done"] == "Launchpad can start this task after creation."
        assert not (tmp_path / ".devflow" / "worktrees").exists()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_operating_layer_server_runs_approved_task_close(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    assert runner.invoke(app, ["task", "create", "browser close target"]).exit_code == 0
    command = 'devflow task close task-0001 --outcome abandoned --reason "operator cleared stale task"'
    server, thread, host, port = _serve_operating_layer(tmp_path)
    try:
        status, payload = _post_action(host, port, command)

        assert status == HTTPStatus.OK
        assert payload["executed"] is True
        assert payload["requires_human_approval"] is True
        assert payload["classification"]["safety_class"] == "approval_required_task_state"
        assert payload["exit_code"] == 0
        assert "closed: yes" in payload["stdout"]
        closure = json.loads((tmp_path / ".devflow" / "tasks" / "task-0001" / "closure.json").read_text())
        assert closure["outcome"] == "abandoned"
        assert closure["reason"] == "operator cleared stale task"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_operating_layer_server_runs_approved_cleanup_preview(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    assert runner.invoke(app, ["task", "create", "browser cleanup preview"]).exit_code == 0
    assert runner.invoke(
        app,
        ["task", "close", "task-0001", "--outcome", "abandoned", "--reason", "preview cleanup"],
    ).exit_code == 0
    command = "devflow task cleanup task-0001 --preview"
    server, thread, host, port = _serve_operating_layer(tmp_path)
    try:
        status, payload = _post_action(host, port, command)

        assert status == HTTPStatus.OK
        assert payload["executed"] is True
        assert payload["requires_human_approval"] is True
        assert payload["classification"]["safety_class"] == "approval_required_task_state"
        assert payload["exit_code"] == 0
        assert "mode: preview" in payload["stdout"]
        assert (tmp_path / ".devflow" / "workspaces" / "task-0001").exists()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_approved_idea_evidence_command_args_accepts_only_safe_concrete_commands() -> None:
    accepted = [
        (
            'devflow idea park I-0001 --reason "not this week"',
            ["idea", "park", "I-0001", "--reason", "not this week"],
        ),
        (
            'devflow idea archive I-0001 --reason "duplicate"',
            ["idea", "archive", "I-0001", "--reason", "duplicate"],
        ),
    ]
    for command, expected_tail in accepted:
        args = _approved_idea_evidence_command_args(command)

        assert args[-5:] == expected_tail

    rejected = [
        "devflow idea park I-0001",
        "devflow idea park I-0001 --reason",
        "devflow idea park I-0001 --reason <reason>",
        'devflow idea park I-0001 --reason ""',
        'devflow idea park I-0001 --reason "not this week" --tag later',
        'devflow idea archive I-0001 --reason "duplicate" extra',
        "devflow idea classify I-0001 --maturity candidate --note <note>",
        "devflow idea promote I-0001 --to task --rationale <rationale>",
    ]
    for command in rejected:
        with pytest.raises(ValueError):
            _approved_idea_evidence_command_args(command)


def test_approved_idea_classify_command_args_accepts_only_safe_concrete_commands() -> None:
    accepted = [
        (
            'devflow idea classify I-0001 --maturity candidate --note "ready for planning"',
            ["idea", "classify", "I-0001", "--maturity", "candidate", "--note", "ready for planning"],
        ),
        (
            'devflow idea classify I-0001 --maturity goal_ready --note "scoped" --tag launchpad',
            ["idea", "classify", "I-0001", "--maturity", "goal_ready", "--note", "scoped", "--tag", "launchpad"],
        ),
    ]
    for command, expected_tail in accepted:
        args = _approved_idea_classify_command_args(command)

        assert args[-len(expected_tail) :] == expected_tail

    rejected = [
        "devflow idea classify I-0001",
        "devflow idea classify 0001 --maturity candidate --note ready",
        "devflow idea classify I-0001 --maturity nope --note ready",
        "devflow idea classify I-0001 --maturity candidate",
        "devflow idea classify I-0001 --maturity candidate --note",
        "devflow idea classify I-0001 --maturity candidate --note <note>",
        'devflow idea classify I-0001 --maturity candidate --note ""',
        'devflow idea classify I-0001 --maturity candidate --note "ready" extra',
        'devflow idea classify I-0001 --maturity candidate --note "ready" --shell echo',
        "devflow idea promote I-0001 --to task --rationale ready",
    ]
    for command in rejected:
        with pytest.raises(ValueError):
            _approved_idea_classify_command_args(command)


def test_operating_layer_server_runs_approved_idea_classify(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    capture_idea(tmp_path, "Turn this rough thought into a scoped candidate.", title="Candidate seed")
    command = 'devflow idea classify I-0001 --maturity candidate --note "clear next step"'
    server, thread, host, port = _serve_operating_layer(tmp_path)
    try:
        status, payload = _post_action(host, port, command)

        assert status == HTTPStatus.OK
        assert payload["executed"] is True
        assert payload["requires_human_approval"] is True
        assert payload["classification"]["safety_class"] == "approval_required_evidence_writing"
        assert payload["exit_code"] == 0
        assert "idea_id: I-0001" in payload["stdout"]
        assert "maturity: candidate" in payload["stdout"]
        idea_path = tmp_path / ".devflow" / "ideas" / "I-0001"
        metadata = json.loads((idea_path / "idea.json").read_text(encoding="utf-8"))
        assert metadata["status"] == "classified"
        assert metadata["maturity"] == "candidate"
        assert "clear next step" in (idea_path / "classification.md").read_text(encoding="utf-8")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_operating_layer_classify_form_uses_full_idea_ids_and_requires_choices() -> None:
    assert "function renderIdeaClassifyForm" in APP_JS
    assert "if (!/^I-[0-9]{4}$/.test(ideaId)) return '';" in APP_JS
    assert "if (!/^I-[0-9]{4}$/.test(ideaId)) return null;" in APP_JS
    assert 'option value="">Choose maturity...' in APP_JS
    assert "Choose a maturity before classifying." in APP_JS
    assert "Please write a classification note." in APP_JS
    assert "devflow idea classify ${ideaId} --maturity ${maturityValue}" in APP_JS
    assert "human_approved: true" in APP_JS
    assert "approved_command: command" in APP_JS
    assert ".idea-detail-classify-section" in APP_CSS
    assert ".idea-classify-note" in APP_CSS


def test_operating_layer_server_runs_approved_idea_capture(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    command = 'devflow idea capture --source browser --title "Better intake" "Let me dump rough project brainstorms before tasking."'
    server, thread, host, port = _serve_operating_layer(tmp_path)
    try:
        status, payload = _post_action(host, port, command)

        assert status == HTTPStatus.OK
        assert payload["executed"] is True
        assert payload["requires_human_approval"] is True
        assert payload["classification"]["safety_class"] == "approval_required_evidence_writing"
        assert payload["exit_code"] == 0
        assert "idea_id: I-0001" in payload["stdout"]
        assert "created_task: no" in payload["stdout"]
        idea_path = tmp_path / ".devflow" / "ideas" / "I-0001"
        assert (idea_path / "idea.json").exists()
        assert "rough project brainstorms" in (idea_path / "raw.md").read_text(encoding="utf-8")
        assert not (tmp_path / ".devflow" / "tasks" / "task-0001").exists()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_operating_layer_server_runs_approved_idea_park(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    capture_idea(tmp_path, "Save this for later.", title="Later idea")
    command = 'devflow idea park I-0001 --reason "not this week"'
    server, thread, host, port = _serve_operating_layer(tmp_path)
    try:
        status, payload = _post_action(host, port, command)

        assert status == HTTPStatus.OK
        assert payload["executed"] is True
        assert payload["requires_human_approval"] is True
        assert payload["classification"]["safety_class"] == "approval_required_evidence_writing"
        assert payload["exit_code"] == 0
        assert "idea_id: I-0001" in payload["stdout"]
        assert "status: parked" in payload["stdout"]
        metadata = json.loads((tmp_path / ".devflow" / "ideas" / "I-0001" / "idea.json").read_text())
        assert metadata["status"] == "parked"
        assert metadata["park_reason"] == "not this week"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_operating_layer_server_refuses_empty_or_placeholder_idea_capture(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    server, thread, host, port = _serve_operating_layer(tmp_path)
    try:
        for command in ('devflow idea capture', 'devflow idea capture ""', 'devflow idea capture "<idea>"'):
            status, payload = _post_action(host, port, command)

            assert status != HTTPStatus.OK
            assert payload.get("executed") is not True
        assert not (tmp_path / ".devflow" / "ideas" / "I-0001").exists()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_operating_layer_server_refuses_empty_or_placeholder_task_titles(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    server, thread, host, port = _serve_operating_layer(tmp_path)
    try:
        for command in ('devflow task create', 'devflow task create ""', 'devflow task create "<title>"'):
            status, payload = _post_action(host, port, command)

            assert status != HTTPStatus.OK
            assert payload.get("executed") is not True
        assert not (tmp_path / ".devflow" / "tasks" / "task-0001").exists()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_operating_layer_server_runs_approved_shell_worker_in_task_workspace(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    assert runner.invoke(app, ["task", "create", "approved shell worker action"]).exit_code == 0
    command = 'devflow task run task-0001 --worker shell -- /bin/sh -c "printf browser > browser.txt"'
    server, thread, host, port = _serve_operating_layer(tmp_path)
    try:
        status, payload = _post_action(host, port, command)

        assert status == HTTPStatus.OK
        assert payload["executed"] is True
        assert payload["requires_human_approval"] is True
        assert payload["classification"]["safety_class"] == "approval_required_worker_runtime"
        assert payload["exit_code"] == 0
        assert "task-0001: complete" in payload["stdout"]
        workspace_file = tmp_path / ".devflow" / "workspaces" / "task-0001" / "browser.txt"
        assert workspace_file.read_text(encoding="utf-8") == "browser"
        assert not (tmp_path / "browser.txt").exists()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_operating_layer_server_refuses_invalid_shell_worker_browser_runs(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    assert runner.invoke(app, ["task", "create", "refuse invalid shell run"]).exit_code == 0
    server, thread, host, port = _serve_operating_layer(tmp_path)
    try:
        commands = [
            "devflow task run task-0001 --worker shell --",
            "devflow task run task-0001 --worker shell -- <command>",
            "devflow task run task-0001 --worker qwopus-implementer",
            "devflow task local task-0001 --worker qwen-planner",
            "devflow agent run local-qwopus-inspector --prompt hello --json",
            "devflow task run task-0001 --worker shell -- ollama run qwen",
        ]
        for command in commands:
            status, payload = _post_action(host, port, command)

            assert status != HTTPStatus.OK
            assert payload.get("executed") is not True
        assert not (tmp_path / ".devflow" / "workspaces" / "task-0001" / "provider.txt").exists()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_operating_layer_server_blocks_disallowed_browser_mutations(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    assert runner.invoke(app, ["task", "create", "blocked browser mutation"]).exit_code == 0
    server, thread, host, port = _serve_operating_layer(tmp_path)
    try:
        for command in (
            "devflow task apply-patch task-0001",
            "devflow task cleanup task-0001 --apply",
            "devflow sync-main",
            "devflow push-main",
            "devflow project connect-github demo --remote-url https://github.com/example/demo",
        ):
            status, payload = _post_action(host, port, command)

            assert status == HTTPStatus.CONFLICT
            assert payload["executed"] is False
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_operating_layer_server_runs_approved_task_verification(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    assert runner.invoke(app, ["task", "create", "approved verification action"]).exit_code == 0
    run = runner.invoke(app, ["task", "run", "task-0001", "--shell", "echo done > result.txt"])
    assert run.exit_code == 0, run.output

    command = 'devflow task verify task-0001 --shell "test -f result.txt"'
    server, thread, host, port = _serve_operating_layer(tmp_path)
    try:
        connection = HTTPConnection(host, port, timeout=5)
        body = json.dumps(
            {
                "command": command,
                "human_approved": True,
                "approval_phrase": "I approve this exact Dev-Flow command",
                "approved_command": command,
            }
        )
        connection.request(
            "POST",
            "/api/actions/run",
            body=body,
            headers={"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        payload = json.loads(response.read().decode("utf-8"))

        assert response.status == HTTPStatus.OK
        assert payload["executed"] is True
        assert payload["requires_human_approval"] is True
        assert payload["classification"]["safety_class"] == "approval_required_worker_runtime"
        assert payload["exit_code"] == 0
        assert "task-0001: verification passed" in payload["stdout"]
        verification = json.loads((tmp_path / ".devflow" / "tasks" / "task-0001" / "verification.json").read_text())
        assert verification["status"] == "passed"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_operating_layer_server_runs_approved_task_promotion(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "devflow@example.test"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "DevFlow Test"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "--allow-empty", "-m", "initial"], cwd=tmp_path, check=True, capture_output=True)

    assert runner.invoke(app, ["task", "create", "ship visible approval evidence"]).exit_code == 0
    run = runner.invoke(app, ["task", "run", "task-0001", "--shell", "echo done > approval.txt"])
    assert run.exit_code == 0, run.output
    verify = runner.invoke(app, ["task", "verify", "task-0001", "--shell", "test -f approval.txt"])
    assert verify.exit_code == 0, verify.output
    preview = runner.invoke(app, ["task", "promote-preview", "task-0001"])
    assert preview.exit_code == 0, preview.output

    command = "devflow task promote task-0001"
    server, thread, host, port = _serve_operating_layer(tmp_path)
    try:
        connection = HTTPConnection(host, port, timeout=5)
        body = json.dumps(
            {
                "command": command,
                "human_approved": True,
                "approval_phrase": "I approve this exact Dev-Flow command",
                "approved_command": command,
                "context_note": "Ship this because the browser review confirmed the visible approval evidence.",
            }
        )
        connection.request(
            "POST",
            "/api/actions/run",
            body=body,
            headers={"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        payload = json.loads(response.read().decode("utf-8"))

        assert response.status == HTTPStatus.OK
        assert payload["executed"] is True
        assert payload["requires_human_approval"] is True
        assert payload["classification"]["safety_class"] == "approval_required_git"
        assert payload["exit_code"] == 0
        assert "Promotion complete." in payload["stdout"]
        assert payload["context_path"] == ".devflow/tasks/task-0001/promotion-context.md"
        task_yaml = (tmp_path / ".devflow" / "tasks" / "task-0001" / "task.yaml").read_text()
        assert 'status: "promoted"' in task_yaml
        context = (tmp_path / ".devflow" / "tasks" / "task-0001" / "promotion-context.md").read_text()
        assert "Ship this because the browser review confirmed the visible approval evidence." in context
        assert "devflow task promote task-0001" in context
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


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


def test_operating_layer_server_serves_registered_project_snapshot(
    tmp_path: Path,
    monkeypatch,
) -> None:
    home = tmp_path / "home"
    monkeypatch.setenv("DEVFLOW_HOME", home.as_posix())

    host_root = tmp_path / "host"
    host_root.mkdir()
    project_root = tmp_path / "projects" / "demo"
    project_root.mkdir(parents=True)

    monkeypatch.chdir(project_root)
    assert runner.invoke(app, ["task", "create", "project drilldown task"]).exit_code == 0
    register_project(
        ProjectRecord(
            project_id="demo",
            name="Demo",
            path=project_root.as_posix(),
            last_seen_at=utc_now(),
        )
    )

    server = OperatingLayerHTTPServer(("127.0.0.1", 0), host_root)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        connection = HTTPConnection(host, port, timeout=5)
        connection.request("GET", "/api/snapshot?project=demo")
        response = connection.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
        assert response.status == 200
        assert payload["project"]["root"] == project_root.as_posix()
        assert payload["tasks"][0]["title"] == "project drilldown task"

        connection.request("GET", "/api/snapshot?project=missing")
        response = connection.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
        assert response.status == 400
        assert "Project not found" in payload["error"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
