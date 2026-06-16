from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

import yaml

from devflow.control_room.agent_registry import (
    AgentDefinition,
    AgentRegistryError,
    ProviderDefinition,
    adapter_maturity,
    is_local_ollama_base_url,
    load_agent_registry,
    load_provider_registry,
    load_role_registry,
)
from devflow.control_room.agent_runtime import agent_runtime_contract, resolve_agent_runtime_definition, runtime_contract_payload
from devflow.control_room.local_agent_discovery import (
    classify_local_model,
    discover_local_ollama_models,
    parse_ollama_show,
)
from devflow.control_room.persistence import atomic_write_text


Authority = Literal["read-only", "advisory", "patch-proposer", "disabled"]

REMOTE_MODEL_ADAPTERS = {"openai_compatible", "openai_chat", "anthropic_messages", "gemini"}
PROVIDER_ADAPTERS = {"ollama_chat", *REMOTE_MODEL_ADAPTERS}
SAFE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{1,79}$")


class AgentOnboardingError(ValueError):
    pass


@dataclass(frozen=True)
class ProviderUpsert:
    status: str
    provider: ProviderDefinition
    path: Path
    dry_run: bool

    def to_payload(self, root: Path) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "status": self.status,
            "dry_run": self.dry_run,
            "will_write": not self.dry_run and self.status == "created",
            "provider": self.provider.model_dump(mode="json"),
            "path": _relative(root, self.path),
        }


@dataclass(frozen=True)
class ModelUpsert:
    status: str
    profile_id: str
    agent: AgentDefinition
    path: Path
    dry_run: bool

    def to_payload(self, root: Path) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "status": self.status,
            "dry_run": self.dry_run,
            "will_write": not self.dry_run and self.status == "created",
            "profile_id": self.profile_id,
            "path": _relative(root, self.path),
            "agent": _agent_yaml_payload(self.agent),
            "runtime_contract": runtime_contract_payload(resolve_agent_runtime_definition(self.agent, _provider_for(root, self.agent))),
        }


def derive_profile_id(provider_id: str, model_id: str, authority: str, role: str) -> str:
    authority = normalize_authority(authority)
    raw = "-".join(
        part
        for part in (
            _slug(provider_id),
            _slug(model_id),
            _slug(authority),
            _slug(role),
        )
        if part
    )
    if len(raw) <= 80 and SAFE_ID_PATTERN.match(raw):
        return raw
    digest = hashlib.sha1(f"{provider_id}|{model_id}|{authority}|{role}".encode("utf-8")).hexdigest()[:10]
    prefix = raw[: 69].rstrip("-_") or "agent"
    candidate = f"{prefix}-{digest}"
    if not SAFE_ID_PATTERN.match(candidate):
        candidate = f"agent-{digest}"
    return candidate


def normalize_authority(authority: str) -> Authority:
    normalized = authority.strip().lower().replace("_", "-")
    if normalized not in {"read-only", "advisory", "patch-proposer", "disabled"}:
        raise AgentOnboardingError(
            "Unsupported authority "
            f"'{authority}'. Allowed: read-only, advisory, patch-proposer, disabled."
        )
    return normalized  # type: ignore[return-value]


def add_provider(
    root: Path,
    provider_id: str,
    *,
    adapter: str,
    base_url: str,
    api_key_env: str | None = None,
    timeout_seconds: int | None = None,
    dry_run: bool = False,
) -> ProviderUpsert:
    root = root.resolve()
    provider_id = _validate_safe_id(provider_id, label="provider id")
    _validate_provider_adapter(adapter)
    _validate_base_url(base_url)
    if api_key_env is not None:
        _validate_api_key_env(api_key_env)
    if timeout_seconds is not None and timeout_seconds < 1:
        raise AgentOnboardingError("timeout_seconds must be a positive integer.")

    provider = ProviderDefinition(
        id=provider_id,
        provider=provider_id,
        adapter=adapter,
        base_url=base_url,
        api_key_env=api_key_env,
        default_timeout_seconds=timeout_seconds,
        enabled=True,
    )
    path = root / ".devflow" / "providers" / f"{provider_id}.yaml"
    payload = _provider_yaml_payload(provider)
    status = "created"
    if path.exists():
        existing = _read_yaml_mapping(path)
        if _normalize_provider_payload(existing, provider_id) != _normalize_provider_payload(payload, provider_id):
            raise AgentOnboardingError(f"Provider '{provider_id}' already exists with different settings.")
        status = "unchanged"
    elif not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(path, _dump_yaml(payload))

    return ProviderUpsert(status=status, provider=provider, path=path, dry_run=dry_run)


