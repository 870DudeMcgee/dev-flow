"""Model registry: describes what execution targets exist.

The registry NEVER assigns models to roles. It only describes models.
Role assignment is the job of the routing layer (routing.py), guided by
role policies (roles.py) and deployment profiles (profiles.yaml).

Registry entries are loaded from YAML config so models can be added,
removed, or modified without touching pipeline code.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml


# ---------------------------------------------------------------------------
# Cost classes (routing hints, not billing calculations)
# ---------------------------------------------------------------------------
COST_CLASSES = (
    "local",               # runs on local hardware, no per-token cost
    "free_cloud",          # free-tier cloud endpoint (e.g. OpenRouter :free)
    "included_subscription",  # covered by an active subscription (e.g. Hermes OAuth)
    "metered_low",         # low per-token cost
    "metered_high",        # expensive per-token cost (frontier)
)


# ---------------------------------------------------------------------------
# Transports (how the pipeline reaches the model)
# ---------------------------------------------------------------------------
KNOWN_TRANSPORTS = (
    "openai-http",         # OpenAI-compatible HTTP endpoint (llama-server, MLX, Ollama, etc.)
    "hermes-chat",         # shell out to `hermes chat` (subscription routing)
)


# ---------------------------------------------------------------------------
# Model entry
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ModelEntry:
    """A single model in the registry."""

    name: str                          # canonical key (e.g. "ornith-35b")
    display_name: str                  # human-readable label
    provider: str                      # provider key (e.g. "local", "zai", "openai-codex")
    transport: str                     # how to reach it (e.g. "openai-http", "hermes-chat")
    endpoint: str                      # URL or routing key
    capabilities: tuple[str, ...]      # what it can do
    cost_class: str                    # one of COST_CLASSES
    context_window: int = 32768        # max context in tokens
    structured_output: bool = False    # can produce reliable JSON?
    tool_support: bool = False         # function calling?
    available: bool = True             # currently usable on this machine?
    retired: bool = False              # superseded / withdrawn?
    auth_method: str = ""              # how it authenticates (informational)
    notes: str = ""                    # operator notes
    model_id: str = ""                 # API model ID (e.g. "tencent/hy3:free" for OpenRouter)
    fallback_model_ids: tuple[str, ...] = ()  # ordered remote model fallbacks
    model_path: str = ""               # local GGUF path (for llama.cpp models)

    def __post_init__(self):
        if self.cost_class not in COST_CLASSES:
            raise ValueError(
                f"Model '{self.name}' has invalid cost_class '{self.cost_class}'. "
                f"Must be one of: {', '.join(COST_CLASSES)}"
            )

    @property
    def is_eligible(self) -> bool:
        """True when this model can be considered for routing."""
        return self.available and not self.retired

    def has_capability(self, cap: str) -> bool:
        return cap in self.capabilities

    def has_all_capabilities(self, caps: tuple[str, ...]) -> bool:
        return all(c in self.capabilities for c in caps)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
class ModelRegistry:
    """In-memory index of ModelEntry objects loaded from YAML."""

    def __init__(self, entries: dict[str, ModelEntry] | None = None):
        self._entries: dict[str, ModelEntry] = dict(entries) if entries else {}

    # -- CRUD-style access --------------------------------------------------
    def add(self, entry: ModelEntry) -> None:
        self._entries[entry.name] = entry

    def get(self, name: str) -> Optional[ModelEntry]:
        return self._entries.get(name)

    def all(self) -> list[ModelEntry]:
        return list(self._entries.values())

    def names(self) -> list[str]:
        return list(self._entries.keys())

    # -- Query helpers ------------------------------------------------------
    def eligible(self) -> list[ModelEntry]:
        """All non-retired, available models."""
        return [e for e in self._entries.values() if e.is_eligible]

    def with_capability(self, cap: str) -> list[ModelEntry]:
        return [e for e in self.eligible() if e.has_capability(cap)]

    def with_capabilities(self, caps: tuple[str, ...]) -> list[ModelEntry]:
        return [e for e in self.eligible() if e.has_all_capabilities(caps)]

    def by_cost_class(self, cost_class: str) -> list[ModelEntry]:
        return [e for e in self.eligible() if e.cost_class == cost_class]

    def by_transport(self, transport: str) -> list[ModelEntry]:
        return [e for e in self.eligible() if e.transport == transport]

    def __len__(self) -> int:
        return len(self._entries)

    def __contains__(self, name: str) -> bool:
        return name in self._entries

    def describe(self) -> str:
        """Compact human-readable summary."""
        lines = []
        for e in self._entries.values():
            status = "retired" if e.retired else ("available" if e.available else "unavailable")
            lines.append(
                f"  {e.name:<25} [{status:<11}] "
                f"{e.cost_class:<22} {e.transport:<14} "
                f"caps: {', '.join(e.capabilities)}"
            )
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# YAML loader
# ---------------------------------------------------------------------------
def _entry_from_dict(name: str, raw: dict) -> ModelEntry:
    """Construct a ModelEntry from a YAML dict, with validation."""
    caps = raw.get("capabilities", [])
    if isinstance(caps, str):
        caps = [c.strip() for c in caps.split(",")]
    return ModelEntry(
        name=name,
        display_name=raw.get("display_name", name),
        provider=str(raw.get("provider", "")),
        transport=str(raw.get("transport", "openai-http")),
        endpoint=str(raw.get("endpoint", "")),
        capabilities=tuple(caps),
        cost_class=str(raw.get("cost_class", "local")),
        context_window=int(raw.get("context_window", 32768)),
        structured_output=bool(raw.get("structured_output", False)),
        tool_support=bool(raw.get("tool_support", False)),
        available=bool(raw.get("available", True)),
        retired=bool(raw.get("retired", False)),
        auth_method=str(raw.get("auth_method", "")),
        notes=str(raw.get("notes", "")),
        model_id=str(raw.get("model_id", "")),
        fallback_model_ids=tuple(str(value) for value in raw.get("fallback_model_ids", [])),
        model_path=str(raw.get("model_path", "")),
    )


def load_registry_from_yaml(path: Path | str) -> ModelRegistry:
    """Load a ModelRegistry from a YAML file.

    Expected structure:
        models:
          ornith-35b:
            display_name: "Ornith 35B MoE"
            provider: local
            transport: openai-http
            endpoint: "http://localhost:8084"
            cost_class: local
            capabilities:
              - code_generation
              - structured_output
              - edit_planning
              - repository_awareness
            ...
    """
    path = Path(path)
    if not path.exists():
        return ModelRegistry()
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    models = data.get("models", {})
    entries: dict[str, ModelEntry] = {}
    for name, raw in models.items():
        if not isinstance(raw, dict):
            continue
        try:
            entries[name] = _entry_from_dict(name, raw)
        except (ValueError, TypeError, KeyError) as exc:
            raise ValueError(f"Invalid model entry '{name}' in {path}: {exc}") from exc
    return ModelRegistry(entries)


# ---------------------------------------------------------------------------
# Default registry path resolution
# ---------------------------------------------------------------------------
_DEFAULT_YAML = Path(__file__).parent / "models.yaml"

# Allow env override for the registry location (useful for profiles / testing).
_REGISTRY_PATH = Path(
    os.environ.get("DEVFLOW_MODELS_YAML", str(_DEFAULT_YAML))
)

# Lazily-loaded singleton; reset by calling _reload_registry() in tests.
_registry_cache: ModelRegistry | None = None


def get_registry() -> ModelRegistry:
    """Return the cached registry, loading from YAML on first call."""
    global _registry_cache
    if _registry_cache is None:
        _registry_cache = load_registry_from_yaml(_REGISTRY_PATH)
    return _registry_cache


def _reload_registry() -> ModelRegistry:
    """Force a reload from disk. Used by tests and profile switches."""
    global _registry_cache
    _registry_cache = load_registry_from_yaml(_REGISTRY_PATH)
    return _registry_cache


__all__ = [
    "COST_CLASSES",
    "KNOWN_TRANSPORTS",
    "ModelEntry",
    "ModelRegistry",
    "load_registry_from_yaml",
    "get_registry",
    "_reload_registry",
]
