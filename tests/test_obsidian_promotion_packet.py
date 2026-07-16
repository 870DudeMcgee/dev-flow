"""Tests for the promotion packet materialization (M1-S5)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from devflow.loop.pipeline_run import create_pipeline_run, update_pipeline_run_record
from devflow.loop.workflow_ledger import (
    DECISION_RECEIPTS_DIR,
    DecisionReceipt,
    DecisionType,
    initialize_workflow_run,
)
from devflow.obsidian.promotion_packet import (
    PROMOTION_PACKET_FILE,
    build_promotion_packet,
    emit_promotion_packet,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_decision_receipt(
    run_dir: Path,
    decision_id: str,
    decision_type: DecisionType = DecisionType.accept,
) -> DecisionReceipt:
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


def _write_verification_receipt(
    run_dir: Path,
    receipt_id: str,
    passed: bool = True,
) -> None:
    data = {
        "receipt_id": receipt_id,
        "passed": passed,
        "summary": "All tests passed." if passed else "2 tests failed.",
        "command": "pytest",
    }
    path = run_dir / f"verification-receipt-{receipt_id}.json"
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _write_reliability_report(run_dir: Path, safe: bool = True) -> None:
    data = {
        "run_id": run_dir.name,
        "safe": safe,
        "action": "admit" if safe else "block",
        "breaches": [] if safe else ["stale_verification"],
    }
    path = run_dir / "reliability-report.json"
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _build_run_with_accept(tmp_path: Path) -> tuple[Path, str, DecisionReceipt]:
    repo = tmp_path / "repo"
    run_id = create_pipeline_run(repo, {"repo": "test/repo"})
    initialize_workflow_run(repo, run_id)

    run_dir = repo / ".devflow" / "pipeline-runs" / run_id

    # Write intent
    update_pipeline_run_record(repo, run_id, "intent.md", "# Objective\n\nAdd a new feature.\n")
    # Write spec
    update_pipeline_run_record(repo, run_id, "fixture-spec.md", "# Spec\n\nFeature spec.\n")
    # Write verification receipt
    _write_verification_receipt(run_dir, "verification-1", passed=True)
    # Write reliability report
    _write_reliability_report(run_dir, safe=True)
    # Write accept decision
    decision = _write_decision_receipt(run_dir, "decision-1", DecisionType.accept)

    return repo, run_id, decision


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_packet_declares_not_run_review(tmp_path: Path) -> None:
    """Independent review section says 'not yet produced'."""
    repo, run_id, _ = _build_run_with_accept(tmp_path)

    packet = build_promotion_packet(repo, run_id)

    assert packet is not None
    assert "Independent Review" in packet
    assert "Not yet produced" in packet
    assert "M4" in packet


def test_packet_includes_objective(tmp_path: Path) -> None:
    """Objective from intent.md appears."""
    repo, run_id, _ = _build_run_with_accept(tmp_path)

    packet = build_promotion_packet(repo, run_id)

    assert packet is not None
    assert "Add a new feature" in packet
    assert "Objective" in packet


def test_packet_includes_specification(tmp_path: Path) -> None:
    """Spec text appears when fixture-spec.md exists."""
    repo, run_id, _ = _build_run_with_accept(tmp_path)

    packet = build_promotion_packet(repo, run_id)

    assert packet is not None
    assert "Feature spec" in packet


def test_packet_includes_verification_summary(tmp_path: Path) -> None:
    """Verification receipt summary appears."""
    repo, run_id, _ = _build_run_with_accept(tmp_path)

    packet = build_promotion_packet(repo, run_id)

    assert packet is not None
    assert "verification-receipt-verification-1.json" in packet
    assert "passed" in packet
    assert "All tests passed" in packet


def test_packet_includes_reliability_summary(tmp_path: Path) -> None:
    """Reliability report summary appears."""
    repo, run_id, _ = _build_run_with_accept(tmp_path)

    packet = build_promotion_packet(repo, run_id)

    assert packet is not None
    assert "Reliability Assessment" in packet
    assert "safe" in packet


def test_packet_recommended_action_matches_decision(tmp_path: Path) -> None:
    """Accept decision → 'Approve'."""
    repo, run_id, _ = _build_run_with_accept(tmp_path)

    packet = build_promotion_packet(repo, run_id)

    assert packet is not None
    assert "Approve" in packet
    assert "Recommended Action" in packet


def test_packet_emitted_only_after_accept(tmp_path: Path) -> None:
    """No accept decision → None."""
    repo = tmp_path / "repo"
    run_id = create_pipeline_run(repo, {"repo": "test/repo"})
    initialize_workflow_run(repo, run_id)

    result = build_promotion_packet(repo, run_id)

    assert result is None


def test_packet_reject_decision_no_packet(tmp_path: Path) -> None:
    """Reject decision → no packet (only accept triggers)."""
    repo = tmp_path / "repo"
    run_id = create_pipeline_run(repo, {"repo": "test/repo"})
    initialize_workflow_run(repo, run_id)
    run_dir = repo / ".devflow" / "pipeline-runs" / run_id
    _write_decision_receipt(run_dir, "decision-1", DecisionType.reject)

    result = build_promotion_packet(repo, run_id)

    assert result is None


def test_packet_idempotent(tmp_path: Path) -> None:
    """Re-emit produces identical content."""
    repo, run_id, _ = _build_run_with_accept(tmp_path)

    path1 = emit_promotion_packet(repo, run_id)
    assert path1 is not None
    content1 = path1.read_text(encoding="utf-8")

    path2 = emit_promotion_packet(repo, run_id)
    assert path2 is not None
    content2 = path2.read_text(encoding="utf-8")

    assert path1 == path2
    assert content1 == content2


def test_packet_does_not_invent_missing_evidence(tmp_path: Path) -> None:
    """Missing verification → 'not available', not fabricated."""
    repo = tmp_path / "repo"
    run_id = create_pipeline_run(repo, {"repo": "test/repo"})
    initialize_workflow_run(repo, run_id)
    run_dir = repo / ".devflow" / "pipeline-runs" / run_id
    _write_decision_receipt(run_dir, "decision-1", DecisionType.accept)

    packet = build_promotion_packet(repo, run_id)

    assert packet is not None
    assert "Not available" in packet
    # Must not invent a verification result
    assert "All tests passed" not in packet


def test_packet_read_only(tmp_path: Path) -> None:
    """Canonical state unchanged after emit."""
    repo, run_id, _ = _build_run_with_accept(tmp_path)
    run_dir = repo / ".devflow" / "pipeline-runs" / run_id

    # Snapshot files before emit (excluding the target itself)
    snapshot_before = {}
    for f in sorted(run_dir.iterdir()):
        if f.is_file() and f.name != PROMOTION_PACKET_FILE:
            snapshot_before[f.name] = f.read_bytes()

    path = emit_promotion_packet(repo, run_id)

    assert path is not None
    # Verify no files modified (only new file added)
    for name, content_before in snapshot_before.items():
        content_after = (run_dir / name).read_bytes()
        assert content_after == content_before, f"File {name} was modified"


def test_packet_contains_decision_metadata(tmp_path: Path) -> None:
    """Decision metadata section has actor, type, timestamp."""
    repo, run_id, _ = _build_run_with_accept(tmp_path)

    packet = build_promotion_packet(repo, run_id)

    assert packet is not None
    assert "Decision Metadata" in packet
    assert "test-operator" in packet
    assert "decision-1" in packet


def test_packet_includes_open_risks_from_breaches(tmp_path: Path) -> None:
    """When reliability has breaches, they appear in Open Risks."""
    repo = tmp_path / "repo"
    run_id = create_pipeline_run(repo, {"repo": "test/repo"})
    initialize_workflow_run(repo, run_id)
    run_dir = repo / ".devflow" / "pipeline-runs" / run_id
    _write_decision_receipt(run_dir, "decision-1", DecisionType.accept)
    _write_reliability_report(run_dir, safe=False)

    packet = build_promotion_packet(repo, run_id)

    assert packet is not None
    assert "Open Risks" in packet
    assert "stale_verification" in packet


def test_emit_writes_to_run_dir(tmp_path: Path) -> None:
    """emit_promotion_packet writes promotion-packet.md in the run directory."""
    repo, run_id, _ = _build_run_with_accept(tmp_path)

    path = emit_promotion_packet(repo, run_id)

    assert path is not None
    assert path.name == PROMOTION_PACKET_FILE
    assert path.is_file()

    run_dir = repo / ".devflow" / "pipeline-runs" / run_id
    assert path.parent == run_dir
