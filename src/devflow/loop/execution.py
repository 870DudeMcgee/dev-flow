"""Native V2 execution engine: real model-driven build/judge/verify workers.

This is the layer that closes the gap between the deterministic V2 spine
(``models``, ``adapter``, ``builder_judge``, ``verification``,
``planning_judge`` — all no-model adapters) and actual local-model work.

Single-flight guarantee (the "one large model resident at a time" rule):
  * Every model call runs inside ``acquire_role_slot`` from
    ``devflow.loop.model_router`` — a machine-wide filesystem lock. The lock
    path is identical regardless of role/model, so at most ONE role holds it
    at any instant, even if two servers happened to be up.
  * Before a call, ``ensure_lane`` brings the role's server up via the
    canonical ``~/.hermes/scripts/model-router`` launcher. That launcher
    swaps out any other heavy-group sibling first, so the resident model
    matches the role we are about to call.

Outputs are persisted through the existing adapters (``builder_judge``,
``verification``) and respect the canonical stage-transition map in
``models.py``. The engine adds the model-calling + lane-swap behavior; it
does not reinvent persistence or stage logic.
"""

from __future__ import annotations

import json
import os
import re
import glob
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from devflow.loop.model_router import acquire_role_slot, resolve_role_slot
from devflow.loop import builder_judge as bj
from devflow.loop import planning_judge as pj
from devflow.loop import verification as ver
from devflow.loop.adapter import load_loop_state, save_loop_state
from devflow.loop.pipeline_run import (
    append_pipeline_event,
    append_worker_feed_entry,
    cancellation_requested,
    clear_worker_live_output,
    load_pipeline_run,
    pipeline_runs_dir,
    read_execution_control,
    update_pipeline_run_record,
    update_execution_control,
    write_worker_live_output,
)
from devflow.loop.models import LoopStage, advance_stage
from devflow.loop.roles import get_role


DEFAULT_MAX_PLANNING_ROUNDS = 3
DEFAULT_MAX_BUILD_ROUNDS = 3
MAX_TARGET_FILES_PER_BUILD = 12  # raised from 6: this project builds the whole brief_intelligence package as one coherent packet so the judge sees all inter-file imports
ROLE_TOKEN_BUDGETS = {
    "builder": 16384,
    "planner": 4096,
    "judge": 2048,
    "planning_judge": 2048,
    "verifier": 2048,
}


# Canonical launcher. Overridable via env for tests / non-default homes.
MODEL_ROUTER_SCRIPT = Path(
    os.environ.get("DEVFLOW_MODEL_ROUTER")
    or os.path.expanduser("~/.hermes/scripts/model-router")
)

ClientFactory = Callable[..., "LocalModelClient"]


def _verification_env() -> dict[str, str]:
    env = dict(os.environ)
    env["PATH"] = f"{Path(sys.executable).parent}{os.pathsep}{env.get('PATH', '')}"
    return env


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------
@dataclass
class RoleResult:
    """Outcome of a single model-call role step."""

    role: str
    model: str
    endpoint: str
    content: str
    usage: dict
    raw: dict


class BuilderOutputError(ValueError):
    """Raised when builder output cannot be safely materialized."""


def build_packets(target_files: list[str]) -> list[dict]:
    """Partition an approved target list into bounded, ordered build packets."""
    unique = list(dict.fromkeys(str(path) for path in target_files))
    return [
        {
            "id": f"packet-{index // MAX_TARGET_FILES_PER_BUILD + 1:02d}",
            "target_files": unique[index:index + MAX_TARGET_FILES_PER_BUILD],
        }
        for index in range(0, len(unique), MAX_TARGET_FILES_PER_BUILD)
    ]


