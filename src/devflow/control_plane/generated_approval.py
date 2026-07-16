"""Resource estimation + visible approval gate for generated workflows (M6-S2).

Three separate steps:
1. **Estimate** — deterministic cost/risk assessment of the generated graph
2. **Present** — human-readable summary for inspection
3. **Approve** — explicit human decision required; no self-escalation

Authority is structurally capped: ``authority_capped`` is always ``True``,
``can_execute()`` requires both approval and cap, and ``actor`` can never be
``"system"``.

Blueprint §6.3 (authority boundaries), §12.5 (generated workflows).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from devflow.loop.workflow_definition import NodeKind
from devflow.loop.workflow_schema import (
    WorkflowSchemaV2,
    WorkflowStrategy,
)

_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"
APPROVAL_EVENTS_DIR = "generated-approvals"
APPROVAL_EVENTS_FILE = "approval-events.jsonl"


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

class ResourceEstimate(BaseModel):
    """Deterministic cost/risk estimate for a generated workflow."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    generation_id: str = Field(pattern=_ID_PATTERN)
    estimated_duration_minutes: int = Field(ge=1)
    estimated_agent_runs: int = Field(ge=1)
    estimated_heavy_model_hours: float = Field(ge=0.0)
    risk_level: Literal["low", "medium", "high"]
    risk_factors: tuple[str, ...] = ()
    authority_capped: bool = True  # always True — cannot self-escalate


class GeneratedApproval(BaseModel):
    """Human approval state for a generated workflow."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    generation_id: str = Field(pattern=_ID_PATTERN)
    ticket_id: str = Field(pattern=_ID_PATTERN)
    workflow_id: str = Field(min_length=1)
    status: Literal["pending", "approved", "rejected"]
    actor: str = Field(min_length=1)  # human operator, never "system"
    decided_at: str | None = None
    reason: str = ""
    schema_version: Literal[1] = 1

    @model_validator(mode="after")
    def reject_system_actor(self) -> "GeneratedApproval":
        if self.actor.lower() == "system":
            raise ValueError(
                "generated approval actor must be a human operator, not 'system'"
            )
        return self


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _control_plane_dir(root: Path | str) -> Path:
    return Path(root) / ".devflow" / "control-plane"


def _approval_dir(root: Path | str) -> Path:
    return _control_plane_dir(root) / APPROVAL_EVENTS_DIR


def _append_event(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, sort_keys=True) + "\n"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


# ---------------------------------------------------------------------------
# Resource estimation
# ---------------------------------------------------------------------------

def estimate_resources(
    workflow: WorkflowSchemaV2,
    generation_id: str,
) -> ResourceEstimate:
    """Estimate duration, agent runs, heavy-model hours, and risk.

    Deterministic — reads node count, kinds, budget, and strategy.
    """
    nodes = workflow.nodes
    node_count = len(nodes)

    # Count node kinds
    gate_count = sum(1 for n in nodes if n.kind in (NodeKind.gate, NodeKind.human_gate))
    agent_count = sum(1 for n in nodes if n.kind == NodeKind.agent)
    code_count = sum(1 for n in nodes if n.kind == NodeKind.code)
    is_dag = workflow.strategy == WorkflowStrategy.dag

    # Duration estimate: agents are expensive, code is fast
    estimated_minutes = max(1, agent_count * 10 + code_count * 2 + gate_count * 5)

    # Agent runs: each agent node runs once + some retries
    estimated_runs = max(1, agent_count + (node_count // 3))

    # Heavy model hours: only if deep_planning or frontier_judgment routes are implied
    heavy_hours = round(max(0.0, (agent_count * 5.0) / 60.0), 2)

    # Risk assessment
    risk_factors: list[str] = []
    if node_count > 12:
        risk_factors.append("large node count")
        risk_level: str = "high"
    elif is_dag and node_count > 6:
        risk_factors.append("DAG strategy with moderate complexity")
        risk_level = "high"
    elif gate_count > 0 or estimated_minutes > 60:
        if estimated_minutes > 180:
            risk_factors.append("long estimated duration")
            risk_level = "high"
        else:
            risk_factors.append("includes gates or moderate duration")
            risk_level = "medium"
    else:
        risk_level = "low"

    return ResourceEstimate(
        generation_id=generation_id,
        estimated_duration_minutes=estimated_minutes,
        estimated_agent_runs=estimated_runs,
        estimated_heavy_model_hours=heavy_hours,
        risk_level=risk_level,  # type: ignore[arg-type]
        risk_factors=tuple(risk_factors),
        authority_capped=True,
    )


# ---------------------------------------------------------------------------
# Approval evaluation
# ---------------------------------------------------------------------------

def approval_required(workflow_id: str) -> bool:
    """True for any generated workflow.

    Fixed/parameterized templates have pre-approved IDs from the library and
    don't need generated-workflow approval.
    """
    return workflow_id.startswith("generated:")


def can_execute(
    approval: GeneratedApproval,
    estimate: ResourceEstimate,
) -> bool:
    """True only when approved AND authority capped."""
    if approval.generation_id != estimate.generation_id:
        return False
    if approval.status != "approved":
        return False
    if not estimate.authority_capped:
        return False
    return True


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def record_approval(
    root: Path | str,
    approval: GeneratedApproval,
) -> GeneratedApproval:
    """Persist approval to ``generated-approvals/approval-events.jsonl``.

    Idempotent — replaying the same approval returns it unchanged.
    """
    events_path = _approval_dir(root) / APPROVAL_EVENTS_FILE

    # Check for duplicate / idempotent
    if events_path.exists():
        for line in events_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                existing = GeneratedApproval.model_validate_json(line)
            except Exception:
                continue
            if existing.generation_id == approval.generation_id:
                if existing == approval:
                    return existing  # idempotent
                raise ValueError(
                    f"conflicting approval for generation {approval.generation_id!r}"
                )

    _append_event(events_path, approval.model_dump(mode="json"))
    return approval


def load_approvals(
    root: Path | str,
) -> tuple[GeneratedApproval, ...]:
    """Load all approvals in append order."""
    events_path = _approval_dir(root) / APPROVAL_EVENTS_FILE
    if not events_path.is_file():
        return ()

    approvals: list[GeneratedApproval] = []
    for line in events_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            approvals.append(GeneratedApproval.model_validate_json(line))
        except Exception:
            continue
    return tuple(approvals)


# ---------------------------------------------------------------------------
# Presentation
# ---------------------------------------------------------------------------

def format_estimate_for_display(estimate: ResourceEstimate) -> str:
    """Human-readable Markdown summary of the estimate for operator inspection."""
    lines: list[str] = ["### Resource Estimate", ""]
    lines.append(f"- **Estimated duration:** {estimate.estimated_duration_minutes} minutes")
    lines.append(f"- **Estimated agent runs:** {estimate.estimated_agent_runs}")
    lines.append(f"- **Heavy model hours:** {estimate.estimated_heavy_model_hours:.2f}h")
    lines.append(f"- **Risk level:** **{estimate.risk_level}**")
    if estimate.risk_factors:
        lines.append(f"- **Risk factors:** {', '.join(estimate.risk_factors)}")
    lines.append("- **Authority capped:** yes (cannot self-escalate)")
    lines.append("")
    lines.append("> Generated workflows require explicit human approval before execution.")
    return "\n".join(lines)


__all__ = [
    "APPROVAL_EVENTS_DIR",
    "APPROVAL_EVENTS_FILE",
    "GeneratedApproval",
    "ResourceEstimate",
    "approval_required",
    "can_execute",
    "estimate_resources",
    "format_estimate_for_display",
    "load_approvals",
    "record_approval",
]
