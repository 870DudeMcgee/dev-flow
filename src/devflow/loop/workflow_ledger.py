"""Authoritative append-only ledger for canonical DevFlow workflow runs."""

from __future__ import annotations

import hashlib
import json
import os
import fcntl
from contextlib import contextmanager
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Iterator
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from devflow.loop.models import LoopStage
from devflow.loop.pipeline_run import pipeline_runs_dir
from devflow.loop.workflow_definition import (
    WORKFLOW_ID,
    WorkflowDefinition,
    WorkflowEdge,
    canonical_product_build_v1,
)
from devflow.loop.workflow_schema import (
    WorkflowSchemaV2,
    WorkflowStrategy,
    _detect_back_edges,
)


WORKFLOW_DEFINITION_FILE = "workflow-definition.json"
WORKFLOW_DEFINITION_V2_FILE = "workflow-definition-v2.json"
WORKFLOW_EVENTS_FILE = "workflow-events.jsonl"
WORKFLOW_RECEIPTS_DIR = "workflow-receipts"
WORKFLOW_SNAPSHOT_FILE = "workflow-snapshot.json"
_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"
_DECISION_SHA256 = r"^[0-9a-f]{64}$"
_DECISION_GIT_SHA = r"^[0-9a-f]{40,64}$"
DECISION_RECEIPTS_DIR = "decision-receipts"
DECISION_EVENTS_FILE = "decision-events.jsonl"


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

    workflow_id: str
    current_node_id: str
    stage: LoopStage
    completed_node_ids: tuple[str, ...] = ()
    active_node_ids: tuple[str, ...] = ()


class DecisionType(str, Enum):
    """Operator decision type at the human_decision boundary.

    Separate from the legacy :class:`HumanDecision` enum in
    ``human_decision.py`` and intentionally does not alter any of its members
    or behavior. Only ``accept`` makes the work promotion-eligible.
    """

    accept = "accept"
    reject = "reject"
    request_changes = "request_changes"


class DecisionReceipt(BaseModel):
    """Immutable operator decision binding the verified integration state.

    The receipt binds the run, the integration worktree head/tree/fingerprint,
    the independent verification receipt id and its canonical sha256 hash, the
    actor, the decision type, and a UTC-aware timestamp. It is persisted
    immutably (O_EXCL + 0o444) and replayable.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    decision_id: str = Field(pattern=_ID_PATTERN)
    run_id: str = Field(pattern=_ID_PATTERN)
    integration_id: str = Field(pattern=_ID_PATTERN)
    integration_head: str = Field(pattern=_DECISION_GIT_SHA)
    integration_tree: str = Field(pattern=_DECISION_GIT_SHA)
    integration_fingerprint: str = Field(pattern=_DECISION_SHA256)
    verification_receipt_id: str = Field(pattern=_ID_PATTERN)
    verification_receipt_hash: str = Field(pattern=_DECISION_SHA256)
    actor: str = Field(min_length=1)
    decision_type: DecisionType
    promotion_eligible: bool
    created_at: datetime

    @model_validator(mode="after")
    def _check_promotion_eligibility(self) -> "DecisionReceipt":
        if self.decision_type == DecisionType.accept and not self.promotion_eligible:
            raise ValueError("accept decisions must be promotion_eligible")
        if self.decision_type != DecisionType.accept and self.promotion_eligible:
            raise ValueError(
                "only accept decisions may be promotion_eligible"
            )
        return self


class DecisionEvent(BaseModel):
    """One ordered, append-only event linking a decision to its receipt."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: str = Field(pattern=_ID_PATTERN)
    decision_id: str = Field(pattern=_ID_PATTERN)
    node_id: Literal["human_decision"]
    outcome: Literal["accept", "reject", "request_changes"]
    receipt_id: str = Field(pattern=_ID_PATTERN)


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


def _v2_definition_bytes(definition: WorkflowSchemaV2) -> bytes:
    payload = definition.model_dump(mode="json")
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()


