"""Behavior tests for the authoritative canonical workflow ledger."""

from __future__ import annotations

from pathlib import Path
import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from devflow.loop.models import LoopStage
from devflow.loop.pipeline_run import create_pipeline_run
from devflow.loop.pipeline_run import update_pipeline_run_record
from devflow.loop.workflow_ledger import (
    EvidenceReference,
    NodeReceipt,
    WorkflowEvent,
    rebuild_workflow_snapshot,
    initialize_workflow_run,
    record_node_outcome,
    replay_workflow_run,
)


def _idea_receipt(receipt_id: str = "receipt-idea-1") -> NodeReceipt:
    return NodeReceipt(
        receipt_id=receipt_id,
        node_id="idea",
        outcome="success",
        evidence=(EvidenceReference(key="idea-brief", reference="brainstorm.md"),),
    )


def _idea_event(
    event_id: str = "event-idea-1",
    receipt_id: str = "receipt-idea-1",
) -> WorkflowEvent:
    return WorkflowEvent(
        event_id=event_id,
        node_id="idea",
        outcome="success",
        receipt_id=receipt_id,
    )


def _run_dir(root: Path, run_id: str) -> Path:
    return root / ".devflow" / "pipeline-runs" / run_id


def test_evidence_backed_event_advances_replayed_stage(tmp_path: Path) -> None:
    run_id = create_pipeline_run(tmp_path, {"repo": "test/repo"})
    initial = initialize_workflow_run(tmp_path, run_id)
    assert initial.stage == LoopStage.idea

    snapshot = record_node_outcome(
        tmp_path,
        run_id,
        receipt=NodeReceipt(
            receipt_id="receipt-idea-1",
            node_id="idea",
            outcome="success",
            evidence=(
                EvidenceReference(key="idea-brief", reference="brainstorm.md"),
            ),
        ),
        event=WorkflowEvent(
            event_id="event-idea-1",
            node_id="idea",
            outcome="success",
            receipt_id="receipt-idea-1",
        ),
    )

    assert snapshot.current_node_id == "definition"
    assert snapshot.stage == LoopStage.definition
    assert snapshot.completed_node_ids == ("idea",)


def test_receipt_ids_are_immutable_and_cannot_be_reused(tmp_path: Path) -> None:
    run_id = create_pipeline_run(tmp_path, {"repo": "test/repo"})
    initialize_workflow_run(tmp_path, run_id)
    receipt = NodeReceipt(
        receipt_id="receipt-idea-1",
        node_id="idea",
        outcome="success",
        evidence=(EvidenceReference(key="idea-brief", reference="brainstorm.md"),),
    )
    event = WorkflowEvent(
        event_id="event-idea-1",
        node_id="idea",
        outcome="success",
        receipt_id=receipt.receipt_id,
    )
    record_node_outcome(tmp_path, run_id, receipt=receipt, event=event)
    receipt_path = _run_dir(tmp_path, run_id) / "workflow-receipts" / "receipt-idea-1.json"
    before = receipt_path.read_bytes()

    with pytest.raises(ValueError, match="duplicate workflow receipt id"):
        record_node_outcome(
            tmp_path,
            run_id,
            receipt=receipt,
            event=WorkflowEvent(
                event_id="event-definition-1",
                node_id="definition",
                outcome="success",
                receipt_id=receipt.receipt_id,
            ),
        )
    assert receipt_path.read_bytes() == before


def test_duplicate_event_ids_fail_closed_before_any_append(tmp_path: Path) -> None:
    run_id = create_pipeline_run(tmp_path, {"repo": "test/repo"})
    initialize_workflow_run(tmp_path, run_id)
    record_node_outcome(
        tmp_path, run_id, receipt=_idea_receipt(), event=_idea_event()
    )
    ledger = _run_dir(tmp_path, run_id) / "workflow-events.jsonl"
    before = ledger.read_bytes()

    with pytest.raises(ValueError, match="duplicate workflow event id"):
        record_node_outcome(
            tmp_path,
            run_id,
            receipt=NodeReceipt(
                receipt_id="receipt-definition-1",
                node_id="definition",
                outcome="success",
                evidence=(
                    EvidenceReference(
                        key="orientation-receipt", reference="orient-result.json"
                    ),
                ),
            ),
            event=WorkflowEvent(
                event_id="event-idea-1",
                node_id="definition",
                outcome="success",
                receipt_id="receipt-definition-1",
            ),
        )

    assert ledger.read_bytes() == before
    assert not (_run_dir(tmp_path, run_id) / "workflow-receipts" / "receipt-definition-1.json").exists()


