"""Orient/Scout adapter — wraps scout_discovery into the v2 loop spine.

This module provides the orient step: scout discovery runs, evidence is
recorded into the pipeline run, and the loop state advances from idea to
definition when the discovery is ready to proceed.

Imported surfaces (and NOT modified):
  - devflow.control_room.scout_discovery
  - devflow.loop.adapter
  - devflow.loop.models
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from devflow.control_room.scout_discovery import AgentScoutDiscovery
from devflow.control_room.scout_discovery import (
    discover_agent_scout_context,
)
from devflow.loop.adapter import load_loop_state, save_loop_state
from devflow.loop.models import (
    advance_stage,
    DevFlowLoopState,
    LoopStage,
)
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# OrientResult
# ---------------------------------------------------------------------------
class OrientResult(BaseModel):
    """Compact result from one orient/scout discovery run."""

    run_id: str
    stage: str = Field(description="Current loop stage name")
    lane: str = Field(description="Recommended lane from discovery")
    files_to_touch: list[str] = Field(default_factory=list)
    files_to_read_next: list[dict[str, str]] = Field(default_factory=list)
    tests: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    verification: str = ""
    map_confidence: str = "unknown"
    context_brief: list[dict] = Field(default_factory=list)
    ready: bool = Field(
        description="True when orientation is sufficient to advance"
    )

    @classmethod
    def from_discovery(cls, discovery: AgentScoutDiscovery, *, run_id: str) -> "OrientResult":
        """Build an OrientResult from an AgentScoutDiscovery."""
        return cls(
            run_id=run_id,
            stage="idea",  # orient only runs from idea stage
            lane=discovery.recommended_lane,
            files_to_touch=list(discovery.files_to_touch),
            files_to_read_next=list(discovery.files_to_read_next),
            tests=list(discovery.tests),
            risks=list(discovery.risks),
            verification=discovery.verification or "",
            map_confidence=discovery.map_freshness.get("state", "unknown"),
            context_brief=list(discovery.context_brief),
            ready=(
                discovery.recommended_lane != "ask_user"
                and len(discovery.files_to_touch) > 0
            ),
        )


# ---------------------------------------------------------------------------
# orient_packet — pure discovery wrapper
# ---------------------------------------------------------------------------
def orient_packet(
    root: Path | str,
    run_id: str,
    *,
    handoff: Optional[str] = None,
    files_to_touch: Optional[list[str]] = None,
) -> OrientResult:
    """Run scout discovery for a pipeline run and return a compact result."""
    discovery = discover_agent_scout_context(
        root,
        run_id,
        handoff=handoff,
        files_to_touch=files_to_touch,
    )
    return OrientResult.from_discovery(discovery, run_id=run_id)


# ---------------------------------------------------------------------------
# run_orient — full orient step with state management
# ---------------------------------------------------------------------------
def run_orient(
    root: Path | str,
    run_id: str,
    *,
    handoff: Optional[str] = None,
    files_to_touch: Optional[list[str]] = None,
) -> tuple[DevFlowLoopState, OrientResult]:
    """Run the full orient step: load state, discover, advance, save, persist."""
    # Load current loop state
    state = load_loop_state(root, run_id)

    # Run scout discovery
    orient = orient_packet(root, run_id, handoff=handoff, files_to_touch=files_to_touch)

    # If we're at idea stage and orient is ready, advance to definition
    if state.stage == LoopStage.idea and orient.ready:
        state = advance_stage(state, LoopStage.definition)
        save_loop_state(root, state)

    # Write orient evidence to pipeline run dir
    orient_json = orient.model_dump_json(indent=2, ensure_ascii=False)
    save_orient_evidence(root, run_id, orient_json)

    return state, orient


def save_orient_evidence(root: Path | str, run_id: str, json_str: str) -> None:
    """Write orient-result.json into the pipeline run directory."""
    run_dir = _run_dir(root, run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    evidence_path = run_dir / "orient-result.json"
    evidence_path.write_text(json_str, encoding="utf-8")


def _run_dir(root: Path | str, run_id: str) -> Path:
    """Resolve the pipeline run directory for a given run_id."""
    from devflow.control_room.pipeline_run import _run_dir as _internal_run_dir

    return _internal_run_dir(Path(root), run_id)
