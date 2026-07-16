"""Projection data contract and extraction (M1-S1).

Turns a canonical DevFlow run into a typed ``ProjectionState`` matching the
blueprint's Appendix C run-state structure. This is a *read-only* extractor —
it never mutates canonical state.

Usage::

    from devflow.obsidian.projection import extract_projection

    state = extract_projection(root, run_id)
    print(state.health, state.current_phase, state.progress_percent)

Noncanonical runs return a minimal ``ProjectionState`` with
``extraction_note="not_canonical"``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from devflow.loop.models import LoopStage
from devflow.loop.pipeline_run import pipeline_runs_dir
from devflow.loop.workflow_ledger import (
    DECISION_RECEIPTS_DIR,
    DecisionReceipt,
    WorkflowSnapshot,
    is_canonical_workflow_run,
    rebuild_workflow_snapshot,
)


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------

class RunHealth(str, Enum):
    """Operator-facing health signal, derived deterministically from state."""

    healthy = "Healthy"
    running = "Running"
    repairing = "Repairing"
    awaiting_decision = "Awaiting Decision"
    blocked = "Blocked"
    verification_failed = "Verification Failed"
    completed = "Completed"


# Maps LoopStage to a human-readable phase name for Command Center display.
PHASE_NAMES: dict[LoopStage, str] = {
    LoopStage.idea: "Idea & Brainstorm",
    LoopStage.definition: "Definition",
    LoopStage.spec: "Specification",
    LoopStage.planning: "Planning",
    LoopStage.planning_judge: "Planning Review",
    LoopStage.assignment: "Assignment",
    LoopStage.build_judge: "Build & Judge",
    LoopStage.verification: "Verification",
    LoopStage.human_decision: "Human Decision",
    LoopStage.complete: "Complete",
    LoopStage.blocked: "Blocked",
}


class DecisionSummary(BaseModel):
    """Compact summary of one decision receipt for projection."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    decision_id: str
    decision_type: str
    actor: str
    promotion_eligible: bool
    created_at: str


class ProjectionState(BaseModel):
    """Derived, read-only projection of one canonical run.

    Matches the blueprint's Appendix C run-state structure. Built purely from
    ledger state and decision receipts — no invented data.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str
    workflow_id: str
    health: RunHealth
    current_phase: str
    stage: LoopStage
    progress: float = Field(ge=0.0, le=1.0)
    progress_percent: int = Field(ge=0, le=100)
    completed_node_ids: tuple[str, ...] = ()
    current_node_id: str | None = None
    pending_node_ids: tuple[str, ...] = ()
    blocker_count: int = 0
    decision_count: int = 0
    handoff_count: int = 0
    open_decisions: tuple[DecisionSummary, ...] = ()
    result_branch: str | None = None
    canonical_run_dir: str
    updated_at: str
    extraction_note: str | None = None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _run_dir(root: Path, run_id: str) -> Path:
    return pipeline_runs_dir(root) / run_id


def _load_decision_receipts(run_dir: Path) -> list[DecisionReceipt]:
    """Read all decision receipts from the run's decision-receipts/ dir."""
    receipts_dir = run_dir / DECISION_RECEIPTS_DIR
    if not receipts_dir.is_dir():
        return []

    receipts: list[DecisionReceipt] = []
    for child in sorted(receipts_dir.iterdir()):
        if not child.is_file() or child.suffix != ".json":
            continue
        try:
            receipt = DecisionReceipt.model_validate_json(
                child.read_text(encoding="utf-8")
            )
        except Exception:
            continue
        receipts.append(receipt)
    return receipts


def _has_failure_event(snapshot: WorkflowSnapshot) -> bool:
    """Check if the run has hit a failure edge (routing to blocked)."""
    return snapshot.stage == LoopStage.blocked


