from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

from devflow.control_room.agent_registry import (
    AgentDefinition,
    AgentRegistry,
    ProviderDefinition,
    ProviderRegistry,
    SAFE_AGENT_ID_PATTERN,
    is_local_openai_compatible_provider,
    is_remote_advisory_agent,
    load_agent_registry,
    load_provider_registry,
    slug_id_part,
)
from devflow.control_room.agent_runtime import agent_runtime_contract


@dataclass(frozen=True)
class HermesCatalogProfile:
    id: str
    hermes_profile: str
    label: str
    provider: str
    model: str


CANONICAL_HERMES_PROFILES: tuple[HermesCatalogProfile, ...] = (
    HermesCatalogProfile("hermes-codex-gpt55", "hermes-codex-gpt55", "Hermes Codex GPT 5.5", "openai-codex", "gpt-5.5"),
    HermesCatalogProfile("hermes-minimaxm3", "hermes-minimaxm3", "Hermes MiniMax M3", "openrouter", "minimax/minimax-m3"),
    HermesCatalogProfile("hermes-qwen37plus", "hermes-qwen37plus", "Hermes Qwen 3.7 Plus", "openrouter", "qwen/qwen3.7-plus"),
    HermesCatalogProfile("hermes-qwen37max", "hermes-qwen37max", "Hermes Qwen 3.7 Max", "openrouter", "qwen/qwen3.7-max"),
    HermesCatalogProfile("hermes-sonnet46", "hermes-sonnet46", "Hermes Sonnet 4.6", "openrouter", "anthropic/claude-sonnet-4.6"),
    HermesCatalogProfile("hermes-opus48", "hermes-opus48", "Hermes Opus 4.8", "openrouter", "anthropic/claude-opus-4.8"),
    HermesCatalogProfile("hermes-qwen32", "hermes-qwen32", "Hermes Qwen 3.2", "qwen35-mtp", "qwen35-9b-mtp"),
    HermesCatalogProfile("hermes-gemma12b", "hermes-gemma12b", "Hermes Gemma 12B", "local", "gemma4:12b-it-qat"),
    HermesCatalogProfile("hermes-qwen36-27b-mtp", "hermes-qwen36-27b-mtp", "Hermes Qwen 36B MTP", "qwen35-mtp", "qwen3.6-27b-mtp"),
    HermesCatalogProfile("hermes-qwen36-27b-mlx4bit", "hermes-qwen36-27b-mlx4bit", "Hermes Qwen 36B MLP 4bit", "local", "qwen3.6-27b-mlxf4bit"),
    HermesCatalogProfile("hermes-qwen36-27b-mlx8bit", "hermes-qwen36-27b-mlx8bit", "Hermes Qwen 36B MLP 8bit", "local", "qwen3.6-27b-mlxf8bit"),
    HermesCatalogProfile("hermes-ornith9b", "hermes-ornith9b", "Hermes Ornith 9B", "local-ornith-9b", "ornith-1.0-9b-q4"),
    HermesCatalogProfile("hermes-ornith35b", "hermes-ornith35b", "Hermes Ornith 35B", "local-ornith-35b", "ornith-1.0-35b-q4"),
)


HERMES_GLOBAL_FALLBACK_IDS: tuple[str, ...] = ("hermes-codex-gpt55", "hermes-qwen32")

CANONICAL_PROFILE_BY_ID: dict[str, HermesCatalogProfile] = {
    profile.id: profile for profile in CANONICAL_HERMES_PROFILES
}
CANONICAL_PROFILE_BY_HERMES_PROFILE: dict[str, str] = {
    profile.hermes_profile: profile.id for profile in CANONICAL_HERMES_PROFILES
}
CANONICAL_PROFILE_IDS: frozenset[str] = frozenset(CANONICAL_PROFILE_BY_ID)

HERMES_PROFILE_PICKER_IDS: dict[str, str] = {
    profile.hermes_profile: profile.id for profile in CANONICAL_HERMES_PROFILES
}
_PICKER_ID_TO_PROFILE = {picker_id: profile for profile, picker_id in HERMES_PROFILE_PICKER_IDS.items()}

