"""Behavior tests for the canonical run read-model adapter (M0-S1)."""

from __future__ import annotations

from pathlib import Path

import pytest

from devflow.loop.models import LoopStage
from devflow.loop.pipeline_run import create_pipeline_run
from devflow.loop.read_model import (
    CanonicalRunModel,
    NodeStatus,
    NotCanonicalRunError,
    derive_canonical_run_model,
    load_canonical_run_model,
)
from devflow.loop.workflow_ledger import (
    EvidenceReference,
    NodeReceipt,
    WorkflowEvent,
    initialize_workflow_run,
    rebuild_workflow_snapshot,
    record_node_outcome,
)


# ---------------------------------------------------------------------------
# Helpers — build disposable canonical runs under tmp_path
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
    # The ledger validates that evidence reference files exist in the run dir.
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


def _advance_to(
    root: Path,
    run_id: str,
    through_node: str,
) -> None:
    """Record success outcomes for all nodes up to and including *through_node*."""
    for idx, (node_id, evidence_id) in enumerate(_SUCCESS_CHAIN, start=1):
        _record_success(root, run_id, node_id, evidence_id, idx)
        if node_id == through_node:
            break


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_derive_from_fresh_snapshot(tmp_path: Path) -> None:
    """Just-initialized run: stage=idea, progress=0.0, no completed nodes."""
    run_id = create_pipeline_run(tmp_path, {"repo": "test/repo"})
    initialize_workflow_run(tmp_path, run_id)
    snapshot = rebuild_workflow_snapshot(tmp_path, run_id)

    model = derive_canonical_run_model(snapshot, run_id)

    assert model.run_id == run_id
    assert model.current_stage == LoopStage.idea
    assert model.current_node_id == "idea"
    assert model.completed_node_ids == ()
    assert model.progress == pytest.approx(0.0)
    assert model.is_terminal is False
    assert model.is_blocked is False
    assert len(model.pending_node_ids) == 8  # all except idea (current)


def test_derive_after_one_node(tmp_path: Path) -> None:
    """idea success → stage=definition, progress=1/9."""
    run_id = create_pipeline_run(tmp_path, {"repo": "test/repo"})
    initialize_workflow_run(tmp_path, run_id)
    _advance_to(tmp_path, run_id, "idea")

    snapshot = rebuild_workflow_snapshot(tmp_path, run_id)
    model = derive_canonical_run_model(snapshot, run_id)

    assert model.current_stage == LoopStage.definition
    assert model.completed_node_ids == ("idea",)
    assert model.progress == pytest.approx(1.0 / 9.0)
    assert model.pending_node_ids == (
        "spec", "planning", "planning_judge", "assignment",
        "build_judge", "verification", "human_decision",
    )
    # idea should be completed, definition current
    nodes_by_id = {n.node_id: n for n in model.nodes}
    assert nodes_by_id["idea"].status == NodeStatus.completed
    assert nodes_by_id["definition"].status == NodeStatus.current
    assert nodes_by_id["spec"].status == NodeStatus.pending


def test_derive_mid_chain(tmp_path: Path) -> None:
    """spec success → progress=3/9, 3 completed nodes."""
    run_id = create_pipeline_run(tmp_path, {"repo": "test/repo"})
    initialize_workflow_run(tmp_path, run_id)
    _advance_to(tmp_path, run_id, "spec")

    snapshot = rebuild_workflow_snapshot(tmp_path, run_id)
    model = derive_canonical_run_model(snapshot, run_id)

    assert model.completed_node_ids == ("idea", "definition", "spec")
    assert model.progress == pytest.approx(3.0 / 9.0)
    assert model.current_stage == LoopStage.planning
    assert model.current_node_id == "planning"


def test_derive_complete(tmp_path: Path) -> None:
    """All 9 productive nodes succeed → stage=complete, progress=1.0, terminal."""
    run_id = create_pipeline_run(tmp_path, {"repo": "test/repo"})
    initialize_workflow_run(tmp_path, run_id)
    _advance_to(tmp_path, run_id, "human_decision")

    snapshot = rebuild_workflow_snapshot(tmp_path, run_id)
    model = derive_canonical_run_model(snapshot, run_id)

    assert model.current_stage == LoopStage.complete
    assert model.progress == pytest.approx(1.0)
    assert model.is_terminal is True
    assert model.is_blocked is False
    assert model.pending_node_ids == ()
    # 'complete' node should appear as current
    nodes_by_id = {n.node_id: n for n in model.nodes}
    assert nodes_by_id["complete"].status == NodeStatus.current