def _load_v2_definition(run_dir: Path) -> WorkflowSchemaV2 | None:
    path = run_dir / WORKFLOW_DEFINITION_V2_FILE
    if not path.is_file():
        return None
    try:
        return WorkflowSchemaV2.model_validate_json(path.read_text())
    except (OSError, ValueError) as exc:
        raise ValueError("generalized workflow definition (v2) is missing or corrupt") from exc


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
        active_node_ids=(),
    )


def _project_v2(
    definition: WorkflowSchemaV2,
    events: tuple[WorkflowEvent, ...],
    receipt_loader,
) -> WorkflowSnapshot:
    """Generalized projection that respects the v2 definition's node order.

    Mirrors :func:`_project` but operates on a :class:`WorkflowSchemaV2` and
    uses its ``workflow_id`` (which is ``str`` rather than the canonical
    literal). The v2 node sequence may start at any node (e.g. ``analyze``),
    unlike the canonical definition which always starts at ``idea``.
    """
    nodes = {node.id: node for node in definition.nodes}
    edges = {
        (edge.source, edge.outcome): edge
        for edge in definition.edges
    }
    if not definition.nodes:
        raise ValueError("generalized workflow definition has no nodes")
    root_ids = {n.id for n in definition.nodes} - {e.target for e in definition.edges}
    if not root_ids:
        raise ValueError("workflow definition has no root node (cycle or empty graph)")
    if len(root_ids) > 1:
        raise ValueError(f"workflow definition has multiple root nodes: {sorted(root_ids)!r}")
    current_node_id = next(iter(root_ids))
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
        workflow_id=definition.workflow_id,
        current_node_id=current_node_id,
        stage=nodes[current_node_id].stage,
        completed_node_ids=tuple(completed),
        active_node_ids=(),
    )


