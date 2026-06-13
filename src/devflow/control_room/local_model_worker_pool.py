from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from devflow.control_room.agent_registry import (
    AgentDefinition,
    AgentRegistryError,
    adapter_maturity,
    is_local_model_worker_pool_agent,
    load_agent_registry,
    load_provider_registry,
)
from devflow.control_room.agent_runtime import resolve_agent_runtime_definition
from devflow.control_room.local_model_client import LocalModelClient, LocalModelClientError
from devflow.control_room.paths import relative_path
from devflow.control_room.persistence import get_task, utc_now
from devflow.control_room.task_packet import build_agent_packet, render_task_packet_text
from devflow.control_room.worker_evidence import expected_worker_evidence_outputs, write_worker_evidence


PROHIBITED_CHECKOUT_PATHS = ["/Users/jewelbait/Desktop/DevFlow"]
LOCAL_MODEL_WORKER_TYPE = "local_model_worker_pool"
GEMMA_NATIVE_PROFILE_IDS = {"local-gemma4-summarizer"}
GEMMA_NATIVE_NUM_CTX = 8192
GEMMA_NATIVE_NUM_PREDICT = 1536


class LocalModelWorkerPoolError(ValueError):
    pass


def registry_json_payload(root: Path) -> dict[str, Any]:
    registry = load_agent_registry(root)
    return {
        "schema_version": registry.version,
        "default_agent_id": registry.default_agent_id,
        "source_path": str(registry.source_path) if registry.source_path else None,
        "agents": [
            _agent_payload(registry.agents[agent_id], root=root)
            for agent_id in sorted(registry.agents)
        ],
    }


def agent_json_payload(root: Path, profile_id: str) -> dict[str, Any]:
    registry = load_agent_registry(root)
    return _agent_payload(registry.require_agent(profile_id), root=root)


def agent_policy_payload() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "policy_id": "devflow-local-model-worker-pool-policy",
        "source_of_truth": "agent_registry.py",
        "worker_outputs_are": "evidence_not_truth",
        "human_approval_controls": ["patch application", "verification command selection", "promotion", "merge", "push"],
        "execution_gates": [
            "profile must exist in the agent registry",
            "profile must be enabled",
            "planned_not_executable adapters cannot run",
            "machine_class must be treated as allocation metadata, not proof that a model is installed on that machine",
            "actual ollama show manifests should override public/model-name assumptions when available",
            "identical Ollama IDs should be flagged as aliases or duplicate tags until proven otherwise",
            "local worker-pool profiles must be read-only evidence writers",
            "workspace_write local patch profiles remain on existing proposal.patch gates",
            "can_promote, can_run_shell, and arbitrary network access must be false for local worker-pool profiles",
            "local model access is allowed only through LocalModelClient against a local Ollama/OpenAI-compatible endpoint",
        ],
        "forbidden": [
            "source edits",
            "workspace edits",
            "proposal.patch writes by read-only profiles",
            "patch application",
            "verification",
            "commit",
            "merge",
            "push",
            "promotion",
            "direct .devflow canonical state mutation",
            f"using quarantined checkout path {PROHIBITED_CHECKOUT_PATHS[0]}",
        ],
        "allowed_evidence_outputs": [
            ".devflow/tasks/<task-id>/local-model-runs/<run-id>/run.json",
            ".devflow/tasks/<task-id>/local-model-runs/<run-id>/packet.md",
            ".devflow/tasks/<task-id>/local-model-runs/<run-id>/response.md",
            ".devflow/tasks/<task-id>/local-model-runs/<run-id>/raw_output.txt",
            ".devflow/tasks/<task-id>/local-model-runs/<run-id>/error.txt",
        ],
        "hermes": {
            "may_request_only_when_profile_hermes_delegable": True,
            "may_read_and_summarize_evidence": True,
            "must_not_own_worker_state": True,
            "must_not_mutate_repo_directly": True,
        },
    }


