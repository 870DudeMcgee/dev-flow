from __future__ import annotations

from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

import yaml
from pydantic import BaseModel, Field, ValidationError


AgentPermissionMode = Literal[
    "read_only",
    "workspace_write",
    "verify_only",
    "docs_only",
    "frontier_read_only",
    "manual_packet_only",
]
AdapterMaturity = Literal["stable_runtime", "local_patch_runtime", "experimental_readonly", "planned_not_executable"]
MachineClass = Literal["mac_mini", "mac_studio", "either"]
WeightClass = Literal["tiny", "small", "medium", "heavy"]

ADAPTER_MATURITY: dict[str, AdapterMaturity] = {
    "shell": "stable_runtime",
    "manual": "stable_runtime",
    "manual_packet": "experimental_readonly",
    "ollama_chat": "local_patch_runtime",
    "openai_responses": "planned_not_executable",
    "openai_compatible": "experimental_readonly",
    "anthropic_messages": "experimental_readonly",
    "gemini": "experimental_readonly",
    "openai_chat": "experimental_readonly",
}
STABLE_RUNTIME_ADAPTERS = tuple(sorted(adapter for adapter, maturity in ADAPTER_MATURITY.items() if maturity == "stable_runtime"))
LOCAL_PATCH_RUNTIME_ADAPTERS = tuple(
    sorted(adapter for adapter, maturity in ADAPTER_MATURITY.items() if maturity == "local_patch_runtime")
)
EXPERIMENTAL_READONLY_ADAPTERS = tuple(
    sorted(adapter for adapter, maturity in ADAPTER_MATURITY.items() if maturity == "experimental_readonly")
)
PLANNED_NOT_EXECUTABLE_ADAPTERS = tuple(
    sorted(adapter for adapter, maturity in ADAPTER_MATURITY.items() if maturity == "planned_not_executable")
)


def adapter_maturity(adapter: str) -> AdapterMaturity:
    return ADAPTER_MATURITY.get(adapter, "planned_not_executable")


def is_stable_runtime_adapter(adapter: str) -> bool:
    return adapter_maturity(adapter) == "stable_runtime"


def is_local_patch_runtime_adapter(adapter: str) -> bool:
    return adapter_maturity(adapter) == "local_patch_runtime"


def is_experimental_readonly_adapter(adapter: str) -> bool:
    return adapter_maturity(adapter) == "experimental_readonly"


def is_planned_not_executable_adapter(adapter: str) -> bool:
    return adapter_maturity(adapter) == "planned_not_executable"


def stable_runtime_adapters_label() -> str:
    return ", ".join(STABLE_RUNTIME_ADAPTERS)


def local_patch_runtime_adapters_label() -> str:
    return ", ".join(LOCAL_PATCH_RUNTIME_ADAPTERS)


def adapter_execution_refusal(adapter: str, agent_id: str | None = None) -> str:
    subject = f"Adapter '{adapter}'"
    if agent_id is not None:
        subject = f"{subject} for agent '{agent_id}'"
    return (
        f"{subject} is {adapter_maturity(adapter)} and cannot execute. "
        "Only stable_runtime adapters or explicitly safe local_patch_runtime agents can execute. "
        f"Stable runtime adapters: {stable_runtime_adapters_label()}. "
        f"Local patch runtime adapters: {local_patch_runtime_adapters_label() or 'none'}."
    )


class AgentRegistryError(ValueError):
    def __init__(self, source_path: Path, errors: list[str]) -> None:
        self.source_path = source_path
        self.errors = errors
        detail = "; ".join(errors)
        super().__init__(f"{_display_path(source_path)}: {detail}")


class AgentDefinition(BaseModel):
    id: str
    provider: str
    model: str
    adapter: str
    adapter_maturity: AdapterMaturity | None = None
    role: str
    tier: str
    default_mode: AgentPermissionMode
    execution_mode: str = "automated"
    purpose: str | None = None
    model_role_name: str | None = None
    machine_class: MachineClass | None = None
    weight_class: WeightClass | None = None
    secondary_roles: list[str] = Field(default_factory=list)
    use_caution: list[str] = Field(default_factory=list)
    required_verification_command: str | None = None
    model_alias_group: str | None = None
    manifest_notes: list[str] = Field(default_factory=list)
    workspace: str
    can_see: list[str] = Field(default_factory=list)
    can_touch: list[str] = Field(default_factory=list)
    cannot_touch: list[str] = Field(default_factory=list)
    allowed_reads: list[str] = Field(default_factory=list)
    allowed_writes: list[str] = Field(default_factory=list)
    forbidden_writes: list[str] = Field(default_factory=list)
    required_outputs: list[str] = Field(default_factory=list)
    completion_rules: list[str] = Field(default_factory=list)
    can_run_shell: bool = False
    can_use_network: bool = False
    can_promote: bool = False
    hermes_delegable: bool = False
    enabled: bool = True


