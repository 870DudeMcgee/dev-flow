"""Behavior tests for the Obsidian projection extractor (M1-S1)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from devflow.loop.models import LoopStage
from devflow.loop.pipeline_run import create_pipeline_run
from devflow.loop.workflow_ledger import (
    DECISION_RECEIPTS_DIR,
    DecisionReceipt,
    DecisionType,
    EvidenceReference,
    NodeReceipt,
    WorkflowEvent,
    initialize_workflow_run,
    record_node_outcome,
)
from devflow.obsidian.projection import (
    PHASE_NAMES,
    RunHealth,
    extract_projection,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SUCCESS_CHAIN: tuple[tuple[str, str], ...] = (
    ("idea", "idea-brief"),
    ("definition", "orientation-receipt"),
    ("spec", "spec"),
    ("planning", "execution-plan"),
    ("planning_judge", "planning-judge-report"),
    ("assignment", "approved-execution-plan"),
    ("build_judge", "build-judge-report"),
    ("verification", "verification-receipt"),
    ("human_decision", "human-decision"),
)


def _record_success(root: Path, run_id: str, node_id: str, evidence_key: str, idx: int) -> None:
    evidence_file = f"{evidence_key}.md"
    run_dir = root / ".devflow" / "pipeline-runs" / run_id
    if not (run_dir / evidence_file).exists():
        (run_dir / evidence_file).write_text(f"# {evidence_key}\n", encoding="utf-8")
    receipt = NodeReceipt(
        receipt_id=f"receipt-{idx}",
        node_id=node_id,
        outcome="success",
        evidence=(EvidenceReference(key=evidence_key, reference=evidence_file),),
    )
    event = WorkflowEvent(
        event_id=f"event-{idx}",
        node_id=node_id,
        outcome="success",
        receipt_id=f"receipt-{idx}",
    )
    record_node_outcome(root, run_id, receipt=receipt, event=event)


def _record_failure(root: Path, run_id: str, node_id: str, evidence_key: str, idx: int) -> None:
    evidence_file = f"{evidence_key}.md"
    run_dir = root / ".devflow" / "pipeline-runs" / run_id
    if not (run_dir / evidence_file).exists():
        (run_dir / evidence_file).write_text(f"# {evidence_key}\n", encoding="utf-8")
    receipt = NodeReceipt(
        receipt_id=f"receipt-{idx}",
        node_id=node_id,
        outcome="failure",
        evidence=(EvidenceReference(key=evidence_key, reference=evidence_file),),
    )
    event = WorkflowEvent(
        event_id=f"event-{idx}",
        node_id=node_id,
        outcome="failure",
        receipt_id=f"receipt-{idx}",
    )
    record_node_outcome(root, run_id, receipt=receipt, event=event)


def _advance_to(root: Path, run_id: str, through_node: str) -> None:
    for idx, (node_id, evidence_id) in enumerate(_SUCCESS_CHAIN, start=1):
        _record_success(root, run_id, node_id, evidence_id, idx)
        if node_id == through_node:
            break


def _write_decision_receipt(
    run_dir: Path,
    decision_id: str,
    decision_type: DecisionType = DecisionType.accept,
) -> DecisionReceipt:
    """Write a decision receipt directly to the run dir (bypasses record_decision
    which requires a full Phase 3-5 integration chain)."""
    receipts_dir = run_dir / DECISION_RECEIPTS_DIR
    receipts_dir.mkdir(exist_ok=True)
    receipt = DecisionReceipt(
        decision_id=decision_id,
        run_id=run_dir.name,
        integration_id="integration-test-1",
        integration_head="a" * 40,
        integration_tree="b" * 40,
        integration_fingerprint="c" * 64,
        verification_receipt_id="verification-receipt-1",
        verification_receipt_hash="d" * 64,
        actor="test-operator",
        decision_type=decision_type,
        promotion_eligible=(decision_type == DecisionType.accept),
        created_at=datetime(2026, 7, 15, 12, 0, 0, tzinfo=timezone.utc),
    )
    path = receipts_dir / f"{decision_id}.json"
    path.write_text(
        json.dumps(receipt.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_extract_fresh_run(tmp_path: Path) -> None:
    """Fresh canonical run: idea stage, health=Running, progress=0."""
    run_id = create_pipeline_run(tmp_path, {"repo": "test/repo"})
    initialize_workflow_run(tmp_path, run_id)

    state = extract_projection(tmp_path, run_id)

    assert state.run_id == run_id
    assert state.workflow_id == "canonical_product_build@1"
    assert state.health == RunHealth.running
    assert state.stage == LoopStage.idea
    assert state.current_phase == "Idea & Brainstorm"
    assert state.progress == pytest.approx(0.0)
    assert state.progress_percent == 0
    assert state.completed_node_ids == ()
    assert state.current_node_id == "idea"
    assert state.extraction_note is None
    assert state.result_branch is None


def test_extract_after_spec(tmp_path: Path) -> None:
    """3 nodes done → progress 33%, phase=Planning."""
    run_id = create_pipeline_run(tmp_path, {"repo": "test/repo"})
    initialize_workflow_run(tmp_path, run_id)
    _advance_to(tmp_path, run_id, "spec")

    state = extract_projection(tmp_path, run_id)

    assert state.progress_percent == 33
    assert state.completed_node_ids == ("idea", "definition", "spec")
    assert state.current_node_id == "planning"
    assert state.current_phase == "Planning"
    assert state.health == RunHealth.running


def test_extract_awaiting_decision(tmp_path: Path) -> None:
    """human_decision stage → Awaiting Decision.

    Advance through verification (8 nodes) so current_node is human_decision.
    """
    run_id = create_pipeline_run(tmp_path, {"repo": "test/repo"})
    initialize_workflow_run(tmp_path, run_id)
    _advance_to(tmp_path, run_id, "verification")

    state = extract_projection(tmp_path, run_id)

    assert state.stage == LoopStage.human_decision
    assert state.health == RunHealth.awaiting_decision
    assert state.current_phase == "Human Decision"
    assert state.current_node_id == "human_decision"


def test_extract_blocked(tmp_path: Path) -> None:
    """blocked stage → Blocked."""
    run_id = create_pipeline_run(tmp_path, {"repo": "test/repo"})
    initialize_workflow_run(tmp_path, run_id)
    _record_failure(tmp_path, run_id, "idea", "idea-brief", 1)

    state = extract_projection(tmp_path, run_id)

    assert state.stage == LoopStage.blocked
    assert state.health == RunHealth.blocked
    assert state.current_phase == "Blocked"
    assert state.blocker_count == 1
    assert state.current_node_id is None  # terminal


def test_extract_complete_with_accept(tmp_path: Path) -> None:
    """complete stage + accept decision → Completed."""
    run_id = create_pipeline_run(tmp_path, {"repo": "test/repo"})
    initialize_workflow_run(tmp_path, run_id)
    _advance_to(tmp_path, run_id, "human_decision")

    run_dir = tmp_path / ".devflow" / "pipeline-runs" / run_id
    _write_decision_receipt(run_dir, "decision-1", DecisionType.accept)

    state = extract_projection(tmp_path, run_id)

    assert state.health == RunHealth.completed
    assert state.decision_count == 1
    assert state.open_decisions[0].decision_type == "accept"
    assert state.open_decisions[0].promotion_eligible is True
    assert state.handoff_count == 1


def test_extract_complete_with_reject(tmp_path: Path) -> None:
    """complete stage + reject → Blocked (needs rework)."""
    run_id = create_pipeline_run(tmp_path, {"repo": "test/repo"})
    initialize_workflow_run(tmp_path, run_id)
    _advance_to(tmp_path, run_id, "human_decision")

    run_dir = tmp_path / ".devflow" / "pipeline-runs" / run_id
    _write_decision_receipt(run_dir, "decision-1", DecisionType.reject)

    state = extract_projection(tmp_path, run_id)

    # snapshot stage is complete, reject → blocked health
    assert state.health == RunHealth.blocked
    assert state.blocker_count == 1


def test_extract_derives_decision_count(tmp_path: Path) -> None:
    """Multiple decision receipts → count matches."""
    run_id = create_pipeline_run(tmp_path, {"repo": "test/repo"})
    initialize_workflow_run(tmp_path, run_id)
    _advance_to(tmp_path, run_id, "human_decision")

    run_dir = tmp_path / ".devflow" / "pipeline-runs" / run_id
    _write_decision_receipt(run_dir, "decision-1", DecisionType.accept)
    _write_decision_receipt(run_dir, "decision-2", DecisionType.request_changes)

    state = extract_projection(tmp_path, run_id)

    assert state.decision_count == 2
    assert len(state.open_decisions) == 2


def test_extract_noncanonical_run_returns_note(tmp_path: Path) -> None:
    """Noncanonical run (no workflow-definition.json) → extraction_note."""
    run_id = create_pipeline_run(tmp_path, {"repo": "test/repo"})
    # Note: initialize_workflow_run NOT called

    state = extract_projection(tmp_path, run_id)

    assert state.extraction_note == "not_canonical"
    assert state.health == RunHealth.healthy
    assert state.workflow_id == "unknown"


def test_extract_no_canonical_state_mutation(tmp_path: Path) -> None:
    """Run dir files unchanged after extract."""
    run_id = create_pipeline_run(tmp_path, {"repo": "test/repo"})
    initialize_workflow_run(tmp_path, run_id)
    _advance_to(tmp_path, run_id, "spec")

    run_dir = tmp_path / ".devflow" / "pipeline-runs" / run_id
    snapshot_before = {}
    for f in sorted(run_dir.iterdir()):
        if f.is_file():
            snapshot_before[f.name] = f.read_bytes()

    state = extract_projection(tmp_path, run_id)

    # Verify no files were modified
    for name, content_before in snapshot_before.items():
        content_after = (run_dir / name).read_bytes()
        assert content_after == content_before, f"File {name} was modified"

    # Check no new files were added (except by extract itself — there should be none)
    files_after = {f.name for f in run_dir.iterdir() if f.is_file()}
    assert files_after == set(snapshot_before.keys())


def test_extract_fail_closed_on_missing_ledger(tmp_path: Path) -> None:
    """Corrupt/missing ledger → clear error, not silent garbage."""
    run_id = create_pipeline_run(tmp_path, {"repo": "test/repo"})
    initialize_workflow_run(tmp_path, run_id)

    run_dir = tmp_path / ".devflow" / "pipeline-runs" / run_id
    # Corrupt the workflow-definition.json to make replay fail.
    # The file is immutable (0o444), so we need to chmod first.
    def_path = run_dir / "workflow-definition.json"
    def_path.chmod(0o644)
    def_path.write_text("INVALID JSON", encoding="utf-8")

    with pytest.raises(Exception):
        extract_projection(tmp_path, run_id)


def test_phase_names_cover_all_stages() -> None:
    """Every LoopStage has a human-readable phase name."""
    for stage in LoopStage:
        assert stage in PHASE_NAMES, f"Missing phase name for {stage}"


def test_projection_state_is_frozen(tmp_path: Path) -> None:
    """ProjectionState is immutable."""
    run_id = create_pipeline_run(tmp_path, {"repo": "test/repo"})
    initialize_workflow_run(tmp_path, run_id)
    state = extract_projection(tmp_path, run_id)

    with pytest.raises(Exception):
        state.health = RunHealth.blocked  # type: ignore[misc]
