"""Tests for verification adapter."""

from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime, timezone

import pytest

from devflow.legacy.control_room.pipeline_run import create_pipeline_run, update_pipeline_run_record
from devflow.loop.models import DevFlowLoopState, LoopStage, new_loop_state
from devflow.loop.verification import (
    VerificationStatus,
    VerificationReceipt,
    record_verification_receipt,
    verification_ready_for_human,
)


@pytest.fixture
def tmp_run(tmp_path: Path) -> tuple[Path, str]:
    """Create a temporary pipeline run."""
    run_id = create_pipeline_run(tmp_path, {"test": "data"})
    return tmp_path, run_id


@pytest.fixture
def setup_verification_state(
    tmp_run: tuple[Path, str],
) -> tuple[Path, str, DevFlowLoopState]:
    """Setup a pipeline run with verification stage state."""
    root, run_id = tmp_run
    state = new_loop_state(run_id)
    state = state.model_copy(update={"stage": LoopStage.verification})
    # Save state to the pipeline run directory
    state_json = state.model_dump_json(indent=2, ensure_ascii=False)
    update_pipeline_run_record(root, run_id, "loop-state.json", state_json)
    return root, run_id, state


@pytest.fixture
def setup_human_decision_state(
    tmp_run: tuple[Path, str],
) -> tuple[Path, str, DevFlowLoopState]:
    """Setup a pipeline run with human_decision stage state."""
    root, run_id = tmp_run
    state = new_loop_state(run_id)
    state = state.model_copy(update={"stage": LoopStage.human_decision})
    # Save state to the pipeline run directory
    state_json = state.model_dump_json(indent=2, ensure_ascii=False)
    update_pipeline_run_record(root, run_id, "loop-state.json", state_json)
    return root, run_id, state


def make_receipt(
    run_id: str,
    receipt_id: str = "r-001",
    status: VerificationStatus = VerificationStatus.passed,
    summary: str = "Verification passed",
    command: str | None = None,
    exit_code: int | None = None,
    evidence_path: str | None = None,
) -> VerificationReceipt:
    """Helper to create a basic receipt with optional extras."""
    return VerificationReceipt(
        run_id=run_id,
        receipt_id=receipt_id,
        status=status,
        summary=summary,
        command=command,
        exit_code=exit_code,
        evidence_path=evidence_path,
        created_at=datetime.now(timezone.utc).isoformat(),
    )


class TestVerificationStatus:
    """Test VerificationStatus enum."""

    def test_all_statuses_exist(self) -> None:
        """Test that all four statuses exist."""
        assert VerificationStatus.passed.value == "passed"
        assert VerificationStatus.failed.value == "failed"
        assert VerificationStatus.blocked.value == "blocked"
        assert VerificationStatus.needs_review.value == "needs_review"

    def test_enum_count(self) -> None:
        """Test that enum has exactly four values."""
        assert len(VerificationStatus) == 4


class TestVerificationReceipt:
    """Test VerificationReceipt model."""

    def test_serialization(self, tmp_run: tuple[Path, str]) -> None:
        """Test serialization and deserialization."""
        _, run_id = tmp_run
        receipt = make_receipt(run_id, status=VerificationStatus.passed)

        # Serialize
        json_str = receipt.model_dump_json()
        assert isinstance(json_str, str)
        assert "passed" in json_str
        assert run_id in json_str

        # Deserialize
        deserialized = VerificationReceipt.model_validate_json(json_str)
        assert deserialized.run_id == receipt.run_id
        assert deserialized.status == receipt.status
        assert deserialized.summary == receipt.summary

    def test_optional_fields(self, tmp_run: tuple[Path, str]) -> None:
        """Test that optional fields work."""
        _, run_id = tmp_run
        receipt = make_receipt(run_id, command="pytest tests/", exit_code=0)
        assert receipt.command == "pytest tests/"
        assert receipt.exit_code == 0
        assert receipt.evidence_path is None

    def test_validation(self, tmp_run: tuple[Path, str]) -> None:
        """Test model validation."""
        _, run_id = tmp_run
        # Valid
        receipt = make_receipt(run_id)
        assert receipt.status == VerificationStatus.passed

        # Invalid status should raise
        with pytest.raises(Exception):
            VerificationReceipt(
                run_id=run_id,
                receipt_id="bad",
                status="invalid_status",  # type: ignore
                summary="test",
            )