class AgentRegistry(BaseModel):
    version: int = 1
    default_agent_id: str | None = None
    agents: dict[str, AgentDefinition] = Field(default_factory=dict)
    source_path: Path | None = None

    model_config = {"arbitrary_types_allowed": True}

    def enabled_agents(self) -> list[AgentDefinition]:
        return [agent for agent in self.agents.values() if agent.enabled]

    def enabled_agent_ids(self) -> list[str]:
        return [agent.id for agent in self.enabled_agents()]

    def default_agent(self) -> AgentDefinition | None:
        if self.default_agent_id is None:
            return None
        agent = self.agents.get(self.default_agent_id)
        if agent is None or not agent.enabled:
            return None
        return agent

    def require_agent(self, agent_id: str) -> AgentDefinition:
        try:
            return self.agents[agent_id]
        except KeyError as exc:
            raise KeyError(f"Unknown agent '{agent_id}'.") from exc


class ProviderDefinition(BaseModel):
    id: str
    provider: str
    adapter: str
    base_url: str | None = None
    api_key_env: str | None = None
    default_timeout_seconds: int | None = None
    delivery: str | None = None
    enabled: bool = True


def is_executable_agent_runtime(agent: AgentDefinition, provider: ProviderDefinition | None = None) -> bool:
    if is_stable_runtime_adapter(agent.adapter):
        return True
    return is_local_patch_runtime_agent(agent, provider=provider) or is_local_model_worker_pool_agent(agent, provider=provider)


def is_local_model_worker_pool_agent(agent: AgentDefinition, provider: ProviderDefinition | None = None) -> bool:
    if agent.adapter != "ollama_chat" or agent.provider != "ollama":
        return False
    if not is_local_patch_runtime_adapter(agent.adapter):
        return False
    if not agent.enabled:
        return False
    if agent.default_mode not in {"read_only", "docs_only", "manual_packet_only"}:
        return False
    if agent.execution_mode != "automated":
        return False
    if agent.workspace != "isolated_task_workspace":
        return False
    if agent.can_promote or agent.can_run_shell or agent.can_use_network:
        return False
    disallowed_write_markers = ("<workspace>", "proposal.patch", ".git/")
    if any(marker in path for path in agent.allowed_writes for marker in disallowed_write_markers):
        return False
    if provider is None:
        return True
    if not provider.enabled or provider.provider != "ollama" or provider.adapter != "ollama_chat":
        return False
    return is_local_ollama_base_url(provider.base_url)


def is_local_patch_runtime_agent(agent: AgentDefinition, provider: ProviderDefinition | None = None) -> bool:
    if not is_local_patch_runtime_adapter(agent.adapter):
        return False
    if agent.adapter != "ollama_chat" or agent.provider != "ollama":
        return False
    if not agent.enabled:
        return False
    if agent.default_mode != "workspace_write":
        return False
    if agent.execution_mode != "automated":
        return False
    if agent.workspace != "isolated_task_workspace":
        return False
    if agent.can_promote or agent.can_run_shell or agent.can_use_network:
        return False
    if provider is None:
        return True
    if not provider.enabled or provider.provider != "ollama" or provider.adapter != "ollama_chat":
        return False
    return is_local_ollama_base_url(provider.base_url)


def is_local_ollama_base_url(base_url: str | None) -> bool:
    if base_url is None or not base_url.strip():
        return True
    parsed = urlparse(base_url)
    return parsed.scheme in {"http", "https"} and parsed.hostname in {"127.0.0.1", "localhost", "::1"}


class ProviderRegistry(BaseModel):
    providers: dict[str, ProviderDefinition] = Field(default_factory=dict)
    source_paths: dict[str, Path] = Field(default_factory=dict)

    model_config = {"arbitrary_types_allowed": True}

    def enabled_providers(self) -> list[ProviderDefinition]:
        return [prov for prov in self.providers.values() if prov.enabled]

    def enabled_provider_ids(self) -> list[str]:
        return [prov.id for prov in self.enabled_providers()]

    def require_provider(self, provider_id: str) -> ProviderDefinition:
        try:
            return self.providers[provider_id]
        except KeyError as exc:
            raise KeyError(f"Unknown provider '{provider_id}'.") from exc


class RoleDefinition(BaseModel):
    role: str
    description: str | None = None
    enabled: bool = True


class RoleRegistry(BaseModel):
    roles: dict[str, RoleDefinition] = Field(default_factory=dict)
    source_path: Path | None = None

    model_config = {"arbitrary_types_allowed": True}

    def enabled_roles(self) -> list[RoleDefinition]:
        return [role for role in self.roles.values() if role.enabled]

    def enabled_role_ids(self) -> list[str]:
        return [role.role for role in self.enabled_roles()]

    def require_role(self, role_id: str) -> RoleDefinition:
        try:
            return self.roles[role_id]
        except KeyError as exc:
            raise KeyError(f"Unknown role '{role_id}'.") from exc