def dry_run_local_model_profile(
    *,
    root: Path,
    task_id: str,
    profile_id: str,
    max_packet_chars: int = 16_000,
) -> dict[str, Any]:
    root = root.resolve()
    profile, provider_base_url, timeout_seconds = _load_runnable_profile(root, profile_id)
    packet_text, packet_was_truncated = _build_packet_text(root, task_id, profile, max_packet_chars)
    run_id = _new_run_id(profile.id, dry_run=True)
    expected_outputs = {
        key: relative_path(root, Path(path))
        for key, path in expected_worker_evidence_outputs(root, task_id, run_id).items()
    }
    task = get_task(root, task_id)
    return {
        "schema_version": 1,
        "dry_run": True,
        "task_id": task_id,
        "task_title": task.title,
        "profile_id": profile.id,
        "worker_id": profile.id,
        "worker_type": LOCAL_MODEL_WORKER_TYPE,
        "model": profile.model,
        "adapter": profile.adapter,
        "runtime": "local_model_client",
        "adapter_maturity": profile.adapter_maturity or adapter_maturity(profile.adapter),
        "permission_mode": profile.default_mode,
        "hermes_delegable": profile.hermes_delegable,
        "model_role_name": profile.model_role_name,
        "machine_class": profile.machine_class,
        "weight_class": profile.weight_class,
        "required_verification_command": profile.required_verification_command,
        "model_alias_group": profile.model_alias_group,
        "provider_base_url": provider_base_url,
        "timeout_seconds": timeout_seconds,
        "packet_inputs": {
            "task_packet": True,
            "rendered_packet_chars": len(packet_text),
            "max_packet_chars": max_packet_chars,
            "truncated": packet_was_truncated,
        },
        "expected_evidence_outputs": expected_outputs,
        "safety_warnings": _safety_warnings(profile),
        "will_call_model": False,
        "will_write_source": False,
        "will_write_proposal_patch": False,
        "will_apply_patch": False,
        "will_commit_merge_push_or_promote": False,
    }


def run_local_model_profile(
    *,
    root: Path,
    task_id: str,
    profile_id: str,
    base_url: str | None = None,
    timeout_seconds: float | None = None,
    temperature: float | None = None,
    max_packet_chars: int = 16_000,
    max_raw_output_chars: int = 200_000,
) -> dict[str, Any]:
    root = root.resolve()
    profile, provider_base_url, provider_timeout = _load_runnable_profile(root, profile_id)
    selected_base_url = base_url or provider_base_url
    selected_timeout = timeout_seconds if timeout_seconds is not None else provider_timeout
    packet_text, packet_was_truncated = _build_packet_text(root, task_id, profile, max_packet_chars)
    run_id = _new_run_id(profile.id)
    started_at = utc_now().isoformat()
    task = get_task(root, task_id)

    client = LocalModelClient(
        base_url=_local_model_base_url(selected_base_url),
        model_id=profile.model,
        timeout_seconds=selected_timeout,
        temperature=temperature,
    )
    system_prompt = _system_prompt(profile)
    user_prompt = _user_prompt(packet_text, profile, task_id=task.id, task_title=task.title, task_status=task.status)
    runtime = "local_model_client"
    evidence_base_url = client.base_url

    try:
        if _uses_native_ollama_chat(profile):
            result = client.native_chat_completion(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                think=False,
                num_ctx=GEMMA_NATIVE_NUM_CTX,
                num_predict=GEMMA_NATIVE_NUM_PREDICT,
            )
            runtime = "local_model_client.native_ollama_chat"
            evidence_base_url = client.get_native_chat_url()
        else:
            result = client.chat_completion(system_prompt=system_prompt, user_prompt=user_prompt)
        raw_output = json.dumps(result.get("response", result), indent=2, sort_keys=True)
        response_text = _assistant_text(result.get("response", {}))
        if not response_text:
            raise LocalModelWorkerPoolError("Local model returned an empty assistant response.")
        status = "success"
        error_message = None
        quality_score, quality_notes = _response_quality(profile, task_id=task.id, response_text=response_text)
        if quality_score is not None and quality_score < 0.75:
            status = "low_quality"
    except (LocalModelClientError, LocalModelWorkerPoolError, ValueError) as exc:
        raw_output = getattr(exc, "response_body", None) or str(exc)
        response_text = ""
        status = "failed"
        error_message = str(exc)
        quality_score = None
        quality_notes = None

    evidence = write_worker_evidence(
        root=root,
        worker_type=LOCAL_MODEL_WORKER_TYPE,
        profile_id=profile.id,
        worker_id=profile.id,
        task_id=task_id,
        run_id=run_id,
        packet_text=packet_text,
        raw_output=raw_output,
        response_text=response_text,
        model=profile.model,
        adapter=profile.adapter,
        adapter_maturity=profile.adapter_maturity or adapter_maturity(profile.adapter),
        permission_mode=profile.default_mode,
        hermes_delegable=profile.hermes_delegable,
        machine_class=profile.machine_class,
        weight_class=profile.weight_class,
        model_role_name=profile.model_role_name,
        required_verification_command=profile.required_verification_command,
        model_alias_group=profile.model_alias_group,
        runtime=runtime,
        status=status,
        started_at=started_at,
        base_url=evidence_base_url,
        error_message=error_message,
        quality_notes=quality_notes,
        quality_score=quality_score,
        max_raw_output_chars=max_raw_output_chars,
    )

    payload = {
        "schema_version": 1,
        "dry_run": False,
        "task_id": task_id,
        "profile_id": profile.id,
        "worker_id": profile.id,
        "worker_type": LOCAL_MODEL_WORKER_TYPE,
        "status": status,
        "run_id": run_id,
        "model": profile.model,
        "adapter": profile.adapter,
        "runtime": runtime,
        "adapter_maturity": profile.adapter_maturity or adapter_maturity(profile.adapter),
        "permission_mode": profile.default_mode,
        "hermes_delegable": profile.hermes_delegable,
        "model_role_name": profile.model_role_name,
        "machine_class": profile.machine_class,
        "weight_class": profile.weight_class,
        "required_verification_command": profile.required_verification_command,
        "model_alias_group": profile.model_alias_group,
        "packet_truncated": packet_was_truncated,
        "evidence_dir": relative_path(root, evidence.evidence_dir),
        "run_metadata_path": relative_path(root, evidence.run_metadata_path),
        "packet_path": relative_path(root, evidence.packet_path),
        "response_path": relative_path(root, evidence.response_path),
        "raw_output_path": relative_path(root, evidence.raw_output_path),
        "error_path": relative_path(root, evidence.error_path) if error_message else None,
        "will_write_source": False,
        "will_write_proposal_patch": False,
        "will_apply_patch": False,
        "will_commit_merge_push_or_promote": False,
    }
    if quality_score is not None:
        payload["quality_score"] = quality_score
    if quality_notes:
        payload["quality_notes"] = quality_notes
    if error_message:
        payload["error_message"] = error_message
    return payload


