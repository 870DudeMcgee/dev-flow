from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from devflow.legacy.control_room.brainstorm import (
    BrainstormError,
    escalate_brainstorm_session,
    run_brainstorm_message,
    start_brainstorm_from_idea,
)
from devflow.legacy.control_room.brainstorm_pipeline import (
    build_intent_summary_preview,
    build_manual_intent_summary,
    classify_and_attach_intent_summary,
    create_task_from_brainstorm,
    load_brainstorm_session_snapshot,
    write_intent_summary_to_run,
)
from devflow.legacy.control_room.project_registry import ProjectRegistryError, resolve_project_root

BRAINSTORM_POST_BAD_REQUEST_ERRORS = (BrainstormError, ProjectRegistryError, OSError, ValueError)


class BrainstormRouteBadRequest(ValueError):
    pass


def build_brainstorm_sessions_payload(root: Path) -> dict[str, object]:
    sessions_dir = root / ".devflow" / "brainstorms"
    sessions: list[dict[str, object]] = []
    if sessions_dir.exists():
        for entry in sorted(
            sessions_dir.iterdir(),
            key=lambda e: e.stat().st_mtime if e.is_dir() else 0,
            reverse=True,
        ):
            if not entry.is_dir():
                continue
            transcript = entry / "transcript.jsonl"
            if not transcript.exists():
                continue
            first_user_msg = ""
            msg_count = 0
            has_spec = (entry / "spec.md").exists()
            has_plan = (entry / "plan.md").exists()
            has_implementation = (entry / "implementation.md").exists()
            for line in transcript.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(rec, dict):
                    msg_count += 1
                    if not first_user_msg and rec.get("role") == "user" and rec.get("kind") == "message":
                        first_user_msg = str(rec.get("content", ""))[:80]
            sessions.append(
                {
                    "session_id": entry.name,
                    "message_count": msg_count,
                    "preview": first_user_msg or "(no messages)",
                    "has_spec": has_spec,
                    "has_plan": has_plan,
                    "has_implementation": has_implementation,
                    "modified_at": datetime.fromtimestamp(entry.stat().st_mtime, tz=timezone.utc)
                    .isoformat()
                    .replace("+00:00", "Z"),
                }
            )
    return {"sessions": sessions}


def build_brainstorm_transcript_payload(root: Path, query: dict[str, list[str]]) -> dict[str, object]:
    session_id = (query.get("session_id") or [None])[0]
    if not session_id:
        raise BrainstormRouteBadRequest("session_id query parameter is required")
    snapshot = load_brainstorm_session_snapshot(root, session_id=session_id)
    return snapshot.model_dump(mode="json")


def run_brainstorm_message_payload(repo_root: Path, payload: dict[str, object]) -> dict[str, Any]:
    root = _payload_project_root(repo_root, payload)
    message = payload.get("message")
    if not isinstance(message, str):
        raise BrainstormError("message is required")
    session_id = payload.get("session_id")
    if session_id is not None and not isinstance(session_id, str):
        raise BrainstormError("session_id must be a string")
    profile_id = payload.get("profile_id")
    if profile_id is not None and not isinstance(profile_id, str):
        raise BrainstormError("profile_id must be a string")
    return run_brainstorm_message(root=root, message=message, session_id=session_id, profile_id=profile_id)


def escalate_brainstorm_payload(repo_root: Path, payload: dict[str, object]) -> dict[str, Any]:
    root = _payload_project_root(repo_root, payload)
    session_id = payload.get("session_id")
    stage = payload.get("stage")
    title = payload.get("title")
    if not isinstance(session_id, str):
        raise BrainstormError("session_id is required")
    if not isinstance(stage, str):
        raise BrainstormError("stage is required")
    if title is not None and not isinstance(title, str):
        raise BrainstormError("title must be a string")
    definition_of_done = payload.get("definition_of_done")
    if definition_of_done is not None and not isinstance(definition_of_done, str):
        raise BrainstormError("definition_of_done must be a string")
    profile_id = payload.get("profile_id")
    if profile_id is not None and not isinstance(profile_id, str):
        raise BrainstormError("profile_id must be a string")
    use_model = payload.get("use_model")
    if use_model is not None and not isinstance(use_model, bool):
        raise BrainstormError("use_model must be a boolean")
    return escalate_brainstorm_session(
        root=root,
        session_id=session_id,
        stage=stage,
        title=title,
        definition_of_done=definition_of_done,
        profile_id=profile_id,
        use_model=use_model,
    )


