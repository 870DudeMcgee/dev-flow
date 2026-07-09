from __future__ import annotations

import json
import shlex
from pathlib import Path

from devflow.legacy.control_room.agent_registry import AgentDefinition, ProviderDefinition
from devflow.legacy.control_room.agent_registry import load_agent_registry, load_provider_registry
from devflow.legacy.control_room.agent_runtime import resolve_agent_runtime_definition
from devflow.legacy.control_room.git_worktree import is_git_worktree_task, refresh_git_worker_evidence, worker_id_for_task
from devflow.legacy.control_room.locks import task_mutation_lock
from devflow.legacy.control_room.models import TaskRecord, WorkerInput, WorkerResult
from devflow.legacy.control_room.paths import relative_path, task_dir
from devflow.legacy.control_room.persistence import atomic_write_text, get_task, utc_now
from devflow.legacy.control_room.task_command_safety import looks_destructive_command
from devflow.legacy.control_room.task_lifecycle import record_task_update
from devflow.legacy.control_room.task_workspace import validated_task_workspace
from devflow.legacy.control_room.worker_adapter import get_worker_adapter


def run_task_worker(
    root: Path,
    task_id: str,
    command: list[str],
    timeout_seconds: int = 60,
    worker_adapter: str = "shell",
    env: dict[str, str] | None = None,
) -> TaskRecord:
    agent, provider, resolved_adapter_name = _resolve_worker_runtime(root, worker_adapter)
    adapter = get_worker_adapter(resolved_adapter_name, agent=agent, provider=provider)
    command = _effective_command(command, worker_adapter, resolved_adapter_name)

    if looks_destructive_command(command):
        _refuse_destructive_command(root, task_id, command)

    with task_mutation_lock(root, task_id, "run"):
        task = get_task(root, task_id)
        task_path = task_dir(root, task_id)
        workspace = validated_task_workspace(root, task)

        worker_input = _build_worker_input(
            root,
            task,
            command,
            timeout_seconds=timeout_seconds,
            agent=agent,
            env=env,
            workspace=workspace,
        )

        _mark_worker_started(root, task, command, timeout_seconds=timeout_seconds, worker_adapter=worker_adapter)
        _write_worker_packet(root, task_id, task_path, agent)

        result = adapter.run(worker_input)
        if resolved_adapter_name not in {"manual", "ollama_chat"}:
            _write_result_evidence(task_id, command, result)
        if agent is not None:
            _write_agent_directory_compatibility(task_path, worker_input.log_file)

        return _mark_worker_finished(root, task, result, worker_input.log_file, worker_input.result_file)


def _resolve_worker_runtime(
    root: Path,
    worker_adapter: str,
) -> tuple[AgentDefinition | None, ProviderDefinition | None, str]:
    registry = load_agent_registry(root)
    providers = load_provider_registry(root)

    agent = None
    provider = None
    resolved_adapter_name = worker_adapter

    if worker_adapter in registry.agents:
        agent = registry.require_agent(worker_adapter)
        if not agent.enabled:
            raise ValueError(f"Agent '{worker_adapter}' is disabled.")
        resolved_adapter_name = agent.adapter
        provider = providers.providers.get(agent.provider)
        runtime = resolve_agent_runtime_definition(agent, provider)
        if not runtime.task_run_allowed:
            raise ValueError(runtime.refusal_reason or f"Agent '{agent.id}' cannot execute through task run.")

    return agent, provider, resolved_adapter_name


def _effective_command(command: list[str], worker_adapter: str, resolved_adapter_name: str) -> list[str]:
    if not command and resolved_adapter_name not in {"manual", "ollama_chat"}:
        raise ValueError("Shell worker requires a command after '--'.")
    if not command and resolved_adapter_name == "manual":
        return ["manual-handoff", worker_adapter]
    return list(command)


def _refuse_destructive_command(root: Path, task_id: str, command: list[str]) -> None:
    with task_mutation_lock(root, task_id, "run"):
        task = get_task(root, task_id)
        record_task_update(
            root,
            task,
            event_type="command_refused",
            event_payload={"command": command},
            status="blocked",
            updated_at=utc_now(),
            write_readiness=False,
        )
    raise ValueError("Refusing obviously destructive command for MVP shell worker.")