def load_provider_registry(root: Path) -> ProviderRegistry:
    root = root.resolve()
    providers_dir = root / ".devflow/providers"

    if providers_dir.is_dir():
        provider_files = sorted(providers_dir.glob("*.yaml"))
        if provider_files:
            providers: dict[str, ProviderDefinition] = {}
            source_paths: dict[str, Path] = {}
            errors: list[str] = []

            for file_path in provider_files:
                provider_id = file_path.stem
                try:
                    payload = _read_provider_file(file_path)
                    if not isinstance(payload, dict):
                        errors.append(f"provider '{provider_id}' root must be a map")
                        continue
                    extracted_prov = payload.get("provider", provider_id)
                    if not isinstance(extracted_prov, str):
                        errors.append(f"provider '{provider_id}' provider must be a string")
                        extracted_prov = provider_id

                    try:
                        provider_def = ProviderDefinition.model_validate({
                            "id": provider_id,
                            "provider": extracted_prov,
                            **payload
                        })
                    except ValidationError as exc:
                        for item in exc.errors():
                            loc = ".".join(str(part) for part in item["loc"])
                            errors.append(f"providers.{provider_id}.{loc}: {item['msg']}")
                        continue

                    if provider_def.api_key_env is not None:
                        val = provider_def.api_key_env
                        if val.startswith("sk-") or not val.isupper() or not all(c.isalnum() or c == '_' for c in val):
                            errors.append(
                                f"providers.{provider_id}.api_key_env must be an uppercase environment variable name, "
                                f"not a literal secret value: '{val}'"
                            )

                    providers[provider_id] = provider_def
                    source_paths[provider_id] = file_path
                except Exception as exc:
                    errors.append(f"provider '{provider_id}' failed to load: {exc}")

            if errors:
                raise AgentRegistryError(providers_dir, errors)

            return ProviderRegistry(providers=providers, source_paths=source_paths)

    seed_registry_path = root / ".devflow/workers/registry.yaml"
    if seed_registry_path.exists():
        return ProviderRegistry()

    return ProviderRegistry()


def _read_provider_file(path: Path) -> dict[str, object]:
    return _read_yaml_mapping(path, "provider")


def load_role_registry(root: Path) -> RoleRegistry:
    root = root.resolve()
    roles_path = root / ".devflow/agents/roles.yaml"
    if roles_path.exists():
        payload = _read_roles_file(roles_path)
        return _build_role_registry(roles_path, payload)

    seed_registry_path = root / ".devflow/workers/registry.yaml"
    if seed_registry_path.exists():
        return RoleRegistry()

    return RoleRegistry()


def _read_roles_file(path: Path) -> dict[str, object]:
    return _read_yaml_mapping(path, "roles")


def _build_role_registry(source_path: Path, payload: dict[str, object]) -> RoleRegistry:
    errors: list[str] = []

    version = payload.get("version", 1)
    if not isinstance(version, int) or version != 1:
        errors.append("version must be 1")

    raw_roles = payload.get("roles", {})
    if raw_roles is None:
        raw_roles = {}
    if not isinstance(raw_roles, dict):
        errors.append("roles must be a map")
        raw_roles = {}

    roles: dict[str, RoleDefinition] = {}
    for role_id, raw_role in raw_roles.items():
        if not isinstance(role_id, str):
            errors.append("role ids must be strings")
            continue
        if not isinstance(raw_role, dict):
            errors.append(f"roles.{role_id} must be a map")
            continue
        try:
            role = RoleDefinition.model_validate({"role": role_id, **raw_role})
        except ValidationError as exc:
            for item in exc.errors():
                loc = ".".join(str(part) for part in item["loc"])
                errors.append(f"roles.{role_id}.{loc}: {item['msg']}")
            continue
        roles[role_id] = role

    if errors:
        raise AgentRegistryError(source_path, errors)

    return RoleRegistry(
        roles=roles,
        source_path=source_path,
    )


def load_agent_registry(root: Path) -> AgentRegistry:
    root = root.resolve()
    registry_path = root / ".devflow/agents/registry.yaml"
    if registry_path.exists():
        payload = _read_registry_file(registry_path)
        return _build_registry(registry_path, payload, root=root)

    seed_registry_path = root / ".devflow/workers/registry.yaml"
    if seed_registry_path.exists():
        payload = _read_registry_file(seed_registry_path)
        if payload.get("workers") == [] and "agents" not in payload:
            return AgentRegistry(
                version=_registry_version(payload),
                default_agent_id="devflow-manual-codex-worker",
                agents=_builtin_agents(),
                source_path=seed_registry_path,
            )
        return _build_registry(seed_registry_path, payload, root=root)

    return AgentRegistry(default_agent_id="devflow-manual-codex-worker", agents=_builtin_agents())


