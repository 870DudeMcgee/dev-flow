from __future__ import annotations

from typing import Protocol

from devflow.control_room.models import WorkerInput, WorkerResult
from devflow.control_room.shell_worker import ShellWorkerAdapter
from devflow.control_room.manual_worker import ManualWorkerAdapter


class WorkerAdapter(Protocol):
    """Execution-only adapter contract; Dev-Flow owns state, verification, and promotion."""

    name: str

    def run(self, worker_input: WorkerInput) -> WorkerResult:
        """Run inside a validated workspace using Dev-Flow-owned log/result paths."""
        ...


_REGISTRY: dict[str, type[WorkerAdapter]] = {
    "shell": ShellWorkerAdapter,
    "manual": ManualWorkerAdapter,
}


class UnsupportedWorkerAdapter(ValueError):
    pass


def list_worker_adapters() -> list[str]:
    """Return sorted registered worker adapter names."""
    return sorted(_REGISTRY.keys())


def get_worker_adapter(name: str) -> WorkerAdapter:
    adapter_cls = _REGISTRY.get(name)
    if adapter_cls is not None:
        return adapter_cls()
    available = ", ".join(list_worker_adapters())
    raise UnsupportedWorkerAdapter(
        f"Unsupported worker adapter '{name}'. Available adapters: {available}."
    )