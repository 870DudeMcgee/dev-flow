from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from devflow.control_room.agent_registry import (
    AgentDefinition,
    ProviderDefinition,
    adapter_execution_refusal,
    adapter_maturity,
    is_executable_agent_runtime,
    is_local_model_worker_pool_agent,
    load_agent_registry,
    load_provider_registry,
)


@dataclass(frozen=True)
class EvidenceContract:
    required_outputs: list[str] = field(default_factory=list)
    optional_outputs: list[str] = field(default_factory=list)
    forbidden_outputs: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ResolvedAgentRuntime:
    agent_id: str
    provider_id: str
    provider: str
    adapter: str
    adapter_maturity: str
    permission_mode: str
    execution_surface: str
    task_run_allowed: bool
    agent_run_allowed: bool
    packet_allowed: bool
    remote_provider: bool
    network_allowed: bool
    can_promote: bool
    refusal_reason: str | None
    next_command: str | None
    evidence_contract: EvidenceContract


LOCAL_PROVIDERS = {"shell", "manual", "ollama", "local"}
PACKET_PERMISSION_MODES = {"manual_packet_only", "read_only", "docs_only", "frontier_read_only"}


def resolve_agent_runtime(root: Path, agent_id: str) -> ResolvedAgentRuntime:
    agent = load_agent_registry(root).require_agent(agent_id)
    provider = _provider_for(root, agent)
    return resolve_agent_runtime_definition(agent, provider)


def resolve_agent_runtime_definition(
    agent: AgentDefinition,
    provider: ProviderDefinition | None = None,
) -> ResolvedAgentRuntime:
    if not agent.enabled:
        execution_surface = "blocked"
        task_run_allowed = False
        agent_run_allowed = False
        packet_allowed = False
        refusal_reason = f"Agent '{agent.id}' is disabled and cannot execute."
        next_command = None
    elif is_local_model_worker_pool_agent(agent, provider=provider):
        execution_surface = "agent_run"
        task_run_allowed = False
        agent_run_allowed = True
        packet_allowed = True
        refusal_reason = (
            f"Agent '{agent.id}' is a read-only local model worker-pool profile. "
            f"Run it with 'devflow agent run --task <task-id> --profile {agent.id} --json', "
            "not task worker adapter execution."
        )
        next_command = f"devflow agent run --task <task-id> --profile {agent.id} --json"
    elif is_executable_agent_runtime(agent, provider=provider):
        execution_surface = "task_run"
        task_run_allowed = True
        agent_run_allowed = False
        packet_allowed = True
        refusal_reason = None
        if agent.adapter == "shell":
            next_command = f"devflow task run <task-id> --worker {agent.id} -- <command>"
        else:
            next_command = f"devflow task run <task-id> --worker {agent.id}"
    elif agent.default_mode == "manual_packet_only" or agent.adapter == "manual_packet":
        execution_surface = "packet_only"
        task_run_allowed = False
        agent_run_allowed = False
        packet_allowed = True
        refusal_reason = (
            f"Agent '{agent.id}' is packet-only and cannot execute. "
            "Create a handoff packet instead of using task worker adapter execution."
        )
        next_command = f"devflow agent packet <task-id> {agent.id}"
    else:
        execution_surface = "blocked"
        task_run_allowed = False
        agent_run_allowed = False
        packet_allowed = agent.default_mode in PACKET_PERMISSION_MODES
        refusal_reason = adapter_execution_refusal(agent.adapter, agent_id=agent.id)
        next_command = None

    return ResolvedAgentRuntime(
        agent_id=agent.id,
        provider_id=agent.provider,
        provider=provider.provider if provider else agent.provider,
        adapter=agent.adapter,
        adapter_maturity=agent.adapter_maturity or adapter_maturity(agent.adapter),
        permission_mode=agent.default_mode,
        execution_surface=execution_surface,
        task_run_allowed=task_run_allowed,
        agent_run_allowed=agent_run_allowed,
        packet_allowed=packet_allowed,
        remote_provider=agent.provider not in LOCAL_PROVIDERS,
        network_allowed=agent.can_use_network,
        can_promote=agent.can_promote,
        refusal_reason=refusal_reason,
        next_command=next_command,
        evidence_contract=EvidenceContract(
            required_outputs=_required_evidence_outputs(agent),
            optional_outputs=list(agent.allowed_writes),
            forbidden_outputs=list(agent.forbidden_writes or agent.cannot_touch),
        ),
    )


def agent_runtime_contract(root: Path, agent: AgentDefinition) -> dict[str, Any]:
    provider = _provider_for(root, agent)
    return runtime_contract_payload(resolve_agent_runtime_definition(agent, provider))


def runtime_contract_payload(runtime: ResolvedAgentRuntime) -> dict[str, Any]:
    return {
        "execution_surface": runtime.execution_surface,
        "task_run_allowed": runtime.task_run_allowed,
        "agent_run_allowed": runtime.agent_run_allowed,
        "packet_allowed": runtime.packet_allowed,
        "refusal_reason": runtime.refusal_reason,
        "next_command": runtime.next_command,
        "evidence_contract": {
            "required_outputs": runtime.evidence_contract.required_outputs,
            "optional_outputs": runtime.evidence_contract.optional_outputs,
            "forbidden_outputs": runtime.evidence_contract.forbidden_outputs,
        },
    }


def _required_evidence_outputs(agent: AgentDefinition) -> list[str]:
    required = list(agent.required_outputs)
    for path in agent.allowed_writes:
        if path.endswith("/proposal.patch") or path.endswith("/result.md") or path == "<task>/local-model-runs/**":
            if path not in required:
                required.append(path)
    return required


def _provider_for(root: Path, agent: AgentDefinition) -> ProviderDefinition | None:
    try:
        return load_provider_registry(root).providers.get(agent.provider)
    except Exception:
        return None
