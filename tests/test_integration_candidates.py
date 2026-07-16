"""Tests for verified integration candidates collector (M3-S4)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from devflow.loop.integration_candidates import (
    CandidateSummary,
    IntegrationCandidate,
    collect_integration_candidates,
)
from devflow.loop.pipeline_run import (
    create_pipeline_run,
    update_pipeline_run_record,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_execution_plan(
    packets: list[dict],
    target_files: list[str] | None = None,
) -> dict:
    """Build a minimal execution-plan.json-compatible dict."""
    all_files = target_files or []
    for p in packets:
        all_files.extend(p.get("target_files", []))
    if not all_files:
        all_files = ["src/main.py"]

    return {
        "schema_version": 1,
        "workflow_id": "canonical_product_build@1",
        "target_files": sorted(set(all_files)),
        "packets": packets,
        "validators": [
            {
                "id": "v1",
                "kind": "command",
                "argv": ["python3", "-c", "pass"],
                "cwd": ".",
                "timeout_seconds": 10,
                "network": "forbid",
                "permissions": [],
                "evidence": ["exit-code"],
            }
        ],
    }


def _write_verification_receipt(
    root: Path,
    run_id: str,
    receipt_id: str,
    passed: bool = True,
) -> None:
    data = {
        "receipt_id": receipt_id,
        "passed": passed,
        "summary": "All tests passed." if passed else "Tests failed.",
    }
    update_pipeline_run_record(
        root, run_id,
        f"verification-receipt-{receipt_id}.json",
        json.dumps(data),
    )


def _build_run_with_plan(
    tmp_path: Path,
    packets: list[dict],
    target_files: list[str] | None = None,
) -> tuple[Path, str]:
    repo = tmp_path / "repo"
    run_id = create_pipeline_run(repo, {"repo": "test/repo"})
    plan = _make_execution_plan(packets, target_files)
    update_pipeline_run_record(repo, run_id, "execution-plan.json", json.dumps(plan))
    return repo, run_id


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_candidates_dependency_ordered(tmp_path: Path) -> None:
    """Candidates returned in dependency order."""
    packets = [
        {"id": "p-b", "target_files": ["src/b.py"], "depends_on": ["p-a"]},
        {"id": "p-a", "target_files": ["src/a.py"], "depends_on": []},
        {"id": "p-c", "target_files": ["src/c.py"], "depends_on": ["p-a", "p-b"]},
    ]
    repo, run_id = _build_run_with_plan(tmp_path, packets)

    summary = collect_integration_candidates(repo, run_id)

    # validate_packet_dag returns sorted by ID, so order is p-a, p-b, p-c
    ids = [c.packet_id for c in summary.candidates]
    assert ids == ["p-a", "p-b", "p-c"]
    assert summary.candidates[0].integration_order_index == 0
    assert summary.candidates[2].integration_order_index == 2


def test_candidates_all_verified(tmp_path: Path) -> None:
    """All packets verified → all_verified=True."""
    packets = [
        {"id": "p-a", "target_files": ["src/a.py"], "depends_on": []},
        {"id": "p-b", "target_files": ["src/b.py"], "depends_on": ["p-a"]},
    ]
    repo, run_id = _build_run_with_plan(tmp_path, packets)
    _write_verification_receipt(repo, run_id, "p-a", passed=True)
    _write_verification_receipt(repo, run_id, "p-b", passed=True)

    summary = collect_integration_candidates(repo, run_id)

    assert summary.all_verified is True
    assert summary.ready_for_integration is True
    assert all(c.verified for c in summary.candidates)


def test_candidates_partial_verified(tmp_path: Path) -> None:
    """Some unverified → all_verified=False."""
    packets = [
        {"id": "p-a", "target_files": ["src/a.py"], "depends_on": []},
        {"id": "p-b", "target_files": ["src/b.py"], "depends_on": ["p-a"]},
    ]
    repo, run_id = _build_run_with_plan(tmp_path, packets)
    _write_verification_receipt(repo, run_id, "p-a", passed=True)
    # p-b not verified

    summary = collect_integration_candidates(repo, run_id)

    assert summary.all_verified is False
    assert summary.ready_for_integration is False
    assert summary.candidates[0].verified is True
    assert summary.candidates[1].verified is False


def test_candidates_empty_plan_raises(tmp_path: Path) -> None:
    """No execution-plan.json → ValueError from load_execution_plan."""
    repo = tmp_path / "repo"
    run_id = create_pipeline_run(repo, {"repo": "test/repo"})

    with pytest.raises(ValueError, match="no authoritative execution-plan"):
        collect_integration_candidates(repo, run_id)


def test_candidates_single_packet(tmp_path: Path) -> None:
    """One packet → one candidate, order 0."""
    packets = [
        {"id": "p-solo", "target_files": ["src/main.py"], "depends_on": []},
    ]
    repo, run_id = _build_run_with_plan(tmp_path, packets)
    _write_verification_receipt(repo, run_id, "p-solo", passed=True)

    summary = collect_integration_candidates(repo, run_id)

    assert len(summary.candidates) == 1
    assert summary.candidates[0].packet_id == "p-solo"
    assert summary.candidates[0].integration_order_index == 0
    assert summary.all_verified is True


def test_ready_for_integration_true(tmp_path: Path) -> None:
    """All verified + deps satisfied → True."""
    packets = [
        {"id": "p-a", "target_files": ["src/a.py"], "depends_on": []},
        {"id": "p-b", "target_files": ["src/b.py"], "depends_on": ["p-a"]},
    ]
    repo, run_id = _build_run_with_plan(tmp_path, packets)
    _write_verification_receipt(repo, run_id, "p-a", passed=True)
    _write_verification_receipt(repo, run_id, "p-b", passed=True)

    summary = collect_integration_candidates(repo, run_id)

    assert summary.ready_for_integration is True


def test_ready_for_integration_false_unverified(tmp_path: Path) -> None:
    """Unverified packet → ready=False."""
    packets = [
        {"id": "p-a", "target_files": ["src/a.py"], "depends_on": []},
    ]
    repo, run_id = _build_run_with_plan(tmp_path, packets)
    # No verification receipt

    summary = collect_integration_candidates(repo, run_id)

    assert summary.ready_for_integration is False
    assert summary.all_verified is False


def test_read_only_no_mutation(tmp_path: Path) -> None:
    """Run dir unchanged after collect."""
    packets = [
        {"id": "p-a", "target_files": ["src/a.py"], "depends_on": []},
    ]
    repo, run_id = _build_run_with_plan(tmp_path, packets)
    _write_verification_receipt(repo, run_id, "p-a", passed=True)

    run_dir = repo / ".devflow" / "pipeline-runs" / run_id
    snapshot_before = {}
    for f in sorted(run_dir.iterdir()):
        if f.is_file():
            snapshot_before[f.name] = f.read_bytes()

    collect_integration_candidates(repo, run_id)

    for name, content_before in snapshot_before.items():
        assert (run_dir / name).read_bytes() == content_before, f"{name} was modified"


def test_candidates_include_target_files(tmp_path: Path) -> None:
    """Each candidate has its target_files."""
    packets = [
        {"id": "p-a", "target_files": ["src/a.py", "src/b.py"], "depends_on": []},
        {"id": "p-b", "target_files": ["src/c.py"], "depends_on": ["p-a"]},
    ]
    repo, run_id = _build_run_with_plan(tmp_path, packets)

    summary = collect_integration_candidates(repo, run_id)

    assert summary.candidates[0].target_files == ("src/a.py", "src/b.py")
    assert summary.candidates[1].target_files == ("src/c.py",)


def test_candidates_include_depends_on(tmp_path: Path) -> None:
    """Each candidate carries its depends_on."""
    packets = [
        {"id": "p-a", "target_files": ["src/a.py"], "depends_on": []},
        {"id": "p-b", "target_files": ["src/b.py"], "depends_on": ["p-a"]},
    ]
    repo, run_id = _build_run_with_plan(tmp_path, packets)

    summary = collect_integration_candidates(repo, run_id)

    assert summary.candidates[0].depends_on == ()
    assert summary.candidates[1].depends_on == ("p-a",)


def test_candidate_summary_frozen() -> None:
    """CandidateSummary is immutable."""
    summary = CandidateSummary(run_id="test")
    with pytest.raises(Exception):
        summary.all_verified = True  # type: ignore[misc]


def test_integration_candidate_frozen() -> None:
    """IntegrationCandidate is immutable."""
    c = IntegrationCandidate(packet_id="p", integration_order_index=0)
    with pytest.raises(Exception):
        c.verified = True  # type: ignore[misc]


def test_failed_verification_not_counted(tmp_path: Path) -> None:
    """A failed receipt doesn't mark the packet as verified."""
    packets = [
        {"id": "p-a", "target_files": ["src/a.py"], "depends_on": []},
    ]
    repo, run_id = _build_run_with_plan(tmp_path, packets)
    _write_verification_receipt(repo, run_id, "p-a", passed=False)

    summary = collect_integration_candidates(repo, run_id)

    assert summary.candidates[0].verified is False
    assert summary.all_verified is False
