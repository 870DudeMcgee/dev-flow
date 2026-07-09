"""Stage artifact contract for brainstorm pipeline quality gates.

Provides a durable record of each stage's quality status (draft/passed/escalated/accepted)
so that _pipeline_stages can show real gate state instead of relying on file-existence alone.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

from devflow.legacy.control_room.paths import relative_path
from devflow.legacy.control_room.persistence import atomic_write_text


ARTIFACT_SCHEMA_VERSION = 1


class StageArtifact(BaseModel):
    """Durable quality record for a brainstorm pipeline stage."""

    schema_version: int = ARTIFACT_SCHEMA_VERSION
    stage: Literal["spec", "plan", "implementation"]
    source: Literal["brainstorm", "builder_judge", "manual"]
    status: Literal["draft", "passed", "escalated", "accepted"]
    artifact_path: str
    quality_gate_path: str | None = None
    score: int | None = None
    next_action: str | None = None

    def model_dump_mode(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def stage_artifact_dir(root: Path, session_id: str) -> Path:
    return root / ".devflow" / "brainstorms" / session_id


def _artifact_file_path(root: Path, session_id: str, stage: str) -> Path:
    """Return the .artifact.json path for a given stage."""
    return stage_artifact_dir(root, session_id) / f"{stage}.artifact.json"


def write_stage_artifact(
    root: Path,
    session_id: str,
    stage: Literal["spec", "plan", "implementation"],
    source: Literal["brainstorm", "builder_judge", "manual"],
    status: Literal["draft", "passed", "escalated", "accepted"],
    artifact_path: Path,
    *,
    quality_gate_path: Path | None = None,
    score: int | None = None,
    next_action: str | None = None,
) -> StageArtifact:
    """Create and persist a StageArtifact record."""
    root = root.resolve()
    rel_artifact = relative_path(root, artifact_path)
    rel_gating = relative_path(root, quality_gate_path) if quality_gate_path else None
    record = StageArtifact(
        stage=stage,
        source=source,
        status=status,
        artifact_path=rel_artifact,
        quality_gate_path=rel_gating,
        score=score,
        next_action=next_action,
    )
    path = _artifact_file_path(root, session_id, stage)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, json.dumps(record.model_dump_mode(), indent=2, sort_keys=True) + "\n")
    return record


def load_stage_artifact(
    root: Path,
    session_id: str,
    stage: Literal["spec", "plan", "implementation"],
) -> StageArtifact | None:
    """Load and validate a persisted StageArtifact, or return None."""
    path = _artifact_file_path(root, session_id, stage)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            return StageArtifact.model_validate(payload)
    except (OSError, ValueError):
        pass
    return None
