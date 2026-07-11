"""Routing layer: connects roles to models.

This is the ONLY place where a role becomes associated with a model.
The routing layer evaluates:
  1. Required capabilities (hard filter — model MUST satisfy these)
  2. Deployment profile (preferred model for this role in this environment)
  3. Role policy (preferred cost classes / transports)
  4. Availability and retirement status (hard filter)
  5. Automatic routing (cheapest eligible model as fallback)

Configuration precedence (highest to lowest):
  1. Explicit per-run override passed to resolve_role()
  2. Active deployment profile (profiles.yaml)
  3. Role policy preferred cost classes (roles.py)
  4. Automatic routing (cheapest eligible model)
  5. Safe fallback (first eligible model in registry)

The pipeline never calls routing directly in the normal flow. It calls
``resolve_role_slot`` from model_router.py, which delegates here. This
keeps the import graph clean: execution.py → model_router → routing →
registry + roles + profiles.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml

from devflow.loop.registry import (
    COST_CLASSES,
    ModelEntry,
    ModelRegistry,
    get_registry,
)
from devflow.loop.roles import RoleDefinition, get_role, known_roles


# ---------------------------------------------------------------------------
# Resolved slot (the output of routing)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ResolvedSlot:
    """The result of routing a role to a model.

    This replaces the old ``ModelSlot`` from model_router.py. Same shape,
    same fields, plus provenance about how it was resolved.
    """

    role: str
    model_name: str
    provider: str
    endpoint: str
    transport: str
    cost_class: str
    resolved_via: str  # "override" | "profile" | "policy" | "auto" | "fallback"
    model_id: str = ""  # API model ID (e.g. "tencent/hy3:free")
    fallback_model_ids: tuple[str, ...] = ()
    model_path: str = ""  # local GGUF path (for llama.cpp models)

    @property
    def model(self) -> str:
        """Alias for model_name, for backward compatibility with ModelSlot."""
        return self.model_name


# ---------------------------------------------------------------------------
# Profile loading
# ---------------------------------------------------------------------------
_DEFAULT_PROFILES_YAML = Path(__file__).parent / "profiles.yaml"

_PROFILES_PATH = Path(
    os.environ.get("DEVFLOW_PROFILES_YAML", str(_DEFAULT_PROFILES_YAML))
)

_active_profile_name: str = os.environ.get("DEVFLOW_PROFILE", "legacy-current")
_profile_cache: dict | None = None


def _load_profiles_yaml() -> dict:
    """Load and cache the profiles YAML."""
    global _profile_cache
    if _profile_cache is None:
        if not _PROFILES_PATH.exists():
            _profile_cache = {"profiles": {}}
        else:
            with open(_PROFILES_PATH, encoding="utf-8") as f:
                _profile_cache = yaml.safe_load(f) or {"profiles": {}}
    return _profile_cache  # type: ignore[return-value]


def get_active_profile_name() -> str:
    return _active_profile_name


def set_active_profile(name: str) -> None:
    """Switch the active deployment profile. Takes effect on next resolve_role call."""
    global _active_profile_name
    _active_profile_name = name


def list_profiles() -> list[str]:
    data = _load_profiles_yaml()
    return list(data.get("profiles", {}).keys())


def _get_profile_role_model(role_name: str, profile_name: str | None = None) -> Optional[str]:
    """Look up a profile's preferred model for a role. Returns model name or None."""
    data = _load_profiles_yaml()
    profiles = data.get("profiles", {})
    pname = profile_name or _active_profile_name
    profile = profiles.get(pname, {})
    role_map = profile.get("roles", {})
    return role_map.get(role_name)


# ---------------------------------------------------------------------------
# Routing logic
# ---------------------------------------------------------------------------
_COST_RANK = {cls: i for i, cls in enumerate(COST_CLASSES)}


def _rank_by_cost_class(
    models: list[ModelEntry],
    preference: tuple[str, ...],
) -> list[ModelEntry]:
    """Sort eligible models by cost-class preference (most preferred first)."""
    pref_rank = {cls: i for i, cls in enumerate(preference)}

    def sort_key(m: ModelEntry) -> tuple[int, str]:
        return (pref_rank.get(m.cost_class, len(preference)), m.name)

    return sorted(models, key=sort_key)


def _candidates_for_role(
    role: RoleDefinition,
    registry: ModelRegistry,
) -> list[ModelEntry]:
    """All eligible models that satisfy the role's required capabilities."""
    return registry.with_capabilities(role.required_capabilities)