def _load_runnable_profile(root: Path, profile_id: str) -> tuple[AgentDefinition, str | None, int | None]:
    try:
        registry = load_agent_registry(root)
        profile = registry.require_agent(profile_id)
        providers = load_provider_registry(root)
        provider = providers.providers.get(profile.provider)
    except (AgentRegistryError, KeyError) as exc:
        raise LocalModelWorkerPoolError(str(exc)) from exc

    if profile.adapter_maturity is None:
        profile.adapter_maturity = adapter_maturity(profile.adapter)
    runtime = resolve_agent_runtime_definition(profile, provider)
    if not runtime.agent_run_allowed:
        next_action = f" Use '{runtime.next_command}' instead." if runtime.next_command else ""
        refusal = f" {runtime.refusal_reason}" if runtime.refusal_reason else ""
        raise LocalModelWorkerPoolError(
            f"Profile '{profile.id}' is not approved for the local model worker pool. "
            f"Execution surface: {runtime.execution_surface}.{next_action}{refusal}"
        )
    return profile, provider.base_url if provider else None, provider.default_timeout_seconds if provider else None


def _build_packet_text(
    root: Path,
    task_id: str,
    profile: AgentDefinition,
    max_packet_chars: int,
) -> tuple[str, bool]:
    try:
        packet = build_agent_packet(task_id, profile, root=root)
    except KeyError as exc:
        raise LocalModelWorkerPoolError(str(exc)) from exc
    packet_text = _render_compact_evidence_packet(packet) if _uses_compact_packet(profile) else render_task_packet_text(packet)
    if max_packet_chars < 1:
        max_packet_chars = 16_000
    if len(packet_text) <= max_packet_chars:
        return packet_text, False
    suffix = f"\n\n[packet capped at {max_packet_chars} characters]\n"
    keep = max(0, max_packet_chars - len(suffix))
    return packet_text[:keep] + suffix, True


def _uses_native_ollama_chat(profile: AgentDefinition) -> bool:
    return profile.id in GEMMA_NATIVE_PROFILE_IDS


