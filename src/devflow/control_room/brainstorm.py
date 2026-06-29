from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from devflow.control_room.agent_registry import (
    AgentDefinition,
    ProviderDefinition,
    is_hermes_subscription_agent,
    is_local_openai_compatible_provider,
    is_remote_advisory_agent,
    load_agent_registry,
    load_provider_registry,
)
from devflow.control_room.brainstorm_pipeline import (
    build_brainstorm_escalation_result,
    build_brainstorm_pipeline_detail,
    write_brainstorm_pipeline_detail,
)
from devflow.control_room.env_loader import resolve_api_key
from devflow.control_room.hermes_profile_resolver import (
    hermes_direct_handoff_state,
    load_hermes_picker_runtime,
)
from devflow.control_room.local_model_server import ensure_local_model_server_for_profile
from devflow.control_room.openrouter_agent import (
    OpenRouterAgentError,
    _assistant_content,
    _chat_completion,
    _redact,
    _safe_json,
)
from devflow.control_room.paths import ideas_dir, relative_path
from devflow.control_room.persistence import atomic_write_text
from devflow.control_room.stage_artifact import write_stage_artifact as save_stage_artifact


BRAINSTORM_PROFILE_ID = "hermes-qwen37plus"
BRAINSTORM_MAX_MESSAGE_CHARS = 100_000
BRAINSTORM_MAX_HISTORY_MESSAGES = 16
SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$")

_OLLAMA_DEFAULT_BASE_URL = "http://127.0.0.1:11434"
_OLLAMA_DEFAULT_TIMEOUT = 300
HERMES_PROFILE_HANDOFF_ERROR = (
    "Hermes/OpenAI subscription profile is visible in model pickers, but direct "
    "Dev-Flow execution is disabled until a safe Hermes runtime adapter exists; "
    "this profile cannot fall back to OpenRouter billing."
)


class BrainstormError(ValueError):
    pass


def _is_ollama_provider(provider: ProviderDefinition) -> bool:
    return provider.provider == "ollama" or provider.adapter == "ollama_chat"


def _ollama_chat_completion(
    *,
    provider: ProviderDefinition,
    model: str,
    system_prompt: str,
    user_prompt: str,
    timeout_seconds: int | None = None,
) -> dict[str, Any]:
    """Call a local Ollama /api/chat endpoint and return a normalized response body."""
    base_url = (provider.base_url or _OLLAMA_DEFAULT_BASE_URL).rstrip("/")
    url = f"{base_url}/api/chat"
    body: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.2},
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    request_timeout = timeout_seconds or provider.default_timeout_seconds or _OLLAMA_DEFAULT_TIMEOUT
    try:
        with urllib.request.urlopen(request, timeout=request_timeout) as response:
            decoded = response.read().decode("utf-8")
    except urllib.error.URLError as exc:
        raise OpenRouterAgentError(
            f"Ollama request failed: {exc.reason}. Is Ollama running at {base_url}?"
        ) from exc
    except TimeoutError as exc:
        raise OpenRouterAgentError(f"Ollama request timed out after {request_timeout}s.") from exc
    try:
        payload = json.loads(decoded)
    except json.JSONDecodeError as exc:
        raise OpenRouterAgentError(f"Ollama returned invalid JSON: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise OpenRouterAgentError("Ollama response root was not a JSON object.")
    return payload


def _ollama_extract_content(response_body: dict[str, Any]) -> str:
    """Extract assistant content from an Ollama /api/chat response."""
    message = response_body.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str):
            return content.strip()
    content = response_body.get("response")
    if isinstance(content, str):
        return content.strip()
    raise OpenRouterAgentError("Ollama response did not include assistant content.")