def _derive_health(
    snapshot: WorkflowSnapshot,
    decisions: list[DecisionReceipt],
) -> RunHealth:
    """Derive the operator-facing health from snapshot + decisions.

    Deterministic rules (checked in priority order):

    1. blocked                                   → Blocked
    2. complete + accept decision present        → Completed
    3. complete + reject/request_changes         → Blocked (needs rework)
    4. human_decision stage                      → Awaiting Decision
    5. verification stage                        → Running (or Completed if
                                                    accept already recorded)
    6. otherwise                                 → Running
    """
    stage = snapshot.stage

    if stage == LoopStage.blocked:
        return RunHealth.blocked

    if stage == LoopStage.complete:
        accept_decisions = [
            d for d in decisions if d.decision_type.value == "accept"
        ]
        if accept_decisions:
            return RunHealth.completed
        return RunHealth.blocked

    if stage == LoopStage.human_decision:
        return RunHealth.awaiting_decision

    return RunHealth.running


def _has_result_branch(repo: Path, run_id: str) -> str | None:
    """Check if refs/heads/devflow/results/<run_id> exists. Return ref or None."""
    ref = f"refs/heads/devflow/results/{run_id}"
    try:
        import subprocess

        result = subprocess.run(
            ["git", "show-ref", "--verify", "--quiet", ref],
            cwd=str(repo),
            capture_output=True,
            timeout=5,
        )
        return ref if result.returncode == 0 else None
    except Exception:
        return None


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_projection(root: Path | str, run_id: str) -> ProjectionState:
    """Extract the Command Center projection for one run.

    For canonical runs, derives health/phase/progress from the ledger read
    model and decision receipts. For noncanonical runs, returns a minimal
    state with ``extraction_note="not_canonical"``.

    Never mutates canonical state — reads only.
    """
    root_path = Path(root).resolve()
    run_dir = _run_dir(root_path, run_id)

    if not is_canonical_workflow_run(root_path, run_id):
        return ProjectionState(
            run_id=run_id,
            workflow_id="unknown",
            health=RunHealth.healthy,
            current_phase="Unknown",
            stage=LoopStage.idea,
            progress=0.0,
            progress_percent=0,
            canonical_run_dir=str(run_dir),
            updated_at=_now_iso(),
            extraction_note="not_canonical",
        )

    snapshot = rebuild_workflow_snapshot(root_path, run_id)
    decisions = _load_decision_receipts(run_dir)
    health = _derive_health(snapshot, decisions)

    from devflow.loop.read_model import derive_canonical_run_model

    model = derive_canonical_run_model(snapshot, run_id)

    decision_summaries = tuple(
        DecisionSummary(
            decision_id=d.decision_id,
            decision_type=d.decision_type.value,
            actor=d.actor,
            promotion_eligible=d.promotion_eligible,
            created_at=d.created_at.isoformat() if hasattr(d.created_at, "isoformat") else str(d.created_at),
        )
        for d in decisions
    )

    result_branch = _has_result_branch(root_path, run_id)

    return ProjectionState(
        run_id=run_id,
        workflow_id=snapshot.workflow_id,
        health=health,
        current_phase=PHASE_NAMES.get(snapshot.stage, snapshot.stage.value),
        stage=snapshot.stage,
        progress=model.progress,
        progress_percent=round(model.progress * 100),
        completed_node_ids=model.completed_node_ids,
        current_node_id=model.current_node_id if not model.is_terminal else None,
        pending_node_ids=model.pending_node_ids,
        blocker_count=1 if health in (RunHealth.blocked, RunHealth.verification_failed) else 0,
        decision_count=len(decisions),
        handoff_count=1 if health == RunHealth.completed else 0,
        open_decisions=decision_summaries,
        result_branch=result_branch,
        canonical_run_dir=str(run_dir),
        updated_at=_now_iso(),
    )


__all__ = [
    "DecisionSummary",
    "PHASE_NAMES",
    "ProjectionState",
    "RunHealth",
    "extract_projection",
]
