from __future__ import annotations

import json
import os
import re
import shlex
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from devflow.control_room.agent_registry import (
    AgentDefinition,
    ProviderDefinition,
    is_remote_advisory_agent,
    load_agent_registry,
    load_provider_registry,
)
from devflow.control_room.openrouter_agent import (
    OpenRouterAgentError,
    _assistant_content,
    _chat_completion,
    _redact,
    _safe_json,
)
from devflow.control_room.paths import relative_path
from devflow.control_room.persistence import atomic_write_text


BRAINSTORM_PROFILE_ID = "deepseek-v4-flash-free-brainstormer"
BRAINSTORM_MAX_MESSAGE_CHARS = 12_000
BRAINSTORM_MAX_HISTORY_MESSAGES = 16
SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$")


class BrainstormError(ValueError):
    pass


def run_brainstorm_message(
    *,
    root: Path,
    message: str,
    session_id: str | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    text = _validate_message(message)
    session = _session_id(session_id)
    profile, provider = _load_brainstorm_profile(root)
    evidence_dir = _session_dir(root, session)
    transcript_path = evidence_dir / "transcript.jsonl"
    run_path = evidence_dir / "run.json"
    raw_response_path = evidence_dir / "response.raw.json"
    created_at = _now()

    _append_transcript(
        transcript_path,
        {
            "created_at": created_at,
            "role": "user",
            "kind": "message",
            "content": text,
        },
    )

    api_key_env = provider.api_key_env or "OPENROUTER_API_KEY"
    api_key = os.environ.get(api_key_env)
    if not api_key:
        error = f"Provider '{provider.id}' requires {api_key_env}, but that environment variable is not set."
        _append_transcript(
            transcript_path,
            {
                "created_at": _now(),
                "role": "system",
                "kind": "provider_error",
                "content": error,
            },
        )
        payload = _run_payload(
            root=root,
            status="failed",
            session_id=session,
            profile=profile,
            provider=provider,
            transcript_path=transcript_path,
            run_path=run_path,
            raw_response_path=None,
            assistant_message=None,
            usage=None,
            error=error,
            will_call_provider=False,
        )
        atomic_write_text(run_path, json.dumps(payload, indent=2, sort_keys=True) + "\n")
        return payload

    try:
        response_body = _chat_completion(
            provider=provider,
            model=profile.model,
            system_prompt=_brainstorm_system_prompt(profile),
            user_prompt=_brainstorm_user_prompt(transcript_path, text),
            api_key=api_key,
            timeout_seconds=provider.default_timeout_seconds,
        )
        raw_text = _safe_json(response_body, api_key=api_key)
        content = _assistant_content(response_body)
        assistant_message = _assistant_message_from_content(content)
        _append_transcript(
            transcript_path,
            {
                "created_at": _now(),
                "role": "assistant",
                "kind": "message",
                "content": assistant_message,
                "model": profile.model,
                "profile_id": profile.id,
            },
        )
        atomic_write_text(raw_response_path, raw_text)
        payload = _run_payload(
            root=root,
            status="success",
            session_id=session,
            profile=profile,
            provider=provider,
            transcript_path=transcript_path,
            run_path=run_path,
            raw_response_path=raw_response_path,
            assistant_message=assistant_message,
            usage=response_body.get("usage") if isinstance(response_body.get("usage"), dict) else None,
            error=None,
            will_call_provider=True,
        )
    except Exception as exc:
        error = _redact(str(exc), api_key=api_key)
        _append_transcript(
            transcript_path,
            {
                "created_at": _now(),
                "role": "system",
                "kind": "provider_error",
                "content": error,
            },
        )
        payload = _run_payload(
            root=root,
            status="failed",
            session_id=session,
            profile=profile,
            provider=provider,
            transcript_path=transcript_path,
            run_path=run_path,
            raw_response_path=None,
            assistant_message=None,
            usage=None,
            error=error,
            will_call_provider=True,
        )
    atomic_write_text(run_path, json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return payload


def escalate_brainstorm_session(
    *,
    root: Path,
    session_id: str,
    stage: str,
    title: str | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    session = _session_id(session_id)
    normalized_stage = str(stage or "").strip().lower()
    if normalized_stage not in {"spec", "plan", "implementation"}:
        raise BrainstormError("stage must be spec, plan, or implementation")

    transcript_path = _session_dir(root, session) / "transcript.jsonl"
    records = _read_transcript(transcript_path)
    if not records:
        raise BrainstormError(f"brainstorm session has no transcript: {session}")

    if normalized_stage == "implementation":
        task_title = _implementation_title(title, records)
        action = {
            "label": "Open Implementation Task",
            "command": f"devflow task create {shlex.quote(task_title)}",
            "scope": "brainstorm",
            "safety_class": "approval_required_task_state",
            "requires_human_approval": True,
            "supervisor_may_auto_run": False,
            "reason": "Creates one Dev-Flow task from an approved brainstorm escalation.",
        }
        artifact_path = _write_stage_artifact(root, session, normalized_stage, records, title=task_title)
        return {
            "schema_version": 1,
            "status": "ready",
            "session_id": session,
            "stage": normalized_stage,
            "artifact_path": relative_path(root, artifact_path),
            "action": action,
        }

    artifact_path = _write_stage_artifact(root, session, normalized_stage, records, title=title)
    return {
        "schema_version": 1,
        "status": "ready",
        "session_id": session,
        "stage": normalized_stage,
        "artifact_path": relative_path(root, artifact_path),
    }


def _load_brainstorm_profile(root: Path) -> tuple[AgentDefinition, ProviderDefinition]:
    profile = load_agent_registry(root).require_agent(BRAINSTORM_PROFILE_ID)
    provider = load_provider_registry(root).require_provider(profile.provider)
    if not is_remote_advisory_agent(profile, provider=provider):
        raise OpenRouterAgentError(f"Profile '{profile.id}' is not an advisory OpenRouter profile.")
    return profile, provider


def _brainstorm_system_prompt(profile: AgentDefinition) -> str:
    return (
        "You are DeepSeek V4 Flash Free inside Dev-Flow's Brainstorm stage. "
        "Chat with the developer about product direction and convert messy intent into clear next steps. "
        "You are advisory evidence only: do not claim to edit files, run workers, verify, promote, commit, or push. "
        "Keep answers concise and implementation-oriented. "
        "Return JSON with keys: message, stage_hint. stage_hint must be brainstorm, spec, plan, or implementation. "
        f"Profile: {profile.id}."
    )


def _brainstorm_user_prompt(transcript_path: Path, message: str) -> str:
    history = _read_transcript(transcript_path)[-BRAINSTORM_MAX_HISTORY_MESSAGES:]
    lines = [
        "## Conversation History",
        json.dumps(history, indent=2, sort_keys=True),
        "",
        "## Latest Developer Message",
        message,
        "",
        "Respond as the brainstorm chat assistant. If enough intent is present, suggest the next escalation stage.",
    ]
    return "\n".join(lines)


def _assistant_message_from_content(content: str) -> str:
    stripped = content.strip()
    if not stripped:
        return "I did not receive a usable response from DeepSeek."
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        return stripped
    if isinstance(payload, dict) and isinstance(payload.get("message"), str) and payload["message"].strip():
        return payload["message"].strip()
    return stripped


def _run_payload(
    *,
    root: Path,
    status: str,
    session_id: str,
    profile: AgentDefinition,
    provider: ProviderDefinition,
    transcript_path: Path,
    run_path: Path,
    raw_response_path: Path | None,
    assistant_message: str | None,
    usage: dict[str, Any] | None,
    error: str | None,
    will_call_provider: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": 1,
        "status": status,
        "session_id": session_id,
        "profile_id": profile.id,
        "provider": provider.id,
        "model": profile.model,
        "adapter": profile.adapter,
        "transcript_path": relative_path(root, transcript_path),
        "run_path": relative_path(root, run_path),
        "will_call_provider": will_call_provider,
        "created_at": _now(),
    }
    if raw_response_path is not None:
        payload["raw_response_path"] = relative_path(root, raw_response_path)
    if assistant_message is not None:
        payload["assistant_message"] = assistant_message
    if usage is not None:
        payload["usage"] = usage
    if error is not None:
        payload["error"] = error
    return payload


def _write_stage_artifact(
    root: Path,
    session_id: str,
    stage: str,
    records: list[dict[str, Any]],
    *,
    title: str | None = None,
) -> Path:
    heading = {"spec": "Brainstorm Spec", "plan": "Brainstorm Plan", "implementation": "Implementation Task"}[stage]
    path = _session_dir(root, session_id) / f"{stage}.md"
    body = [
        f"# {heading}",
        "",
        f"Session: `{session_id}`",
        f"Title: {title or _derive_title(records)}",
        "",
        "## Source Conversation",
        "",
    ]
    for record in records:
        role = str(record.get("role") or "unknown")
        content = str(record.get("content") or "").strip()
        if content:
            body.extend([f"### {role.title()}", "", content, ""])
    atomic_write_text(path, "\n".join(body).rstrip() + "\n")
    return path


def _append_transcript(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def _read_transcript(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            records.append(value)
    return records


def _session_dir(root: Path, session_id: str) -> Path:
    return root / ".devflow" / "brainstorms" / session_id


def _session_id(value: str | None) -> str:
    if value is None or not value.strip():
        return "brainstorm-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    normalized = value.strip()
    if not SESSION_ID_PATTERN.match(normalized):
        raise BrainstormError("session_id may contain only letters, numbers, '.', '_', and '-'")
    return normalized


def _validate_message(message: str) -> str:
    text = str(message or "").strip()
    if not text:
        raise BrainstormError("message is required")
    if len(text) > BRAINSTORM_MAX_MESSAGE_CHARS:
        raise BrainstormError(f"message must be {BRAINSTORM_MAX_MESSAGE_CHARS} characters or fewer")
    return text


def _implementation_title(title: str | None, records: list[dict[str, Any]]) -> str:
    candidate = str(title or "").strip() or _derive_title(records)
    if not candidate or candidate.lower() in {"todo", "tbd", "task", "<title>"}:
        raise BrainstormError("implementation title is required")
    return candidate[:120]


def _derive_title(records: list[dict[str, Any]]) -> str:
    for record in records:
        if record.get("role") == "user":
            content = " ".join(str(record.get("content") or "").split())
            if content:
                return content[:80]
    return "Brainstorm follow-up"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