def _project_v2_general(
    definition: WorkflowSchemaV2,
    events: tuple[WorkflowEvent, ...],
    receipt_loader,
) -> WorkflowSnapshot:
    """Frontier-based projection for parallel/dag/loop v2 workflows.

    Unlike :func:`_project_v2` (strict single cursor), this tracks a SET of
    active nodes (the frontier). Each event marks its node completed and
    advances any successor whose preconditions are now met onto the frontier.
    Parallel/dag fan-out and loop back-edges are handled by set semantics.
    """
    nodes = {node.id: node for node in definition.nodes}
    # (source, outcome) -> list[edge] because a node may fan out to
    # multiple targets via several 'success' edges (parallel/dag).
    edges: dict[tuple[str, str], list[WorkflowEdge]] = {}
    for edge in definition.edges:
        edges.setdefault((edge.source, edge.outcome), []).append(edge)
    if not definition.nodes:
        raise ValueError("generalized workflow definition has no nodes")

    # Build the adjacency graph so the intentional loop back-edge can be
    # detected (DFS) and excluded from in-degree for root discovery.
    graph: dict[str, list[str]] = {nid: [] for nid in nodes}
    for edge in definition.edges:
        graph[edge.source].append(edge.target)

    # For strategy=loop the one intentional DFS back-edge must be excluded
    # from in-degree so the loop head (its intended target) is correctly
    # identified as the single root. Non-loop strategies have no back-edge.
    back_edges: set[tuple[str, str]] = set()
    if definition.strategy == WorkflowStrategy.loop:
        back_edges = _detect_back_edges(graph)

    in_degree: dict[str, int] = {nid: 0 for nid in nodes}
    for edge in definition.edges:
        if (edge.source, edge.target) in back_edges:
            continue
        in_degree[edge.target] += 1
    # Loop head (in-degree 0 after excluding the back-edge) is the start;
    # for non-loop the unique root (parallel may have several).
    roots = [nid for nid, d in in_degree.items() if d == 0]
    if not roots:
        raise ValueError("workflow definition has no root node (cycle or empty graph)")
    if definition.strategy == WorkflowStrategy.loop:
        if len(roots) != 1:
            raise ValueError(f"workflow definition has multiple root nodes: {sorted(roots)!r}")
    elif len(roots) > 1 and definition.strategy != WorkflowStrategy.parallel:
        raise ValueError(f"workflow definition has multiple root nodes: {sorted(roots)!r}")

    # Incoming predecessors per target, and the (source, target) -> outcomes
    # map. A non-terminal target (a real DAG join) must wait until every
    # non-terminal predecessor has completed via the outcome that fires its
    # edge into the target. Terminal predecessors never block activation.
    terminal_stages = {LoopStage.complete, LoopStage.blocked}
    predecessors: dict[str, list[str]] = {nid: [] for nid in nodes}
    source_target_outcomes: dict[tuple[str, str], set[str]] = {}
    for edge in definition.edges:
        predecessors.setdefault(edge.target, [])
        if edge.source not in predecessors[edge.target]:
            predecessors[edge.target].append(edge.source)
        source_target_outcomes.setdefault(
            (edge.source, edge.target), set()
        ).add(edge.outcome)

    active: set[str] = set(roots)
    completed: list[str] = []
    reached_terminals: list[str] = []
    # node_id -> set of outcomes for which a matching event was replayed.
    fired: dict[str, set[str]] = {}
    event_ids: set[str] = set()
    used_receipt_ids: set[str] = set()

    for event in events:
        if event.event_id in event_ids:
            raise ValueError(f"duplicate workflow event id: {event.event_id}")
        if event.receipt_id in used_receipt_ids:
            raise ValueError(f"duplicate workflow receipt reference: {event.receipt_id}")
        if event.node_id not in active:
            raise ValueError(
                f"invalid workflow transition: node {event.node_id!r} "
                f"is not active; active={sorted(active)!r}"
            )
        matching_edges = edges.get((event.node_id, event.outcome))
        if not matching_edges:
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
        active.discard(event.node_id)
        # Record this node's fired outcome so downstream joins can wait on it.
        fired.setdefault(event.node_id, set()).add(event.outcome)
        for edge in matching_edges:
            target = edge.target
            if nodes[target].stage in terminal_stages:
                # Terminal node reached; record it so the snapshot can
                # resolve current_node_id to the terminal when the
                # frontier empties (mirrors the linear projector). Do not
                # emit terminal node events.
                reached_terminals.append(target)
                continue
            # Real DAG join: a non-terminal target is activated only after
            # every non-terminal predecessor has completed via the outcome
            # that fires its edge into this target. Terminal predecessors
            # (e.g. a loop that ended) never block activation; and a
            # predecessor that fired the *wrong* outcome for this target is
            # likewise not a pending precondition (it routed elsewhere).
            preds = predecessors.get(target, [])
            pending = [
                src for src in preds
                if src in nodes
                and nodes[src].stage not in terminal_stages
                and not (
                    source_target_outcomes.get((src, target), set())
                    & fired.get(src, set())
                )
            ]
            if pending:
                # Not all join preconditions are met yet; keep the join
                # inactive until the remaining predecessors succeed on the
                # edges that lead into it.
                continue
            active.add(target)

    if not active:
        current = reached_terminals[-1] if reached_terminals else (completed[-1] if completed else sorted(roots)[0])
        return WorkflowSnapshot(
            workflow_id=definition.workflow_id,
            current_node_id=current,
            stage=nodes[current].stage,
            completed_node_ids=tuple(completed),
            active_node_ids=(),
        )
    return WorkflowSnapshot(
        workflow_id=definition.workflow_id,
        current_node_id=sorted(active)[0] if len(active) == 1 else sorted(active)[0],
        stage=nodes[sorted(active)[0]].stage,
        completed_node_ids=tuple(completed),
        active_node_ids=tuple(sorted(active)),
    )


def _project_v2_strategy(
    definition: WorkflowSchemaV2,
    events: tuple[WorkflowEvent, ...],
    receipt_loader,
) -> WorkflowSnapshot:
    """Dispatch to the linear or frontier projector based on strategy."""
    if definition.strategy == WorkflowStrategy.sequence:
        return _project_v2(definition, events, receipt_loader)
    return _project_v2_general(definition, events, receipt_loader)


def _replay_unlocked(run_dir: Path) -> WorkflowSnapshot:
    definition = _load_definition(run_dir)
    events = _load_events(run_dir)
    receipts = _load_all_receipts(run_dir)
    referenced = {event.receipt_id for event in events}
    if set(receipts) != referenced:
        raise ValueError("workflow receipt store does not match the event ledger")
    return _project(definition, events, lambda receipt_id: receipts[receipt_id])