def _build_registry(source_path: Path, payload: dict[str, object], root: Path | None = None) -> AgentRegistry:
    errors: list[str] = []
    version = _registry_version(payload)
    if version != 1:
        errors.append("version must be 1")

    default_agent_id = payload.get("default_agent")
    if default_agent_id is not None and not isinstance(default_agent_id, str):
        errors.append("default_agent must be a string")
        default_agent_id = None

    raw_agents = payload.get("agents", {})
    if raw_agents is None:
        raw_agents = {}
    if not isinstance(raw_agents, dict):
        errors.append("agents must be a map")
        raw_agents = {}

    providers = None
    roles = None
    if root is not None:
        try:
            providers = load_provider_registry(root)
        except Exception:
            pass
        try:
            roles = load_role_registry(root)
        except Exception:
            pass

    agents: dict[str, AgentDefinition] = {}
    for agent_id, raw_agent in raw_agents.items():
        if not isinstance(agent_id, str):
            errors.append("agent ids must be strings")
            continue
        if not isinstance(raw_agent, dict):
            errors.append(f"agents.{agent_id} must be a map")
            continue
        try:
            agent = AgentDefinition.model_validate({"id": agent_id, **raw_agent})
        except ValidationError as exc:
            for item in exc.errors():
                loc = ".".join(str(part) for part in item["loc"])
                errors.append(f"agents.{agent_id}.{loc}: {item['msg']}")
            continue
        if agent.adapter_maturity is None:
            agent.adapter_maturity = adapter_maturity(agent.adapter)
        agents[agent_id] = agent
        errors.extend(_validate_agent_policy(agent, providers=providers, roles=roles))

    for builtin_id, builtin_agent in _builtin_agents().items():
        agents.setdefault(builtin_id, builtin_agent)

    if default_agent_id is not None:
        default_agent = agents.get(default_agent_id)
        if default_agent is None:
            errors.append(f"default_agent '{default_agent_id}' is not defined")
        elif not default_agent.enabled:
            errors.append(f"default_agent '{default_agent_id}' is disabled")

    if errors:
        raise AgentRegistryError(source_path, errors)

    return AgentRegistry(
        version=version,
        default_agent_id=default_agent_id,
        agents=agents,
        source_path=source_path,
    )


