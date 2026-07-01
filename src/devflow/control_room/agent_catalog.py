from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from devflow.control_room.agent_catalog_hermes import configured_hermes_agents
from devflow.control_room.agent_catalog_local import (
    _local_model_policy,
    _local_ollama_catalog,
    _local_openai_compatible_catalog,
    _profile_availability,
    _provider_model_rows,
)
from devflow.control_room.agent_registry import (
    AgentDefinition,
    AgentRegistryError,
    SAFE_AGENT_ID_PATTERN as SAFE_ID_PATTERN,
    load_agent_registry,
    load_provider_registry,
    slug_id_part,
    slug_id_part as _slug,
)
from devflow.control_room.agent_runtime import agent_runtime_contract
from devflow.control_room.machine_capability import discover_machine_capability
from devflow.control_room.local_agent_discovery import LocalDiscoveryReport


def build_agent_catalog(
    root: Path,
    *,
    provider_id: str | None = None,
    live_discovery: bool = True,
    configured_hermes_agent_rows: list[dict[str, Any]] | None = None,
    local_discovery_report: LocalDiscoveryReport | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    providers = load_provider_registry(root)
    registry = load_agent_registry(root)
    provider_filter = provider_id.strip() if provider_id else None
    if provider_filter and provider_filter not in providers.providers:
        raise AgentRegistryError(root / ".devflow" / "providers", [f"Unknown provider '{provider_filter}'."])

    provider_rows = []
    for provider in sorted(providers.providers.values(), key=lambda item: item.id):
        if provider_filter and provider.id != provider_filter:
            continue
        missing_env = bool(provider.api_key_env and not os.environ.get(provider.api_key_env))
        provider_rows.append(
            {
                "id": provider.id,
                "provider": provider.provider,
                "adapter": provider.adapter,
                "base_url": provider.base_url,
                "api_key_env": provider.api_key_env,
                "api_key_env_missing": missing_env,
                "default_timeout_seconds": provider.default_timeout_seconds,
                "enabled": provider.enabled,
            }
        )

    machine = discover_machine_capability()
    local_ollama = _local_ollama_catalog(registry, local_discovery_report=local_discovery_report)
    local_openai_compatible = _local_openai_compatible_catalog(
        registry, providers, machine=machine, live_discovery=live_discovery
    )
    local_model_policy = _local_model_policy(local_openai_compatible, local_ollama, machine)
    hermes_agents = (
        configured_hermes_agent_rows
        if configured_hermes_agent_rows is not None
        else configured_hermes_agents(root)
    )
    if provider_filter:
        hermes_agents = [agent for agent in hermes_agents if agent.get("provider") == provider_filter]

    profiles = []
    for agent in sorted(registry.agents.values(), key=lambda item: item.id):
        if provider_filter and agent.provider != provider_filter:
            continue
        provider = providers.providers.get(agent.provider)
        profiles.append(
            {
                "id": agent.id,
                "provider": agent.provider,
                "model": agent.model,
                "adapter": agent.adapter,
                "role": agent.role,
                "authority": _authority_for_agent(agent),
                "default_mode": agent.default_mode,
                "enabled": agent.enabled,
                "capabilities": _profile_capabilities(agent),
                "availability": _profile_availability(
                    agent,
                    provider=provider,
                    local_ollama=local_ollama,
                    local_openai_compatible=local_openai_compatible,
                ),
                "runtime_contract": agent_runtime_contract(root, agent),
            }
        )

    actions = _catalog_actions(provider_rows, local_openai_compatible=local_openai_compatible)
    return {
        "schema_version": 1,
        "providers": provider_rows,
        "profiles": profiles,
        "local_ollama": local_ollama,
        "local_openai_compatible": local_openai_compatible,
        "local_model_policy": local_model_policy,
        "hermes_agents": hermes_agents,
        "actions": actions,
    }


def _profile_capabilities(agent: Any) -> dict[str, Any]:
    return {
        "reliable_context_tokens": agent.reliable_context_tokens,
        "vision": agent.vision,
        "thinking": agent.thinking,
        "code_focus": agent.code_focus,
        "speed_class": agent.speed_class,
        "architecture_class": agent.architecture_class,
        "fim_support": agent.fim_support,
        "input_modalities": list(agent.input_modalities),
        "tool_access": list(agent.tool_access),
        "tuned_for_archetypes": list(agent.tuned_for_archetypes),
        "secondary_roles": list(agent.secondary_roles),
    }


def _catalog_actions(
    provider_rows: list[dict[str, Any]], *, local_openai_compatible: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    actions = [
        {
            "label": "Refresh catalog",
            "command": "devflow agent catalog --json",
            "scope": "agent_catalog",
            "safety_class": "pure_read_only",
            "requires_human_approval": False,
            "supervisor_may_auto_run": True,
            "reason": "Read providers, profiles, runtime contracts, env status, local Ollama, and local OpenAI-compatible discovery.",
        }
    ]
    for provider in provider_rows[:6]:
        default_authority = "read-only" if provider["provider"] == "ollama" else "advisory"
        default_role = "local_senior_worker" if provider["provider"] == "ollama" else "frontier_planner_architect_reviewer"
        actions.append(
            {
                "label": f"Add model to {provider['id']}",
                "command": (
                    f"devflow agent add-model --provider {provider['id']} --model <model-id> "
                    f"--authority {default_authority} --role {default_role}"
                ),
                "scope": "agent_catalog",
                "safety_class": "approval_required_task_state",
                "requires_human_approval": True,
                "supervisor_may_auto_run": False,
                "reason": "Writes or upserts one safe registry profile after exact approval.",
            }
        )
    if local_openai_compatible:
        actions.extend(_local_openai_onboarding_actions(local_openai_compatible))
    return actions


def _local_openai_onboarding_actions(local_openai_compatible: dict[str, Any]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for provider in local_openai_compatible.get("providers", []):
        if not isinstance(provider, dict) or provider.get("status") != "ready":
            continue
        provider_id = _safe_provider_id_from_discovery(provider)
        if not provider_id:
            continue
        base_url = str(provider.get("base_url") or "").strip()
        actions.append(
            {
                "label": f"Register {provider.get('name') or provider_id}",
                "command": f"devflow agent add-provider {provider_id} --adapter openai_compatible --base-url {base_url}",
                "scope": "agent_catalog",
                "safety_class": "approval_required_task_state",
                "requires_human_approval": True,
                "supervisor_may_auto_run": False,
                "reason": "Registers this discovered local Hermes/OpenAI-compatible provider after exact approval.",
            }
        )
        for model in _provider_model_rows(provider):
            model_id = str(model.get("id") or "").strip()
            if not model_id:
                continue
            profile_id = f"hermes-{slug_id_part(model_id)}"
            actions.append(
                {
                    "label": f"Add {model_id}",
                    "command": (
                        f"devflow agent add-model --provider {provider_id} --model {model_id} "
                        "--authority advisory --role frontier_planner_architect_reviewer "
                        f"--profile-id {profile_id}"
                    ),
                    "scope": "agent_catalog",
                    "safety_class": "approval_required_task_state",
                    "requires_human_approval": True,
                    "supervisor_may_auto_run": False,
                    "reason": "Adds a bounded advisory profile for the discovered local model.",
                }
            )
    return actions


def _safe_provider_id_from_discovery(provider: dict[str, Any]) -> str | None:
    provider_id = str(provider.get("id") or provider.get("name") or "").strip()
    if provider_id.startswith("hermes:"):
        provider_id = provider_id.split(":", 1)[1]
    provider_id = _slug(provider_id)
    return provider_id if SAFE_ID_PATTERN.match(provider_id) else None


def _authority_for_agent(agent: AgentDefinition) -> str:
    if not agent.enabled:
        return "disabled"
    if agent.default_mode == "patch_proposal_only":
        return "patch-proposer"
    if agent.default_mode == "workspace_write" and agent.adapter == "ollama_chat":
        return "patch-proposer"
    if agent.default_mode == "frontier_read_only":
        return "advisory"
    return "read-only"
