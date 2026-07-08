"""Tests for human decision adapter."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from devflow.control_room.pipeline_run import create_pipeline_run, update_pipeline_run_record
from devflow.loop.models import LoopStage, new_loop_state
from devflow.loop.human_decision import (
    HumanDecision,
    HumanDecisionRecord,
    record_human_decision,
    decision_completes_loop,
)


@pytest.fixture
def tmp_run(tmp_path) -> tuple:
    """Create a temporary pipeline run."""
    run_id = create_pipeline_run(tmp_path, {"test": "data"})
    return tmp_path, run_id


def make_record(
    run_id: str,
    decision_id: str = "hd-001",
    decision: HumanDecision = HumanDecision.accept,
    summary: str = "Accepted the work",
    next_stage: LoopStage | None = None,
    notes: str | None = None,
) -> HumanDecisionRecord:
    """Helper to create a basic decision record."""
    return HumanDecisionRecord(
        run_id=run_id,
        decision_id=decision_id,
        decision=decision,
        summary=summary,
        notes=notes,
        next_stage=next_stage,
        created_at=datetime.now(timezone.utc).isoformat(),
    )


def setup_state(
    root,
    run_id,
    stage: LoopStage,
) -> tuple:
    """Setup a pipeline run with a given loop stage."""
    state = new_loop_state(run_id)
    state = state.model_copy(update={"stage": stage})
    state_json = state.model_dump_json(indent=2, ensure_ascii=False)
    update_pipeline_run_record(
        root, run_id, "loop-state.json", state_json
    )
    return root, run_id, state


# ---------------------------------------------------------------------------
# HumanDecision enum
# ---------------------------------------------------------------------------
class TestHumanDecision:
    def test_all_six_values_exist(self) -> None:
        assert HumanDecision.accept.value == "accept"
        assert HumanDecision.continue_work.value == "continue_work"
        assert HumanDecision.revise_plan.value == "revise_plan"
        assert HumanDecision.revise_spec.value == "revise_spec"
        assert HumanDecision.block.value == "block"
        assert HumanDecision.complete.value == "complete"

    def test_enum_count(self) -> None:
        assert len(HumanDecision) == 6


# ---------------------------------------------------------------------------
# HumanDecisionRecord
# ---------------------------------------------------------------------------
class TestHumanDecisionRecord:
    def test_serialization(self, tmp_run) -> None:
        _, run_id = tmp_run
        record = make_record(run_id, decision=HumanDecision.accept)

        json_str = record.model_dump_json()
        assert isinstance(json_str, str)
        assert "accept" in json_str

        deserialized = HumanDecisionRecord.model_validate_json(json_str)
        assert deserialized.decision == HumanDecision.accept
        assert deserialized.summary == "Accepted the work"

    def test_optional_fields(self, tmp_run) -> None:
        _, run_id = tmp_run
        record = make_record(
            run_id,
            notes="Operator notes here",
            next_stage=LoopStage.spec,
        )
        assert record.notes == "Operator notes here"
        assert record.next_stage == LoopStage.spec

    def test_validation_rejects_invalid_decision(self, tmp_run) -> None:
        _, run_id = tmp_run
        with pytest.raises(Exception):
            HumanDecisionRecord(
                run_id=run_id,
                decision_id="bad",
                decision="not_a_valid_decision",  # type: ignore
                summary="test",
            )


# ---------------------------------------------------------------------------
# record_human_decision — transitions
# ---------------------------------------------------------------------------
class TestRecordHumanDecision:
    def test_accept_transitions_to_complete(self, tmp_run) -> None:
        root, run_id, _ = setup_state(tmp_run[0], tmp_run[1], LoopStage.human_decision)
        record = make_record(run_id, decision=HumanDecision.accept)
        new_state, recorded = record_human_decision(root, record)

        assert new_state.stage == LoopStage.complete
        assert recorded.decision == HumanDecision.accept

    def test_complete_transitions_to_complete(self, tmp_run) -> None:
        root, run_id, _ = setup_state(tmp_run[0], tmp_run[1], LoopStage.human_decision)
        record = make_record(run_id, decision=HumanDecision.complete)
        new_state, recorded = record_human_decision(root, record)

        assert new_state.stage == LoopStage.complete
        assert recorded.decision == HumanDecision.complete

    def test_continue_work_transitions_to_assignment_by_default(self, tmp_run) -> None:
        root, run_id, _ = setup_state(tmp_run[0], tmp_run[1], LoopStage.human_decision)
        record = make_record(run_id, decision=HumanDecision.continue_work)
        new_state, recorded = record_human_decision(root, record)

        assert new_state.stage == LoopStage.assignment
        assert recorded.decision == HumanDecision.continue_work

    def test_continue_work_honors_allowed_next_stage(self, tmp_run) -> None:
        root, run_id, _ = setup_state(tmp_run[0], tmp_run[1], LoopStage.human_decision)
        record = make_record(
            run_id,
            decision=HumanDecision.continue_work,
            next_stage=LoopStage.build_judge,
        )
        new_state, _ = record_human_decision(root, record)

        assert new_state.stage == LoopStage.build_judge

    def test_continue_work_rejects_disallowed_next_stage(self, tmp_run) -> None:
        root, run_id, _ = setup_state(tmp_run[0], tmp_run[1], LoopStage.human_decision)
        record = make_record(
            run_id,
            decision=HumanDecision.continue_work,
            next_stage=LoopStage.idea,
        )

        with pytest.raises(ValueError, match="Invalid next_stage"):
            record_human_decision(root, record)

    def test_revise_plan_transitions_to_planning(self, tmp_run) -> None:
        root, run_id, _ = setup_state(tmp_run[0], tmp_run[1], LoopStage.human_decision)
        record = make_record(run_id, decision=HumanDecision.revise_plan)
        new_state, recorded = record_human_decision(root, record)

        assert new_state.stage == LoopStage.planning
        assert recorded.decision == HumanDecision.revise_plan

    def test_revise_spec_transitions_to_spec(self, tmp_run) -> None:
        root, run_id, _ = setup_state(tmp_run[0], tmp_run[1], LoopStage.human_decision)
        record = make_record(run_id, decision=HumanDecision.revise_spec)
        new_state, recorded = record_human_decision(root, record)

        assert new_state.stage == LoopStage.spec
        assert recorded.decision == HumanDecision.revise_spec

    def test_block_transitions_to_blocked(self, tmp_run) -> None:
        root, run_id, _ = setup_state(tmp_run[0], tmp_run[1], LoopStage.verification)
        record = make_record(
            run_id, decision=HumanDecision.block, summary="Critical issue"
        )
        new_state, recorded = record_human_decision(root, record)

        assert new_state.stage == LoopStage.blocked
        assert recorded.decision == HumanDecision.block

    def test_rejects_wrong_stage(self, tmp_run) -> None:
        root, run_id, _ = setup_state(tmp_run[0], tmp_run[1], LoopStage.idea)
        record = make_record(run_id, decision=HumanDecision.accept)

        with pytest.raises(ValueError, match="Expected stage human_decision"):
            record_human_decision(root, record)

    def test_writes_human_decision_file(self, tmp_run) -> None:
        root, run_id, _ = setup_state(tmp_run[0], tmp_run[1], LoopStage.human_decision)
        record = make_record(run_id, decision_id="hd-001")

        record_human_decision(root, record)

        run_dir = root / ".devflow" / "pipeline-runs" / run_id
        decision_file = run_dir / "human-decision-hd-001.json"
        assert decision_file.exists()

        data = json.loads(decision_file.read_text())
        assert data["decision_id"] == "hd-001"
        assert data["decision"] == "accept"

    def test_next_human_decision_set_to_summary(self, tmp_run) -> None:
        root, run_id, _ = setup_state(tmp_run[0], tmp_run[1], LoopStage.human_decision)
        record = make_record(run_id, summary="Great work!")
        new_state, _ = record_human_decision(root, record)

        assert new_state.next_human_decision == "Great work!"


# ---------------------------------------------------------------------------
# decision_completes_loop
# ---------------------------------------------------------------------------
class TestDecisionCompletesLoop:
    def test_accept_completes(self, tmp_run) -> None:
        _, run_id = tmp_run
        record = make_record(run_id, decision=HumanDecision.accept)
        assert decision_completes_loop(record) is True

    def test_complete_completes(self, tmp_run) -> None:
        _, run_id = tmp_run
        record = make_record(run_id, decision=HumanDecision.complete)
        assert decision_completes_loop(record) is True

    def test_continue_work_does_not_complete(self, tmp_run) -> None:
        _, run_id = tmp_run
        record = make_record(run_id, decision=HumanDecision.continue_work)
        assert decision_completes_loop(record) is False

    def test_revise_plan_does_not_complete(self, tmp_run) -> None:
        _, run_id = tmp_run
        record = make_record(run_id, decision=HumanDecision.revise_plan)
        assert decision_completes_loop(record) is False

    def test_revise_spec_does_not_complete(self, tmp_run) -> None:
        _, run_id = tmp_run
        record = make_record(run_id, decision=HumanDecision.revise_spec)
        assert decision_completes_loop(record) is False

    def test_block_does_not_complete(self, tmp_run) -> None:
        _, run_id = tmp_run
        record = make_record(run_id, decision=HumanDecision.block)
        assert decision_completes_loop(record) is False
