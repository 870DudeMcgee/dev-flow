from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

from devflow.control_room.agent_registry import slug_id_part as _slug


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


def configured_hermes_local_provider_rows() -> list[dict[str, Any]]:
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


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
