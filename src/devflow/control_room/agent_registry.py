from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError


AgentPermissionMode = Literal[
    "read_only",
    "workspace_write",
    "verify_only",
    "docs_only",
    "frontier_read_only",
    "manual_packet_only",
]


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
    role: str
    tier: str
    default_mode: AgentPermissionMode
    execution_mode: str = "automated"
    purpose: str | None = None
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
    text = path.read_text(encoding="utf-8")
    stripped = text.strip()
    if not stripped:
        return {}
    if stripped.startswith("{"):
        payload = json.loads(stripped)
        if not isinstance(payload, dict):
            raise AgentRegistryError(path, ["provider root must be a map"])
        return payload
    return _parse_flat_yaml(text)


def _parse_flat_yaml(text: str) -> dict[str, object]:
    lines = [
        (len(raw) - len(raw.lstrip(" ")), raw.strip())
        for raw in text.splitlines()
        if raw.strip() and not raw.lstrip().startswith("#")
    ]
    data: dict[str, object] = {}
    for indent, line in lines:
        if indent == 0 and ":" in line:
            key, value = line.split(":", 1)
            data[key.strip()] = _parse_scalar(value.strip())
    return data


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
    text = path.read_text(encoding="utf-8")
    stripped = text.strip()
    if not stripped:
        return {}
    if stripped.startswith("{"):
        payload = json.loads(stripped)
        if not isinstance(payload, dict):
            raise AgentRegistryError(path, ["roles root must be a map"])
        return payload
    return _parse_yaml_subset_roles(text)


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


def _parse_yaml_subset_roles(text: str) -> dict[str, object]:
    lines = [
        (len(raw) - len(raw.lstrip(" ")), raw.strip())
        for raw in text.splitlines()
        if raw.strip() and not raw.lstrip().startswith("#")
    ]
    data: dict[str, object] = {}
    index = 0
    while index < len(lines):
        indent, line = lines[index]
        if indent != 0 or ":" not in line:
            index += 1
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if key == "roles" and value == "":
            roles, index = _parse_roles_block(lines, index + 1)
            data[key] = roles
            continue
        data[key] = _parse_scalar(value)
        index += 1
    return data


def _parse_roles_block(
    lines: list[tuple[int, str]],
    index: int,
) -> tuple[dict[str, dict[str, object]], int]:
    roles: dict[str, dict[str, object]] = {}
    while index < len(lines):
        indent, line = lines[index]
        if indent < 2:
            break
        if indent != 2 or not line.endswith(":"):
            index += 1
            continue
        role_id = line[:-1].strip()
        role_data, index = _parse_role_fields(lines, index + 1)
        roles[role_id] = role_data
    return roles, index


def _parse_role_fields(
    lines: list[tuple[int, str]],
    index: int,
) -> tuple[dict[str, object], int]:
    role_data: dict[str, object] = {}
    while index < len(lines):
        indent, line = lines[index]
        if indent < 4:
            break
        if indent != 4 or ":" not in line:
            index += 1
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        role_data[key] = _parse_scalar(value)
        index += 1
    return role_data, index


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
    return {proof_agent.id: proof_agent}


def _validate_agent_policy(
    agent: AgentDefinition,
    providers: ProviderRegistry | None = None,
    roles: RoleRegistry | None = None,
) -> list[str]:
    errors: list[str] = []
    prefix = f"agents.{agent.id}"
    
    if agent.can_promote:
        errors.append(f"{prefix}.can_promote must be false")
        
    if agent.tier == "frontier" and agent.default_mode == "workspace_write":
        errors.append(f"{prefix}.frontier agents cannot use workspace_write")
        
    if agent.tier == "frontier" and agent.can_run_shell:
        errors.append(f"{prefix}.frontier agents cannot run shell commands")

    # P1 Hardening Validations
    if providers is not None and providers.providers:
        if agent.provider not in providers.providers:
            errors.append(f"{prefix}.provider '{agent.provider}' does not exist in provider registry")
            
    if roles is not None and roles.roles:
        if agent.role not in roles.roles:
            errors.append(f"{prefix}.role '{agent.role}' does not exist in role registry")

    ALLOWED_ADAPTERS = {"shell", "manual", "ollama_chat", "openai_responses", "openai_compatible", "anthropic_messages", "manual_packet", "gemini", "openai_chat"}
    if agent.adapter not in ALLOWED_ADAPTERS:
        errors.append(f"{prefix}.adapter '{agent.adapter}' is unsupported. Allowed: {sorted(list(ALLOWED_ADAPTERS))}")

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

    return errors


def _registry_version(payload: dict[str, object]) -> int:
    version = payload.get("version", 1)
    return version if isinstance(version, int) else -1


def _read_registry_file(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8")
    stripped = text.strip()
    if not stripped:
        return {}
    if stripped.startswith("{"):
        payload = json.loads(stripped)
        if not isinstance(payload, dict):
            raise AgentRegistryError(path, ["registry root must be a map"])
        return payload
    return _parse_yaml_subset(text)


def _parse_yaml_subset(text: str) -> dict[str, object]:
    lines = [
        (len(raw) - len(raw.lstrip(" ")), raw.strip())
        for raw in text.splitlines()
        if raw.strip() and not raw.lstrip().startswith("#")
    ]
    data: dict[str, object] = {}
    index = 0
    while index < len(lines):
        indent, line = lines[index]
        if indent != 0 or ":" not in line:
            index += 1
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if key == "agents" and value == "":
            agents, index = _parse_agents_block(lines, index + 1)
            data[key] = agents
            continue
        data[key] = _parse_scalar(value)
        index += 1
    return data


def _parse_agents_block(
    lines: list[tuple[int, str]],
    index: int,
) -> tuple[dict[str, dict[str, object]], int]:
    agents: dict[str, dict[str, object]] = {}
    while index < len(lines):
        indent, line = lines[index]
        if indent < 2:
            break
        if indent != 2 or not line.endswith(":"):
            index += 1
            continue
        agent_id = line[:-1].strip()
        agent_data, index = _parse_agent_fields(lines, index + 1)
        agents[agent_id] = agent_data
    return agents, index


def _parse_agent_fields(
    lines: list[tuple[int, str]],
    index: int,
) -> tuple[dict[str, object], int]:
    agent_data: dict[str, object] = {}
    while index < len(lines):
        indent, line = lines[index]
        if indent < 4:
            break
        if indent != 4 or ":" not in line:
            index += 1
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if value == "":
            values, index = _parse_list(lines, index + 1)
            agent_data[key] = values
            continue
        agent_data[key] = _parse_scalar(value)
        index += 1
    return agent_data, index


def _parse_list(lines: list[tuple[int, str]], index: int) -> tuple[list[object], int]:
    values: list[object] = []
    while index < len(lines):
        indent, line = lines[index]
        if indent < 6 or not line.startswith("- "):
            break
        values.append(_parse_scalar(line[2:].strip()))
        index += 1
    return values, index


def _parse_scalar(value: str) -> object:
    if value == "":
        return {}
    if value == "[]":
        return []
    if value == "true":
        return True
    if value == "false":
        return False
    try:
        return int(value)
    except ValueError:
        return _strip_yaml_quotes(value)


def _strip_yaml_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def _display_path(path: Path) -> str:
    parts = path.parts
    if ".devflow" in parts:
        return "/".join(parts[parts.index(".devflow") :])
    return path.as_posix()
