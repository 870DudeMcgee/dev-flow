"""Canonical run read-model adapter (M0-S1).

Derives a public, honest read model from the authoritative workflow ledger for
canonical-marked runs. This is an *additive* read model — it does not replace
``LoopStage``, does not change any writer, and does not mutate canonical state.

Usage::

    from devflow.loop.read_model import load_canonical_run_model

    model = load_canonical_run_model(root, run_id)
    print(model.current_stage, model.progress, model.is_blocked)

Noncanonical runs (those without the ``workflow-definition.json`` marker) raise
``NotCanonicalRunError``.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from devflow.loop.models import LoopStage
from devflow.loop.workflow_definition import canonical_product_build_v1
from devflow.loop.workflow_ledger import (
    WorkflowSnapshot,
    is_canonical_workflow_run,
    rebuild_workflow_snapshot,
)

# The productive chain length — 9 nodes from ``idea`` through ``human_decision``.
# ``complete`` and ``blocked`` are terminal and excluded from progress scoring.
_PRODUCTIVE_NODE_COUNT = 9


class NotCanonicalRunError(ValueError):
    """Raised when a run lacks the canonical workflow marker."""

    def __init__(self, run_id: str) -> None:
        super().__init__(
            f"run {run_id!r} is not a canonical workflow run "
            "(missing workflow-definition.json)"
        )
        self.run_id = run_id


class NodeStatus(str):
    """Per-node lifecycle status within the success chain."""

    completed = "completed"
    current = "current"
    pending = "pending"


class NodeInfo(BaseModel):
    """One workflow node with its derived status."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    node_id: str = Field(min_length=1)
    stage: LoopStage
    status: str = Field(min_length=1)


class CanonicalRunModel(BaseModel):
    """Derived public read model for one canonical workflow run.

    Built purely from :class:`WorkflowSnapshot` via
    :func:`derive_canonical_run_model`. No persistence, no I/O, no mutation.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str = Field(min_length=1)
    workflow_id: str = Field(min_length=1)
    current_node_id: str
    current_stage: LoopStage
    completed_node_ids: tuple[str, ...] = ()
    pending_node_ids: tuple[str, ...] = ()
    nodes: tuple[NodeInfo, ...] = ()
    progress: float = Field(ge=0.0, le=1.0)
    is_terminal: bool
    is_blocked: bool
    snapshot_stage: LoopStage


def _productive_chain() -> tuple[str, ...]:
    """Return the ordered productive node IDs from the canonical definition.

    Walks success edges starting at ``idea`` until ``complete``. Excludes
    ``complete`` and ``blocked`` since they are terminal.
    """
    definition = canonical_product_build_v1()
    success_targets: dict[str, str] = {}
    for edge in definition.edges:
        if edge.outcome == "success":
            success_targets[edge.source] = edge.target

    chain: list[str] = []
    current = "idea"
    visited: set[str] = set()
    while current is not None and current not in visited:
        visited.add(current)
        if current in ("complete", "blocked"):
            break
        chain.append(current)
        current = success_targets.get(current)
    return tuple(chain)


def _node_to_stage(node_id: str) -> LoopStage:
    """Map a node ID to its LoopStage using the canonical definition."""
    definition = canonical_product_build_v1()
    for node in definition.nodes:
        if node.id == node_id:
            return node.stage
    raise ValueError(f"unknown node id {node_id!r} in canonical definition")


def derive_canonical_run_model(
    snapshot: WorkflowSnapshot,
    run_id: str,
) -> CanonicalRunModel:
    """Derive the public read model from a workflow snapshot.

    Pure function — no I/O, no mutation. ``snapshot`` must come from
    :func:`rebuild_workflow_snapshot` or :func:`replay_workflow_run`.
    """
    chain = _productive_chain()
    completed = snapshot.completed_node_ids
    completed_set = set(completed)

    is_blocked = snapshot.stage == LoopStage.blocked
    is_complete = snapshot.stage == LoopStage.complete
    is_terminal = is_blocked or is_complete

    if is_terminal:
        pending: tuple[str, ...] = ()
    else:
        pending = tuple(
            nid
            for nid in chain
            if nid not in completed_set and nid != snapshot.current_node_id
        )

    progress = len(completed) / _PRODUCTIVE_NODE_COUNT
    if progress > 1.0:
        progress = 1.0

    node_infos: list[NodeInfo] = []
    for nid in chain:
        if nid in completed_set:
            status = NodeStatus.completed
        elif nid == snapshot.current_node_id and not is_terminal:
            status = NodeStatus.current
        else:
            status = NodeStatus.pending
        node_infos.append(
            NodeInfo(
                node_id=nid,
                stage=_node_to_stage(nid),
                status=status,
            )
        )
    # Append terminal nodes for completeness.
    for terminal_id in ("complete", "blocked"):
        if is_complete and terminal_id == "complete":
            node_infos.append(
                NodeInfo(
                    node_id="complete",
                    stage=LoopStage.complete,
                    status=NodeStatus.current,
                )
            )
        elif is_blocked and terminal_id == "blocked":
            node_infos.append(
                NodeInfo(
                    node_id="blocked",
                    stage=LoopStage.blocked,
                    status=NodeStatus.current,
                )
            )

    return CanonicalRunModel(
        run_id=run_id,
        workflow_id=snapshot.workflow_id,
        current_node_id=snapshot.current_node_id,
        current_stage=snapshot.stage,
        completed_node_ids=completed,
        pending_node_ids=pending,
        nodes=tuple(node_infos),
        progress=progress,
        is_terminal=is_terminal,
        is_blocked=is_blocked,
        snapshot_stage=snapshot.stage,
    )


def load_canonical_run_model(
    root: Path | str,
    run_id: str,
) -> CanonicalRunModel:
    """Load and derive the read model for one canonical run.

    Raises :class:`NotCanonicalRunError` for noncanonical runs.
    """
    if not is_canonical_workflow_run(root, run_id):
        raise NotCanonicalRunError(run_id)
    snapshot = rebuild_workflow_snapshot(root, run_id)
    return derive_canonical_run_model(snapshot, run_id)


__all__ = [
    "CanonicalRunModel",
    "NodeInfo",
    "NodeStatus",
    "NotCanonicalRunError",
    "derive_canonical_run_model",
    "load_canonical_run_model",
]
