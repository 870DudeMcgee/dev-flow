from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from devflow.control_room import agent_registry, estimator, router, service as task_service, worker_adapter


@dataclass(frozen=True)
class TaskAutoRunCommandResult:
    lines: tuple[str, ...]
    exit_code: int


def run_task_auto_run_command(
    root: Path,
    task_id: str,
    *,
    dry_run: bool = False,
    project_id: str | None = None,
    project_option: str = "",
) -> TaskAutoRunCommandResult:
    root = Path(root)
    lines: list[str] = []

    fit_data = estimator.estimate_task_fit(root, task_id)
    task_fit = fit_data.get("task_fit", {})
    estimator.save_task_fit(root, task_id, fit_data)
    archetype_id = task_fit.get("archetype_id", "unknown")
    context_estimate = fit_data.get("repo_scan", {}).get("total_context_estimate", 0)
    requires_vision = task_fit.get("requires_vision", False)
    requires_thinking = task_fit.get("requires_thinking", "optional")

    lines.extend(
        [
            f"task_id: {task_id}",
            f"archetype: {archetype_id}",
            f"context_estimate: {context_estimate} tokens",
            f"requires_vision: {requires_vision}",
            f"requires_thinking: {requires_thinking}",
            "---",
        ]
    )

    decision_data = router.route_task(root, task_id, project_id=project_id)
    router.save_routing_decision(root, task_id, decision_data)
    routing_decision = decision_data.get("routing_decision", {})
    selected = routing_decision.get("selected", {})
    worker_id = selected.get("worker") if isinstance(selected, dict) else None
    reasons = routing_decision.get("reason", [])
    unresolved = routing_decision.get("unresolved", [])

    if worker_id:
        lines.append(f"selected_worker: {worker_id}")
        for reason in reasons:
            if "score=" in reason or "tuned" in reason or "selected:" in reason:
                lines.append(f"  reason: {reason}")
        for item in unresolved:
            lines.append(f"  unresolved: {item.get('role')} - {item.get('reason', '')}")
    else:
        lines.append("no eligible worker selected")
        for item in unresolved:
            lines.append(f"  unresolved: {item.get('role')} - {item.get('reason', '')}")
        return TaskAutoRunCommandResult(lines=tuple(lines), exit_code=0 if dry_run else 1)

    if dry_run:
        lines.extend(
            [
                "---",
                f"Dry-run mode — to execute: devflow task run {task_id}{project_option} --worker {worker_id}",
            ]
        )
        return TaskAutoRunCommandResult(lines=tuple(lines), exit_code=0)

    lines.extend(
        [
            "---",
            f"Executing worker: {worker_id}",
        ]
    )

    registry = agent_registry.load_agent_registry(root)
    selected_agent = registry.agents.get(worker_id)
    is_registry_backed_ollama = (
        selected_agent is not None
        and selected_agent.provider == "ollama"
        and selected_agent.adapter == "ollama_chat"
    )

    if is_registry_backed_ollama:
        lines.extend(
            [
                "worker_mode: registry_backed_local_ollama_patch_worker",
                "worker_note: writes proposal.patch evidence only; "
                "Dev-Flow applies patches separately and verifies separately.",
            ]
        )

    valid_agents = list(registry.agents.keys())
    valid_adapters_list = worker_adapter.list_worker_adapters()
    if worker_id not in valid_agents and worker_id not in valid_adapters_list:
        try:
            worker_adapter.get_worker_adapter(worker_id)
        except worker_adapter.UnsupportedWorkerAdapter as exc:
            lines.append(str(exc))
            return TaskAutoRunCommandResult(lines=tuple(lines), exit_code=1)

    try:
        task = task_service.run_shell_task(root, task_id, [], worker_adapter=worker_id)
    except (KeyError, ValueError) as exc:
        lines.append(str(exc))
        return TaskAutoRunCommandResult(lines=tuple(lines), exit_code=1)

    lines.extend(
        [
            f"status: {task.status}",
            f"log_path: {task.log_path}",
        ]
    )
    if task.latest_log_line:
        lines.append(f"latest_log_line: {task.latest_log_line}")

    if is_registry_backed_ollama and task.status == "complete":
        lines.append(f"suggested_next_action: devflow task review-patch {task.id} --agent {worker_id}")

    exit_code = 0 if task.status == "complete" else (task.last_exit_code if task.last_exit_code is not None else 1)
    return TaskAutoRunCommandResult(lines=tuple(lines), exit_code=exit_code)
