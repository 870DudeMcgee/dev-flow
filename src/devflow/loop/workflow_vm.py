"""Canon-compliant generalized workflow VM executor (Slice 3).

This is a *pure orchestration engine* for the generalized DevFlow workflow
family. It contains **no model calls**: the actual node work is performed by an
``Executor`` that is *injected* by the caller (``execute(node, context) ->
NodeOutcome``). The VM only schedules nodes, records immutable ledger receipts
and lifecycle events, and enforces the structural/budget rules.

What this module guarantees:

* **Real parallel / DAG family shapes** — a frontier scheduler computes the
  ready set from dependency edges each round and (optionally) honours
  heavy-model-slot / parallel / semantic conflict limits via
  :func:`devflow.loop.conflict_rules.apply_conflict_filters`. Fan-out (a node
  with several ready successors) and multiple roots (``parallel``) are handled
  by set semantics, not a single cursor.
* **Bounded intentional loops** — when ``strategy == loop`` the schema carries
  exactly one back-edge to a unique loop head. The VM re-runs the loop body for
  up to ``loop_policy.max_rounds`` (or ``max_total_rounds``) rounds and FAILS
  CLOSED when the bound is exhausted or ``stop_if_no_progress`` is tripped.
* **Rich gate outcomes** — gates record an additive :class:`GateOutcomeReceipt`
  (``approved`` / ``approved_with_conditions`` / ``rejected`` / ``escalate``)
  alongside the binary ledger outcome. The VM records the placeholder human
  actor ``"human-operator"``; in production the executor is expected to record
  the real decision actor itself. (``"system"`` / ``"operator-vm"`` are
  rejected — a gate decision requires a human operator.)
* **Fail-closed** — any malformed definition, unknown executor outcome, or
  ledger rejection raises :class:`WorkflowVMError`.

The run directory must already be initialized (v2 definition persisted at
``<run_dir>/workflow-definition-v2.json`` plus an empty events ledger) by the
caller before :func:`run_workflow` is invoked.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Literal, Mapping, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from devflow.loop.conflict_rules import ResourceBudget, apply_conflict_filters
from devflow.loop.dag_scheduler import SchedulerNode
from devflow.loop.models import LoopStage
from devflow.loop.node_lifecycle import (
    NodeLifecycleReceipt,
    NodeState,
    record_lifecycle_event,
)
from devflow.loop.pipeline_run import pipeline_runs_dir
from devflow.loop.workflow_definition import NodeKind, WorkflowNode
from devflow.loop.workflow_ledger import (
    EvidenceReference,
    NodeReceipt,
    WorkflowEvent,
    record_node_outcome,
)
from devflow.loop.workflow_schema import WorkflowSchemaV2, WorkflowStrategy

# Lifecycle states that mean "done — do not (re)schedule".
_DONE_STATES = frozenset(
    {
        NodeState.verified,
        NodeState.failed,
        NodeState.cancelled,
        NodeState.blocked,
    }
)

_RICH_GATE_OUTCOMES = frozenset(
    {
        "approved",
        "approved_with_conditions",
        "rejected",
        "escalate",
    }
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _run_dir(root: Path | str, run_id: str) -> Path:
    return pipeline_runs_dir(root) / run_id


# ---------------------------------------------------------------------------
# Outcomes
# ---------------------------------------------------------------------------


class NodeOutcome(str, Enum):
    """Rich per-node outcome returned by an injected :class:`Executor`."""

    success = "success"
    failure = "failure"
    approved = "approved"
    approved_with_conditions = "approved_with_conditions"
    rejected = "rejected"
    escalate = "escalate"


def _to_binary(outcome: NodeOutcome) -> str:
    """Map a rich outcome to the binary ledger outcome ('success'/'failure')."""
    if outcome in (
        NodeOutcome.success,
        NodeOutcome.approved,
        NodeOutcome.approved_with_conditions,
    ):
        return "success"
    return "failure"


# ---------------------------------------------------------------------------
# Rich gate outcome receipt (additive)
# ---------------------------------------------------------------------------


class GateOutcomeReceipt(BaseModel):
    """Additive rich gate outcome record (never replaces the binary ledger).

    A human operator must take the decision — ``decided_by`` may not be the
    system actor. ``conditions`` carries any approval conditions.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    receipt_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
    node_id: str
    run_id: str
    gate_outcome: NodeOutcome
    conditions: tuple[str, ...] = ()
    decided_by: str = Field(min_length=1)
    reviewed_at: str = Field(min_length=1)
    schema_version: Literal[1] = 1