def test_missing_required_evidence_fails_without_persisting_records(tmp_path: Path) -> None:
    run_id = create_pipeline_run(tmp_path, {"repo": "test/repo"})
    initialize_workflow_run(tmp_path, run_id)

    with pytest.raises(ValueError, match="missing evidence"):
        record_node_outcome(
            tmp_path,
            run_id,
            receipt=NodeReceipt(
                receipt_id="receipt-idea-1",
                node_id="idea",
                outcome="success",
                evidence=(),
            ),
            event=_idea_event(),
        )

    run_dir = _run_dir(tmp_path, run_id)
    assert (run_dir / "workflow-events.jsonl").read_text() == ""
    assert list((run_dir / "workflow-receipts").iterdir()) == []


def test_invalid_transition_fails_closed(tmp_path: Path) -> None:
    run_id = create_pipeline_run(tmp_path, {"repo": "test/repo"})
    initialize_workflow_run(tmp_path, run_id)
    (_run_dir(tmp_path, run_id) / "spec.md").write_text("spec evidence")

    with pytest.raises(ValueError, match="expected node 'idea'"):
        record_node_outcome(
            tmp_path,
            run_id,
            receipt=NodeReceipt(
                receipt_id="receipt-spec-1",
                node_id="spec",
                outcome="success",
                evidence=(EvidenceReference(key="spec", reference="spec.md"),),
            ),
            event=WorkflowEvent(
                event_id="event-spec-1",
                node_id="spec",
                outcome="success",
                receipt_id="receipt-spec-1",
            ),
        )


def test_event_and_receipt_must_match(tmp_path: Path) -> None:
    run_id = create_pipeline_run(tmp_path, {"repo": "test/repo"})
    initialize_workflow_run(tmp_path, run_id)

    with pytest.raises(ValueError, match="does not match its receipt"):
        record_node_outcome(
            tmp_path,
            run_id,
            receipt=_idea_receipt(),
            event=WorkflowEvent(
                event_id="event-idea-1",
                node_id="idea",
                outcome="failure",
                receipt_id="receipt-idea-1",
            ),
        )


def test_failure_route_replays_to_blocked(tmp_path: Path) -> None:
    run_id = create_pipeline_run(tmp_path, {"repo": "test/repo"})
    initialize_workflow_run(tmp_path, run_id)
    snapshot = record_node_outcome(
        tmp_path,
        run_id,
        receipt=NodeReceipt(
            receipt_id="receipt-idea-failed",
            node_id="idea",
            outcome="failure",
            evidence=(EvidenceReference(key="idea-brief", reference="brainstorm.md"),),
        ),
        event=WorkflowEvent(
            event_id="event-idea-failed",
            node_id="idea",
            outcome="failure",
            receipt_id="receipt-idea-failed",
        ),
    )

    assert snapshot.current_node_id == "blocked"
    assert snapshot.stage == LoopStage.blocked


def test_corrupt_event_record_fails_closed(tmp_path: Path) -> None:
    run_id = create_pipeline_run(tmp_path, {"repo": "test/repo"})
    initialize_workflow_run(tmp_path, run_id)
    (_run_dir(tmp_path, run_id) / "workflow-events.jsonl").write_text("{\n")

    with pytest.raises(ValueError):
        replay_workflow_run(tmp_path, run_id)


def test_corrupt_receipt_record_fails_closed(tmp_path: Path) -> None:
    run_id = create_pipeline_run(tmp_path, {"repo": "test/repo"})
    initialize_workflow_run(tmp_path, run_id)
    record_node_outcome(
        tmp_path, run_id, receipt=_idea_receipt(), event=_idea_event()
    )
    receipt_path = _run_dir(tmp_path, run_id) / "workflow-receipts" / "receipt-idea-1.json"
    receipt_path.chmod(0o644)
    receipt_path.write_text("{}\n")

    with pytest.raises(ValueError, match="missing or corrupt"):
        replay_workflow_run(tmp_path, run_id)