def add_model(
    root: Path,
    *,
    provider_id: str,
    model_id: str,
    authority: str,
    role: str,
    profile_id: str | None = None,
    dry_run: bool = False,
) -> ModelUpsert:
    root = root.resolve()
    authority = normalize_authority(authority)
    provider = _require_provider(root, provider_id)
    _validate_role(root, role)
    _validate_provider_authority(provider, authority)
    if profile_id is None:
        profile_id = derive_profile_id(provider_id, model_id, authority, role)
    else:
        profile_id = _validate_safe_id(profile_id, label="profile id")

    agent = render_agent_definition(
        profile_id=profile_id,
        provider=provider,
        model_id=model_id,
        authority=authority,
        role=role,
        root=root,
    )
    path = root / ".devflow" / "agents" / "registry.yaml"
    payload = _read_registry_payload(path)
    agents = payload.setdefault("agents", {})
    if not isinstance(agents, dict):
        raise AgentOnboardingError(".devflow/agents/registry.yaml agents must be a map.")

    generated_payload = _agent_yaml_payload(agent)
    registry = load_agent_registry(root)
    status = "created"
    existing = agents.get(profile_id)
    if existing is not None:
        if not isinstance(existing, dict):
            raise AgentOnboardingError(f"Profile '{profile_id}' already exists but is not a map.")
        if _canonical_agent_payload(existing) != _canonical_agent_payload(generated_payload):
            raise AgentOnboardingError(f"Profile '{profile_id}' already exists with different settings.")
        status = "unchanged"
    elif profile_id in registry.agents:
        existing_payload = _agent_yaml_payload(registry.require_agent(profile_id))
        if _canonical_agent_payload(existing_payload) != _canonical_agent_payload(generated_payload):
            raise AgentOnboardingError(f"Profile '{profile_id}' already exists with different settings.")
        status = "unchanged"
    else:
        duplicate = _duplicate_profile_for(registry, generated_payload, profile_id)
        if duplicate is not None:
            raise AgentOnboardingError(
                f"Model '{model_id}' is already registered for provider '{provider_id}' "
                f"and role '{role}' as profile '{duplicate}'."
            )
        if not dry_run:
            agents[profile_id] = generated_payload
            path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_text(path, _dump_yaml(payload))
            try:
                load_agent_registry(root).require_agent(profile_id)
            except (AgentRegistryError, KeyError) as exc:
                raise AgentOnboardingError(f"Written registry failed validation: {exc}") from exc

    return ModelUpsert(status=status, profile_id=profile_id, agent=agent, path=path, dry_run=dry_run)


