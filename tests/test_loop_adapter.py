"""Tests for devflow.loop.adapter — bridge between pipeline_run and LoopState."""

from __future__ import annotations

import json
from pathlib import Path

from devflow.legacy.control_room.pipeline_run import (
    create_pipeline_run,
    pipeline_runs_dir,
    update_pipeline_run_record,
)
from devflow.loop.adapter import (
    create_run_with_state,
    infer_stage,
    load_loop_state,
    save_loop_state,
)
from devflow.loop.models import DevFlowLoopState, LoopStage


# ---------------------------------------------------------------------------
# infer_stage — mapping logic
# ---------------------------------------------------------------------------
class TestInferStage:
    def test_validation_success_returns_verification(self) -> None:
        data = {
            "validation.json": {"results": {"checks": "passed"}, "status": "ok"},
        }
        assert infer_stage(data) == LoopStage.verification

    def test_validation_with_errors_skips_verification(self) -> None:
        data = {
            "validation.json": {"results": {"checks": "passed"}, "errors": ["fail"]},
            "loop-packet.md": "",
            "readiness-packet.md": "",
            "classification.json": {},
            "brainstorm.md": "",
        }
        assert infer_stage(data) == LoopStage.idea

    def test_nonempty_loop_packet_returns_build_judge(self) -> None:
        data = {
            "loop-packet.md": "# Build packet content",
            "validation.json": {},
            "readiness-packet.md": "",
            "classification.json": {},
            "brainstorm.md": "",
        }
        assert infer_stage(data) == LoopStage.build_judge

    def test_nonempty_readiness_packet_returns_assignment(self) -> None:
        data = {
            "loop-packet.md": "",
            "readiness-packet.md": "# Readiness packet",
            "validation.json": {},
            "classification.json": {},
            "brainstorm.md": "",
        }
        assert infer_stage(data) == LoopStage.assignment

    def test_classification_with_planning_keys_returns_planning(self) -> None:
        data = {
            "loop-packet.md": "",
            "readiness-packet.md": "",
            "classification.json": {"subtasks": ["t1"]},
            "brainstorm.md": "",
        }
        assert infer_stage(data) == LoopStage.planning

    def test_classification_without_planning_keys_returns_spec(self) -> None:
        data = {
            "loop-packet.md": "",
            "readiness-packet.md": "",
            "classification.json": {"tags": ["ui"]},
            "brainstorm.md": "",
        }
        assert infer_stage(data) == LoopStage.spec

    def test_nonempty_brainstorm_returns_definition(self) -> None:
        data = {
            "loop-packet.md": "",
            "readiness-packet.md": "",
            "classification.json": {},
            "brainstorm.md": "Some brainstorming content",
        }
        assert infer_stage(data) == LoopStage.definition

    def test_empty_all_files_returns_idea(self) -> None:
        data = {
            "validation.json": {},
            "loop-packet.md": "",
            "readiness-packet.md": "",
            "classification.json": {},
            "brainstorm.md": "",
        }
        assert infer_stage(data) == LoopStage.idea

    def test_empty_dict_returns_idea(self) -> None:
        assert infer_stage({}) == LoopStage.idea


# ---------------------------------------------------------------------------
# load_loop_state — real filesystem round-trip
# ---------------------------------------------------------------------------
class TestLoadLoopState:
    def test_loads_from_real_pipeline_run(self, tmp_path: Path) -> None:
        run_id = create_pipeline_run(tmp_path, {"repo": "test/repo"})
        state = load_loop_state(tmp_path, run_id)
        assert isinstance(state, DevFlowLoopState)
        assert state.run_id == run_id
        assert state.stage == LoopStage.idea

    def test_loads_artifacts(self, tmp_path: Path) -> None:
        run_id = create_pipeline_run(tmp_path, {"repo": "test/repo"})
        update_pipeline_run_record(
            tmp_path, run_id, "artifacts.json",
            {"spec_path": "/tmp/spec.md", "assignments": ["task-1"]}
        )
        state = load_loop_state(tmp_path, run_id)
        assert state.spec_path == "/tmp/spec.md"
        assert state.assignments == ["task-1"]

    def test_loads_inferred_stage(self, tmp_path: Path) -> None:
        run_id = create_pipeline_run(tmp_path, {"repo": "test/repo"})
        update_pipeline_run_record(
            tmp_path, run_id, "readiness-packet.md", "# Readiness content"
        )
        state = load_loop_state(tmp_path, run_id)
        assert state.stage == LoopStage.assignment


