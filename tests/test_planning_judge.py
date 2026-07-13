"""Tests for the planning judge implementation.

These tests verify the deterministic, rule-based judge logic that gates
planning from assignment in the DevFlow pipeline.
"""
import json
from pathlib import Path

import pytest

from devflow.loop.pipeline_run import create_pipeline_run
from devflow.loop.models import (
    LoopStage,
    new_loop_state,
)
from devflow.loop.planning_judge import (
    JudgeDecision,
    PlanningEvidence,
    PlanningJudgeReport,
    judge_plan,
    run_planning_judge,
)


@pytest.fixture
def valid_evidence():
    """Create a valid planning evidence with all required fields."""
    return PlanningEvidence(
        run_id="test-run-001",
        plan_path="plan.md",
        spec_path="spec.md",
        target_files=["src/main.py", "src/utils.py"],
        verification_command="python -m pytest tests/",
        constraints=["must not break CI"],
        files_exist=True,
        has_verification=True,
    )


@pytest.fixture
def run_root(tmp_path):
    """Create a pipeline run directory for testing."""
    run_id = create_pipeline_run(tmp_path, {"repo": "test/repo"})
    return (tmp_path, run_id)


class TestJudgeDecision:
    """Test JudgeDecision enum."""

    def test_judge_decision_has_all_values(self):
        """JudgeDecision enum has all four values."""
        assert JudgeDecision.approve.value == "approve"
        assert JudgeDecision.revise.value == "revise"
        assert JudgeDecision.block.value == "block"
        assert JudgeDecision.escalate_to_user.value == "escalate_to_user"

    def test_judge_decision_values_are_strings(self):
        """All JudgeDecision values are strings."""
        for decision in JudgeDecision:
            assert isinstance(decision.value, str)


class TestPlanningEvidence:
    """Test PlanningEvidence model."""

    def test_evidence_creation(self):
        """PlanningEvidence can be created with required fields."""
        evidence = PlanningEvidence(run_id="test-123")
        assert evidence.run_id == "test-123"
        assert evidence.plan_path is None
        assert evidence.spec_path is None
        assert evidence.target_files == []
        assert evidence.verification_command is None
        assert evidence.constraints == []
        assert evidence.files_exist is False
        assert evidence.has_verification is False

    def test_evidence_serialization(self):
        """PlanningEvidence can be serialized and deserialized."""
        evidence = PlanningEvidence(
            run_id="test-123",
            plan_path="plan.md",
            spec_path="spec.md",
            target_files=["file1.py", "file2.py"],
            verification_command="pytest",
            constraints=["no_breaking_changes"],
            files_exist=True,
            has_verification=True,
        )
        serialized = evidence.model_dump()
        deserialized = PlanningEvidence(**serialized)
        assert deserialized.run_id == evidence.run_id
        assert deserialized.plan_path == evidence.plan_path
        assert deserialized.spec_path == evidence.spec_path
        assert deserialized.target_files == evidence.target_files
        assert deserialized.verification_command == evidence.verification_command
        assert deserialized.constraints == evidence.constraints
        assert deserialized.files_exist == evidence.files_exist
        assert deserialized.has_verification == evidence.has_verification


class TestPlanningJudgeReport:
    """Test PlanningJudgeReport model."""

    def test_report_creation(self):
        """PlanningJudgeReport can be created."""
        report = PlanningJudgeReport(
            run_id="test-123",
            decision=JudgeDecision.approve,
            repo_grounding="Test grounding",
            task_boundaries="Test boundaries",
            verification_reality="Test reality",
            overbuild_risk="Test risk",
            simpler_path="Test path",
            required_changes=[],
            next_safe_action="Test action",
            created_at="2026-01-01T00:00:00Z",
        )
        assert report.run_id == "test-123"
        assert report.decision == JudgeDecision.approve
        assert report.required_changes == []

    def test_report_serialization_round_trip(self):
        """PlanningJudgeReport can be serialized and deserialized."""
        report = PlanningJudgeReport(
            run_id="test-123",
            decision=JudgeDecision.revise,
            repo_grounding="Test grounding",
            task_boundaries="Test boundaries",
            verification_reality="Test reality",
            overbuild_risk="Test risk",
            simpler_path="Test path",
            required_changes=["Change 1", "Change 2"],
            next_safe_action="Test action",
            created_at="2026-01-01T00:00:00Z",
        )
        serialized = report.model_dump_json()
        deserialized = PlanningJudgeReport.model_validate_json(serialized)
        assert deserialized.run_id == report.run_id
        assert deserialized.decision == report.decision
        assert deserialized.required_changes == report.required_changes
        assert deserialized.next_safe_action == report.next_safe_action
        assert deserialized.created_at == report.created_at