def test_derive_blocked(tmp_path: Path) -> None:
    """A failure outcome routes to blocked → is_blocked, is_terminal."""
    run_id = create_pipeline_run(tmp_path, {"repo": "test/repo"})
    initialize_workflow_run(tmp_path, run_id)
    _record_failure(tmp_path, run_id, "idea", "idea-brief", 1)

    snapshot = rebuild_workflow_snapshot(tmp_path, run_id)
    model = derive_canonical_run_model(snapshot, run_id)

    assert model.current_stage == LoopStage.blocked
    assert model.is_blocked is True
    assert model.is_terminal is True
    assert model.pending_node_ids == ()
    nodes_by_id = {n.node_id: n for n in model.nodes}
    assert "blocked" in nodes_by_id
    assert nodes_by_id["blocked"].status == NodeStatus.current


def test_pending_nodes_excludes_completed(tmp_path: Path) -> None:
    """pending = full chain - completed - current."""
    run_id = create_pipeline_run(tmp_path, {"repo": "test/repo"})
    initialize_workflow_run(tmp_path, run_id)
    # Advance through spec → 3 completed (idea, definition, spec), current=planning
    _advance_to(tmp_path, run_id, "spec")

    snapshot = rebuild_workflow_snapshot(tmp_path, run_id)
    model = derive_canonical_run_model(snapshot, run_id)

    assert model.completed_node_ids == ("idea", "definition", "spec")
    assert model.current_node_id == "planning"
    # pending = chain minus completed minus current
    assert model.pending_node_ids == (
        "planning_judge", "assignment", "build_judge",
        "verification", "human_decision",
    )


def test_load_rejects_noncanonical_run(tmp_path: Path) -> None:
    """No workflow-definition.json → NotCanonicalRunError."""
    run_id = create_pipeline_run(tmp_path, {"repo": "test/repo"})
    # Note: initialize_workflow_run NOT called — no canonical marker

    with pytest.raises(NotCanonicalRunError, match="not a canonical workflow run"):
        load_canonical_run_model(tmp_path, run_id)


def test_loopstage_still_importable() -> None:
    """LoopStage is NOT deleted — compat projection retained."""
    # Simple import + usage check
    assert LoopStage.idea.value == "idea"
    assert LoopStage.complete.value == "complete"
    assert LoopStage.blocked.value == "blocked"


def test_existing_writers_unchanged(tmp_path: Path) -> None:
    """record_node_outcome still works correctly after read_model import."""
    run_id = create_pipeline_run(tmp_path, {"repo": "test/repo"})
    initialize_workflow_run(tmp_path, run_id)
    _advance_to(tmp_path, run_id, "idea")

    # read_model import should not have affected the ledger
    snapshot = rebuild_workflow_snapshot(tmp_path, run_id)
    assert snapshot.stage == LoopStage.definition
    assert snapshot.completed_node_ids == ("idea",)

    # Load the read model — should be consistent with the snapshot
    model = load_canonical_run_model(tmp_path, run_id)
    assert model.current_stage == LoopStage.definition
    assert model.completed_node_ids == ("idea",)


def test_model_is_frozen(tmp_path: Path) -> None:
    """The derived model is immutable."""
    run_id = create_pipeline_run(tmp_path, {"repo": "test/repo"})
    initialize_workflow_run(tmp_path, run_id)
    model = load_canonical_run_model(tmp_path, run_id)

    with pytest.raises(Exception):
        model.current_stage = LoopStage.spec  # type: ignore[misc]


def test_node_infos_cover_chain(tmp_path: Path) -> None:
    """The nodes tuple covers all productive chain nodes."""
    run_id = create_pipeline_run(tmp_path, {"repo": "test/repo"})
    initialize_workflow_run(tmp_path, run_id)
    model = load_canonical_run_model(tmp_path, run_id)

    chain_ids = {n.node_id for n in model.nodes}
    expected = {
        "idea", "definition", "spec", "planning", "planning_judge",
        "assignment", "build_judge", "verification", "human_decision",
    }
    assert expected.issubset(chain_ids)


def test_workflow_id_is_canonical(tmp_path: Path) -> None:
    """The model reports the correct workflow_id."""
    run_id = create_pipeline_run(tmp_path, {"repo": "test/repo"})
    initialize_workflow_run(tmp_path, run_id)
    model = load_canonical_run_model(tmp_path, run_id)

    assert model.workflow_id == "canonical_product_build@1"