def _local_openai_compatible_chat_completion(
    *,
    provider: ProviderDefinition,
    model: str,
    system_prompt: str,
    user_prompt: str,
    timeout_seconds: int | None = None,
) -> dict[str, Any]:
    if not provider.base_url:
        raise OpenRouterAgentError(f"Provider '{provider.id}' base_url is missing.")
    base_url = provider.base_url.rstrip("/")
    url = f"{base_url}/chat/completions"
    body: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    request_timeout = timeout_seconds or provider.default_timeout_seconds or _OLLAMA_DEFAULT_TIMEOUT
    try:
        with urllib.request.urlopen(request, timeout=request_timeout) as response:
            decoded = response.read().decode("utf-8")
    except urllib.error.URLError as exc:
        raise OpenRouterAgentError(
            f"Local OpenAI-compatible request failed: {exc.reason}. Is the service running at {base_url}?"
        ) from exc
    except TimeoutError as exc:
        raise OpenRouterAgentError(
            f"Local OpenAI-compatible request timed out after {request_timeout}s."
        ) from exc
    try:
        payload = json.loads(decoded)
    except json.JSONDecodeError as exc:
        raise OpenRouterAgentError(f"Local OpenAI-compatible provider returned invalid JSON: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise OpenRouterAgentError("Local OpenAI-compatible response root was not a JSON object.")
    return payload


def _chat_completion_for_profile(
    *,
    profile: AgentDefinition,
    provider: ProviderDefinition,
    system_prompt: str,
    user_prompt: str,
    api_key: str | None = None,
) -> dict[str, Any]:
    """Route to OpenRouter or Ollama depending on the provider."""
    if profile.adapter == "hermes_profile" or provider.adapter == "hermes_profile" or is_hermes_subscription_agent(profile, provider=provider):
        raise OpenRouterAgentError(HERMES_PROFILE_HANDOFF_ERROR)
    if _is_ollama_provider(provider):
        return _ollama_chat_completion(
            provider=provider,
            model=profile.model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            timeout_seconds=provider.default_timeout_seconds,
        )
    if is_local_openai_compatible_provider(provider) and not api_key:
        return _chat_completion(
            provider=provider,
            model=profile.model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            api_key=api_key,
            timeout_seconds=provider.default_timeout_seconds,
        )
    if not api_key:
        raise OpenRouterAgentError(
            f"Provider '{provider.id}' requires an API key but none was provided."
        )
    return _chat_completion(
        provider=provider,
        model=profile.model,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        api_key=api_key,
        timeout_seconds=provider.default_timeout_seconds,
    )


def _extract_content_for_profile(
    *,
    provider: ProviderDefinition,
    response_body: dict[str, Any],
) -> str:
    """Extract assistant content from either Ollama or OpenRouter response."""
    if _is_ollama_provider(provider):
        return _ollama_extract_content(response_body)
    return _assistant_content(response_body)


def _normalize_raw_response(response_body: dict[str, Any], *, api_key: str | None = None) -> str:
    """Serialize the raw response for evidence, redacting if needed."""
    if api_key:
        return _safe_json(response_body, api_key=api_key)
    return json.dumps(response_body, indent=2, sort_keys=True)


def run_brainstorm_message(
    *,
    root: Path,
    message: str,
    session_id: str | None = None,
    profile_id: str | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    text = _validate_message(message)
    session = _session_id(session_id)
    profile, provider = _load_brainstorm_profile(root, profile_id=profile_id)
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

    handoff_state = hermes_direct_handoff_state(profile, provider)
    is_hermes_profile = handoff_state is not None or is_hermes_subscription_agent(profile, provider=provider)
    is_local_provider = _is_ollama_provider(provider) or is_local_openai_compatible_provider(provider)
    api_key: str | None = None
    local_model_server_lifecycle: dict[str, Any] | None = None
    if is_hermes_profile:
        handoff_error = (handoff_state or {}).get("error") or HERMES_PROFILE_HANDOFF_ERROR
        _append_transcript(
            transcript_path,
            {
                "created_at": _now(),
                "role": "system",
                "kind": "provider_error",
                "content": handoff_error,
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
            error=handoff_error,
            will_call_provider=False,
            handoff_state=handoff_state,
        )
        atomic_write_text(run_path, json.dumps(payload, indent=2, sort_keys=True) + "\n")
        return payload
    if not is_local_provider:
        api_key_env = provider.api_key_env or "OPENROUTER_API_KEY"
        api_key = resolve_api_key(api_key_env)
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
        if is_local_openai_compatible_provider(provider):
            local_model_server_lifecycle = ensure_local_model_server_for_profile(
                root=root,
                provider=profile.provider,
                model=profile.model,
                base_url=provider.base_url,
                wait_for_ready=False,
            )
        response_body = _chat_completion_for_profile(
            profile=profile,
            provider=provider,
            system_prompt=_brainstorm_system_prompt(profile),
            user_prompt=_brainstorm_user_prompt(transcript_path, text),
            api_key=api_key,
        )
        raw_text = _normalize_raw_response(response_body, api_key=api_key)
        content = _extract_content_for_profile(provider=provider, response_body=response_body)
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
            local_model_server_lifecycle=local_model_server_lifecycle,
        )
    except Exception as exc:
        error = _redact(str(exc), api_key=api_key or "") if api_key else str(exc)
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
            local_model_server_lifecycle=local_model_server_lifecycle,
        )
    atomic_write_text(run_path, json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return payload


def escalate_brainstorm_session(
    *,
    root: Path,
    session_id: str,
    stage: str,
    title: str | None = None,
    definition_of_done: str | None = None,
    profile_id: str | None = None,
    use_model: bool | None = None,
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

    source_idea_id = _extract_source_idea_id(records)
    model_info: dict[str, Any] | None = None
    if use_model and normalized_stage in {"spec", "plan"}:
        model_info = _generate_stage_with_model(root, session, normalized_stage, records, profile_id=profile_id)

    if normalized_stage == "implementation":
        task_title = _implementation_title(title, records)
        done_text = _definition_of_done(definition_of_done)
        artifact_path = _write_stage_artifact(
            root,
            session,
            normalized_stage,
            records,
            title=task_title,
            definition_of_done=done_text,
            model_info=model_info,
            source_idea_id=source_idea_id,
        )
        # Also leave a draft StageArtifact so _pipeline_stages sees quality-gate state.
        save_stage_artifact(
            root,
            session,
            normalized_stage,  # type: ignore[arg-type]
            "manual",
            "draft",
            artifact_path,
            next_action=f"Escalated to {normalized_stage}. Review and optionally run a quality gate.",
        )
        detail = build_brainstorm_pipeline_detail(
            root,
            session_id=session,
            stage=normalized_stage,
            records=records,
            artifact_path=artifact_path,
            title=task_title,
            definition_of_done=done_text,
            model_info=model_info,
            source_idea_id=source_idea_id,
            advisory_profile=_advisory_profile_payload(root, profile_id=profile_id),
        )
        write_brainstorm_pipeline_detail(root, detail)
        return build_brainstorm_escalation_result(
            detail,
            artifact_path=relative_path(root, artifact_path),
            model_info=model_info,
        ).model_dump(mode="json")

    artifact_path = _write_stage_artifact(
        root,
        session,
        normalized_stage,
        records,
        title=title,
        model_info=model_info,
        source_idea_id=source_idea_id,
    )
    # Also leave a draft StageArtifact so _pipeline_stages sees quality-gate state.
    save_stage_artifact(
        root,
        session,
        normalized_stage,  # type: ignore[arg-type]
        "manual",
        "draft",
        artifact_path,
        next_action=f"Escalated to {normalized_stage}. Review and optionally run a quality gate.",
    )
    detail = build_brainstorm_pipeline_detail(
        root,
        session_id=session,
        stage=normalized_stage,
        records=records,
        artifact_path=artifact_path,
        title=title,
        model_info=model_info,
        source_idea_id=source_idea_id,
        advisory_profile=_advisory_profile_payload(root, profile_id=profile_id),
    )
    write_brainstorm_pipeline_detail(root, detail)
    return build_brainstorm_escalation_result(
        detail,
        artifact_path=relative_path(root, artifact_path),
        model_info=model_info,
    ).model_dump(mode="json")


def _generate_stage_with_model(
    root: Path,
    session: str,
    stage: str,
    records: list[dict[str, Any]],
    *,
    profile_id: str | None = None,
) -> dict[str, Any]:
    """Call a model to produce a structured spec/plan from the brainstorm transcript."""
    profile, provider = _load_brainstorm_profile(root, profile_id=profile_id)
    handoff_state = hermes_direct_handoff_state(profile, provider)
    if handoff_state is not None or is_hermes_subscription_agent(profile, provider=provider):
        return {
            "used_model": False,
            "error": (handoff_state or {}).get("error") or HERMES_PROFILE_HANDOFF_ERROR,
            "profile_id": profile.id,
            "model": profile.model,
            "handoff_state": handoff_state,
            "runtime_contract": (handoff_state or {}).get("runtime_contract"),
            "next_command": (handoff_state or {}).get("next_command"),
        }
    is_local_provider = _is_ollama_provider(provider) or is_local_openai_compatible_provider(provider)
    api_key: str | None = None
    if not is_local_provider:
        api_key_env = provider.api_key_env or "OPENROUTER_API_KEY"
        api_key = resolve_api_key(api_key_env)
        if not api_key:
            return {
                "used_model": False,
                "error": f"Provider '{provider.id}' requires {api_key_env}, but that environment variable is not set.",
                "profile_id": profile.id,
                "model": profile.model,
            }

    system_prompt = _stage_system_prompt(profile, stage)
    user_prompt = _stage_user_prompt(records, stage)
    try:
        response_body = _chat_completion_for_profile(
            profile=profile,
            provider=provider,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            api_key=api_key,
        )
    except Exception as exc:
        return {
            "used_model": False,
            "error": _redact(str(exc), api_key=api_key or "") if api_key else str(exc),
            "profile_id": profile.id,
            "model": profile.model,
        }

    raw_text = _normalize_raw_response(response_body, api_key=api_key)
    content = _extract_content_for_profile(provider=provider, response_body=response_body)
    structured = _parse_stage_content(content, stage)
    evidence_dir = _session_dir(root, session)
    raw_response_path = evidence_dir / f"{stage}.raw.json"
    atomic_write_text(raw_response_path, raw_text)

    _append_transcript(
        evidence_dir / "transcript.jsonl",
        {
            "created_at": _now(),
            "role": "assistant",
            "kind": f"{stage}_generation",
            "content": structured,
            "model": profile.model,
            "profile_id": profile.id,
        },
    )

    return {
        "used_model": True,
        "profile_id": profile.id,
        "model": profile.model,
        "content": structured,
        "raw_response_path": relative_path(root, raw_response_path),
        "usage": response_body.get("usage") if isinstance(response_body.get("usage"), dict) else None,
    }


def _stage_system_prompt(profile: AgentDefinition, stage: str) -> str:
    stage_word = "specification" if stage == "spec" else "plan"
    return (
        f"You are {profile.model} inside Dev-Flow's {stage.title()} stage. "
        f"A developer has been brainstorming with an AI assistant. Your job is to read the full brainstorm transcript "
        f"and produce a clean, structured {stage_word} document that captures the decisions, requirements, and next steps. "
        f"Write in clear markdown. Do not invent features that were not discussed. "
        f"Return JSON with keys: title, {stage}_markdown, next_steps (array of strings). "
        f"Profile: {profile.id}."
    )


def _stage_user_prompt(records: list[dict[str, Any]], stage: str) -> str:
    lines = ["## Brainstorm Transcript", ""]
    for record in records:
        role = str(record.get("role") or "unknown")
        content = str(record.get("content") or "").strip()
        if content:
            lines.extend([f"### {role.title()}", "", content, ""])
    lines.extend([
        "## Task",
        "",
        f"Produce a structured {stage} document from this transcript. "
        f"Extract the core idea, decisions made, requirements, and concrete next steps. "
        f"Do not include content that was not discussed.",
    ])
    return "\n".join(lines)


def _parse_stage_content(content: str, stage: str) -> str:
    stripped = content.strip()
    if not stripped:
        return f"(Model returned empty {stage} content.)"
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        return stripped
    if isinstance(payload, dict):
        md_key = f"{stage}_markdown"
        md = payload.get(md_key) or payload.get("markdown") or payload.get("content") or ""
        title = payload.get("title") or ""
        next_steps = payload.get("next_steps") or []
        parts = []
        if title:
            parts.append(f"# {title}")
            parts.append("")
        if isinstance(md, str) and md.strip():
            parts.append(md.strip())
            parts.append("")
        if isinstance(next_steps, list) and next_steps:
            parts.append("## Next Steps")
            parts.append("")
            for step in next_steps:
                parts.append(f"- {step}")
            parts.append("")
        if parts:
            return "\n".join(parts)
    return stripped


def _load_brainstorm_profile(root: Path, *, profile_id: str | None = None) -> tuple[AgentDefinition, ProviderDefinition]:
    agent_id = profile_id or BRAINSTORM_PROFILE_ID
    hermes_runtime = load_hermes_picker_runtime(root, agent_id)
    if hermes_runtime is not None:
        return hermes_runtime
    profile = load_agent_registry(root).require_agent(agent_id)
    provider = load_provider_registry(root).require_provider(profile.provider)
    is_ollama = _is_ollama_provider(provider)
    is_local_openai = is_local_openai_compatible_provider(provider)
    is_hermes_profile = is_hermes_subscription_agent(profile, provider=provider)
    if not is_ollama and not is_local_openai and not is_hermes_profile and not is_remote_advisory_agent(profile, provider=provider):
        raise OpenRouterAgentError(f"Profile '{profile.id}' is not an approved advisory model profile.")
    return profile, provider


def _advisory_profile_payload(root: Path, *, profile_id: str | None = None) -> dict[str, Any] | None:
    try:
        profile, provider = _load_brainstorm_profile(root, profile_id=profile_id)
    except Exception:
        return {"profile_id": profile_id} if profile_id else None
    return {
        "profile_id": profile.id,
        "model": profile.model,
        "provider": provider.id,
        "adapter": profile.adapter,
    }


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
    local_model_server_lifecycle: dict[str, Any] | None = None,
    handoff_state: dict[str, Any] | None = None,
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
        "local_model_server_lifecycle": local_model_server_lifecycle,
        "created_at": _now(),
    }
    if handoff_state is not None:
        payload["handoff_state"] = handoff_state
        payload["runtime_contract"] = handoff_state.get("runtime_contract")
        payload["next_command"] = handoff_state.get("next_command")
    if raw_response_path is not None:
        payload["raw_response_path"] = relative_path(root, raw_response_path)
    if assistant_message is not None:
        payload["assistant_message"] = assistant_message
    if usage is not None:
        payload["usage"] = usage
    if error is not None:
        payload["error"] = error
    return payload


def _extract_source_idea_id(records: list[dict[str, Any]]) -> str | None:
    """Pull source_idea_id from the transcript's brainstorm_start seed record.

    Returns None when the session was started manually (no `brainstorm_start` kind).
    """
    for record in records:
        if record.get("kind") == "brainstorm_start":
            meta = record.get("metadata")
            if isinstance(meta, dict):
                return str(meta.get("source_idea_id", "")).strip() or None
    return None


def _write_stage_artifact(
    root: Path,
    session_id: str,
    stage: str,
    records: list[dict[str, Any]],
    *,
    title: str | None = None,
    definition_of_done: str | None = None,
    model_info: dict[str, Any] | None = None,
    source_idea_id: str | None = None,
) -> Path:
    heading = {"spec": "Brainstorm Spec", "plan": "Brainstorm Plan", "implementation": "Implementation Task"}[stage]
    path = _session_dir(root, session_id) / f"{stage}.md"
    sourced_id = source_idea_id or _extract_source_idea_id(records)
    body = [
        f"# {heading}",
        "",
        f"Session: `{session_id}`",
    ]
    if sourced_id:
        body.extend([f"Idea: `{sourced_id}`", ""])
    resolved_title = title or _derive_title(records)
    body.append(f"Title: {resolved_title}")
    body.append("")

    if definition_of_done:
        body.extend(["## Definition of Done", "", definition_of_done, ""])
    if model_info and model_info.get("used_model"):
        body.extend([
            f"Model: `{model_info.get('model', '?')}` (`{model_info.get('profile_id', '?')}`)",
            "",
        ])
    elif model_info and model_info.get("error"):
        body.extend([
            f"Model error: {model_info['error']}",
            "",
        ])
    if model_info and model_info.get("used_model") and model_info.get("content"):
        body.extend([
            "## Model-Generated " + stage.title(),
            "",
            model_info["content"],
            "",
            "## Source Conversation",
            "",
        ])
    else:
        body.extend([
            "## Source Conversation",
            "",
        ])
    for record in records:
        role = str(record.get("role") or "unknown")
        content = str(record.get("content") or "").strip()
        if content:
            body.extend([f"### {role.title()}", "", content, ""])
    atomic_write_text(path, "\n".join(body).rstrip() + "\n")
    _write_stage_lineage_sidecar(
        root,
        session_id=session_id,
        stage=stage,
        artifact_path=path,
        source_idea_id=sourced_id,
    )
    return path


def _write_stage_lineage_sidecar(
    root: Path,
    *,
    session_id: str,
    stage: str,
    artifact_path: Path,
    source_idea_id: str | None,
) -> Path:
    payload: dict[str, Any] = {
        "schema_version": 1,
        "artifact_stage": stage,
        "artifact_path": relative_path(root, artifact_path),
        "brainstorm_session_id": session_id,
        "brainstorm_path": relative_path(root, _session_dir(root, session_id)),
    }
    if source_idea_id:
        payload["source_idea_id"] = source_idea_id
    sidecar_path = artifact_path.with_suffix(".lineage.json")
    atomic_write_text(sidecar_path, json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return sidecar_path


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


def _definition_of_done(value: str | None) -> str | None:
    text = str(value or "").strip()
    return text or None


def _derive_title(records: list[dict[str, Any]]) -> str:
    for record in records:
        if record.get("role") == "user":
            content = " ".join(str(record.get("content") or "").split())
            if content:
                return content[:80]
    return "Brainstorm follow-up"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# Slice 4 — start brainstorm from idea
# ---------------------------------------------------------------------------

def start_brainstorm_from_idea(
    root: Path,
    idea_id: str,
) -> dict[str, Any]:
    """Open (or create) a brainstorm session seeded with the raw content of *idea_id*.

    The session folder is keyed by ``<session>-source-<idea_id>`` so repeated calls
    for the same idea return the existing session.
    """
    root = root.resolve()
    from devflow.control_room.idea_foundry import IdeaFoundryError, _get_idea, _read_optional_text

    try:
        metadata = _get_idea(root, idea_id)
        item_dir = ideas_dir(root) / idea_id
        raw_text = (
            _read_optional_text(item_dir / "raw.md")
            or (metadata.get("title", "") + "\n(No raw text found.)")
        ).strip()
    except IdeaFoundryError as exc:
        raise BrainstormError(f"Idea not found: {idea_id}") from exc

    folder_name = f"brainstorm-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-source-{idea_id}"
    brainstorms_root = root / ".devflow" / "brainstorms"
    brainstorms_root.mkdir(parents=True, exist_ok=True)
    session_dir = brainstorms_root / folder_name

    # If a previous brainstorm already owns this idea, reuse it
    candidates = [
        entry for entry in brainstorms_root.iterdir()
        if entry.is_dir() and entry.name.endswith(f"-source-{idea_id}")
    ]
    if candidates:
        reusable = candidates[0]
        transcript_path = reusable / "transcript.jsonl"
        already_has_seed = (
            transcript_path.exists()
            and any(
                json.loads(line).get("kind") == "brainstorm_start"
                for line in transcript_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            )
        )
        if not already_has_seed:
            _append_transcript(transcript_path, {
                "created_at": _now(),
                "role": "user",
                "kind": "brainstorm_start",
                "content": raw_text,
                "metadata": {"source_idea_id": idea_id},
            })
        _record_idea_brainstorm_link(root, metadata, reusable.name)
        return {"status": "reuse", "session_id": reusable.name, "source_idea_id": idea_id, "appended_seed_record": not already_has_seed}

    session_dir.mkdir(parents=True, exist_ok=True)
    transcript_path = session_dir / "transcript.jsonl"
    _append_transcript(transcript_path, {
        "created_at": _now(),
        "role": "user",
        "kind": "brainstorm_start",
        "content": raw_text,
        "metadata": {"source_idea_id": idea_id},
    })
    _record_idea_brainstorm_link(root, metadata, folder_name)
    return {"status": "ready", "session_id": folder_name, "source_idea_id": idea_id}


def _record_idea_brainstorm_link(root: Path, metadata: dict[str, Any], session_id: str) -> None:
    """Persist the latest brainstorm session on the source idea metadata."""
    from devflow.control_room.idea_foundry import _write_idea

    idea_id = str(metadata.get("id") or "").strip()
    if not idea_id:
        return
    session_path = f".devflow/brainstorms/{session_id}"
    sessions = list(metadata.get("brainstorm_session_ids") or [])
    if session_id not in sessions:
        sessions.append(session_id)
    paths = list(metadata.get("brainstorm_session_paths") or [])
    if session_path not in paths:
        paths.append(session_path)
    metadata["brainstorm_session_ids"] = sessions
    metadata["brainstorm_session_paths"] = paths
    metadata["latest_brainstorm_session_id"] = session_id
    metadata["latest_brainstorm_session_path"] = session_path
    metadata["updated_at"] = _now()
    _write_idea(root, metadata)
