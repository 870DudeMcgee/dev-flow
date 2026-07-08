"""Tests for devflow.loop.models — canonical loop state model."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from devflow.loop.models import (
    LoopStage,
    DevFlowLoopState,
    advance_stage,
    is_terminal,
    new_loop_state,
)


# ---------------------------------------------------------------------------
# new_loop_state
# ---------------------------------------------------------------------------
class TestNewLoopState:
    def test_factory_at_idea_stage(self) -> None:
        state = new_loop_state("run-001")
        assert state.run_id == "run-001"
        assert state.stage == LoopStage.idea

    def test_timestamps_are_iso_strings(self) -> None:
        state = new_loop_state("run-002")
        assert isinstance(state.created_at, str)
        assert isinstance(state.updated_at, str)
        # Basic ISO format check: contains T and timezone offset
        assert "T" in state.created_at
        assert state.created_at == state.updated_at

    def test_empty_lists_are_defaults(self) -> None:
        state = new_loop_state("run-003")
        assert state.assignments == []
        assert state.builder_judge_runs == []
        assert state.verification_receipts == []
        assert state.idea_brief_path is None
        assert state.spec_path is None
        assert state.plan_path is None
        assert state.planning_judge_path is None
        assert state.next_human_decision is None


# ---------------------------------------------------------------------------
# advance_stage — valid forward transitions
# ---------------------------------------------------------------------------
class TestAdvanceStageValid:
    def test_idea_to_definition(self) -> None:
        state = new_loop_state("r1")
        updated = advance_stage(state, LoopStage.definition)
        assert updated.stage == LoopStage.definition
        assert updated.updated_at != state.updated_at
        assert updated.run_id == state.run_id

    def test_full_forward_chain(self) -> None:
        state = new_loop_state("r2")
        chain = [
            LoopStage.idea,
            LoopStage.definition,
            LoopStage.spec,
            LoopStage.planning,
            LoopStage.planning_judge,
            LoopStage.assignment,
            LoopStage.build_judge,
            LoopStage.verification,
            LoopStage.human_decision,
            LoopStage.complete,
        ]
        for next_stage in chain[1:]:
            state = advance_stage(state, next_stage)
            assert state.stage == next_stage

    def test_state_is_immutable_after_advance(self) -> None:
        state = new_loop_state("r3")
        # Go idea -> definition -> spec (valid forward chain)
        state = advance_stage(state, LoopStage.definition)
        updated = advance_stage(state, LoopStage.spec)
        # Original unchanged
        assert state.stage == LoopStage.definition
        # Updated is new
        assert updated.stage == LoopStage.spec
        # All fields preserved
        assert updated.run_id == state.run_id
        assert updated.created_at == state.created_at


# ---------------------------------------------------------------------------
# advance_stage — invalid transitions
# ---------------------------------------------------------------------------
class TestAdvanceStageInvalid:
    def test_backward_transition_raises(self) -> None:
        state = new_loop_state("r4")
        # Go idea -> definition -> spec
        state = advance_stage(state, LoopStage.definition)
        state = advance_stage(state, LoopStage.spec)
        with pytest.raises(ValueError, match="Invalid transition"):
            advance_stage(state, LoopStage.definition)

    def test_skip_stage_raises(self) -> None:
        state = new_loop_state("r5")
        with pytest.raises(ValueError):
            advance_stage(state, LoopStage.planning)  # skip definition, spec

    def test_complete_is_terminal(self) -> None:
        # Full forward chain to complete: idea -> definition -> spec ->
        # planning -> planning_judge -> assignment -> build_judge ->
        # verification -> human_decision -> complete
        state = new_loop_state("r6")
        state = advance_stage(state, LoopStage.definition)
        state = advance_stage(state, LoopStage.spec)
        state = advance_stage(state, LoopStage.planning)
        state = advance_stage(state, LoopStage.planning_judge)
        state = advance_stage(state, LoopStage.assignment)
        state = advance_stage(state, LoopStage.build_judge)
        state = advance_stage(state, LoopStage.verification)
        state = advance_stage(state, LoopStage.human_decision)
        state = advance_stage(state, LoopStage.complete)
        with pytest.raises(ValueError, match="terminal"):
            advance_stage(state, LoopStage.assignment)

    def test_invalid_stage_name_in_message(self) -> None:
        # complete is unreachable from idea; verify error message mentions allowed stages
        state = new_loop_state("r7")
        with pytest.raises(ValueError, match="Allowed next stages"):
            advance_stage(state, LoopStage.complete)


# ---------------------------------------------------------------------------
# Blocked transitions
# ---------------------------------------------------------------------------
class TestBlockedTransitions:
    def test_blocked_from_any_stage(self) -> None:
        # Go idea -> definition -> spec first
        state = new_loop_state("r8")
        state = advance_stage(state, LoopStage.definition)
        state = advance_stage(state, LoopStage.spec)
        blocked = advance_stage(state, LoopStage.blocked)
        assert blocked.stage == LoopStage.blocked

    def test_blocked_from_idea(self) -> None:
        state = new_loop_state("r9")
        blocked = advance_stage(state, LoopStage.blocked)
        assert blocked.stage == LoopStage.blocked

    def test_blocked_can_return_to_non_terminal(self) -> None:
        state = new_loop_state("r10")
        state = advance_stage(state, LoopStage.blocked)
        # Should be able to go back to any non-terminal stage (but not complete)
        non_terminal_stages = [
            s for s in LoopStage if s != LoopStage.blocked and s != LoopStage.complete
        ]
        for stage in non_terminal_stages:
            new_s = advance_stage(state, stage)
            assert new_s.stage == stage

    def test_blocked_cannot_go_to_complete_directly(self) -> None:
        state = new_loop_state("r11")
        state = advance_stage(state, LoopStage.blocked)
        with pytest.raises(ValueError):
            advance_stage(state, LoopStage.complete)


# ---------------------------------------------------------------------------
# is_terminal
# ---------------------------------------------------------------------------
class TestIsTerminal:
    def test_complete_is_terminal(self) -> None:
        # Full chain to complete
        state = new_loop_state("r12")
        state = advance_stage(state, LoopStage.definition)
        state = advance_stage(state, LoopStage.spec)
        state = advance_stage(state, LoopStage.planning)
        state = advance_stage(state, LoopStage.planning_judge)
        state = advance_stage(state, LoopStage.assignment)
        state = advance_stage(state, LoopStage.build_judge)
        state = advance_stage(state, LoopStage.verification)
        state = advance_stage(state, LoopStage.human_decision)
        state = advance_stage(state, LoopStage.complete)
        assert is_terminal(state) is True

    def test_blocked_is_terminal(self) -> None:
        state = new_loop_state("r13")
        state = advance_stage(state, LoopStage.blocked)
        assert is_terminal(state) is True

    def test_idea_is_not_terminal(self) -> None:
        state = new_loop_state("r14")
        assert is_terminal(state) is False

    def test_mid_loop_is_not_terminal(self) -> None:
        state = new_loop_state("r15")
        # idea -> definition -> spec (valid forward)
        state = advance_stage(state, LoopStage.definition)
        state = advance_stage(state, LoopStage.spec)
        assert is_terminal(state) is False
        state = advance_stage(state, LoopStage.planning)
        assert is_terminal(state) is False

    def test_all_non_terminal_stages(self) -> None:
        non_terminal = [
            LoopStage.idea,
            LoopStage.definition,
            LoopStage.spec,
            LoopStage.planning,
            LoopStage.planning_judge,
            LoopStage.assignment,
            LoopStage.build_judge,
            LoopStage.verification,
            LoopStage.human_decision,
        ]
        for stage in non_terminal:
            state = new_loop_state("r16")
            if stage == LoopStage.idea:
                # Already at idea
                pass
            elif stage == LoopStage.definition:
                # Already there after new_loop_state (which starts at idea)
                state = advance_stage(state, LoopStage.definition)
            else:
                # Need to go idea -> definition -> spec -> ... -> target stage
                # Go through full chain to this stage
                stage_list = [
                    LoopStage.idea,
                    LoopStage.definition,
                    LoopStage.spec,
                    LoopStage.planning,
                    LoopStage.planning_judge,
                    LoopStage.assignment,
                    LoopStage.build_judge,
                    LoopStage.verification,
                    LoopStage.human_decision,
                ]
                idx = stage_list.index(stage)
                for s in stage_list[1:idx+1]:
                    state = advance_stage(state, s)
            assert is_terminal(state) is False, f"{stage.value} should not be terminal"


# ---------------------------------------------------------------------------
# Serialization round-trip
# ---------------------------------------------------------------------------
class TestSerialization:
    def test_model_dump_returns_dict(self) -> None:
        state = new_loop_state("r17")
        data = state.model_dump()
        assert isinstance(data, dict)
        assert data["run_id"] == "r17"
        assert data["stage"] == "idea"

    def test_round_trip_dump_validate(self) -> None:
        original = new_loop_state("r18")
        data = original.model_dump()
        restored = DevFlowLoopState.model_validate(data)
        assert restored.run_id == original.run_id
        assert restored.stage == original.stage
        assert restored.created_at == original.created_at
        assert restored.assignments == []

    def test_round_trip_with_optional_fields(self) -> None:
        now = datetime.now(timezone.utc).isoformat()
        state = DevFlowLoopState(
            run_id="r19",
            stage=LoopStage.spec,
            created_at=now,
            updated_at=now,
            idea_brief_path="/tmp/brief.md",
            spec_path="/tmp/spec.md",
            assignments=["task-1", "task-2"],
        )
        data = state.model_dump()
        restored = DevFlowLoopState.model_validate(data)
        assert restored.run_id == "r19"
        assert restored.stage == LoopStage.spec
        assert restored.idea_brief_path == "/tmp/brief.md"
        assert restored.spec_path == "/tmp/spec.md"
        assert restored.assignments == ["task-1", "task-2"]

    def test_json_round_trip(self) -> None:
        state = new_loop_state("r20")
        # Go idea -> definition -> spec (valid forward)
        state = advance_stage(state, LoopStage.definition)
        state = advance_stage(state, LoopStage.spec)
        json_str = state.model_dump_json()
        restored = DevFlowLoopState.model_validate_json(json_str)
        assert restored.run_id == "r20"
        assert restored.stage == LoopStage.spec

    def test_serialization_preserves_updated_at(self) -> None:
        state = new_loop_state("r21")
        original_updated = state.updated_at
        state = advance_stage(state, LoopStage.definition)
        assert state.updated_at != original_updated
        # Round trip preserves the new timestamp
        data = state.model_dump()
        restored = DevFlowLoopState.model_validate(data)
        assert restored.updated_at == state.updated_at