class TestJudgePlan:
    """Test judge_plan function."""

    def test_block_when_no_target_files(self, valid_evidence):
        """judge_plan returns BLOCK when no target files."""
        valid_evidence.target_files = []
        report = judge_plan(valid_evidence)
        assert report.decision == JudgeDecision.block
        assert len(report.required_changes) > 0
        assert len(report.next_safe_action) > 0

    def test_block_when_no_spec_path(self, valid_evidence):
        """judge_plan returns BLOCK when no spec_path."""
        valid_evidence.spec_path = None
        report = judge_plan(valid_evidence)
        assert report.decision == JudgeDecision.block

    def test_block_when_no_plan_path(self, valid_evidence):
        """judge_plan returns BLOCK when no plan_path."""
        valid_evidence.plan_path = None
        report = judge_plan(valid_evidence)
        assert report.decision == JudgeDecision.block

    def test_revise_when_files_dont_exist(self, valid_evidence):
        """judge_plan returns REVISE when files_exist is False."""
        valid_evidence.files_exist = False
        report = judge_plan(valid_evidence)
        assert report.decision == JudgeDecision.revise

    def test_revise_when_no_verification(self, valid_evidence):
        """judge_plan returns REVISE when no verification command."""
        valid_evidence.has_verification = False
        valid_evidence.verification_command = None
        report = judge_plan(valid_evidence)
        assert report.decision == JudgeDecision.revise

    def test_revise_when_too_many_target_files(self, valid_evidence):
        """judge_plan returns REVISE when too many target files (>8)."""
        valid_evidence.target_files = [f"file_{i}.py" for i in range(9)]
        report = judge_plan(valid_evidence)
        assert report.decision == JudgeDecision.revise

    def test_escalate_to_user_when_constraints_say_escalate(self, valid_evidence):
        """judge_plan returns ESCALATE_TO_USER when constraints say escalate."""
        valid_evidence.constraints = ["must escalate to user"]
        valid_evidence.files_exist = True
        valid_evidence.has_verification = True
        report = judge_plan(valid_evidence)
        assert report.decision == JudgeDecision.escalate_to_user

    def test_escalate_to_user_when_constraints_say_user_decision(self, valid_evidence):
        """judge_plan returns ESCALATE_TO_USER when constraints say user_decision."""
        valid_evidence.constraints = ["requires user_decision"]
        valid_evidence.files_exist = True
        valid_evidence.has_verification = True
        report = judge_plan(valid_evidence)
        assert report.decision == JudgeDecision.escalate_to_user

    def test_approve_when_all_valid(self, valid_evidence):
        """judge_plan returns APPROVE when all evidence is valid."""
        report = judge_plan(valid_evidence)
        assert report.decision == JudgeDecision.approve
        assert len(report.required_changes) == 0

    def test_typed_validators_are_explicit_planning_evidence(self, valid_evidence):
        valid_evidence.verification_command = None
        valid_evidence.validators = [
            {
                "id": "focused-tests",
                "kind": "command",
                "argv": ["python", "-m", "pytest", "tests/", "-q"],
            }
        ]
        valid_evidence.has_verification = True

        report = judge_plan(valid_evidence)

        assert valid_evidence.validators[0]["id"] == "focused-tests"
        assert report.decision == JudgeDecision.approve
        assert "typed validator" in report.verification_reality.lower()

    def test_approve_report_has_empty_required_changes(self, valid_evidence):
        """APPROVE report has empty required_changes."""
        report = judge_plan(valid_evidence)
        assert report.decision == JudgeDecision.approve
        assert report.required_changes == []

    def test_block_report_has_non_empty_required_changes(self, valid_evidence):
        """BLOCK reports have non-empty required_changes."""
        valid_evidence.target_files = []
        report = judge_plan(valid_evidence)
        assert report.decision == JudgeDecision.block
        assert len(report.required_changes) > 0

    def test_revise_report_has_non_empty_required_changes(self, valid_evidence):
        """REVISE reports have non-empty required_changes."""
        valid_evidence.has_verification = False
        report = judge_plan(valid_evidence)
        assert report.decision == JudgeDecision.revise
        assert len(report.required_changes) > 0

    def test_all_reports_have_assessment_strings(self, valid_evidence):
        """All reports have non-empty assessment strings."""
        # Test BLOCK
        valid_evidence.target_files = []
        report_block = judge_plan(valid_evidence)
        assert report_block.repo_grounding != ""
        assert report_block.task_boundaries != ""
        assert report_block.verification_reality != ""
        assert report_block.overbuild_risk != ""
        assert report_block.simpler_path != ""
        assert report_block.next_safe_action != ""

        # Test REVISE
        valid_evidence.target_files = ["file.py"]
        valid_evidence.files_exist = False
        report_revise = judge_plan(valid_evidence)
        assert report_revise.repo_grounding != ""
        assert report_revise.task_boundaries != ""
        assert report_revise.verification_reality != ""
        assert report_revise.overbuild_risk != ""
        assert report_revise.simpler_path != ""
        assert report_revise.next_safe_action != ""

        # Test APPROVE
        valid_evidence.files_exist = True
        valid_evidence.has_verification = True
        report_approve = judge_plan(valid_evidence)
        assert report_approve.repo_grounding != ""
        assert report_approve.task_boundaries != ""
        assert report_approve.verification_reality != ""
        assert report_approve.overbuild_risk != ""
        assert report_approve.simpler_path != ""
        assert report_approve.next_safe_action != ""

    def test_escalate_report_has_required_changes(self, valid_evidence):
        """ESCALATE_TO_USER report has required changes."""
        valid_evidence.constraints = ["escalate to user"]
        valid_evidence.files_exist = True
        valid_evidence.has_verification = True
        report = judge_plan(valid_evidence)
        assert report.decision == JudgeDecision.escalate_to_user
        assert len(report.required_changes) > 0


