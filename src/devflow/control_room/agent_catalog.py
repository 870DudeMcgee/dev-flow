from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

from devflow.control_room.agent_registry import (
    AgentDefinition,
    AgentRegistryError,
    ProviderDefinition,
    SAFE_AGENT_ID_PATTERN as SAFE_ID_PATTERN,
    derive_profile_id,
    load_agent_registry,
    load_provider_registry,
    slug_id_part as _slug,
)
from devflow.control_room.agent_runtime import agent_runtime_contract
from devflow.control_room.local_agent_discovery import discover_local_ollama_models
from devflow.control_room.machine_capability import (
    LOCAL_DEFAULT_MODEL_ID,
    LOCAL_DEFAULT_PROVIDER_ID,
    MachineCapability,
    classify_model_fit,
    discover_machine_capability,
    local_model_concurrency_policy,
)


LOCAL_ENDPOINT_TIMEOUT_SECONDS = 1.0
DEVFLOW_HERMES_PROFILES: dict[str, tuple[str, str]] = {
    "dfcodex55": ("openai-codex", "gpt-5.5"),
    "dfsonnet46": ("openrouter", "anthropic/claude-sonnet-4.6"),
    "dfopus48": ("openrouter", "anthropic/claude-opus-4.8"),
    "dfqwen37max": ("openrouter", "qwen/qwen3.7-max"),
    "dfqwen37plus": ("openrouter", "qwen/qwen3.7-plus"),
    "dfminimaxm3": ("openrouter", "minimax/minimax-m3"),
    "dflocalfast": ("qwen35-mtp", "qwen35-9b-mtp"),
    "dflocallong": ("local", "gemma4:12b-it-qat"),
    "dflocalcode": ("local", "qwen2.5-coder:14b"),
}


def build_agent_catalog(root: Path, *, provider_id: str | None = None) -> dict[str, Any]:
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
    local_ollama = _local_ollama_catalog(registry)
    local_openai_compatible = _local_openai_compatible_catalog(registry, providers, machine=machine)
    local_model_policy = _local_model_policy(local_openai_compatible, local_ollama, machine)
    hermes_agents = configured_hermes_agents()
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
            profile_id = "local-qwen35-mtp" if model_id == LOCAL_DEFAULT_MODEL_ID else derive_profile_id(
                provider_id, model_id, "advisory", "frontier_planner_architect_reviewer"
            )
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


def _local_ollama_catalog(registry: Any) -> dict[str, Any]:
    try:
        report = discover_local_ollama_models()
    except Exception as exc:
        return {
            "status": "unavailable",
            "error": str(exc),
            "installed_models": [],
            "unregistered_models": [],
            "manifests": [],
        }
    installed_names = [model.name for model in report.installed_models]
    registered_models = {agent.model for agent in registry.agents.values() if agent.provider == "ollama"}
    return {
        "status": "ready",
        "installed_models": [model.to_dict() for model in report.installed_models],
        "unregistered_models": sorted(set(installed_names) - registered_models),
        "manifests": [manifest.to_dict() for manifest in report.manifests],
        "errors": list(report.errors),
    }


def _local_model_policy(
    local_openai_compatible: dict[str, Any],
    local_ollama: dict[str, Any],
    machine: MachineCapability,
) -> dict[str, Any]:
    default_provider: dict[str, Any] | None = None
    default_model: dict[str, Any] | None = None
    ready_providers = [
        provider
        for provider in local_openai_compatible.get("providers", [])
        if isinstance(provider, dict) and provider.get("status") == "ready"
    ]
    for provider in ready_providers:
        models = _provider_model_rows(provider)
        preferred = [model for model in models if model.get("id") == LOCAL_DEFAULT_MODEL_ID]
        if preferred:
            default_provider = provider
            default_model = preferred[0]
            break
    if default_provider is None:
        for provider in ready_providers:
            models = _provider_model_rows(provider)
            if provider.get("hermes_default_model"):
                for model in models:
                    if model.get("id") == provider.get("hermes_default_model"):
                        default_provider = provider
                        default_model = model
                        break
            if default_model is not None:
                break
    if default_provider is None:
        for provider in ready_providers:
            models = _provider_model_rows(provider)
            if models:
                default_provider = provider
                default_model = models[0]
                break

    ollama_default = None
    if default_model is None:
        installed = [
            model
            for model in local_ollama.get("installed_models", [])
            if isinstance(model, dict) and model.get("name")
        ]
        if installed:
            ollama_default = installed[0]

    model_id = str(default_model.get("id")) if default_model else str(ollama_default.get("name")) if ollama_default else LOCAL_DEFAULT_MODEL_ID
    provider_id = str(default_provider.get("id")) if default_provider else "ollama" if ollama_default else LOCAL_DEFAULT_PROVIDER_ID
    machine_payload = machine.to_payload()
    machine_payload.pop("local_model_concurrency", None)
    return {
        "default_model": model_id,
        "default_provider_id": provider_id,
        "default_source": default_provider.get("source") if default_provider else "ollama" if ollama_default else "configured_default",
        "machine": machine_payload,
        "local_model_concurrency": local_model_concurrency_policy(),
    }


