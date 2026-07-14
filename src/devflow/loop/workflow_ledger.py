"""Authoritative append-only ledger for canonical DevFlow workflow runs."""

from __future__ import annotations

import json
import os
import fcntl
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from devflow.loop.models import LoopStage
from devflow.loop.pipeline_run import pipeline_runs_dir
from devflow.loop.workflow_definition import (
    WORKFLOW_ID,
    WorkflowDefinition,
    canonical_product_build_v1,
)


WORKFLOW_DEFINITION_FILE = "workflow-definition.json"
WORKFLOW_EVENTS_FILE = "workflow-events.jsonl"
WORKFLOW_RECEIPTS_DIR = "workflow-receipts"
WORKFLOW_SNAPSHOT_FILE = "workflow-snapshot.json"
_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"


class EvidenceReference(BaseModel):
    """Immutable reference to persisted evidence required by a workflow node."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str = Field(min_length=1)
    reference: str = Field(min_length=1)


class NodeReceipt(BaseModel):
    """Immutable outcome receipt for one workflow node."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    receipt_id: str = Field(min_length=1, pattern=_ID_PATTERN)
    node_id: str = Field(min_length=1, pattern=_ID_PATTERN)
    outcome: Literal["success", "failure"]
    evidence: tuple[EvidenceReference, ...]


class WorkflowEvent(BaseModel):
    """One append-only event linking a node outcome to its receipt."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: str = Field(min_length=1, pattern=_ID_PATTERN)
    node_id: str = Field(min_length=1, pattern=_ID_PATTERN)
    outcome: Literal["success", "failure"]
    receipt_id: str = Field(min_length=1, pattern=_ID_PATTERN)


class WorkflowSnapshot(BaseModel):
    """Rebuildable projection of the authoritative workflow ledger."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    workflow_id: Literal["canonical_product_build@1"]
    current_node_id: str
    stage: LoopStage
    completed_node_ids: tuple[str, ...] = ()


def _run_dir(root: Path | str, run_id: str) -> Path:
    runs_dir = pipeline_runs_dir(root).resolve()
    run_dir = (runs_dir / run_id).resolve()
    try:
        run_dir.relative_to(runs_dir)
    except ValueError as exc:
        raise ValueError("workflow run id escapes the pipeline run directory") from exc
    if not run_dir.is_dir():
        raise FileNotFoundError(f"Pipeline run not found: {run_dir}")
    return run_dir


@contextmanager
def _ledger_lock(run_dir: Path, *, exclusive: bool) -> Iterator[None]:
    lock_path = run_dir / ".workflow-ledger.lock"
    with lock_path.open("a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _canonical_definition_bytes() -> bytes:
    payload = canonical_product_build_v1().model_dump(mode="json")
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()


def _write_exclusive(path: Path, data: bytes, *, mode: int = 0o444) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
    except Exception:
        path.unlink(missing_ok=True)
        raise


def _load_definition(run_dir: Path) -> WorkflowDefinition:
    path = run_dir / WORKFLOW_DEFINITION_FILE
    try:
        definition = WorkflowDefinition.model_validate_json(path.read_text())
    except (OSError, ValueError) as exc:
        raise ValueError("canonical workflow definition is missing or corrupt") from exc
    if definition != canonical_product_build_v1():
        raise ValueError("persisted workflow definition is not canonical_product_build@1")
    return definition


def _load_events(run_dir: Path) -> tuple[WorkflowEvent, ...]:
    path = run_dir / WORKFLOW_EVENTS_FILE
    try:
        raw_lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ValueError("canonical workflow event ledger is missing") from exc
    events: list[WorkflowEvent] = []
    for line_number, line in enumerate(raw_lines, start=1):
        if not line.strip():
            raise ValueError(f"workflow event line {line_number} is empty")
        try:
            events.append(WorkflowEvent.model_validate_json(line))
        except ValueError as exc:
            raise ValueError(f"workflow event line {line_number} is corrupt") from exc
    return tuple(events)


def _load_receipt(run_dir: Path, receipt_id: str) -> NodeReceipt:
    path = run_dir / WORKFLOW_RECEIPTS_DIR / f"{receipt_id}.json"
    try:
        receipt = NodeReceipt.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"workflow receipt {receipt_id!r} is missing or corrupt") from exc
    if receipt.receipt_id != receipt_id:
        raise ValueError(f"workflow receipt filename does not match {receipt_id!r}")
    _validate_evidence_references(run_dir, receipt)
    return receipt


