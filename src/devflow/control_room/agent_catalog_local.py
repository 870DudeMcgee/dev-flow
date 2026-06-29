from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlparse

from devflow.control_room.agent_catalog_hermes import (
    configured_hermes_local_provider_rows,
)
from devflow.control_room.agent_registry import AgentDefinition, ProviderDefinition
from devflow.control_room.local_agent_discovery import discover_local_ollama_models
from devflow.control_room.machine_capability import (
    LOCAL_DEFAULT_MODEL_ID,
    LOCAL_DEFAULT_PROVIDER_ID,
    MachineCapability,
    classify_model_fit,
    local_model_concurrency_policy,
)


LOCAL_ENDPOINT_TIMEOUT_SECONDS = 1.0


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


def _local_openai_compatible_catalog(
    registry: Any,
    providers: Any,
    *,
    machine: MachineCapability,
    live_discovery: bool = True,
) -> dict[str, Any]:
    provider_rows = _local_openai_provider_rows(providers)
    provider_rows.extend(configured_hermes_local_provider_rows())
    if not provider_rows:
        return {"status": "none", "providers": [], "unregistered_models": []}

    seen: set[tuple[str, str]] = set()
    discovered = []
    for row in provider_rows:
        key = (row["id"], row["base_url"])
        if key in seen:
            continue
        seen.add(key)
        discovered.append(
            _discover_openai_compatible_provider(row, machine=machine, live_discovery=live_discovery)
        )

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


def _discover_openai_compatible_provider(
    row: dict[str, Any], *, machine: MachineCapability, live_discovery: bool = True
) -> dict[str, Any]:
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
    if not live_discovery:
        result["status"] = "not_checked"
        result["error"] = "live_discovery_disabled"
        result["configured_models"] = _annotate_model_fit(
            result["configured_models"],
            machine=machine,
            preferred_model=str(row.get("hermes_default_model") or row.get("configured_model") or ""),
        )
        return result
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
