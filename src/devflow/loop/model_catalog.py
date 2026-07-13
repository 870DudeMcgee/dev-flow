"""Dynamic free-cloud model discovery and capability classification.

The generated snapshot is the shared, read-only source consumed by routing,
the control room, and the Obsidian inventory renderer. It does not mutate the
static machine registry or promote paid models.
"""

from __future__ import annotations

import hashlib
import json
import os
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Callable, Mapping


OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
CATALOG_SCHEMA_VERSION = 1

_CODING_TERMS = (
    "code",
    "coding",
    "developer",
    "programming",
    "repository",
    "software engineering",
    "swe",
)
_REASONING_TERMS = (
    "analysis",
    "judge",
    "planning",
    "reasoner",
    "reasoning",
)
_RESEARCH_TERMS = (
    "agent",
    "research",
    "search",
    "tool",
)
_SAFETY_TERMS = (
    "classification",
    "classifier",
    "moderation",
    "safety",
)


@dataclass(frozen=True)
class CatalogRefreshResult:
    """Semantic result of one catalog refresh."""

    changed: bool
    added: tuple[str, ...]
    removed: tuple[str, ...]
    modified: tuple[str, ...]
    current_path: Path
    history_path: Path | None
    model_count: int


def fetch_openrouter_catalog(*, timeout: float = 30.0) -> dict:
    """Fetch OpenRouter's public model catalog without requiring credentials."""

    request = urllib.request.Request(
        OPENROUTER_MODELS_URL,
        headers={
            "Accept": "application/json",
            "User-Agent": "DevFlow-model-catalog/1",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.load(response)
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise ValueError("OpenRouter catalog response did not contain a data list.")
    return payload


def _is_zero_price(value: object) -> bool:
    try:
        return Decimal(str(value)) == 0
    except (InvalidOperation, TypeError, ValueError):
        return False


def _advertised_text(raw: Mapping[str, object]) -> str:
    return " ".join(
        str(raw.get(key) or "").lower()
        for key in ("id", "name", "description")
    )


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _safe_int(value: object) -> int:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return 0


def _classify_model(raw: Mapping[str, object]) -> dict:
    architecture = raw.get("architecture")
    architecture = architecture if isinstance(architecture, Mapping) else {}
    inputs = architecture.get("input_modalities")
    outputs = architecture.get("output_modalities")
    input_modalities = sorted(str(value) for value in inputs) if isinstance(inputs, list) else ["text"]
    output_modalities = sorted(str(value) for value in outputs) if isinstance(outputs, list) else ["text"]
    parameters_value = raw.get("supported_parameters")
    parameters = sorted(str(value) for value in parameters_value) if isinstance(parameters_value, list) else []
    parameter_set = set(parameters)
    text = _advertised_text(raw)
    context_length = _safe_int(raw.get("context_length"))

    coding = _contains_any(text, _CODING_TERMS)
    reasoning = bool(
        {"reasoning", "reasoning_effort", "include_reasoning"} & parameter_set
        or _contains_any(text, _REASONING_TERMS)
    )
    tool_calling = "tools" in parameter_set
    structured_output = bool(
        {"structured_outputs", "response_format"} & parameter_set
    )
    capabilities = {
        "coding": coding,
        "image_input": "image" in input_modalities,
        "long_context": context_length >= 131_072,
        "reasoning": reasoning,
        "structured_output": structured_output,
        "tool_calling": tool_calling,
    }

    profiles: list[str] = []
    if coding and (tool_calling or structured_output):
        profiles.append("builder")
    if coding:
        profiles.append("code-scout")
    if reasoning:
        profiles.append("judge-reviewer")
    if reasoning and capabilities["long_context"]:
        profiles.append("planning-specification")
    if tool_calling or reasoning or _contains_any(text, _RESEARCH_TERMS):
        profiles.append("research-scout")
    if capabilities["image_input"]:
        profiles.append("vision-research")
    if _contains_any(text, _SAFETY_TERMS):
        profiles.append("classifier-safety")

    return {
        "capabilities": capabilities,
        "context_length": context_length,
        "eligible_profiles": sorted(profiles),
        "input_modalities": input_modalities,
        "output_modalities": output_modalities,
        "supported_parameters": parameters,
    }


def _is_free_text_chat_model(raw: Mapping[str, object]) -> bool:
    pricing = raw.get("pricing")
    if not isinstance(pricing, Mapping):
        return False
    if not (
        _is_zero_price(pricing.get("prompt"))
        and _is_zero_price(pricing.get("completion"))
    ):
        return False
    architecture = raw.get("architecture")
    if not isinstance(architecture, Mapping):
        return True
    outputs = architecture.get("output_modalities")
    return not isinstance(outputs, list) or outputs == ["text"]


def _normalize_model(raw: Mapping[str, object]) -> dict:
    model_id = str(raw.get("id") or "").strip()
    classified = _classify_model(raw)
    description = str(raw.get("description") or "").strip()
    return {
        "id": model_id,
        "name": str(raw.get("name") or model_id).strip(),
        "description": description,
        "created": raw.get("created"),
        **classified,
        "cost_class": "free_cloud",
        "eligibility": "immediate",
        "health": "healthy",
        "confidence": "advertised",
        "sample_count": 0,
        "evidence_sources": [
            "structured_api_metadata",
            *(["catalog_description"] if description else []),
        ],
        "source_url": f"https://openrouter.ai/{model_id}",
    }


def _catalog_fingerprint(models: list[dict]) -> str:
    encoded = json.dumps(models, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_free_cloud_catalog(
    payload: Mapping[str, object],
    *,
    fetched_at: datetime | None = None,
) -> dict:
    """Build a deterministic catalog from an OpenRouter-style models payload."""

    raw_models = payload.get("data")
    if not isinstance(raw_models, list):
        raise ValueError("Model catalog payload must contain a data list.")
    models = [
        _normalize_model(raw)
        for raw in raw_models
        if isinstance(raw, Mapping)
        and str(raw.get("id") or "").strip()
        and _is_free_text_chat_model(raw)
    ]
    models.sort(key=lambda model: model["id"])
    checked_at = fetched_at or datetime.now(timezone.utc)
    if checked_at.tzinfo is None:
        checked_at = checked_at.replace(tzinfo=timezone.utc)
    return {
        "schema_version": CATALOG_SCHEMA_VERSION,
        "provider": "openrouter",
        "source_url": OPENROUTER_MODELS_URL,
        "fetched_at": checked_at.isoformat(),
        "model_count": len(models),
        "catalog_fingerprint": _catalog_fingerprint(models),
        "models": models,
    }


def _read_catalog(path: Path) -> dict | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def load_free_cloud_catalog(root: Path | str) -> dict:
    """Load the current generated catalog, returning an empty valid snapshot."""

    path = Path(root) / ".devflow" / "model-catalog" / "current.json"
    catalog = _read_catalog(path)
    if catalog is not None:
        return catalog
    return {
        "schema_version": CATALOG_SCHEMA_VERSION,
        "provider": "openrouter",
        "source_url": OPENROUTER_MODELS_URL,
        "fetched_at": None,
        "model_count": 0,
        "catalog_fingerprint": "",
        "models": [],
    }


def _model_index(catalog: Mapping[str, object] | None) -> dict[str, dict]:
    if not catalog:
        return {}
    models = catalog.get("models")
    if not isinstance(models, list):
        return {}
    return {
        str(model["id"]): model
        for model in models
        if isinstance(model, dict) and model.get("id")
    }


def _semantic_model(model: Mapping[str, object]) -> dict:
    """Remove observation timestamps before capability-change comparison."""

    return {
        key: value
        for key, value in model.items()
        if key not in {"first_seen", "last_seen"}
    }


def _write_json_atomic(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def refresh_free_cloud_catalog(
    root: Path | str,
    *,
    fetch_catalog: Callable[[], dict] = fetch_openrouter_catalog,
    fetched_at: datetime | None = None,
) -> CatalogRefreshResult:
    """Refresh the persisted catalog and report semantic model changes."""

    root_path = Path(root)
    catalog_dir = root_path / ".devflow" / "model-catalog"
    current_path = catalog_dir / "current.json"
    previous = _read_catalog(current_path)
    current = build_free_cloud_catalog(fetch_catalog(), fetched_at=fetched_at)

    previous_models = _model_index(previous)
    current_models = _model_index(current)
    observed_at = str(current["fetched_at"])
    for model_id, model in current_models.items():
        previous_model = previous_models.get(model_id, {})
        model["first_seen"] = str(previous_model.get("first_seen") or observed_at)
        model["last_seen"] = observed_at
    previous_ids = set(previous_models)
    current_ids = set(current_models)
    added = tuple(sorted(current_ids - previous_ids))
    removed = tuple(sorted(previous_ids - current_ids))
    modified = tuple(
        sorted(
            model_id
            for model_id in previous_ids & current_ids
            if _semantic_model(previous_models[model_id]) != _semantic_model(current_models[model_id])
        )
    )
    changed = bool(added or removed or modified)

    _write_json_atomic(current_path, current)
    history_path: Path | None = None
    if changed:
        timestamp = datetime.fromisoformat(str(current["fetched_at"]))
        history_path = catalog_dir / "history" / f"{timestamp.date().isoformat()}.json"
        _write_json_atomic(history_path, current)

    return CatalogRefreshResult(
        changed=changed,
        added=added,
        removed=removed,
        modified=modified,
        current_path=current_path,
        history_path=history_path,
        model_count=int(current["model_count"]),
    )


__all__ = [
    "CATALOG_SCHEMA_VERSION",
    "OPENROUTER_MODELS_URL",
    "CatalogRefreshResult",
    "build_free_cloud_catalog",
    "fetch_openrouter_catalog",
    "load_free_cloud_catalog",
    "refresh_free_cloud_catalog",
]