def _replay_unlocked_v2(run_dir: Path) -> WorkflowSnapshot:
    definition = _load_v2_definition(run_dir)
    if definition is None:
        raise ValueError("generalized workflow definition (v2) is missing")
    events = _load_events(run_dir)
    receipts = _load_all_receipts(run_dir)
    referenced = {event.receipt_id for event in events}
    if set(receipts) != referenced:
        raise ValueError("workflow receipt store does not match the event ledger")
    return _project_v2_strategy(definition, events, lambda receipt_id: receipts[receipt_id])


def _replay_unlocked_any(run_dir: Path) -> WorkflowSnapshot:
    """Replay a run, dispatching to the canonical or v2 projection automatically.

    A run is treated as generalized when it carries a v2 definition marker and
    no canonical (v1) definition. The legacy canonical path is unchanged.
    """
    if (run_dir / WORKFLOW_DEFINITION_FILE).is_file():
        return _replay_unlocked(run_dir)
    if (run_dir / WORKFLOW_DEFINITION_V2_FILE).is_file():
        return _replay_unlocked_v2(run_dir)
    return _replay_unlocked(run_dir)


def replay_workflow_run(root: Path | str, run_id: str) -> WorkflowSnapshot:
    """Derive current state only from the immutable definition, events, and receipts."""

    run_dir = _run_dir(root, run_id)
    with _ledger_lock(run_dir, exclusive=False):
        return _replay_unlocked_any(run_dir)


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
        snapshot = _replay_unlocked_any(run_dir)
        _write_snapshot(run_dir, snapshot)
        return snapshot


def is_canonical_workflow_run(root: Path | str, run_id: str) -> bool:
    """Return whether a run carries the explicit canonical workflow marker."""

    try:
        return (_run_dir(root, run_id) / WORKFLOW_DEFINITION_FILE).is_file()
    except FileNotFoundError:
        return False


def initialize_workflow_run(
    root: Path | str,
    run_id: str,
    *,
    definition: WorkflowDefinition | WorkflowSchemaV2 | None = None,
) -> WorkflowSnapshot:
    """Persist the workflow definition and an empty append-only ledger.

    The definition marker written depends on the ``definition`` argument:

    * ``None`` (default) — write the canonical ``canonical_product_build@1``
      definition to ``workflow-definition.json`` (legacy behavior, unchanged).
    * a :class:`WorkflowDefinition` (v1) — write canonical definition bytes.
    * a :class:`WorkflowSchemaV2` — write the generalized definition to
      ``workflow-definition-v2.json``. The run is NOT canonical, but it is
      fully recorded and projectable through :func:`_project_v2`.

    The rest of initialization (events file, receipts dir, snapshot) is
    identical regardless of which definition is used.
    """

    run_dir = _run_dir(root, run_id)
    definition_path = run_dir / WORKFLOW_DEFINITION_FILE
    v2_definition_path = run_dir / WORKFLOW_DEFINITION_V2_FILE
    events_path = run_dir / WORKFLOW_EVENTS_FILE
    receipts_path = run_dir / WORKFLOW_RECEIPTS_DIR

    with _ledger_lock(run_dir, exclusive=True):
        if (
            definition_path.exists()
            or v2_definition_path.exists()
            or events_path.exists()
            or receipts_path.exists()
        ):
            if not (
                (
                    definition_path.is_file()
                    and events_path.is_file()
                    and receipts_path.is_dir()
                )
                or (
                    v2_definition_path.is_file()
                    and events_path.is_file()
                    and receipts_path.is_dir()
                )
            ):
                raise ValueError("workflow initialization is partial or corrupt")
            snapshot = _replay_unlocked_any(run_dir)
            _write_snapshot(run_dir, snapshot)
            return snapshot

        if isinstance(definition, WorkflowSchemaV2):
            _write_exclusive(v2_definition_path, _v2_definition_bytes(definition))
        else:
            _write_exclusive(definition_path, _canonical_definition_bytes())
        try:
            _write_exclusive(events_path, b"", mode=0o644)
            receipts_path.mkdir(mode=0o755)
        except Exception:
            definition_path.unlink(missing_ok=True)
            v2_definition_path.unlink(missing_ok=True)
            events_path.unlink(missing_ok=True)
            raise
        snapshot = _replay_unlocked_any(run_dir)
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
        # Detect generalized (v2) definitions without breaking the legacy
        # canonical path. A run with a v2 definition marker but no canonical
        # marker is projected through _project_v2.
        v2_definition = None
        if not (run_dir / WORKFLOW_DEFINITION_FILE).is_file():
            v2_definition = _load_v2_definition(run_dir)

        if v2_definition is not None:
            definition = v2_definition  # type: ignore[assignment]
            events = _load_events(run_dir)
            if any(existing.event_id == event.event_id for existing in events):
                raise ValueError(f"duplicate workflow event id: {event.event_id}")
            receipt_path = run_dir / WORKFLOW_RECEIPTS_DIR / f"{receipt.receipt_id}.json"
            if receipt_path.exists():
                raise ValueError(f"duplicate workflow receipt id: {receipt.receipt_id}")
            _project_v2_strategy(
                definition,  # type: ignore[arg-type]
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
            rebuilt = _replay_unlocked_v2(run_dir)
            _write_snapshot(run_dir, rebuilt)
            return rebuilt

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


def _load_decision_receipt(run_dir: Path, decision_id: str) -> DecisionReceipt:
    path = run_dir / DECISION_RECEIPTS_DIR / f"{decision_id}.json"
    try:
        receipt = DecisionReceipt.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"decision receipt {decision_id!r} is missing or corrupt") from exc
    if receipt.decision_id != decision_id:
        raise ValueError(f"decision receipt filename does not match {decision_id!r}")
    return receipt


