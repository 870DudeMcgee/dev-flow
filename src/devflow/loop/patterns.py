"""Reusable orchestration patterns (M3-S3, blueprint §8.5).

Five composable pattern builders that produce valid workflow subgraphs.
These are **schema-level builders** — they compose nodes and edges into
reusable shapes. No new runtime; the output is nodes + edges that can be
inserted into a :class:`~devflow.loop.workflow_schema.WorkflowSchemaV2`.

All patterns use functional role names only — no model identity (naming rule).

Patterns (blueprint §8.5):

- **Scatter–gather**: N independent investigators → 1 synthesizer.
- **Competing proposals**: M planners propose → 1 judge selects/merges.
- **Adversarial verification**: Builder → reviewer tries to disprove.
- **Map–verify–reduce**: Fan-out over items, each verified, then reduced.
- **Convergence loop**: Check → repair → recheck until pass or bound.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from devflow.loop.models import LoopStage
from devflow.loop.workflow_definition import (
    NodeKind,
    WorkflowEdge,
    WorkflowNode,
)


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

PATTERN_KINDS = frozenset({
    "scatter_gather",
    "competing",
    "adversarial",
    "map_verify_reduce",
    "convergence",
})


class PatternSpec(BaseModel):
    """Specification for one pattern instance."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    pattern_id: str = Field(min_length=1)
    kind: str = Field(min_length=1)  # one of PATTERN_KINDS
    node_prefix: str = Field(min_length=1)  # prefix for generated node IDs
    participant_roles: tuple[str, ...] = ()  # functional role names only
    config: dict[str, Any] = {}