class TestRecordVerificationReceipt:
    """Test record_verification_receipt function."""

    def test_advances_on_passed(
        self, setup_verification_state
    ) -> None:
        """Test that passing receipt advances to human_decision."""
        root, run_id, _ = setup_verification_state
        receipt = make_receipt(run_id, status=VerificationStatus.passed)

        new_state, recorded = record_verification_receipt(root, receipt)

        assert new_state.stage == LoopStage.human_decision
        assert recorded.status == VerificationStatus.passed

    def test_stays_on_failed(
        self, setup_verification_state
    ) -> None:
        """Test that failed receipt stays at verification."""
        root, run_id, _ = setup_verification_state
        receipt = make_receipt(run_id, status=VerificationStatus.failed)

        new_state, recorded = record_verification_receipt(root, receipt)

        assert new_state.stage == LoopStage.verification
        assert recorded.status == VerificationStatus.failed
        assert new_state.next_human_decision is not None

    def test_stays_on_needs_review(
        self, setup_verification_state
    ) -> None:
        """Test that needs_review receipt stays at verification."""
        root, run_id, _ = setup_verification_state
        receipt = make_receipt(run_id, status=VerificationStatus.needs_review)

        new_state, recorded = record_verification_receipt(root, receipt)

        assert new_state.stage == LoopStage.verification
        assert recorded.status == VerificationStatus.needs_review
        assert new_state.next_human_decision is not None

    def test_transitions_on_blocked(
        self, setup_verification_state
    ) -> None:
        """Test that blocked receipt transitions to blocked stage."""
        root, run_id, _ = setup_verification_state
        receipt = make_receipt(
            run_id, status=VerificationStatus.blocked, summary="Critical error"
        )

        new_state, recorded = record_verification_receipt(root, receipt)

        assert new_state.stage == LoopStage.blocked
        assert recorded.status == VerificationStatus.blocked
        assert new_state.next_human_decision == "Critical error"

    def test_rejects_wrong_stage(self, tmp_run: tuple[Path, str]) -> None:
        """Test that recording fails at wrong stage."""
        root, run_id = tmp_run
        state = new_loop_state(run_id)
        state = state.model_copy(update={"stage": LoopStage.idea})
        state_json = state.model_dump_json(indent=2, ensure_ascii=False)
        update_pipeline_run_record(root, run_id, "loop-state.json", state_json)

        receipt = make_receipt(run_id)

        with pytest.raises(ValueError, match="Expected stage verification or human_decision"):
            record_verification_receipt(root, receipt)

    def test_adds_receipt_to_state(
        self, setup_verification_state
    ) -> None:
        """Test that receipt path is added to verification_receipts."""
        root, run_id, _ = setup_verification_state
        receipt = make_receipt(run_id, receipt_id="r-001")

        new_state, _ = record_verification_receipt(root, receipt)

        assert "verification-receipt-r-001.json" in new_state.verification_receipts

    def test_idempotent_receipts(
        self, setup_verification_state
    ) -> None:
        """Test that duplicate receipt doesn't add path twice."""
        root, run_id, _ = setup_verification_state
        receipt = make_receipt(run_id, receipt_id="r-001")

        record_verification_receipt(root, receipt)
        record_verification_receipt(root, receipt)

        # Reload state
        from devflow.loop.adapter import load_loop_state
        state = load_loop_state(root, run_id)

        # Should only appear once
        assert state.verification_receipts.count("verification-receipt-r-001.json") == 1

    def test_writes_receipt_file(
        self, setup_verification_state
    ) -> None:
        """Test that receipt JSON is written to pipeline run dir."""
        root, run_id, _ = setup_verification_state
        receipt = make_receipt(run_id, receipt_id="r-001")

        record_verification_receipt(root, receipt)

        # Check that the receipt file was written
        run_dir = root / ".devflow" / "pipeline-runs" / run_id
        receipt_file = run_dir / "verification-receipt-r-001.json"
        assert receipt_file.exists()

        # Verify JSON content
        receipt_data = json.loads(receipt_file.read_text())
        assert receipt_data["receipt_id"] == "r-001"
        assert receipt_data["status"] == "passed"

    def test_append_to_human_decision(
        self, setup_human_decision_state
    ) -> None:
        """Test that additional receipts can be appended at human_decision."""
        root, run_id, _ = setup_human_decision_state
        receipt = make_receipt(run_id, receipt_id="r-002")

        new_state, recorded = record_verification_receipt(root, receipt)

        # Should stay at human_decision
        assert new_state.stage == LoopStage.human_decision
        assert recorded.status == VerificationStatus.passed
        assert "verification-receipt-r-002.json" in new_state.verification_receipts


class TestVerificationReadyForHuman:
    """Test verification_ready_for_human function."""

    def test_returns_false_at_verification(self, setup_verification_state) -> None:
        """Test that it returns False when at verification stage."""
        root, run_id, state = setup_verification_state
        assert verification_ready_for_human(state) is False

    def test_returns_false_at_human_decision_no_receipts(
        self, setup_human_decision_state
    ) -> None:
        """Test that it returns False at human_decision with no receipts."""
        _, _, state = setup_human_decision_state
        assert verification_ready_for_human(state) is False

    def test_returns_true_at_human_decision_with_receipts(
        self, setup_human_decision_state
    ) -> None:
        """Test that it returns True at human_decision with receipts."""
        root, run_id, _ = setup_human_decision_state
        receipt = make_receipt(run_id, receipt_id="r-001")
        new_state, _ = record_verification_receipt(root, receipt)

        assert verification_ready_for_human(new_state) is True

    def test_returns_false_at_other_stages(self, tmp_run: tuple[Path, str]) -> None:
        """Test that it returns False at other stages."""
        _, run_id = tmp_run
        state = new_loop_state(run_id)
        state = state.model_copy(update={"stage": LoopStage.idea})

        assert verification_ready_for_human(state) is False
