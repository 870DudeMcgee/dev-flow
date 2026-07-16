"""Human-approved template refinements (M7-S2, blueprint §12.5/§13).

The system learns from evidence and proposes template refinements, but humans
approve every change. No self-modifying policies.

Three steps:
1. **Propose** — deterministic heuristics analyze metrics history
2. **Present** — human-readable summary for inspection
3. **Apply** — only with an explicit human approval receipt

Proposing never modifies the library. Even approved refinements produce a new
template version; existing templates are never overwritten.
"""

from __future__ import annotations

import itertools
import json
import os
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from devflow.loop.metrics_aggregator import WorkflowMetrics

_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"
REFINEMENT_APPROVALS_FILE = "refinement-approvals.jsonl"

_refine_counter = itertools.count(1)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class RefinementKind(str, Enum):
    """Type of proposed refinement."""

    budget_adjustment = "budget_adjustment"
    node_addition = "node_addition"
    node_removal = "node_removal"
    phase_reorder = "phase_reorder"


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

class TemplateRefinement(BaseModel):
    """A proposed refinement to a workflow template."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    refinement_id: str = Field(pattern=_ID_PATTERN)
    template_id: str = Field(min_length=1)
    kind: RefinementKind
    description: str = Field(min_length=1)
    rationale: str = ""
    proposed_change: str = ""
    confidence: float = Field(ge=0.0, le=1.0)
    schema_version: Literal[1] = 1


class RefinementApproval(BaseModel):
    """Human approval for a proposed refinement."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    refinement_id: str = Field(pattern=_ID_PATTERN)
    template_id: str = Field(min_length=1)
    status: Literal["pending", "approved", "rejected"]
    actor: str = Field(min_length=1)  # human, never "system"
    decided_at: str | None = None
    reason: str = ""
    schema_version: Literal[1] = 1

    @model_validator(mode="after")
    def reject_system_actor(self) -> "RefinementApproval":
        if self.actor.lower() == "system":
            raise ValueError(
                "refinement approval actor must be a human operator, not 'system'"
            )
        return self


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _refine_id() -> str:
    return f"ref-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{next(_refine_counter):04d}"


def _control_plane_dir(root: Path | str) -> Path:
    return Path(root) / ".devflow" / "control-plane"


def _append_event(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, sort_keys=True) + "\n"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


# ---------------------------------------------------------------------------
# Proposal heuristics
# ---------------------------------------------------------------------------

def propose_refinements(
    template_id: str,
    metrics_history: tuple[WorkflowMetrics, ...],
) -> tuple[TemplateRefinement, ...]:
    """Analyze metrics history and propose refinements.

    Deterministic heuristics:
    - High retry count (> 3 avg) → budget_adjustment (increase repair rounds)
    - Long duration (> 120 min avg) with low retries (< 2) → phase_reorder
    - Frequent human interventions (> 1 avg) → node_addition (review gate)
    - All within norms → empty tuple (no refinements)

    Never modifies the library.
    """
    if not metrics_history:
        return ()

    avg_retries = sum(m.retry_count for m in metrics_history) / len(metrics_history)
    avg_duration_min = sum(m.total_duration_seconds for m in metrics_history) / len(metrics_history) / 60.0
    avg_interventions = sum(m.human_interventions for m in metrics_history) / len(metrics_history)

    refinements: list[TemplateRefinement] = []

    # High retry count → increase repair budget
    if avg_retries > 3:
        refinements.append(TemplateRefinement(
            refinement_id=_refine_id(),
            template_id=template_id,
            kind=RefinementKind.budget_adjustment,
            description=f"Increase max_repair_rounds (avg retries: {avg_retries:.1f})",
            rationale=f"Average retry count {avg_retries:.1f} exceeds threshold of 3.0",
            proposed_change=json.dumps({"field": "max_repair_rounds", "direction": "increase"}),
            confidence=min(0.9, avg_retries / 10.0),
        ))

    # Slow with few retries → parallelization opportunity
    if avg_duration_min > 120 and avg_retries < 2:
        refinements.append(TemplateRefinement(
            refinement_id=_refine_id(),
            template_id=template_id,
            kind=RefinementKind.phase_reorder,
            description=f"Parallelize phases (avg duration: {avg_duration_min:.0f} min)",
            rationale=(
                f"Long duration ({avg_duration_min:.0f} min) with low retries "
                f"({avg_retries:.1f}) suggests sequential bottleneck"
            ),
            proposed_change=json.dumps({"direction": "parallelize"}),
            confidence=0.6,
        ))

    # Frequent interventions → add review gate
    if avg_interventions > 1:
        refinements.append(TemplateRefinement(
            refinement_id=_refine_id(),
            template_id=template_id,
            kind=RefinementKind.node_addition,
            description="Add a review gate node for earlier intervention",
            rationale=(
                f"Average human interventions {avg_interventions:.1f} suggests "
                f"review is needed earlier in the workflow"
            ),
            proposed_change=json.dumps({"node_kind": "human_gate", "position": "pre_integration"}),
            confidence=min(0.85, avg_interventions / 5.0),
        ))

    return tuple(refinements)


