"""Chat backend for the DevFlow UI brainstorm surface.

This module provides the server-side chat API that the embedded chat sidebar
uses. It reuses the existing brainstorm persistence (transcript.jsonl +
brainstorm.md sync) and the existing model-calling infrastructure
(HermesSubscriptionClient for subscription models, LocalModelClient for
local llama.cpp models).

The chat surface is the brainstorm stage of the product-building loop.
Conversations started here create pipeline runs at stage=idea and persist
transcripts that can be escalated to definition, planning, and build.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from devflow.control_room import brainstorm as br
from devflow.loop.registry import get_registry, ModelEntry


BRAINSTORM_SYSTEM = (
    "You are the DevFlow brainstorm partner. Turn a rough product idea into a "
    "clear, decision-ready Idea Brief without prematurely designing the whole "
    "system.\n\n"
    "## Brainstorm workflow (follow this order)\n"
    "1. CLARIFY the user, problem, desired outcome, and observable success.\n"
    "2. BOUND what is in scope, what is explicitly out of scope, and which "
    "existing repository, product, data, or environment the idea must respect.\n"
    "3. SURFACE only decisions that materially change the product or safe next "
    "stage. Ask focused questions instead of opening broad speculative branches.\n"
    "4. SYNTHESIZE the smallest coherent Idea Brief supported by the conversation. "
    "Clearly label assumptions and unresolved human decisions.\n"
    "5. STOP when the idea is defined enough for specification; do not drift into "
    "implementation planning unless the user asks.\n\n"
    "## Anti-patterns (do NOT do these)\n"
    "- Do not invent requirements, users, constraints, or integrations.\n"
    "- Do not turn one idea into a feature backlog or comprehensive architecture.\n"
    "- Do not ask questions already answered in the conversation.\n"
    "- Do not hide uncertainty behind confident prose.\n"
    "- Do not select or mention a model as part of the role; the runtime owns routing."
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Model listing
# ---------------------------------------------------------------------------

def list_chat_models() -> list[dict]:
    """Return all eligible models that can serve as the brainstorm/chat model.

    A model is chat-eligible if it is available, not retired, and has at
    least high_level_reasoning or code_generation capability (i.e. it can
    hold a conversation about building software).
    """
    reg = get_registry()
    chat_caps = {"high_level_reasoning", "code_generation", "ambiguity_resolution"}
    models: list[dict] = []
    for entry in reg.eligible():
        if not (set(entry.capabilities) & chat_caps):
            continue
        models.append(_model_to_dict(entry))
    return models


def _model_to_dict(entry: ModelEntry) -> dict:
    return {
        "name": entry.name,
        "display_name": entry.display_name,
        "provider": entry.provider,
        "transport": entry.transport,
        "cost_class": entry.cost_class,
        "context_window": entry.context_window,
        "notes": entry.notes,
    }


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------

def start_chat_session(
    root: Path | str,
    *,
    intent: str,
    model: Optional[str] = None,
) -> dict:
    """Start a new chat session and generate the first assistant response.

    Creates a pipeline run at stage=idea, writes the user's intent as the
    first message, calls the model, and persists the response. Returns
    session_id, run_id, model, and the assistant's response in one round-trip
    so the frontend doesn't need a separate send call for the first message.
    """
    root = Path(root).resolve()
    session_id, run_id = br.start_session(root, intent=intent)

    resolved_model = model or _default_model()
    if not resolved_model:
        raise ValueError("No model selected and no default available.")
    _set_session_model(root, session_id, resolved_model)

    reg = get_registry()
    entry = reg.get(resolved_model)
    if entry is None:
        raise ValueError(f"Unknown model: {resolved_model}")

    transcript = get_transcript(root, session_id)
    messages = _build_messages(transcript)
    content, usage = _call_model(entry, messages)

    br._append_transcript_line(br._transcript_path(root, session_id), {
        "created_at": _now(),
        "role": "assistant",
        "kind": "message",
        "content": content,
        "model": resolved_model,
    })
    br._sync_brainstorm_md(root, session_id, run_id)

    return {
        "session_id": session_id,
        "run_id": run_id,
        "model": resolved_model,
        "response": {
            "role": "assistant",
            "content": content,
            "model": resolved_model,
            "usage": usage,
        },
    }


def _default_model() -> str:
    """Return the default brainstorm model from the active profile."""
    from devflow.loop.routing import resolve_role_compatible
    try:
        slot = resolve_role_compatible("brainstorm")
        return slot.model_name
    except ValueError:
        return ""


def _session_dir(root: Path, session_id: str) -> Path:
    return root.resolve() / ".devflow" / "brainstorms" / session_id


def _model_path(root: Path, session_id: str) -> Path:
    return _session_dir(root, session_id) / "chat-model.json"


def _set_session_model(root: Path, session_id: str, model: str) -> None:
    path = _model_path(root, session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"model": model, "updated_at": _now()}, indent=2) + "\n",
        encoding="utf-8",
    )


def _get_session_model(root: Path, session_id: str) -> str:
    path = _model_path(root, session_id)
    if not path.exists():
        return _default_model()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return str(data.get("model") or _default_model())
    except (json.JSONDecodeError, OSError):
        return _default_model()


def list_chat_sessions(root: Path | str) -> list[dict]:
    """Return all chat sessions, newest first."""
    root = Path(root).resolve()
    brainstorms_dir = root / ".devflow" / "brainstorms"
    if not brainstorms_dir.exists():
        return []
    sessions: list[dict] = []
    for entry in sorted(brainstorms_dir.iterdir(), key=lambda e: e.name, reverse=True):
        if not entry.is_dir():
            continue
        session_id = entry.name
        transcript = br._read_transcript(br._transcript_path(root, session_id))
        first_user = next(
            (r for r in transcript if r.get("role") == "user" and r.get("content")),
            None,
        )
        run_id = br._read_link(root, session_id) or ""
        sessions.append({
            "session_id": session_id,
            "run_id": run_id,
            "model": _get_session_model(root, session_id),
            "message_count": len(transcript),
            "preview": (first_user.get("content", "")[:120] if first_user else ""),
            "updated_at": _session_mtime(entry),
        })
    return sessions


def _session_mtime(session_dir: Path) -> str:
    """Return the latest file mtime in a session directory as ISO string."""
    try:
        latest = max(
            (f.stat().st_mtime for f in session_dir.rglob("*") if f.is_file()),
            default=0,
        )
        if latest:
            return datetime.fromtimestamp(latest, tz=timezone.utc).isoformat()
    except OSError:
        pass
    return ""


# ---------------------------------------------------------------------------
# Transcript access
# ---------------------------------------------------------------------------

def get_transcript(root: Path | str, session_id: str) -> list[dict]:
    """Return the conversation history for a chat session."""
    root = Path(root).resolve()
    records = br._read_transcript(br._transcript_path(root, session_id))
    result: list[dict] = []
    for rec in records:
        if rec.get("kind") != "message":
            continue
        result.append({
            "role": rec.get("role", "unknown"),
            "content": rec.get("content", ""),
            "timestamp": rec.get("created_at", ""),
            "model": rec.get("model", ""),
        })
    return result


# ---------------------------------------------------------------------------
# Message dispatch — the core chat round-trip
# ---------------------------------------------------------------------------

def send_message(
    root: Path | str,
    *,
    session_id: str,
    message: str,
    model: Optional[str] = None,
) -> dict:
    """Send a user message and return the assistant's response.

    Appends the user message to the transcript, builds the full conversation
    history, calls the selected model, appends the response, and syncs to
    the pipeline run's brainstorm.md.

    For subscription models (hermes-chat transport), the conversation is
    flattened into a single prompt. For local models (openai-http), the
    full messages array is passed to the OpenAI-compatible endpoint.

    Returns a dict with the assistant's content, the model used, and usage
    metadata if available.
    """
    root = Path(root).resolve()
    if not message.strip():
        raise ValueError("Message cannot be empty.")

    resolved_model = model or _get_session_model(root, session_id)
    if not resolved_model:
        raise ValueError("No model selected and no default available.")

    # Persist the user message
    br.append_brainstorm(
        root, session_id=session_id, role="user", content=message,
    )

    # Build conversation history for the model call
    transcript = get_transcript(root, session_id)
    messages = _build_messages(transcript)

    # Resolve the model entry to determine transport
    reg = get_registry()
    entry = reg.get(resolved_model)
    if entry is None:
        raise ValueError(f"Unknown model: {resolved_model}")

    content, usage = _call_model(entry, messages)

    # Persist the assistant response
    br._append_transcript_line(br._transcript_path(root, session_id), {
        "created_at": _now(),
        "role": "assistant",
        "kind": "message",
        "content": content,
        "model": resolved_model,
    })
    run_id = br._read_link(root, session_id)
    if run_id:
        br._sync_brainstorm_md(root, session_id, run_id)

    # Persist the model selection
    _set_session_model(root, session_id, resolved_model)

    return {
        "session_id": session_id,
        "role": "assistant",
        "content": content,
        "model": resolved_model,
        "usage": usage,
    }


def _build_messages(transcript: list[dict]) -> list[dict]:
    """Convert transcript records into an OpenAI messages array."""
    messages: list[dict] = [{"role": "system", "content": BRAINSTORM_SYSTEM}]
    for rec in transcript:
        role = rec.get("role", "user")
        content = rec.get("content", "")
        if not content:
            continue
        messages.append({"role": role, "content": content})
    return messages


def _call_model(entry: ModelEntry, messages: list[dict]) -> tuple[str, dict]:
    """Call the model based on its transport and return (content, usage)."""
    if entry.transport == "hermes-chat":
        return _call_hermes_chat(entry, messages)
    elif entry.transport == "openai-http":
        return _call_openai_http(entry, messages)
    else:
        raise ValueError(f"Unsupported transport: {entry.transport}")


def _call_hermes_chat(entry: ModelEntry, messages: list[dict]) -> tuple[str, dict]:
    """Call a subscription model via the HermesSubscriptionClient."""
    from devflow.loop.execution import HermesSubscriptionClient

    client = HermesSubscriptionClient(entry.endpoint)
    content, usage = client.chat(messages=messages)
    return content, usage


def _call_openai_http(entry: ModelEntry, messages: list[dict]) -> tuple[str, dict]:
    """Call a local or remote OpenAI-compatible model.

    For local endpoints, the model router brings the configured model up first.
    """
    from devflow.loop.execution import LocalModelClient

    # Check if this is a local endpoint that needs lane management
    is_local = LocalModelClient._is_local_endpoint(entry.endpoint)
    if is_local:
        _ensure_local_lane(entry)

    if entry.model_id:
        client = LocalModelClient(entry.endpoint, model_name=entry.model_id)
    else:
        client = LocalModelClient(entry.endpoint)

    content, usage = client.chat(
        messages=messages,
        max_tokens=4096,
        temperature=0.7,
    )
    return content, usage


def _ensure_local_lane(entry: ModelEntry) -> None:
    """Bring up the correct local model on the shared llama.cpp server.

    Uses the model-router launcher directly with the model's path and alias,
    matching the pattern in execution.ensure_lane but without needing a role.
    """
    import os
    import subprocess
    from devflow.loop.execution import MODEL_ROUTER_SCRIPT

    if not entry.model_path:
        return
    port = entry.endpoint.rsplit(":", 1)[-1]
    env = dict(os.environ)
    env["MINI_QWEN_MODEL_PATH"] = os.path.expanduser(entry.model_path)
    env["MINI_MODEL_ALIAS"] = entry.model_id or entry.name
    subprocess.run(
        [str(MODEL_ROUTER_SCRIPT), "start", port],
        check=False, env=env,
    )


__all__ = [
    "list_chat_models",
    "start_chat_session",
    "list_chat_sessions",
    "get_transcript",
    "send_message",
]
