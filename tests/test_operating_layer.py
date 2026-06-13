from __future__ import annotations

import json
import subprocess
import threading
from http import HTTPStatus
from http.client import HTTPConnection
from pathlib import Path

from typer.testing import CliRunner

from devflow.cli import app
from devflow.control_room.goal_lifecycle import ensure_goal_lifecycle
from devflow.control_room.operating_layer import build_operating_layer_snapshot
from devflow.control_room.operating_layer_assets import APP_CSS, APP_JS, INDEX_HTML
from devflow.control_room.operating_layer_html import INDEX_HTML as SPLIT_INDEX_HTML
from devflow.control_room.operating_layer_script import APP_JS as SPLIT_APP_JS
from devflow.control_room.operating_layer_server import OperatingLayerHTTPServer, OperatingLayerRequestHandler
from devflow.control_room.operating_layer_styles import APP_CSS as SPLIT_APP_CSS
from devflow.control_room.persistence import utc_now
from devflow.control_room.project_models import ProjectMetadata, ProjectRecord
from devflow.control_room.project_registry import register_project, write_project_metadata


runner = CliRunner()


def _create_goal(tmp_path: Path) -> None:
    brief = tmp_path / "brief.md"
    brief.write_text("# Operating layer goal\n", encoding="utf-8")
    result = runner.invoke(app, ["goal", "init", "G-0001", "--from", str(brief)])
    assert result.exit_code == 0, result.output


def test_operating_layer_assets_facade_keeps_split_asset_contract() -> None:
    assert INDEX_HTML is SPLIT_INDEX_HTML
    assert APP_CSS is SPLIT_APP_CSS
    assert APP_JS is SPLIT_APP_JS
    assert '<link rel="stylesheet" href="/app.css">' in INDEX_HTML
    assert '<script src="/app.js"></script>' in INDEX_HTML
    assert ".approved-verification-control" in APP_CSS
    assert ".task-review-panel" in APP_CSS
    assert "refreshSnapshotAfterApprovedAction" in APP_JS
    assert "isTaskPromotionAction" in APP_JS
    assert "Approve & promote" in APP_JS
    assert "data-promotion-context" in APP_JS
    assert "data-promotion-approval" not in APP_JS
    assert 'id="task-review-panel"' in INDEX_HTML
    assert "I approve this exact Dev-Flow command" in APP_JS


def test_operating_layer_approved_action_result_retention_hooks_are_present() -> None:
    assert "lastApprovedActionResult" in APP_JS
    assert "rememberApprovedActionResult" in APP_JS
    assert "refreshSnapshotAfterApprovedAction" in APP_JS
    assert "preservedActionResultForSelectedTask" in APP_JS
    assert "Last approved command" in APP_JS


def test_operating_layer_active_nav_item_scrolls_into_mobile_view() -> None:
    assert "scrollActiveNavIntoView" in APP_JS
    assert "scrollIntoView({ block: \"nearest\", inline: \"center\" })" in APP_JS
    assert "scrollActiveNavIntoView(link)" in APP_JS


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
    assert payload["lanes"][5]["name"] == "new"
    assert payload["lanes"][5]["task_ids"] == ["task-0001"]
    assert payload["tasks"][0]["id"] == "task-0001"
    assert payload["tasks"][0]["lane"] == "new"
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
    assert payload["gate_receipts"][0]["task_id"] == "task-0001"
    assert payload["gate_receipts"][0]["next_gate"] == "run_worker"
    assert payload["mission_feed"][0]["label"] == "Task progress"
    assert payload["mission_feed"][0]["task_id"] == "task-0001"
    assert payload["mission_feed"][0]["detail"] == "2/5 required steps done. Next: run a worker."
    assert payload["freshness"]["snapshot_path"] == ".devflow/freshness/latest.json"

    assert not (tmp_path / ".devflow" / "freshness" / "latest.json").exists()
    assert not (tmp_path / ".devflow" / "freshness" / "events.jsonl").exists()


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
    assert snapshot.questions[0].question == "Which API shape should I preserve?"
    assert snapshot.inbox[0].kind == "question"
    assert snapshot.inbox[0].priority == 10
    assert snapshot.inbox[0].message == "Which API shape should I preserve?"
    assert snapshot.inbox[0].command == "devflow task show task-0001"


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
    assert snapshot.tasks[0].next_action.command == (
        "devflow task run task-0001 --worker shell --project demo -- <command>"
    )
    assert snapshot.tasks[0].actions[1].command == "devflow task show task-0001 --project demo"
    projects = {project.project_id: project for project in snapshot.multi_project.projects}
    assert projects["demo"].next_action == "devflow project status demo"
    assert projects["missing"].path_status == "missing"
    assert projects["missing"].next_action == "devflow project doctor missing"