def _provider_model_rows(provider: dict[str, Any]) -> list[dict[str, Any]]:
    advertised = provider.get("advertised_models")
    if isinstance(advertised, list) and advertised:
        return [item for item in advertised if isinstance(item, dict)]
    configured = provider.get("configured_models")
    if isinstance(configured, list):
        return [item for item in configured if isinstance(item, dict)]
    return []


def configured_hermes_agents() -> list[dict[str, Any]]:
    """Return sanitized Hermes-configured agent rows.

    This is a projection over Hermes configuration, not a Dev-Flow registry
    mutation. It reports key presence without returning key values.
    """

    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    hermes_env_path = Path.home() / ".hermes" / ".env"
    hermes_env_keys = _hermes_env_key_names(hermes_env_path)

    for config_path in _hermes_config_paths():
        if not config_path.exists():
            continue
        try:
            payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue

        profile = _hermes_profile_name(config_path)
        expected_model = DEVFLOW_HERMES_PROFILES.get(profile)
        if expected_model is None:
            continue
        for item in _configured_hermes_model_rows(payload):
            provider = _normalize_hermes_provider_id(item.get("provider"))
            model = _optional_str(item.get("model"))
            if not provider or not model:
                continue
            if (provider, model) != expected_model:
                continue
            key = (profile, provider, model)
            if key in seen:
                continue
            seen.add(key)
            rows.append(
                _hermes_agent_row(
                    profile=profile,
                    provider=provider,
                    model=model,
                    base_url=_optional_str(item.get("base_url")),
                    config_path=config_path,
                    hermes_env_keys=hermes_env_keys,
                    inline_key_present=bool(item.get("api_key_present")),
                )
            )

    return sorted(rows, key=lambda item: item["id"])


def _configured_hermes_model_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    active_model = payload.get("model") if isinstance(payload.get("model"), dict) else {}
    if isinstance(active_model, dict):
        provider = _normalize_hermes_provider_id(active_model.get("provider"))
        model = _optional_str(active_model.get("default") or active_model.get("model") or active_model.get("id"))
        if provider == "openai-codex" and not model:
            model = _optional_str(os.environ.get("DEVFLOW_DF_CODEX_MODEL")) or "gpt-5.5"
        if provider and model:
            rows.append(
                {
                    "provider": provider,
                    "model": model,
                    "base_url": active_model.get("base_url") or _default_hermes_base_url(provider),
                    "api_key_present": bool(active_model.get("api_key")),
                }
            )

    providers = payload.get("providers")
    if isinstance(providers, dict):
        for provider_name, raw_provider in sorted(providers.items()):
            if not isinstance(raw_provider, dict):
                continue
            provider = _normalize_hermes_provider_id(provider_name)
            if not provider:
                continue
            base_url = _optional_str(raw_provider.get("api") or raw_provider.get("base_url"))
            inline_key_present = bool(raw_provider.get("api_key"))
            for model in _hermes_provider_models(raw_provider):
                rows.append(
                    {
                        "provider": provider,
                        "model": model,
                        "base_url": base_url,
                        "api_key_present": inline_key_present,
                    }
                )

    custom_providers = payload.get("custom_providers")
    if isinstance(custom_providers, list):
        for raw_provider in custom_providers:
            if not isinstance(raw_provider, dict):
                continue
            provider = _normalize_hermes_provider_id(raw_provider.get("name"))
            if not provider:
                continue
            base_url = _optional_str(raw_provider.get("base_url") or raw_provider.get("api"))
            inline_key_present = bool(raw_provider.get("api_key"))
            models = _hermes_provider_models(raw_provider)
            configured_model = _optional_str(raw_provider.get("model"))
            if configured_model and configured_model not in models:
                models.append(configured_model)
            for model in models:
                rows.append(
                    {
                        "provider": provider,
                        "model": model,
                        "base_url": base_url,
                        "api_key_present": inline_key_present,
                    }
                )

    return rows


