"""Tests for builder/judge adapter."""

import json
from pathlib import Path
from datetime import datetime

import pytest

from devflow.loop.builder_judge import (
    BuilderJudgeAssignment,
    BuilderJudgeLink,
    prepare_builder_judge_assignment,
    record_builder_judge_result,
)
from devflow.loop.models import DevFlowLoopState, LoopStage, new_loop_state
from devflow.legacy.control_room.pipeline_run import create_pipeline_run, update_pipeline_run_record


@pytest.fixture
def tmp_run(tmp_path: Path) -> tuple[Path, str]:
    """Create a temporary pipeline run."""
    run_id = create_pipeline_run(tmp_path, {"test": "data"})
    return tmp_path, run_id


@pytest.fixture
def setup_assignment_state(
    tmp_run: tuple[Path, str]
) -> tuple[Path, str, DevFlowLoopState]:
    """Setup a pipeline run with assignment stage state."""
    root, run_id = tmp_run
    state = new_loop_state(run_id)
    state = state.model_copy(update={"stage": LoopStage.assignment})
    # Save state to the pipeline run directory
    state_json = state.model_dump_json(indent=2, ensure_ascii=False)
    update_pipeline_run_record(root, run_id, "loop-state.json", state_json)
    return root, run_id, state


@pytest.fixture
def setup_build_judge_state(
    tmp_run: tuple[Path, str]
) -> tuple[Path, str, DevFlowLoopState]:
    """Setup a pipeline run with build_judge stage state."""
    root, run_id = tmp_run
    state = new_loop_state(run_id)
    state = state.model_copy(update={"stage": LoopStage.build_judge})
    # Save state to the pipeline run directory
    state_json = state.model_dump_json(indent=2, ensure_ascii=False)
    update_pipeline_run_record(root, run_id, "loop-state.json", state_json)
    return root, run_id, state


class TestBuilderJudgeAssignment:
    """Test BuilderJudgeAssignment model."""

    def test_creation(self):
        """Test creating a BuilderJudgeAssignment."""
        assignment = BuilderJudgeAssignment(
            run_id="run-123",
            assignment_id="assign-456",
            definition_of_done="Code passes all tests",
            target_files=["src/main.py", "tests/test_main.py"],
            verification_command="pytest tests/",
        )
        assert assignment.run_id == "run-123"
        assert assignment.assignment_id == "assign-456"
        assert assignment.definition_of_done == "Code passes all tests"
        assert assignment.target_files == ["src/main.py", "tests/test_main.py"]
        assert assignment.verification_command == "pytest tests/"
        assert assignment.builder_judge_run_id is None

    def test_serialization(self):
        """Test serialization and deserialization."""
        assignment = BuilderJudgeAssignment(
            run_id="run-123",
            assignment_id="assign-456",
            definition_of_done="Code passes all tests",
            target_files=["src/main.py"],
            builder_judge_run_id="bj-run-789",
        )
        # Serialize
        json_str = assignment.model_dump_json()
        assert isinstance(json_str, str)
        assert "run-123" in json_str
        assert "assign-456" in json_str
        
        # Deserialize
        deserialized = BuilderJudgeAssignment.model_validate_json(json_str)
        assert deserialized.run_id == assignment.run_id
        assert deserialized.assignment_id == assignment.assignment_id
        assert deserialized.builder_judge_run_id == assignment.builder_judge_run_id

    def test_defaults(self):
        """Test default values."""
        assignment = BuilderJudgeAssignment(
            run_id="run-123",
            assignment_id="assign-456",
            definition_of_done="Test",
        )
        assert assignment.target_files == []
        assert assignment.verification_command is None
        assert assignment.builder_judge_run_id is None