def _load_all_receipts(run_dir: Path) -> dict[str, NodeReceipt]:
    receipts_dir = run_dir / WORKFLOW_RECEIPTS_DIR
    if not receipts_dir.is_dir():
        raise ValueError("canonical workflow receipt store is missing")
    receipts: dict[str, NodeReceipt] = {}
    for path in sorted(receipts_dir.iterdir()):
        if not path.is_file() or path.suffix != ".json":
            raise ValueError(f"unexpected workflow receipt record: {path.name!r}")
        receipt_id = path.stem
        receipt = _load_receipt(run_dir, receipt_id)
        if receipt.receipt_id in receipts:
            raise ValueError(f"duplicate workflow receipt id: {receipt.receipt_id}")
        receipts[receipt.receipt_id] = receipt
    return receipts


def _validate_evidence_references(run_dir: Path, receipt: NodeReceipt) -> None:
    for evidence in receipt.evidence:
        reference = Path(evidence.reference)
        if reference.is_absolute() or reference.name != evidence.reference:
            raise ValueError(
                f"workflow evidence reference {evidence.reference!r} is outside the run"
            )
        if not (run_dir / reference).is_file():
            raise ValueError(
                f"workflow evidence reference {evidence.reference!r} is missing"
            )


def _project(
    definition: WorkflowDefinition,
    events: tuple[WorkflowEvent, ...],
    receipt_loader,
) -> WorkflowSnapshot:
    nodes = {node.id: node for node in definition.nodes}
    edges = {
        (edge.source, edge.outcome): edge
        for edge in definition.edges
    }
    current_node_id = definition.nodes[0].id
    completed: list[str] = []
    event_ids: set[str] = set()
    used_receipt_ids: set[str] = set()

    for event in events:
        if event.event_id in event_ids:
            raise ValueError(f"duplicate workflow event id: {event.event_id}")
        if event.receipt_id in used_receipt_ids:
            raise ValueError(f"duplicate workflow receipt reference: {event.receipt_id}")
        if event.node_id != current_node_id:
            raise ValueError(
                f"invalid workflow transition: expected node {current_node_id!r}, "
                f"got {event.node_id!r}"
            )
        edge = edges.get((event.node_id, event.outcome))
        if edge is None:
            raise ValueError(
                f"invalid workflow outcome {event.outcome!r} for node {event.node_id!r}"
            )
        receipt = receipt_loader(event.receipt_id)
        if (
            receipt.node_id != event.node_id
            or receipt.outcome != event.outcome
            or receipt.receipt_id != event.receipt_id
        ):
            raise ValueError(f"workflow event {event.event_id!r} does not match its receipt")
        evidence_keys = [reference.key for reference in receipt.evidence]
        if len(evidence_keys) != len(set(evidence_keys)):
            raise ValueError(f"workflow receipt {receipt.receipt_id!r} has duplicate evidence keys")
        missing = set(nodes[event.node_id].required_evidence) - set(evidence_keys)
        if missing:
            raise ValueError(
                f"workflow receipt {receipt.receipt_id!r} is missing evidence: "
                f"{sorted(missing)}"
            )
        event_ids.add(event.event_id)
        used_receipt_ids.add(event.receipt_id)
        completed.append(event.node_id)
        current_node_id = edge.target

    return WorkflowSnapshot(
        workflow_id=WORKFLOW_ID,
        current_node_id=current_node_id,
        stage=nodes[current_node_id].stage,
        completed_node_ids=tuple(completed),
    )


def _replay_unlocked(run_dir: Path) -> WorkflowSnapshot:
    definition = _load_definition(run_dir)
    events = _load_events(run_dir)
    receipts = _load_all_receipts(run_dir)
    referenced = {event.receipt_id for event in events}
    if set(receipts) != referenced:
        raise ValueError("workflow receipt store does not match the event ledger")
    return _project(definition, events, lambda receipt_id: receipts[receipt_id])


def replay_workflow_run(root: Path | str, run_id: str) -> WorkflowSnapshot:
    """Derive current state only from the immutable definition, events, and receipts."""

    run_dir = _run_dir(root, run_id)
    with _ledger_lock(run_dir, exclusive=False):
        return _replay_unlocked(run_dir)


