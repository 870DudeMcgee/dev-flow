"""Tests for the V2 pipeline status board and brainstorm pipeline-run helpers.

The brainstorm chat surface is now Hermes itself — this test covers the
helpers that write pipeline runs and the status board API that reads them.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from devflow.control_room import brainstorm
from devflow.control_room.page import STATUS_PAGE_HTML
from devflow.control_room.server import _extract_run_info, STAGE_ORDER, STAGE_LABELS
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
    assert ".active-left" in STATUS_PAGE_HTML
    assert "display: flex; flex-direction: column; min-height: 0" in STATUS_PAGE_HTML
    assert ".artifact-preview" in STATUS_PAGE_HTML
    assert "flex: 1; min-height: 0; max-height: none; overflow-y: auto" in STATUS_PAGE_HTML
    assert ".worker-feed-container" in STATUS_PAGE_HTML
    assert "worker-output-content" in STATUS_PAGE_HTML
    assert "flex: 1; min-height: 0; overflow-y: auto" in STATUS_PAGE_HTML
    assert 'class="worker-feed-container"' in STATUS_PAGE_HTML
    assert "captureScrollState" in STATUS_PAGE_HTML
    assert "restoreScrollState" in STATUS_PAGE_HTML
    assert "await showArtifact" in STATUS_PAGE_HTML