class TestBuilderJudgeLink:
    """Test BuilderJudgeLink model."""

    def test_creation(self):
        """Test creating a BuilderJudgeLink."""
        link = BuilderJudgeLink(
            run_id="run-123",
            assignment_id="assign-456",
            builder_judge_run_id="bj-run-789",
            status="pending",
            evidence_path="evidence.json",
            created_at="2024-01-01T00:00:00Z",
        )
        assert link.run_id == "run-123"
        assert link.assignment_id == "assign-456"
        assert link.builder_judge_run_id == "bj-run-789"
        assert link.status == "pending"
        assert link.evidence_path == "evidence.json"

    def test_serialization(self):
        """Test serialization and deserialization."""
        now = datetime.utcnow().isoformat()
        link = BuilderJudgeLink(
            run_id="run-123",
            assignment_id="assign-456",
            builder_judge_run_id="bj-run-789",
            status="passed",
            created_at=now,
        )
        # Serialize
        json_str = link.model_dump_json()
        assert isinstance(json_str, str)
        assert "run-123" in json_str
        assert "passed" in json_str
        
        # Deserialize
        deserialized = BuilderJudgeLink.model_validate_json(json_str)
        assert deserialized.run_id == link.run_id
        assert deserialized.status == link.status
        assert deserialized.created_at == link.created_at

    def test_valid_statuses(self):
        """Test that only valid statuses are accepted."""
        # These should all work without error
        valid_statuses = ["pending", "running", "passed", "failed", "needs_review"]
        for status in valid_statuses:
            link = BuilderJudgeLink(
                run_id="run-123",
                assignment_id="assign-456",
                builder_judge_run_id="bj-run-789",
                status=status,
                created_at="2024-01-01T00:00:00Z",
            )
            assert link.status == status


class TestPrepareBuilderJudgeAssignment:
    """Test prepare_builder_judge_assignment function."""

    def test_advances_from_assignment(self, setup_assignment_state):
        """Test that prepare advances from assignment to build_judge."""
        root, run_id, _ = setup_assignment_state
        
        assignment = BuilderJudgeAssignment(
            run_id=run_id,
            assignment_id="assign-001",
            definition_of_done="Code works correctly",
            target_files=["src/main.py"],
        )
        
        new_state, link = prepare_builder_judge_assignment(root, assignment)
        
        assert new_state.stage == LoopStage.build_judge
        assert link.run_id == run_id
        assert link.assignment_id == "assign-001"
        assert link.builder_judge_run_id == "assign-001"  # Falls back to assignment_id
        assert link.status == "pending"

    def test_stays_at_build_judge(self, setup_build_judge_state):
        """Test that prepare stays at build_judge if already there."""
        root, run_id, _ = setup_build_judge_state
        
        assignment = BuilderJudgeAssignment(
            run_id=run_id,
            assignment_id="assign-002",
            definition_of_done="Code works correctly",
        )
        
        new_state, link = prepare_builder_judge_assignment(root, assignment)
        
        assert new_state.stage == LoopStage.build_judge
        assert link.status == "pending"

    def test_rejects_wrong_stage(self, tmp_run):
        """Test that prepare rejects stages other than assignment or build_judge."""
        root, run_id = tmp_run
        state = new_loop_state(run_id)
        state = state.model_copy(update={"stage": LoopStage.verification})
        state_json = state.model_dump_json(indent=2, ensure_ascii=False)
        update_pipeline_run_record(root, run_id, "loop-state.json", state_json)
        
        assignment = BuilderJudgeAssignment(
            run_id=run_id,
            assignment_id="assign-003",
            definition_of_done="Test",
        )
        
        with pytest.raises(ValueError, match="Expected stage assignment or build_judge"):
            prepare_builder_judge_assignment(root, assignment)

    def test_writes_link_file(self, setup_assignment_state):
        """Test that prepare writes builder-judge-link.json."""
        root, run_id, _ = setup_assignment_state
        
        assignment = BuilderJudgeAssignment(
            run_id=run_id,
            assignment_id="assign-004",
            definition_of_done="Test",
        )
        
        prepare_builder_judge_assignment(root, assignment)
        
        # Check that the link file was written (nested under .devflow/pipeline-runs/)
        run_dir = root / ".devflow" / "pipeline-runs" / run_id
        link_file = run_dir / "builder-judge-link.json"
        assert link_file.exists()
        
        link_data = json.loads(link_file.read_text())
        assert link_data["assignment_id"] == "assign-004"
        assert link_data["status"] == "pending"

    def test_uses_provided_run_id(self, setup_assignment_state):
        """Test that prepare uses provided builder_judge_run_id."""
        root, run_id, _ = setup_assignment_state
        
        assignment = BuilderJudgeAssignment(
            run_id=run_id,
            assignment_id="assign-005",
            definition_of_done="Test",
            builder_judge_run_id="custom-run-id",
        )
        
        new_state, link = prepare_builder_judge_assignment(root, assignment)
        
        assert link.builder_judge_run_id == "custom-run-id"
        assert "custom-run-id" in new_state.builder_judge_runs

    def test_uses_assignment_id_as_fallback(self, setup_assignment_state):
        """Test that prepare uses assignment_id as fallback."""
        root, run_id, _ = setup_assignment_state
        
        assignment = BuilderJudgeAssignment(
            run_id=run_id,
            assignment_id="fallback-id",
            definition_of_done="Test",
        )
        
        new_state, link = prepare_builder_judge_assignment(root, assignment)
        
        assert link.builder_judge_run_id == "fallback-id"
        assert "fallback-id" in new_state.builder_judge_runs