# ---------------------------------------------------------------------------
# Local OpenAI-compatible client (stdlib only — no new dependency)
# ---------------------------------------------------------------------------
class LocalModelClient:
    """Tiny OpenAI-compatible client for llama-server-style local endpoints.

    Also supports remote OpenAI-compatible endpoints (OpenRouter, etc.) when
    the endpoint URL is not localhost. In that case, the model name is
    extracted from the registry entry and the API key is read from env.
    """

    def __init__(
        self,
        endpoint: str,
        *,
        timeout: int = 240,
        model_name: Optional[str] = None,
        api_key: Optional[str] = None,
    ):
        self.endpoint = endpoint.rstrip("/")
        self.timeout = timeout
        self._model_id: Optional[str] = model_name
        self._api_key: Optional[str] = api_key
        self._is_remote = not self._is_local_endpoint(self.endpoint)

    @staticmethod
    def _is_local_endpoint(endpoint: str) -> bool:
        """True for localhost / 127.0.0.1 / 0.0.0.0 endpoints."""
        return any(
            host in endpoint
            for host in ("localhost", "127.0.0.1", "0.0.0.0", "[::1]")
        )

    def _resolve_api_key(self) -> Optional[str]:
        """Resolve the API key for remote endpoints."""
        if self._api_key:
            return self._api_key
        if not self._is_remote:
            return None
        # OpenRouter endpoints use OPENROUTER_API_KEY
        if "openrouter.ai" in self.endpoint:
            return os.environ.get("OPENROUTER_API_KEY")
        return None

    def _fetch_model_id(self) -> str:
        if self._model_id is not None:
            return self._model_id
        # For remote endpoints, don't probe /v1/models — use a generic name
        # and let the registry/routing layer supply the real model name.
        if self._is_remote:
            self._model_id = "remote-model"
            return self._model_id
        try:
            with urllib.request.urlopen(f"{self.endpoint}/v1/models", timeout=10) as r:
                data = json.loads(r.read().decode("utf-8"))
            models = data.get("data") or []
            if models:
                self._model_id = models[0].get("id")
        except Exception:
            pass
        if self._model_id is None:
            self._model_id = "local-model"
        return self._model_id

    @staticmethod
    def _chat_completions_url(endpoint: str) -> str:
        """Return the OpenAI chat-completions path without duplicating /v1."""
        base = endpoint.rstrip("/")
        suffix = "/chat/completions" if base.endswith("/v1") else "/v1/chat/completions"
        return f"{base}{suffix}"

    @staticmethod
    def _do_post(endpoint: str, payload: dict, timeout: int, api_key: Optional[str] = None) -> dict:
        body = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        req = urllib.request.Request(
            LocalModelClient._chat_completions_url(endpoint),
            data=body,
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))

    def chat(
        self,
        *,
        messages: list[dict],
        max_tokens: int = 2048,
        temperature: float = 0.0,
        reasoning: bool = False,
        stop: Optional[list[str]] = None,
    ) -> tuple[str, dict]:
        model_id = self._fetch_model_id()
        api_key = self._resolve_api_key()
        payload: dict = {
            "model": model_id,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if stop:
            payload["stop"] = stop
        if self._is_remote:
            payload["reasoning_effort"] = "low" if reasoning else "none"
            payload["include_reasoning"] = False
        # Ornith runs with --reasoning auto; disable the thinking trace so the
        # content budget is spent on the actual answer, not a CoT dump.
        if not reasoning and not self._is_remote:
            payload["chat_template_kwargs"] = {"enable_thinking": False}
        try:
            data = self._do_post(self.endpoint, payload, self.timeout, api_key)
        except urllib.error.HTTPError:
            # Some servers reject chat_template_kwargs; retry without it.
            if "chat_template_kwargs" in payload:
                payload.pop("chat_template_kwargs")
                data = self._do_post(self.endpoint, payload, self.timeout, api_key)
            else:
                raise
        content = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
        usage = data.get("usage", {}) or {}
        return content, usage

    def chat_stream(
        self,
        *,
        messages: list[dict],
        max_tokens: int = 2048,
        temperature: float = 0.0,
        reasoning: bool = False,
        stop: Optional[list[str]] = None,
        on_delta: Optional[Callable[[str], None]] = None,
        on_reasoning_delta: Optional[Callable[[str], None]] = None,
    ) -> tuple[str, dict, str, str]:
        """Stream an OpenAI-compatible response and expose each text delta.

        Returns ``(content, usage, finish_reason, reasoning_content)``.
        The 4th element captures the model's chain-of-thought (``reasoning_content``
        in llama-server / OpenAI-compatible streaming) so the operator can watch
        what the worker is *thinking*, not just its final output.
        """
        payload: dict = {
            "model": self._fetch_model_id(),
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if stop:
            payload["stop"] = stop
        if self._is_remote:
            payload["reasoning_effort"] = "low" if reasoning else "none"
            payload["include_reasoning"] = False
        if not reasoning and not self._is_remote:
            payload["chat_template_kwargs"] = {"enable_thinking": False}

        api_key = self._resolve_api_key()

        def request(active_payload: dict):
            headers = {"Content-Type": "application/json"}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
            req = urllib.request.Request(
                self._chat_completions_url(self.endpoint),
                data=json.dumps(active_payload).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            return urllib.request.urlopen(req, timeout=self.timeout)

        try:
            response = request(payload)
        except urllib.error.HTTPError:
            if "chat_template_kwargs" not in payload:
                raise
            payload.pop("chat_template_kwargs")
            response = request(payload)

        chunks: list[str] = []
        reasoning_chunks: list[str] = []
        usage: dict = {}
        finish_reason = ""
        with response:
            for raw_line in response:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line.startswith("data:"):
                    continue
                data_text = line[5:].strip()
                if not data_text or data_text == "[DONE]":
                    continue
                try:
                    data = json.loads(data_text)
                except json.JSONDecodeError:
                    continue
                if isinstance(data.get("usage"), dict):
                    usage = data["usage"]
                choice = (data.get("choices") or [{}])[0]
                delta = choice.get("delta") or {}
                text = delta.get("content") or ""
                if text:
                    chunks.append(text)
                    if on_delta:
                        on_delta(text)
                reasoning_text = delta.get("reasoning_content") or ""
                if reasoning_text:
                    reasoning_chunks.append(reasoning_text)
                    if on_reasoning_delta:
                        on_reasoning_delta(reasoning_text)
                if choice.get("finish_reason"):
                    finish_reason = str(choice["finish_reason"])
        return (
            "".join(chunks),
            usage,
            finish_reason or "stop",
            "".join(reasoning_chunks),
        )


class HermesSubscriptionClient:
    """GLM verifier client that routes through the user's Hermes subscription.

    Uses the ``hermes chat`` CLI (already configured with the user's Z.AI /
    OpenAI OAuth) so scoring/verification does NOT incur a per-token local API
    call. Returns the model text. Falls back to the configured GPT model if
    GLM fails.
    """

    def __init__(self, endpoint: str, *, timeout: int = 60):
        # endpoint encodes the routing, e.g. "hermes://chat/zai/glm-5.2"
        self.endpoint = endpoint
        self.timeout = timeout
        parts = endpoint.replace("hermes://", "").strip("/").split("/")
        # expect: chat/<provider>/<model>
        self.provider = parts[1] if len(parts) > 1 else "zai"
        self.model = parts[2] if len(parts) > 2 else "glm-5.2"
        self.fallback_provider = "openai-codex"
        self.fallback_model = "gpt-5.5"

    def _call(self, prompt: str, *, provider: str, model: str) -> str:
        # hermes chat -q expects a single-line prompt; newlines in the arg can
        # hang or misbehave, so flatten to spaces for the CLI invocation.
        flat = " ".join(str(prompt).split())
        cmd = [
            "hermes", "chat",
            "-q", flat,
            "-Q",
            "-m", model,
            "--provider", provider,
        ]
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=self.timeout
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"hermes chat failed ({provider}/{model}): "
                f"{proc.stderr.strip()[:200]}"
            )
        return proc.stdout

    def chat(
        self,
        *,
        messages: list[dict],
        max_tokens: int = 2048,
        temperature: float = 0.0,
        reasoning: bool = False,
        stop: Optional[list[str]] = None,
    ) -> tuple[str, dict]:
        user_prompt = "\n".join(
            m.get("content", "") for m in messages if m.get("role") == "user"
        )
        system_prompt = "\n".join(
            m.get("content", "") for m in messages if m.get("role") == "system"
        )
        full_prompt = (
            f"{system_prompt}\n\n{user_prompt}" if system_prompt else user_prompt
        )
        try:
            content = self._call(full_prompt, provider=self.provider, model=self.model)
        except Exception:
            content = self._call(
                full_prompt, provider=self.fallback_provider, model=self.fallback_model
            )
        return content, {}


# ---------------------------------------------------------------------------
# Lane lifecycle (uses the real model-router launcher)
# ---------------------------------------------------------------------------
def ensure_lane(role: str, *, script: Optional[Path] = None) -> None:
    """Bring the role's server up, swapping out any different local model.

    For local openai-http endpoints (llama-server), delegates to
    ``model-router start <port>`` — the canonical launcher.  When the
    resolved slot carries a ``model_path``, it is passed via the
    ``MINI_QWEN_MODEL_PATH`` and ``MINI_MODEL_ALIAS`` env vars so the
    launcher loads the correct GGUF.

    For hermes-chat (subscription) and remote openai-http (OpenRouter),
    this is a no-op: no local server to start.
    """
    slot = resolve_role_slot(role)
    # Subscription and remote-cloud endpoints don't need a local server.
    if slot.transport == "hermes-chat":
        return
    # Remote openai-http endpoints (OpenRouter etc.) don't need a local server.
    if "openrouter.ai" in slot.endpoint:
        return
    if not LocalModelClient._is_local_endpoint(slot.endpoint):
        return
    port = slot.endpoint.rsplit(":", 1)[-1]
    script = script or MODEL_ROUTER_SCRIPT
    env = dict(os.environ)
    if slot.model_path:
        env["MINI_QWEN_MODEL_PATH"] = os.path.expanduser(slot.model_path)
        env["MINI_MODEL_ALIAS"] = slot.model_id or slot.model_name
    # model-router prints; we only care about the side effect.
    subprocess.run([str(script), "start", port], check=False, env=env)


# ---------------------------------------------------------------------------
# Core role runner (single-flight inside acquire_role_slot)
# ---------------------------------------------------------------------------
def run_role(
    root: Path | str,
    *,
    role: str,
    system_prompt: str,
    user_prompt: str,
    task_id: Optional[str] = None,
    worker_id: Optional[str] = None,
    max_tokens: Optional[int] = None,
    reasoning: Optional[bool] = None,
    ensure_lane_on: bool = True,
    client_factory: Optional[ClientFactory] = None,
) -> RoleResult:
    slot = resolve_role_slot(role)
    role_definition = get_role(slot.role)
    resolved_reasoning = (
        reasoning
        if reasoning is not None
        else bool(role_definition and role_definition.reasoning)
    )
    requested_max_tokens = int(max_tokens or ROLE_TOKEN_BUDGETS.get(role, 2048))
    if ensure_lane_on:
        ensure_lane(role)

    # Transport-aware client selection: hermes-chat → HermesSubscriptionClient,
    # everything else → LocalModelClient. Caller can override via client_factory.
    if client_factory is not None:
        factory = client_factory
    elif slot.transport == "hermes-chat":
        factory = HermesSubscriptionClient
    else:
        factory = LocalModelClient

    # Only resident local servers require the machine-wide single-flight lock.
    # Cloud HTTP (OpenRouter) and Hermes subscription calls neither consume a
    # local model slot nor need to block local planner/builder/judge work.
    needs_local_lock = (
        slot.transport == "openai-http"
        and LocalModelClient._is_local_endpoint(slot.endpoint)
    )
    slot_lock = (
        acquire_role_slot(Path(root), role=role, task_id=task_id, worker_id=worker_id)
        if needs_local_lock
        else nullcontext(slot)
    )
    with slot_lock:
        # A role is "started" only after it owns its applicable execution slot.
        append_worker_feed_entry(root, task_id or slot.role, {
            "event": "started",
            "role": role,
            "model": slot.model,
            "endpoint": slot.endpoint,
            "worker_id": worker_id,
            "task_id": task_id,
            "requested_max_tokens": requested_max_tokens,
            "system_prompt": system_prompt[:500],
            "user_prompt": user_prompt[:2000],
        })
        existing_control = read_execution_control(root, task_id or slot.role)
        heartbeat_status = (
            existing_control.get("status")
            if existing_control.get("status") in {"cancelling", "cancelled"}
            else "running"
        )
        update_execution_control(
            root, task_id or slot.role,
            status=heartbeat_status, active_role=role, model=slot.model,
            requested_max_tokens=requested_max_tokens,
            heartbeat_at=datetime.now(timezone.utc).isoformat(),
        )
        # Pass model_id to LocalModelClient for remote endpoints (OpenRouter etc.)
        if factory is LocalModelClient and slot.model_id:
            client = factory(slot.endpoint, model_name=slot.model_id)
        else:
            client = factory(slot.endpoint)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        streamed: list[str] = []
        streamed_reasoning: list[str] = []
        streamed_size = 0
        last_publish_at = 0.0
        last_publish_size = 0

        def _publish_live_output(status_override: Optional[str] = None) -> None:
            """Publish the current streamed content + reasoning to worker-live.json."""
            control = read_execution_control(root, task_id or slot.role)
            current_status = status_override or (
                control.get("status")
                if control.get("status") in {"cancelling", "cancelled"}
                else "running"
            )
            live_payload: dict = {
                "event": "streaming",
                "status": current_status,
                "role": role,
                "model": slot.model,
                "content": "".join(streamed),
                "requested_max_tokens": requested_max_tokens,
            }
            reasoning_text = "".join(streamed_reasoning)
            if reasoning_text:
                live_payload["reasoning_content"] = reasoning_text
            write_worker_live_output(root, task_id or slot.role, live_payload)
            update_execution_control(
                root, task_id or slot.role,
                status=current_status, active_role=role,
                heartbeat_at=datetime.now(timezone.utc).isoformat(),
            )

        def on_delta(delta: str) -> None:
            nonlocal last_publish_at, last_publish_size, streamed_size
            streamed.append(delta)
            streamed_size += len(delta)
            now = time.monotonic()
            current_size = streamed_size
            if now - last_publish_at < 0.25 and current_size - last_publish_size < 512:
                return
            _publish_live_output()
            last_publish_at = now
            last_publish_size = current_size

        def on_reasoning_delta(delta: str) -> None:
            streamed_reasoning.append(delta)

        finish_reason = "stop"
        reasoning_content = ""
        try:
            if hasattr(client, "chat_stream"):
                result = client.chat_stream(
                    messages=messages,
                    max_tokens=requested_max_tokens,
                    reasoning=resolved_reasoning,
                    on_delta=on_delta,
                    on_reasoning_delta=on_reasoning_delta,
                )
                # Support both 3-tuple (legacy) and 4-tuple (reasoning) returns.
                if len(result) >= 4:
                    content, usage, finish_reason, reasoning_content = result[:4]
                else:
                    content, usage, finish_reason = result[:3]
                    reasoning_content = ""
            else:
                content, usage = client.chat(
                    messages=messages,
                    max_tokens=requested_max_tokens,
                    reasoning=resolved_reasoning,
                )
        except Exception as exc:
            partial = "".join(streamed)
            partial_reasoning = "".join(streamed_reasoning)
            error_payload: dict = {
                "event": "failed", "status": "stalled", "role": role,
                "model": slot.model, "content": partial,
                "requested_max_tokens": requested_max_tokens,
                "error": str(exc),
            }
            if partial_reasoning:
                error_payload["reasoning_content"] = partial_reasoning
            write_worker_live_output(root, task_id or slot.role, error_payload)
            failed_entry: dict = {
                "event": "failed", "role": role, "model": slot.model,
                "content": partial, "error": str(exc),
                "requested_max_tokens": requested_max_tokens,
            }
            if partial_reasoning:
                failed_entry["reasoning_content"] = partial_reasoning
            append_worker_feed_entry(root, task_id or slot.role, failed_entry)
            update_execution_control(
                root, task_id or slot.role,
                status="stalled", active_role=role, error=str(exc),
            )
            raise
        token_cap_reached = finish_reason == "length"
        append_pipeline_event(
            root,
            task_id or slot.role,
            {
                "event": "model_call",
                "role": role,
                "model": slot.model,
                "usage": usage,
                "requested_max_tokens": requested_max_tokens,
                "finish_reason": finish_reason,
            },
        )

        # Write "completed" entry with the actual model output
        completed_entry: dict = {
            "event": "completed",
            "role": role,
            "model": slot.model,
            "worker_id": worker_id,
            "task_id": task_id,
            "content": content,
            "usage": usage,
            "requested_max_tokens": requested_max_tokens,
            "finish_reason": finish_reason,
            "token_cap_reached": token_cap_reached,
        }
        if reasoning_content:
            completed_entry["reasoning_content"] = reasoning_content
        append_worker_feed_entry(root, task_id or slot.role, completed_entry)
        clear_worker_live_output(root, task_id or slot.role)
        control = read_execution_control(root, task_id or slot.role)
        completed_status = (
            control.get("status")
            if control.get("status") in {"cancelling", "cancelled"}
            else "running"
        )
        update_execution_control(
            root, task_id or slot.role,
            status=completed_status, active_role=None, last_completed_role=role,
            heartbeat_at=datetime.now(timezone.utc).isoformat(),
        )

        return RoleResult(
            role=role,
            model=slot.model,
            endpoint=slot.endpoint,
            content=content,
            usage=usage,
            raw={
                "requested_max_tokens": requested_max_tokens,
                "finish_reason": finish_reason,
                "token_cap_reached": token_cap_reached,
                "reasoning_content": reasoning_content,
            },
        )


# ---------------------------------------------------------------------------
# Workers (persist through existing deterministic adapters)
# ---------------------------------------------------------------------------
BUILDER_SYSTEM = (
    "You are the DevFlow builder. Produce a concrete code implementation that "
    "satisfies the assignment and its definition of done. Output ONLY the file "
    "contents — no explanations, no commentary, no introductions, no summaries. "
    "For multiple files, use this EXACT format for each file:\n"
    "# src/path/to/file.py\n"
    "<file contents>\n\n"
    "# tests/path/to/test.py\n"
    "<file contents>\n\n"
    "Each file block MUST start with '# path/to/file.py' on its own line "
    "(matching one of the declared target files). Do NOT wrap output in markdown "
    "code fences. Do NOT include test runs or verification output. "
    "Do NOT refuse to produce code when existing code context is provided — "
    "use that context to extend the existing modules. Start with the first "
    "file marker, end with the last file's content."
)

PLANNER_SYSTEM = (
    "You are the DevFlow planner. Given a task, produce a bounded, concrete "
    "implementation plan as a single JSON object and nothing else: "
    '{"spec": "<what to build and why>", "plan": "<step-by-step steps>", '
    '"target_files": ["relative/path/to/file.py"], '
    '"packets": [{"id": "packet-01", "target_files": ["at most six files"]}], '
    '"verification_command": "<shell command that verifies the change>"}'
)
JUDGE_SYSTEM = (
    "You are the DevFlow judge. Evaluate the builder output against the "
    "definition of done. Respond with a single JSON object and nothing else: "
    '{"status": "passed"|"failed"|"needs_review", "rationale": "..."}.'
)

PLANNING_JUDGE_SYSTEM = (
    "You are the DevFlow planning judge using Qwen. Review the planner's spec "
    "and execution plan against repo evidence and DevFlow's definition of done. "
    "Greenfield files are allowed when the plan clearly identifies them as files "
    "to create; do not reject a plan merely because new target files do not yet "
    "exist. Return one JSON object only with: "
    '{"decision":"approve|revise|block|escalate_to_user",'
    '"repo_grounding":"...","task_boundaries":"...",'
    '"verification_reality":"...","overbuild_risk":"...",'
    '"simpler_path":"...","required_changes":["..."],'
    '"next_safe_action":"..."}'
)


def _loop_exhausted(
    root: Path | str,
    run_id: str,
    *,
    role: str,
    max_rounds: int,
    last_decision: str,
    next_action: str,
) -> None:
    append_worker_feed_entry(root, run_id, {
        "event": "loop_exhausted",
        "role": role,
        "model": "devflow-orchestrator",
        "content": json.dumps({
            "max_rounds": max_rounds,
            "last_decision": last_decision,
            "next_safe_action": next_action,
        }, indent=2),
        "usage": {},
    })
    # Finalize execution-control to a terminal state so the status board
    # cannot show a stale "running" when the loop is actually parked at
    # human_decision.  active_role cleared; last_completed_role preserved.
    update_execution_control(root, run_id, status="idle", active_role=None)
    # Advance loop state to human_decision with an explicit next action
    # so the board and JSON artifacts agree on stage and next step.
    try:
        state = load_loop_state(root, run_id)
        if state.stage not in (LoopStage.complete, LoopStage.blocked):
            state = state.model_copy(update={
                "stage": LoopStage.human_decision,
                "next_human_decision": next_action,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            })
            save_loop_state(root, state)
    except Exception:
        pass


def _builder_preflight(
    workspace: Path,
    declared_files: list[str],
) -> Optional[str]:
    """Deterministic completeness check before the judge runs.

    Returns ``None`` if all checks pass, or a concise failure reason.
    Checks:
      1. Every declared target file exists in the workspace.
      2. Every ``.py`` file parses without SyntaxError.
    """
    missing = [
        f for f in declared_files
        if not (workspace / f).exists()
    ]
    if missing:
        return f"Missing declared files: {', '.join(sorted(missing))}"

    for rel in declared_files:
        if not rel.endswith(".py"):
            continue
        fpath = workspace / rel
        try:
            source = fpath.read_text(encoding="utf-8", errors="replace")
            compile(source, str(fpath), "exec")
        except SyntaxError as exc:
            return f"Syntax error in {rel}: {exc}"

    return None


def _write_build_judge_summary(
    root: Path | str,
    run_id: str,
    *,
    packet_id: str,
    build_rounds: list[dict],
    judge_decision: str,
    judge_rationale: str,
    build_cap_exhausted: bool,
    builder_model: str = "",
    judge_model: str = "",
) -> None:
    """Persist a compact build/judge summary with the decisive judge rationale.

    This is the single artifact an operator should read to understand the
    outcome of a build/judge run — not the raw worker feed.
    """
    # Collect per-round reasons (compact)
    rounds_compact = []
    for rnd in build_rounds:
        rounds_compact.append({
            "round": rnd.get("round"),
            "decision": rnd.get("decision"),
            "rationale": str(rnd.get("rationale", ""))[:500],
        })

    summary = {
        "packet_id": packet_id,
        "judge_decision": judge_decision,
        "build_cap_exhausted": build_cap_exhausted,
        "build_rounds": len(build_rounds),
        "builder_model": builder_model,
        "judge_model": judge_model,
        "final_judge_rationale": judge_rationale[:1000],
        "rounds": rounds_compact,
    }
    update_pipeline_run_record(
        root, run_id, f"packet-{packet_id}-build-judge-summary.json", summary,
    )


def _read_record(root: Path | str, run_id: str, name: str) -> Optional[str]:
    data = load_pipeline_run(root, run_id)
    val = data.get(name)
    if isinstance(val, str):
        return val
    if isinstance(val, dict):
        return json.dumps(val)
    return None


def _write_record(root: Path | str, run_id: str, name: str, content: str) -> None:
    """Persist a named text record for the run (JSON string stored as-is)."""
    update_pipeline_run_record(root, run_id, name, content)


def _run_workspace_tests(
    workspace: Path,
    *,
    test_files: Optional[list[str]] = None,
) -> dict:
    """Run bounded workspace tests and return a compact result dict.

    A build workspace contains only the staged implementation plus its changed
    tests. Running every copied repository test would fail collection for
    unrelated modules absent from the staged source tree, so callers should
    pass changed test paths from the build manifest.
    """
    result = {"exit_code": -1, "passed": 0, "failed": 0, "errors": 0, "summary": "", "working_directory": str(workspace)}
    if not workspace.exists():
        result["summary"] = "no workspace directory; tests not run"
        return result
    # CRITICAL: pytest discovers config (pyproject.toml) by walking UP from the
    # cwd. When the workspace is nested under the repo (e.g.
    # .devflow/pipeline-runs/<id>/workspace/), pytest finds the REPO's
    # pyproject.toml which has pythonpath=["src","."] pointing at the REPO's
    # src/, not the workspace's. This causes tests to import the repo's version
    # of the package instead of the builder's freshly-built copy.
    #
    # Fix: use --rootdir (absolute) to pin the workspace, and --override-ini
    # to set pythonpath to the workspace's own src/ so pytest does not inherit
    # the repo's pyproject.toml pythonpath.
    ws_abs = workspace.resolve()
    ws_src = ws_abs / "src"
    # Write a root-level conftest.py in the workspace that injects the
    # workspace's src/ into sys.path BEFORE any test collection. This is the
    # most reliable way to prevent pytest from resolving imports to the repo's
    # src/ directory (which happens because pytest discovers the repo's
    # pyproject.toml with pythonpath=["src","."]).
    ws_conftest = ws_abs / "conftest.py"
    conftest_body = (
        '"""Auto-generated by DevFlow: isolate workspace imports."""\n'
        'import sys\n'
        'from pathlib import Path\n'
        f'ROOT = Path({str(ws_abs)!r})\n'
        f'SRC = Path({str(ws_src)!r})\n'
        'for path in (ROOT, SRC):\n'
        '    if str(path) not in sys.path:\n'
        '        sys.path.insert(0, str(path))\n'
    )
    try:
        ws_conftest.write_text(conftest_body, encoding="utf-8")
    except Exception:
        pass
    staged_test_files = [
        str(ws_abs / rel)
        for rel in (test_files or [])
        if rel.startswith(("tests/", "test/")) and (ws_abs / rel).is_file()
    ]
    # Fall back to the workspace tests directory only for legacy callers that
    # do not provide a build manifest.
    pytest_targets = staged_test_files or [str(ws_abs / "tests")]
    pytest_args = [
        sys.executable, "-m", "pytest",
        *pytest_targets,
        "-q", "--no-header",
        "-p", "no:cacheprovider",
        f"--rootdir={ws_abs}",
        f"--override-ini=pythonpath={ws_abs} {ws_src}",
        "--override-ini=testpaths=tests",
    ]
    try:
        proc = subprocess.run(
            pytest_args,
            cwd=str(ws_abs),
            capture_output=True,
            text=True,
            timeout=180,
            env={
                **os.environ,
                "PYTHONPATH": os.pathsep.join((str(ws_abs), str(ws_src))),
                "HERMES_ISOLATE_CHILD": "1",
            },
        )
    except FileNotFoundError:
        result["summary"] = "pytest not installed; tests not run"
        return result
    except Exception as exc:  # subprocess timeout / other
        result["summary"] = f"test run error: {exc}"
        return result
    result["exit_code"] = proc.returncode
    out = (proc.stdout or "") + (proc.stderr or "")
    # Parse the classic pytest summary line: "8 passed" / "2 failed, 1 passed"
    import re as _re
    m_pass = _re.search(r"(\d+) passed", out)
    m_fail = _re.search(r"(\d+) failed", out)
    m_err = _re.search(r"(\d+) error", out)
    result["passed"] = int(m_pass.group(1)) if m_pass else 0
    result["failed"] = int(m_fail.group(1)) if m_fail else 0
    result["errors"] = int(m_err.group(1)) if m_err else 0
    # Fallback: if no textual summary was found but exit code is 0, count
    # the dots in the progress line (e.g. "........" = 8 passed).  This
    # fixes the bug where pytest -q --no-header produces only dots without
    # a "N passed" line in some versions.
    if result["passed"] == 0 and result["failed"] == 0 and result["errors"] == 0:
        # Count leading dots from the progress output (before any summary line)
        progress_match = _re.search(r"^(\.+F?E?)+", out, _re.MULTILINE)
        if progress_match and proc.returncode == 0:
            dots = progress_match.group(0).count(".")
            if dots > 0:
                result["passed"] = dots
    # Safety: nonzero exit code must not be recorded as all-pass.
    if proc.returncode != 0 and result["failed"] == 0 and result["errors"] == 0:
        # The run failed but we didn't parse failure counts — record at least
        # one error so consumers don't mistake this for a clean pass.
        result["errors"] = max(result["errors"], 1)
    # Keep the tail (failures/summary) so GLM sees what broke.
    result["summary"] = out[-1500:]
    return result


def _planner_context_block(root: Path | str, run_id: str) -> str:
    """Return persisted human/orchestrator context the planner must satisfy."""
    intent = (_read_record(root, run_id, "intent.md") or "").strip()
    brainstorm = (_read_record(root, run_id, "brainstorm.md") or "").strip()
    readiness = (_read_record(root, run_id, "readiness-packet.md") or "").strip()
    parts: list[str] = []
    if intent:
        parts.append(f"# Persisted Intent\n{intent}")
    if readiness:
        parts.append(
            "# Definition of Done / Readiness Packet\n"
            f"{readiness}\n\n"
            "The spec and plan MUST satisfy this Definition of Done. Do not replace "
            "frontier-model semantic scoring, Obsidian output, cron/backfill, or "
            "Brainstorm Queue requirements with a standalone keyword CLI unless the "
            "readiness packet explicitly narrows the scope. Frontier API clients must "
            "use an injectable transport so local tests can mock provider responses "
            "without replacing the semantic integration contract."
        )
    if brainstorm:
        parts.append(f"# Brainstorm Transcript\n{brainstorm}")
    return "\n\n".join(parts)


def _safe_target_paths(root: Path, target_files: list[str]) -> list[str]:
    safe: list[str] = []
    for file_name in target_files:
        requested = Path(str(file_name))
        if requested.is_absolute() or ".." in requested.parts or requested == Path("."):
            raise BuilderOutputError(f"Unsafe target file: {file_name}")
        resolved = (root / requested).resolve()
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise BuilderOutputError(f"Unsafe target file: {file_name}") from exc
        safe.append(requested.as_posix())
    return list(dict.fromkeys(safe))


def _strip_diff_fence(content: str) -> str:
    text = content.strip()
    if text.startswith("```diff") and text.endswith("```"):
        return text[len("```diff"): -3].strip() + "\n"
    if text.startswith("```") and text.endswith("```"):
        first_newline = text.find("\n")
        return text[first_newline + 1: -3].strip() + "\n"
    return content


def _split_and_write_greenfield(
    workspace: Path, content: str, declared: list[str]
) -> list[str]:
    """Split a multi-file greenfield builder output and write each file.

    Local models output files using path-comment markers. The two most common
    formats are:

    1. Comment-header format (no code fences):
       ``# src/foo.py``
       ``code line 1``
       ``code line 2``

    2. Code-fence format with path comment inside or above:
       ```` ```python ``
       ``# src/foo.py``
       ``code...``
       ```` ``` ````

    This parser detects path-comment markers that match declared target files
    and splits the content accordingly.
    """
    declared_set = {Path(d).as_posix() for d in declared}
    declared_lower = {d.lower(): d for d in declared_set}

    # Build a regex that matches path-comment markers for declared files.
    # It looks for "# path/to/file" at start of a line (possibly with leading
    # whitespace), where path matches one of the declared files.
    declared_alt = "|".join(
        re.escape(d) for d in sorted(declared_set, key=len, reverse=True)
    )

    # Match: optional whitespace, #, whitespace, then a declared path
    marker_re = re.compile(
        r"(?:^|\n)[ \t]*#[ \t]*(" + declared_alt + r")[ \t]*\n",
        re.IGNORECASE,
    )

    # Find all marker positions
    markers = list(marker_re.finditer(content))
    if not markers:
        raise BuilderOutputError(
            f"Could not parse multi-file greenfield output. "
            f"Expected '# path/to/file' markers for: {', '.join(sorted(declared_set))}. "
            f"Use '# src/foo.py' as the first line of each file block."
        )

    segments: list[tuple[str, str]] = []
    for i, m in enumerate(markers):
        raw_path = m.group(1)
        norm = Path(raw_path).as_posix()
        # Resolve to actual declared path (case-insensitive)
        if norm in declared_set:
            actual = norm
        elif norm.lower() in declared_lower:
            actual = declared_lower[norm.lower()]
        else:
            continue

        # Content starts right after the marker line, ends at next marker or EOF
        start = m.end()
        end = markers[i + 1].start() if i + 1 < len(markers) else len(content)
        code = content[start:end].rstrip() + "\n"

        # Strip trailing code fence if present (for fence format)
        # Also strip leading code fence if present
        lines = code.split("\n")
        # Remove leading ```language line if present
        if lines and re.match(r"^```[a-zA-Z]*$", lines[0].strip()):
            lines = lines[1:]
        # Remove trailing ``` if present
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        code = "\n".join(lines).strip() + "\n"

        segments.append((actual, code))

    # Deduplicate — keep first occurrence
    seen: set[str] = set()
    written: list[str] = []
    for path, code in segments:
        if path in seen:
            continue
        destination = workspace / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(code, encoding="utf-8")
        written.append(path)
        seen.add(path)

    missing = sorted(declared_set - seen)
    if missing:
        raise BuilderOutputError(
            f"Builder output is missing declared files: {', '.join(missing)}"
        )

    return written


def materialize_builder_output(
    root: Path | str,
    run_id: str,
    content: str,
    *,
    target_files: list[str],
) -> dict:
    """Materialize one bounded builder result in an isolated run workspace."""
    root_path = Path(root).resolve()
    load_pipeline_run(root_path, run_id)  # validates run id and existence
    declared = _safe_target_paths(root_path, target_files)
    if not declared:
        raise BuilderOutputError("Builder requires at least one declared target file")

    runs_dir = pipeline_runs_dir(root_path).resolve()
    run_dir = (runs_dir / run_id).resolve()
    try:
        run_dir.relative_to(runs_dir)
    except ValueError as exc:
        raise BuilderOutputError("Pipeline run workspace escaped the run root") from exc
    workspace = run_dir / "workspace"
    if workspace.exists():
        shutil.rmtree(workspace)
    workspace.mkdir(parents=True)
    # Seed the workspace with the declared target files AND any sibling files
    # in the same package directory so the builder can see/extend existing code.
    # This is critical for extension tasks: if the builder is told to extend
    # main.py, it must be able to see parser.py, models.py, etc.
    context_files: set[str] = set(declared)
    for declared_file in declared:
        declared_path = Path(declared_file)
        parent = declared_path.parent
        # If this file is in a package (has __init__.py or other .py siblings),
        # include ALL siblings as read-only context.
        repo_parent = root_path / parent
        if repo_parent.is_dir():
            for sibling in repo_parent.iterdir():
                if sibling.is_file() and sibling.suffix == ".py":
                    rel = sibling.relative_to(root_path).as_posix()
                    context_files.add(rel)
    for relative in context_files:
        source = root_path / relative
        destination = workspace / relative
        if source.is_file():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
    # Also copy any Reference/ or fixture data directories at the root.
    for context_dir_name in ("Reference", "fixtures", "testdata"):
        ctx_dir = root_path / context_dir_name
        if ctx_dir.is_dir():
            dst_ctx = workspace / context_dir_name
            if dst_ctx.exists():
                shutil.rmtree(dst_ctx)
            shutil.copytree(ctx_dir, dst_ctx)

    implementation = _strip_diff_fence(content)
    is_diff = bool(re.search(r"(?m)^diff --git a/.+ b/.+$", implementation))
    changed_files: list[str]
    if is_diff:
        changed_files = []
        for match in re.finditer(r"(?m)^\+\+\+ (?:b/)?(.+)$", implementation):
            value = match.group(1).strip()
            if value == "/dev/null":
                continue
            changed_files.append(Path(value).as_posix())
        changed_files = list(dict.fromkeys(changed_files))
        undeclared = sorted(set(changed_files) - set(declared))
        if undeclared:
            raise BuilderOutputError(
                f"Builder patch contains undeclared target files: {', '.join(undeclared)}"
            )
        if not changed_files:
            raise BuilderOutputError("Builder unified diff contains no writable files")
        patch_path = run_dir / "build-diff.patch"
        patch_path.write_text(implementation, encoding="utf-8")
        checked = subprocess.run(
            ["git", "apply", "--check", "--whitespace=nowarn", str(patch_path)],
            cwd=str(workspace), capture_output=True, text=True,
        )
        if checked.returncode != 0:
            raise BuilderOutputError(
                f"Builder unified diff is incomplete or invalid: {(checked.stderr or checked.stdout).strip()}"
            )
        applied = subprocess.run(
            ["git", "apply", "--whitespace=nowarn", str(patch_path)],
            cwd=str(workspace), capture_output=True, text=True,
        )
        if applied.returncode != 0:
            raise BuilderOutputError(
                f"Builder unified diff could not be applied: {(applied.stderr or applied.stdout).strip()}"
            )
    else:
        # Multi-file greenfield support: split content by file-path markers.
        # Local models naturally output files as separate code blocks with
        # path headers like "# src/foo.py" or "src/foo.py" or "```python\n# path".
        if len(declared) == 1:
            changed_files = declared
            destination = workspace / declared[0]
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(implementation, encoding="utf-8")
            update_pipeline_run_record(root_path, run_id, "build-diff.patch", implementation)
        else:
            changed_files = _split_and_write_greenfield(
                workspace, implementation, declared
            )
            update_pipeline_run_record(root_path, run_id, "build-diff.patch", implementation)

    manifest = {
        "workspace": str(workspace),
        "changed_files": changed_files,
        "declared_target_files": declared,
        "patch_path": str(run_dir / "build-diff.patch"),
    }
    update_pipeline_run_record(root_path, run_id, "build-manifest.json", manifest)
    return manifest


def run_builder(
    root: Path | str,
    run_id: str,
    *,
    assignment: str,
    definition_of_done: str,
    target_files: Optional[list[str]] = None,
    verification_command: Optional[str] = None,
    revision_feedback: Optional[str] = None,
    round_index: int = 1,
    max_tokens: int = ROLE_TOKEN_BUDGETS["builder"],
    worker_id: str = "native-builder",
    ensure_lane_on: bool = True,
    client_factory: Optional[ClientFactory] = None,
) -> RoleResult:
    if len(target_files or []) > MAX_TARGET_FILES_PER_BUILD:
        raise BuilderOutputError(
            f"A builder packet may touch at most {MAX_TARGET_FILES_PER_BUILD} files; "
            "use build-packets.json and dispatch the packets separately."
        )
    state = load_loop_state(root, run_id)
    if state.stage not in (LoopStage.assignment, LoopStage.build_judge):
        raise ValueError(
            f"Expected assignment or build_judge, got {state.stage.value}."
        )

    # Deterministic prep/link (no model call) -> advances to build_judge.
    bj.prepare_builder_judge_assignment(
        root,
        bj.BuilderJudgeAssignment(
            run_id=run_id,
            assignment_id=run_id,
            definition_of_done=definition_of_done,
            target_files=target_files or [],
            verification_command=verification_command,
            builder_judge_run_id=run_id,
        ),
    )

    files_block = "\n".join(target_files or [])

    # Include existing source context so the builder can see what it's extending.
    # This is critical: without it, the builder refuses to write code referencing
    # modules it cannot see.
    root_path = Path(root)
    context_parts: list[str] = []
    for tf in (target_files or []):
        tf_path = root_path / tf
        if tf_path.exists() and tf.endswith(".py"):
            context_parts.append(f"# Existing {tf}\n{tf_path.read_text()}")
        # Include sibling .py files in the same package
        parent = tf_path.parent
        if parent.is_dir():
            for sibling in sorted(parent.iterdir()):
                if (sibling.suffix == ".py" and sibling != tf_path
                        and sibling.name != "__init__.py"
                        and sibling.stat().st_size < 4000):
                    rel = sibling.relative_to(root_path).as_posix()
                    context_parts.append(
                        f"# Existing {rel} (read-only context)\n{sibling.read_text()}"
                    )
    context_block = "\n\n".join(context_parts[-6000:]) if context_parts else ""

    user = (
        f"# Builder/Judge Round\n{round_index}\n\n"
        f"# Assignment\n{assignment}\n\n"
        f"# Definition of Done\n{definition_of_done}\n\n"
        f"# Target files\n{files_block}\n"
    )
    if context_block:
        user += f"\n# Existing code context (extend, do NOT rewrite these)\n{context_block}\n"
    if revision_feedback:
        user += f"\n# Previous judge feedback to fix\n{revision_feedback}\n"

    result = run_role(
        root,
        role="builder",
        system_prompt=BUILDER_SYSTEM,
        user_prompt=user,
        task_id=run_id,
        worker_id=worker_id,
        max_tokens=max_tokens,
        ensure_lane_on=ensure_lane_on,
        client_factory=client_factory,
    )

    manifest = materialize_builder_output(
        root, run_id, result.content, target_files=target_files or []
    )
    if verification_command:
        proc = subprocess.run(
            verification_command,
            shell=True,
            cwd=manifest["workspace"],
            capture_output=True,
            text=True,
            timeout=300,
            env=_verification_env(),
        )
        build_verification = {
            "command": verification_command,
            "exit_code": proc.returncode,
            "status": "passed" if proc.returncode == 0 else "failed",
            "summary": (proc.stdout or proc.stderr or "")[-4000:],
            "workspace": manifest["workspace"],
        }
        update_pipeline_run_record(
            root, run_id, "build-verification.json", build_verification
        )
        result.raw["build_verification"] = build_verification
    result.raw["build_manifest"] = manifest
    # Keep the raw response as evidence; the workspace manifest is authoritative.
    update_pipeline_run_record(root, run_id, "loop-packet.md", result.content)
    return result


def _parse_judge_decision(text: str) -> str:
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            obj = json.loads(m.group(0))
            s = str(obj.get("status", "")).lower()
            if s in ("passed", "failed", "needs_review"):
                return s
        except Exception:
            pass
    low = text.lower()
    for s in ("passed", "failed", "needs_review"):
        if s in low:
            return s
    return "needs_review"


def _parse_judge_payload(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            obj = json.loads(m.group(0))
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass
    return {"status": _parse_judge_decision(text), "rationale": text.strip()}


def _planning_decision_from_payload(payload: dict) -> pj.JudgeDecision:
    raw = str(payload.get("decision") or payload.get("status") or "").lower()
    aliases = {
        "approved": "approve",
        "pass": "approve",
        "passed": "approve",
        "fail": "revise",
        "failed": "revise",
        "needs_review": "revise",
        "needs-revision": "revise",
        "escalate": "escalate_to_user",
        "escalate_to_human": "escalate_to_user",
    }
    raw = aliases.get(raw, raw)
    if raw in {d.value for d in pj.JudgeDecision}:
        return pj.JudgeDecision(raw)
    return pj.JudgeDecision.revise


def _planning_report_from_payload(
    run_id: str,
    payload: dict,
) -> pj.PlanningJudgeReport:
    decision = _planning_decision_from_payload(payload)
    required_changes = payload.get("required_changes") or []
    if isinstance(required_changes, str):
        required_changes = [required_changes]
    if decision == pj.JudgeDecision.approve:
        required_changes = []
    return pj.PlanningJudgeReport(
        run_id=run_id,
        decision=decision,
        repo_grounding=str(payload.get("repo_grounding") or "Qwen planning judge reviewed repo grounding."),
        task_boundaries=str(payload.get("task_boundaries") or "Qwen planning judge reviewed task boundaries."),
        verification_reality=str(payload.get("verification_reality") or "Qwen planning judge reviewed verification reality."),
        overbuild_risk=str(payload.get("overbuild_risk") or "Qwen planning judge reviewed overbuild risk."),
        simpler_path=str(payload.get("simpler_path") or "Qwen planning judge reviewed simpler paths."),
        required_changes=[str(item) for item in required_changes],
        next_safe_action=str(payload.get("next_safe_action") or "Return to the orchestrator for the next safe action."),
        created_at=datetime.now(timezone.utc).isoformat(),
    )


def _record_planning_judge_report(
    root: Path | str,
    run_id: str,
    report: pj.PlanningJudgeReport,
) -> None:
    update_pipeline_run_record(
        root,
        run_id,
        "planning-judge.json",
        report.model_dump_json(indent=2, ensure_ascii=False),
    )
    append_worker_feed_entry(root, run_id, {
        "event": "completed",
        "role": "planning_judge_report",
        "model": "qwen-27b-q5km",
        "content": json.dumps({
            "decision": report.decision.value,
            "required_changes": report.required_changes,
            "next_safe_action": report.next_safe_action,
            "repo_grounding": report.repo_grounding,
            "task_boundaries": report.task_boundaries,
            "overbuild_risk": report.overbuild_risk,
            "simpler_path": report.simpler_path,
        }, indent=2),
        "usage": {},
    })

    state = load_loop_state(root, run_id)
    state = state.model_copy(update={"planning_judge_path": "planning-judge.json"})
    if report.decision == pj.JudgeDecision.approve and state.stage == LoopStage.planning_judge:
        state = advance_stage(state, LoopStage.assignment)
    elif report.decision == pj.JudgeDecision.block:
        state = advance_stage(state, LoopStage.blocked)
    elif report.decision == pj.JudgeDecision.escalate_to_user:
        state = state.model_copy(update={
            "stage": LoopStage.blocked,
            "next_human_decision": "Make a human decision on the planning judge escalation.",
        })
    save_loop_state(root, state)


def run_planning_judge_model(
    root: Path | str,
    run_id: str,
    *,
    evidence: pj.PlanningEvidence,
    planner_content: str,
    worker_id: str = "native-planning-judge",
    ensure_lane_on: bool = True,
    client_factory: Optional[ClientFactory] = None,
) -> tuple[RoleResult, pj.PlanningJudgeReport]:
    """Run Qwen as the planning judge, using deterministic checks as context only."""
    deterministic_report = pj.judge_plan(evidence)
    spec = _read_record(root, run_id, "spec.md") or ""
    plan = _read_record(root, run_id, "plan.md") or ""
    persisted_context = _planner_context_block(root, run_id)
    user = (
        f"# Planner Output\n{planner_content}\n\n"
        f"# Persisted Human Context And Definition Of Done\n{persisted_context}\n\n"
        f"# Persisted Spec\n{spec}\n\n"
        f"# Persisted Plan\n{plan}\n\n"
        f"# Evidence JSON\n{evidence.model_dump_json(indent=2)}\n\n"
        f"# Deterministic Guardrail Findings (context, not final decision)\n"
        f"{deterministic_report.model_dump_json(indent=2)}\n\n"
        "Decide whether this plan is executable AND satisfies the persisted "
        "Definition of Done. Approve greenfield files when they are plausible "
        "files to create and verification is concrete, but REVISE when the plan "
        "solves a smaller or different problem than the readiness packet."
    )
    result = run_role(
        root,
        role="planning_judge",
        system_prompt=PLANNING_JUDGE_SYSTEM,
        user_prompt=user,
        task_id=run_id,
        worker_id=worker_id,
        max_tokens=ROLE_TOKEN_BUDGETS["planning_judge"],
        ensure_lane_on=ensure_lane_on,
        client_factory=client_factory,
    )
    payload = _parse_judge_payload(result.content)
    report = _planning_report_from_payload(run_id, payload)
    _record_planning_judge_report(root, run_id, report)
    return result, report


def run_judge(
    root: Path | str,
    run_id: str,
    *,
    definition_of_done: str,
    worker_id: str = "native-judge",
    ensure_lane_on: bool = True,
    client_factory: Optional[ClientFactory] = None,
) -> tuple[RoleResult, str]:
    state = load_loop_state(root, run_id)
    if state.stage != LoopStage.build_judge:
        raise ValueError(f"Expected build_judge, got {state.stage.value}.")

    build_evidence = _read_record(root, run_id, "build-diff.patch") or ""
    build_manifest = _read_record(root, run_id, "build-manifest.json") or ""
    build_verification = _read_record(root, run_id, "build-verification.json") or ""

    # List existing test files in the repo so the judge knows which tests
    # already exist and were NOT part of this builder's target.  Without this
    # context the judge rejects builds for "missing tests" that are actually
    # pre-existing files the builder was explicitly told not to rewrite.
    root_path = Path(root)
    existing_tests: list[str] = []
    for test_dir in [root_path / "tests", root_path / "test"]:
        if test_dir.is_dir():
            for f in test_dir.rglob("test_*.py"):
                rel = f.relative_to(root_path).as_posix()
                existing_tests.append(rel)
    existing_tests_block = (
        "\n".join(f"  - {t}" for t in sorted(existing_tests))
        if existing_tests else "(none found)"
    )

    user = (
        f"# Definition of Done\n{definition_of_done}\n\n"
        f"# Materialized Builder Changes\n{build_evidence}\n\n"
        f"# Build Manifest\n{build_manifest}\n\n"
        f"# Pre-Judge Verification\n{build_verification}\n\n"
        f"# Pre-existing test files in repo (NOT rebuilt this round)\n"
        f"These tests already exist in the repository and were intentionally "
        f"excluded from the builder target. Do NOT fail the build for missing "
        f"coverage of modules whose tests appear here.\n{existing_tests_block}\n"
    )

    result = run_role(
        root,
        role="judge",
        system_prompt=JUDGE_SYSTEM,
        user_prompt=user,
        task_id=run_id,
        worker_id=worker_id,
        max_tokens=ROLE_TOKEN_BUDGETS["judge"],
        ensure_lane_on=ensure_lane_on,
        client_factory=client_factory,
    )

    decision = _parse_judge_decision(result.content)
    bj.record_builder_judge_result(
        root,
        run_id,
        builder_judge_run_id=run_id,
        status=decision,
        evidence_path="loop-packet.md",
    )
    return result, decision


def _parse_planner_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        raise ValueError(f"Planner did not return JSON: {text[:200]!r}")
    return json.loads(m.group(0))


def run_planner(
    root: Path | str,
    run_id: str,
    *,
    topic: str,
    target_files: Optional[list[str]] = None,
    revision_feedback: Optional[str] = None,
    round_index: int = 1,
    worker_id: str = "native-planner",
    max_tokens: int = ROLE_TOKEN_BUDGETS["planner"],
    ensure_lane_on: bool = True,
    client_factory: Optional[ClientFactory] = None,
) -> tuple[RoleResult, pj.PlanningJudgeReport]:
    """Run the planner lane (8087) then the deterministic planning judge.

    Produces spec.md + plan.md artifacts, builds PlanningEvidence from the
    model output, and evaluates it via ``pj.run_planning_judge`` (which writes
    planning-judge.json and advances the stage on approve).
    """
    state = load_loop_state(root, run_id)
    if state.stage != LoopStage.planning_judge:
        raise ValueError(f"Expected planning_judge, got {state.stage.value}.")

    files_block = "\n".join(target_files or [])
    persisted_context = _planner_context_block(root, run_id)
    user = (
        f"# Planning Round\n{round_index}\n\n"
        f"# Task\n{topic}\n\n"
        f"# Persisted Human Context And Definition Of Done\n{persisted_context}\n\n"
        f"# Existing target files to plan against\n{files_block}\n"
    )
    if revision_feedback:
        user += f"\n# Previous planning judge feedback to fix\n{revision_feedback}\n"
    result = run_role(
        root,
        role="planner",
        system_prompt=PLANNER_SYSTEM,
        user_prompt=user,
        task_id=run_id,
        worker_id=worker_id,
        max_tokens=max_tokens,
        ensure_lane_on=ensure_lane_on,
        client_factory=client_factory,
    )

    plan = _parse_planner_json(result.content)
    spec = plan.get("spec", "")
    plan_text = plan.get("plan", "")
    planned_files = plan.get("target_files", target_files or [])
    packets = plan.get("packets") or build_packets(list(planned_files))
    verification_command = plan.get("verification_command")

    update_pipeline_run_record(root, run_id, "spec.md", spec)
    update_pipeline_run_record(root, run_id, "plan.md", plan_text)
    update_pipeline_run_record(root, run_id, "build-packets.json", packets)
    state = load_loop_state(root, run_id)
    state = state.model_copy(update={"spec_path": "spec.md", "plan_path": "plan.md"})
    save_loop_state(root, state)

    root_path = Path(root)
    files_exist = all(
        (root_path / f).exists() for f in planned_files
    ) if planned_files else False

    evidence = pj.PlanningEvidence(
        run_id=run_id,
        plan_path="plan.md",
        spec_path="spec.md",
        target_files=planned_files,
        verification_command=verification_command,
        constraints=[],
        files_exist=files_exist,
        has_verification=bool(verification_command),
    )
    _, report = run_planning_judge_model(
        root,
        run_id,
        evidence=evidence,
        planner_content=result.content,
        worker_id=f"{worker_id}-planning-judge",
        ensure_lane_on=ensure_lane_on,
        client_factory=client_factory,
    )
    return result, report


def run_planning_loop(
    root: Path | str,
    run_id: str,
    *,
    topic: str,
    target_files: Optional[list[str]] = None,
    max_rounds: int = DEFAULT_MAX_PLANNING_ROUNDS,
    worker_id: str = "native-planner",
    ensure_lane_on: bool = True,
    client_factory: Optional[ClientFactory] = None,
) -> dict:
    """Run planner → planning judge until approved, blocked, or capped."""
    rounds: list[dict] = []
    last_result: Optional[RoleResult] = None
    last_report: Optional[pj.PlanningJudgeReport] = None
    feedback: Optional[str] = None

    for round_index in range(1, max_rounds + 1):
        result, report = run_planner(
            root,
            run_id,
            topic=topic,
            target_files=target_files,
            revision_feedback=feedback,
            round_index=round_index,
            worker_id=worker_id,
            ensure_lane_on=ensure_lane_on,
            client_factory=client_factory,
        )
        last_result = result
        last_report = report
        rounds.append({
            "round": round_index,
            "planner": result,
            "decision": report.decision.value,
            "required_changes": report.required_changes,
            "next_safe_action": report.next_safe_action,
        })
        if report.decision == pj.JudgeDecision.approve:
            break
        if report.decision in (pj.JudgeDecision.block, pj.JudgeDecision.escalate_to_user):
            break
        feedback = json.dumps({
            "decision": report.decision.value,
            "required_changes": report.required_changes,
            "next_safe_action": report.next_safe_action,
        }, indent=2)

    cap_exhausted = bool(
        last_report
        and last_report.decision == pj.JudgeDecision.revise
        and len(rounds) >= max_rounds
    )
    if cap_exhausted and last_report:
        _loop_exhausted(
            root,
            run_id,
            role="planning_loop",
            max_rounds=max_rounds,
            last_decision=last_report.decision.value,
            next_action=last_report.next_safe_action,
        )

    return {
        "planner": last_result,
        "planning_report": last_report,
        "planning_decision": last_report.decision.value if last_report else None,
        "planning_rounds": rounds,
        "planning_cap_exhausted": cap_exhausted,
    }


def run_plan_build_judge(
    root: Path | str,
    run_id: str,
    *,
    topic: str,
    target_files: Optional[list[str]] = None,
    definition_of_done: str,
    max_planning_rounds: int = DEFAULT_MAX_PLANNING_ROUNDS,
    max_build_rounds: int = DEFAULT_MAX_BUILD_ROUNDS,
    worker_id: str = "native-executor",
    ensure_lane_on: bool = True,
    client_factory: Optional[ClientFactory] = None,
) -> dict:
    """Full capped plan/judge loop → build/judge loop chain."""
    planning_loop = run_planning_loop(
        root,
        run_id,
        topic=topic,
        target_files=target_files,
        max_rounds=max_planning_rounds,
        worker_id=worker_id,
        ensure_lane_on=ensure_lane_on,
        client_factory=client_factory,
    )
    planning_report = planning_loop["planning_report"]

    out: dict = {
        "planner": planning_loop["planner"],
        "planning_decision": planning_loop["planning_decision"],
        "planning_rounds": planning_loop["planning_rounds"],
        "planning_cap_exhausted": planning_loop["planning_cap_exhausted"],
        "build": None,
        "judge": None,
        "decision": None,
        "verification": None,
        "build_rounds": [],
        "build_cap_exhausted": False,
    }

    # Only proceed to build if the planning judge approved.
    if not planning_report or planning_report.decision != pj.JudgeDecision.approve:
        return out

    assignment = (
        f"# Spec\n{planning_report.repo_grounding}\n\n"
        f"# Plan\n{(target_files or [])}\n\n"
        f"Implement per the planner output for: {topic}"
    )
    out.update(run_build_judge_verify(
        root,
        run_id,
        assignment=assignment,
        definition_of_done=definition_of_done,
        target_files=target_files,
        verification_command=None,
        max_rounds=max_build_rounds,
        worker_id=worker_id,
        ensure_lane_on=ensure_lane_on,
        client_factory=client_factory,
    ))
    return out


def run_verification(
    root: Path | str,
    run_id: str,
    *,
    verification_command: str,
    worker_id: str = "native-verify",
    working_directory: Path | str | None = None,
) -> ver.VerificationReceipt:
    """Execute the verification command (shell) and record a receipt.

    No model call — but the command is the pipeline's own verification_command,
    not arbitrary input. Advances to human_decision on pass.
    """
    state = load_loop_state(root, run_id)
    if state.stage != LoopStage.verification:
        raise ValueError(f"Expected verification, got {state.stage.value}.")

    proc = subprocess.run(
        verification_command,
        shell=True,
        capture_output=True,
        text=True,
        timeout=300,
        cwd=str(working_directory or Path(root).resolve()),
        env=_verification_env(),
    )
    status = (
        ver.VerificationStatus.passed
        if proc.returncode == 0
        else ver.VerificationStatus.failed
    )
    receipt = ver.VerificationReceipt(
        run_id=run_id,
        receipt_id=f"vr-{int(time.time() * 1000)}",
        status=status,
        command=verification_command,
        summary=(proc.stdout or proc.stderr or "")[-2000:],
        evidence_path=None,
        exit_code=proc.returncode,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    ver.record_verification_receipt(root, receipt)
    return receipt


GLM_VERIFIER_SYSTEM = (
    "You are the autonomous DevFlow verifier. You review build plus judge "
    "evidence and decide whether the implementation satisfies the Definition "
    "of Done. Respond with a single JSON object and nothing else: a status "
    "field set to passed, failed, or needs_review, and a rationale field with "
    "a short explanation. Pass only if the code is coherent, importable, and "
    "meets the DoD. Use needs_review for borderline cases a human should "
    "confirm."
)


def run_glm_verification(
    root: Path | str,
    run_id: str,
    *,
    definition_of_done: str,
    worker_id: str = "glm-verifier",
    client_factory: Optional[ClientFactory] = None,
) -> ver.VerificationReceipt:
    """Autonomous verification via a GLM agent (Hermes Z.AI subscription).

    Reads the current build-diff + judge result, asks GLM to verify against the
    DoD, parses the decision, and records a VerificationReceipt (advancing the
    loop on pass). Does NOT use a per-token API — routes through Hermes.

    Falls back to the local verifier role only if the Hermes call is
    unrecoverable.
    """
    state = load_loop_state(root, run_id)
    if state.stage != LoopStage.verification:
        raise ValueError(f"Expected verification, got {state.stage.value}.")

    import json as _json
    import re as _re

    # Read the build-diff as evidence (used in the code excerpt below).
    _read_record(root, run_id, "build-diff.patch")  # noqa: B018 — validates existence
    # Pull the most recent judge decision from the run dir (best-effort).
    judge_text = "unknown"
    try:
        summaries = sorted(
            glob.glob(str(Path(root) / run_id / "packet-*-build-judge-summary.json"))
        )
        if summaries:
            with open(summaries[-1]) as _f:
                judge_text = _json.load(_f).get("judge_decision", "unknown")
    except Exception:
        judge_text = "unknown"

    # Build a BOUNDED code excerpt from the actual on-disk files listed in the
    # build manifest: for each source file, surface its top-level def/class
    # signatures (truncated per file). This lets GLM judge real coherence
    # without dumping the entire 17KB build-diff (which blows GLM's context).
    manifest = _read_record(root, run_id, "build-manifest.json") or "{}"
    try:
        changed = _json.loads(manifest).get("changed_files", []) or []
    except Exception:
        changed = []
    workspace = ""
    try:
        workspace = _json.loads(manifest).get("workspace", "")
    except Exception:
        workspace = ""

    excerpt_parts: list[str] = []
    per_file_cap = 900  # chars per file (signatures + imports + Item fields)
    _sig_re = _re.compile(r"^\s*(def |class |async def )")
    _import_re = _re.compile(r"^\s*(from |import )")
    for rel in changed:
        if rel.endswith("__init__.py"):
            continue
        fpath = Path(workspace) / rel if workspace else Path(root) / run_id / "workspace" / rel
        if not fpath.exists():
            continue
        try:
            lines = fpath.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception:
            continue
        kept: list[str] = []
        capture_item = False
        for ln in lines:
            if _sig_re.match(ln) or _import_re.match(ln):
                kept.append(ln.strip())
            # also capture the Item dataclass field definitions
            if ln.strip().startswith("class Item"):
                capture_item = True
                kept.append(ln.strip())
            elif capture_item:
                stripped = ln.strip()
                if stripped and not stripped.startswith("#"):
                    kept.append(stripped)
                # stop capturing once we leave the class body (indent drops)
                if stripped and not ln.startswith(" ") and not ln.startswith("\t") and "class Item" not in stripped:
                    capture_item = False
        if not kept:
            continue
        joined = "\n".join(kept)[:per_file_cap]
        excerpt_parts.append(f"## {rel}\n{joined}")
    code_excerpt = "\n\n".join(excerpt_parts)

    # Run only build-manifest test files inside the staged workspace. The
    # workspace intentionally omits unrelated source modules, so a full copied
    # repository suite would produce irrelevant collection errors.
    test_result = _run_workspace_tests(
        Path(workspace) if workspace else Path(root) / run_id / "workspace",
        test_files=changed,
    )
    try:
        _write_record(root, run_id, "test-result.json", _json.dumps(test_result))
    except Exception:
        pass

    dod_head = definition_of_done.strip().splitlines()[:10]

    # List existing test files so the verifier doesn't flag missing tests
    # that already exist in the repo (same fix as run_judge).
    root_path = Path(root)
    existing_tests_v: list[str] = []
    for test_dir in [root_path / "tests", root_path / "test"]:
        if test_dir.is_dir():
            for f in test_dir.rglob("test_*.py"):
                rel = f.relative_to(root_path).as_posix()
                existing_tests_v.append(rel)
    existing_tests_v_block = (
        "\n".join(f"  - {t}" for t in sorted(existing_tests_v))
        if existing_tests_v else "(none)"
    )

    test_block = (
        f"# Test results (actual pytest run)\n"
        f"exit_code: {test_result['exit_code']}\n"
        f"passed: {test_result['passed']}  failed: {test_result['failed']}  "
        f"errors: {test_result['errors']}\n"
        f"{test_result['summary'].strip()[:1500]}"
    )
    # Test signatures alone can hide the assertions that satisfy a narrow DoD.
    # Include a bounded head+tail excerpt for each changed test file so the
    # verifier can see the real asserted behavior without receiving the whole
    # suite.
    changed_test_parts: list[str] = []
    for rel in changed:
        if not rel.startswith(("tests/", "test/")):
            continue
        test_path = Path(workspace) / rel if workspace else Path(root) / run_id / "workspace" / rel
        try:
            text = test_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        excerpt = text if len(text) <= 2400 else f"{text[:600]}\n...\n{text[-1800:]}"
        changed_test_parts.append(f"## {rel}\n{excerpt}")
    changed_test_evidence = "\n\n".join(changed_test_parts) or "(no changed test file available)"
    user = (
        "# Definition of Done (head)\n" + "\n".join(dod_head) + "\n\n"
        f"# Prior Judge Decision\n{judge_text}\n\n"
        "# Built source (ACTUAL signatures extracted from the built files):\n"
        f"{code_excerpt}\n\n"
        f"# Changed test-file evidence (ACTUAL staged test content)\n{changed_test_evidence}\n\n"
        f"{test_block}\n\n"
        f"# Pre-existing test files in repo (NOT rebuilt this round)\n"
        f"Do NOT flag missing coverage for modules whose tests appear here.\n"
        f"{existing_tests_v_block}\n\n"
        "You are verifying coherence from the supplied signatures, staged test "
        "result, Definition of Done, and prior judge decision. Confirm: (1) each "
        "Definition-of-Done API is present in the supplied built files, (2) the "
        "reported test command passed with exit code 0, (3) imports referenced by "
        "the changed files are either stdlib, third-party dependencies, or supplied "
        "project symbols, and (4) no supplied evidence contradicts the prior judge. "
        "A failing test run must be 'failed'. Use needs_review only when the "
        "provided evidence is genuinely insufficient. Output only the JSON decision."
    )

    # Route through the verifier role's assigned transport. The verifier may
    # be GLM (hermes-chat), GPT Luna (hermes-chat), or HY3 (openai-http).
    factory = client_factory
    slot = resolve_role_slot("glm_verifier")
    if factory is None:
        if slot.transport == "hermes-chat":
            factory = HermesSubscriptionClient
        else:
            # For openai-http (e.g. HY3), use LocalModelClient with model_id
            factory = LocalModelClient
    try:
        append_worker_feed_entry(root, run_id, {
            "event": "started",
            "role": "glm_verifier",
            "model": slot.model,
            "provider": slot.provider,
            "worker_id": worker_id,
            "task_id": run_id,
        })
        # Construct client with model_id for remote HTTP endpoints
        if factory is LocalModelClient and slot.model_id:
            client = factory(slot.endpoint, model_name=slot.model_id)
        else:
            client = factory(slot.endpoint)
        content, _ = client.chat(
            messages=[
                {"role": "system", "content": GLM_VERIFIER_SYSTEM},
                {"role": "user", "content": user},
            ],
            max_tokens=ROLE_TOKEN_BUDGETS.get("verifier", 2048),
            reasoning=True,
        )
        decision = _parse_judge_decision(content)  # reuse judge payload parser
        append_worker_feed_entry(root, run_id, {
            "event": "completed",
            "role": "glm_verifier",
            "model": slot.model,
            "content": content[:2000],
            "decision": decision,
        })
    except Exception as exc:  # never let the verifier hang the loop
        decision = "needs_review"
        content = f"GLM verifier error: {exc!r}"

    status = (
        ver.VerificationStatus.passed if decision == "passed"
        else ver.VerificationStatus.needs_review if decision == "needs_review"
        else ver.VerificationStatus.failed
    )
    receipt = ver.VerificationReceipt(
        run_id=run_id,
        receipt_id=f"vr-glm-{int(time.time() * 1000)}",
        status=status,
        command="glm_verifier (hermes chat zai/glm-5.2)",
        summary=f"GLM verifier decision: {decision}\n{content[:1500]}",
        evidence_path=None,
        exit_code=0 if decision == "passed" else 1,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    ver.record_verification_receipt(root, receipt)
    return receipt


def _auto_verify_enabled(root: Path | str, run_id: str) -> bool:
    """True when the run's loop state has auto_verify turned on."""
    try:
        return bool(load_loop_state(root, run_id).auto_verify)
    except Exception:
        return False


def trigger_autonomous_run(
    root: Path | str,
    run_id: str,
    *,
    assignment: str,
    definition_of_done: str,
    target_files: Optional[list[str]] = None,
    loop_cap: int = 3,
    worker_id: str = "autonomous-operator",
    ensure_lane_on: bool = True,
    client_factory: Optional[ClientFactory] = None,
) -> dict:
    """Run the full autonomous loop with GLM auto-verify, bounded by loop_cap.

    No UI. Cycles build -> judge -> (GLM verify) until the verification stage
    reaches human_decision with a passing receipt, the loop_cap is exhausted,
    or the run is blocked/cancelled. Each cycle increments loop_iteration.
    """
    state = load_loop_state(root, run_id)
    state = state.model_copy(update={"auto_verify": True, "loop_cap": loop_cap})
    save_loop_state(root, state)

    result: dict = {}
    for iteration in range(1, loop_cap + 1):
        state = load_loop_state(root, run_id)
        if state.stage in (LoopStage.complete, LoopStage.blocked):
            break
        state = state.model_copy(update={"loop_iteration": iteration})
        save_loop_state(root, state)

        result = run_build_judge_verify(
            root, run_id,
            assignment=assignment,
            definition_of_done=definition_of_done,
            target_files=target_files,
            verification_command=None,  # GLM verifier handles verification
            max_rounds=3,
            worker_id=worker_id,
            ensure_lane_on=ensure_lane_on,
            client_factory=client_factory,
        )
        # After a passing judge + GLM verify, stage is human_decision (parked).
        # In autonomous mode we treat a verified pass as a completed cycle.
        state = load_loop_state(root, run_id)
        if state.stage == LoopStage.human_decision and state.verification_receipts:
            result["autonomous_complete"] = True
            break
        if state.stage == LoopStage.blocked:
            break

    final_state = load_loop_state(root, run_id)
    result["loop_iteration"] = final_state.loop_iteration
    result["loop_cap"] = final_state.loop_cap
    result["auto_verify"] = final_state.auto_verify
    result["final_stage"] = final_state.stage.value
    return result


# ---------------------------------------------------------------------------
# Pipeline orchestrator (serialized build -> judge -> verify)
# ---------------------------------------------------------------------------
def run_build_judge_verify(
    root: Path | str,
    run_id: str,
    *,
    assignment: str,
    definition_of_done: str,
    target_files: Optional[list[str]] = None,
    verification_command: Optional[str] = None,
    max_rounds: int = DEFAULT_MAX_BUILD_ROUNDS,
    worker_id: str = "native-executor",
    ensure_lane_on: bool = True,
    client_factory: Optional[ClientFactory] = None,
    max_tokens: int = ROLE_TOKEN_BUDGETS["builder"],
) -> dict:
    """Run build → judge until DoD passes or the capped loop is exhausted.

    Each model step swaps in its lane via ``ensure_lane`` (single-flight).
    Judge runs only after build; verification only after a passing judge.
    """
    build: Optional[RoleResult] = None
    judge_result: Optional[RoleResult] = None
    decision: Optional[str] = None
    verification: Optional[ver.VerificationReceipt] = None
    rounds: list[dict] = []
    feedback: Optional[str] = None
    update_execution_control(root, run_id, status="running", cancel_mode=None)

    for round_index in range(1, max_rounds + 1):
        if cancellation_requested(root, run_id):
            decision = "cancelled"
            break
        build = run_builder(
            root,
            run_id,
            assignment=assignment,
            definition_of_done=definition_of_done,
            target_files=target_files,
            verification_command=verification_command,
            revision_feedback=feedback,
            round_index=round_index,
            worker_id=worker_id,
            ensure_lane_on=ensure_lane_on,
            client_factory=client_factory,
            max_tokens=max_tokens,
        )
        if cancellation_requested(root, run_id):
            decision = "cancelled"
            break
        # Deterministic preflight: check files exist and Python parses.
        # If it fails, skip the judge and feed the reason to the next round.
        manifest = (build.raw.get("build_manifest") or {}) if build else {}
        ws_path = manifest.get("workspace", "")
        declared = manifest.get("declared_target_files", [])
        preflight_failure = None
        if ws_path and declared:
            preflight_failure = _builder_preflight(Path(ws_path), declared)
        if preflight_failure:
            decision = "failed"
            payload = {"status": "failed", "rationale": preflight_failure}
            judge_result = RoleResult(
                role="judge",
                model="preflight",
                endpoint="",
                content=json.dumps(payload),
                usage={},
                raw={"preflight": True},
            )
            rounds.append({
                "round": round_index,
                "build": build,
                "judge": judge_result,
                "decision": decision,
                "rationale": preflight_failure,
            })
            feedback = preflight_failure
        else:
            judge_result, decision = run_judge(
                root,
                run_id,
                definition_of_done=definition_of_done,
                worker_id=worker_id,
                ensure_lane_on=ensure_lane_on,
                client_factory=client_factory,
            )
            payload = _parse_judge_payload(judge_result.content)
            rounds.append({
                "round": round_index,
                "build": build,
                "judge": judge_result,
                "decision": decision,
                "rationale": payload.get("rationale", ""),
            })
        if decision == "passed":
            if verification_command:
                verification = run_verification(
                    root, run_id,
                    verification_command=verification_command,
                    working_directory=(build.raw.get("build_manifest") or {}).get("workspace"),
                )
            elif _auto_verify_enabled(root, run_id):
                # Autonomous path: GLM agent verifies through Hermes subscription.
                verification = run_glm_verification(
                    root, run_id,
                    definition_of_done=definition_of_done,
                    worker_id=worker_id,
                    client_factory=client_factory,
                )
            break
        feedback = json.dumps(payload, indent=2)

    if decision == "cancelled":
        update_execution_control(root, run_id, status="cancelled", active_role=None)
        append_worker_feed_entry(root, run_id, {
            "event": "cancelled", "role": "orchestrator", "model": "devflow",
            "content": json.dumps({"decision": "cancelled", "next_safe_action": "Inspect preserved evidence before retrying."}),
        })
    elif decision == "passed":
        update_execution_control(root, run_id, status="idle", active_role=None)
    cap_exhausted = bool(
        decision not in {"passed", "cancelled"} and len(rounds) >= max_rounds
    )
    if cap_exhausted:
        _loop_exhausted(
            root,
            run_id,
            role="build_judge_loop",
            max_rounds=max_rounds,
            last_decision=decision or "unknown",
            next_action="Return to the orchestrator with the last judge feedback.",
        )

    # Persist a compact build/judge summary with the decisive rationale.
    # This is the single artifact an operator reads — not the raw worker feed.
    final_rationale = ""
    if rounds:
        final_rationale = str(rounds[-1].get("rationale", ""))
    _write_build_judge_summary(
        root, run_id,
        packet_id="consolidated",
        build_rounds=rounds,
        judge_decision=decision or "unknown",
        judge_rationale=final_rationale,
        build_cap_exhausted=cap_exhausted,
        builder_model=(build.model if build else ""),
        judge_model=(judge_result.model if judge_result else ""),
    )

    return {
        "build": build,
        "judge": judge_result,
        "decision": decision,
        "verification": verification,
        "build_rounds": rounds,
        "build_cap_exhausted": cap_exhausted,
    }


__all__ = [
    "RoleResult",
    "LocalModelClient",
    "ensure_lane",
    "run_role",
    "run_planner",
    "run_planning_judge_model",
    "run_planning_loop",
    "run_plan_build_judge",
    "run_builder",
    "run_judge",
    "run_verification",
    "run_glm_verification",
    "trigger_autonomous_run",
    "run_build_judge_verify",
    "BUILDER_SYSTEM",
    "PLANNER_SYSTEM",
    "JUDGE_SYSTEM",
    "PLANNING_JUDGE_SYSTEM",
    "MODEL_ROUTER_SCRIPT",
]
