from __future__ import annotations

import re
import shlex
from typing import Any

from devflow.control_room.agent_registry import slug_id_part


LOCAL_DISCOVERY_SOURCES = {"ollama", "local_openai_compatible"}


def build_local_model_inventory(agent_catalog: dict[str, Any]) -> dict[str, Any]:
    catalog = agent_catalog if isinstance(agent_catalog, dict) else {}
    policy = _mapping(catalog.get("local_model_policy"))
    machine = _mapping(policy.get("machine"))
    concurrency = _mapping(policy.get("local_model_concurrency"))
    local_ollama = _mapping(catalog.get("local_ollama"))
    local_openai = _mapping(catalog.get("local_openai_compatible"))
    profiles = _dict_rows(catalog.get("profiles"))
    endpoint_providers = _dict_rows(local_openai.get("providers"))

    rows: list[dict[str, Any]] = []
    registered_profile_keys: set[tuple[str, str]] = set()
    seen_endpoint_identity_keys: set[tuple[str, str, str]] = set()
    for profile in profiles:
        row = _registered_profile_row(profile, endpoint_providers, local_ollama)
        if row is None:
            continue
        rows.append(row)
        provider_id = row.get("provider_id")
        model = row.get("model")
        if isinstance(provider_id, str) and isinstance(model, str):
            registered_profile_keys.add((provider_id, model))

    for model_name in _string_rows(local_ollama.get("unregistered_models")):
        installed = _installed_ollama_model(local_ollama, model_name)
        manifest = _ollama_manifest(local_ollama, model_name)
        rows.append(_unregistered_ollama_row(model_name, installed, manifest))

    for provider in endpoint_providers:
        rows.extend(_endpoint_rows(provider, registered_profile_keys, seen_endpoint_identity_keys))

    default_model = _text_or_none(policy.get("default_model"))
    default_provider_id = _text_or_none(policy.get("default_provider_id"))
    rows.sort(key=lambda row: _row_sort_key(row, default_model))
    actions = [row["action"] for row in rows if isinstance(row.get("action"), dict)]

    return {
        "schema_version": 1,
        "summary": {
            "default_model": default_model,
            "default_provider_id": default_provider_id,
            "machine_label": _machine_label(machine),
            "concurrency_label": _concurrency_label(concurrency),
            "ollama_installed_count": len(_dict_rows(local_ollama.get("installed_models"))),
            "local_endpoint_model_count": _local_endpoint_model_count(endpoint_providers),
            "available_profile_count": sum(
                1
                for row in rows
                if row.get("kind") == "registered_profile" and row.get("status") == "available"
            ),
            "unregistered_count": len(_string_rows(local_ollama.get("unregistered_models")))
            + len(_dict_rows(local_openai.get("unregistered_models"))),
        },
        "machine": machine,
        "concurrency": concurrency,
        "rows": rows,
        "actions": actions,
    }


def _registered_profile_row(
    profile: dict[str, Any],
    endpoint_providers: list[dict[str, Any]],
    local_ollama: dict[str, Any],
) -> dict[str, Any] | None:
    availability = _mapping(profile.get("availability"))
    source = _text(availability.get("source"))
    if source not in LOCAL_DISCOVERY_SOURCES:
        return None
    profile_id = _text(profile.get("id"))
    model = _text(profile.get("model"))
    provider_id = _text(profile.get("provider"))
    if not profile_id or not model or not provider_id:
        return None

    endpoint_model = _endpoint_model(endpoint_providers, provider_id, model) if source == "local_openai_compatible" else {}
    manifest = _ollama_manifest(local_ollama, model) if source == "ollama" else {}
    machine_fit = _mapping(endpoint_model.get("machine_fit"))
    status = _text(availability.get("status")) or "unknown"
    detail = "Registered profile is available on this machine." if status == "available" else _profile_detail(status, availability)

    return {
        "row_id": f"profile:{profile_id}",
        "kind": "registered_profile",
        "provider_id": provider_id,
        "provider_label": _provider_label(endpoint_providers, provider_id),
        "model": model,
        "profile_id": profile_id,
        "selectable_profile_id": profile_id if status == "available" else None,
        "status": status,
        "status_label": _status_label(status),
        "source": source,
        "adapter": _text(profile.get("adapter")) or None,
        "role": _text(profile.get("role")) or None,
        "authority": _text(profile.get("authority")) or None,
        "size": None,
        "context_length": _first_int(endpoint_model.get("context_length"), manifest.get("context_length")),
        "n_params": _first_int(endpoint_model.get("n_params"), _manifest_n_params(manifest)),
        "weight_class": _text(machine_fit.get("weight_class")) or None,
        "machine_fit_status": _text(machine_fit.get("status")) or None,
        "machine_fit_reason": _text(machine_fit.get("reason")) or None,
        "action": None,
        "detail": detail,
    }