class TestRecordBuilderJudgeResult:
    """Test record_builder_judge_result function."""

    def test_advances_on_passed(self, setup_build_judge_state):
        """Test that record advances to verification on passed status."""
        root, run_id, _ = setup_build_judge_state
        
        new_state, link = record_builder_judge_result(
            root,
            run_id,
            builder_judge_run_id="bj-run-001",
            status="passed",
        )
        
        assert new_state.stage == LoopStage.verification
        assert link.status == "passed"

    def test_stays_on_failed(self, setup_build_judge_state):
        """Test that record stays at build_judge on failed status."""
        root, run_id, _ = setup_build_judge_state
        
        new_state, link = record_builder_judge_result(
            root,
            run_id,
            builder_judge_run_id="bj-run-002",
            status="failed",
        )
        
        assert new_state.stage == LoopStage.build_judge
        assert link.status == "failed"

    def test_stays_on_needs_review(self, setup_build_judge_state):
        """Test that record stays at build_judge on needs_review status."""
        root, run_id, _ = setup_build_judge_state
        
        new_state, link = record_builder_judge_result(
            root,
            run_id,
            builder_judge_run_id="bj-run-003",
            status="needs_review",
        )
        
        assert new_state.stage == LoopStage.build_judge
        assert link.status == "needs_review"

    def test_rejects_invalid_status(self, setup_build_judge_state):
        """Test that record rejects invalid status."""
        root, run_id, _ = setup_build_judge_state
        
        with pytest.raises(ValueError, match="Invalid status"):
            record_builder_judge_result(
                root,
                run_id,
                builder_judge_run_id="bj-run-004",
                status="invalid_status",
            )

    def test_rejects_wrong_stage(self, tmp_run):
        """Test that record rejects stages other than build_judge."""
        root, run_id = tmp_run
        state = new_loop_state(run_id)
        state = state.model_copy(update={"stage": LoopStage.verification})
        state_json = state.model_dump_json(indent=2, ensure_ascii=False)
        update_pipeline_run_record(root, run_id, "loop-state.json", state_json)
        
        with pytest.raises(ValueError, match="Expected stage build_judge"):
            record_builder_judge_result(
                root,
                run_id,
                builder_judge_run_id="bj-run-005",
                status="passed",
            )

    def test_writes_link_file(self, setup_build_judge_state):
        """Test that record writes builder-judge-link.json."""
        root, run_id, _ = setup_build_judge_state
        
        record_builder_judge_result(
            root,
            run_id,
            builder_judge_run_id="bj-run-006",
            status="passed",
        )
        
        link_file = Path(root) / ".devflow" / "pipeline-runs" / run_id / "builder-judge-link.json"
        assert link_file.exists()
        
        link_data = json.loads(link_file.read_text())
        assert link_data["status"] == "passed"
        assert link_data["builder_judge_run_id"] == "bj-run-006"

    def test_uses_custom_evidence_path(self, setup_build_judge_state):
        """Test that record uses custom evidence path."""
        root, run_id, _ = setup_build_judge_state
        
        _, link = record_builder_judge_result(
            root,
            run_id,
            builder_judge_run_id="bj-run-007",
            status="passed",
            evidence_path="custom/evidence.json",
        )
        
        assert link.evidence_path == "custom/evidence.json"
        
        # Check file content
        link_file = Path(root) / ".devflow" / "pipeline-runs" / run_id / "builder-judge-link.json"
        link_data = json.loads(link_file.read_text())
        assert link_data["evidence_path"] == "custom/evidence.json"