def _write_snapshot(run_dir: Path, snapshot: WorkflowSnapshot) -> None:
    path = run_dir / WORKFLOW_SNAPSHOT_FILE
    temp = run_dir / f".{WORKFLOW_SNAPSHOT_FILE}.tmp"
    temp.write_text(
        json.dumps(snapshot.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temp.replace(path)


def rebuild_workflow_snapshot(root: Path | str, run_id: str) -> WorkflowSnapshot:
    """Replace the disposable snapshot with a fresh deterministic replay projection."""

    run_dir = _run_dir(root, run_id)
    with _ledger_lock(run_dir, exclusive=True):
        snapshot = _replay_unlocked(run_dir)
        _write_snapshot(run_dir, snapshot)
        return snapshot


def is_canonical_workflow_run(root: Path | str, run_id: str) -> bool:
    """Return whether a run carries the explicit canonical workflow marker."""

    try:
        return (_run_dir(root, run_id) / WORKFLOW_DEFINITION_FILE).is_file()
    except FileNotFoundError:
        return False


def initialize_workflow_run(root: Path | str, run_id: str) -> WorkflowSnapshot:
    """Persist the one canonical definition and an empty append-only ledger."""

    run_dir = _run_dir(root, run_id)
    definition_path = run_dir / WORKFLOW_DEFINITION_FILE
    events_path = run_dir / WORKFLOW_EVENTS_FILE
    receipts_path = run_dir / WORKFLOW_RECEIPTS_DIR

    with _ledger_lock(run_dir, exclusive=True):
        if definition_path.exists() or events_path.exists() or receipts_path.exists():
            if not (
                definition_path.is_file()
                and events_path.is_file()
                and receipts_path.is_dir()
            ):
                raise ValueError("canonical workflow initialization is partial or corrupt")
            snapshot = _replay_unlocked(run_dir)
            _write_snapshot(run_dir, snapshot)
            return snapshot

        _write_exclusive(definition_path, _canonical_definition_bytes())
        try:
            _write_exclusive(events_path, b"", mode=0o644)
            receipts_path.mkdir(mode=0o755)
        except Exception:
            definition_path.unlink(missing_ok=True)
            events_path.unlink(missing_ok=True)
            raise
        snapshot = _replay_unlocked(run_dir)
        _write_snapshot(run_dir, snapshot)
        return snapshot


def record_node_outcome(
    root: Path | str,
    run_id: str,
    *,
    receipt: NodeReceipt,
    event: WorkflowEvent,
) -> WorkflowSnapshot:
    """Validate then append one immutable receipt and one authoritative event."""

    run_dir = _run_dir(root, run_id)
    with _ledger_lock(run_dir, exclusive=True):
        _replay_unlocked(run_dir)
        definition = _load_definition(run_dir)
        events = _load_events(run_dir)
        if any(existing.event_id == event.event_id for existing in events):
            raise ValueError(f"duplicate workflow event id: {event.event_id}")
        receipt_path = run_dir / WORKFLOW_RECEIPTS_DIR / f"{receipt.receipt_id}.json"
        if receipt_path.exists():
            raise ValueError(f"duplicate workflow receipt id: {receipt.receipt_id}")
        _project(
            definition,
            events + (event,),
            lambda receipt_id: receipt
            if receipt_id == receipt.receipt_id
            else _load_receipt(run_dir, receipt_id),
        )
        _validate_evidence_references(run_dir, receipt)
        receipt_payload = json.dumps(
            receipt.model_dump(mode="json"), indent=2, sort_keys=True
        ).encode() + b"\n"
        _write_exclusive(receipt_path, receipt_payload)
        event_path = run_dir / WORKFLOW_EVENTS_FILE
        try:
            with event_path.open("a", encoding="utf-8") as handle:
                handle.write(
                    json.dumps(event.model_dump(mode="json"), sort_keys=True) + "\n"
                )
                handle.flush()
                os.fsync(handle.fileno())
        except Exception:
            receipt_path.chmod(0o644)
            receipt_path.unlink(missing_ok=True)
            raise
        rebuilt = _replay_unlocked(run_dir)
        _write_snapshot(run_dir, rebuilt)
        return rebuilt


__all__ = [
    "EvidenceReference",
    "NodeReceipt",
    "WorkflowEvent",
    "WorkflowSnapshot",
    "is_canonical_workflow_run",
    "initialize_workflow_run",
    "rebuild_workflow_snapshot",
    "record_node_outcome",
    "replay_workflow_run",
]