def _unregistered_ollama_row(
    model_name: str,
    installed: dict[str, Any],
    manifest: dict[str, Any],
) -> dict[str, Any]:
    command = (
        "devflow agent add-model "
        f"--provider {shlex.quote('ollama')} "
        f"--model {shlex.quote(model_name)} "
        "--authority read-only --role local_senior_worker --json"
    )
    return {
        "row_id": f"ollama:{model_name}",
        "kind": "unregistered_ollama_model",
        "provider_id": "ollama",
        "provider_label": "Ollama",
        "model": model_name,
        "profile_id": None,
        "selectable_profile_id": None,
        "status": "needs_profile",
        "status_label": "Needs profile",
        "source": "ollama",
        "adapter": "ollama_chat",
        "role": "local_senior_worker",
        "authority": "read-only",
        "size": installed.get("size"),
        "context_length": _first_int(manifest.get("context_length")),
        "n_params": _manifest_n_params(manifest),
        "weight_class": None,
        "machine_fit_status": None,
        "machine_fit_reason": None,
        "action": _action("Add profile", command, "Adds this installed Ollama model as a read-only local worker profile."),
        "detail": "Installed locally but not registered as a Dev-Flow profile.",
    }


def _endpoint_rows(
    provider: dict[str, Any],
    registered_profile_keys: set[tuple[str, str]],
    seen_identity_keys: set[tuple[str, str, str]],
) -> list[dict[str, Any]]:
    provider_id = _text(provider.get("id"))
    if not provider_id:
        return []
    provider_label = _text(provider.get("name")) or provider_id
    base_url = _text(provider.get("base_url"))
    status = _text(provider.get("status")) or "unknown"
    if status != "ready":
        return [
            {
                "row_id": f"endpoint:{provider_id}",
                "kind": "local_endpoint",
                "provider_id": provider_id,
                "provider_label": provider_label,
                "model": None,
                "profile_id": None,
                "selectable_profile_id": None,
                "status": "unavailable",
                "status_label": "Unavailable",
                "source": "local_openai_compatible",
                "adapter": "openai_compatible",
                "role": None,
                "authority": None,
                "size": None,
                "context_length": None,
                "n_params": None,
                "weight_class": None,
                "machine_fit_status": None,
                "machine_fit_reason": None,
                "action": _provider_action(provider_id, base_url),
                "detail": _offline_endpoint_detail(provider_label, base_url, _text(provider.get("error"))),
            }
        ]

    rows = []
    for model in _provider_model_rows(provider):
        model_id = _text(model.get("id"))
        if not model_id:
            continue
        profile_id = _endpoint_profile_id(provider_id, model_id)
        identity_key = (_text(base_url), model_id, profile_id)
        if identity_key in seen_identity_keys:
            continue
        seen_identity_keys.add(identity_key)
        machine_fit = _mapping(model.get("machine_fit"))
        registered = (provider_id, model_id) in registered_profile_keys
        rows.append(
            {
                "row_id": f"endpoint:{provider_id}:{model_id}",
                "kind": "local_endpoint_model",
                "provider_id": provider_id,
                "provider_label": provider_label,
                "model": model_id,
                "profile_id": None,
                "selectable_profile_id": None,
                "status": "ready" if registered else "needs_profile",
                "status_label": "Ready" if registered else "Needs profile",
                "source": "local_openai_compatible",
                "adapter": "openai_compatible",
                "role": "frontier_planner_architect_reviewer",
                "authority": "advisory",
                "size": None,
                "context_length": _first_int(model.get("context_length")),
                "n_params": _first_int(model.get("n_params")),
                "weight_class": _text(machine_fit.get("weight_class")) or None,
                "machine_fit_status": _text(machine_fit.get("status")) or None,
                "machine_fit_reason": _text(machine_fit.get("reason")) or None,
                "action": None if registered else _endpoint_model_action(provider_id, model_id, base_url),
                "detail": "Endpoint model is ready." if registered else "Endpoint model is discovered but not registered.",
            }
        )
    return rows


