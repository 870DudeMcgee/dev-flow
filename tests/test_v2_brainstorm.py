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
from devflow.loop.adapter import advance_loop_state, load_loop_state, save_loop_state
from devflow.loop.models import LoopStage
from devflow.loop.pipeline_run import update_pipeline_run_record


@pytest.fixture
def repo_root(tmp_path: Path) -> Path:
    return tmp_path


def _advance_canonical_fixture(
    root: Path, run_id: str, target: LoopStage
) -> None:
    chain = [
        (LoopStage.definition, "idea-brief", "brainstorm.md"),
        (LoopStage.spec, "orientation-receipt", "orient-result.json"),
        (LoopStage.planning, "spec", "spec.md"),
        (LoopStage.planning_judge, "execution-plan", "execution-plan.json"),
        (LoopStage.assignment, "planning-judge-report", "planning-judge.json"),
        (LoopStage.build_judge, "approved-execution-plan", "execution-plan.json"),
    ]
    for stage, evidence_key, evidence_file in chain:
        if evidence_file not in {"brainstorm.md"}:
            update_pipeline_run_record(root, run_id, evidence_file, {})
        state = load_loop_state(root, run_id)
        state = advance_loop_state(
            root,
            state,
            stage,
            evidence={evidence_key: evidence_file},
        )
        save_loop_state(root, state)
        if stage == target:
            return
    raise AssertionError(f"unsupported fixture target: {target}")


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