def _hermes_provider_models(raw_provider: dict[str, Any]) -> list[str]:
    models: list[str] = []
    raw_models = raw_provider.get("models")
    if isinstance(raw_models, dict):
        models.extend(str(model).strip() for model in raw_models if str(model).strip())
    elif isinstance(raw_models, list):
        for item in raw_models:
            if isinstance(item, str) and item.strip():
                models.append(item.strip())
            elif isinstance(item, dict):
                model = _optional_str(item.get("id") or item.get("model") or item.get("name"))
                if model:
                    models.append(model)
    default_model = _optional_str(raw_provider.get("default_model"))
    if default_model and default_model not in models:
        models.insert(0, default_model)
    return list(dict.fromkeys(models))


def _hermes_agent_row(
    *,
    profile: str,
    provider: str,
    model: str,
    base_url: str | None,
    config_path: Path,
    hermes_env_keys: set[str],
    inline_key_present: bool,
) -> dict[str, Any]:
    key_env = _hermes_provider_key_env(provider)
    key_status, key_source = _hermes_key_status(
        key_env=key_env,
        hermes_env_keys=hermes_env_keys,
        inline_key_present=inline_key_present,
        base_url=base_url,
        provider=provider,
    )
    blocked_reason = None
    if key_status == "missing" and key_env:
        blocked_reason = f"{key_env} is not present in the process environment or Hermes env file."
    agent_id = f"hermes-{_hermes_id_slug(profile)}-{_hermes_id_slug(provider)}-{_hermes_id_slug(model)}"
    label = _hermes_agent_label(provider, model)
    status = "blocked" if blocked_reason else "available"
    return {
        "id": agent_id[:80].rstrip("-_"),
        "label": label,
        "source": "hermes",
        "adapter": "hermes_profile",
        "provider": provider,
        "model": model,
        "base_url": base_url,
        "hermes_profile": profile,
        "config_path": config_path.as_posix(),
        "status": status,
        "blocked_reason": blocked_reason,
        "key_env": key_env,
        "key_status": key_status,
        "key_source": key_source,
        "runtime_contract": _hermes_agent_runtime_contract(profile),
    }


def _hermes_agent_runtime_contract(profile: str) -> dict[str, Any]:
    next_command = "hermes chat -q <prompt>" if profile == "default" else f"hermes -p {profile} chat -q <prompt>"
    return {
        "execution_surface": "hermes_profile_handoff",
        "task_run_allowed": False,
        "agent_run_allowed": False,
        "packet_allowed": True,
        "refusal_reason": "Hermes-configured agents are launched through Hermes profile packets, not Dev-Flow task-run execution.",
        "next_command": next_command,
        "evidence_contract": {
            "required_outputs": [
                "Create a Dev-Flow serial packet with model identity, allowed files, and verification commands.",
                "Hermes launch evidence, if run, must stay under .devflow/local-agent-runs/<run-id>/.",
            ],
            "optional_outputs": [],
            "forbidden_outputs": [
                "<main_checkout>/**",
                "<task>/task.yaml",
                "<task>/events.jsonl",
                "<task>/verification.json",
                "<task>/merge-readiness.json",
                ".git/**",
            ],
        },
    }


def _hermes_profile_name(config_path: Path) -> str:
    parts = config_path.parts
    if len(parts) >= 3 and parts[-1] == "config.yaml" and parts[-3] == "profiles":
        return _hermes_id_slug(parts[-2])
    return "default"


def _normalize_hermes_provider_id(value: object) -> str | None:
    text = _optional_str(value)
    if not text:
        return None
    if text.startswith("custom:"):
        text = text.split(":", 1)[1].strip()
    return text or None


def _default_hermes_base_url(provider: str) -> str | None:
    if provider == "openrouter":
        return "https://openrouter.ai/api/v1"
    if provider == "openai-codex":
        return "https://chatgpt.com/backend-api/codex"
    return None


def _hermes_provider_key_env(provider: str) -> str | None:
    if provider == "openrouter":
        return "OPENROUTER_API_KEY"
    if provider in {"openai", "openai-chat"}:
        return "OPENAI_API_KEY"
    if provider == "anthropic":
        return "ANTHROPIC_API_KEY"
    if provider in {"gemini", "google"}:
        return "GEMINI_API_KEY"
    if provider in {"xai", "grok"}:
        return "XAI_API_KEY"
    return None