def render_agent_definition(
    *,
    profile_id: str,
    provider: ProviderDefinition,
    model_id: str,
    authority: Authority,
    role: str,
    root: Path,
) -> AgentDefinition:
    is_ollama = _is_ollama_provider(provider)
    manifest_notes: list[str] = []
    machine_class = None
    weight_class = None
    tier = "local" if is_ollama else "frontier"
    if is_ollama:
        enrichment = _ollama_enrichment(model_id)
        manifest_notes = enrichment["manifest_notes"]
        weight_class = enrichment["weight_class"]
        machine_class = enrichment["machine_class"]
        tier = enrichment["tier"]

    if authority == "disabled":
        base_authority: Authority = "read-only" if is_ollama else "advisory"
        agent = render_agent_definition(
            profile_id=profile_id,
            provider=provider,
            model_id=model_id,
            authority=base_authority,
            role=role,
            root=root,
        )
        data = agent.model_dump(mode="json")
        data["enabled"] = False
        data["purpose"] = f"Disabled model profile for {provider.id}/{model_id}; no runtime is allowed."
        return AgentDefinition.model_validate(data)

    if is_ollama and authority == "read-only":
        return _local_read_only_agent(
            profile_id=profile_id,
            provider=provider,
            model_id=model_id,
            role=role,
            tier=tier,
            machine_class=machine_class,
            weight_class=weight_class,
            manifest_notes=manifest_notes,
        )
    if is_ollama and authority == "patch-proposer":
        return _local_patch_agent(
            profile_id=profile_id,
            provider=provider,
            model_id=model_id,
            role=role,
            tier=tier,
            machine_class=machine_class,
            weight_class=weight_class,
            manifest_notes=manifest_notes,
        )
    if not is_ollama and authority in {"read-only", "advisory"}:
        return _remote_advisory_agent(
            profile_id=profile_id,
            provider=provider,
            model_id=model_id,
            role=role,
            authority=authority,
        )
    if not is_ollama and authority == "patch-proposer":
        return _remote_patch_agent(
            profile_id=profile_id,
            provider=provider,
            model_id=model_id,
            role=role,
        )
    raise AgentOnboardingError(
        f"Authority '{authority}' is not supported for provider '{provider.id}' with adapter '{provider.adapter}'."
    )


def build_agent_catalog(root: Path, *, provider_id: str | None = None) -> dict[str, Any]:
    root = root.resolve()
    providers = load_provider_registry(root)
    registry = load_agent_registry(root)
    provider_filter = provider_id.strip() if provider_id else None
    if provider_filter and provider_filter not in providers.providers:
        raise AgentOnboardingError(f"Unknown provider '{provider_filter}'.")

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

    profiles = []
    for agent in sorted(registry.agents.values(), key=lambda item: item.id):
        if provider_filter and agent.provider != provider_filter:
            continue
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
                "runtime_contract": agent_runtime_contract(root, agent),
            }
        )

    local_ollama = _local_ollama_catalog(registry)
    actions = _catalog_actions(provider_rows)
    return {
        "schema_version": 1,
        "providers": provider_rows,
        "profiles": profiles,
        "local_ollama": local_ollama,
        "actions": actions,
    }


