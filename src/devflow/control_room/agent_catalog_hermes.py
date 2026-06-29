from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

from devflow.control_room.agent_registry import slug_id_part as _slug
from devflow.control_room.hermes_profile_resolver import (
    configured_hermes_agent_rows,
)


def configured_hermes_agents(root: Path | None = None) -> list[dict[str, Any]]:
    """Return sanitized Hermes-configured agent rows.

    This is a projection over Hermes configuration, not a Dev-Flow registry
    mutation. It reports key presence without returning key values.
    """
    return configured_hermes_agent_rows(root)

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
