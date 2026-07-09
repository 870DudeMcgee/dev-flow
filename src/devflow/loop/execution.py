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
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from devflow.loop.model_router import acquire_role_slot, resolve_role_slot
from devflow.loop import builder_judge as bj
from devflow.loop import verification as ver
from devflow.loop.adapter import load_loop_state
from devflow.loop.pipeline_run import (
    append_pipeline_event,
    load_pipeline_run,
    update_pipeline_run_record,
)
from devflow.loop.models import DevFlowLoopState, LoopStage


# Canonical launcher. Overridable via env for tests / non-default homes.
MODEL_ROUTER_SCRIPT = Path(
    os.environ.get("DEVFLOW_MODEL_ROUTER")
    or os.path.expanduser("~/.hermes/scripts/model-router")
)

ClientFactory = Callable[..., "LocalModelClient"]


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


# ---------------------------------------------------------------------------
# Local OpenAI-compatible client (stdlib only — no new dependency)
# ---------------------------------------------------------------------------
class LocalModelClient:
    """Tiny OpenAI-compatible client for llama-server-style local endpoints."""

    def __init__(self, endpoint: str, *, timeout: int = 240):
        self.endpoint = endpoint.rstrip("/")
        self.timeout = timeout
        self._model_id: Optional[str] = None

    def _fetch_model_id(self) -> str:
        if self._model_id is not None:
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
    def _do_post(endpoint: str, payload: dict, timeout: int) -> dict:
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{endpoint}/v1/chat/completions",
            data=body,
            headers={"Content-Type": "application/json"},
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
        payload: dict = {
            "model": model_id,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if stop:
            payload["stop"] = stop
        # Ornith runs with --reasoning auto; disable the thinking trace so the
        # content budget is spent on the actual answer, not a CoT dump.
        if not reasoning:
            payload["chat_template_kwargs"] = {"enable_thinking": False}
        try:
            data = self._do_post(self.endpoint, payload, self.timeout)
        except urllib.error.HTTPError:
            # Some servers reject chat_template_kwargs; retry without it.
            if not reasoning and "chat_template_kwargs" in payload:
                payload.pop("chat_template_kwargs")
                data = self._do_post(self.endpoint, payload, self.timeout)
            else:
                raise
        content = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
        usage = data.get("usage", {}) or {}
        return content, usage


# ---------------------------------------------------------------------------
# Lane lifecycle (uses the real model-router launcher)
# ---------------------------------------------------------------------------
def ensure_lane(role: str, *, script: Optional[Path] = None) -> None:
    """Bring the role's server up, swapping out any heavy-group sibling.

    Delegates to ``model-router start <port>`` — the canonical, config-driven
    launcher. No launch strings are invented here.
    """
    slot = resolve_role_slot(role)
    port = slot.endpoint.rsplit(":", 1)[-1]
    script = script or MODEL_ROUTER_SCRIPT
    # model-router prints; we only care about the side effect.
    subprocess.run([str(script), "start", port], check=False)


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
    max_tokens: int = 2048,
    reasoning: bool = False,
    ensure_lane_on: bool = True,
    client_factory: Optional[ClientFactory] = None,
) -> RoleResult:
    slot = resolve_role_slot(role)
    if ensure_lane_on:
        ensure_lane(role)

    factory = client_factory or LocalModelClient
    with acquire_role_slot(
        Path(root), role=role, task_id=task_id, worker_id=worker_id
    ) as held:
        client = factory(slot.endpoint)
        content, usage = client.chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=max_tokens,
            reasoning=reasoning,
        )
        append_pipeline_event(
            root,
            task_id or slot.role,
            {
                "event": "model_call",
                "role": role,
                "model": slot.model,
                "usage": usage,
            },
        )
        return RoleResult(
            role=role,
            model=slot.model,
            endpoint=slot.endpoint,
            content=content,
            usage=usage,
            raw={},
        )


# ---------------------------------------------------------------------------
# Workers (persist through existing deterministic adapters)
# ---------------------------------------------------------------------------
BUILDER_SYSTEM = (
    "You are the DevFlow builder. Produce a concrete code implementation that "
    "satisfies the assignment and its definition of done. Prefer a unified diff "
    "or a complete file. Output only the implementation — no commentary."
)

JUDGE_SYSTEM = (
    "You are the DevFlow judge. Evaluate the builder output against the "
    "definition of done. Respond with a single JSON object and nothing else: "
    '{"status": "passed"|"failed"|"needs_review", "rationale": "..."}.'
)


def _read_record(root: Path | str, run_id: str, name: str) -> Optional[str]:
    data = load_pipeline_run(root, run_id)
    val = data.get(name)
    if isinstance(val, str):
        return val
    if isinstance(val, dict):
        return json.dumps(val)
    return None


def run_builder(
    root: Path | str,
    run_id: str,
    *,
    assignment: str,
    definition_of_done: str,
    target_files: Optional[list[str]] = None,
    verification_command: Optional[str] = None,
    max_tokens: int = 4096,
    worker_id: str = "native-builder",
    ensure_lane_on: bool = True,
    client_factory: Optional[ClientFactory] = None,
) -> RoleResult:
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
    user = (
        f"# Assignment\n{assignment}\n\n"
        f"# Definition of Done\n{definition_of_done}\n\n"
        f"# Target files\n{files_block}\n"
    )

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

    # loop-packet.md is the canonical build_judge artifact (see adapter.infer_stage).
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

    loop_packet = _read_record(root, run_id, "loop-packet.md") or ""
    user = (
        f"# Definition of Done\n{definition_of_done}\n\n"
        f"# Builder Output\n{loop_packet}\n"
    )

    result = run_role(
        root,
        role="judge",
        system_prompt=JUDGE_SYSTEM,
        user_prompt=user,
        task_id=run_id,
        worker_id=worker_id,
        max_tokens=1024,
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


def run_verification(
    root: Path | str,
    run_id: str,
    *,
    verification_command: str,
    worker_id: str = "native-verify",
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
    worker_id: str = "native-executor",
    ensure_lane_on: bool = True,
    client_factory: Optional[ClientFactory] = None,
) -> dict:
    """Run the full native execution chain.

    Each model step swaps in its lane via ``ensure_lane`` (single-flight).
    Judge runs only after build; verification only after a passing judge.
    """
    build = run_builder(
        root,
        run_id,
        assignment=assignment,
        definition_of_done=definition_of_done,
        target_files=target_files,
        verification_command=verification_command,
        worker_id=worker_id,
        ensure_lane_on=ensure_lane_on,
        client_factory=client_factory,
    )
    judge_result, decision = run_judge(
        root,
        run_id,
        definition_of_done=definition_of_done,
        worker_id=worker_id,
        ensure_lane_on=ensure_lane_on,
        client_factory=client_factory,
    )
    out: dict = {
        "build": build,
        "judge": judge_result,
        "decision": decision,
        "verification": None,
    }
    if decision == "passed" and verification_command:
        out["verification"] = run_verification(
            root, run_id, verification_command=verification_command
        )
    return out


__all__ = [
    "RoleResult",
    "LocalModelClient",
    "ensure_lane",
    "run_role",
    "run_builder",
    "run_judge",
    "run_verification",
    "run_build_judge_verify",
    "BUILDER_SYSTEM",
    "JUDGE_SYSTEM",
    "MODEL_ROUTER_SCRIPT",
]