# ---------------------------------------------------------------------------
# Phase 6A — typed immutable human-decision authority
# ---------------------------------------------------------------------------
def record_decision(
    root: Path | str,
    receipt: DecisionReceipt,
    *,
    repo: Path | str,
    event_id: str | None = None,
) -> DecisionReceipt:
    """Persist an immutable operator decision and append one ordered event.

    Reuses the Phase 5 authority to fail closed before any terminal state is
    exposed:

    * the integration worktree must be clean (not dirty/stale/mismatched) and
      its live ``head``/``tree``/``fingerprint`` must match the receipt;
    * the bound independent verification receipt must be present, non-corrupt,
      passing, and of the ``integration_verification`` family;
    * the bound verification receipt's canonical sha256 must equal
      ``receipt.verification_receipt_hash``.

    Persistence is immutable (O_EXCL + 0o444) and the ordered event is fsync'd
    to ``decision-events.jsonl`` *before* the receipt file is exposed. Identical
    replay returns the existing receipt; a conflicting replay fails closed.

    ``accept`` sets ``promotion_eligible`` only. It does not complete the loop,
    create or move a result branch, or mutate ``main``. ``reject`` and
    ``request_changes`` are non-promoting and non-completing and create/move no
    branch.
    """
    from devflow.loop.run_integration import (
        IntegrationError,
        IntegrationVerificationReceipt,
        load_integration_snapshot,
        load_sandbox_receipt,
    )

    if receipt.decision_type == DecisionType.accept and not receipt.promotion_eligible:
        raise ValueError("accept decisions must be promotion_eligible")
    if receipt.decision_type != DecisionType.accept and receipt.promotion_eligible:
        raise ValueError("only accept decisions may be promotion_eligible")

    run_dir = _run_dir(root, receipt.run_id)
    with _ledger_lock(run_dir, exclusive=True):
        # --- Phase 5 integration worktree checks (reused, never weakened) ---
        state = load_integration_snapshot(root, receipt.run_id)
        if state.integration_id != receipt.integration_id:
            raise ValueError(
                "decision is bound to a different integration id than the run"
            )
        if state.sandbox_id is None:
            raise ValueError("integration worktree has not been created")
        sandbox = load_sandbox_receipt(root, receipt.run_id, state.sandbox_id)
        worktree = Path(sandbox.path).resolve()
        if not worktree.is_dir():
            raise ValueError("integration worktree is missing")
        from devflow.loop.run_integration import _status_paths, _current_git_state

        if _status_paths(worktree):
            raise ValueError("integration worktree is dirty")
        live_head, live_tree = _current_git_state(worktree)
        if (live_head, live_tree) != (receipt.integration_head, receipt.integration_tree):
            raise ValueError(
                "integration worktree head/tree does not match the decision receipt"
            )
        if state.fingerprint != receipt.integration_fingerprint:
            raise ValueError(
                "integration fingerprint does not match the decision receipt"
            )

        # --- Phase 5 independent verification receipt checks (reused) ---
        verification_path = (
            run_dir / "integration-verification-receipts" / f"{receipt.verification_receipt_id}.json"
        )
        try:
            verification = IntegrationVerificationReceipt.model_validate_json(
                verification_path.read_text(encoding="utf-8")
            )
        except (OSError, ValueError) as exc:
            raise ValueError(
                "bound integration verification receipt is missing or corrupt"
            ) from exc
        if verification.receipt_id != receipt.verification_receipt_id:
            raise ValueError(
                "integration verification receipt filename does not match its id"
            )
        if verification.run_id != receipt.run_id:
            raise ValueError(
                "integration verification receipt is bound to a different run"
            )
        if verification.integration_id != receipt.integration_id:
            raise ValueError(
                "integration verification receipt is bound to a different integration"
            )
        if verification.verdict != "pass":
            raise ValueError(
                "decision cannot bind a non-passing integration verification receipt"
            )
        try:
            verification_sha256 = hashlib.sha256(
                json.dumps(
                    verification.model_dump(mode="json"),
                    indent=2,
                    sort_keys=True,
                ).encode()
                + b"\n"
            ).hexdigest()
        except IntegrationError as exc:  # pragma: no cover - defensive
            raise ValueError(
                "bound integration verification receipt is corrupt"
            ) from exc
        if verification_sha256 != receipt.verification_receipt_hash:
            raise ValueError(
                "integration verification receipt hash does not match the decision receipt"
            )

        receipts_dir = run_dir / DECISION_RECEIPTS_DIR
        receipts_dir.mkdir(mode=0o755, exist_ok=True)
        receipt_path = receipts_dir / f"{receipt.decision_id}.json"

        if receipt_path.exists():
            existing = _load_decision_receipt(run_dir, receipt.decision_id)
            if existing == receipt:
                return existing
            raise ValueError(
                f"conflicting decision receipt replay for {receipt.decision_id!r}"
            )

        resolved_event_id = event_id or f"decision-{receipt.decision_id}"
        events_path = run_dir / DECISION_EVENTS_FILE
        if events_path.exists():
            for line in events_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    recorded = DecisionEvent.model_validate_json(line)
                except ValueError:
                    continue
                if recorded.receipt_id == receipt.decision_id:
                    raise ValueError(
                        f"duplicate decision event for receipt {receipt.decision_id!r}"
                    )

        event = DecisionEvent(
            event_id=resolved_event_id,
            decision_id=receipt.decision_id,
            node_id="human_decision",
            outcome=receipt.decision_type.value,  # type: ignore[arg-type]
            receipt_id=receipt.decision_id,
        )

        # Ordered event appended and fsync'd BEFORE the terminal receipt is exposed.
        try:
            with events_path.open("a", encoding="utf-8") as handle:
                handle.write(
                    json.dumps(event.model_dump(mode="json"), sort_keys=True) + "\n"
                )
                handle.flush()
                os.fsync(handle.fileno())
        except Exception:
            raise

        receipt_payload = (
            json.dumps(receipt.model_dump(mode="json"), indent=2, sort_keys=True).encode()
            + b"\n"
        )
        try:
            _write_exclusive(receipt_path, receipt_payload)
        except Exception:
            events_path.unlink(missing_ok=True)
            raise
        return receipt


__all__ = [
    "EvidenceReference",
    "NodeReceipt",
    "WorkflowEvent",
    "WorkflowSnapshot",
    "DecisionType",
    "DecisionReceipt",
    "DecisionEvent",
    "is_canonical_workflow_run",
    "initialize_workflow_run",
    "rebuild_workflow_snapshot",
    "record_node_outcome",
    "record_decision",
    "replay_workflow_run",
]