def _endpoint_model_action(provider_id: str, model_id: str, base_url: str) -> dict[str, Any] | None:
    safe_provider_id = _safe_endpoint_provider_id(provider_id)
    if not safe_provider_id:
        return None
    if safe_provider_id != provider_id:
        command = (
            "devflow agent add-provider "
            f"{shlex.quote(safe_provider_id)} --adapter openai_compatible "
            f"--base-url {shlex.quote(base_url)} --json"
        )
        return _action("Register provider", command, "Registers this local OpenAI-compatible endpoint.")
    profile_id = _endpoint_profile_id(provider_id, model_id)
    profile_option = f" --profile-id {shlex.quote(profile_id)}" if profile_id else ""
    command = (
        "devflow agent add-model "
        f"--provider {shlex.quote(safe_provider_id)} "
        f"--model {shlex.quote(model_id)} "
        "--authority advisory --role frontier_planner_architect_reviewer"
        f"{profile_option} --json"
    )
    return _action("Add profile", command, "Adds this local endpoint model as an advisory profile.")


def _endpoint_profile_id(provider_id: str, model_id: str) -> str | None:
    return _local_profile_id(model_id)


def _local_profile_id(model_id: str) -> str:
    return f"hermes-{slug_id_part(model_id)}"


def _provider_action(provider_id: str, base_url: str) -> dict[str, Any] | None:
    safe_provider_id = _safe_endpoint_provider_id(provider_id)
    if not safe_provider_id or not base_url:
        return None
    command = (
        "devflow agent add-provider "
        f"{shlex.quote(safe_provider_id)} --adapter openai_compatible "
        f"--base-url {shlex.quote(base_url)} --json"
    )
    return _action("Register provider", command, "Registers this local OpenAI-compatible endpoint.")


def _offline_endpoint_detail(provider_label: str, base_url: str, error: str | None) -> str:
    target = f"{provider_label} at {base_url}" if base_url else provider_label
    if error:
        return f"Offline endpoint: {target}. {error}"
    return f"Offline endpoint: {target}."


def _action(label: str, command: str, reason: str) -> dict[str, Any]:
    return {
        "label": label,
        "command": command,
        "scope": "agent_catalog",
        "safety_class": "approval_required_task_state",
        "requires_human_approval": True,
        "supervisor_may_auto_run": False,
        "reason": reason,
    }


def _endpoint_model(
    providers: list[dict[str, Any]],
    provider_id: str,
    model_id: str,
) -> dict[str, Any]:
    for provider in providers:
        if provider.get("id") != provider_id:
            continue
        for model in _provider_model_rows(provider):
            if model.get("id") == model_id:
                return model
    for provider in providers:
        for model in _provider_model_rows(provider):
            if model.get("id") == model_id:
                return model
    return {}


def _provider_label(providers: list[dict[str, Any]], provider_id: str) -> str:
    for provider in providers:
        if provider.get("id") == provider_id:
            return _text(provider.get("name")) or provider_id
    return provider_id


def _provider_model_rows(provider: dict[str, Any]) -> list[dict[str, Any]]:
    advertised = _dict_rows(provider.get("advertised_models"))
    if advertised:
        return advertised
    return _dict_rows(provider.get("configured_models"))