class PatternResult(BaseModel):
    """Result of building a pattern — nodes and edges to insert into a workflow."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    nodes: tuple[WorkflowNode, ...]
    edges: tuple[WorkflowEdge, ...]
    entry_node_id: str  # first node to execute
    exit_node_id: str   # last node (gather/reduce/judge)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _node(
    prefix: str,
    suffix: str,
    kind: NodeKind = NodeKind.agent,
    stage: LoopStage = LoopStage.spec,
    evidence: tuple[str, ...] = ("output",),
) -> WorkflowNode:
    return WorkflowNode(
        id=f"{prefix}-{suffix}",
        kind=kind,
        stage=stage,
        required_evidence=evidence,
    )


def _edge(source: str, target: str, outcome: str = "success") -> WorkflowEdge:
    return WorkflowEdge(
        id=f"{source}:{outcome}",
        source=source,
        target=target,
        outcome=outcome,  # type: ignore[arg-type]
    )


def _failure_to_blocked(source: str) -> WorkflowEdge:
    return WorkflowEdge(
        id=f"{source}:failure",
        source=source,
        target=f"{_node_id_base(source)}-blocked",
        outcome="failure",
    )


def _node_id_base(full_id: str) -> str:
    """Extract the pattern prefix from a node ID (strip last '-segment')."""
    parts = full_id.rsplit("-", 1)
    return parts[0] if len(parts) > 1 else full_id


# ---------------------------------------------------------------------------
# Pattern builders
# ---------------------------------------------------------------------------

def build_scatter_gather(spec: PatternSpec) -> PatternResult:
    """N independent investigators → 1 synthesizer.

    Config:
        investigators: int (default: len(participant_roles) or 2)
    """
    n = spec.config.get("investigators", len(spec.participant_roles) or 2)
    p = spec.node_prefix

    nodes: list[WorkflowNode] = []
    edges: list[WorkflowEdge] = []

    # Investigator nodes (parallel)
    investigator_ids: list[str] = []
    for i in range(n):
        nid = f"{p}-investigator-{i+1}"
        investigator_ids.append(nid)
        nodes.append(_node(p, f"investigator-{i+1}", NodeKind.agent, LoopStage.spec))

    # Synthesizer (gather)
    synth_id = f"{p}-synthesizer"
    nodes.append(_node(p, "synthesizer", NodeKind.agent, LoopStage.planning))

    # Blocked terminal
    blocked_id = f"{p}-blocked"
    nodes.append(_node(p, "blocked", NodeKind.human, LoopStage.blocked, evidence=()))

    # Edges: each investigator → synthesizer (success), each → blocked (failure)
    for inv_id in investigator_ids:
        edges.append(_edge(inv_id, synth_id))
        edges.append(_failure_to_blocked(inv_id))

    return PatternResult(
        nodes=tuple(nodes),
        edges=tuple(edges),
        entry_node_id=investigator_ids[0] if investigator_ids else synth_id,
        exit_node_id=synth_id,
    )


def build_competing(spec: PatternSpec) -> PatternResult:
    """M planners propose → 1 judge selects/merges.

    Config:
        proposers: int (default: len(participant_roles) or 2)
    """
    m = spec.config.get("proposers", len(spec.participant_roles) or 2)
    p = spec.node_prefix

    nodes: list[WorkflowNode] = []
    edges: list[WorkflowEdge] = []

    proposer_ids: list[str] = []
    for i in range(m):
        nid = f"{p}-proposer-{i+1}"
        proposer_ids.append(nid)
        nodes.append(_node(p, f"proposer-{i+1}", NodeKind.agent, LoopStage.planning))

    judge_id = f"{p}-judge"
    nodes.append(_node(p, "judge", NodeKind.agent, LoopStage.planning_judge))

    blocked_id = f"{p}-blocked"
    nodes.append(_node(p, "blocked", NodeKind.human, LoopStage.blocked, evidence=()))

    for prop_id in proposer_ids:
        edges.append(_edge(prop_id, judge_id))
        edges.append(_failure_to_blocked(prop_id))

    return PatternResult(
        nodes=tuple(nodes),
        edges=tuple(edges),
        entry_node_id=proposer_ids[0] if proposer_ids else judge_id,
        exit_node_id=judge_id,
    )


def build_adversarial(spec: PatternSpec) -> PatternResult:
    """Builder → adversarial reviewer.

    The builder produces; the reviewer independently tries to disprove.
    """
    p = spec.node_prefix

    builder_id = f"{p}-builder"
    reviewer_id = f"{p}-reviewer"
    blocked_id = f"{p}-blocked"

    nodes = (
        _node(p, "builder", NodeKind.agent, LoopStage.assignment),
        _node(p, "reviewer", NodeKind.agent, LoopStage.build_judge),
        _node(p, "blocked", NodeKind.human, LoopStage.blocked, evidence=()),
    )
    edges = (
        _edge(builder_id, reviewer_id),
        _failure_to_blocked(builder_id),
        _failure_to_blocked(reviewer_id),
    )

    return PatternResult(
        nodes=nodes,
        edges=edges,
        entry_node_id=builder_id,
        exit_node_id=reviewer_id,
    )


def build_map_verify_reduce(spec: PatternSpec) -> PatternResult:
    """Fan-out over items, each verified, then reduced.

    Config:
        items: int (default: len(participant_roles) or 3)
    """
    n = spec.config.get("items", len(spec.participant_roles) or 3)
    p = spec.node_prefix

    nodes: list[WorkflowNode] = []
    edges: list[WorkflowEdge] = []

    worker_ids: list[str] = []
    verifier_ids: list[str] = []
    for i in range(n):
        wid = f"{p}-worker-{i+1}"
        vid = f"{p}-verifier-{i+1}"
        worker_ids.append(wid)
        verifier_ids.append(vid)
        nodes.append(_node(p, f"worker-{i+1}", NodeKind.agent, LoopStage.assignment))
        nodes.append(_node(p, f"verifier-{i+1}", NodeKind.code, LoopStage.verification))

    reducer_id = f"{p}-reducer"
    nodes.append(_node(p, "reducer", NodeKind.agent, LoopStage.build_judge))

    blocked_id = f"{p}-blocked"
    nodes.append(_node(p, "blocked", NodeKind.human, LoopStage.blocked, evidence=()))

    # worker_i → verifier_i (success), worker_i → blocked (failure)
    for wid, vid in zip(worker_ids, verifier_ids, strict=True):
        edges.append(_edge(wid, vid))
        edges.append(_failure_to_blocked(wid))

    # verifier_i → reducer (success), verifier_i → blocked (failure)
    for vid in verifier_ids:
        edges.append(_edge(vid, reducer_id))
        edges.append(_failure_to_blocked(vid))

    return PatternResult(
        nodes=tuple(nodes),
        edges=tuple(edges),
        entry_node_id=worker_ids[0] if worker_ids else reducer_id,
        exit_node_id=reducer_id,
    )


def build_convergence(spec: PatternSpec) -> PatternResult:
    """Check → repair → recheck loop with bounds.

    Config:
        max_rounds: int (default: 4)
        stop_if_no_progress: int (default: 2)
    """
    p = spec.node_prefix

    checker_id = f"{p}-checker"
    repair_id = f"{p}-repair"
    exit_id = f"{p}-passed"
    blocked_id = f"{p}-blocked"

    nodes = (
        _node(p, "checker", NodeKind.code, LoopStage.verification),
        _node(p, "repair", NodeKind.agent, LoopStage.build_judge),
        _node(p, "passed", NodeKind.code, LoopStage.complete, evidence=()),
        _node(p, "blocked", NodeKind.human, LoopStage.blocked, evidence=()),
    )
    edges = (
        # checker success → passed (exit), checker failure → repair
        _edge(checker_id, exit_id),
        WorkflowEdge(
            id=f"{checker_id}:failure",
            source=checker_id,
            target=repair_id,
            outcome="failure",
        ),
        # repair success → checker (loop back), repair failure → blocked
        _edge(repair_id, checker_id),
        _failure_to_blocked(repair_id),
    )

    # Config is stored in the spec, not in the graph itself — the runtime
    # reads spec.config to know the loop bounds. We include it in the result
    # metadata for consumers.
    return PatternResult(
        nodes=nodes,
        edges=edges,
        entry_node_id=checker_id,
        exit_node_id=exit_id,
    )


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

_BUILBERS: dict[str, Any] = {
    "scatter_gather": build_scatter_gather,
    "competing": build_competing,
    "adversarial": build_adversarial,
    "map_verify_reduce": build_map_verify_reduce,
    "convergence": build_convergence,
}


def build_pattern(spec: PatternSpec) -> PatternResult:
    """Dispatch to the correct builder by ``spec.kind``.

    Raises ``ValueError`` for unknown pattern kinds.
    """
    if spec.kind not in PATTERN_KINDS:
        raise ValueError(
            f"unknown pattern kind {spec.kind!r}. "
            f"Known kinds: {', '.join(sorted(PATTERN_KINDS))}"
        )
    builder = _BUILBERS[spec.kind]
    return builder(spec)


__all__ = [
    "PATTERN_KINDS",
    "PatternResult",
    "PatternSpec",
    "build_adversarial",
    "build_competing",
    "build_convergence",
    "build_map_verify_reduce",
    "build_pattern",
    "build_scatter_gather",
]
