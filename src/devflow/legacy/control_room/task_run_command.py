from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from devflow.legacy.control_room.agent_registry import AgentDefinition, load_agent_registry
from devflow.legacy.control_room.models import TaskRecord
from devflow.legacy.control_room.paths import relative_path
from devflow.legacy.control_room.project_registry import project_task_ref
from devflow.legacy.control_room.service import run_shell_task
from devflow.legacy.control_room.worker_adapter import UnsupportedWorkerAdapter, get_worker_adapter


TRUSTED_LOCAL_WARNING = "Security: shell execution is path-isolated, not sandboxed; run only trusted local commands."


class TaskRunCommandError(RuntimeError):
    def __init__(self, message: str | None = None, *, lines: Iterable[str] | None = None, exit_code: int = 1) -> None:
        rendered_lines = list(lines or ([message] if message else []))
        super().__init__(message or "\n".join(rendered_lines))
        self.lines = tuple(rendered_lines)
        self.exit_code = exit_code


@dataclass(frozen=True)
class TaskRunCommandResult:
    root: Path
    task_id: str
    command: tuple[str, ...]
    worker_adapter: str
    timeout_seconds: int
    task: TaskRecord
    lines: tuple[str, ...]
    exit_code: int
    project_id: str | None = None


def run_task_command(
    root: Path,
    task_id: str,
    command: list[str],
    *,
    worker_adapter: str = "shell",
    timeout_seconds: int = 60,
    project_id: str | None = None,
) -> TaskRunCommandResult:
    root = Path(root)
    lines = _worker_warning_lines(worker_adapter)
    registry = load_agent_registry(root)
    selected_agent = registry.agents.get(worker_adapter)

    if _is_registry_backed_ollama_patch_worker(selected_agent):
        lines.extend(_registry_backed_ollama_patch_worker_note_lines())

    if worker_adapter not in registry.agents:
        try:
            get_worker_adapter(worker_adapter)
        except UnsupportedWorkerAdapter as exc:
            raise TaskRunCommandError(str(exc), lines=[*lines, str(exc)], exit_code=1) from exc

    try:
        task = run_shell_task(
            root,
            task_id,
            command,
            timeout_seconds=timeout_seconds,
            worker_adapter=worker_adapter,
        )
    except (KeyError, ValueError) as exc:
        raise TaskRunCommandError(str(exc), lines=[*lines, str(exc)], exit_code=1) from exc

    lines.extend(_task_run_status_lines(root, task, worker_adapter=worker_adapter, project_id=project_id))
    if _is_registry_backed_ollama_patch_worker(selected_agent):
        lines.extend(_registry_patch_worker_evidence_lines(root, task.id, worker_adapter))
    lines.extend(_task_run_followup_lines(root, task, worker_adapter=worker_adapter, selected_agent=selected_agent))

    return TaskRunCommandResult(
        root=root,
        task_id=task.id,
        command=tuple(command),
        worker_adapter=worker_adapter,
        timeout_seconds=timeout_seconds,
        task=task,
        lines=tuple(lines),
        exit_code=_task_exit_code(task),
        project_id=project_id,
    )


def render_task_run_lines(result: TaskRunCommandResult) -> list[str]:
    return list(result.lines)


def _worker_warning_lines(worker_adapter: str) -> list[str]:
    if worker_adapter == "manual":
        return ["Warning: 'manual' worker is experimental and does not execute work."]
    if worker_adapter == "shell":
        return [TRUSTED_LOCAL_WARNING]
    return []


def _is_registry_backed_ollama_patch_worker(agent: AgentDefinition | None) -> bool:
    return agent is not None and agent.provider == "ollama" and agent.adapter == "ollama_chat"


def _registry_backed_ollama_patch_worker_note_lines() -> list[str]:
    return [
        "worker_mode: registry_backed_local_ollama_patch_worker",
        "worker_note: writes proposal.patch evidence only; Dev-Flow applies patches separately and verifies separately.",
    ]


def _task_run_status_lines(
    root: Path,
    task: TaskRecord,
    *,
    worker_adapter: str,
    project_id: str | None,
) -> list[str]:
    lines = [f"{project_task_ref(task.id, project_id)}: {task.status}"]
    if project_id:
        lines.append(f"project_root: {root}")
    lines.append(f"log_path: {task.log_path}")
    lines.append(f"result_path: {task.result_path}")

    handoff_path = root / ".devflow" / "tasks" / task.id / "agents" / worker_adapter / "handoff.md"
    if handoff_path.exists():
        lines.append(f"manual_handoff_path: {relative_path(root, handoff_path)}")

    return lines


def _registry_patch_worker_evidence_lines(root: Path, task_id: str, agent_id: str) -> list[str]:
    agent_dir = root / ".devflow" / "tasks" / task_id / "agents" / agent_id
    return [
        f"agent_packet_path: {relative_path(root, agent_dir / 'packet.json')}",
        f"raw_output_path: {relative_path(root, agent_dir / 'raw_output.md')}",
        f"proposal_patch_path: {relative_path(root, agent_dir / 'proposal.patch')}",
        f"run_metadata_path: {relative_path(root, agent_dir / 'run.json')}",
        f"agent_result_path: {relative_path(root, agent_dir / 'result.md')}",
        f"agent_log_path: {relative_path(root, agent_dir / 'logs' / 'worker.log')}",
    ]


def _task_run_followup_lines(
    root: Path,
    task: TaskRecord,
    *,
    worker_adapter: str,
    selected_agent: AgentDefinition | None,
) -> list[str]:
    lines = []
    if task.latest_log_line:
        lines.append(f"latest_log_line: {task.latest_log_line}")
    if _is_registry_backed_ollama_patch_worker(selected_agent) and task.status == "complete":
        lines.append(f"suggested_next_action: devflow task review-patch {task.id} --agent {worker_adapter}")
    return lines


def _task_exit_code(task: TaskRecord) -> int:
    if task.status == "complete":
        return 0
    return task.last_exit_code if task.last_exit_code is not None else 1