def _local_endpoint_model_count(providers: list[dict[str, Any]]) -> int:
    return sum(len(_provider_model_rows(provider)) for provider in providers if provider.get("status") == "ready")


def _installed_ollama_model(local_ollama: dict[str, Any], model_name: str) -> dict[str, Any]:
    for model in _dict_rows(local_ollama.get("installed_models")):
        if model.get("name") == model_name:
            return model
    return {}


def _ollama_manifest(local_ollama: dict[str, Any], model_name: str) -> dict[str, Any]:
    for manifest in _dict_rows(local_ollama.get("manifests")):
        if manifest.get("model") == model_name:
            return manifest
    return {}


def _manifest_n_params(manifest: dict[str, Any]) -> int | None:
    billions = manifest.get("parameter_count_billions")
    if isinstance(billions, bool) or billions is None:
        return None
    if isinstance(billions, (int, float)):
        return int(float(billions) * 1_000_000_000)
    return None


def _profile_detail(status: str, availability: dict[str, Any]) -> str:
    reason = _text(availability.get("reason"))
    if status == "missing":
        return "Registered profile exists, but the model is not currently available."
    if status == "unavailable":
        return reason or "Registered profile exists, but the local endpoint is unavailable."
    if status == "disabled":
        return "Registered profile is disabled."
    return reason or "Registered profile availability is not confirmed."


def _row_sort_key(row: dict[str, Any], default_model: str | None) -> tuple[int, int, str]:
    kind = row.get("kind")
    status = row.get("status")
    if kind == "registered_profile" and status == "available":
        group = 0
    elif kind == "unregistered_ollama_model":
        group = 1
    elif kind == "local_endpoint_model":
        group = 2
    elif status == "unavailable" or kind == "local_endpoint":
        group = 3
    else:
        group = 4
    default_rank = 0 if default_model and row.get("model") == default_model else 1
    return (default_rank, group, _text(row.get("row_id")))


def _machine_label(machine: dict[str, Any]) -> str:
    machine_class = _text(machine.get("machine_class")) or "unknown"
    memory = machine.get("total_memory_gb")
    if isinstance(memory, bool) or memory is None:
        return machine_class
    try:
        return f"{int(memory)}GB {machine_class}"
    except (TypeError, ValueError):
        return machine_class


def _concurrency_label(concurrency: dict[str, Any]) -> str:
    if concurrency.get("mode") == "single_flight":
        return "one local model at a time"
    max_runs = concurrency.get("max_parallel_local_model_runs")
    if isinstance(max_runs, int) and max_runs > 1:
        return f"up to {max_runs} local models at a time"
    return "local model concurrency unknown"


def _status_label(status: str) -> str:
    labels = {
        "available": "Available",
        "disabled": "Disabled",
        "missing": "Missing",
        "needs_profile": "Needs profile",
        "ready": "Ready",
        "unavailable": "Unavailable",
        "unknown": "Unknown",
    }
    return labels.get(status, status.replace("_", " ").title())


def _safe_endpoint_provider_id(provider_id: str) -> str | None:
    value = provider_id
    if value.startswith("hermes:"):
        value = value.split(":", 1)[1]
    value = _slug(value)
    return value if re.fullmatch(r"[a-z][a-z0-9_-]{1,79}", value) else None


def _slug(value: str) -> str:
    text = value.strip().lower()
    text = re.sub(r"[^a-z0-9_-]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-_")
    if text and not text[0].isalpha():
        text = f"agent-{text}"
    return text


def _mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _dict_rows(value: object) -> list[dict[str, Any]]:
    return [dict(item) for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _string_rows(value: object) -> list[str]:
    return [item for item in value if isinstance(item, str) and item.strip()] if isinstance(value, list) else []


def _first_int(*values: object) -> int | None:
    for value in values:
        if isinstance(value, bool) or value is None:
            continue
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str):
            try:
                return int(value)
            except ValueError:
                continue
    return None


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""


def _text_or_none(value: object) -> str | None:
    text = _text(value)
    return text or None
