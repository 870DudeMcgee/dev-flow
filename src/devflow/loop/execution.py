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
import time
import urllib.error
import urllib.request
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
    load_pipeline_run,
    update_pipeline_run_record,
)
from devflow.loop.models import LoopStage, advance_stage


DEFAULT_MAX_PLANNING_ROUNDS = 3
DEFAULT_MAX_BUILD_ROUNDS = 3


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

    # Write "started" entry to worker feed so the board shows what's about to happen
    append_worker_feed_entry(root, task_id or slot.role, {
        "event": "started",
        "role": role,
        "model": slot.model,
        "endpoint": slot.endpoint,
        "worker_id": worker_id,
        "task_id": task_id,
        "system_prompt": system_prompt[:500],
        "user_prompt": user_prompt[:2000],
    })

    with acquire_role_slot(
        Path(root), role=role, task_id=task_id, worker_id=worker_id
    ):
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

        # Write "completed" entry with the actual model output
        append_worker_feed_entry(root, task_id or slot.role, {
            "event": "completed",
            "role": role,
            "model": slot.model,
            "worker_id": worker_id,
            "task_id": task_id,
            "content": content,
            "usage": usage,
        })

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

PLANNER_SYSTEM = (
    "You are the DevFlow planner. Given a task, produce a bounded, concrete "
    "implementation plan as a single JSON object and nothing else: "
    '{"spec": "<what to build and why>", "plan": "<step-by-step steps>", '
    '"target_files": ["relative/path/to/file.py"], '
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
    revision_feedback: Optional[str] = None,
    round_index: int = 1,
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
        f"# Builder/Judge Round\n{round_index}\n\n"
        f"# Assignment\n{assignment}\n\n"
        f"# Definition of Done\n{definition_of_done}\n\n"
        f"# Target files\n{files_block}\n"
    )
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
    user = (
        f"# Planner Output\n{planner_content}\n\n"
        f"# Persisted Spec\n{spec}\n\n"
        f"# Persisted Plan\n{plan}\n\n"
        f"# Evidence JSON\n{evidence.model_dump_json(indent=2)}\n\n"
        f"# Deterministic Guardrail Findings (context, not final decision)\n"
        f"{deterministic_report.model_dump_json(indent=2)}\n\n"
        "Decide whether this plan is executable. Approve greenfield files when "
        "they are plausible files to create and verification is concrete."
    )
    result = run_role(
        root,
        role="planning_judge",
        system_prompt=PLANNING_JUDGE_SYSTEM,
        user_prompt=user,
        task_id=run_id,
        worker_id=worker_id,
        max_tokens=2048,
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
    max_tokens: int = 2048,
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
    user = (
        f"# Planning Round\n{round_index}\n\n"
        f"# Task\n{topic}\n\n"
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
    verification_command = plan.get("verification_command")

    update_pipeline_run_record(root, run_id, "spec.md", spec)
    update_pipeline_run_record(root, run_id, "plan.md", plan_text)

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
    max_rounds: int = DEFAULT_MAX_BUILD_ROUNDS,
    worker_id: str = "native-executor",
    ensure_lane_on: bool = True,
    client_factory: Optional[ClientFactory] = None,
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

    for round_index in range(1, max_rounds + 1):
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
        )
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
                    root, run_id, verification_command=verification_command
                )
            break
        feedback = json.dumps(payload, indent=2)

    cap_exhausted = bool(decision != "passed" and len(rounds) >= max_rounds)
    if cap_exhausted:
        _loop_exhausted(
            root,
            run_id,
            role="build_judge_loop",
            max_rounds=max_rounds,
            last_decision=decision or "unknown",
            next_action="Return to the orchestrator with the last judge feedback.",
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
    "run_build_judge_verify",
    "BUILDER_SYSTEM",
    "PLANNER_SYSTEM",
    "JUDGE_SYSTEM",
    "PLANNING_JUDGE_SYSTEM",
    "MODEL_ROUTER_SCRIPT",
]