# ---------------------------------------------------------------------------
# Approval evaluation
# ---------------------------------------------------------------------------

def can_apply_refinement(
    approval: RefinementApproval,
) -> bool:
    """True only when status == 'approved'."""
    return approval.status == "approved"


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def record_refinement_approval(
    root: Path | str,
    approval: RefinementApproval,
) -> RefinementApproval:
    """Persist approval to ``refinement-approvals.jsonl``.

    Idempotent — replaying the same approval returns it unchanged.
    """
    events_path = _control_plane_dir(root) / REFINEMENT_APPROVALS_FILE

    # Check for duplicate / idempotent
    if events_path.exists():
        for line in events_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                existing = RefinementApproval.model_validate_json(line)
            except Exception:
                continue
            if existing.refinement_id == approval.refinement_id:
                if existing == approval:
                    return existing  # idempotent
                raise ValueError(
                    f"conflicting approval for refinement {approval.refinement_id!r}"
                )

    _append_event(events_path, approval.model_dump(mode="json"))
    return approval


def load_refinement_approvals(
    root: Path | str,
) -> tuple[RefinementApproval, ...]:
    """Load all refinement approvals in append order."""
    events_path = _control_plane_dir(root) / REFINEMENT_APPROVALS_FILE
    if not events_path.is_file():
        return ()

    approvals: list[RefinementApproval] = []
    for line in events_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            approvals.append(RefinementApproval.model_validate_json(line))
        except Exception:
            continue
    return tuple(approvals)


# ---------------------------------------------------------------------------
# Presentation
# ---------------------------------------------------------------------------

def format_refinement_for_display(refinement: TemplateRefinement) -> str:
    """Human-readable Markdown summary for operator inspection."""
    lines: list[str] = ["### Proposed Refinement", ""]
    lines.append(f"- **ID:** `{refinement.refinement_id}`")
    lines.append(f"- **Template:** `{refinement.template_id}`")
    lines.append(f"- **Kind:** {refinement.kind.value}")
    lines.append(f"- **Description:** {refinement.description}")
    lines.append(f"- **Confidence:** {refinement.confidence:.0%}")
    if refinement.rationale:
        lines.append(f"- **Rationale:** {refinement.rationale}")
    lines.append("")
    lines.append("> This refinement requires explicit human approval before it can be applied.")
    return "\n".join(lines)


__all__ = [
    "REFINEMENT_APPROVALS_FILE",
    "RefinementApproval",
    "RefinementKind",
    "TemplateRefinement",
    "can_apply_refinement",
    "format_refinement_for_display",
    "load_refinement_approvals",
    "propose_refinements",
    "record_refinement_approval",
]
