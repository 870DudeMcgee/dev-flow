"""Tests for metrics aggregation + promotion packet integration (M5-S3)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from devflow.loop.metrics_aggregator import (
    WorkflowMetrics,
    aggregate_metrics,
    format_metrics_section,
)
from devflow.loop.independent_review import ReviewResult, record_review
from devflow.loop.pipeline_run import create_pipeline_run


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, sort_keys=True) + "\n")


def _make_accept_receipt(run_id: str = "run-1") -> object:
    """Create a minimally valid accept DecisionReceipt for tests."""
    from devflow.loop.workflow_ledger import DecisionReceipt, DecisionType
    from datetime import datetime, timezone

    return DecisionReceipt(
        decision_id="d1",
        run_id=run_id,
        integration_id="int-1",
        integration_head="a" * 40,
        integration_tree="b" * 40,
        integration_fingerprint="c" * 64,
        verification_receipt_id="vr-1",
        verification_receipt_hash="d" * 64,
        actor="operator",
        decision_type=DecisionType.accept,
        promotion_eligible=True,
        created_at=datetime.now(timezone.utc),
    )


def _write_accept_decision(tmp_path: Path, run_id: str) -> None:
    """Write an accept decision receipt to the run dir."""
    from devflow.loop.workflow_ledger import DECISION_RECEIPTS_DIR

    run_dir = tmp_path / ".devflow" / "pipeline-runs" / run_id
    receipts_dir = run_dir / DECISION_RECEIPTS_DIR
    receipts_dir.mkdir(parents=True, exist_ok=True)
    receipt = _make_accept_receipt(run_id)
    (receipts_dir / "d1.json").write_text(
        receipt.model_dump_json(indent=2), encoding="utf-8"  # type: ignore[union-attr]
    )


# ---------------------------------------------------------------------------
# aggregate_metrics tests
# ---------------------------------------------------------------------------

def test_aggregate_metrics_no_data(tmp_path: Path) -> None:
    """Missing files → zeros."""
    run_id = create_pipeline_run(tmp_path, {"repo": "test"})
    metrics = aggregate_metrics(tmp_path, run_id)

    assert metrics.run_id == run_id
    assert metrics.total_duration_seconds == 0.0
    assert metrics.total_tokens == 0
    assert metrics.repair_rounds == 0
    assert metrics.retry_count == 0
    assert metrics.human_interventions == 0
    assert metrics.reliability_safe is None
    assert metrics.reliability_breaches == ()


def test_aggregate_metrics_from_reliability(tmp_path: Path) -> None:
    """Reads reliability-report.json for safe/breaches/duration."""
    run_id = create_pipeline_run(tmp_path, {"repo": "test"})
    run_dir = tmp_path / ".devflow" / "pipeline-runs" / run_id
    (run_dir / "reliability-report.json").write_text(json.dumps({
        "safe": True,
        "action": "proceed",
        "breaches": [],
        "metrics": {
            "total_duration_seconds": 3600.0,
            "total_tokens": 15420,
        },
    }), encoding="utf-8")

    metrics = aggregate_metrics(tmp_path, run_id)

    assert metrics.reliability_safe is True
    assert metrics.total_duration_seconds == 3600.0
    assert metrics.total_tokens == 15420


def test_aggregate_metrics_repair_rounds(tmp_path: Path) -> None:
    """Counts repair events."""
    run_id = create_pipeline_run(tmp_path, {"repo": "test"})
    run_dir = tmp_path / ".devflow" / "pipeline-runs" / run_id
    _write_jsonl(run_dir / "repair-events.jsonl", [
        {"round_number": 1, "triggered_by": "test_fail"},
        {"round_number": 2, "triggered_by": "test_fail"},
    ])

    metrics = aggregate_metrics(tmp_path, run_id)

    assert metrics.repair_rounds == 2


def test_aggregate_metrics_retry_count(tmp_path: Path) -> None:
    """Counts lifecycle transitions with to_state='retrying'."""
    run_id = create_pipeline_run(tmp_path, {"repo": "test"})
    run_dir = tmp_path / ".devflow" / "pipeline-runs" / run_id
    _write_jsonl(run_dir / "node-lifecycle-events.jsonl", [
        {"node_id": "build", "from_state": "running", "to_state": "verified"},
        {"node_id": "spec", "from_state": "running", "to_state": "retrying"},
        {"node_id": "spec", "from_state": "retrying", "to_state": "verified"},
    ])

    metrics = aggregate_metrics(tmp_path, run_id)

    assert metrics.retry_count == 1


def test_aggregate_metrics_human_interventions(tmp_path: Path) -> None:
    """Counts review events."""
    run_id = create_pipeline_run(tmp_path, {"repo": "test"})
    run_dir = tmp_path / ".devflow" / "pipeline-runs" / run_id
    _write_jsonl(run_dir / "review-events.jsonl", [
        {"review_id": "r1", "verdict": "pass"},
        {"review_id": "r2", "verdict": "fail"},
    ])

    metrics = aggregate_metrics(tmp_path, run_id)

    assert metrics.human_interventions == 2


def test_aggregate_metrics_workflow_version(tmp_path: Path) -> None:
    """Reads workflow-definition.json for version."""
    run_id = create_pipeline_run(tmp_path, {"repo": "test"})
    run_dir = tmp_path / ".devflow" / "pipeline-runs" / run_id
    (run_dir / "workflow-definition.json").write_text(json.dumps({
        "workflow_id": "hotfix@1",
    }), encoding="utf-8")

    metrics = aggregate_metrics(tmp_path, run_id)

    assert metrics.workflow_version == "hotfix@1"


def test_aggregate_metrics_routes(tmp_path: Path) -> None:
    """Capability routes from reliability metrics."""
    run_id = create_pipeline_run(tmp_path, {"repo": "test"})
    run_dir = tmp_path / ".devflow" / "pipeline-runs" / run_id
    (run_dir / "reliability-report.json").write_text(json.dumps({
        "safe": True,
        "metrics": {
            "capability_routes": ["bounded_coding", "independent_review"],
        },
    }), encoding="utf-8")

    metrics = aggregate_metrics(tmp_path, run_id)

    assert "bounded_coding" in metrics.role_routes
    assert "independent_review" in metrics.role_routes


# ---------------------------------------------------------------------------
# Read-only tests
# ---------------------------------------------------------------------------

def test_metrics_read_only(tmp_path: Path) -> None:
    """Run dir unchanged after aggregate."""
    run_id = create_pipeline_run(tmp_path, {"repo": "test"})
    run_dir = tmp_path / ".devflow" / "pipeline-runs" / run_id

    # Snapshot all file contents
    snapshot: dict[str, bytes] = {}
    for p in run_dir.rglob("*"):
        if p.is_file():
            snapshot[str(p.relative_to(run_dir))] = p.read_bytes()

    aggregate_metrics(tmp_path, run_id)

    for p in run_dir.rglob("*"):
        if p.is_file():
            key = str(p.relative_to(run_dir))
            if key in snapshot:
                assert p.read_bytes() == snapshot[key]


def test_workflow_metrics_frozen() -> None:
    """WorkflowMetrics is immutable."""
    m = WorkflowMetrics(run_id="r")
    with pytest.raises(Exception):
        m.run_id = "modified"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# format_metrics_section tests
# ---------------------------------------------------------------------------

def test_format_metrics_section_format() -> None:
    """Human-readable Markdown format."""
    metrics = WorkflowMetrics(
        run_id="r1",
        total_duration_seconds=5400.0,
        total_tokens=15420,
        retry_count=2,
        repair_rounds=1,
        human_interventions=0,
        reliability_safe=True,
        role_routes=("bounded_coding",),
        workflow_version="hotfix@1",
    )

    section = format_metrics_section(metrics)

    assert "## Workflow Metrics" in section
    assert "90.0 minutes" in section
    assert "15,420" in section
    assert "Retries: 2" in section
    assert "**safe**" in section
    assert "bounded_coding" in section
    assert "hotfix@1" in section


def test_format_metrics_no_data() -> None:
    """Graceful with all zeros."""
    metrics = WorkflowMetrics(run_id="r1")

    section = format_metrics_section(metrics)

    assert "0.0 minutes" in section
    assert "_not available_" in section


# ---------------------------------------------------------------------------
# Promotion packet integration tests
# ---------------------------------------------------------------------------

def test_packet_contains_workflow_metrics(tmp_path: Path) -> None:
    """Promotion packet includes a Workflow Metrics section."""
    from devflow.obsidian.promotion_packet import build_promotion_packet

    run_id = create_pipeline_run(tmp_path, {"repo": "test"})
    run_dir = tmp_path / ".devflow" / "pipeline-runs" / run_id

    _write_accept_decision(tmp_path, run_id)

    # Write reliability report
    (run_dir / "reliability-report.json").write_text(json.dumps({
        "safe": True,
        "action": "proceed",
        "breaches": [],
        "metrics": {"total_duration_seconds": 3600.0, "total_tokens": 5000},
    }), encoding="utf-8")

    packet = build_promotion_packet(tmp_path, run_id)

    assert packet is not None
    assert "## Workflow Metrics" in packet
    assert "60.0 minutes" in packet
    assert "**safe**" in packet


def test_packet_upgrades_review_when_present(tmp_path: Path) -> None:
    """When review-events.jsonl exists, review section shows real findings."""
    from devflow.obsidian.promotion_packet import build_promotion_packet

    run_id = create_pipeline_run(tmp_path, {"repo": "test"})
    run_dir = tmp_path / ".devflow" / "pipeline-runs" / run_id

    _write_accept_decision(tmp_path, run_id)

    # Create a review
    review = ReviewResult(
        review_id="r1",
        run_id=run_id,
        reviewer_family="family-b",
        builder_family="family-a",
        verdict="pass",
        findings=("code quality acceptable", "tests pass"),
        families_independent=True,
        reviewed_at="2026-01-01T00:00:00Z",
    )
    record_review(tmp_path, run_id, review)

    packet = build_promotion_packet(tmp_path, run_id)

    assert packet is not None
    assert "**PASS**" in packet
    assert "code quality acceptable" in packet
    assert "Not yet produced" not in packet


def test_packet_review_not_yet_produced_without_reviews(tmp_path: Path) -> None:
    """No review events → honest 'not yet produced' message."""
    from devflow.obsidian.promotion_packet import build_promotion_packet

    run_id = create_pipeline_run(tmp_path, {"repo": "test"})

    _write_accept_decision(tmp_path, run_id)

    packet = build_promotion_packet(tmp_path, run_id)

    assert packet is not None
    assert "Not yet produced" in packet