def _hermes_key_status(
    *,
    key_env: str | None,
    hermes_env_keys: set[str],
    inline_key_present: bool,
    base_url: str | None,
    provider: str,
) -> tuple[str, str | None]:
    if provider == "openai-codex":
        return "managed_by_hermes", "hermes_auth"
    if key_env is None:
        if _is_local_http_base_url(base_url):
            return "not_required", None
        if inline_key_present:
            return "available", "hermes_config"
        return "not_checked", None
    if os.environ.get(key_env):
        return "available", "process_env"
    if key_env in hermes_env_keys:
        return "available", "hermes_env"
    if inline_key_present:
        return "available", "hermes_config"
    return "missing", None


def _hermes_env_key_names(env_path: Path) -> set[str]:
    if not env_path.exists():
        return set()
    keys: set[str] = set()
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip()
        if key and value.strip() and key.replace("_", "").isalnum():
            keys.add(key)
    return keys


def _hermes_agent_label(provider: str, model: str) -> str:
    if provider == "openrouter":
        return f"Hermes OpenRouter - {model}"
    if provider == "openai-codex":
        return f"Hermes Codex - {model}"
    return f"Hermes {provider} - {model}"


def _hermes_id_slug(value: str) -> str:
    value = value.lower().replace(":", "-").replace("/", "-").replace(".", "-")
    value = re.sub(r"[^a-z0-9_-]+", "-", value)
    value = re.sub(r"[-_]{2,}", "-", value).strip("-_")
    return value or "model"


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _local_openai_compatible_catalog(registry: Any, providers: Any, *, machine: MachineCapability) -> dict[str, Any]:
    provider_rows = _local_openai_provider_rows(providers)
    provider_rows.extend(_hermes_custom_provider_rows())
    if not provider_rows:
        return {"status": "none", "providers": [], "unregistered_models": []}

    seen: set[tuple[str, str]] = set()
    discovered = []
    for row in provider_rows:
        key = (row["id"], row["base_url"])
        if key in seen:
            continue
        seen.add(key)
        discovered.append(_discover_openai_compatible_provider(row, machine=machine))

    registered_by_provider: dict[str, set[str]] = {}
    for agent in registry.agents.values():
        registered_by_provider.setdefault(agent.provider, set()).add(agent.model)

    unregistered = []
    for provider in discovered:
        registered = registered_by_provider.get(provider["id"], set())
        model_ids = {
            item["id"]
            for item in provider.get("advertised_models", [])
            if isinstance(item, dict) and item.get("id")
        }
        if not model_ids:
            model_ids = {
                item["id"]
                for item in provider.get("configured_models", [])
                if isinstance(item, dict) and item.get("id")
            }
        for model_id in sorted(model_ids - registered):
            unregistered.append(
                {
                    "provider_id": provider["id"],
                    "model": model_id,
                    "source": provider["source"],
                    "base_url": provider["base_url"],
                }
            )

    ready = any(provider["status"] == "ready" for provider in discovered)
    return {
        "status": "ready" if ready else "unavailable",
        "providers": discovered,
        "unregistered_models": unregistered,
    }


def _profile_availability(
    agent: AgentDefinition,
    *,
    provider: ProviderDefinition | None,
    local_ollama: dict[str, Any],
    local_openai_compatible: dict[str, Any],
) -> dict[str, Any]:
    if not agent.enabled:
        return {"status": "disabled", "source": "registry", "reason": "agent_disabled"}

    if agent.provider == "ollama" or agent.adapter == "ollama_chat":
        if local_ollama.get("status") != "ready":
            return {"status": "unknown", "source": "ollama", "reason": local_ollama.get("error") or "ollama_unavailable"}
        installed = {item.get("name") for item in local_ollama.get("installed_models", []) if isinstance(item, dict)}
        if agent.model in installed:
            return {"status": "available", "source": "ollama", "reason": None}
        return {"status": "missing", "source": "ollama", "reason": "model_not_installed"}

    if provider and provider.adapter in {"openai_compatible", "openai_chat"} and _is_local_http_base_url(provider.base_url):
        matching = [
            item
            for item in local_openai_compatible.get("providers", [])
            if isinstance(item, dict) and item.get("id") == provider.id
        ]
        if not matching:
            return {"status": "unknown", "source": "local_openai_compatible", "reason": "provider_not_discovered"}
        endpoint = matching[0]
        if endpoint.get("status") != "ready":
            return {
                "status": "unavailable",
                "source": "local_openai_compatible",
                "reason": endpoint.get("error") or "endpoint_unavailable",
            }
        available_models = _provider_model_id_set(endpoint)
        if agent.model in available_models:
            return {"status": "available", "source": "local_openai_compatible", "reason": None}
        return {"status": "missing", "source": "local_openai_compatible", "reason": "model_not_advertised"}

    return {"status": "not_checked", "source": "registry", "reason": "not_local_discovery_surface"}