def resolve_role(
    role_name: str,
    *,
    override_model: Optional[str] = None,
    registry: Optional[ModelRegistry] = None,
    profile_name: Optional[str] = None,
) -> ResolvedSlot:
    """Route a role to the best available model.

    This is the single entry point for role → model resolution.

    Args:
        role_name: Canonical role name (brainstorm, planner, etc.)
        override_model: Explicit model name — highest precedence.
        registry: Use a specific registry (for testing). Defaults to global.
        profile_name: Use a specific profile (for testing). Defaults to active.

    Returns:
        ResolvedSlot with provider, endpoint, and provenance.

    Raises:
        ValueError: If the role is unknown or no eligible model exists.
    """
    role = get_role(role_name)
    if role is None:
        raise ValueError(
            f"Unknown DevFlow role '{role_name}'. Known roles: {', '.join(known_roles())}"
        )

    reg = registry if registry is not None else get_registry()
    candidates = _candidates_for_role(role, reg)
    if not candidates:
        raise ValueError(
            f"No eligible model for role '{role_name}'. "
            f"Required capabilities: {', '.join(role.required_capabilities)}. "
            f"Check models.yaml for models with these capabilities."
        )

    # 1. Explicit override — highest precedence. Still must be eligible.
    if override_model:
        entry = reg.get(override_model)
        if entry and entry.is_eligible and entry.has_all_capabilities(role.required_capabilities):
            return _make_slot(role_name, entry, "override")
        # Override model doesn't satisfy requirements — fall through with a warning.
        # Don't silently substitute; let the profile/auto path find something valid.
        # (We don't raise because the operator may have set a stale override.)

    # 2. Deployment profile preference
    profile_model_name = _get_profile_role_model(role_name, profile_name)
    if profile_model_name:
        entry = reg.get(profile_model_name)
        if entry and entry.is_eligible and entry.has_all_capabilities(role.required_capabilities):
            return _make_slot(role_name, entry, "profile")
        # Profile model unavailable/retired — fall through to auto routing.

    # 3+4. Automatic routing: rank by cost-class preference
    ranked = _rank_by_cost_class(candidates, role.preferred_cost_classes)
    return _make_slot(role_name, ranked[0], "auto")


def _make_slot(role_name: str, entry: ModelEntry, resolved_via: str) -> ResolvedSlot:
    return ResolvedSlot(
        role=role_name,
        model_name=entry.name,
        provider=entry.provider,
        endpoint=entry.endpoint,
        transport=entry.transport,
        cost_class=entry.cost_class,
        resolved_via=resolved_via,
        model_id=entry.model_id,
        fallback_model_ids=entry.fallback_model_ids,
        model_path=entry.model_path,
    )


# ---------------------------------------------------------------------------
# Backward compatibility aliases
# ---------------------------------------------------------------------------
# The old model_router.py exposed these role names. Map them to canonical
# roles so existing code keeps working during the transition.
_ROLE_ALIASES: dict[str, str] = {
    "judge": "build_judge",  # old generic name retained for active judge callers
}


def _resolve_canonical_role(role_name: str) -> str:
    """Map legacy role names to canonical names."""
    return _ROLE_ALIASES.get(role_name, role_name)


def resolve_role_compatible(role_name: str, **kwargs) -> ResolvedSlot:
    """Resolve a role, accepting legacy role names.

    This is the bridge function called by model_router.py's resolve_role_slot()
    to maintain backward compatibility with existing callers.
    """
    canonical = _resolve_canonical_role(role_name)
    return resolve_role(canonical, **kwargs)


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------
def describe_routing() -> str:
    """Human-readable summary of how every role would resolve right now."""
    lines = []
    lines.append(f"Active profile: {get_active_profile_name()}")
    lines.append(f"Registry: {len(get_registry())} models")
    lines.append("")
    for role_name in known_roles():
        try:
            slot = resolve_role(role_name)
            lines.append(
                f"  {role_name:<20} → {slot.model_name:<25} "
                f"[{slot.cost_class:<22}] via {slot.resolved_via}"
            )
        except ValueError as exc:
            lines.append(f"  {role_name:<20} → UNRESOLVABLE: {exc}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Test / reload helpers
# ---------------------------------------------------------------------------
def _reload_all() -> None:
    """Force reload of registry and profiles from disk."""
    from devflow.loop.registry import _reload_registry
    global _profile_cache
    _reload_registry()
    _profile_cache = None


__all__ = [
    "ResolvedSlot",
    "resolve_role",
    "resolve_role_compatible",
    "get_active_profile_name",
    "set_active_profile",
    "list_profiles",
    "describe_routing",
    "_reload_all",
]