def _build_worker_input(
    root: Path,
    task: TaskRecord,
    command: list[str],
    *,
    timeout_seconds: int,
    agent: AgentDefinition | None,
    env: dict[str, str] | None,
    workspace: Path,
) -> WorkerInput:
    task_path = task_dir(root, task.id)
    log_file = task_path / "logs" / "worker.log"
    result_file = task_path / "result.md"

    if agent is not None:
        agent_dir = task_path / "agents" / agent.id
        agent_dir.mkdir(parents=True, exist_ok=True)
        (agent_dir / "logs").mkdir(parents=True, exist_ok=True)
        log_file = agent_dir / "logs" / "worker.log"
        result_file = agent_dir / "result.md"

    return WorkerInput(
        task_id=task.id,
        repo_root=root,
        workspace_path=workspace,
        task_file=task_path / "task.yaml",
        context_file=task_path / "events.jsonl",
        status_file=task_path / "task.yaml",
        questions_file=task_path / "questions.jsonl",
        result_file=result_file,
        log_file=log_file,
        command=command,
        env={**(env or {}), **({"DEVFLOW_AGENT_ID": agent.id} if agent is not None else {})},
        timeout_seconds=timeout_seconds,
    )


def _mark_worker_started(
    root: Path,
    task: TaskRecord,
    command: list[str],
    *,
    timeout_seconds: int,
    worker_adapter: str,
) -> None:
    task.worker = worker_adapter
    task.timeout_seconds = timeout_seconds
    task.worker_command = shlex.join(command)
    task.started_at = utc_now()
    record_task_update(
        root,
        task,
        event_type="worker_started",
        event_payload={"command": command, "cwd": task.workspace},
        status="running",
        updated_at=task.started_at,
        write_readiness=False,
    )


def _write_worker_packet(
    root: Path,
    task_id: str,
    task_path: Path,
    agent: AgentDefinition | None,
) -> None:
    if agent is not None:
        from devflow.legacy.control_room.task_packet import build_agent_packet

        agent_packet = build_agent_packet(task_id, agent, root=root)
        agent_packet_json = json.dumps(agent_packet.model_dump(mode="json"), sort_keys=True, indent=2) + "\n"
        atomic_write_text(task_path / "agents" / agent.id / "packet.json", agent_packet_json)
        atomic_write_text(task_path / "packet.json", agent_packet_json)
        return

    from devflow.legacy.control_room.task_packet import build_task_packet

    packet = build_task_packet(task_id, root=root)
    packet_json = json.dumps(packet.model_dump(mode="json"), sort_keys=True, indent=2) + "\n"
    atomic_write_text(task_path / "packet.json", packet_json)


def _write_result_evidence(task_id: str, command: list[str], result: WorkerResult) -> None:
    command_text = " ".join(command)
    body = (
        f"# Result: {task_id}\n\n"
        f"## Summary\n\n{result.summary}\n\n"
        f"## Status\n\n{result.status}\n\n"
        f"## Command\n\n```bash\n{command_text}\n```\n\n"
        f"## Exit Code\n\n{result.exit_code if result.exit_code is not None else 'none'}\n\n"
        f"## Log\n\n{result.log_file}\n"
    )
    atomic_write_text(result.result_file, body)


def _write_agent_directory_compatibility(task_path: Path, log_file: Path) -> None:
    compat_log = task_path / "logs" / "worker.log"
    compat_log.write_text(log_file.read_text(encoding="utf-8"), encoding="utf-8")


def _mark_worker_finished(
    root: Path,
    task: TaskRecord,
    result: WorkerResult,
    log_file: Path,
    result_file: Path,
) -> TaskRecord:
    task.last_exit_code = result.exit_code
    task.latest_log_line = result.latest_log_line
    task.log_path = relative_path(root, log_file)
    task.result_path = relative_path(root, result_file) if result_file.exists() else None
    task.finished_at = utc_now()
    if is_git_worktree_task(task):
        state = refresh_git_worker_evidence(root, task, worker_id=worker_id_for_task(task))
        task.workspace_dirty = bool(state["dirty"])
    record_task_update(
        root,
        task,
        event_type="worker_finished",
        event_payload={"status": result.status, "exit_code": result.exit_code, "log_path": task.log_path},
        status=result.status,
        updated_at=task.finished_at,
    )
    return task