def start_brainstorm_from_idea_payload(repo_root: Path, payload: dict[str, object]) -> dict[str, Any]:
    idea_id_raw = payload.get("idea_id")
    if not isinstance(idea_id_raw, str):
        raise BrainstormError("idea_id is required and must be a string")
    idea_id = idea_id_raw.strip().upper()
    if not re.fullmatch(r"I-[0-9]{4}", idea_id):
        raise BrainstormError(f"idea_id must match I-NNNN pattern, got: {idea_id_raw!r}")
    result = start_brainstorm_from_idea(repo_root, idea_id)
    if result.get("status") == "reuse":
        result["session_id"] = result["session_id"]
    return result


def create_brainstorm_task_payload(repo_root: Path, payload: dict[str, object]) -> dict[str, Any]:
    root = _payload_project_root(repo_root, payload)
    session_id = payload.get("session_id")
    title = payload.get("title")
    if not isinstance(session_id, str):
        raise BrainstormError("session_id is required and must be a string")
    if not isinstance(title, str) or not title.strip():
        raise BrainstormError("title is required and must be a non-empty string")
    definition_of_done = payload.get("definition_of_done")
    if definition_of_done is not None and not isinstance(definition_of_done, str):
        raise BrainstormError("definition_of_done must be a string")
    source_idea_id = payload.get("source_idea_id")
    if source_idea_id is not None and not isinstance(source_idea_id, str):
        raise BrainstormError("source_idea_id must be a string")
    return create_task_from_brainstorm(
        root=root,
        session_id=session_id,
        stage="implementation",
        title=title,
        definition_of_done=definition_of_done or None,
        source_idea_id=source_idea_id or None,
    )


def _payload_project_root(repo_root: Path, payload: dict[str, object]) -> Path:
    project_id = payload.get("project")
    if isinstance(project_id, str) and project_id.strip():
        return resolve_project_root(repo_root, project_id.strip()).root
    return repo_root


def classify_brainstorm_payload(repo_root: Path, payload: dict[str, object]) -> dict[str, Any]:
    """Validate payload and classify brainstorm intent.

    POST /api/brainstorm/classify body: {operator_intent, run_id?, project?}
    If run_id is provided, writes classification.json to the pipeline run.
    """
    from devflow.legacy.control_room.brainstorm_pipeline import (
        build_classification_preview,
        classify_and_attach_to_run,
    )

    root = _payload_project_root(repo_root, payload)
    operator_intent = payload.get("operator_intent")
    if not isinstance(operator_intent, str) or not operator_intent.strip():
        raise BrainstormError("operator_intent is required and must be a non-empty string")

    run_id = payload.get("run_id")
    if isinstance(run_id, str) and run_id.strip():
        return classify_and_attach_to_run(root, run_id.strip(), operator_intent.strip())
    return build_classification_preview({"operator_intent": operator_intent.strip()})


def build_intent_summary_payload(repo_root: Path, payload: dict[str, object]) -> dict[str, Any]:
    """Validate payload and generate (or import manual) intent summary.

    POST /api/brainstorm/intent-summary body: {operator_intent, run_id?, project?, manual_summary?}
    If manual_summary is provided, uses it directly instead of generating.
    If run_id is provided, writes intent-summary.json to the pipeline run.
    """
    root = _payload_project_root(repo_root, payload)
    operator_intent = payload.get("operator_intent")
    if not isinstance(operator_intent, str) or not operator_intent.strip():
        raise BrainstormError("operator_intent is required and must be a non-empty string")

    manual_summary = payload.get("manual_summary")
    run_id = payload.get("run_id")

    # Manual override path
    if isinstance(manual_summary, dict) and manual_summary:
        result = build_manual_intent_summary(operator_intent.strip(), manual_summary)
        if isinstance(run_id, str) and run_id.strip():
            write_intent_summary_to_run(root, run_id.strip(), result["intent_summary"])
            from devflow.legacy.control_room.pipeline_run import _run_dir, pipeline_runs_dir
            run_dir = _run_dir(root, run_id.strip())
            result["run_id"] = run_id.strip()
            result["intent_summary_path"] = str(run_dir / "intent-summary.json")
            result["pipeline_runs_dir"] = str(pipeline_runs_dir(root))
        return result

    # Generated path
    if isinstance(run_id, str) and run_id.strip():
        return classify_and_attach_intent_summary(root, run_id.strip(), operator_intent.strip())
    return build_intent_summary_preview(operator_intent.strip())