def test_operating_layer_server_serves_app_and_snapshot(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    assert runner.invoke(app, ["task", "create", "ui shell task"]).exit_code == 0

    server = OperatingLayerHTTPServer(("127.0.0.1", 0), tmp_path)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        connection = HTTPConnection(host, port, timeout=5)
        connection.request("GET", "/")
        response = connection.getresponse()
        body = response.read().decode("utf-8")
        assert response.status == 200
        assert "Dev-Flow Operating Layer" in body
        assert "Operating Map" in body
        assert ">Goals<" in body
        assert "Scope" in body
        assert 'aria-live="polite"' in body
        assert "Spec Board" in body
        assert "Goal Board" in body
        assert "Task Progress" in body
        assert "progress-summary-grid" in body
        assert "progress-checklist" in body
        assert "Multi-Project Overview" in body
        assert "Action Rail" in body
        assert "action-preview" in body
        assert 'data-toggle-section="actions"' in body
        assert "global-filter" in body
        assert "Question &amp; Blocker Inbox" in body or "Question & Blocker Inbox" in body
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
        assert "map-list" in css
        assert "map-node" in css
        assert "context-bar" in css
        assert "focus-visible" in css
        assert "lane-board" in css
        assert "goal-board-list" in css
        assert "goal-select" in css
        assert "gate-card" in css
        assert "progress-task-row" in css
        assert "progress-step-grid" in css
        assert "work-status-card" in css
        assert "event-status-card" in css
        assert "action-preview-grid" in css
        assert "filter-control" in css
        assert "page-hidden" in css

        connection.request("GET", "/app.js")
        response = connection.getresponse()
        js = response.read().decode("utf-8")
        assert response.status == 200
        assert "renderOperatingMap" in js
        assert "renderContextBar" in js
        assert "currentContext" in js
        assert "clearContext" in js
        assert "clear-context-button" in js
        assert "aria-current" in js
        assert "aria-pressed" in js
        assert "keydown" in js
        assert "Escape" in js
        assert "operatingMapNodes" in js
        assert "selectedMapNode" in js
        assert "mapScopedActions" in js
        assert "visibleTasksForMapScope" in js
        assert "visibleGateReceipts" in js
        assert "filterGateReceipts" in js
        assert "visibleEvidence" in js
        assert "mapStatus" in js
        assert "renderGoalBoard" in js
        assert "renderProgressTask" in js
        assert "progressStepState" in js
        assert "plainTaskStatusLine" in js
        assert "plainEventLabel" in js
        assert "plainFeedDetail" in js
        assert "renderActionPreview" in js
        assert "selectedActionCommand" in js
        assert "globalFilter" in js
        assert "taskMatchesFilter" in js
        assert "selectedGoalSelection" in js
        assert "goalSelectionPayload" in js
        assert "selectedGoalTaskIds" in js
        assert "selectedGoalGateReceipts" in js
        assert "selectedGoalEvidence" in js
        assert "plainGoalState" in js
        assert "goal-page-card" in js
        assert "pageSections" in js
        assert 'lanes: ["command", "lanes", "context"]' in js
        assert 'gates: ["command", "gates", "context"]' in js
        assert 'projects: ["command", "projects"]' in js
        assert "setCurrentPage" in js
        assert "hashchange" in js
        assert "gateSummary" in js
        assert "evidenceSummary" in js
        assert "/api/snapshot?project=" in js
        assert "all-projects-button" in js
        assert "/api/actions/run" in js
        assert "executeAction" in js
        assert "refreshSnapshotAfterApprovedAction" in js
        assert "await refreshSnapshotAfterApprovedAction(action)" in js
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


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
    assert {check["id"] for check in plan["checks"]} >= {
        "desktop-screenshot",
        "mobile-screenshot",
        "no-horizontal-overflow",
        "orchestrator-first",
        "mission-feed-contained",
        "worker-progress-rows",
        "action-rail-safety-states",
    }
    assert all(check["status"] == "pass" for check in plan["checks"])


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
        "app loads -> first viewport renders Orchestrator, Mission Feed, worker progress, "
        "and Action Rail safety states without horizontal overflow"
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
    assert payload["image_fallback"]["status"] == "pass"
    assert payload["image_fallback"]["format"] == "png+svg"
    assert payload["image_fallback"]["capture_method"] == "deterministic-snapshot-fallback"
    assert payload["image_fallback"]["browser_ready"] is False
    for artifact in payload["image_fallback"]["artifacts"]:
        current = tmp_path / artifact["current"]
        baseline = tmp_path / artifact["baseline"]
        current_png = tmp_path / artifact["current_png"]
        baseline_png = tmp_path / artifact["baseline_png"]
        current_metadata = tmp_path / artifact["current_metadata"]
        baseline_metadata = tmp_path / artifact["baseline_metadata"]
        assert current.exists(), artifact
        assert baseline.exists(), artifact
        assert current_png.exists(), artifact
        assert baseline_png.exists(), artifact
        assert current_metadata.exists(), artifact
        assert baseline_metadata.exists(), artifact
        assert artifact["capture_method"] == "deterministic-snapshot-fallback"
        assert current.read_text(encoding="utf-8").startswith("<svg")
        assert "Dev-Flow Operating Layer" in current.read_text(encoding="utf-8")
        assert current_png.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


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
                "orchestrator_first": True,
                "mission_feed_contained": True,
                "worker_progress_rows": True,
                "action_rail_safety_states": True,
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

    server = OperatingLayerHTTPServer(("127.0.0.1", 0), tmp_path)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
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

    server = OperatingLayerHTTPServer(("127.0.0.1", 0), tmp_path)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        connection = HTTPConnection(host, port, timeout=5)
        command = "devflow task run task-0001 --worker shell -- echo hi"
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


def test_operating_layer_server_runs_approved_task_verification(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    assert runner.invoke(app, ["task", "create", "approved verification action"]).exit_code == 0
    run = runner.invoke(app, ["task", "run", "task-0001", "--shell", "echo done > result.txt"])
    assert run.exit_code == 0, run.output

    command = 'devflow task verify task-0001 --shell "test -f result.txt"'
    server = OperatingLayerHTTPServer(("127.0.0.1", 0), tmp_path)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
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
    server = OperatingLayerHTTPServer(("127.0.0.1", 0), tmp_path)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
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
