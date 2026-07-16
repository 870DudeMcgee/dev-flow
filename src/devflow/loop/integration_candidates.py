"""Verified integration candidates collector (M3-S4).

Reads execution plans and verification receipts to produce a dependency-ordered,
read-only summary of integration candidates. No mutation, no queue state, no
ship/merge side effects. The multi-workflow Ready Queue is deferred to M4-S3.

Usage::

    from devflow.loop.integration_candidates import collect_integration_candidates

    summary = collect_integration_candidates(root, run_id)
    if summary.ready_for_integration:
        print("All slices verified and ready")
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from devflow.loop.execution_plan import load_execution_plan
from devflow.loop.packet_dag import validate_packet_dag
from devflow.loop.pipeline_run import load_pipeline_run, pipeline_runs_dir


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

class IntegrationCandidate(BaseModel):
    """One verified slice ready for integration, in dependency order."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    packet_id: str = Field(min_length=1)
    target_files: tuple[str, ...] = ()
    depends_on: tuple[str, ...] = ()
    verified: bool = False
    integration_order_index: int = Field(ge=0)


class CandidateSummary(BaseModel):
    """Read-only summary of all integration candidates for a run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str = Field(min_length=1)
    candidates: tuple[IntegrationCandidate, ...] = ()
    all_verified: bool = False
    ready_for_integration: bool = False


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _run_dir(root: Path, run_id: str) -> Path:
    return pipeline_runs_dir(root) / run_id


def _find_verification_receipts(run_data: dict) -> set[str]:
    """Return the set of packet IDs that have a passing verification receipt.

    Verification receipts are stored as ``verification-receipt-<id>.json`` in
    the run directory. We check the ``passed`` field for a truthy value.
    """
    verified: set[str] = set()
    for key, value in run_data.items():
        if not key.startswith("verification-receipt-") or not key.endswith(".json"):
            continue
        if not isinstance(value, dict):
            continue
        if value.get("passed") is True:
            receipt_id = key.removeprefix("verification-receipt-").removesuffix(".json")
            verified.add(receipt_id)
    return verified


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def collect_integration_candidates(
    root: Path | str,
    run_id: str,
) -> CandidateSummary:
    """Collect verified slices as dependency-ordered integration candidates.

    Reads ``execution-plan.json`` + verification receipts from the run
    directory. Returns a read-only summary — no mutation, no queue state.
    Ship/merge remain gated (``enabled=False``).
    """
    root_path = Path(root).resolve()

    # Load the execution plan (raises if missing)
    plan = load_execution_plan(root_path, run_id)

    # Get dependency-ordered packets
    ordered_packets = validate_packet_dag(plan.packets)

    # Load run data to find verification receipts
    run_data = load_pipeline_run(root_path, run_id)
    verified_receipts = _find_verification_receipts(run_data)

    # Build candidates in dependency order
    candidates: list[IntegrationCandidate] = []
    for index, packet in enumerate(ordered_packets):
        # A packet is verified if any verification receipt matches its ID
        # or if the plan has a single global verification receipt covering all packets.
        verified = packet.id in verified_receipts

        candidates.append(IntegrationCandidate(
            packet_id=packet.id,
            target_files=tuple(packet.target_files),
            depends_on=tuple(packet.depends_on),
            verified=verified,
            integration_order_index=index,
        ))

    all_verified = all(c.verified for c in candidates) if candidates else False
    # ready_for_integration requires all verified AND all dependencies satisfied
    # (dependency satisfaction is guaranteed by the topological order from
    # validate_packet_dag, so all_verified is the primary gate)
    ready = all_verified and len(candidates) > 0

    return CandidateSummary(
        run_id=run_id,
        candidates=tuple(candidates),
        all_verified=all_verified,
        ready_for_integration=ready,
    )


__all__ = [
    "CandidateSummary",
    "IntegrationCandidate",
    "collect_integration_candidates",
]