def _uses_compact_packet(profile: AgentDefinition) -> bool:
    return profile.id in GEMMA_NATIVE_PROFILE_IDS


def _render_compact_evidence_packet(packet: Any) -> str:
    lines = [
        "# Compact Dev-Flow Evidence Packet",
        f"- Task ID: {packet.task_id}",
        f"- Title: {packet.title}",
        f"- Status: {packet.status}",
        f"- Agent/Profile: {packet.agent_id or 'unknown'}",
        f"- Adapter: {packet.adapter}",
        f"- Workspace Path: {packet.workspace_path}",
    ]
    if packet.goal_context:
        lines.extend(
            [
                "",
                "## Goal Link",
                f"- Goal ID: {packet.goal_context.get('goal_id', 'unknown')}",
                f"- Slice ID: {packet.goal_context.get('slice_id', 'unknown')}",
                f"- Execution Mode: {packet.goal_context.get('execution_mode', 'unknown')}",
                f"- Human Checkpoint Required: {packet.goal_context.get('human_checkpoint_required', 'unknown')}",
                f"- Promotion Allowed: {packet.goal_context.get('promotion_allowed', 'unknown')}",
            ]
        )
    if packet.task_slice:
        acceptance = packet.task_slice.get("acceptance_criteria") or []
        lines.extend(
            [
                "",
                "## Task Slice",
                f"- Summary: {packet.task_slice.get('summary', 'unknown')}",
                "- Acceptance Criteria:",
            ]
        )
        lines.extend(f"  - {item}" for item in acceptance[:8])
    if packet.verification:
        lines.extend(
            [
                "",
                "## Verification",
                f"- Status: {packet.verification.get('status', 'unknown')}",
                f"- Command: {packet.verification.get('command', 'unknown')}",
                f"- Exit Code: {packet.verification.get('exit_code', 'unknown')}",
            ]
        )
    if packet.next_action:
        lines.extend(
            [
                "",
                "## Next Action Projection",
                f"- Action: {packet.next_action.get('action', 'unknown')}",
                f"- Command: {packet.next_action.get('command', 'unknown')}",
                f"- Reason: {packet.next_action.get('reason', 'unknown')}",
            ]
        )
    if packet.recent_events:
        lines.extend(["", "## Recent Events"])
        for event in packet.recent_events[-8:]:
            event_type = event.get("event") or event.get("type") or "event"
            timestamp = event.get("timestamp") or event.get("created_at") or "unknown-time"
            detail = event.get("status") or event.get("summary") or event.get("command") or ""
            suffix = f" ({detail})" if detail else ""
            lines.append(f"- {timestamp}: {event_type}{suffix}")
    if packet.result_summary:
        lines.extend(["", "## Result Summary", packet.result_summary])
    lines.extend(
        [
            "",
            "## Hard Constraints",
            "- Use the exact Task ID from this packet.",
            "- Do not claim source edits, verification, commits, merge, push, or promotion unless this packet proves them.",
            "- Treat model output as advisory evidence only.",
        ]
    )
    return "\n".join(lines) + "\n"


def _system_prompt(profile: AgentDefinition) -> str:
    return (
        "You are a replaceable local model worker inside Dev-Flow.\n"
        "Dev-Flow owns task state, evidence, verification, and promotion.\n"
        "Use only the bounded task packet provided.\n"
        "Never invent or substitute a task id, title, status, command, file path, or execution result.\n"
        "If a required detail is absent from the packet, write `unknown` and explain what evidence is missing.\n"
        "Do not claim you edited files, ran verification, applied patches, committed, merged, pushed, or promoted.\n"
        "Do not write or request proposal.patch for this read-only worker-pool profile.\n"
        f"Profile: {profile.id}\n"
        f"Role: {profile.role}\n"
        f"Purpose: {profile.purpose or 'local evidence worker'}\n"
    )