def test_dispatch_to_planning_requires_ready_orientation_before_advancing(
    repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from devflow.loop import execution

    sid, run_id = brainstorm.start_session(repo_root, intent="Ground this plan")
    brainstorm.escalate_to_definition(repo_root, session_id=sid)
    called = False

    def fake_planning_loop(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("planner must not run without orientation")

    monkeypatch.setattr(execution, "run_planning_loop", fake_planning_loop)

    with pytest.raises(ValueError, match="orientation receipt"):
        brainstorm.dispatch_to_planning(
            repo_root,
            session_id=sid,
            ensure_lane_on=False,
        )

    assert called is False
    assert load_loop_state(repo_root, run_id).stage == LoopStage.definition


def test_ready_orientation_receipt_is_valid_after_definition(
    repo_root: Path,
) -> None:
    from devflow.loop.orient import OrientResult, require_orientation_receipt

    sid, run_id = brainstorm.start_session(repo_root, intent="Ground this plan")
    brainstorm.escalate_to_definition(repo_root, session_id=sid)
    receipt = OrientResult(
        run_id=run_id,
        stage="definition",
        lane="builder",
        files_to_touch=["src/app.py"],
        ready=True,
    )
    from devflow.loop.orient import save_orient_evidence

    save_orient_evidence(repo_root, run_id, receipt.model_dump_json())

    restored = require_orientation_receipt(repo_root, run_id)
    assert restored.ready is True
    assert restored.files_to_touch == ["src/app.py"]
    assert load_loop_state(repo_root, run_id).stage == LoopStage.definition


def test_resumed_build_includes_last_capped_judge_feedback(
    repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A human continue-work decision must not lose the decisive judge defect."""
    from types import SimpleNamespace
    from devflow.loop.pipeline_run import update_pipeline_run_record
    from devflow.loop import execution
    from devflow.loop.execution_plan import (
        ExecutionPacket,
        ExecutionPlan,
        ExecutionValidator,
        save_execution_plan,
    )

    sid, run_id = brainstorm.start_session(repo_root, intent="Resume a capped build")
    _advance_canonical_fixture(repo_root, run_id, LoopStage.build_judge)
    update_pipeline_run_record(repo_root, run_id, "spec.md", "bounded spec")
    update_pipeline_run_record(repo_root, run_id, "plan.md", "bounded plan")
    update_pipeline_run_record(
        repo_root, run_id, "build-packets.json",
        [{"id": "packet-01", "target_files": ["src/new.py"]}],
    )
    save_execution_plan(
        repo_root,
        run_id,
        ExecutionPlan(
            target_files=["src/new.py"],
            packets=[ExecutionPacket(id="packet-01", target_files=["src/new.py"])],
            validators=[
                ExecutionValidator(
                    id="syntax",
                    argv=["python", "-m", "py_compile", "src/new.py"],
                    evidence=["exit-code"],
                )
            ],
        ),
    )
    update_pipeline_run_record(
        repo_root, run_id, "packet-consolidated-build-judge-summary.json",
        {"final_judge_rationale": "Verification appeared before the builder gate."},
    )
    captured = {}

    def fake_run(*args, **kwargs):
        captured["assignment"] = kwargs["assignment"]
        return {
            "build": SimpleNamespace(model="laguna", content="code"),
            "judge": SimpleNamespace(model="luna"),
            "decision": "passed",
            "verification": None,
            "build_rounds": [{}],
            "build_cap_exhausted": False,
        }

    monkeypatch.setattr(execution, "run_build_judge_verify", fake_run)

    brainstorm.dispatch_to_build(
        repo_root,
        session_id=sid,
        definition_of_done="Stay bounded.",
        target_files=["src/new.py"],
    )

    assert "# Previous capped judge feedback" in captured["assignment"]
    assert "Verification appeared before the builder gate." in captured["assignment"]


def test_dispatch_to_build_uses_authoritative_first_packet_and_holds_remainder(
    repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from types import SimpleNamespace

    from devflow.loop import execution
    from devflow.loop.execution_plan import (
        ExecutionPacket,
        ExecutionPlan,
        ExecutionValidator,
        save_execution_plan,
    )
    from devflow.loop.pipeline_run import update_pipeline_run_record

    sid, run_id = brainstorm.start_session(repo_root, intent="Two packet plan")
    _advance_canonical_fixture(repo_root, run_id, LoopStage.assignment)
    update_pipeline_run_record(repo_root, run_id, "spec.md", "typed spec")
    save_execution_plan(
        repo_root,
        run_id,
        ExecutionPlan(
            target_files=["src/a.py", "tests/test_a.py"],
            packets=[
                ExecutionPacket(id="packet-01", target_files=["src/a.py"]),
                ExecutionPacket(
                    id="packet-02",
                    target_files=["tests/test_a.py"],
                    depends_on=["packet-01"],
                ),
            ],
            validators=[
                ExecutionValidator(
                    id="focused-tests",
                    argv=["python", "-m", "pytest", "tests/test_a.py", "-q"],
                    evidence=["exit-code"],
                )
            ],
        ),
    )
    captured: dict = {}

    def fake_run(*args, **kwargs):
        captured.update(kwargs)
        return {
            "build": SimpleNamespace(model="builder", content="code"),
            "judge": SimpleNamespace(model="judge"),
            "decision": "passed",
            "verification": None,
            "build_rounds": [{}],
            "build_cap_exhausted": False,
        }

    monkeypatch.setattr(execution, "run_build_judge_verify", fake_run)

    result = brainstorm.dispatch_to_build(
        repo_root,
        session_id=sid,
        definition_of_done="Both packets are complete.",
        target_files=["caller.py"],
        verification_command="unsafe shell text",
        ensure_lane_on=False,
    )

    assert captured["target_files"] == ["src/a.py"]
    assert captured["validators"][0].id == "focused-tests"
    assert captured["verification_command"] is None
    assert result["dispatched_packet_id"] == "packet-01"
    assert result["remaining_packet_ids"] == ["packet-02"]
    assert result["plan_complete"] is False
    assert result["dispatch_status"] == "awaiting_packet_scheduler"


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
    _advance_canonical_fixture(repo_root, run_id, LoopStage.build_judge)
    st = load_loop_state(repo_root, run_id)
    st = st.model_copy(update={
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
    assert first["entries"][0]["stages"] == ["spec", "planning"]
    assert first["entries"][-1]["stages"] == ["planning_judge"]


def test_completed_idle_projection_has_no_running_history_and_explains_judge() -> None:
    feed = [
        {
            "timestamp": "2026-07-11T16:22:07+00:00",
            "event": "started",
            "role": "builder",
            "model": "free-code-fleet",
        },
        {
            "timestamp": "2026-07-11T16:22:40+00:00",
            "event": "completed",
            "role": "builder",
            "model": "free-code-fleet",
            "content": "builder finished",
        },
        {
            "timestamp": "2026-07-11T16:22:41+00:00",
            "event": "started",
            "role": "judge",
            "model": "free-review-fleet",
        },
        {
            "timestamp": "2026-07-11T16:22:48+00:00",
            "event": "completed",
            "role": "judge",
            "model": "free-review-fleet",
            "content": (
                '{"status":"passed","rationale":"The change satisfies the contract.",'
                '"diff_evidence":"src/example.py and tests/test_example.py"}'
            ),
            "usage": {"actual_model": "provider/exact-review-model:free"},
        },
    ]

    info = _extract_run_info(
        "run-complete",
        {
            "loop-state.json": {"stage": "complete"},
            "intent.md": "# Intent\n\nDeterministic completion confidence",
            "brainstorm.md": "# Brainstorm Transcript\n\n## User\n\nMake completion decisions auditable.\n\n## Assistant\n\nUnderstood.",
            "spec.md": "Add one deterministic completion function with focused branch tests.",
            "execution-control.json": {"status": "idle"},
            "worker-feed.jsonl": feed,
            "build-manifest.json": {
                "changed_files": ["src/example.py", "tests/test_example.py"],
            },
            "build-diff.patch": "diff --git a/src/example.py b/src/example.py",
            "judge-decision.json": {
                "status": "passed",
                "rationale": "The change satisfies the contract.",
                "diff_evidence": "src/example.py and tests/test_example.py",
            },
            "build-verification.json": {
                "status": "passed",
                "summary": "6 passed in 0.08s",
                "command": "python -m pytest tests/test_example.py",
            },
            "human-decision-accept.json": {
                "decision": "accept",
                "summary": "Accepted after independent review and tests.",
            },
            "worker-live.json": {
                "status": "running",
                "event": "streaming",
                "role": "judge",
                "content": "stale live output",
            },
        },
    )

    assert info["execution_status"] == "idle"
    assert info["worker_projection"]["current"] is None
    assert info["worker_projection"]["latest"]["outcome"] == "passed"
    assert len(info["worker_feed"]) == len(feed)
    assert all(entry["outcome"] != "running" for entry in info["worker_feed"])
    judge = info["worker_feed"][-1]
    assert judge["resolved_model"] == "provider/exact-review-model:free"
    assert judge["resolved_model_recorded"] is True
    assert judge["operator_detail"]["why"] == "The change satisfies the contract."
    assert judge["operator_detail"]["evidence"] == "src/example.py and tests/test_example.py"
    assert info["run_overview"] == {
        "product": "Deterministic completion confidence",
        "why": "Make completion decisions auditable.",
        "scope": "Add one deterministic completion function with focused branch tests.",
        "files": ["src/example.py", "tests/test_example.py"],
        "code_artifact": "build-diff.patch",
        "result": "Accepted after independent review and tests.",
        "evidence": (
            "src/example.py and tests/test_example.py\n"
            "passed · 6 passed in 0.08s · python -m pytest tests/test_example.py"
        ),
        "evidence_artifact": "build-verification.json",
        "next": "No further action is required. Start the next bounded iteration when ready.",
    }


def test_active_projection_marks_only_unmatched_current_start_running() -> None:
    feed = [
        {"timestamp": "2026-07-11T10:00:00+00:00", "event": "started", "role": "builder"},
        {"timestamp": "2026-07-11T10:00:10+00:00", "event": "completed", "role": "builder"},
        {"timestamp": "2026-07-11T10:00:11+00:00", "event": "started", "role": "builder"},
    ]

    projected = _project_worker_feed(
        "run-active",
        "build_judge",
        feed,
        execution_status="running",
    )

    assert [entry["outcome"] for entry in projected["entries"]] == [
        "neutral",
        "completed",
        "running",
    ]
    assert projected["current"] is projected["latest"]
    assert projected["current"]["is_current"] is True


def test_historical_start_inherits_exact_model_from_its_matching_terminal_event() -> None:
    feed = [
        {
            "timestamp": "2026-07-11T16:22:07+00:00",
            "event": "started",
            "role": "builder",
            "model": "free-code-fleet",
        },
        {
            "timestamp": "2026-07-11T16:22:40+00:00",
            "event": "completed",
            "role": "builder",
            "model": "free-code-fleet",
            "usage": {"actual_model": "google/gemma-4-26b-a4b-it:free"},
        },
    ]

    projected = _project_worker_feed(
        "20260711-162136",
        "complete",
        feed,
        execution_status="idle",
    )

    started, completed = projected["entries"]
    assert started["resolved_model"] == "google/gemma-4-26b-a4b-it:free"
    assert started["resolved_model_recorded"] is True
    assert completed["resolved_model"] == "google/gemma-4-26b-a4b-it:free"
    assert started["model"] == completed["model"] == "free-code-fleet"


def test_completed_overview_projects_persisted_reliability_evidence() -> None:
    info = _extract_run_info(
        "run-with-reliability",
        {
            "loop-state.json": {"stage": "complete"},
            "intent.md": "# Intent\n\nReliability-gated release",
            "reliability-report.json": {
                "safe": False,
                "action": "rollback",
                "breaches": ["provider fault threshold exceeded"],
                "metrics": {"provider_faults": 3, "routing_drifts": 0},
                "thresholds": {"max_provider_faults": 2, "max_routing_drifts": 0},
                "recovery_actions": ["Rollback to the last accepted source state."],
            },
        },
    )

    assert "reliability-report.json" in info["artifacts"]
    assert info["run_overview"]["reliability"] == {
        "safe": False,
        "action": "rollback",
        "breaches": ["provider fault threshold exceeded"],
        "breached_metrics": ["provider faults: 3 > threshold 2"],
        "recovery_actions": ["Rollback to the last accepted source state."],
        "artifact": "reliability-report.json",
    }


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


@pytest.mark.parametrize("run_id", ["../outside", "nested/../../outside", "..\\outside"])
def test_artifact_endpoint_rejects_run_id_traversal(repo_root: Path, run_id: str) -> None:
    """The artifact endpoint cannot resolve a run outside pipeline-runs."""
    import io
    from http import HTTPStatus
    from urllib.parse import parse_qs, urlsplit
    from devflow.control_room.server import StatusRequestHandler

    captured: dict = {}
    _root = repo_root

    class _FakeHandler(StatusRequestHandler):  # type: ignore[misc]
        def send_error(self, code, message=None):  # type: ignore[override]
            captured["code"] = code

        @property
        def server(self):
            class _S:
                repo_root = _root
            return _S()

        @property
        def wfile(self):
            return io.BytesIO()

    handler = _FakeHandler.__new__(_FakeHandler)
    handler._handle_artifact(parse_qs(urlsplit(
        f"/api/artifact?run={run_id}&file=brainstorm.md"
    ).query))  # type: ignore[attr-defined]

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
    """Worker output rail leads with the latest outcome and keeps technical evidence secondary."""
    assert "Current loop outcome" in STATUS_PAGE_HTML
    assert "worker-current-summary" in STATUS_PAGE_HTML
    assert "Attempts &amp; decisions" in STATUS_PAGE_HTML
    assert "Technical details" in STATUS_PAGE_HTML
    assert "Latest " in STATUS_PAGE_HTML
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
    assert "function toggleHistory()" in STATUS_PAGE_HTML
    assert "localStorage.getItem('devflow.historyOpen')" in STATUS_PAGE_HTML
    assert 'class="history-section ${HISTORY_OPEN ? \'open\' : \'\'}"' in STATUS_PAGE_HTML


def test_status_page_stage_controls_drive_persisted_evidence_filter() -> None:
    assert "function selectActivityStage(runId, stage)" in STATUS_PAGE_HTML
    assert "localStorage.getItem('devflow.selectedStages')" in STATUS_PAGE_HTML
    assert 'class="stage-control ${cls} ${selected ? \'selected\' : \'\'}"' in STATUS_PAGE_HTML
    assert 'aria-pressed="${selected}"' in STATUS_PAGE_HTML
    assert "(entry.stages || []).includes(selectedStage)" in STATUS_PAGE_HTML
    assert "No model call was recorded for" in STATUS_PAGE_HTML
    assert "stageArtifactCandidates" in STATUS_PAGE_HTML


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
    runner = repo_root / ".devflow" / "pipeline-runs" / run_id / "runner.py"
    runner.write_text("# owned test runner\n", encoding="utf-8")
    update_execution_control(
        repo_root, run_id,
        status="running", pid=4321, process_group=4321,
        script=f".devflow/pipeline-runs/{run_id}/runner.py",
    )
    signals: list[tuple[int, int]] = []
    monkeypatch.setattr(server, "_pid_is_alive", lambda pid: pid == 4321)
    monkeypatch.setattr(server.os, "getpgid", lambda pid: 4321)
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


def test_status_projection_keeps_more_than_two_hundred_events_and_reports_visibility() -> None:
    feed = [
        {
            "timestamp": f"2026-01-01T00:00:{index % 60:02d}+00:00",
            "event": "completed",
            "role": "builder",
            "model": "free-code-fleet",
            "content": str(index),
        }
        for index in range(250)
    ]

    info = _extract_run_info(
        "run-many-events",
        {"loop-state.json": {"stage": "build_judge"}, "worker-feed.jsonl": feed},
    )

    assert len(info["worker_feed"]) == 250
    assert info["worker_feed_total"] == 250
    assert info["worker_feed_visible"] == 250
    assert info["worker_feed_truncated"] is False


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
    assert "activateOutputTab(viewer, 'summary')" in STATUS_PAGE_HTML


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
    assert 'id="header-run-selector"' in STATUS_PAGE_HTML
    assert "text.slice(0, 8000)" not in STATUS_PAGE_HTML


def test_files_drawer_close_survives_live_refresh() -> None:
    """Rehydrating a selected artifact must not undo an explicit Close."""
    assert "async function showArtifact(runId, fileName, silent=false, openDrawer=true)" in STATUS_PAGE_HTML
    assert "if (openDrawer) setFilesDrawerOpen(true);" in STATUS_PAGE_HTML
    assert "/*openDrawer*/ false" in STATUS_PAGE_HTML


def test_status_page_keeps_diagnostics_in_system_popover() -> None:
    assert 'id="system-widget"' in STATUS_PAGE_HTML
    assert 'id="system-popover"' in STATUS_PAGE_HTML
    assert "toggleSystemDetails" in STATUS_PAGE_HTML
    assert "closeSystemDetails" in STATUS_PAGE_HTML
