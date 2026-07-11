"""Tests for the V2 pipeline status board and brainstorm pipeline-run helpers.

The brainstorm chat surface is now Hermes itself — this test covers the
helpers that write pipeline runs and the status board API that reads them.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from devflow.control_room import brainstorm
from devflow.control_room.page import STATUS_PAGE_HTML
from devflow.control_room.server import (
    _extract_run_info,
    _project_worker_feed,
    record_operator_action,
    STAGE_ORDER,
    STAGE_LABELS,
)
from devflow.loop.adapter import load_loop_state
from devflow.loop.models import LoopStage


@pytest.fixture
def repo_root(tmp_path: Path) -> Path:
    return tmp_path


def test_start_session_creates_pipeline_run_at_idea(repo_root: Path) -> None:
    """When Hermes starts a brainstorm, a pipeline run is created at stage=idea."""
    sid, run_id = brainstorm.start_session(
        repo_root, intent="Build a CNC maintenance tracker"
    )
    assert sid
    assert run_id

    state = load_loop_state(repo_root, run_id)
    assert state.stage == LoopStage.idea

    # Intent written
    intent_path = repo_root / ".devflow" / "pipeline-runs" / run_id / "intent.md"
    assert "CNC maintenance" in intent_path.read_text()


def test_append_brainstorm_writes_to_run(repo_root: Path) -> None:
    """Brainstorm transcript lines get written to the pipeline run."""
    sid, run_id = brainstorm.start_session(repo_root, intent="Test idea")
    brainstorm.append_brainstorm(
        repo_root, session_id=sid, role="assistant",
        content="Let's define the scope more clearly."
    )
    brainstorm.append_brainstorm(
        repo_root, session_id=sid, role="user",
        content="It should track spindle hours and coolant changes."
    )

    md_path = repo_root / ".devflow" / "pipeline-runs" / run_id / "brainstorm.md"
    md = md_path.read_text()
    assert "scope" in md.lower()
    assert "spindle" in md.lower()


def test_escalate_to_definition_advances_loop(repo_root: Path) -> None:
    """Escalating writes definition artifacts and advances idea→definition."""
    sid, run_id = brainstorm.start_session(repo_root, intent="Some idea")
    result = brainstorm.escalate_to_definition(
        repo_root, session_id=sid,
        title="Test Project",
        definition_of_done="It works",
    )
    assert result["stage"] == "definition"
    state = load_loop_state(repo_root, run_id)
    assert state.stage == LoopStage.definition


def test_status_extraction_reads_real_run(repo_root: Path) -> None:
    """The status board API correctly extracts run info from disk."""
    sid, run_id = brainstorm.start_session(repo_root, intent="Status test idea")
    brainstorm.append_brainstorm(
        repo_root, session_id=sid, role="user", content="Detail here"
    )

    from devflow.loop.pipeline_run import load_pipeline_run
    data = load_pipeline_run(repo_root, run_id)
    info = _extract_run_info(run_id, data)

    assert info["run_id"] == run_id
    assert info["stage"] == "idea"
    assert info["stage_label"] == "Brainstorm"
    assert info["stage_index"] == 0
    assert "Status test" in info["intent"]
    assert "brainstorm.md" in info["artifacts"]
    assert info["has_brainstorm"] is True


def test_status_extraction_handles_completed_run(repo_root: Path) -> None:
    """A completed run shows the right stage and all progress segments."""
    sid, run_id = brainstorm.start_session(repo_root, intent="Completed test")
    brainstorm.escalate_to_definition(repo_root, session_id=sid, title="Done project")

    from devflow.loop.pipeline_run import load_pipeline_run
    data = load_pipeline_run(repo_root, run_id)
    info = _extract_run_info(run_id, data)

    assert info["stage"] == "definition"
    assert info["stage_index"] == 1  # definition is index 1


def test_stage_order_complete() -> None:
    """All 10 canonical stages are in the order list."""
    assert len(STAGE_ORDER) == 10
    assert STAGE_ORDER[0] == "idea"
    assert STAGE_ORDER[-1] == "complete"
    assert len(STAGE_LABELS) >= 10


def test_status_extraction_reads_workers(repo_root: Path) -> None:
    """Worker assignments + receipts from loop-state surface on the board."""
    sid, run_id = brainstorm.start_session(repo_root, intent="Workers test")
    from devflow.loop.adapter import load_loop_state, save_loop_state
    from devflow.loop.models import LoopStage
    st = load_loop_state(repo_root, run_id)
    st = st.model_copy(update={
        "stage": LoopStage.build_judge,
        "assignments": [
            {"task_id": "t1", "worker_id": "Ornith-35B", "role": "builder", "status": "active"},
        ],
        "verification_receipts": [
            {"verifier": "pytest", "status": "passed", "passed": True},
        ],
    })
    save_loop_state(repo_root, st)

    from devflow.loop.pipeline_run import load_pipeline_run
    data = load_pipeline_run(repo_root, run_id)
    info = _extract_run_info(run_id, data)

    assert info["stage"] == "build_judge"
    assert len(info["workers"]) == 1
    assert info["workers"][0]["worker"] == "Ornith-35B"
    assert info["workers"][0]["role"] == "builder"
    assert info["receipts"][0]["passed"] is True


def test_worker_feed_projection_separates_execution_status_from_failed_outcome() -> None:
    """A finished dispatch must not look successful when its judge failed."""
    feed = [
        {
            "timestamp": "2026-07-09T17:04:00+00:00",
            "event": "started",
            "role": "builder",
            "model": "ornith-35b",
        },
        {
            "timestamp": "2026-07-09T17:05:00+00:00",
            "event": "completed",
            "role": "judge",
            "model": "qwen-27b-q5km",
            "content": '{"status":"failed","rationale":"Missing edge case"}',
        },
        {
            "timestamp": "2026-07-09T17:06:00+00:00",
            "event": "loop_exhausted",
            "role": "build_judge_loop",
            "model": "devflow-orchestrator",
            "content": '{"max_rounds":2,"last_decision":"failed","next_safe_action":"Return to the orchestrator with judge feedback."}',
        },
        {
            "timestamp": "2026-07-09T17:06:01+00:00",
            "event": "completed",
            "role": "packet_1_dispatch",
            "model": "frontier-orchestrator",
            "content": '{"judge_decision":"failed","build_rounds":2,"build_cap_exhausted":true}',
        },
    ]

    projected = _project_worker_feed("run-1", "build_judge", feed)

    dispatch = projected["entries"][-1]
    assert dispatch["execution_status"] == "completed"
    assert dispatch["outcome"] == "failed"
    assert dispatch["summary"] == "Builder/Judge failed after 2 rounds"
    assert projected["current"]["outcome"] == "failed"
    assert projected["current"]["next_safe_action"] == "Return to the orchestrator with judge feedback."


def test_worker_feed_projection_returns_stable_loop_and_entry_ids() -> None:
    feed = [
        {"timestamp": "2026-07-09T10:00:00+00:00", "event": "started", "role": "planner", "model": "agents-a1-q4"},
        {"timestamp": "2026-07-09T10:01:00+00:00", "event": "completed", "role": "planner", "model": "agents-a1-q4", "content": "plan"},
        {"timestamp": "2026-07-09T10:02:00+00:00", "event": "completed", "role": "planning_judge", "model": "qwen", "content": '{"decision":"approve","next_safe_action":"Proceed to assignment."}'},
    ]

    first = _project_worker_feed("run-1", "planning_judge", feed)
    second = _project_worker_feed("run-1", "planning_judge", feed)

    assert [entry["entry_id"] for entry in first["entries"]] == [entry["entry_id"] for entry in second["entries"]]
    assert first["loops"][0]["loop_id"] == second["loops"][0]["loop_id"]
    assert first["current"]["outcome"] == "passed"
    assert first["current"]["next_safe_action"] == "Proceed to assignment."


def test_artifact_endpoint_serves_and_guards(repo_root: Path) -> None:
    """The /api/artifact endpoint serves real file content and blocks traversal."""
    import io
    from http import HTTPStatus
    from urllib.parse import urlsplit, parse_qs
    from devflow.control_room.server import StatusRequestHandler

    sid, run_id = brainstorm.start_session(repo_root, intent="Artifact endpoint test")

    _root = repo_root  # bind to avoid closure confusion
    captured: dict = {}

    class _FakeHandler(StatusRequestHandler):  # type: ignore[misc]
        def _send_json(self, payload):  # pragma: no cover
            captured["json"] = payload

        def send_response(self, code):  # type: ignore[override]
            captured["code"] = code

        def send_header(self, *args):  # pragma: no cover
            pass

        def end_headers(self):  # pragma: no cover
            captured["headers"] = True

        def send_error(self, code, message=None):  # type: ignore[override]
            captured["code"] = code

        @property
        def wfile(self):
            buf = io.BytesIO()
            captured["body"] = buf
            return buf

        @property
        def server(self):
            class _S:
                repo_root = _root
            return _S()

        @property
        def path(self):
            return self._path  # type: ignore[attr-defined]

    # Valid request
    h = _FakeHandler.__new__(_FakeHandler)
    h._path = f"/api/artifact?run={run_id}&file=brainstorm.md"
    parsed = urlsplit(h._path)
    h._handle_artifact(parse_qs(parsed.query))  # type: ignore[attr-defined]
    assert captured["code"] == HTTPStatus.OK
    assert b"Brainstorm" in captured["body"].getvalue()

    # Traversal attempt must be rejected
    captured.clear()
    h2 = _FakeHandler.__new__(_FakeHandler)
    h2._path = f"/api/artifact?run={run_id}&file=../../../etc/passwd"
    parsed2 = urlsplit(h2._path)
    h2._handle_artifact(parse_qs(parsed2.query))  # type: ignore[attr-defined]
    assert captured["code"] == HTTPStatus.BAD_REQUEST


def test_status_page_uses_full_height_scroll_regions() -> None:
    """Active pipeline panels fill available card height and scroll text bodies."""
    assert "html { height: 100%; overflow: hidden; }" in STATUS_PAGE_HTML
    assert "height: 100vh;" in STATUS_PAGE_HTML
    assert "overflow: hidden;" in STATUS_PAGE_HTML
    assert ".active-left" in STATUS_PAGE_HTML
    assert "display: flex; flex-direction: column; min-height: 0" in STATUS_PAGE_HTML
    assert ".artifact-preview" in STATUS_PAGE_HTML
    assert "flex: 1; min-height: 0; max-height: none; overflow-y: auto" in STATUS_PAGE_HTML
    assert ".worker-feed-container" in STATUS_PAGE_HTML
    assert "output-viewer-content" in STATUS_PAGE_HTML
    assert "flex: 1; min-height: 0; overflow-y: auto" in STATUS_PAGE_HTML
    assert 'class="worker-feed-container"' in STATUS_PAGE_HTML
    assert "captureScrollState" in STATUS_PAGE_HTML
    assert "restoreScrollState" in STATUS_PAGE_HTML
    assert ".worker-card-list" in STATUS_PAGE_HTML
    assert ".viewer-panel" in STATUS_PAGE_HTML
    assert "grid-template-columns: minmax(240px, 300px) minmax(0, 1fr)" in STATUS_PAGE_HTML
    assert "@media (max-width: 900px)" in STATUS_PAGE_HTML
    assert "await showArtifact" in STATUS_PAGE_HTML


def test_status_page_groups_worker_outputs_by_loop_and_preserves_expansion() -> None:
    """Worker output rail leads with the current outcome and keeps raw evidence secondary."""
    assert "Current loop outcome" in STATUS_PAGE_HTML
    assert "worker-current-summary" in STATUS_PAGE_HTML
    assert "Attempts &amp; decisions" in STATUS_PAGE_HTML
    assert "Raw evidence" in STATUS_PAGE_HTML
    assert "r.worker_projection" in STATUS_PAGE_HTML
    assert "worker-loop-group" in STATUS_PAGE_HTML
    assert "data-group-id" in STATUS_PAGE_HTML
    assert "OPEN_WORKER_GROUPS" in STATUS_PAGE_HTML
    assert "CLOSED_WORKER_GROUPS" in STATUS_PAGE_HTML
    assert "IS_RENDERING" in STATUS_PAGE_HTML
    assert "localStorage.getItem('devflow.openWorkerGroups')" in STATUS_PAGE_HTML
    assert "localStorage.getItem('devflow.closedWorkerGroups')" in STATUS_PAGE_HTML
    assert "hasWorkerGroupPreference" in STATUS_PAGE_HTML
    assert "if (IS_RENDERING) return;" in STATUS_PAGE_HTML
    assert "onWorkerGroupToggle" in STATUS_PAGE_HTML
    assert "auto-refreshing live feed" in STATUS_PAGE_HTML
    assert 'type="button" class="${cardClass}"' in STATUS_PAGE_HTML
    assert 'aria-selected="false"' in STATUS_PAGE_HTML
    assert "aria-controls" in STATUS_PAGE_HTML
    assert ":focus-visible" in STATUS_PAGE_HTML
    assert "grid-template-areas" in STATUS_PAGE_HTML
    assert ".worker-loop-group { flex: 0 0 auto;" in STATUS_PAGE_HTML
    assert "loop-title" in STATUS_PAGE_HTML and "text-overflow: ellipsis" in STATUS_PAGE_HTML
    assert "USER_SELECTED_OUTPUT" in STATUS_PAGE_HTML
    assert "if (options.isUserAction) USER_SELECTED_OUTPUT = true;" in STATUS_PAGE_HTML


def test_status_page_keeps_blocked_and_history_runs_inspectable() -> None:
    """Blocked runs stay front-and-center and history rows can reopen details."""
    assert "const liveOrNeedsAttention = runs.filter(r => r.stage !== 'complete');" in STATUS_PAGE_HTML
    assert "Active / Needs Attention" in STATUS_PAGE_HTML
    assert "Click a history row below to inspect its files, activity, and evidence." in STATUS_PAGE_HTML
    assert "function focusRun(runId)" in STATUS_PAGE_HTML
    assert "localStorage.setItem('devflow.focusedRunId', runId)" in STATUS_PAGE_HTML
    assert "onclick=\"focusRun('" in STATUS_PAGE_HTML


def test_assignment_stage_surfaces_operator_control_buttons() -> None:
    """Assignment gates show explicit yes/no controls instead of requiring typing."""
    assert "function renderOperatorControls(r)" in STATUS_PAGE_HTML
    assert "Ready for Builder/Judge?" in STATUS_PAGE_HTML
    assert "Yes — Dispatch Packet 1" in STATUS_PAGE_HTML
    assert "No — Hold / Redirect" in STATUS_PAGE_HTML
    assert "/api/operator-action" in STATUS_PAGE_HTML
    assert "dispatch_packet_1" in STATUS_PAGE_HTML
    assert "hold_redirect" in STATUS_PAGE_HTML


def test_record_operator_action_persists_request(repo_root: Path) -> None:
    """Operator control buttons record visible requests, not hidden model work."""
    _, run_id = brainstorm.start_session(repo_root, intent="Operator control test")

    record = record_operator_action(repo_root, run_id, "dispatch_packet_1")

    assert record["action"] == "dispatch_packet_1"
    actions_path = repo_root / ".devflow" / "pipeline-runs" / run_id / "operator-actions.jsonl"
    assert "dispatch_packet_1" in actions_path.read_text()
    feed_path = repo_root / ".devflow" / "pipeline-runs" / run_id / "worker-feed.jsonl"
    assert "operator_action_requested" in feed_path.read_text()


def test_stop_after_step_persists_cancelling_state(repo_root: Path) -> None:
    _, run_id = brainstorm.start_session(repo_root, intent="Cancelable run")

    record = record_operator_action(repo_root, run_id, "stop_after_step")

    assert record["action"] == "stop_after_step"
    control = (
        repo_root / ".devflow" / "pipeline-runs" / run_id / "execution-control.json"
    ).read_text()
    assert '"status": "cancelling"' in control
    assert '"cancel_mode": "after_step"' in control


def test_stop_now_signals_only_the_recorded_dispatch_process_group(
    repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from types import SimpleNamespace
    from devflow.control_room import server
    from devflow.loop.pipeline_run import update_execution_control

    _, run_id = brainstorm.start_session(repo_root, intent="Immediate stop")
    update_execution_control(
        repo_root, run_id,
        status="running", pid=4321, process_group=4321,
        script=f".devflow/pipeline-runs/{run_id}/runner.py",
    )
    signals: list[tuple[int, int]] = []
    monkeypatch.setattr(server, "_pid_is_alive", lambda pid: pid == 4321)
    monkeypatch.setattr(
        server.subprocess, "run",
        lambda *args, **kwargs: SimpleNamespace(
            stdout=f"python .devflow/pipeline-runs/{run_id}/runner.py"
        ),
    )
    monkeypatch.setattr(server.os, "killpg", lambda pgid, sig: signals.append((pgid, sig)))

    control = server.stop_owned_dispatch(repo_root, run_id)

    assert signals == [(4321, server.signal.SIGTERM)]
    assert control["status"] == "cancelling"
    assert control["cancel_mode"] == "immediate"


def test_status_projection_marks_old_unfinished_role_as_stalled(repo_root: Path) -> None:
    from devflow.loop.pipeline_run import append_worker_feed_entry, load_pipeline_run

    _, run_id = brainstorm.start_session(repo_root, intent="Stalled run")
    append_worker_feed_entry(repo_root, run_id, {
        "timestamp": "2020-01-01T00:00:00+00:00",
        "event": "started",
        "role": "builder",
        "model": "ornith-35b",
    })

    info = _extract_run_info(run_id, load_pipeline_run(repo_root, run_id))

    assert info["execution_status"] == "stalled"
    assert info["worker_projection"]["current"]["outcome"] == "stalled"


def test_status_page_uses_one_focused_workspace_with_live_output_and_stop_controls() -> None:
    assert "renderRunQueue" in STATUS_PAGE_HTML
    assert "focusedRun" in STATUS_PAGE_HTML
    assert "active.map(r => renderActive(r)).join('')" not in STATUS_PAGE_HTML
    assert "Live output" in STATUS_PAGE_HTML
    assert "Stop after current step" in STATUS_PAGE_HTML
    assert "Stop now" in STATUS_PAGE_HTML
    assert "Reclaim stale lock" in STATUS_PAGE_HTML
    assert "OUTPUT_TABS[entryId]" in STATUS_PAGE_HTML
    assert "activateOutputTab(viewer, 'raw')" in STATUS_PAGE_HTML


def test_status_page_prioritizes_now_activity_and_files_drawer() -> None:
    """The focused workspace leads with operator meaning and keeps files on demand."""
    assert 'class="focused-workspace"' in STATUS_PAGE_HTML
    assert 'class="now-card ${escapeHtml(nowOutcome)}"' in STATUS_PAGE_HTML
    assert 'class="activity-card"' in STATUS_PAGE_HTML
    assert 'class="files-drawer ${FILES_DRAWER_OPEN ? \'open\' : \'\'}"' in STATUS_PAGE_HTML
    assert "function renderArtifactTree" in STATUS_PAGE_HTML
    assert "localStorage.getItem('devflow.filesDrawerOpen')" in STATUS_PAGE_HTML
    assert "localStorage.setItem('devflow.filesDrawerOpen'" in STATUS_PAGE_HTML
    assert "toggleFilesDrawer" in STATUS_PAGE_HTML
    assert "closeFilesDrawer" in STATUS_PAGE_HTML
    assert "focusedCompleted\n    ? [...liveOrNeedsAttention, focusedCompleted]" in STATUS_PAGE_HTML


def test_status_page_keeps_diagnostics_in_system_popover() -> None:
    assert 'id="system-widget"' in STATUS_PAGE_HTML
    assert 'id="system-popover"' in STATUS_PAGE_HTML
    assert "toggleSystemDetails" in STATUS_PAGE_HTML
    assert "closeSystemDetails" in STATUS_PAGE_HTML
