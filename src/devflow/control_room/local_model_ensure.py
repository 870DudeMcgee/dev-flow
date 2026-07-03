from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from devflow.control_room.agent_registry import (
    is_local_openai_compatible_provider,
    load_agent_registry,
    load_provider_registry,
)
from devflow.control_room.hermes_profile_resolver import (
    HERMES_RETIRED_ALIAS_TO_CANONICAL_ID,
    resolve_hermes_profile,
)
from devflow.control_room.local_model_readiness import load_expected_local_model_manifest
from devflow.control_room.local_model_server import ensure_local_model_server_for_profile


EnsureServer = Callable[..., dict[str, Any]]


@dataclass(frozen=True)
class LocalModelEnsureProfile:
    profile_id: str
    requested_profile_id: str
    provider: str
    model: str
    adapter: str
    base_url: str | None
    source: str
    label: str | None = None
    hermes_profile: str | None = None
    local_server_backed: bool = False

    @property
    def is_ollama(self) -> bool:
        return self.provider == "ollama" or self.adapter == "ollama_chat"

    @property
    def is_local(self) -> bool:
        if self.is_ollama or self.local_server_backed:
            return True
        return _is_local_http_base_url(self.base_url)

    def evidence(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "requested_profile_id": self.requested_profile_id,
            "label": self.label,
            "provider": self.provider,
            "model": self.model,
            "adapter": self.adapter,
            "base_url": self.base_url,
            "source": self.source,
            "hermes_profile": self.hermes_profile,
            "is_local": self.is_local,
            "is_ollama": self.is_ollama,
            "local_server_backed": self.local_server_backed,
        }


def _resolve_local_model_ensure_profile(root: Path, profile_id: str) -> LocalModelEnsureProfile:
    if profile_id in HERMES_RETIRED_ALIAS_TO_CANONICAL_ID or profile_id.startswith("hermes-profile-"):
        raise KeyError(f"Unknown profile_id '{profile_id}'")
    registry_profile = _registry_ensure_profile(root, profile_id)
    if registry_profile is not None:
        return registry_profile

    hermes_profile = _hermes_ensure_profile(profile_id)
    if hermes_profile is not None:
        return hermes_profile

    manifest_profile = _manifest_ensure_profile(profile_id)
    if manifest_profile is not None:
        return manifest_profile

    raise KeyError(f"Unknown profile_id '{profile_id}'")


def ensure_local_model_profile(
    root: Path,
    profile_id: str,
    *,
    ensure_server: EnsureServer = ensure_local_model_server_for_profile,
) -> dict[str, Any]:
    resolved = _resolve_local_model_ensure_profile(root, profile_id)
    if resolved.is_ollama:
        return _local_model_ensure_skipped_payload(
            resolved,
            status="unmanaged",
            management="managed_by_ollama",
            reason="Ollama profiles are managed by Ollama; Dev-Flow does not stop or start Ollama.",
        )

    if not resolved.is_local:
        return _local_model_ensure_skipped_payload(
            resolved,
            status="skipped",
            management="provider_managed_remote",
            reason="Remote/frontier profiles are provider-managed; no local model server boot is needed.",
        )

    lifecycle = ensure_server(
        root,
        provider=resolved.provider,
        model=resolved.model,
        base_url=resolved.base_url,
    )
    return _local_model_ensure_payload(resolved, lifecycle)


def _registry_ensure_profile(root: Path, profile_id: str) -> LocalModelEnsureProfile | None:
    try:
        agent = load_agent_registry(root).require_agent(profile_id)
    except KeyError:
        return None
    providers = load_provider_registry(root)
    provider = providers.providers.get(agent.provider)
    if provider is not None:
        return LocalModelEnsureProfile(
            profile_id=agent.id,
            requested_profile_id=profile_id,
            provider=provider.provider,
            model=agent.model,
            adapter=agent.adapter,
            base_url=provider.base_url,
            source="agent_registry",
            label=agent.model_role_name or agent.id,
            hermes_profile=agent.id if agent.id.startswith("hermes-") else None,
            local_server_backed=is_local_openai_compatible_provider(provider),
        )

    manifest_profile = _manifest_ensure_profile(profile_id)
    if manifest_profile is not None:
        return manifest_profile
    return None