def _local_openai_provider_rows(providers: Any) -> list[dict[str, Any]]:
    rows = []
    for provider in sorted(providers.providers.values(), key=lambda item: item.id):
        if provider.adapter not in {"openai_compatible", "openai_chat"}:
            continue
        if not provider.enabled or not _is_local_http_base_url(provider.base_url):
            continue
        rows.append(
            {
                "id": provider.id,
                "name": provider.id,
                "source": "devflow",
                "base_url": provider.base_url,
                "configured_model": None,
                "configured_models": [],
            }
        )
    return rows


def _hermes_custom_provider_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for path in _hermes_config_paths():
        if not path.exists():
            continue
        try:
            payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        active_model = payload.get("model") if isinstance(payload.get("model"), dict) else {}
        active_provider_name = _custom_provider_name(active_model.get("provider")) if isinstance(active_model, dict) else None
        active_default_model = str(active_model.get("default") or active_model.get("model") or "").strip() if isinstance(active_model, dict) else ""
        raw_providers = payload.get("custom_providers")
        if isinstance(active_model, dict) and active_provider_name and active_model.get("base_url"):
            raw_providers = list(raw_providers) if isinstance(raw_providers, list) else []
            raw_providers.append(
                {
                    "name": active_provider_name,
                    "base_url": active_model.get("base_url"),
                    "model": active_default_model,
                    "models": {
                        active_default_model: {
                            "context_length": active_model.get("context_length"),
                            "supports_vision": active_model.get("supports_vision"),
                        }
                    }
                    if active_default_model
                    else {},
                    "_hermes_active_default": True,
                }
            )
        if not isinstance(raw_providers, list):
            continue
        for raw_provider in raw_providers:
            if not isinstance(raw_provider, dict):
                continue
            name = str(raw_provider.get("name") or "").strip()
            base_url = str(raw_provider.get("base_url") or "").strip()
            if not name or not base_url or not _is_local_http_base_url(base_url):
                continue
            key = (name, base_url)
            if key in seen:
                continue
            seen.add(key)
            configured_model = str(raw_provider.get("model") or "").strip() or None
            is_active_default = bool(raw_provider.get("_hermes_active_default")) or (
                active_provider_name == name and bool(active_default_model)
            )
            rows.append(
                {
                    "id": f"hermes:{_slug(name)}",
                    "name": name,
                    "source": "hermes",
                    "base_url": base_url,
                    "configured_model": configured_model,
                    "configured_models": _configured_models_from_hermes(raw_provider.get("models")),
                    "config_path": path.as_posix(),
                    "hermes_default_model": active_default_model if is_active_default else None,
                    "hermes_default_provider": bool(is_active_default),
                }
            )
    return rows


def _custom_provider_name(value: object) -> str | None:
    text = str(value or "").strip()
    if not text.startswith("custom:"):
        return None
    name = text.split(":", 1)[1].strip()
    return name or None


def _hermes_config_paths() -> list[Path]:
    hermes_root = Path.home() / ".hermes"
    paths = [hermes_root / "config.yaml"]
    profiles_dir = hermes_root / "profiles"
    if profiles_dir.is_dir():
        paths.extend(sorted(profiles_dir.glob("*/config.yaml")))
    return paths


def _configured_models_from_hermes(raw_models: object) -> list[dict[str, Any]]:
    if not isinstance(raw_models, dict):
        return []
    models = []
    for model_id, raw_meta in sorted(raw_models.items()):
        if not isinstance(model_id, str):
            continue
        meta = raw_meta if isinstance(raw_meta, dict) else {}
        models.append(
            {
                "id": model_id,
                "context_length": _int_or_none(meta.get("context_length")),
                "n_params": _int_or_none(meta.get("n_params") or meta.get("parameter_count") or meta.get("parameters")),
                "supports_vision": bool(meta.get("supports_vision")) if "supports_vision" in meta else None,
            }
        )
    return models