HERMES_RETIRED_ALIAS_TO_CANONICAL_ID: dict[str, str] = {
    "fast_local": "hermes-qwen32",
    "long_local": "hermes-gemma12b",
    "code_local": "hermes-qwen36-27b-mtp",
    "dflocalfast": "hermes-qwen32",
    "dflocallong": "hermes-gemma12b",
    "dflocalcode": "hermes-qwen36-27b-mtp",
    "local-qwen35-mtp": "hermes-qwen32",
    "qwen-worker": "hermes-qwen32",
    "ornith9b": "hermes-ornith9b",
    "ornith35b": "hermes-ornith35b",
    "dfcodex55": "hermes-codex-gpt55",
    "dfminimaxm3": "hermes-minimaxm3",
    "dfqwen37plus": "hermes-qwen37plus",
    "dfqwen37max": "hermes-qwen37max",
    "dfsonnet46": "hermes-sonnet46",
    "dfopus48": "hermes-opus48",
}


@dataclass(frozen=True)
class HermesProfile:
    id: str
    hermes_profile: str
    label: str
    provider: str
    model: str
    base_url: str | None
    config_path: Path
    status: str
    blocked_reason: str | None
    key_env: str | None
    key_status: str
    key_source: str | None
    setup_guidance: str
    dynamic_id: bool
    parse_error: str | None = None

    @property
    def is_local(self) -> bool:
        return self.provider in {"ollama", "local"} or _is_local_http_base_url(self.base_url)

    @property
    def registry_profile_id(self) -> str | None:
        return None if self.dynamic_id else self.id

    def runtime_contract(self) -> dict[str, Any]:
        next_command = (
            "hermes chat -q <prompt>"
            if self.hermes_profile == "default"
            else f"hermes -p {self.hermes_profile} chat -q <prompt>"
        )
        return {
            "execution_surface": "hermes_profile_handoff",
            "runtime_contract": "handoff_v1",
            "task_run_allowed": False,
            "agent_run_allowed": False,
            "direct_chat_allowed": False,
            "packet_allowed": True,
            "refusal_reason": (
                "Hermes profile identities are selected here, but direct Dev-Flow chat "
                "requires an approved registry-backed advisory path or an explicit Hermes handoff."
            ),
            "next_command": next_command,
            "profile": self.hermes_profile,
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

    def to_agent_row(self, *, runtime_contract: dict[str, Any] | None = None) -> dict[str, Any]:
        availability_status = "available" if self.status == "available" else self.status
        return {
            "id": self.id,
            "label": self.label,
            "source": "hermes",
            "adapter": "hermes_profile",
            "provider": self.provider,
            "model": self.model,
            "base_url": self.base_url,
            "hermes_profile": self.hermes_profile,
            "config_path": self.config_path.as_posix(),
            "status": self.status,
            "blocked_reason": self.blocked_reason,
            "key_env": self.key_env,
            "key_status": self.key_status,
            "key_source": self.key_source,
            "setup_guidance": self.setup_guidance,
            "parse_error": self.parse_error,
            "runtime_contract": runtime_contract or self.runtime_contract(),
            "availability": {
                "status": availability_status,
                "source": "hermes_profile",
                "reason": self.blocked_reason,
            },
            "is_local": self.is_local,
            "authority": "advisory",
            "role": "frontier_planner_architect_reviewer",
            "tier": "local" if self.is_local else "frontier",
            "purpose": self.setup_guidance if self.status != "available" else "Hermes profile identity.",
        }


@dataclass(frozen=True)
class HermesFallbackResolution:
    requested_profile_id: str
    profile: HermesProfile | None
    fallback_chain: tuple[str, ...]
    failure_reasons: tuple[str, ...]

    @property
    def status(self) -> str:
        return "available" if self.profile is not None else "failed"

    def to_payload(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "requested_profile_id": self.requested_profile_id,
            "selected_profile_id": self.profile.id if self.profile else None,
            "selected_hermes_profile": self.profile.hermes_profile if self.profile else None,
            "fallback_chain": list(self.fallback_chain),
            "failure_reasons": list(self.failure_reasons),
        }


def discover_hermes_profiles() -> list[HermesProfile]:
    profiles_dir = Path.home() / ".hermes" / "profiles"
    hermes_env_keys = _hermes_env_key_names(Path.home() / ".hermes" / ".env")
    rows = [
        _profile_from_catalog_entry(
            entry,
            profiles_dir / entry.hermes_profile / "config.yaml",
            hermes_env_keys,
        )
        for entry in CANONICAL_HERMES_PROFILES
    ]
    return sorted(rows, key=lambda profile: profile.id)


_MISSING_REGISTRY = object()


def configured_hermes_agent_rows(root: Path | None = None) -> list[dict[str, Any]]:
    agent_registry: object = _MISSING_REGISTRY
    provider_registry: object = _MISSING_REGISTRY
    if root is not None:
        try:
            agent_registry = load_agent_registry(root)
            provider_registry = load_provider_registry(root)
        except Exception:
            agent_registry = None
            provider_registry = None

    rows = []
    for profile in discover_hermes_profiles():
        contract = None
        if root is not None:
            approved = approved_registry_runtime(
                root,
                profile,
                agent_registry=agent_registry,
                provider_registry=provider_registry,
            )
            if approved is not None:
                agent, _provider = approved
                contract = agent_runtime_contract(root, agent)
                contract = {**contract, "runtime_contract": "registry_backed_advisory"}
        rows.append(profile.to_agent_row(runtime_contract=contract))
    return rows


def resolve_hermes_profile(profile_id: str) -> HermesProfile | None:
    wanted = str(profile_id or "").strip()
    if not wanted:
        return None
    entry = CANONICAL_PROFILE_BY_ID.get(wanted)
    if entry is None:
        return None
    config_path = Path.home() / ".hermes" / "profiles" / entry.hermes_profile / "config.yaml"
    return _profile_from_catalog_entry(
        entry,
        config_path,
        _hermes_env_key_names(Path.home() / ".hermes" / ".env"),
    )


def resolve_hermes_profile_for_historical_cleanup(profile_id: str) -> HermesProfile | None:
    wanted = str(profile_id or "").strip()
    if not wanted:
        return None
    canonical_id = HERMES_RETIRED_ALIAS_TO_CANONICAL_ID.get(wanted)
    if canonical_id is None and wanted.startswith("hermes-profile-"):
        canonical_id = HERMES_RETIRED_ALIAS_TO_CANONICAL_ID.get(wanted.removeprefix("hermes-profile-").strip())
        if canonical_id is None:
            canonical_candidate = wanted.removeprefix("hermes-profile-").strip()
            canonical_id = CANONICAL_PROFILE_BY_HERMES_PROFILE.get(canonical_candidate)
            if canonical_id is None and canonical_candidate in CANONICAL_PROFILE_BY_ID:
                canonical_id = canonical_candidate
    if canonical_id is None:
        canonical_id = CANONICAL_PROFILE_BY_HERMES_PROFILE.get(wanted) or (
            wanted if wanted in CANONICAL_PROFILE_BY_ID else None
        )
    if canonical_id is None:
        return None
    return resolve_hermes_profile(canonical_id)


def resolve_hermes_profile_with_global_fallback(profile_id: str) -> HermesFallbackResolution:
    requested = str(profile_id or "").strip()
    reasons: list[str] = []
    resolved = resolve_hermes_profile(requested) if requested else None
    if resolved is not None and resolved.status == "available":
        return HermesFallbackResolution(requested, resolved, HERMES_GLOBAL_FALLBACK_IDS, ())
    if resolved is not None:
        reasons.append(f"{resolved.id}: {resolved.blocked_reason or resolved.status}")
    elif requested:
        reasons.append(f"{requested}: not a canonical Hermes profile id")
    for fallback_id in HERMES_GLOBAL_FALLBACK_IDS:
        profile = resolve_hermes_profile(fallback_id)
        if profile is not None and profile.status == "available":
            return HermesFallbackResolution(requested, profile, HERMES_GLOBAL_FALLBACK_IDS, tuple(reasons))
        if profile is None:
            reasons.append(f"{fallback_id}: not found")
        else:
            reasons.append(f"{fallback_id}: {profile.blocked_reason or profile.status}")
    return HermesFallbackResolution(requested, None, HERMES_GLOBAL_FALLBACK_IDS, tuple(reasons))


def load_hermes_picker_runtime(
    root: Path,
    profile_id: str,
) -> tuple[AgentDefinition, ProviderDefinition] | None:
    resolved = resolve_hermes_profile(profile_id)
    if resolved is None:
        if profile_id.startswith("hermes-profile-"):
            profile_name = profile_id.removeprefix("hermes-profile-").strip()
            if profile_name:
                resolved = _profile_from_catalog_entry(
                    HermesCatalogProfile(profile_id, profile_name, profile_name, "hermes-profile", "unconfigured"),
                    Path.home() / ".hermes" / "profiles" / profile_name / "config.yaml",
                    _hermes_env_key_names(Path.home() / ".hermes" / ".env"),
                    profile_id=profile_id,
                    dynamic_id=True,
                )
                return synthetic_handoff_runtime(resolved)
        return None
    approved = approved_registry_runtime(root, resolved)
    if approved is not None:
        return approved
    return synthetic_handoff_runtime(resolved)


def approved_registry_runtime(
    root: Path,
    profile: HermesProfile,
    *,
    agent_registry: AgentRegistry | object = _MISSING_REGISTRY,
    provider_registry: ProviderRegistry | object = _MISSING_REGISTRY,
) -> tuple[AgentDefinition, ProviderDefinition] | None:
    registry_id = profile.registry_profile_id
    if not registry_id:
        return None
    try:
        if agent_registry is _MISSING_REGISTRY:
            agent = load_agent_registry(root).require_agent(registry_id)
        else:
            agent = agent_registry.require_agent(registry_id)
        if provider_registry is _MISSING_REGISTRY:
            provider = load_provider_registry(root).require_provider(agent.provider)
        else:
            provider = provider_registry.require_provider(agent.provider)
    except Exception:
        return None
    if profile.provider and agent.provider != profile.provider:
        return None
    if profile.model and agent.model != profile.model:
        return None
    if is_remote_advisory_agent(agent, provider=provider):
        return agent, provider
    if _is_ollama_provider(agent, provider) or is_local_openai_compatible_provider(provider):
        return agent, provider
    return None


def synthetic_handoff_runtime(profile: HermesProfile) -> tuple[AgentDefinition, ProviderDefinition]:
    provider_id = profile.provider or "hermes-profile"
    model = profile.model or "unconfigured"
    tier = "local" if profile.is_local else "frontier"
    agent = AgentDefinition(
        id=profile.id,
        provider=provider_id,
        model=model,
        adapter="hermes_profile",
        role="frontier_planner_architect_reviewer",
        tier=tier,
        default_mode="frontier_read_only",
        execution_mode="manual_handoff",
        purpose=profile.setup_guidance,
        model_role_name=profile.label,
        secondary_roles=["brainstorm", "builder", "judge", "hermes-handoff"],
        use_caution=[
            "Direct Dev-Flow provider execution is disabled for this Hermes profile identity.",
            "Use serial-packet evidence or launch the Hermes profile explicitly outside the browser.",
        ],
        workspace="isolated_task_workspace",
        can_see=["status_projection", "task_packet", "verification_ledger_summary"],
        can_touch=[],
        cannot_touch=["<main_checkout>/**", ".git/**"],
        allowed_reads=[],
        allowed_writes=[],
        forbidden_writes=["<main_checkout>/**", ".git/**"],
        required_outputs=["Return Hermes handoff/setup state; do not call raw provider APIs."],
        completion_rules=["Do not execute direct chat through raw provider APIs for this Hermes profile."],
        can_run_shell=False,
        can_use_network=False,
        can_promote=False,
        hermes_delegable=False,
        enabled=True,
    )
    provider = ProviderDefinition(
        id=provider_id,
        provider=provider_id,
        adapter="hermes_profile",
        base_url=profile.base_url,
        api_key_env=profile.key_env,
        enabled=True,
    )
    return agent, provider


def hermes_direct_handoff_state(
    agent: AgentDefinition,
    provider: ProviderDefinition,
) -> dict[str, Any] | None:
    if agent.adapter != "hermes_profile":
        return None
    profile = resolve_hermes_profile(agent.id)
    if profile is None:
        profile = _profile_from_agent(agent, provider)
    contract = profile.runtime_contract()
    error = _handoff_error(profile, contract)
    return {
        "runtime_contract": contract,
        "next_command": contract["next_command"],
        "profile": {
            "id": profile.id,
            "hermes_profile": profile.hermes_profile,
            "label": profile.label,
            "provider": profile.provider,
            "model": profile.model,
            "base_url": profile.base_url,
            "config_path": profile.config_path.as_posix(),
        },
        "key_status": profile.key_status,
        "key_env": profile.key_env,
        "endpoint_status": "not_checked" if profile.base_url else "not_configured",
        "setup_guidance": profile.setup_guidance,
        "error": error,
    }


def _profile_from_catalog_entry(
    catalog_profile: HermesCatalogProfile,
    config_path: Path,
    hermes_env_keys: set[str],
    *,
    profile_id: str | None = None,
    dynamic_id: bool = False,
) -> HermesProfile:
    safe_profile_name = _profile_slug(catalog_profile.hermes_profile)
    provider = catalog_profile.provider
    model = catalog_profile.model
    base_url: str | None = _default_hermes_base_url(provider)
    parse_error: str | None = None
    blocked_reason: str | None = None

    if not config_path.exists():
        blocked_reason = f"Missing Hermes profile config: {config_path.as_posix()}"
    else:
        try:
            payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
            if not isinstance(payload, dict):
                raise ValueError("config root must be a map")
            active = payload.get("model") if isinstance(payload.get("model"), dict) else {}
            if isinstance(active, dict):
                provider = _normalize_hermes_provider_id(active.get("provider")) or provider
                model = _optional_str(active.get("default") or active.get("model") or active.get("id")) or model
                base_url = _optional_str(active.get("base_url")) or _default_hermes_base_url(provider) or base_url
                if provider == "openai-codex" and not model:
                    model = _optional_str(os.environ.get("DEVFLOW_DF_CODEX_MODEL")) or "gpt-5.5"
            if not provider or not model:
                first_row = next(iter(_configured_hermes_model_rows(payload)), None)
                if first_row:
                    provider = _normalize_hermes_provider_id(first_row.get("provider")) or provider
                    model = _optional_str(first_row.get("model")) or model
                    base_url = _optional_str(first_row.get("base_url")) or base_url
        except Exception as exc:
            parse_error = str(exc)
            blocked_reason = f"Unreadable Hermes profile config: {config_path.as_posix()} ({exc})"

    if not provider or not model:
        blocked_reason = blocked_reason or f"Hermes profile '{safe_profile_name}' does not declare a provider and model."

    key_env = _hermes_provider_key_env(provider)
    key_status, key_source = _hermes_key_status(
        key_env=key_env,
        hermes_env_keys=hermes_env_keys,
        inline_key_present=False,
        base_url=base_url,
        provider=provider,
    )
    if blocked_reason is None and key_status == "missing" and key_env:
        blocked_reason = f"Needs key: {key_env} for Hermes profile {safe_profile_name}."

    status = "available" if blocked_reason is None else "setup_required" if parse_error or "Missing Hermes profile config" in blocked_reason or not provider or not model else "blocked"
    return HermesProfile(
        id=profile_id or _picker_id(safe_profile_name),
        hermes_profile=safe_profile_name,
        label=catalog_profile.label,
        provider=provider,
        model=model,
        base_url=base_url,
        config_path=config_path,
        status=status,
        blocked_reason=blocked_reason,
        key_env=key_env,
        key_status=key_status,
        key_source=key_source,
        setup_guidance=_setup_guidance(safe_profile_name, provider, model, base_url, blocked_reason),
        dynamic_id=dynamic_id,
        parse_error=parse_error,
    )


def _profile_from_agent(agent: AgentDefinition, provider: ProviderDefinition) -> HermesProfile:
    profile_name = _PICKER_ID_TO_PROFILE.get(agent.id) or agent.id.replace("hermes-profile-", "", 1)
    return HermesProfile(
        id=agent.id,
        hermes_profile=profile_name,
        label=agent.model_role_name or agent.id,
        provider=agent.provider,
        model=agent.model,
        base_url=provider.base_url,
        config_path=Path.home() / ".hermes" / "profiles" / profile_name / "config.yaml",
        status="blocked",
        blocked_reason="Direct Dev-Flow chat is not available for this Hermes profile.",
        key_env=provider.api_key_env,
        key_status="not_checked",
        key_source=None,
        setup_guidance=f"Use Hermes profile {profile_name} through handoff or serial-packet evidence.",
        dynamic_id=agent.id not in CANONICAL_PROFILE_IDS,
    )


def _picker_id(profile_name: str) -> str:
    stable = HERMES_PROFILE_PICKER_IDS.get(profile_name)
    if stable:
        return stable
    slug = slug_id_part(profile_name)
    candidate = f"hermes-profile-{slug}"
    if len(candidate) <= 80 and SAFE_AGENT_ID_PATTERN.match(candidate):
        return candidate
    digest = hashlib.sha1(profile_name.encode("utf-8")).hexdigest()[:10]
    prefix = candidate[:68].rstrip("-_") or "hermes-profile"
    return f"{prefix}-{digest}"


def _profile_slug(value: str) -> str:
    return slug_id_part(value)


def _setup_guidance(
    profile: str,
    provider: str,
    model: str,
    base_url: str | None,
    blocked_reason: str | None,
) -> str:
    if blocked_reason:
        return f"{blocked_reason} Next: configure ~/.hermes/profiles/{profile}/config.yaml, then refresh model setup."
    if _is_local_http_base_url(base_url):
        return f"Hermes profile {profile} targets {model} at {base_url}. If it is offline, start that endpoint before use."
    return f"Hermes profile {profile} targets {model} via {provider}. Use Hermes handoff or an approved registry-backed advisory path."


def _handoff_error(profile: HermesProfile, contract: dict[str, Any]) -> str:
    if profile.status != "available":
        return f"Hermes profile setup required for {profile.hermes_profile}: {profile.setup_guidance}"
    return (
        f"Hermes profile {profile.hermes_profile} is selected, but this direct Dev-Flow path "
        f"requires handoff. Next command: {contract['next_command']}"
    )


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
            for model in _hermes_provider_models(raw_provider):
                rows.append({"provider": provider, "model": model, "base_url": base_url})
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


def _is_ollama_provider(agent: AgentDefinition, provider: ProviderDefinition) -> bool:
    return provider.provider == "ollama" or agent.adapter == "ollama_chat"


def _is_local_http_base_url(base_url: str | None) -> bool:
    if base_url is None or not base_url.strip():
        return False
    parsed = urlparse(base_url)
    return parsed.scheme in {"http", "https"} and parsed.hostname in {"127.0.0.1", "localhost", "::1"}


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


__all__ = [
    "HermesProfile",
    "approved_registry_runtime",
    "configured_hermes_agent_rows",
    "discover_hermes_profiles",
    "hermes_direct_handoff_state",
    "load_hermes_picker_runtime",
    "resolve_hermes_profile",
    "resolve_hermes_profile_for_historical_cleanup",
    "resolve_hermes_profile_with_global_fallback",
    "synthetic_handoff_runtime",
]
