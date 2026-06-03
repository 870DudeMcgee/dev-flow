from __future__ import annotations

from typing import Protocol

from devflow.control_room.models import WorkerInput, WorkerResult
from devflow.control_room.shell_worker import ShellWorkerAdapter
from devflow.control_room.manual_worker import ManualWorkerAdapter
from devflow.control_room.ollama_worker import OllamaChatWorkerAdapter
from devflow.control_room.openai_compatible_worker import OpenAICompatibleWorkerAdapter
from devflow.control_room.anthropic_worker import AnthropicMessagesWorkerAdapter
from devflow.control_room.gemini_worker import GeminiWorkerAdapter
from devflow.control_room.openai_chat_worker import OpenAIChatWorkerAdapter
from devflow.control_room.agent_registry import (
    AgentDefinition,
    ProviderDefinition,
    adapter_execution_refusal,
    is_executable_agent_runtime,
    is_experimental_readonly_adapter,
    is_local_model_worker_pool_agent,
    is_local_patch_runtime_adapter,
    is_stable_runtime_adapter,
)


class WorkerAdapter(Protocol):
    """Execution-only adapter contract; Dev-Flow owns state, verification, and promotion."""

    name: str

    def run(self, worker_input: WorkerInput) -> WorkerResult:
        """Run inside a validated workspace using Dev-Flow-owned log/result paths."""
        ...


_STABLE_RUNTIME_REGISTRY: dict[str, type[WorkerAdapter]] = {
    "shell": ShellWorkerAdapter,
    "manual": ManualWorkerAdapter,
}

_LOCAL_PATCH_RUNTIME_REGISTRY: dict[str, type[WorkerAdapter]] = {
    "ollama_chat": OllamaChatWorkerAdapter,
}

_EXPERIMENTAL_PROVIDER_REGISTRY: dict[str, type[WorkerAdapter]] = {
    "openai_compatible": OpenAICompatibleWorkerAdapter,
    "anthropic_messages": AnthropicMessagesWorkerAdapter,
    "gemini": GeminiWorkerAdapter,
    "openai_chat": OpenAIChatWorkerAdapter,
}

_REGISTRY: dict[str, type[WorkerAdapter]] = {
    **_STABLE_RUNTIME_REGISTRY,
    **_LOCAL_PATCH_RUNTIME_REGISTRY,
    **_EXPERIMENTAL_PROVIDER_REGISTRY,
}


for _adapter_name in _STABLE_RUNTIME_REGISTRY:
    if not is_stable_runtime_adapter(_adapter_name):
        raise RuntimeError(f"Adapter '{_adapter_name}' is registered as stable runtime but is not stable_runtime.")
for _adapter_name in _LOCAL_PATCH_RUNTIME_REGISTRY:
    if not is_local_patch_runtime_adapter(_adapter_name):
        raise RuntimeError(
            f"Adapter '{_adapter_name}' is registered as local patch runtime but is not local_patch_runtime."
        )
for _adapter_name in _EXPERIMENTAL_PROVIDER_REGISTRY:
    if not is_experimental_readonly_adapter(_adapter_name):
        raise RuntimeError(
            f"Adapter '{_adapter_name}' is registered as experimental provider but is not experimental_readonly."
        )


class UnsupportedWorkerAdapter(ValueError):
    pass


def list_worker_adapters() -> list[str]:
    """Return sorted registered worker adapter names."""
    return sorted(_REGISTRY.keys())


def get_worker_adapter(
    name: str,
    *,
    agent: AgentDefinition | None = None,
    provider: ProviderDefinition | None = None,
) -> WorkerAdapter:
    if agent is None:
        if not is_stable_runtime_adapter(name):
            raise UnsupportedWorkerAdapter(adapter_execution_refusal(name))
    elif is_local_model_worker_pool_agent(agent, provider=provider):
        raise UnsupportedWorkerAdapter(
            f"Agent '{agent.id}' is a read-only local model worker-pool profile. "
            "Run it with 'devflow agent run --task <task-id> --profile <profile-id>', not task worker adapter execution."
        )
    elif not is_executable_agent_runtime(agent, provider=provider):
        raise UnsupportedWorkerAdapter(adapter_execution_refusal(name, agent_id=agent.id))
    adapter_cls = _REGISTRY.get(name)
    if adapter_cls is not None:
        return adapter_cls()
    available = ", ".join(list_worker_adapters())
    raise UnsupportedWorkerAdapter(
        f"Unsupported worker adapter '{name}'. Available adapters: {available}."
    )