class TestRunPlanningJudge:
    """Test run_planning_judge function with filesystem operations."""

    def test_advances_to_assignment_on_approve(self, valid_evidence, run_root):
        """run_planning_judge advances to assignment on APPROVE."""
        root, run_id = run_root
        state = new_loop_state(run_id)
        state = state.model_copy(update={"stage": LoopStage.planning_judge})

        # Save initial state
        from devflow.loop.adapter import save_loop_state
        save_loop_state(root, state)

        # Run judge
        updated_state, report = run_planning_judge(root, run_id, valid_evidence)

        assert report.decision == JudgeDecision.approve
        assert updated_state.stage == LoopStage.assignment

    def test_transitions_to_blocked_on_block(self, run_root):
        """run_planning_judge transitions to blocked on BLOCK."""
        root, run_id = run_root
        from devflow.loop.adapter import save_loop_state
        state = new_loop_state(run_id)
        state = state.model_copy(update={"stage": LoopStage.planning_judge})
        save_loop_state(root, state)

        evidence = PlanningEvidence(
            run_id=run_id,
            plan_path="plan.md",
            spec_path="spec.md",
            target_files=[],  # Empty target files
            files_exist=True,
            has_verification=True,
        )

        updated_state, report = run_planning_judge(root, run_id, evidence)

        assert report.decision == JudgeDecision.block
        assert updated_state.stage == LoopStage.blocked

    def test_stays_at_planning_judge_on_revise(self, valid_evidence, run_root):
        """run_planning_judge stays at planning_judge on REVISE."""
        root, run_id = run_root
        from devflow.loop.adapter import save_loop_state
        state = new_loop_state(run_id)
        state = state.model_copy(update={"stage": LoopStage.planning_judge})
        save_loop_state(root, state)

        valid_evidence.has_verification = False
        updated_state, report = run_planning_judge(root, run_id, valid_evidence)

        assert report.decision == JudgeDecision.revise
        assert updated_state.stage == LoopStage.planning_judge

    def test_writes_planning_judge_json(self, valid_evidence, run_root):
        """run_planning_judge writes planning-judge.json to run dir."""
        root, run_id = run_root
        from devflow.loop.adapter import save_loop_state
        state = new_loop_state(run_id)
        state = state.model_copy(update={"stage": LoopStage.planning_judge})
        save_loop_state(root, state)

        run_planning_judge(root, run_id, valid_evidence)

        # Check that planning-judge.json was written
        judge_file = Path(root) / ".devflow" / "pipeline-runs" / run_id / "planning-judge.json"
        assert judge_file.exists()

        # Check it's valid JSON
        content = judge_file.read_text()
        data = json.loads(content)
        assert "decision" in data
        assert "run_id" in data

    def test_escalate_sets_next_human_decision(self, valid_evidence, run_root):
        """run_planning_judge sets next_human_decision on ESCALATE_TO_USER."""
        root, run_id = run_root
        from devflow.loop.adapter import save_loop_state
        state = new_loop_state(run_id)
        state = state.model_copy(update={"stage": LoopStage.planning_judge})
        save_loop_state(root, state)

        valid_evidence.constraints = ["escalate to user"]
        updated_state, report = run_planning_judge(root, run_id, valid_evidence)

        assert report.decision == JudgeDecision.escalate_to_user
        assert updated_state.stage == LoopStage.blocked
        assert updated_state.next_human_decision is not None
        assert len(updated_state.next_human_decision) > 0


class TestJudgePlanEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_constraints_list(self, valid_evidence):
        """Empty constraints list doesn't trigger escalation."""
        valid_evidence.constraints = []
        valid_evidence.files_exist = True
        valid_evidence.has_verification = True
        report = judge_plan(valid_evidence)
        assert report.decision == JudgeDecision.approve

    def test_constraints_without_escalate_keywords(self, valid_evidence):
        """Constraints without escalate/user_decision keywords don't trigger escalation."""
        valid_evidence.constraints = ["must pass tests", "no breaking changes"]
        valid_evidence.files_exist = True
        valid_evidence.has_verification = True
        report = judge_plan(valid_evidence)
        assert report.decision == JudgeDecision.approve

    def test_exactly_eight_target_files(self, valid_evidence):
        """Exactly 8 target files should be approved."""
        valid_evidence.target_files = [f"file_{i}.py" for i in range(8)]
        report = judge_plan(valid_evidence)
        assert report.decision == JudgeDecision.approve

    def test_nine_target_files_triggers_revise(self, valid_evidence):
        """9 target files should trigger REVISE."""
        valid_evidence.target_files = [f"file_{i}.py" for i in range(9)]
        report = judge_plan(valid_evidence)
        assert report.decision == JudgeDecision.revise

    def test_block_priority_over_revise(self, valid_evidence):
        """BLOCK conditions take priority over REVISE conditions."""
        # Set up with both BLOCK and REVISE conditions
        valid_evidence.target_files = []
        valid_evidence.files_exist = False
        valid_evidence.has_verification = False
        report = judge_plan(valid_evidence)
        assert report.decision == JudgeDecision.block

    def test_escalate_priority_over_revise(self, valid_evidence):
        """ESCALATE_TO_USER takes priority over REVISE conditions."""
        # ESCALATE conditions
        valid_evidence.constraints = ["escalate to user"]
        valid_evidence.files_exist = True
        valid_evidence.has_verification = True
        # REVISE conditions (but ESCALATE should win)
        valid_evidence.target_files = [f"file_{i}.py" for i in range(9)]
        report = judge_plan(valid_evidence)
        assert report.decision == JudgeDecision.escalate_to_user
