from __future__ import annotations

from typing import Protocol

from devflow.control_room.models import WorkerInput, WorkerResult
from devflow.control_room.shell_worker import ShellWorkerAdapter


class WorkerAdapter(Protocol):
    """Execution-only adapter contract; Dev-Flow owns state, verification, and promotion."""

    name: str

    def run(self, worker_input: WorkerInput) -> WorkerResult:
        """Run inside a validated workspace using Dev-Flow-owned log/result paths."""
        ...


class UnsupportedWorkerAdapter(ValueError):
    pass


def get_worker_adapter(name: str) -> WorkerAdapter:
    if name == ShellWorkerAdapter.name:
        return ShellWorkerAdapter()
    raise UnsupportedWorkerAdapter(
        f"Unsupported worker adapter '{name}'. Only 'shell' is available in the MVP."
    )