def _catalog_actions(provider_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    actions = [
        {
            "label": "Refresh catalog",
            "command": "devflow agent catalog --json",
            "scope": "agent_catalog",
            "safety_class": "pure_read_only",
            "requires_human_approval": False,
            "supervisor_may_auto_run": True,
            "reason": "Read providers, profiles, runtime contracts, env status, and local Ollama discovery.",
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
    return actions


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


def _local_read_only_agent(
    *,
    profile_id: str,
    provider: ProviderDefinition,
    model_id: str,
    role: str,
    tier: str,
    machine_class: str | None,
    weight_class: str | None,
    manifest_notes: list[str],
) -> AgentDefinition:
    return AgentDefinition(
        id=profile_id,
        provider=provider.id,
        model=model_id,
        adapter=provider.adapter,
        adapter_maturity=adapter_maturity(provider.adapter),
        role=role,
        tier=tier,
        default_mode="read_only",
        execution_mode="automated",
        purpose=f"Read-only local Ollama evidence profile for {model_id}.",
        model_role_name=_slug(profile_id),
        machine_class=machine_class,
        weight_class=weight_class if weight_class in {"tiny", "small", "medium", "heavy"} else None,
        secondary_roles=_secondary_roles(role, ["reviewer", "summarizer", "bounded-local-evidence"]),
        use_caution=["Advisory evidence only; do not apply patches, verify, promote, commit, merge, or push."],
        required_verification_command=f"ollama show {model_id}",
        manifest_notes=manifest_notes or ["Ollama manifest was not available during onboarding; treat as low-trust until shown."],
        workspace="isolated_task_workspace",
        can_see=["task_packet", "assigned_workspace", "recent_events", "verification_plan", "verification_summary"],
        can_touch=["<task>/local-model-runs/**"],
        cannot_touch=[
            "<main_checkout>/**",
            "<workspace>/**",
            "<task>/task.yaml",
            "<task>/events.jsonl",
            "<task>/verification.json",
            "<task>/merge-readiness.json",
            "<task>/agents/**/proposal.patch",
            ".git/**",
        ],
        allowed_reads=["<task>/packet.json", "<task>/events.jsonl", "<task>/questions.jsonl", "<workspace>/**"],
        allowed_writes=["<task>/local-model-runs/**"],
        forbidden_writes=[
            "<main_checkout>/**",
            "<workspace>/**",
            "<task>/task.yaml",
            "<task>/events.jsonl",
            "<task>/verification.json",
            "<task>/merge-readiness.json",
            "<task>/packet.json",
            "<task>/agents/**/proposal.patch",
            ".git/**",
        ],
        required_outputs=[
            "Write bounded WorkerEvidence only under <task>/local-model-runs/<run-id>/.",
            "Preserve capped raw output, response text, packet text, and run metadata.",
            "Treat all recommendations as advisory evidence only.",
        ],
        completion_rules=[
            "Do not edit source files or the assigned workspace.",
            "Do not write proposal.patch, apply patches, verify, commit, merge, push, or promote.",
            "Use the local model endpoint only through Dev-Flow's configured local model client boundary.",
        ],
        can_run_shell=False,
        can_use_network=False,
        can_promote=False,
        hermes_delegable=False,
        enabled=True,
    )


def _local_patch_agent(
    *,
    profile_id: str,
    provider: ProviderDefinition,
    model_id: str,
    role: str,
    tier: str,
    machine_class: str | None,
    weight_class: str | None,
    manifest_notes: list[str],
) -> AgentDefinition:
    return AgentDefinition(
        id=profile_id,
        provider=provider.id,
        model=model_id,
        adapter=provider.adapter,
        adapter_maturity=adapter_maturity(provider.adapter),
        role=role,
        tier=tier,
        default_mode="workspace_write",
        execution_mode="automated",
        purpose=f"Local Ollama patch-proposal evidence profile for {model_id}.",
        model_role_name=_slug(profile_id),
        machine_class=machine_class,
        weight_class=weight_class if weight_class in {"tiny", "small", "medium", "heavy"} else None,
        secondary_roles=_secondary_roles(role, ["patch-proposal", "bounded-local-evidence"]),
        use_caution=[
            "Patch proposal evidence only; review-patch, patch-dry-run, apply-patch, verification, and promotion gates remain required."
        ],
        required_verification_command=f"ollama show {model_id}",
        manifest_notes=manifest_notes or ["Ollama manifest was not available during onboarding; treat as low-trust until shown."],
        workspace="isolated_task_workspace",
        can_see=["task_packet", "assigned_workspace", "recent_events", "verification_plan", "verification_summary"],
        can_touch=[
            f"<task>/agents/{profile_id}/proposal.patch",
            f"<task>/agents/{profile_id}/raw_output.md",
            f"<task>/agents/{profile_id}/result.md",
            f"<task>/agents/{profile_id}/run.json",
            f"<task>/agents/{profile_id}/logs/**",
            f"<task>/agents/{profile_id}/questions.jsonl",
            f"<task>/agents/{profile_id}/worker_failed.json",
        ],
        cannot_touch=[
            "<main_checkout>/**",
            "<workspace>/**",
            "<task>/task.yaml",
            "<task>/events.jsonl",
            "<task>/verification.json",
            "<task>/merge-readiness.json",
            ".git/**",
        ],
        allowed_reads=["<task>/packet.json", "<task>/events.jsonl", "<task>/questions.jsonl", "<workspace>/**"],
        allowed_writes=[
            f"<task>/agents/{profile_id}/proposal.patch",
            f"<task>/agents/{profile_id}/raw_output.md",
            f"<task>/agents/{profile_id}/result.md",
            f"<task>/agents/{profile_id}/run.json",
            f"<task>/agents/{profile_id}/logs/**",
            f"<task>/agents/{profile_id}/questions.jsonl",
            f"<task>/agents/{profile_id}/worker_failed.json",
        ],
        forbidden_writes=[
            "<main_checkout>/**",
            "<workspace>/**",
            "<task>/task.yaml",
            "<task>/events.jsonl",
            "<task>/verification.json",
            "<task>/merge-readiness.json",
            "<task>/packet.json",
            ".git/**",
        ],
        required_outputs=[
            f"Write <task>/agents/{profile_id}/proposal.patch with a unified diff.",
            f"Always preserve raw model output in <task>/agents/{profile_id}/raw_output.md and run metadata in <task>/agents/{profile_id}/run.json.",
            "Do not apply patches, run verification, promote, commit, merge, or push.",
        ],
        completion_rules=[
            "Propose changes only as a unified diff in proposal.patch; do not directly edit the workspace or main checkout.",
            "Dev-Flow review-patch, patch-dry-run, apply-patch, verification, and promotion gates remain required.",
            "Worker completion is not promotion readiness.",
        ],
        can_run_shell=False,
        can_use_network=False,
        can_promote=False,
        hermes_delegable=False,
        enabled=True,
    )


def _remote_advisory_agent(
    *,
    profile_id: str,
    provider: ProviderDefinition,
    model_id: str,
    role: str,
    authority: Authority,
) -> AgentDefinition:
    return AgentDefinition(
        id=profile_id,
        provider=provider.id,
        model=model_id,
        adapter=provider.adapter,
        adapter_maturity=adapter_maturity(provider.adapter),
        role=role,
        tier="frontier",
        default_mode="read_only" if authority == "read-only" else "frontier_read_only",
        execution_mode="automated",
        purpose=f"Bounded remote advisory evidence profile for {provider.id}/{model_id}.",
        model_role_name=_slug(profile_id),
        secondary_roles=_secondary_roles(role, ["gap-analysis", "review", "status", "advisory"]),
        use_caution=[
            "Advisory evidence only; do not create tasks, run workers, apply patches, verify, promote, commit, merge, or push."
        ],
        manifest_notes=["Model slug is accepted from operator input; no remote catalog call was made during onboarding."],
        workspace="isolated_task_workspace",
        can_see=["supervisor_packet", "task_packet", "status_projection", "verification_ledger_summary"],
        can_touch=["<task>/agent-advisory-runs/**"],
        cannot_touch=[
            "<main_checkout>/**",
            "<workspace>/**",
            "<task>/task.yaml",
            "<task>/events.jsonl",
            "<task>/verification.json",
            "<task>/merge-readiness.json",
            "<task>/agents/**/proposal.patch",
            ".git/**",
        ],
        allowed_reads=[
            "<task>/packet.json",
            "<task>/events.jsonl",
            "<task>/questions.jsonl",
            "<workspace>/**",
            "<repo>/docs/verification-ledger.md",
        ],
        allowed_writes=["<reports>/agent-advisory-runs/**", "<task>/agent-advisory-runs/**"],
        forbidden_writes=[
            "<main_checkout>/**",
            "<workspace>/**",
            "<task>/task.yaml",
            "<task>/events.jsonl",
            "<task>/verification.json",
            "<task>/merge-readiness.json",
            "<task>/packet.json",
            "<task>/agents/**/proposal.patch",
            ".git/**",
        ],
        required_outputs=[
            "Write advisory prompt, response, run metadata, usage when returned, recommendations, and safety flags under agent-advisory-runs.",
            "Treat all recommendations as evidence only; Dev-Flow and the human operator own task creation, worker execution, verification, promotion, commit, merge, and push.",
        ],
        completion_rules=[
            "Use bounded Dev-Flow state only; do not scan the full repository blindly.",
            "Do not create tasks, run workers, apply patches, verify, promote, commit, push, or mutate canonical state.",
            "Return one highest-impact next safe action grounded in the supplied evidence.",
        ],
        can_run_shell=False,
        can_use_network=False,
        can_promote=False,
        hermes_delegable=False,
        enabled=True,
    )


def _remote_patch_agent(
    *,
    profile_id: str,
    provider: ProviderDefinition,
    model_id: str,
    role: str,
) -> AgentDefinition:
    return AgentDefinition(
        id=profile_id,
        provider=provider.id,
        model=model_id,
        adapter=provider.adapter,
        adapter_maturity=adapter_maturity(provider.adapter),
        role=role,
        tier="frontier",
        default_mode="patch_proposal_only",
        execution_mode="automated",
        purpose=(
            f"Explicit remote patch proposal lane for {provider.id}/{model_id}. It writes proposal.patch "
            "evidence only; Dev-Flow review, dry-run, apply, verification, and promotion gates remain separate."
        ),
        model_role_name=_slug(profile_id),
        secondary_roles=["patch-proposal", "explicit-human-approved-lane"],
        use_caution=[
            "Not Hermes-delegable and not cron-callable by default.",
            "Do not use through task run or generic agent run.",
        ],
        manifest_notes=["Model slug is accepted from operator input; no remote catalog call was made during onboarding."],
        workspace="isolated_task_workspace",
        can_see=["task_packet", "assigned_workspace", "recent_events", "verification_plan"],
        can_touch=[
            f"<task>/agents/{profile_id}/proposal.patch",
            f"<task>/agents/{profile_id}/raw_output.md",
            f"<task>/agents/{profile_id}/run.json",
            f"<task>/agents/{profile_id}/result.md",
        ],
        cannot_touch=[
            "<main_checkout>/**",
            "<workspace>/**",
            "<task>/task.yaml",
            "<task>/events.jsonl",
            "<task>/verification.json",
            "<task>/merge-readiness.json",
            ".git/**",
        ],
        allowed_reads=["<task>/packet.json", "<task>/events.jsonl", "<task>/questions.jsonl", "<workspace>/**"],
        allowed_writes=[
            f"<task>/agents/{profile_id}/proposal.patch",
            f"<task>/agents/{profile_id}/raw_output.md",
            f"<task>/agents/{profile_id}/run.json",
            f"<task>/agents/{profile_id}/result.md",
        ],
        forbidden_writes=[
            "<main_checkout>/**",
            "<workspace>/**",
            "<task>/task.yaml",
            "<task>/events.jsonl",
            "<task>/verification.json",
            "<task>/merge-readiness.json",
            "<task>/packet.json",
            ".git/**",
        ],
        required_outputs=[
            f"Write <task>/agents/{profile_id}/proposal.patch with a unified diff.",
            f"Write <task>/agents/{profile_id}/raw_output.md, run.json, and result.md as proposal evidence.",
            "Do not apply patches, run verification, promote, commit, merge, or push.",
        ],
        completion_rules=[
            "Only run by explicit human-selected propose-patch command.",
            "Existing review-patch, patch-dry-run, apply-patch, verification, and promotion gates remain required.",
            "Worker completion is not promotion readiness.",
        ],
        can_run_shell=False,
        can_use_network=False,
        can_promote=False,
        hermes_delegable=False,
        enabled=True,
    )


def _require_provider(root: Path, provider_id: str) -> ProviderDefinition:
    try:
        return load_provider_registry(root).require_provider(provider_id)
    except (AgentRegistryError, KeyError) as exc:
        raise AgentOnboardingError(f"Unknown provider '{provider_id}'.") from exc


def _provider_for(root: Path, agent: AgentDefinition) -> ProviderDefinition | None:
    try:
        return load_provider_registry(root).providers.get(agent.provider)
    except Exception:
        return None


def _validate_role(root: Path, role: str) -> None:
    try:
        roles = load_role_registry(root)
    except AgentRegistryError as exc:
        raise AgentOnboardingError(str(exc)) from exc
    if roles.roles and role not in roles.enabled_role_ids():
        raise AgentOnboardingError(f"Unknown role '{role}'.")


def _validate_provider_authority(provider: ProviderDefinition, authority: Authority) -> None:
    if authority == "disabled":
        return
    if _is_ollama_provider(provider):
        if authority not in {"read-only", "patch-proposer"}:
            raise AgentOnboardingError("Ollama providers support read-only or patch-proposer authority.")
        if provider.adapter != "ollama_chat":
            raise AgentOnboardingError("Ollama providers must use the ollama_chat adapter.")
        if not is_local_ollama_base_url(provider.base_url):
            raise AgentOnboardingError("Ollama model onboarding requires a localhost Ollama base_url.")
        return
    if provider.adapter not in REMOTE_MODEL_ADAPTERS:
        raise AgentOnboardingError(
            f"Provider '{provider.id}' adapter '{provider.adapter}' does not support model onboarding."
        )
    if authority not in {"read-only", "advisory", "patch-proposer"}:
        raise AgentOnboardingError(f"Authority '{authority}' is not supported for provider '{provider.id}'.")


def _is_ollama_provider(provider: ProviderDefinition) -> bool:
    return provider.provider == "ollama" or provider.id == "ollama"


def _ollama_enrichment(model_id: str) -> dict[str, Any]:
    try:
        from devflow.control_room.local_agent_discovery import _run_ollama

        result = _run_ollama(["ollama", "show", model_id], check=False)
    except Exception:
        return {
            "manifest_notes": [],
            "weight_class": None,
            "machine_class": None,
            "tier": "local",
        }
    if result.returncode != 0:
        return {
            "manifest_notes": [],
            "weight_class": None,
            "machine_class": None,
            "tier": "local",
        }
    manifest = parse_ollama_show(model_id, result.stdout)
    profile = classify_local_model(manifest)
    weight_class = profile.weight_class if profile.weight_class in {"tiny", "small", "medium", "heavy"} else None
    machine_class = "mac_studio" if weight_class == "heavy" else "either"
    tier = "premium_local" if weight_class == "heavy" else "strong_local" if weight_class == "medium" else "local"
    notes = []
    if manifest.architecture:
        notes.append(f"Manifest architecture: {manifest.architecture}.")
    if manifest.parameters:
        notes.append(f"Manifest parameters: {manifest.parameters}.")
    if manifest.context_length:
        notes.append(f"Manifest context length: {manifest.context_length}.")
    if manifest.quantization:
        notes.append(f"Manifest quantization: {manifest.quantization}.")
    if manifest.capabilities:
        notes.append(f"Manifest capabilities: {', '.join(manifest.capabilities)}.")
    return {
        "manifest_notes": notes,
        "weight_class": weight_class,
        "machine_class": machine_class,
        "tier": tier,
    }


def _validate_safe_id(value: str, *, label: str) -> str:
    value = value.strip()
    if not SAFE_ID_PATTERN.match(value):
        raise AgentOnboardingError(
            f"Unsafe {label} '{value}'. Use 2-80 chars: lowercase letters, digits, underscores, or hyphens; start with a letter."
        )
    return value


def _validate_provider_adapter(adapter: str) -> None:
    if adapter not in PROVIDER_ADAPTERS:
        allowed = ", ".join(sorted(PROVIDER_ADAPTERS))
        raise AgentOnboardingError(f"Unsupported provider adapter '{adapter}'. Allowed: {allowed}.")
    if adapter_maturity(adapter) == "planned_not_executable":
        raise AgentOnboardingError(f"Adapter '{adapter}' is not executable enough for onboarding.")


def _validate_base_url(base_url: str) -> None:
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise AgentOnboardingError("base_url must be an http(s) URL.")


def _validate_api_key_env(api_key_env: str) -> None:
    if api_key_env.startswith("sk-") or not api_key_env.isupper() or not all(c.isalnum() or c == "_" for c in api_key_env):
        raise AgentOnboardingError("api_key_env must be an uppercase environment variable name, not a literal key.")


def _provider_yaml_payload(provider: ProviderDefinition) -> dict[str, Any]:
    return {
        "id": provider.id,
        "provider": provider.provider,
        "adapter": provider.adapter,
        "base_url": provider.base_url,
        **({"api_key_env": provider.api_key_env} if provider.api_key_env else {}),
        **(
            {"default_timeout_seconds": provider.default_timeout_seconds}
            if provider.default_timeout_seconds is not None
            else {}
        ),
        "enabled": provider.enabled,
    }


def _agent_yaml_payload(agent: AgentDefinition) -> dict[str, Any]:
    payload = agent.model_dump(mode="json", exclude={"id", "adapter_maturity"}, exclude_none=True)
    return payload


def _read_registry_payload(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": 1, "default_agent": "devflow-manual-codex-worker", "agents": {}}
    payload = _read_yaml_mapping(path)
    payload.setdefault("version", 1)
    payload.setdefault("agents", {})
    return payload


def _read_yaml_mapping(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    if not text.strip():
        return {}
    payload = yaml.safe_load(text)
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise AgentOnboardingError(f"{path} root must be a map.")
    return payload


def _dump_yaml(payload: dict[str, Any]) -> str:
    return yaml.safe_dump(payload, sort_keys=False, allow_unicode=False)


def _normalize_provider_payload(payload: dict[str, Any], provider_id: str) -> dict[str, Any]:
    normalized = dict(payload)
    normalized.setdefault("id", provider_id)
    normalized.setdefault("provider", provider_id)
    normalized.setdefault("enabled", True)
    normalized = {key: value for key, value in normalized.items() if value is not None}
    return normalized


def _canonical_agent_payload(payload: dict[str, Any]) -> dict[str, Any]:
    data = dict(payload)
    data.pop("adapter_maturity", None)
    data.setdefault("execution_mode", "automated")
    data.setdefault("secondary_roles", [])
    data.setdefault("use_caution", [])
    data.setdefault("manifest_notes", [])
    data.setdefault("can_see", [])
    data.setdefault("can_touch", [])
    data.setdefault("cannot_touch", [])
    data.setdefault("allowed_reads", [])
    data.setdefault("allowed_writes", [])
    data.setdefault("forbidden_writes", [])
    data.setdefault("required_outputs", [])
    data.setdefault("completion_rules", [])
    data.setdefault("can_run_shell", False)
    data.setdefault("can_use_network", False)
    data.setdefault("can_promote", False)
    data.setdefault("hermes_delegable", False)
    data.setdefault("enabled", True)
    return data


def _duplicate_profile_for(registry: Any, generated: dict[str, Any], profile_id: str) -> str | None:
    for existing_id, existing_agent in registry.agents.items():
        if existing_id == profile_id:
            continue
        if (
            existing_agent.provider == generated.get("provider")
            and existing_agent.model == generated.get("model")
            and existing_agent.role == generated.get("role")
            and existing_agent.default_mode == generated.get("default_mode")
            and bool(existing_agent.enabled) == bool(generated.get("enabled", True))
        ):
            return existing_id
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


def _secondary_roles(primary_role: str, roles: list[str]) -> list[str]:
    return sorted({role for role in roles if role != primary_role})


def _slug(value: str) -> str:
    value = value.lower().replace(":", "-").replace("/", "-").replace(".", "")
    value = re.sub(r"[^a-z0-9_-]+", "-", value)
    value = re.sub(r"[-_]{2,}", "-", value).strip("-_")
    return value or "model"


def _relative(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()