def _user_prompt(
    packet_text: str,
    profile: AgentDefinition,
    *,
    task_id: str,
    task_title: str,
    task_status: str,
) -> str:
    return (
        "# Response Grounding Contract\n\n"
        f"Your response must begin with this exact task id: {task_id}\n"
        f"Task title from Dev-Flow: {task_title}\n"
        f"Task status from Dev-Flow: {task_status}\n"
        "Do not write `N/A`, `unknown`, `task-0000`, or any other placeholder for Task ID.\n\n"
        "# Bounded Dev-Flow Task Packet\n\n"
        f"```markdown\n{packet_text}\n```\n\n"
        "# Requested Output\n\n"
        "Return concise structured evidence with these exact sections:\n"
        "## Task Grounding\n"
        f"- Task ID: {task_id}\n"
        f"- Task Title: {task_title}\n"
        f"- Task Status: {task_status}\n"
        f"- Worker/Profile: {profile.id}\n"
        "- Evidence Reviewed:\n"
        f"If the packet says {task_id}, the response must say {task_id}. Do not use placeholder task ids.\n\n"
        "## Summary\n"
        "Summarize only what the packet proves. Distinguish pending work from completed work.\n\n"
        "## Findings\n"
        "List useful observations grounded in packet evidence. Avoid generic local-model readiness boilerplate.\n\n"
        "## Risks Or Questions\n"
        "Name missing evidence, contradictions, or reasons the summary may be weak.\n\n"
        "## Suggested Next Dev-Flow Action\n"
        "Return one concrete Dev-Flow command or human review action. Do not suggest execution if the packet shows it already ran.\n\n"
        f"Keep the response aligned to profile `{profile.id}` and treat all recommendations as advisory evidence only."
    )


def _response_quality(profile: AgentDefinition, *, task_id: str, response_text: str) -> tuple[float | None, str | None]:
    if profile.id != "local-gemma4-summarizer":
        return None, None

    text = response_text.strip()
    lowered = text.lower()
    score = 1.0
    notes: list[str] = []
    required_sections = (
        "## Task Grounding",
        "## Summary",
        "## Findings",
        "## Risks Or Questions",
        "## Suggested Next Dev-Flow Action",
    )
    for section in required_sections:
        if section.lower() not in lowered:
            score -= 0.12
            notes.append(f"missing required section {section}")
    if task_id not in text:
        score -= 0.45
        notes.append(f"response did not include task id {task_id}")
    if "task-0000" in lowered or "task id: n/a" in lowered or "**task id:** n/a" in lowered:
        score -= 0.25
        notes.append("response used a placeholder task id")
    if "execute the inference process" in lowered or "pending execution" in lowered:
        score -= 0.15
        notes.append("response suggested generic execution instead of summarizing packet evidence")

    score = max(0.0, round(score, 2))
    return score, "; ".join(notes) if notes else "passed grounded summarizer checks"


def _assistant_text(response: dict[str, Any]) -> str:
    message = response.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()
    choices = response.get("choices")
    if isinstance(choices, list) and choices:
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, str):
                return content.strip()
        text = choices[0].get("text") if isinstance(choices[0], dict) else None
        if isinstance(text, str):
            return text.strip()
    direct_response = response.get("response")
    if isinstance(direct_response, str):
        return direct_response.strip()
    content = response.get("content")
    if isinstance(content, str):
        return content.strip()
    raise LocalModelWorkerPoolError("Local model response did not include assistant content.")


def _new_run_id(profile_id: str, *, dry_run: bool = False) -> str:
    if dry_run:
        return f"dry-run-{profile_id}"
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"{timestamp}-{os.urandom(4).hex()}-{profile_id}"


def _local_model_base_url(base_url: str | None) -> str | None:
    if not base_url:
        return None
    cleaned = base_url.rstrip("/")
    return cleaned if cleaned.endswith("/v1") else f"{cleaned}/v1"


def _safety_warnings(profile: AgentDefinition) -> list[str]:
    warnings = [
        "Dry-run only; no model call is made.",
        "Worker output is evidence, not truth.",
        "No source, workspace, proposal.patch, Git, verification, or promotion mutation is permitted.",
        f"Quarantined checkout path is forbidden: {PROHIBITED_CHECKOUT_PATHS[0]}",
    ]
    if not profile.hermes_delegable:
        warnings.append("Profile is not Hermes-delegable.")
    return warnings


def _agent_payload(agent: AgentDefinition, *, root: Path) -> dict[str, Any]:
    payload = agent.model_dump(mode="json")
    payload["adapter_maturity"] = payload.get("adapter_maturity") or adapter_maturity(agent.adapter)
    payload["local_model_worker_pool_runnable"] = is_local_model_worker_pool_agent(agent)
    payload["registry_source"] = "builtin" if not (root / ".devflow/agents/registry.yaml").exists() else ".devflow/agents/registry.yaml"
    return payload