def _builtin_agents() -> dict[str, AgentDefinition]:
    proof_agent = AgentDefinition(
        id="devflow-manual-codex-worker",
        provider="manual",
        model="human-launched-codex",
        adapter="manual",
        adapter_maturity="stable_runtime",
        role="implementation_worker",
        tier="manual",
        default_mode="workspace_write",
        execution_mode="human_launched_agent",
        purpose=(
            "Consume a bounded Dev-Flow task packet, edit only the assigned isolated workspace, "
            "produce structured result/question/failure evidence, then stop. Dev-Flow owns "
            "verification and human-controlled promotion."
        ),
        workspace="isolated_task_workspace",
        can_see=[
            "task_packet",
            "assigned_workspace",
            "recent_events",
            "verification_plan",
            "verification_summary",
        ],
        can_touch=[
            "<workspace>/**",
            "<task>/agents/devflow-manual-codex-worker/result.md",
            "<task>/agents/devflow-manual-codex-worker/questions.jsonl",
            "<task>/agents/devflow-manual-codex-worker/worker_failed.json",
        ],
        cannot_touch=[
            "<main_checkout>/**",
            "<task>/task.yaml",
            "<task>/events.jsonl",
            "<task>/verification.json",
            "<task>/merge-readiness.json",
            ".git/**",
        ],
        allowed_reads=[
            "<task>/packet.json",
            "<task>/events.jsonl",
            "<task>/questions.jsonl",
            "<task>/agents/devflow-manual-codex-worker/handoff.md",
            "<workspace>/**",
        ],
        allowed_writes=[
            "<workspace>/**",
            "<task>/agents/devflow-manual-codex-worker/result.md",
            "<task>/agents/devflow-manual-codex-worker/questions.jsonl",
            "<task>/agents/devflow-manual-codex-worker/worker_failed.json",
        ],
        forbidden_writes=[
            "<main_checkout>/**",
            "<task>/task.yaml",
            "<task>/events.jsonl",
            "<task>/verification.json",
            "<task>/merge-readiness.json",
            "<task>/packet.json",
            ".git/**",
        ],
        required_outputs=[
            "On completion, write <task>/agents/devflow-manual-codex-worker/result.md with status, summary, changed files, and suggested verification.",
            "When blocked, append one blocked_question JSON object to <task>/agents/devflow-manual-codex-worker/questions.jsonl.",
            "When failed, write <task>/agents/devflow-manual-codex-worker/worker_failed.json with summary, error_type, evidence, and next_safe_action.",
        ],
        completion_rules=[
            "Edit only files under <workspace>.",
            "Never edit the main checkout, .git, <task>/task.yaml, <task>/events.jsonl, <task>/verification.json, or promotion artifacts.",
            "Do not run provider API calls, route models, select models automatically, schedule other agents, verify, promote, commit, or push.",
            "Stop after writing exactly one terminal evidence artifact.",
            "Dev-Flow verification is required after result.md; worker completion is not promotion readiness.",
        ],
        can_run_shell=False,
        can_use_network=False,
        can_promote=False,
        enabled=True,
    )
    agents = {proof_agent.id: proof_agent}

    # Define standard automated agents mapping to each new execution runtime.
    # Only local Ollama patch agents may execute; remote provider agents stay disabled.
    presets = [
        ("qwopus-implementer", "ollama", "qwopus:latest", "ollama_chat", False, "implementation_worker", "strong_local", "workspace_write", True),
        ("devflow-ollama-worker", "ollama", "qwen2.5-coder:14b", "ollama_chat", False, "implementation_worker", "strong_local", "workspace_write", False),
        ("devflow-openai-worker", "openai", "gpt-4o", "openai_chat", True, "implementation_worker", "strong_local", "workspace_write", False),
        ("devflow-anthropic-worker", "anthropic", "claude-3-5-sonnet", "anthropic_messages", True, "implementation_worker", "strong_local", "workspace_write", False),
        ("devflow-gemini-worker", "gemini", "gemini-1.5-pro", "gemini", True, "implementation_worker", "strong_local", "workspace_write", False),
        ("devflow-openai-compatible-worker", "openai_compatible", "custom-model", "openai_compatible", True, "implementation_worker", "strong_local", "workspace_write", False),
        ("devflow-openai-planner", "openai", "gpt-4o", "openai_chat", True, "frontier_planner_architect_reviewer", "frontier", "frontier_read_only", False),
        ("devflow-openai-reviewer", "openai", "gpt-4o", "openai_chat", True, "frontier_planner_architect_reviewer", "frontier", "frontier_read_only", False),
    ]

    for agent_id, provider, model, adapter, can_use_network, role, tier, default_mode, enabled in presets:
        if default_mode == "workspace_write":
            can_touch = [
                "<workspace>/**",
                f"<task>/agents/{agent_id}/proposal.patch",
                f"<task>/agents/{agent_id}/raw_output.md",
                f"<task>/agents/{agent_id}/result.md",
                f"<task>/agents/{agent_id}/run.json",
                f"<task>/agents/{agent_id}/logs/**",
                f"<task>/agents/{agent_id}/questions.jsonl",
                f"<task>/agents/{agent_id}/worker_failed.json",
            ]
            allowed_writes = [
                "<workspace>/**",
                f"<task>/agents/{agent_id}/proposal.patch",
                f"<task>/agents/{agent_id}/raw_output.md",
                f"<task>/agents/{agent_id}/result.md",
                f"<task>/agents/{agent_id}/run.json",
                f"<task>/agents/{agent_id}/logs/**",
                f"<task>/agents/{agent_id}/questions.jsonl",
                f"<task>/agents/{agent_id}/worker_failed.json",
            ]
            forbidden_writes = [
                "<main_checkout>/**",
                "<task>/task.yaml",
                "<task>/events.jsonl",
                "<task>/verification.json",
                "<task>/merge-readiness.json",
                "<task>/packet.json",
                ".git/**",
            ]
            comp_rules = [
                "Edit only files under <workspace>.",
                "Never edit the main checkout, .git, <task>/task.yaml, <task>/events.jsonl, <task>/verification.json, or promotion artifacts.",
                "Stop after writing exactly one terminal evidence artifact.",
                "Dev-Flow verification is required after result.md; worker completion is not promotion readiness.",
            ]
        else:
            can_touch = [
                f"<task>/agents/{agent_id}/result.md",
                f"<task>/agents/{agent_id}/questions.jsonl",
                f"<task>/agents/{agent_id}/worker_failed.json",
            ]
            allowed_writes = [
                f"<task>/agents/{agent_id}/result.md",
                f"<task>/agents/{agent_id}/questions.jsonl",
                f"<task>/agents/{agent_id}/worker_failed.json",
            ]
            forbidden_writes = [
                "<main_checkout>/**",
                "<task>/task.yaml",
                "<task>/events.jsonl",
                "<task>/verification.json",
                "<task>/merge-readiness.json",
                "<task>/packet.json",
                ".git/**",
                "<workspace>/**",
            ]
            comp_rules = [
                "Do not edit files in the workspace.",
                "Never edit the main checkout, .git, <task>/task.yaml, <task>/events.jsonl, <task>/verification.json, or promotion artifacts.",
                "Stop after writing exactly one terminal evidence artifact.",
                "Dev-Flow verification is required after result.md; worker completion is not promotion readiness.",
            ]

        agents[agent_id] = AgentDefinition(
            id=agent_id,
            provider=provider,
            model=model,
            adapter=adapter,
            adapter_maturity=adapter_maturity(adapter),
            role=role,
            tier=tier,
            default_mode=default_mode,
            execution_mode="automated",
            purpose=f"Automated execution worker that drives {role} tasks using the {provider} provider.",
            workspace="isolated_task_workspace",
            can_see=[
                "task_packet",
                "assigned_workspace",
                "recent_events",
                "verification_plan",
                "verification_summary",
            ],
            can_touch=can_touch,
            cannot_touch=[
                "<main_checkout>/**",
                "<task>/task.yaml",
                "<task>/events.jsonl",
                "<task>/verification.json",
                "<task>/merge-readiness.json",
                ".git/**",
            ],
            allowed_reads=[
                "<task>/packet.json",
                "<task>/events.jsonl",
                "<task>/questions.jsonl",
                f"<task>/agents/{agent_id}/handoff.md",
                "<workspace>/**",
            ],
            allowed_writes=allowed_writes,
            forbidden_writes=forbidden_writes,
            required_outputs=[
                f"On completion, write <task>/agents/{agent_id}/result.md with status, summary, changed files, and suggested verification.",
                f"When blocked, append one blocked_question JSON object to <task>/agents/{agent_id}/questions.jsonl.",
                f"When failed, write <task>/agents/{agent_id}/worker_failed.json with summary, error_type, evidence, and next_safe_action.",
            ],
            completion_rules=comp_rules,
            can_run_shell=False,
            can_use_network=can_use_network,
            can_promote=False,
            enabled=enabled,
        )

    starter_local_profiles = [
        {
            "id": "local-qwopus-inspector",
            "model": "qwopus:latest",
            "role": "local_senior_worker",
            "tier": "strong_local",
            "model_role_name": "qwopus-supervisor",
            "machine_class": "mac_studio",
            "weight_class": "heavy",
            "secondary_roles": ["qwen-local-supervisor", "repo-reasoner", "task-decomposer", "deep-debugger"],
            "purpose": "Inspect bounded Dev-Flow task evidence, architecture risk, and likely next actions without editing files.",
            "use_caution": ["Likely alias of qwen3.6:latest until ollama show proves different templates or parameters."],
            "required_verification_command": "ollama show qwopus:latest",
            "model_alias_group": "qwopus-qwen36-07d35212591f",
            "manifest_notes": ["Heavy Mac Studio local supervisor/planner/repo reasoner."],
            "hermes_delegable": True,
        },
        {
            "id": "local-qwen36-inspector",
            "model": "qwen3.6:latest",
            "role": "local_senior_worker",
            "tier": "strong_local",
            "model_role_name": "qwen-local-supervisor",
            "machine_class": "mac_studio",
            "weight_class": "heavy",
            "secondary_roles": ["qwopus-supervisor", "repo-reasoner", "task-decomposer", "deep-debugger"],
            "purpose": "Inspect bounded Dev-Flow task evidence and provide architecture or risk review; treated as distinct from Qwopus only after real evidence proves it.",
            "use_caution": ["Likely alias of qwopus:latest until ollama show proves different templates or parameters."],
            "required_verification_command": "ollama show qwen3.6:latest",
            "model_alias_group": "qwopus-qwen36-07d35212591f",
            "manifest_notes": ["Current local list reports the same Ollama ID as qwopus:latest."],
            "hermes_delegable": True,
        },
        {
            "id": "local-qwen25-coder-32b-code-reviewer",
            "model": "qwen2.5-coder:32b-instruct",
            "role": "implementation_worker",
            "tier": "premium_local",
            "model_role_name": "qwen-coder-heavy",
            "machine_class": "mac_studio",
            "weight_class": "heavy",
            "secondary_roles": ["heavy-implementer", "debugger", "patch-planner", "test-writer"],
            "purpose": "Provide premium local code review, debugging analysis, and test-writing advice from bounded task packets.",
            "use_caution": ["Use existing patch proposal/review/dry-run/apply gates for any future patch-producing path."],
            "required_verification_command": "ollama show qwen2.5-coder:32b-instruct",
            "manifest_notes": ["Mac Studio heavy coding model, approximately 19 GB in Josh's local fleet."],
            "hermes_delegable": True,
        },
        {
            "id": "local-qwen25-coder-32b-patch-proposer",
            "model": "qwen2.5-coder:32b-instruct",
            "role": "implementation_worker",
            "tier": "premium_local",
            "model_role_name": "qwen-coder-heavy",
            "machine_class": "mac_studio",
            "weight_class": "heavy",
            "secondary_roles": ["heavy-implementer", "patch-planner"],
            "purpose": "Draft patch proposal guidance only; Dev-Flow must use existing patch proposal, review, dry-run, apply, and verification gates.",
            "use_caution": ["Not Hermes-delegable because patch proposal is promotion-adjacent."],
            "required_verification_command": "ollama show qwen2.5-coder:32b-instruct",
            "manifest_notes": ["Registry-visible and dry-run-visible until a safe proposal path is explicitly promoted."],
            "hermes_delegable": False,
        },
        {
            "id": "local-qwen25-coder-14b-test-planner",
            "model": "qwen2.5-coder:14b",
            "role": "implementation_worker",
            "tier": "strong_local",
            "model_role_name": "qwen-coder-medium",
            "machine_class": "either",
            "weight_class": "medium",
            "secondary_roles": ["test-planner", "medium-code-reviewer", "small-debugger"],
            "purpose": "Plan focused tests and smaller debugging/review tasks from bounded task packets.",
            "use_caution": ["Borderline for Mac mini; assign to Mac mini only after observed performance is acceptable."],
            "required_verification_command": "ollama show qwen2.5-coder:14b",
            "manifest_notes": ["Medium model; machine assignment is configurable, not assumed."],
            "hermes_delegable": True,
        },
        {
            "id": "local-qwen25-coder-7b-code-reviewer",
            "model": "qwen2.5-coder:7b-instruct",
            "role": "implementation_worker",
            "tier": "fast_local",
            "model_role_name": "qwen-coder-fast",
            "machine_class": "mac_mini",
            "weight_class": "small",
            "secondary_roles": ["small-patch-helper", "syntax-fixer", "small-test-helper"],
            "purpose": "Provide fast local code review and helper feedback from bounded task packets.",
            "use_caution": ["Keep to small isolated edits, syntax fixes, simple tests, and low-risk implementation loops."],
            "required_verification_command": "ollama show qwen2.5-coder:7b-instruct",
            "manifest_notes": ["Mac mini small-worker class."],
            "hermes_delegable": True,
        },
        {
            "id": "local-qwen25-coder-15b-classifier",
            "model": "qwen2.5-coder:1.5b",
            "role": "implementation_worker",
            "tier": "tiny_local",
            "model_role_name": "qwen-coder-tiny",
            "machine_class": "mac_mini",
            "weight_class": "tiny",
            "secondary_roles": ["classifier", "short-summarizer", "label-suggester", "simple-extractor"],
            "purpose": "Classify task quality, routing hints, and obvious risk from bounded task packets.",
            "use_caution": ["Use only for low-risk structured chores; do not ask it to judge complex code correctness."],
            "required_verification_command": "ollama show qwen2.5-coder:1.5b",
            "manifest_notes": ["Mac mini tiny utility/control-loop worker."],
            "hermes_delegable": True,
        },
        {
            "id": "local-gemma4-summarizer",
            "model": "gemma4:latest",
            "role": "local_senior_worker",
            "tier": "local",
            "model_role_name": "gemma-fast-reviewer",
            "machine_class": "mac_mini",
            "weight_class": "small",
            "secondary_roles": ["gemma-mini-multimodal-reviewer", "handoff-writer", "evidence-brief-writer"],
            "purpose": "Summarize worker evidence, task state, and handoff notes without editing files.",
            "use_caution": ["Do not confuse gemma4:latest with gemma4:31b; Josh's latest manifest identifies gemma4:latest as 8B Q4_K_M."],
            "required_verification_command": "ollama show gemma4:latest",
            "manifest_notes": ["Manifest: architecture gemma4, 8.0B, context 131072, embedding 2560, Q4_K_M, Apache 2.0."],
            "hermes_delegable": True,
        },
        {
            "id": "local-gemma4-doc-reviewer",
            "model": "gemma4:latest",
            "role": "local_senior_worker",
            "tier": "local",
            "model_role_name": "gemma-fast-reviewer",
            "machine_class": "mac_mini",
            "weight_class": "small",
            "secondary_roles": ["gemma-mini-multimodal-reviewer", "docs-reviewer", "handoff-writer"],
            "purpose": "Review documentation, handoffs, and evidence briefs from bounded task packets without editing files.",
            "use_caution": ["Do not confuse gemma4:latest with gemma4:31b; use actual ollama show manifests when available."],
            "required_verification_command": "ollama show gemma4:latest",
            "manifest_notes": ["Mac mini small multimodal/thinking/tool-capable reviewer when manifest supports needed capabilities."],
            "hermes_delegable": True,
        },
        {
            "id": "local-gemma4-31b-dense-judge",
            "model": "gemma4-review:latest",
            "role": "local_senior_worker",
            "tier": "premium_local",
            "model_role_name": "gemma-dense-judge",
            "machine_class": "mac_studio",
            "weight_class": "heavy",
            "secondary_roles": ["strict-reviewer", "final-local-judge", "ux-spec-verifier", "multimodal-artifact-reviewer"],
            "purpose": "Provide strict local final review and goal-satisfaction judgment from bounded task packets.",
            "use_caution": ["Use as a reviewer/judge, not a default implementation worker; tuned alias constrains context to reduce local memory pressure."],
            "required_verification_command": "ollama show gemma4-review:latest",
            "manifest_notes": ["Mac Studio dense 31B Gemma reviewer/judge via local gemma4-review:latest alias from gemma4:31b with num_ctx 32768."],
            "hermes_delegable": True,
        },
    ]

    for profile in starter_local_profiles:
        agents[str(profile["id"])] = AgentDefinition(
            id=profile["id"],
            provider="ollama",
            model=profile["model"],
            adapter="ollama_chat",
            adapter_maturity=adapter_maturity("ollama_chat"),
            role=profile["role"],
            tier=profile["tier"],
            default_mode="read_only",
            execution_mode="automated",
            purpose=profile["purpose"],
            model_role_name=profile["model_role_name"],
            machine_class=profile["machine_class"],
            weight_class=profile["weight_class"],
            secondary_roles=profile["secondary_roles"],
            use_caution=profile["use_caution"],
            required_verification_command=profile["required_verification_command"],
            model_alias_group=profile.get("model_alias_group"),
            manifest_notes=profile["manifest_notes"],
            workspace="isolated_task_workspace",
            can_see=[
                "task_packet",
                "assigned_workspace",
                "recent_events",
                "verification_plan",
                "verification_summary",
            ],
            can_touch=[
                "<task>/local-model-runs/**",
            ],
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
            ],
            allowed_writes=[
                "<task>/local-model-runs/**",
            ],
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
                "Treat any quality score or routing hint as advisory evidence only.",
            ],
            completion_rules=[
                "Do not edit source files or the assigned workspace.",
                "Do not write proposal.patch, apply patches, verify, commit, merge, push, promote, or mutate task canonical state.",
                "Use the local model endpoint only through Dev-Flow's configured local model client boundary.",
                "Worker output is evidence, not truth; human approval controls promotion.",
            ],
            can_run_shell=False,
            can_use_network=False,
            can_promote=False,
            hermes_delegable=bool(profile["hermes_delegable"]),
            enabled=True,
        )

    return agents


