from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from devflow.control_room.agent_registry import (
    AgentDefinition,
    ProviderDefinition,
    is_local_ollama_base_url,
    load_agent_registry,
    load_provider_registry,
)
from devflow.control_room.agent_runtime import resolve_agent_runtime_definition
from devflow.control_room.estimator import estimate_task_fit, save_task_fit
from devflow.control_room.paths import task_dir
from devflow.control_room.persistence import get_task


POLICY_VERSION = 2
LOCAL_MODEL_PROVIDERS = {"ollama", "local"}

_IMPLEMENTATION_MODES = {"workspace_write"}
_READ_ONLY_MODES = {"read_only", "docs_only", "manual_packet_only", "frontier_read_only", "verify_only"}
_SAFE_YAML_SCALAR = re.compile(r"^[A-Za-z0-9_.\-/<>]+$")


def _read_selected_agent_evidence(root: Path, task_id: str) -> dict[str, Any] | None:
    selection_path = task_dir(root, task_id) / "agent-selection.json"
    if not selection_path.exists():
        return None
    try:
        payload = json.loads(selection_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {"status": "invalid", "error": f"invalid selected-agent evidence: {exc}"}
    if not isinstance(payload, dict):
        return {"status": "invalid", "error": "invalid selected-agent evidence: root must be an object"}
    return payload


def _tier_cost(tier: str) -> int:
    costs = {
        "deterministic": 0,
        "tiny_local": 1,
        "fast_local": 1,
        "local": 1,
        "strong_local": 2,
        "premium_local": 2,
        "frontier": 3,
    }
    return costs.get(tier.lower(), 0)


def _role_matches(agent: AgentDefinition, role: str) -> bool:
    role = role.lower()
    fields = [
        agent.id,
        agent.role,
        agent.model_role_name or "",
        agent.purpose or "",
        *agent.secondary_roles,
    ]
    text = " ".join(fields).lower()
    if role == "worker":
        return any(marker in text for marker in ("implementation_worker", "worker", "developer", "coder", "implementer"))
    if role == "planner":
        return any(marker in text for marker in ("planner", "architect", "architecture", "lead"))
    if role == "reviewer":
        return any(marker in text for marker in ("reviewer", "review", "audit", "architect"))
    return role in text


def _selected_local_agent_id(root: Path, task_id: str) -> str | None:
    evidence = _read_selected_agent_evidence(root, task_id)
    if not evidence or evidence.get("status") != "selected":
        return None
    evidence_task_id = evidence.get("task_id")
    if evidence_task_id is not None and evidence_task_id != task_id:
        return None
    if evidence.get("role") != "implementation_worker":
        return None
    selected_agent_id = evidence.get("selected_agent_id")
    if not isinstance(selected_agent_id, str) or not selected_agent_id.strip():
        return None
    return selected_agent_id


def route_task(root: Path, task_id: str) -> dict[str, Any]:
    """Build an evidence-only routing decision without running workers or providers."""
    task_fit_file = task_dir(root, task_id) / "task-fit.yaml"
    fit_data = estimate_task_fit(root, task_id)
    if not task_fit_file.exists():
        save_task_fit(root, task_id, fit_data)

    task = get_task(root, task_id)
    task_fit = fit_data.get("task_fit", {})
    repo_scan = fit_data.get("repo_scan", {})
    registry = load_agent_registry(root)
    providers, provider_registry_error = _load_provider_registry(root)
    enabled_agents = [
        agent
        for agent in registry.enabled_agents()
        if agent.adapter != "manual" and agent.execution_mode != "human_launched_agent"
    ]

    total_context_estimate = int(repo_scan.get("total_context_estimate") or 0)
    recommended_worker_tier = str(task_fit.get("recommended_worker_tier", "strong_local"))
    requires_escalation = _requires_escalation(task_fit)
    selected: dict[str, str] = {"verifier": "deterministic-shell"}
    rejected: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    recommended_next_commands: dict[str, str] = {
        "verifier": f"devflow task verify {task_id} --shell \"<verification command>\"",
    }
    reasons = [
        "evidence-only routing records recommendations and next commands but never runs workers or providers",
        f"context estimate ({total_context_estimate} tokens) is {task_fit.get('context_requirement', 'medium')}",
        f"architectural risk is {task_fit.get('architectural_risk', 'medium')}",
        f"code edit risk is {task_fit.get('code_edit_risk', 'medium')}",
    ]
    if task.verification_command:
        recommended_next_commands["verifier"] = f"devflow task verify {task_id} --shell {json.dumps(task.verification_command)}"

    selected_agent_id = _selected_local_agent_id(root, task_id)
    selected_agent_evidence = _read_selected_agent_evidence(root, task_id)
    worker_candidates = [agent for agent in enabled_agents if _role_matches(agent, "worker")]

    for role in ("planner", "reviewer"):
        _record_readonly_role_candidates(
            role=role,
            agents=enabled_agents,
            providers=providers,
            provider_registry_error=provider_registry_error,
            rejected=rejected,
            blocked=blocked,
        )

    for agent in worker_candidates:
        rejection_reason = _worker_rejection_reason(
            task_id=task_id,
            agent=agent,
            provider=providers.get(agent.provider),
            provider_registry_error=provider_registry_error,
            selected_agent_id=selected_agent_id,
            selected_agent_evidence=selected_agent_evidence,
            recommended_worker_tier=recommended_worker_tier,
            total_context_estimate=total_context_estimate,
            task_fit=task_fit,
            requires_escalation=requires_escalation,
        )
        if rejection_reason is not None:
            rejected.append({"role": "worker", "agent": agent.id, "reason": rejection_reason})
            if _is_runtime_blocking_reason(rejection_reason):
                blocked.append({"role": "worker", "agent": agent.id, "status": "blocked_runtime", "reason": rejection_reason})
            continue
        selected["worker"] = agent.id
        recommended_next_commands["worker"] = f"devflow task run {task_id} --worker {agent.id}"
        reasons.append(f"worker selected from matching selected-agent evidence: {agent.id}")
        break

    if "worker" not in selected:
        if requires_escalation:
            _add_unresolved(
                unresolved,
                role="worker",
                status="human_escalation_required",
                reason="task risk or model-routing scope requires human selection before worker execution",
                next_command=f"devflow agent select-local {task_id} --role implementation_worker --json",
            )
        elif any("no selected-agent evidence" in item["reason"] for item in rejected if item.get("role") == "worker"):
            _add_unresolved(
                unresolved,
                role="worker",
                status="needs_human_agent_selection",
                reason="eligible local model workers require explicit selected-agent evidence",
                next_command=f"devflow agent select-local {task_id} --role implementation_worker --json",
            )
        else:
            _add_unresolved(
                unresolved,
                role="worker",
                status="no_eligible_worker",
                reason="no registry candidate met role, runtime, risk, context, and evidence requirements",
            )

    if requires_escalation:
        for role in ("planner", "reviewer"):
            _add_unresolved(
                unresolved,
                role=role,
                status="human_escalation_required",
                reason="frontier or high-risk planning/review remains a human escalation decision in evidence-only routing",
            )

    return {
        "routing_decision": {
            "task_id": task_id,
            "policy_version": POLICY_VERSION,
            "decision_mode": "evidence_only",
            "task_fit_profile_path": f".devflow/tasks/{task_id}/task-fit.yaml",
            "requires_escalation": requires_escalation,
            "selected": selected,
            "reason": reasons,
            "rejected": rejected,
            "blocked": blocked,
            "unresolved": unresolved,
            "recommended_next_commands": recommended_next_commands,
            "execution_boundary": {
                "will_run_worker": False,
                "will_call_provider": False,
                "will_apply_patch": False,
                "will_verify": False,
                "worker_execution_requires_explicit_command": True,
            },
        }
    }


def save_routing_decision(root: Path, task_id: str, decision_data: dict[str, Any]) -> None:
    """Save the routing decision data to routing-decision.yaml inside the task directory."""
    task_directory = task_dir(root, task_id)
    task_directory.mkdir(parents=True, exist_ok=True)
    yaml_file = task_directory / "routing-decision.yaml"

    rd = decision_data.get("routing_decision", {})
    field_order = [
        "task_id",
        "policy_version",
        "decision_mode",
        "task_fit_profile_path",
        "requires_escalation",
        "selected",
        "reason",
        "rejected",
        "blocked",
        "unresolved",
        "recommended_next_commands",
        "execution_boundary",
    ]
    lines = ["routing_decision:"]
    for field in field_order:
        _append_yaml(lines, field, rd.get(field), indent=2)

    yaml_file.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _record_readonly_role_candidates(
    *,
    role: str,
    agents: list[AgentDefinition],
    providers: dict[str, ProviderDefinition],
    provider_registry_error: str | None,
    rejected: list[dict[str, Any]],
    blocked: list[dict[str, Any]],
) -> None:
    for agent in agents:
        if not _role_matches(agent, role):
            continue
        provider_error = _provider_registry_block_reason(agent, provider_registry_error)
        if provider_error is not None:
            rejected.append({"role": role, "agent": agent.id, "reason": provider_error})
            blocked.append({"role": role, "agent": agent.id, "status": "blocked_runtime", "reason": provider_error})
            continue
        provider = providers.get(agent.provider)
        runtime = resolve_agent_runtime_definition(agent, provider)
        if runtime.remote_provider or runtime.adapter_maturity in {"experimental_readonly", "planned_not_executable"}:
            reason = _runtime_block_reason(runtime, provider)
            rejected.append({"role": role, "agent": agent.id, "reason": reason})
            blocked.append({"role": role, "agent": agent.id, "status": "blocked_runtime", "reason": reason})


def _worker_rejection_reason(
    *,
    task_id: str,
    agent: AgentDefinition,
    provider: ProviderDefinition | None,
    provider_registry_error: str | None,
    selected_agent_id: str | None,
    selected_agent_evidence: dict[str, Any] | None,
    recommended_worker_tier: str,
    total_context_estimate: int,
    task_fit: dict[str, Any],
    requires_escalation: bool,
) -> str | None:
    provider_error = _provider_registry_block_reason(agent, provider_registry_error)
    if provider_error is not None:
        return provider_error

    runtime = resolve_agent_runtime_definition(agent, provider)
    if runtime.remote_provider:
        return _runtime_block_reason(runtime, provider)
    if runtime.adapter_maturity in {"experimental_readonly", "planned_not_executable"}:
        return _runtime_block_reason(runtime, provider)

    if agent.default_mode in _READ_ONLY_MODES or agent.default_mode not in _IMPLEMENTATION_MODES:
        return f"read-only profile cannot serve as implementation worker (default_mode={agent.default_mode})"

    if agent.provider not in LOCAL_MODEL_PROVIDERS and agent.provider != "shell":
        return _runtime_block_reason(runtime, provider)
    if runtime.execution_surface == "blocked" or not runtime.task_run_allowed:
        return _runtime_block_reason(runtime, provider)

    useful_context_tokens = _useful_context_tokens(agent.tier)
    if total_context_estimate > useful_context_tokens:
        return (
            "useful context below pack estimate "
            f"(agent tier {agent.tier} useful context {useful_context_tokens} tokens < "
            f"pack estimate {total_context_estimate} tokens)"
        )

    task_risk_high = task_fit.get("code_edit_risk") in {"high", "critical"} or task_fit.get("architectural_risk") in {
        "high",
        "critical",
    }
    if task_risk_high and _tier_cost(agent.tier) < _tier_cost("strong_local"):
        return f"risk mismatch (high task risk requires strong local or frontier tier, got {agent.tier} agent {agent.id})"

    if _tier_cost(agent.tier) < _tier_cost(recommended_worker_tier):
        return f"tier mismatch (agent tier {agent.tier} is below recommended {recommended_worker_tier})"

    if requires_escalation:
        return "human escalation required before selecting implementation worker for critical or model-routing task"

    if agent.provider in LOCAL_MODEL_PROVIDERS:
        if selected_agent_evidence and selected_agent_evidence.get("status") == "invalid":
            return str(selected_agent_evidence.get("error", "invalid selected-agent evidence"))
        if selected_agent_id is None:
            return (
                "no selected-agent evidence for local model worker; "
                f"run devflow agent select-local {task_id} --role implementation_worker --json"
            )
        if selected_agent_id != agent.id:
            return f"selected-agent evidence chose {selected_agent_id}, not {agent.id}"
        selected_model = selected_agent_evidence.get("selected_model") if selected_agent_evidence else None
        if selected_model and selected_model != agent.model:
            return f"selected-agent evidence model mismatch (selected {selected_model}, registry model {agent.model})"

    return None


def _requires_escalation(task_fit: dict[str, Any]) -> bool:
    return (
        task_fit.get("task_type") in {"model_routing_change", "architecture_change", "repo_refactor"}
        or task_fit.get("code_edit_risk") in {"high", "critical"}
        or task_fit.get("architectural_risk") in {"high", "critical"}
        or task_fit.get("recommended_worker_tier") == "frontier"
    )


def _load_provider_registry(root: Path) -> tuple[dict[str, ProviderDefinition], str | None]:
    try:
        return load_provider_registry(root).providers, None
    except Exception as exc:
        return {}, f"provider registry failed to load: {exc}"


def _provider_registry_block_reason(agent: AgentDefinition, provider_registry_error: str | None) -> str | None:
    if provider_registry_error is None or agent.provider in {"shell", "manual"}:
        return None
    return f"{provider_registry_error}; refusing provider-backed routing candidate {agent.id}"


def _runtime_block_reason(runtime: Any, provider: ProviderDefinition | None = None) -> str:
    if provider and provider.provider == "ollama" and not is_local_ollama_base_url(provider.base_url):
        return f"provider registry marks ollama base_url as non-local ({provider.base_url}); runtime is blocked"
    maturity = str(runtime.adapter_maturity).replace("_", "-")
    if runtime.remote_provider:
        return f"provider is {maturity}; remote provider execution is blocked by evidence-only routing"
    if runtime.refusal_reason:
        return runtime.refusal_reason
    return f"runtime is {maturity}; candidate cannot execute through evidence-only routing"


def _is_runtime_blocking_reason(reason: str) -> bool:
    return "provider is" in reason or "cannot execute" in reason or "blocked" in reason


def _useful_context_tokens(tier: str) -> int:
    ceilings = {
        "tiny_local": 8192,
        "fast_local": 16384,
        "local": 32768,
        "strong_local": 48000,
        "premium_local": 65536,
        "frontier": 128000,
    }
    return ceilings.get(tier.lower(), 32768)


def _add_unresolved(
    unresolved: list[dict[str, Any]],
    *,
    role: str,
    status: str,
    reason: str,
    next_command: str | None = None,
) -> None:
    if any(item.get("role") == role and item.get("status") == status for item in unresolved):
        return
    item: dict[str, Any] = {"role": role, "status": status, "reason": reason}
    if next_command is not None:
        item["next_command"] = next_command
    unresolved.append(item)


def _yaml_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if value is None:
        return "null"
    text = str(value)
    if _SAFE_YAML_SCALAR.match(text):
        return text
    return json.dumps(text)


def _append_yaml(lines: list[str], key: str, value: Any, *, indent: int) -> None:
    prefix = " " * indent
    if isinstance(value, dict):
        if not value:
            lines.append(f"{prefix}{key}: {{}}")
            return
        lines.append(f"{prefix}{key}:")
        for child_key, child_value in value.items():
            _append_yaml(lines, str(child_key), child_value, indent=indent + 2)
        return
    if isinstance(value, list):
        if not value:
            lines.append(f"{prefix}{key}: []")
            return
        lines.append(f"{prefix}{key}:")
        for item in value:
            if isinstance(item, dict):
                lines.append(f"{prefix}  -")
                for child_key, child_value in item.items():
                    _append_yaml(lines, str(child_key), child_value, indent=indent + 4)
            else:
                lines.append(f"{prefix}  - {_yaml_scalar(item)}")
        return
    lines.append(f"{prefix}{key}: {_yaml_scalar(value)}")
