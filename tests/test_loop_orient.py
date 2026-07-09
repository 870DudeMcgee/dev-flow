"""Tests for devflow.loop.orient — orient/scout adapter."""

from __future__ import annotations

import json
from pathlib import Path

from devflow.legacy.control_room.pipeline_run import create_pipeline_run
from devflow.legacy.control_room.scout_discovery import AgentScoutDiscovery
from devflow.loop.adapter import load_loop_state
from devflow.loop.models import LoopStage
from devflow.loop.orient import OrientResult, orient_packet, run_orient


# ---------------------------------------------------------------------------
# OrientResult construction
# ---------------------------------------------------------------------------
class TestOrientResult:
    def test_creates_from_discovery(self) -> None:
        discovery = AgentScoutDiscovery(
            handoff_path=None,
            handoff_read=False,
            files_to_touch=["src/main.py"],
            files_to_read_next=[{"path": "src/main.py", "reason": "target"}],
            tests=["tests/test_main.py"],
            risks=["risk-1"],
            recommended_lane="build",
            verification="python -m pytest tests/",
            map_freshness={"state": "fresh"},
            evidence_paths=[],
            context_brief=[{"path": "src/main.py", "summary": "entry point"}],
        )
        result = OrientResult.from_discovery(discovery, run_id="run-1")
        assert result.run_id == "run-1"
        assert result.stage == "idea"
        assert result.lane == "build"
        assert result.files_to_touch == ["src/main.py"]
        assert result.files_to_read_next == [{"path": "src/main.py", "reason": "target"}]
        assert result.tests == ["tests/test_main.py"]
        assert result.risks == ["risk-1"]
        assert result.verification == "python -m pytest tests/"
        assert result.map_confidence == "fresh"
        assert result.context_brief == [{"path": "src/main.py", "summary": "entry point"}]
        assert result.ready is True

    def test_ready_false_when_lane_ask_user(self) -> None:
        discovery = AgentScoutDiscovery(
            handoff_path=None,
            handoff_read=False,
            files_to_touch=["src/main.py"],
            files_to_read_next=[],
            tests=[],
            risks=[],
            recommended_lane="ask_user",
            verification="",
            map_freshness={},
            evidence_paths=[],
            context_brief=[],
        )
        result = OrientResult.from_discovery(discovery, run_id="run-1")
        assert result.ready is False

    def test_ready_false_when_no_files(self) -> None:
        discovery = AgentScoutDiscovery(
            handoff_path=None,
            handoff_read=False,
            files_to_touch=[],
            files_to_read_next=[],
            tests=[],
            risks=[],
            recommended_lane="build",
            verification="",
            map_freshness={},
            evidence_paths=[],
            context_brief=[],
        )
        result = OrientResult.from_discovery(discovery, run_id="run-1")
        assert result.ready is False


# ---------------------------------------------------------------------------
# orient_packet
# ---------------------------------------------------------------------------
class TestOrientPacket:
    def test_returns_correct_fields(self, tmp_path: Path) -> None:
        run_id = create_pipeline_run(tmp_path, {"repo": "test/repo"})
        result = orient_packet(tmp_path, run_id)
        assert isinstance(result, OrientResult)
        assert result.run_id == run_id
        assert isinstance(result.files_to_touch, list)
        assert isinstance(result.tests, list)
        assert isinstance(result.risks, list)
        assert isinstance(result.files_to_read_next, list)
        assert isinstance(result.context_brief, list)

    def test_with_no_handoff_and_no_files_returns_not_ready(self, tmp_path: Path) -> None:
        run_id = create_pipeline_run(tmp_path, {"repo": "test/repo"})
        result = orient_packet(tmp_path, run_id)
        assert result.ready is False

    def test_with_files_to_touch_returns_ready_when_lane_not_ask_user(self, tmp_path: Path) -> None:
        run_id = create_pipeline_run(tmp_path, {"repo": "test/repo"})
        # Pass a real file so the discovery finds something
        src_dir = tmp_path / "src"
        src_dir.mkdir(exist_ok=True)
        (src_dir / "main.py").write_text("print('hello')")
        result = orient_packet(tmp_path, run_id, files_to_touch=["src/main.py"])
        assert result.ready is True


# ---------------------------------------------------------------------------
# run_orient
# ---------------------------------------------------------------------------
class TestRunOrient:
    def test_advances_from_idea_to_definition_when_ready(
        self, tmp_path: Path
    ) -> None:
        run_id = create_pipeline_run(tmp_path, {"repo": "test/repo"})
        # Add a real file so orient discovers something
        src_dir = tmp_path / "src"
        src_dir.mkdir(exist_ok=True)
        (src_dir / "main.py").write_text("print('hello')")

        state, orient = run_orient(tmp_path, run_id, files_to_touch=["src/main.py"])
        assert orient.ready is True
        assert state.stage == LoopStage.definition

    def test_does_not_advance_when_not_ready(self, tmp_path: Path) -> None:
        run_id = create_pipeline_run(tmp_path, {"repo": "test/repo"})
        state, orient = run_orient(tmp_path, run_id)
        # orient should not be ready (no files, no handoff)
        assert orient.ready is False
        # Stage should remain idea (no advancement)
        assert state.stage == LoopStage.idea

    def test_writes_orient_result_json(self, tmp_path: Path) -> None:
        run_id = create_pipeline_run(tmp_path, {"repo": "test/repo"})
        run_orient(tmp_path, run_id)

        from devflow.legacy.control_room.pipeline_run import _run_dir
        run_dir = _run_dir(tmp_path, run_id)
        orient_file = run_dir / "orient-result.json"
        assert orient_file.exists()
        data = json.loads(orient_file.read_text())
        assert data["run_id"] == run_id

    def test_round_trip_pipeline_run(self, tmp_path: Path) -> None:
        # Create a pipeline run with a real source file
        src_dir = tmp_path / "src"
        src_dir.mkdir(exist_ok=True)
        (src_dir / "app.py").write_text("def main(): pass")

        run_id = create_pipeline_run(tmp_path, {"repo": "test/repo"})

        # Run orient with files_to_touch
        state, orient = run_orient(tmp_path, run_id, files_to_touch=["src/app.py"])

        # Stage should have advanced
        assert state.stage == LoopStage.definition, f"Expected definition, got {state.stage}"

        # Load state back from filesystem
        reloaded = load_loop_state(tmp_path, run_id)
        assert reloaded.stage == LoopStage.definition, f"Reloaded state: {reloaded.stage}"