# ---------------------------------------------------------------------------
# save_loop_state — writes loop-state.json
# ---------------------------------------------------------------------------
class TestSaveLoopState:
    def test_writes_loop_state_json(self, tmp_path: Path) -> None:
        run_id = create_pipeline_run(tmp_path, {"repo": "test/repo"})
        state = load_loop_state(tmp_path, run_id)
        save_loop_state(tmp_path, state)

        # Verify file exists and is valid JSON
        state_file = pipeline_runs_dir(tmp_path) / run_id / "loop-state.json"
        assert state_file.exists()
        data = json.loads(state_file.read_text())
        assert data["run_id"] == run_id
        assert data["stage"] == "idea"

    def test_appends_stage_change_event(self, tmp_path: Path) -> None:
        run_id = create_pipeline_run(tmp_path, {"repo": "test/repo"})
        # Advance state by writing loop-packet.md to simulate build_judge
        update_pipeline_run_record(
            tmp_path, run_id, "loop-packet.md", "# Build packet"
        )
        state = load_loop_state(tmp_path, run_id)
        assert state.stage == LoopStage.build_judge

        # Save — should detect stage change from idea -> build_judge
        save_loop_state(tmp_path, state)

        # Check run-log.jsonl has an event
        log_file = pipeline_runs_dir(tmp_path) / run_id / "run-log.jsonl"
        lines = [ln for ln in log_file.read_text().splitlines() if ln.strip()]
        assert len(lines) == 1
        event = json.loads(lines[0])
        assert event["event"] == "stage_changed"
        assert event["from"] == "idea"
        assert event["to"] == "build_judge"

    def test_no_event_when_stage_unchanged(self, tmp_path: Path) -> None:
        run_id = create_pipeline_run(tmp_path, {"repo": "test/repo"})
        state = load_loop_state(tmp_path, run_id)
        save_loop_state(tmp_path, state)

        log_file = pipeline_runs_dir(tmp_path) / run_id / "run-log.jsonl"
        lines = [ln for ln in log_file.read_text().splitlines() if ln.strip()]
        assert len(lines) == 0


# ---------------------------------------------------------------------------
# create_run_with_state — convenience factory
# ---------------------------------------------------------------------------
class TestCreateRunWithState:
    def test_returns_run_id_and_state(self, tmp_path: Path) -> None:
        run_id, state = create_run_with_state(tmp_path, {"repo": "test/repo"})
        assert isinstance(run_id, str)
        assert isinstance(state, DevFlowLoopState)
        assert state.run_id == run_id

    def test_initial_state_is_idea_stage(self, tmp_path: Path) -> None:
        _, state = create_run_with_state(tmp_path, {"repo": "test/repo"})
        assert state.stage == LoopStage.idea

    def test_run_directory_created(self, tmp_path: Path) -> None:
        run_id, _ = create_run_with_state(tmp_path, {"repo": "test/repo"})
        run_dir = pipeline_runs_dir(tmp_path) / run_id
        assert run_dir.is_dir()


# ---------------------------------------------------------------------------
# Round-trip consistency
# ---------------------------------------------------------------------------
class TestRoundTrip:
    def test_save_then_load_returns_consistent_stage(self, tmp_path: Path) -> None:
        run_id, state = create_run_with_state(tmp_path, {"repo": "test/repo"})
        save_loop_state(tmp_path, state)
        loaded = load_loop_state(tmp_path, run_id)
        assert loaded.stage == state.stage

    def test_round_trip_preserves_artifacts(self, tmp_path: Path) -> None:
        run_id, state = create_run_with_state(tmp_path, {"repo": "test/repo"})
        # Set some artifacts
        state = state.model_copy(update={"spec_path": "/tmp/spec.md"})
        save_loop_state(tmp_path, state)
        loaded = load_loop_state(tmp_path, run_id)
        assert loaded.spec_path == "/tmp/spec.md"