def _validate_agent_policy(
    agent: AgentDefinition,
    providers: ProviderRegistry | None = None,
    roles: RoleRegistry | None = None,
) -> list[str]:
    errors: list[str] = []
    prefix = f"agents.{agent.id}"
    
    if agent.can_promote:
        errors.append(f"{prefix}.can_promote must be false")
        if agent.hermes_delegable:
            errors.append(f"{prefix}.hermes_delegable must be false when can_promote is true")

    if agent.hermes_delegable:
        if agent.adapter_maturity == "planned_not_executable" or is_planned_not_executable_adapter(agent.adapter):
            errors.append(f"{prefix}.hermes_delegable must be false for planned_not_executable adapters")
        if agent.default_mode == "workspace_write":
            errors.append(f"{prefix}.hermes_delegable requires a read-only or proposal-only permission mode")
        if agent.can_run_shell or agent.can_use_network:
            errors.append(f"{prefix}.hermes_delegable cannot grant shell or arbitrary network access")
        if any("<workspace>" in path or "proposal.patch" in path for path in agent.allowed_writes):
            errors.append(f"{prefix}.hermes_delegable cannot write workspace files or proposal.patch")
        
    if agent.tier == "frontier" and agent.default_mode == "workspace_write":
        errors.append(f"{prefix}.frontier agents cannot use workspace_write")
        
    if agent.tier == "frontier" and agent.can_run_shell:
        errors.append(f"{prefix}.frontier agents cannot run shell commands")

    # P1 Hardening Validations
    if providers is not None and providers.providers:
        if agent.provider not in providers.providers and agent.provider not in {"manual", "shell", "local"}:
            errors.append(f"{prefix}.provider '{agent.provider}' does not exist in provider registry")
            
    if roles is not None and roles.roles:
        if agent.role not in roles.roles and agent.role not in {"implementation_worker", "senior_developer_worker", "frontier_planner_architect_reviewer"}:
            errors.append(f"{prefix}.role '{agent.role}' does not exist in role registry")

    ALLOWED_ADAPTERS = set(ADAPTER_MATURITY)
    if agent.adapter not in ALLOWED_ADAPTERS:
        errors.append(f"{prefix}.adapter '{agent.adapter}' is unsupported. Allowed: {sorted(list(ALLOWED_ADAPTERS))}")
    elif agent.adapter_maturity is not None and agent.adapter_maturity != adapter_maturity(agent.adapter):
        errors.append(
            f"{prefix}.adapter_maturity '{agent.adapter_maturity}' does not match adapter '{agent.adapter}' maturity '{adapter_maturity(agent.adapter)}'"
        )

    if agent.tier == "frontier" and agent.default_mode not in {"read_only", "frontier_read_only", "manual_packet_only"}:
        errors.append(f"{prefix}.default_mode '{agent.default_mode}' is not compatible with frontier tier")

    for path in agent.can_touch:
        if not (path.startswith("<workspace>/") or path.startswith("<task>/") or path == "<workspace>" or path == "<task>"):
            errors.append(f"{prefix}.can_touch cannot include main checkout path: '{path}'")

    if not any(".git" in path for path in agent.cannot_touch):
        agent.cannot_touch.append(".git/**")

    if agent.tier == "local" and agent.can_use_network:
        errors.append(f"{prefix}.local agents cannot have can_use_network: true")

    if agent.can_run_shell:
        if agent.default_mode != "verify_only" and agent.adapter != "shell":
            errors.append(f"{prefix}.can_run_shell is true but is not aligned with verify_only mode or shell adapter")

    prohibited_path = "/Users/jewelbait/Desktop/DevFlow"
    for field_name in (
        "can_see",
        "can_touch",
        "cannot_touch",
        "allowed_reads",
        "allowed_writes",
        "forbidden_writes",
        "required_outputs",
        "completion_rules",
    ):
        for path in getattr(agent, field_name):
            if prohibited_path in path:
                errors.append(f"{prefix}.{field_name} must not reference quarantined checkout path '{prohibited_path}'")

    return errors


def _registry_version(payload: dict[str, object]) -> int:
    version = payload.get("version", 1)
    return version if isinstance(version, int) else -1


def _read_registry_file(path: Path) -> dict[str, object]:
    return _read_yaml_mapping(path, "registry")


def _read_yaml_mapping(path: Path, label: str) -> dict[str, object]:
    text = path.read_text(encoding="utf-8")
    stripped = text.strip()
    if not stripped:
        return {}
    try:
        payload = yaml.safe_load(stripped)
    except yaml.YAMLError as exc:
        raise AgentRegistryError(path, [f"{label} YAML is invalid: {exc}"]) from exc
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise AgentRegistryError(path, [f"{label} root must be a map"])
    return payload


def _display_path(path: Path) -> str:
    parts = path.parts
    if ".devflow" in parts:
        return "/".join(parts[parts.index(".devflow") :])
    return path.as_posix()
