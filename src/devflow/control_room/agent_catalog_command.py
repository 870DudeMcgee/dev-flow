from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from devflow.control_room.agent_catalog import build_agent_catalog
from devflow.control_room.agent_registry import AgentRegistryError


class AgentCatalogCommandError(ValueError):
    """User-facing agent catalog command error."""


def build_agent_catalog_command_payload(root: Path, *, provider_id: str | None = None) -> dict[str, Any]:
    try:
        return build_agent_catalog(root, provider_id=provider_id)
    except AgentRegistryError as exc:
        raise AgentCatalogCommandError(str(exc)) from exc


def render_agent_catalog_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)


def render_agent_catalog_lines(payload: dict[str, Any]) -> tuple[str, ...]:
    lines = ["providers:"]
    for item in payload["providers"]:
        missing = " missing-env" if item["api_key_env_missing"] else ""
        lines.append(f"- {item['id']} ({item['adapter']}){missing}")

    lines.append("profiles:")
    for profile in payload["profiles"]:
        contract = profile["runtime_contract"]
        lines.append(
            f"- {profile['id']}: {profile['provider']}/{profile['model']} "
            f"{profile['authority']} -> {contract['execution_surface']}"
        )

    hermes_agents = payload.get("hermes_agents", [])
    if hermes_agents:
        lines.append("hermes_agents:")
        for agent in hermes_agents:
            blocked = f" blocked: {agent['blocked_reason']}" if agent.get("blocked_reason") else ""
            lines.append(
                f"- {agent['id']}: {agent['provider']}/{agent['model']} "
                f"profile={agent['hermes_profile']} status={agent['status']}{blocked}"
            )

    local = payload["local_ollama"]
    lines.append(f"local_ollama: {local['status']}")
    if local.get("unregistered_models"):
        lines.append("unregistered_local_models:")
        lines.extend(f"- {model}" for model in local["unregistered_models"])

    local_openai = payload.get("local_openai_compatible", {})
    lines.append(f"local_openai_compatible: {local_openai.get('status', 'none')}")
    local_policy = payload.get("local_model_policy", {})
    if local_policy:
        concurrency = local_policy.get("local_model_concurrency", {})
        default_provider = local_policy.get("default_provider_id")
        default_model = local_policy.get("default_model")
        default_text = f"{default_provider}/{default_model}" if default_provider and default_model else "none"
        lines.append(f"local_model_default: {default_text}")
        lines.append(f"local_model_concurrency: {concurrency.get('mode', 'unknown')}")

    for provider_row in local_openai.get("providers", []):
        model_count = len(provider_row.get("advertised_models") or provider_row.get("configured_models") or [])
        lines.append(
            f"- {provider_row.get('id')}: {provider_row.get('status')} "
            f"({model_count} models, {provider_row.get('base_url')})"
        )
    return tuple(lines)
