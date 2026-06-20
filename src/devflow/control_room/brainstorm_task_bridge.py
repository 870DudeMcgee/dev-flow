"""Atomic Brainstorm -> Task bridge.

Provides a single function that creates a task AND writes its implementation
context in one atomic operation, so the browser never needs to choreograph two
separate round-trips (task create + context write).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from devflow.control_room.brainstorm_pipeline import (
    BrainstormImplementationContext,
    build_implementation_context,
)
from devflow.control_room.persistence import append_event, atomic_write_text, utc_now
from devflow.control_room.paths import relative_path, workspace_path
from devflow.control_room.service import create_task


def create_task_from_brainstorm(
    root: Path,
    session_id: str,
    stage: str,
    title: str,
    definition_of_done: str | None = None,
    source_idea_id: str | None = None,
) -> dict[str, Any]:
    """Create a task from a brainstorm implementation-stage escalation.

    1. Validate that the brainstorm session has an implementation artifact.
    2. Create the task via ``service.create_task``.
    3. Write ``implementation-context.md`` into the new workspace.
    4. Append a brainstorm-lineage event to the task's events.jsonl.
    5. Update the brainstorm pipeline's lineage with ``created_task_id``.
    6. Return structured result.

    Returns keys: task_id, title, context_path, status, actions (list of dicts
    for worker options), lineages (dict with brainstorm + task event paths).
    """
    root = root.resolve()
    stage_lower = str(stage or "").lower().strip()
    if stage_lower != "implementation":
        raise ValueError("create_task_from_brainstorm only supports stage=implementation")

    session_path = root / ".devflow" / "brainstorms" / session_id
    transcript_path = session_path / "transcript.jsonl"
    implementation_artifact = session_path / "implementation.md"

    # Validate implementation stage is ready
    if not transcript_path.exists():
        raise ValueError(f"brainstorm session has no transcript: {session_id}")
    records = _read_transcript(transcript_path)
    if not records:
        raise ValueError(f"brainstorm session has no transcript records: {session_id}")
    if not implementation_artifact.exists():
        raise ValueError(
            f"brainstorm stage is not implementation for session {session_id}; "
            f"implementation.md missing."
        )

    # Load pipeline detail (may already have lineage from escalation)
    detail = _load_detail(root, session_id, records)
    _detail_lineage = detail.get("lineage")
    existing_lineage: dict[str, Any] = dict(_detail_lineage) if _detail_lineage else {
        "schema_version": 1,
        "brainstorm_session_id": session_id,
        "brainstorm_path": relative_path(root, session_path),
        "artifact_stage": stage_lower,
    }
    if source_idea_id:
        existing_lineage["source_idea_id"] = source_idea_id

    # Create the task via service.create_task
    now = utc_now()
    task_record = create_task(
        root=root,
        title=title,
        definition_of_done=definition_of_done,
    )
    task_id: str = task_record.id
    task_path = workspace_path(root, task_id)

    # Write implementation-context.md
    context = build_implementation_context(
        root=root,
        session_id=session_id,
        records=records,
        artifact_path=implementation_artifact,
        source_idea_id=source_idea_id,
        lineage=existing_lineage,
    )
    if context is None:
        # Fallback: build from implementation.md directly if spec/plan missing
        impl_content = implementation_artifact.read_text(encoding="utf-8").strip()
        context = BrainstormImplementationContext(
            text=impl_content,
            source_paths=[relative_path(root, implementation_artifact)],
            lineage=existing_lineage,
        )

    context_file = task_path / "implementation-context.md"
    atomic_write_text(context_file, context.text + "\n", encoding="utf-8")

    # Append task event with brainstorm lineage
    append_event(
        root,
        task_id,
        "brainstorm_created",
        {
            "session_id": session_id,
            "source_idea_id": source_idea_id,
            "lineage": existing_lineage,
            "definition_of_done": definition_of_done,
            "context_path": relative_path(root, context_file),
        },
    )

    # Update brainstorm pipeline JSON with created_task_ids and lineage
    pipeline_path = session_path / "pipeline.json"
    if pipeline_path.exists():
        pipeline_payload = json.loads(pipeline_path.read_text(encoding="utf-8"))
        if "created_task_ids" not in pipeline_payload:
            pipeline_payload["created_task_ids"] = []
        pipeline_payload["created_task_ids"].append(task_id)
        pipeline_payload["lineage"] = existing_lineage
        atomic_write_text(pipeline_path, json.dumps(pipeline_payload, indent=2, sort_keys=True) + "\n")

    # Build worker actions (minimal for this bridge)
    actions = [
        {
            "label": "Inspect",
            "command": f"devflow task show {task_id}",
            "enabled": True,
            "safety_class": "pure_read_only",
            "requires_human_approval": False,
        },
        {
            "label": "Verify",
            "command": f'devflow task verify {task_id} --shell "<command>"',
            "enabled": True,
            "safety_class": "approval_required_worker_runtime",
            "requires_human_approval": True,
        },
    ]

    return {
        "schema_version": 1,
        "status": "created",
        "task_id": task_id,
        "title": title,
        "context_path": relative_path(root, context_file),
        "actions": actions,
        "lineage": existing_lineage,
    }


def _load_detail(
    root: Path, session_id: str, records: list[dict[str, Any]]
) -> dict[str, Any]:
    """Attempt to load and return BrainstormPipelineDetail as a dict."""
    try:
        from devflow.control_room.brainstorm_pipeline import (
            load_brainstorm_pipeline_detail,
        )

        loaded = load_brainstorm_pipeline_detail(root, session_id=session_id, records=records)
        return loaded.model_dump(mode="json")
    except Exception:
        pass
    # Fallback dict
    lineage = {
        "schema_version": 1,
        "brainstorm_session_id": session_id,
        "brainstorm_path": f".devflow/brainstorms/{session_id}",
        "artifact_stage": "implementation",
    }
    if source_idea := _extract_source_idea_id(records):
        lineage["source_idea_id"] = source_idea
    return {
        "schema_version": 1,
        "session_id": session_id,
        "stage": "implementation",
        "status": "ready",
        "has_transcript": bool(records),
        "has_spec": False,
        "has_plan": False,
        "has_implementation": True,
        "stages": [],
        "artifact_path": None,
        "evidence_paths": [],
        "lineage": lineage,
    }


def _extract_source_idea_id(records: list[dict[str, Any]]) -> str | None:
    """Walk transcript records for a source_idea_id hint."""
    for rec in reversed(records):
        if rec.get("kind") == "brainstorm_start" and rec.get("metadata"):
            sid = rec["metadata"].get("source_idea_id")
            if sid:
                return str(sid)
    return None


def _read_transcript(path: Path) -> list[dict[str, Any]]:
    """Read the brainstorm transcript.jsonl into records."""
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(rec, dict):
            records.append(rec)
    return records