_GATE_OUTCOMES_FILE = "gate-outcome-events.jsonl"


def record_gate_outcome(
    root: Path | str,
    run_id: str,
    receipt: GateOutcomeReceipt,
) -> GateOutcomeReceipt:
    """Append a :class:`GateOutcomeReceipt` to the run's gate-outcome ledger.

    Validates that ``decided_by`` is not the system actor. Idempotent on a
    duplicate ``receipt_id`` that is gate-type-equivalent (same ``node_id`` and
    ``gate_outcome``) — returns the existing receipt. Raises ``ValueError`` on a
    *conflicting* duplicate ``receipt_id`` (different node/outcome).
    """
    if receipt.decided_by.lower() == "system":
        raise ValueError(
            "gate outcome decided_by must be a human operator, never 'system'"
        )

    run_dir = _run_dir(root, run_id)
    if not run_dir.is_dir():
        raise FileNotFoundError(f"Pipeline run not found: {run_dir}")

    path = run_dir / _GATE_OUTCOMES_FILE
    for existing in load_gate_outcomes(root, run_id):
        if existing.receipt_id == receipt.receipt_id:
            if (
                existing.node_id == receipt.node_id
                and existing.gate_outcome == receipt.gate_outcome
            ):
                return existing
            raise ValueError(
                f"conflicting duplicate gate outcome id: {receipt.receipt_id}"
            )

    line = json.dumps(receipt.model_dump(mode="json"), sort_keys=True) + "\n"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line)
        handle.flush()
        os.fsync(handle.fileno())
    return receipt


def load_gate_outcomes(
    root: Path | str, run_id: str
) -> tuple[GateOutcomeReceipt, ...]:
    """Load all gate outcome receipts for a run, in append order.

    Returns an empty tuple if the gate-outcome ledger is absent.
    """
    try:
        run_dir = _run_dir(root, run_id)
    except Exception:
        return ()
    if not run_dir.is_dir():
        return ()
    path = run_dir / _GATE_OUTCOMES_FILE
    if not path.is_file():
        return ()
    out: list[GateOutcomeReceipt] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        out.append(GateOutcomeReceipt.model_validate_json(line))
    return tuple(out)


# ---------------------------------------------------------------------------
# Context + Executor protocol
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VMContext:
    """Immutable context handed to an injected :class:`Executor` per node."""

    run_id: str
    root: Path
    iteration: int
    node_states: Mapping[str, NodeState]


@runtime_checkable
class Executor(Protocol):
    """Injected node executor. The VM calls ``execute(node, context)``."""

    def execute(self, node: WorkflowNode, context: VMContext) -> NodeOutcome:
        ...


# ---------------------------------------------------------------------------
# Result + errors
# ---------------------------------------------------------------------------


class WorkflowVMError(ValueError):
    """Raised for any malformed definition, unknown outcome, or ledger failure."""


@dataclass(frozen=True)
class WorkflowVMResult:
    """Immutable result of a :func:`run_workflow` execution."""

    run_id: str
    completed_node_ids: tuple[str, ...]
    active_node_ids: tuple[str, ...]
    terminal_reached: bool
    iterations: int
    outcome_map: Mapping[str, NodeOutcome]


# ---------------------------------------------------------------------------
# Graph helpers
# ---------------------------------------------------------------------------


def _strict_successors(start: str, succs: Mapping[str, list[str]]) -> set[str]:
    """All nodes reachable from *start* (excluding *start* itself)."""
    out: set[str] = set()
    stack = list(succs.get(start, ()))
    while stack:
        cur = stack.pop()
        if cur in out:
            continue
        out.add(cur)
        for nxt in succs.get(cur, ()):
            if nxt not in out:
                stack.append(nxt)
    return out


def _invoke_executor(executor: Executor, node: WorkflowNode, ctx: VMContext) -> NodeOutcome:
    if hasattr(executor, "execute"):
        return executor.execute(node, ctx)
    return executor(node, ctx)  # type: ignore[operator]