class TestIdempotency:
    """Test idempotency of adapter operations."""

    def test_prepare_idempotent(self, setup_assignment_state):
        """Test that calling prepare twice doesn't break things."""
        root, run_id, _ = setup_assignment_state
        
        assignment = BuilderJudgeAssignment(
            run_id=run_id,
            assignment_id="assign-008",
            definition_of_done="Test",
        )
        
        # First call
        state1, link1 = prepare_builder_judge_assignment(root, assignment)
        assert state1.stage == LoopStage.build_judge
        
        # Second call - should still work
        state2, link2 = prepare_builder_judge_assignment(root, assignment)
        assert state2.stage == LoopStage.build_judge
        assert link2.builder_judge_run_id == link1.builder_judge_run_id

    def test_record_idempotent(self, setup_build_judge_state):
        """Test that calling record twice doesn't break things."""
        root, run_id, _ = setup_build_judge_state
        
        # First call
        state1, link1 = record_builder_judge_result(
            root,
            run_id,
            builder_judge_run_id="bj-run-009",
            status="failed",
        )
        assert state1.stage == LoopStage.build_judge
        
        # Second call
        state2, link2 = record_builder_judge_result(
            root,
            run_id,
            builder_judge_run_id="bj-run-009",
            status="passed",
        )
        assert state2.stage == LoopStage.verification
        assert link2.status == "passed"


class TestEndToEnd:
    """Test complete flow from assignment to verification."""

    def test_full_workflow(self, setup_assignment_state):
        """Test complete workflow: assignment → build_judge → verification."""
        root, run_id, _ = setup_assignment_state
        
        # Step 1: Prepare assignment (advances to build_judge)
        assignment = BuilderJudgeAssignment(
            run_id=run_id,
            assignment_id="e2e-assign",
            definition_of_done="Full workflow test",
            target_files=["src/main.py"],
        )
        
        state1, link1 = prepare_builder_judge_assignment(root, assignment)
        assert state1.stage == LoopStage.build_judge
        assert link1.status == "pending"
        
        # Step 2: Record failed result (stays at build_judge)
        state2, link2 = record_builder_judge_result(
            root,
            run_id,
            builder_judge_run_id="e2e-bj-run",
            status="failed",
        )
        assert state2.stage == LoopStage.build_judge
        assert link2.status == "failed"
        
        # Step 3: Record passed result (advances to verification)
        state3, link3 = record_builder_judge_result(
            root,
            run_id,
            builder_judge_run_id="e2e-bj-run",
            status="passed",
        )
        assert state3.stage == LoopStage.verification
        assert link3.status == "passed"
        
        # Verify link file was updated
        link_file = Path(root) / ".devflow" / "pipeline-runs" / run_id / "builder-judge-link.json"
        link_data = json.loads(link_file.read_text())
        assert link_data["status"] == "passed"
        assert link_data["builder_judge_run_id"] == "e2e-bj-run"