def _hermes_ensure_profile(profile_id: str) -> LocalModelEnsureProfile | None:
    profile = resolve_hermes_profile(profile_id)
    if profile is None:
        return None
    manifest_profile = _manifest_ensure_profile(profile.id) or _manifest_ensure_profile(profile.hermes_profile)
    return LocalModelEnsureProfile(
        profile_id=profile.id,
        requested_profile_id=profile_id,
        provider=manifest_profile.provider if manifest_profile else profile.provider,
        model=manifest_profile.model if manifest_profile else profile.model,
        adapter=manifest_profile.adapter if manifest_profile else "hermes_profile",
        base_url=manifest_profile.base_url if manifest_profile else profile.base_url,
        source="hermes_profile",
        label=profile.label,
        hermes_profile=profile.hermes_profile,
        local_server_backed=bool(manifest_profile and manifest_profile.local_server_backed),
    )


def _manifest_ensure_profile(profile_id: str) -> LocalModelEnsureProfile | None:
    try:
        manifest = load_expected_local_model_manifest()
    except Exception:
        return None
    for lane in manifest.lanes.values():
        aliases = {
            lane.profile_id,
            lane.lane_id,
            lane.provider_id,
            lane.model_id,
        }
        if profile_id not in aliases:
            continue
        return LocalModelEnsureProfile(
            profile_id=lane.profile_id,
            requested_profile_id=profile_id,
            provider=lane.provider_id,
            model=lane.model_id,
            adapter=lane.adapter,
            base_url=lane.base_url,
            source="local_model_manifest",
            label=lane.profile_id,
            hermes_profile=lane.profile_id if lane.profile_id.startswith("hermes-") else None,
            local_server_backed=lane.local_server_backed,
        )
    return None


def _local_model_ensure_payload(
    resolved: LocalModelEnsureProfile,
    lifecycle: dict[str, Any],
) -> dict[str, Any]:
    status = str(lifecycle.get("status") or "unknown")
    payload: dict[str, Any] = {
        "action": "ensure_local_model_server",
        "status": status,
        "will_manage_local_server": bool(lifecycle.get("will_manage_local_server")),
        "management": "devflow_managed_local_server" if lifecycle.get("will_manage_local_server") else "unmanaged_local_endpoint",
        "reason": lifecycle.get("reason") or "local model server lifecycle completed",
        "profile": resolved.evidence(),
        "lifecycle": lifecycle,
    }
    payload.update(resolved.evidence())
    return payload


def _local_model_ensure_skipped_payload(
    resolved: LocalModelEnsureProfile,
    *,
    status: str,
    management: str,
    reason: str,
) -> dict[str, Any]:
    lifecycle = {
        "action": "ensure",
        "status": status,
        "will_manage_local_server": False,
        "provider": resolved.provider,
        "model": resolved.model,
        "base_url": resolved.base_url,
        "management": management,
        "reason": reason,
    }
    payload: dict[str, Any] = {
        "action": "ensure_local_model_server",
        "status": status,
        "will_manage_local_server": False,
        "management": management,
        "reason": reason,
        "profile": resolved.evidence(),
        "lifecycle": lifecycle,
    }
    payload.update(resolved.evidence())
    return payload


def _is_local_http_base_url(base_url: str | None) -> bool:
    if not base_url:
        return False
    try:
        parsed = urlparse(base_url)
    except ValueError:
        return False
    return parsed.scheme in {"http", "https"} and parsed.hostname in {"127.0.0.1", "localhost", "::1"}