def test_unreferenced_or_corrupt_receipt_records_fail_closed(tmp_path: Path) -> None:
    run_id = create_pipeline_run(tmp_path, {"repo": "test/repo"})
    initialize_workflow_run(tmp_path, run_id)
    orphan = _run_dir(tmp_path, run_id) / "workflow-receipts" / "orphan.json"
    orphan.write_text("{}\n")

    with pytest.raises(ValueError, match="missing or corrupt"):
        replay_workflow_run(tmp_path, run_id)


def test_generic_persistence_cannot_overwrite_authoritative_ledger_files(
    tmp_path: Path,
) -> None:
    run_id = create_pipeline_run(tmp_path, {"repo": "test/repo"})
    initialize_workflow_run(tmp_path, run_id)

    for file_name in ("workflow-definition.json", "workflow-events.jsonl"):
        with pytest.raises(ValueError, match="workflow ledger API"):
            update_pipeline_run_record(tmp_path, run_id, file_name, {})


def test_snapshot_contents_are_ignored_and_rebuildable(tmp_path: Path) -> None:
    run_id = create_pipeline_run(tmp_path, {"repo": "test/repo"})
    initialize_workflow_run(tmp_path, run_id)
    expected = record_node_outcome(
        tmp_path, run_id, receipt=_idea_receipt(), event=_idea_event()
    )
    snapshot_path = _run_dir(tmp_path, run_id) / "workflow-snapshot.json"
    snapshot_path.write_text(json.dumps({"stage": "complete"}))

    assert replay_workflow_run(tmp_path, run_id) == expected
    assert rebuild_workflow_snapshot(tmp_path, run_id) == expected
    assert json.loads(snapshot_path.read_text())["stage"] == "definition"


def test_replaying_same_ledger_is_deterministic(tmp_path: Path) -> None:
    run_id = create_pipeline_run(tmp_path, {"repo": "test/repo"})
    initialize_workflow_run(tmp_path, run_id)
    record_node_outcome(
        tmp_path, run_id, receipt=_idea_receipt(), event=_idea_event()
    )

    first = replay_workflow_run(tmp_path, run_id)
    second = replay_workflow_run(tmp_path, run_id)

    assert first == second
    assert first.model_dump_json() == second.model_dump_json()


def test_corrupt_or_unsupported_definition_fails_closed(tmp_path: Path) -> None:
    run_id = create_pipeline_run(tmp_path, {"repo": "test/repo"})
    initialize_workflow_run(tmp_path, run_id)
    definition_path = _run_dir(tmp_path, run_id) / "workflow-definition.json"
    definition_path.chmod(0o644)
    definition_path.write_text('{"workflow_id":"canonical_product_build@2"}\n')

    with pytest.raises(ValueError, match="missing or corrupt"):
        replay_workflow_run(tmp_path, run_id)


def test_concurrent_outcomes_serialize_without_partial_ledger_state(
    tmp_path: Path,
) -> None:
    run_id = create_pipeline_run(tmp_path, {"repo": "test/repo"})
    initialize_workflow_run(tmp_path, run_id)

    def record(suffix: str) -> object:
        return record_node_outcome(
            tmp_path,
            run_id,
            receipt=_idea_receipt(f"receipt-idea-{suffix}"),
            event=_idea_event(f"event-idea-{suffix}", f"receipt-idea-{suffix}"),
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(record, suffix) for suffix in ("a", "b")]
    outcomes = []
    for future in futures:
        try:
            outcomes.append(future.result())
        except ValueError as exc:
            outcomes.append(exc)

    assert sum(not isinstance(outcome, Exception) for outcome in outcomes) == 1
    assert sum(isinstance(outcome, ValueError) for outcome in outcomes) == 1
    assert replay_workflow_run(tmp_path, run_id).stage == LoopStage.definition
    run_dir = _run_dir(tmp_path, run_id)
    assert len((run_dir / "workflow-events.jsonl").read_text().splitlines()) == 1
    assert len(list((run_dir / "workflow-receipts").iterdir())) == 1