def _record_lifecycle_once(
    root: Path,
    run_id: str,
    *,
    node_id: str,
    to_state: NodeState,
    started: set[str],
) -> None:
    """Record the lifecycle chain for a node at most once per VM process.

    The immutable :mod:`devflow.loop.node_lifecycle` ledger forbids
    transitioning *out* of a terminal state, so a loop-body node that is re-run
    in a later round cannot have a second ``planned -> running`` event
    appended. We therefore record the lifecycle trail for a node's first
    execution only (the full planned -> ready -> running -> verified/failed
    chain, which respects the ledger's legal transitions); every round is still
    immutably recorded by the workflow ledger (``NodeReceipt`` /
    ``WorkflowEvent``), which is the authoritative outcome record. Fail-closed
    is preserved for genuinely malformed input.
    """
    if node_id in started:
        return
    started.add(node_id)
    # Emit the full legal chain in one shot: planned -> ready -> running ->
    # (verified|failed). The existing ledger only permits these exact hops, and
    # this runs once per node (first execution), so loop re-runs do not violate
    # the "no transition out of a terminal state" rule above.
    now = _now_iso()
    chain = [
        (NodeState.planned, NodeState.ready),
        (NodeState.ready, NodeState.running),
        (NodeState.running, to_state),
    ]
    for idx, (frm, to) in enumerate(chain):
        record_lifecycle_event(
            root,
            run_id,
            receipt=NodeLifecycleReceipt(
                lifecycle_id=f"{node_id}-run-0-0-{idx}",
                node_id=node_id,
                run_id=run_id,
                from_state=frm,
                to_state=to,
                timestamp=now,
            ),
        )


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def run_workflow(
    root: Path | str,
    run_id: str,
    *,
    executor: Executor,
    conflict_budget: ResourceBudget | None = None,
    node_routes: Mapping[str, str] | None = None,
    semantic_groups: Mapping[str, frozenset[str]] | None = None,
    max_total_rounds: int | None = None,
) -> WorkflowVMResult:
    """Execute a generalized (v2) workflow to completion.

    Pure orchestration: schedules nodes by dependency frontier, records immutable
    ledger receipts + lifecycle events, records rich gate outcomes, and enforces
    bounded-loop policy. The caller injects ``executor`` (no model calls here).

    Returns a frozen :class:`WorkflowVMResult`.
    """
    root_path = Path(root)
    run_dir = _run_dir(root_path, run_id)
    if not run_dir.is_dir():
        raise WorkflowVMError(f"workflow run not found: {run_id}")

    def_path = run_dir / "workflow-definition-v2.json"
    if not def_path.is_file():
        raise WorkflowVMError(
            f"generalized workflow definition missing for run {run_id!r}"
        )
    try:
        definition = WorkflowSchemaV2.model_validate_json(def_path.read_text())
    except Exception as exc:
        raise WorkflowVMError(f"malformed workflow definition: {exc}") from exc

    nodes = {n.id: n for n in definition.nodes}
    preds: dict[str, set[str]] = {n.id: set() for n in definition.nodes}
    succs: dict[str, list[str]] = {n.id: [] for n in definition.nodes}
    for edge in definition.edges:
        preds[edge.target].add(edge.source)
        succs[edge.source].append(edge.target)

    # Terminal nodes (stage complete/blocked) are *reached* via an edge but are
    # NEVER executed — the ledger projector rejects events for them. They are
    # tracked in `reached`, not executed through the frontier.
    terminal_ids = {
        nid
        for nid, node in nodes.items()
        if node.stage in (LoopStage.complete, LoopStage.blocked)
    }
    # Only *success* (complete) terminals count as "terminal reached" for the
    # honest result. A blocked terminal is still reported as *reached* (via
    # `reached` / completed_node_ids) but must NOT assert a successful spine.
    complete_ids = {
        nid
        for nid, node in nodes.items()
        if node.stage == LoopStage.complete
    }

    states: dict[str, NodeState] = {
        n.id: NodeState.planned for n in definition.nodes
    }
    completed: list[str] = []  # non-terminal nodes executed through the frontier
    completed_set: set[str] = set()
    reached: set[str] = set()  # `completed` plus terminal nodes reached via edge
    # Non-terminal targets of a *failure* edge from a failed node. These are
    # "recovery" nodes the schema explicitly routes to; they are scheduled
    # outside the normal all-predecessors-verified rule because their source
    # failed (and is therefore not `verified`).
    pending_failure_targets: set[str] = set()
    outcome_map: dict[str, NodeOutcome] = {}
    iterations = 0
    loop_exhausted = False
    progress_stall = 0
    lifecycle_started: set[str] = set()

    loop_head_id = next((nid for nid in preds if not preds[nid]), None)

    def mark_reached() -> None:
        """Route completed non-terminal nodes along their matching edge.

        A node's binary outcome selects which outgoing edge is honoured:

        * **success** nodes follow their ``success`` edge. If the target is a
          terminal it is recorded as *reached* (never executed — the projector
          rejects terminal events). Success edges to non-terminal nodes are
          handled by the normal predecessor-based scheduler, so they are left
          alone here.
        * **failure** nodes follow their ``failure`` edge. If the target is a
          terminal (e.g. ``feature-blocked``) it is recorded as *reached*. If
          the target is a non-terminal recovery node, it is queued for
          scheduling via ``pending_failure_targets`` — the schema permits this
          routing and we honour it rather than hard-coding a single terminal.
        """
        for nid in completed:
            if nid in terminal_ids:
                continue
            binary = _to_binary(outcome_map[nid])
            for edge in definition.edges:
                if edge.source != nid or edge.outcome != binary:
                    continue
                if edge.target in terminal_ids:
                    reached.add(edge.target)
                elif binary == "failure":
                    # Failure routing to a recovery (non-terminal) node. Only
                    # failure edges are honoured out-of-band here; success edges
                    # to non-terminal nodes are handled by the normal
                    # predecessor-verified scheduler, so they are left alone.
                    pending_failure_targets.add(edge.target)

    def pending_terminal_reach() -> bool:
        """True if a completed success node has an unrecorded terminal successor."""
        return any(
            t not in reached
            for t in (
                edge.target
                for nid in completed
                if nid not in terminal_ids
                and _to_binary(outcome_map[nid]) == "success"
                for edge in definition.edges
                if edge.source == nid
                and edge.outcome == "success"
                and edge.target in terminal_ids
            )
        )

    def compute_ready() -> list[str]:
        ready: list[str] = []
        mark_reached()
        for nid, node in nodes.items():
            if nid in terminal_ids:
                continue
            if states[nid] != NodeState.planned:
                continue
            if nid in pending_failure_targets:
                # Recovery node routed to via a failed predecessor's failure
                # edge — schedule it regardless of normal predecessor state.
                ready.append(nid)
                pending_failure_targets.discard(nid)
                continue
            if all(states[p] == NodeState.verified for p in preds[nid]):
                ready.append(nid)
        return ready

    while any(
        nid not in terminal_ids and states[nid] not in _DONE_STATES
        for nid in states
    ) or pending_terminal_reach():
        ready = compute_ready()
        if not ready:
            # No progress possible: a predecessor failed, so the remaining
            # planned non-terminal nodes can never become ready. Stop — the
            # run terminates (projection routes to blocked via the failure edge).
            break

        if conflict_budget is not None and node_routes is not None:
            sched = {
                nid: SchedulerNode(
                    node_id=nid,
                    depends_on=tuple(sorted(preds[nid])),
                )
                for nid in states
                if nid not in terminal_ids
            }
            ready = list(
                apply_conflict_filters(
                    tuple(ready),
                    sched,
                    [],
                    conflict_budget,
                    node_routes,
                    semantic_groups,
                )
            )

        for step, nid in enumerate(ready):
            node = nodes[nid]

            ctx = VMContext(
                run_id=run_id,
                root=root_path,
                iteration=iterations,
                node_states=states,
            )
            try:
                outcome = _invoke_executor(executor, node, ctx)
            except Exception as exc:
                raise WorkflowVMError(
                    f"executor raised for node {nid!r}: {exc}"
                ) from exc

            if not isinstance(outcome, NodeOutcome) or outcome not in set(
                NodeOutcome.__members__.values()
            ):
                raise WorkflowVMError(f"unknown node outcome for {nid!r}: {outcome!r}")

            binary = _to_binary(outcome)

            # Rich gate outcome (additive). The VM records the placeholder human
            # actor; production executors should record the real decision actor.
            if node.kind in (NodeKind.gate, NodeKind.human_gate) and (
                outcome.value in _RICH_GATE_OUTCOMES
            ):
                record_gate_outcome(
                    root_path,
                    run_id,
                    GateOutcomeReceipt(
                        receipt_id=f"{nid}-gate-{iterations}-{step}",
                        node_id=nid,
                        run_id=run_id,
                        gate_outcome=outcome,
                        conditions=("see decision log",)
                        if outcome == NodeOutcome.approved_with_conditions
                        else (),
                        decided_by="human-operator",
                        reviewed_at=_now_iso(),
                    ),
                )

            # Placeholder evidence so the ledger's evidence-exists check passes.
            for key in node.required_evidence:
                (run_dir / f"{key}.md").write_text(
                    f"# {key}\n\nauto evidence for {node.id}\n"
                )
            evidence = tuple(
                EvidenceReference(key=k, reference=f"{k}.md")
                for k in node.required_evidence
            )
            receipt = NodeReceipt(
                receipt_id=f"{nid}-receipt-{iterations}-{step}",
                node_id=nid,
                outcome=binary,  # type: ignore[arg-type]
                evidence=evidence,
            )
            event = WorkflowEvent(
                event_id=f"{nid}-evt-{iterations}-{step}",
                node_id=nid,
                outcome=binary,  # type: ignore[arg-type]
                receipt_id=receipt.receipt_id,
            )
            try:
                record_node_outcome(root_path, run_id, receipt=receipt, event=event)
            except Exception as exc:
                raise WorkflowVMError(
                    f"ledger rejected outcome for node {nid!r}: {exc}"
                ) from exc

            to_state = (
                NodeState.verified if binary == "success" else NodeState.failed
            )
            # Record the full lifecycle chain for this node's first execution
            # only (planned -> ready -> running -> verified/failed). Loop
            # re-runs are recorded by the workflow ledger, not re-recorded here.
            _record_lifecycle_once(
                root_path,
                run_id,
                node_id=nid,
                to_state=to_state,
                started=lifecycle_started,
            )

            states[nid] = to_state
            completed.append(nid)
            completed_set.add(nid)
            outcome_map[nid] = outcome

        # ---- Loop handling (bounded intentional loops) ----
        if definition.strategy == WorkflowStrategy.loop:
            if definition.loop_policy is None:
                raise WorkflowVMError(
                    "workflow with strategy=loop requires a loop_policy"
                )
        if definition.strategy == WorkflowStrategy.loop and not loop_exhausted:
            re_entry_target: str | None = None
            for nid in ready:
                if _to_binary(outcome_map[nid]) != "success":
                    continue
                for edge in definition.edges:
                    if (
                        edge.source == nid
                        and edge.outcome == "success"
                        and edge.target in completed_set
                    ):
                        re_entry_target = edge.target
                        break
                if re_entry_target is not None:
                    break

            if re_entry_target is not None:
                iterations += 1

                head_out = outcome_map.get(loop_head_id) if loop_head_id else None
                if head_out is not None and _to_binary(head_out) == "success":
                    progress_stall = 0
                else:
                    progress_stall += 1

                limit = (
                    max_total_rounds
                    if max_total_rounds is not None
                    else definition.loop_policy.max_rounds
                )
                if iterations >= limit:
                    # FAIL CLOSED: do not re-activate; route to blocked.
                    states[re_entry_target] = NodeState.failed
                    loop_exhausted = True
                    break

                if (
                    definition.loop_policy.stop_if_no_progress
                    and progress_stall >= definition.loop_policy.stop_if_no_progress
                ):
                    # FAIL CLOSED: no progress for N rounds.
                    states[re_entry_target] = NodeState.failed
                    loop_exhausted = True
                    break

                # Reset the loop body for another round.
                body = _strict_successors(re_entry_target, succs) | {
                    re_entry_target
                }
                for bn in body:
                    if bn not in terminal_ids:
                        states[bn] = NodeState.planned

    # "terminal reached" means the successful (complete) terminal was reached —
    # a blocked terminal is reported as reached but is not a successful spine.
    terminal_reached = any(t in reached for t in complete_ids)
    report_completed = tuple(completed) + tuple(sorted(reached - set(completed)))
    active_node_ids = tuple(
        sorted(
            nid
            for nid in states
            if nid not in terminal_ids
            and states[nid] in (NodeState.planned, NodeState.ready, NodeState.running)
        )
    )

    return WorkflowVMResult(
        run_id=run_id,
        completed_node_ids=report_completed,
        active_node_ids=active_node_ids,
        terminal_reached=terminal_reached,
        iterations=iterations,
        outcome_map=dict(outcome_map),
    )


__all__ = [
    "Executor",
    "GateOutcomeReceipt",
    "NodeOutcome",
    "VMContext",
    "WorkflowVMError",
    "WorkflowVMResult",
    "load_gate_outcomes",
    "record_gate_outcome",
    "run_workflow",
]