def _discover_openai_compatible_provider(row: dict[str, Any], *, machine: MachineCapability) -> dict[str, Any]:
    result = {
        "id": row["id"],
        "name": row["name"],
        "source": row["source"],
        "base_url": row["base_url"],
        "configured_model": row.get("configured_model"),
        "configured_models": row.get("configured_models", []),
        "hermes_default_model": row.get("hermes_default_model"),
        "hermes_default_provider": bool(row.get("hermes_default_provider")),
        "status": "unavailable",
        "advertised_models": [],
    }
    if row.get("config_path"):
        result["config_path"] = row["config_path"]
    try:
        request = urllib.request.Request(_models_url(row["base_url"]), headers={"Accept": "application/json"})
        with urllib.request.urlopen(request, timeout=LOCAL_ENDPOINT_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        result["error"] = str(exc)
        return result
    result["status"] = "ready"
    result["advertised_models"] = _annotate_model_fit(
        _advertised_models_from_payload(payload),
        machine=machine,
        preferred_model=str(row.get("hermes_default_model") or row.get("configured_model") or ""),
    )
    result["configured_models"] = _annotate_model_fit(
        result["configured_models"],
        machine=machine,
        preferred_model=str(row.get("hermes_default_model") or row.get("configured_model") or ""),
    )
    return result


def _annotate_model_fit(
    rows: list[dict[str, Any]], *, machine: MachineCapability, preferred_model: str
) -> list[dict[str, Any]]:
    annotated = []
    for row in rows:
        item = dict(row)
        model_id = str(item.get("id") or "")
        preferred = model_id == LOCAL_DEFAULT_MODEL_ID or (bool(preferred_model) and model_id == preferred_model)
        item["machine_fit"] = classify_model_fit(item, machine=machine, preferred=preferred)
        annotated.append(item)
    return annotated


def _advertised_models_from_payload(payload: object) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    rows: dict[str, dict[str, Any]] = {}
    for item in payload.get("data", []) if isinstance(payload.get("data"), list) else []:
        if not isinstance(item, dict):
            continue
        model_id = item.get("id")
        if not isinstance(model_id, str) or not model_id:
            continue
        meta = item.get("meta") if isinstance(item.get("meta"), dict) else {}
        rows[model_id] = {
            "id": model_id,
            "owned_by": item.get("owned_by"),
            "context_length": _int_or_none(meta.get("n_ctx") or item.get("context_length")),
            "n_params": _int_or_none(meta.get("n_params") or item.get("n_params") or item.get("parameter_count")),
        }
    for item in payload.get("models", []) if isinstance(payload.get("models"), list) else []:
        if not isinstance(item, dict):
            continue
        model_id = item.get("model") or item.get("name") or item.get("id")
        if not isinstance(model_id, str) or not model_id:
            continue
        row = rows.setdefault(
            model_id,
            {"id": model_id, "owned_by": item.get("owned_by"), "context_length": None, "n_params": None},
        )
        details = item.get("details") if isinstance(item.get("details"), dict) else {}
        row.setdefault("owned_by", item.get("owned_by"))
        row["context_length"] = row.get("context_length") or _int_or_none(item.get("context_length") or details.get("n_ctx"))
        row["n_params"] = row.get("n_params") or _int_or_none(item.get("n_params") or details.get("n_params"))
    return [rows[key] for key in sorted(rows)]


def _provider_model_id_set(provider: dict[str, Any]) -> set[str]:
    model_ids = {
        item.get("id")
        for item in provider.get("advertised_models", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    model_ids.update(
        item.get("id")
        for item in provider.get("configured_models", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    )
    return {model_id for model_id in model_ids if isinstance(model_id, str)}


def _models_url(base_url: str) -> str:
    stripped = base_url.rstrip("/")
    parsed = urlparse(stripped)
    path = parsed.path.rstrip("/")
    if path.endswith("/v1"):
        return f"{stripped}/models"
    return f"{stripped}/v1/models"


def _is_local_http_base_url(base_url: str | None) -> bool:
    if base_url is None or not base_url.strip():
        return False
    parsed = urlparse(base_url)
    return parsed.scheme in {"http", "https"} and parsed.hostname in {"127.0.0.1", "localhost", "::1"}


def _int_or_none(value: object) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        stripped = value.strip().lower().replace(",", "")
        scaled = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)\s*([bmk])", stripped)
        if scaled:
            multiplier = {"b": 1_000_000_000, "m": 1_000_000, "k": 1_000}[scaled.group(2)]
            return int(float(scaled.group(1)) * multiplier)
        digits = re.sub(r"[^0-9]", "", stripped)
        return int(digits) if digits else None
    return None


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
