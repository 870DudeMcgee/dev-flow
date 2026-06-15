from __future__ import annotations

import shlex
import json
import hashlib
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from devflow.control_room.models import TASK_SCHEMA_VERSION, TaskRecord, WorkerInput, WorkerResult
from devflow.control_room.locks import TASK_LOCK_STALE_AFTER_SECONDS, task_mutation_lock
from devflow.control_room.paths import (
    absolute_path,
    relative_path,
    config_path,
    devflow_dir,
    system_dir,
    system_events_path,
    task_dir,
    task_worker_dir,
    tasks_dir,
    worktree_path,
    workspaces_dir,
)
from devflow.control_room.git_worktree import (
    GitWorktreeError,
    build_git_promotion_preview,
    create_git_worktree,
    git_branch_sharing_checks,
    git_doctor_checks,
    git_worktree_readiness_errors,
    is_git_worktree_task,
    refresh_git_worker_evidence,
    worker_id_for_task,
)
from devflow.control_room.persistence import (
    get_task,
    list_tasks,
    load_task,
    timestamp,
    utc_now,
    validate_event_log,
    atomic_write_text,
)
from devflow.control_room.promotion import (
    _get_relative_files,
    current_main_head,
    format_stale_baseline_refusal,
    main_checkout_has_uncommitted_changes,
    promotion_baseline,
)
from devflow.control_room.project_registry import ProjectRegistryError, load_project_metadata
from devflow.control_room.readiness import format_promotion_refusal, promotion_readiness_errors
from devflow.control_room.seed import initialize_seed, validate_seed_contract
from devflow.control_room.task_lifecycle import (
    append_task_event,
    apply_lifecycle_metadata,
    invalidate_verification_after_workspace_mutation,
    record_task_update,
    write_task_state,
)
from devflow.control_room.task_artifacts import (
    ensure_task_baseline_artifacts,
    missing_task_baseline_artifacts,
)
from devflow.control_room.verification import VerificationResult, run_verification_command
from devflow.control_room.worker_adapter import get_worker_adapter
from devflow.control_room.workspace import create_workspace
from devflow.control_room.local_ollama_worker import (
    LocalOllamaRunResult,
    get_local_worker_definition,
    run_local_ollama_worker,
)
from devflow.control_room.log_sanitizer import DEFAULT_LATEST_LOG_LINE_MAX_CHARS, latest_visible_log_line
from devflow.control_room.patch_applier import (
    PatchError,
    PatchSelectionError,
    PatchParseError,
    PatchApplicationError,
    parse_unified_diff,
    apply_patch_files,
)



# Dynamic compatibility shims and mappings
_load_task = load_task
_append_event = append_task_event
_relative = relative_path
_absolute = absolute_path


def preview_task_promotion(root: Path, task_id: str) -> dict[str, Any]:
    import devflow.control_room.promotion as promotion
    # Forward monkeypatch if service._get_relative_files was overridden in a test
    if _get_relative_files is not promotion._get_relative_files:
        promotion._get_relative_files = _get_relative_files
    return promotion.preview_task_promotion(root, task_id)


def promote_task(
    root: Path,
    task_id: str,
    force: bool = False,
    apply_deletions: bool = False,
    force_stale_baseline: bool = False,
) -> TaskRecord:
    import devflow.control_room.promotion as promotion
    # Forward monkeypatch if service._get_relative_files was overridden in a test
    if _get_relative_files is not promotion._get_relative_files:
        promotion._get_relative_files = _get_relative_files
    with task_mutation_lock(root, task_id, "promote"):
        return promotion.promote_task(
            root,
            task_id,
            force=force,
            apply_deletions=apply_deletions,
            force_stale_baseline=force_stale_baseline,
        )



def init_control_room(root: Path, project_seed: Any | None = None) -> None:
    devflow_dir(root).mkdir(parents=True, exist_ok=True)
    initialize_seed(root, project_seed=project_seed)
    system_dir(root).mkdir(parents=True, exist_ok=True)
    tasks_dir(root).mkdir(parents=True, exist_ok=True)
    workspaces_dir(root).mkdir(parents=True, exist_ok=True)
    system_events_path(root).touch(exist_ok=True)
    if not config_path(root).exists():
        config_path(root).write_text(
            "version: 1\n"
            "source_of_truth: filesystem\n"
            "tasks: .devflow/tasks\n"
            "workspaces: .devflow/workspaces\n"
            "workers:\n"
            "  shell:\n"
            "    type: shell\n",
            encoding="utf-8",
        )


def create_task(root: Path, title: str, git_worktree: bool = False, worker_id: str = "shell") -> TaskRecord:
    init_control_room(root)
    _require_managed_project_git_baseline(root)

    # Concurrency Lock: Retryatomic directory creation to prevent task creation races
    lock_dir = devflow_dir(root) / ".lock"
    import time
    for _ in range(200):
        try:
            lock_dir.mkdir(parents=True, exist_ok=False)
            break
        except FileExistsError:
            time.sleep(0.01)

    try:
        task_id = _next_task_id(root)
        task_path = task_dir(root, task_id)
        
        # Atomically create the task directory, fail if already exists
        task_path.mkdir(parents=True, exist_ok=False)
        (task_path / "logs").mkdir(parents=True, exist_ok=True)
    finally:
        # Release the lock directory
        try:
            lock_dir.rmdir()
        except Exception:
            pass

    workspace = create_git_worktree(root, task_id, worker_id=worker_id) if git_worktree else create_workspace(root, task_id)

    now = utc_now()
    record = TaskRecord(
        id=task_id,
        title=title,
        status="created",
        created_at=now,
        updated_at=now,
        workspace=_relative(root, workspace.path),
        workspace_path=_relative(root, workspace.path),
        workspace_kind=workspace.kind,
        worker="shell",
        last_event="task_created",
        verification_status="not_run",
        branch_name=workspace.branch_name,
        workspace_commit=workspace.commit_sha,
        workspace_dirty=workspace.dirty,
        git={
            "base_ref": workspace.base_ref,
            "base_commit": workspace.commit_sha,
            "branch": workspace.branch_name,
            "workspace": _relative(root, workspace.path),
        },
    )
    _write_initial_artifacts(task_path, task_id, record.workspace)
    if git_worktree:
        refresh_git_worker_evidence(root, record, worker_id=worker_id)
    event_payload: dict[str, Any] = {
        "title": title,
        "workspace": record.workspace,
        "branch_name": workspace.branch_name,
        "workspace_commit": workspace.commit_sha,
        "workspace_dirty": workspace.dirty,
        "workspace_kind": workspace.kind,
        "git": record.git,
    }
    if workspace.skipped_symlinks:
        event_payload["skipped_symlinks"] = list(workspace.skipped_symlinks)
    record_task_update(
        root,
        record,
        event_type="task_created",
        event_payload=event_payload,
        event_position="before_save",
    )
    return record


def _require_managed_project_git_baseline(root: Path) -> None:
    try:
        metadata = load_project_metadata(root)
    except ProjectRegistryError:
        return
    if not metadata.source_control.local_repo:
        return

    head = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD"],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    if head.returncode == 0:
        return

    raise ValueError(
        "Project local Git baseline is missing. "
        f"Run `devflow git checkpoint --message \"chore: initialize project baseline\" --yes` from {root} "
        "before creating tasks."
    )



def run_shell_task(
    root: Path,
    task_id: str,
    command: list[str],
    timeout_seconds: int = 60,
    worker_adapter: str = "shell",
    env: dict[str, str] | None = None,
) -> TaskRecord:
    from devflow.control_room.agent_registry import (
        load_agent_registry,
        load_provider_registry,
    )
    from devflow.control_room.agent_runtime import resolve_agent_runtime_definition
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

    adapter = get_worker_adapter(resolved_adapter_name, agent=agent, provider=provider)
    if not command and resolved_adapter_name not in {"manual", "ollama_chat"}:
        raise ValueError("Shell worker requires a command after '--'.")
    if not command and resolved_adapter_name == "manual":
        command = ["manual-handoff", worker_adapter]

    if _looks_destructive(command):
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

    with task_mutation_lock(root, task_id, "run"):
        task = get_task(root, task_id)
        task_path = task_dir(root, task_id)
        workspace = _resolve_task_workspace(root, task)

        log_file = task_path / "logs" / "worker.log"
        result_file = task_path / "result.md"

        if agent is not None:
            agent_dir = task_path / "agents" / agent.id
            agent_dir.mkdir(parents=True, exist_ok=True)
            (agent_dir / "logs").mkdir(parents=True, exist_ok=True)
            log_file = agent_dir / "logs" / "worker.log"
            result_file = agent_dir / "result.md"

        worker_input = WorkerInput(
            task_id=task_id,
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

        if agent is not None:
            from devflow.control_room.task_packet import build_agent_packet
            agent_packet = build_agent_packet(task_id, agent, root=root)
            agent_packet_json = json.dumps(agent_packet.model_dump(mode="json"), sort_keys=True, indent=2) + "\n"
            (task_path / "agents" / agent.id / "packet.json").write_text(agent_packet_json, encoding="utf-8")
            (task_path / "packet.json").write_text(agent_packet_json, encoding="utf-8")
        else:
            from devflow.control_room.task_packet import build_task_packet
            packet = build_task_packet(task_id, root=root)
            packet_json = json.dumps(packet.model_dump(mode="json"), sort_keys=True, indent=2) + "\n"
            (task_path / "packet.json").write_text(packet_json, encoding="utf-8")

        result = adapter.run(worker_input)
        if resolved_adapter_name not in {"manual", "ollama_chat"}:
            _write_result(task_path if agent is None else (task_path / "agents" / agent.id), task_id, command, result)
        if agent is not None:
            compat_log = task_path / "logs" / "worker.log"
            compat_log.write_text(log_file.read_text(encoding="utf-8"), encoding="utf-8")
            if resolved_adapter_name not in {"manual", "ollama_chat"}:
                _write_result(task_path, task_id, command, result)

        task.last_exit_code = result.exit_code
        task.latest_log_line = result.latest_log_line
        task.log_path = _relative(root, log_file)
        task.result_path = _relative(root, result_file) if result_file.exists() else None
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


def run_local_model_task(
    root: Path,
    task_id: str,
    worker_name: str,
    *,
    input_worker: str | None = None,
    timeout_seconds: int | None = None,
) -> LocalOllamaRunResult:
    definition = get_local_worker_definition(worker_name)
    timeout = timeout_seconds or definition.default_timeout_seconds
    if timeout <= 0:
        raise ValueError("Local worker timeout must be greater than zero.")

    # Resolve workspace and read configuration lock-free
    task = get_task(root, task_id)
    task_path = task_dir(root, task_id)
    workspace = _resolve_task_workspace(root, task)
    task_yaml_text = (task_path / "task.yaml").read_text(encoding="utf-8")

    # Run the Ollama subprocess lock-free so multiple local workers can run in parallel
    result = run_local_ollama_worker(
        root,
        task_id,
        workspace,
        worker_name,
        input_worker=input_worker,
        timeout_seconds=timeout,
        task_yaml_text=task_yaml_text,
    )

    # Acquire the task lock briefly post-run to synchronize canonical task updates and event appends
    with task_mutation_lock(root, task_id, "local-worker"):
        task = get_task(root, task_id)
        task.last_exit_code = result.exit_code
        task.latest_log_line = _local_worker_latest_line(result)
        task.log_path = _relative(root, result.stderr_path)
        task.result_path = _relative(root, result.response_path)
        task.finished_at = result.finished_at
        if is_git_worktree_task(task):
            state = refresh_git_worker_evidence(root, task, worker_id=worker_id_for_task(task))
            task.workspace_dirty = bool(state["dirty"])
        apply_lifecycle_metadata(
            task,
            event_type="local_worker_finished",
            status=result.task_status,
            updated_at=task.finished_at,
        )

        # Chronologically append start and finish events to task history under synchronized lock
        append_task_event(
            root,
            task_id,
            "local_worker_started",
            {
                "worker_name": worker_name,
                "model": definition.model,
                "artifact_dir": _relative(root, result.artifact_dir),
                "input_worker": input_worker or definition.default_input_worker,
                "run_id": result.run_id,
            },
        )
        append_task_event(
            root,
            task_id,
            "local_worker_finished",
            {
                "worker_name": worker_name,
                "model": definition.model,
                "status": result.status,
                "exit_code": result.exit_code,
                "run_id": result.run_id,
                "run_json_path": _relative(root, result.run_json_path),
                "response_path": _relative(root, result.response_path),
                "stderr_path": _relative(root, result.stderr_path),
            },
        )

        write_task_state(root, task)

    return result


def verify_task(root: Path, task_id: str, command: list[str], timeout_seconds: int = 120) -> TaskRecord:
    if not command:
        raise ValueError("Verification requires a command after '--'.")
    if _looks_destructive(command):
        with task_mutation_lock(root, task_id, "verify"):
            append_task_event(root, task_id, "verification_refused", {"command": command})
        raise ValueError("Refusing obviously destructive verification command.")

    with task_mutation_lock(root, task_id, "verify"):
        task = get_task(root, task_id)
        task_path = task_dir(root, task_id)
        workspace = _resolve_task_workspace(root, task)
        verify_log = task_path / "logs" / "verify.log"

        append_task_event(root, task_id, "verification_started", {"command": command, "cwd": task.workspace})
        result = run_verification_command(workspace, command, verify_log, timeout_seconds=timeout_seconds)

        task.verification_status = result.status
        task.verification_command = shlex.join(command)
        task.verification_exit_code = result.exit_code
        task.verification_log_path = _relative(root, result.log_file)
        task.latest_log_line = result.latest_log_line
        if is_git_worktree_task(task):
            state = refresh_git_worker_evidence(root, task, worker_id=worker_id_for_task(task))
            task.workspace_dirty = bool(state["dirty"])
        apply_lifecycle_metadata(
            task,
            event_type="verification_finished",
            status="verified" if result.status == "passed" else "verification_failed",
            updated_at=utc_now(),
        )
        _write_verification_json(root, task_path, task, result)
        _write_verification_report(task_path, task, result)
        record_task_update(
            root,
            task,
            event_type="verification_finished",
            event_payload={"status": result.status, "exit_code": result.exit_code, "log_path": task.verification_log_path},
        )
        return task


def doctor(root: Path, strict: bool = False) -> list[tuple[str, bool, str]]:
    seed_errors = validate_seed_contract(root)
    checks = [
        ("runtime directory", devflow_dir(root).exists(), str(devflow_dir(root))),
        ("config", config_path(root).exists(), str(config_path(root))),
        ("system directory", system_dir(root).exists(), str(system_dir(root))),
        ("system events", system_events_path(root).exists(), str(system_events_path(root))),
        ("tasks directory", tasks_dir(root).exists(), str(tasks_dir(root))),
        ("workspaces directory", workspaces_dir(root).exists(), str(workspaces_dir(root))),
    ]
    import sys
    import os
    if sys.platform == "darwin":
        for path_str in sys.path:
            if not path_str:
                continue
            try:
                path = Path(path_str).resolve()
            except Exception:
                continue
            try:
                abs_root = root.resolve()
                if abs_root in path.parents or path == abs_root:
                    curr = path
                    while curr != abs_root and curr != curr.parent:
                        st = os.stat(curr)
                        if hasattr(st, "st_flags") and (st.st_flags & 0x8000):
                            checks.append((
                                f"python path hygiene ({curr.name})",
                                True,
                                f"local environment hygiene: macOS hidden flag set on {curr}; if imports fail, run 'chflags -R nohidden {curr}'"
                            ))
                            break
                        curr = curr.parent
            except Exception:
                pass
    if seed_errors:
        checks.append(("seed contract", False, "; ".join(seed_errors)))
    elif devflow_dir(root).exists():
        checks.append(("seed contract", True, ".devflow seed contract"))
    strict_tasks: list[TaskRecord] = []
    if tasks_dir(root).exists():
        for path in sorted(tasks_dir(root).iterdir()):
            if not path.is_dir():
                continue
            yaml_path = path / "task.yaml"
            checks.append((f"{path.name} task.yaml", yaml_path.exists(), str(yaml_path)))
            if yaml_path.exists():
                try:
                    task = _load_task(path)
                except ValueError as exc:
                    checks.append((f"{path.name} task.yaml valid", False, str(exc)))
                    continue
                strict_tasks.append(task)
                workspace_exists = _absolute(root, task.workspace).is_dir()
                if task.status == "closed" and not workspace_exists:
                    checks.append((f"{path.name} workspace", True, f"closed task workspace not required: {task.workspace}"))
                else:
                    checks.append((f"{path.name} workspace", workspace_exists, task.workspace))
                missing_baseline = missing_task_baseline_artifacts(path)
                checks.append((
                    f"{path.name} baseline artifacts",
                    not missing_baseline,
                    "complete" if not missing_baseline else f"missing: {', '.join(missing_baseline)}",
                ))
                for name in ("events.jsonl", "questions.jsonl", "result.md", "verification.json"):
                    checks.append((f"{path.name} {name}", (path / name).exists(), str(path / name)))
                events_ok, events_detail = validate_event_log(path / "events.jsonl")
                checks.append((f"{path.name} events integrity", events_ok, events_detail))
                if strict:
                    checks.extend(_strict_task_checks(root, path, task))
    if strict:
        checks.extend(git_branch_sharing_checks(strict_tasks))

        # 1. No experimental provider adapters enabled in loaded registry
        try:
            from devflow.control_room.agent_registry import load_agent_registry, load_provider_registry
            from devflow.control_room.agent_runtime import resolve_agent_runtime_definition
            registry = load_agent_registry(root)
            providers = load_provider_registry(root)
            unstable_agents = []
            for agent in registry.enabled_agents():
                provider = providers.providers.get(agent.provider)
                runtime = resolve_agent_runtime_definition(agent, provider)
                if not (runtime.task_run_allowed or runtime.agent_run_allowed or runtime.packet_allowed):
                    unstable_agents.append(f"{agent.id} ({agent.adapter})")
            if unstable_agents:
                checks.append(("strict: only executable runtime agents enabled", False, f"unstable: {', '.join(unstable_agents)}"))
            else:
                checks.append(("strict: only executable runtime agents enabled", True, "all enabled agents use approved runtime adapters"))
        except Exception as exc:
            checks.append(("strict: agent registry validation", False, str(exc)))

        # 2. Main checkout has no uncommitted changes (clean main worktree)
        try:
            from devflow.control_room.promotion import main_checkout_has_uncommitted_changes
            dirty = main_checkout_has_uncommitted_changes(root)
            if dirty:
                checks.append(("strict: clean main worktree", False, "uncommitted changes present"))
            else:
                checks.append(("strict: clean main worktree", True, "git worktree is clean"))
        except Exception as exc:
            checks.append(("strict: git worktree check", False, str(exc)))
    return checks


def _strict_task_checks(root: Path, task_path: Path, task: TaskRecord) -> list[tuple[str, bool, str]]:
    checks: list[tuple[str, bool, str]] = []
    task_id = task.id
    worker_id = worker_id_for_task(task) if is_git_worktree_task(task) else "shell"
    expected_workspace_rel = (
        f".devflow/worktrees/{task_id}/{worker_id}"
        if is_git_worktree_task(task)
        else f".devflow/workspaces/{task_id}"
    )
    expected_workspace = (
        worktree_path(root, task_id, worker_id).resolve()
        if is_git_worktree_task(task)
        else (workspaces_dir(root) / task_id).resolve()
    )
    workspace = _absolute(root, task.workspace).resolve()
    workspace_rel_ok = Path(task.workspace).as_posix() == expected_workspace_rel
    workspace_resolved_ok = workspace == expected_workspace
    checks.append((
        f"strict: {task_id} workspace path",
        workspace_rel_ok and workspace_resolved_ok,
        expected_workspace_rel if workspace_rel_ok and workspace_resolved_ok else f"expected {expected_workspace_rel}",
    ))

    logs_dir = task_path / "logs"
    for log_name in ("worker.log", "verify.log"):
        log_path = logs_dir / log_name
        checks.append((f"strict: {task_id} {log_name}", log_path.exists(), str(log_path)))

    checks.extend(_strict_task_json_checks(task_path, task))
    checks.append(_strict_task_lock_check(task_path, task_id))
    checks.extend(_strict_manual_evidence_checks(task_path, task_id))
    checks.extend(_strict_patch_evidence_checks(root, task_path, task_id))
    checks.extend(git_doctor_checks(root, task))
    checks.append(_strict_promoted_consistency_check(task_path, task))
    return checks


def _strict_task_json_checks(task_path: Path, task: TaskRecord) -> list[tuple[str, bool, str]]:
    checks: list[tuple[str, bool, str]] = []
    task_id = task.id
    for artifact_name, optional in (
        ("verification.json", False),
        ("summary.json", True),
        ("merge-readiness.json", True),
    ):
        artifact_path = task_path / artifact_name
        if optional and not artifact_path.exists():
            continue
        ok, detail = _strict_json_artifact_detail(artifact_path, task)
        checks.append((f"strict: {task_id} {artifact_name}", ok, detail))
    return checks


def _strict_json_artifact_detail(path: Path, task: TaskRecord) -> tuple[bool, str]:
    if not path.exists():
        return False, str(path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return False, f"invalid JSON: {exc.msg}"
    if not isinstance(payload, dict):
        return False, "invalid JSON: expected object"
    if payload.get("task_id") not in (None, task.id):
        return False, "task_id does not match task.yaml"
    if path.name == "summary.json" and payload.get("status") not in (None, task.status):
        return False, "status does not match task.yaml"
    if path.name == "merge-readiness.json" and not isinstance(payload.get("ready"), bool):
        return False, "ready must be boolean"
    return True, str(path)


def _strict_task_lock_check(task_path: Path, task_id: str) -> tuple[str, bool, str]:
    lock_dir = task_path / ".lock"
    name = f"strict: {task_id} task lock"
    if not lock_dir.exists():
        return (name, True, "no task lock present")
    owner_path = lock_dir / "owner.json"
    try:
        payload = json.loads(owner_path.read_text(encoding="utf-8"))
        acquired_at = datetime.fromisoformat(str(payload.get("acquired_at")))
    except Exception as exc:
        return (name, False, f"lock owner unreadable: {exc}")
    if acquired_at.tzinfo is None:
        acquired_at = acquired_at.replace(tzinfo=timezone.utc)
    age_seconds = (datetime.now(timezone.utc) - acquired_at).total_seconds()
    operation = payload.get("operation") or "unknown"
    if age_seconds > TASK_LOCK_STALE_AFTER_SECONDS:
        return (name, False, f"stale lock: operation {operation}, acquired_at {payload.get('acquired_at')}")
    return (name, False, f"active lock: operation {operation}, acquired_at {payload.get('acquired_at')}")


def _strict_manual_evidence_checks(task_path: Path, task_id: str) -> list[tuple[str, bool, str]]:
    checks: list[tuple[str, bool, str]] = []
    agents_dir = task_path / "agents"
    if not agents_dir.exists():
        return checks
    for agent_dir in sorted(path for path in agents_dir.iterdir() if path.is_dir()):
        agent_id = agent_dir.name
        failed_path = agent_dir / "worker_failed.json"
        if failed_path.exists():
            checks.append(_strict_worker_failed_check(failed_path, task_id, agent_id))
        questions_path = agent_dir / "questions.jsonl"
        if questions_path.exists():
            checks.append(_strict_questions_check(questions_path, task_id, agent_id))
    return checks


def _strict_worker_failed_check(path: Path, task_id: str, agent_id: str) -> tuple[str, bool, str]:
    name = f"strict: {task_id} {agent_id} worker_failed.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return (name, False, f"invalid JSON: {exc.msg}")
    if not isinstance(payload, dict):
        return (name, False, "invalid JSON: expected object")
    if payload.get("status") != "worker_failed":
        return (name, False, "status must be worker_failed")
    if payload.get("task_id") != task_id or payload.get("agent_id") != agent_id:
        return (name, False, "task_id or agent_id does not match")
    if not isinstance(payload.get("summary"), str) or not payload.get("summary", "").strip():
        return (name, False, "summary is required")
    return (name, True, str(path))


def _strict_questions_check(path: Path, task_id: str, agent_id: str) -> tuple[str, bool, str]:
    name = f"strict: {task_id} {agent_id} questions.jsonl"
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw_line.strip():
            continue
        try:
            payload = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            return (name, False, f"line {line_number}: invalid JSON ({exc.msg})")
        if not isinstance(payload, dict):
            return (name, False, f"line {line_number}: expected JSON object")
        if payload.get("type") != "blocked_question":
            return (name, False, f"line {line_number}: type must be blocked_question")
        if payload.get("task_id") != task_id or payload.get("agent_id") != agent_id:
            return (name, False, f"line {line_number}: task_id or agent_id does not match")
        if not isinstance(payload.get("question"), str) or not payload.get("question", "").strip():
            return (name, False, f"line {line_number}: question is required")
    return (name, True, str(path))


def _strict_patch_evidence_checks(root: Path, task_path: Path, task_id: str) -> list[tuple[str, bool, str]]:
    checks: list[tuple[str, bool, str]] = []
    events_path = task_path / "events.jsonl"
    if not events_path.exists():
        return checks
    for event in _read_task_events(events_path):
        if event.get("event") != "patch_applied":
            continue
        patch_hash = event.get("patch_hash")
        evidence_path_text = event.get("patch_evidence_path")
        name = f"strict: {task_id} patch evidence {patch_hash or 'missing-hash'}"
        if not isinstance(patch_hash, str) or not patch_hash:
            checks.append((name, False, "patch_applied event missing patch_hash"))
            continue
        if not isinstance(evidence_path_text, str) or not evidence_path_text:
            checks.append((name, False, "patch_applied event missing patch_evidence_path"))
            continue
        evidence_path = _absolute(root, evidence_path_text)
        ok, detail = _strict_patch_evidence_detail(evidence_path, task_id, patch_hash)
        checks.append((name, ok, detail))
    return checks


def _strict_patch_evidence_detail(path: Path, task_id: str, patch_hash: str) -> tuple[bool, str]:
    if not path.exists():
        return False, str(path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return False, f"invalid JSON: {exc.msg}"
    if not isinstance(payload, dict):
        return False, "invalid JSON: expected object"
    if payload.get("task_id") != task_id:
        return False, "task_id does not match patch_applied event"
    if payload.get("patch_hash") != patch_hash:
        return False, "patch_hash does not match patch_applied event"
    if not isinstance(payload.get("changed_files"), list):
        return False, "changed_files must be a list"
    return True, str(path)


def _strict_promoted_consistency_check(task_path: Path, task: TaskRecord) -> tuple[str, bool, str]:
    name = f"strict: {task.id} promoted consistency"
    if task.status != "promoted":
        return (name, True, "not promoted")
    events = _read_task_events(task_path / "events.jsonl")
    promoted_events = [event for event in events if event.get("event") == "task_promoted"]
    if not promoted_events:
        return (name, False, "missing task_promoted event")
    if task.verification_status != "passed":
        return (name, False, "promoted task verification_status is not passed")
    return (name, True, "task_promoted event present")


def _read_task_events(path: Path) -> list[dict[str, Any]]:
    events = []
    if not path.exists():
        return events
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        if not raw_line.strip():
            continue
        try:
            event = json.loads(raw_line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            events.append(event)
    return events


def _write_initial_artifacts(task_path: Path, task_id: str, workspace_rel: str) -> None:
    ensure_task_baseline_artifacts(task_path, task_id=task_id, workspace_rel=workspace_rel)


def _write_result(task_path: Path, task_id: str, command: list[str], result: WorkerResult) -> None:
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


def _local_worker_latest_line(result: LocalOllamaRunResult) -> str | None:
    if result.error_message:
        return result.error_message
    if not result.stderr_path.exists():
        return None
    latest = latest_visible_log_line(result.stderr_path, max_chars=DEFAULT_LATEST_LOG_LINE_MAX_CHARS)
    return latest or None


def _write_verification_json(root: Path, task_path: Path, task: TaskRecord, result: VerificationResult) -> None:
    payload = {
        "schema_version": TASK_SCHEMA_VERSION,
        "task_id": task.id,
        "workspace": task.workspace,
        "command": result.command,
        "status": result.status,
        "task_status": task.status,
        "exit_code": result.exit_code,
        "latest_log_line": result.latest_log_line,
        "log_path": _relative(root, result.log_file),
        "finished_at": utc_now().isoformat(),
    }
    latest_patch = _read_patch_application_evidence(task_path)
    if latest_patch is not None and latest_patch.get("patch_hash"):
        payload.update(
            {
                "verified_patch_hash": latest_patch.get("patch_hash"),
                "verified_patch_application_path": _relative(root, task_path / "patch-application.json"),
                "patch_applied_at": latest_patch.get("applied_at"),
            }
        )
    if is_git_worktree_task(task):
        state = refresh_git_worker_evidence(root, task, worker_id=worker_id_for_task(task))
        payload.update(
            {
                "worker_id": state["worker_id"],
                "branch": state["worker_branch"],
                "verified_commit": state["head_commit"],
                "base_commit": state["base_commit"],
                "main_head_at_verification": current_main_head(root),
                "dirty_at_verification": state["dirty"],
            }
        )
        worker_verification = task_worker_dir(root, task.id, state["worker_id"]) / "verification.json"
        atomic_write_text(worker_verification, json.dumps(payload, indent=2) + "\n")
    atomic_write_text(task_path / "verification.json", json.dumps(payload, indent=2) + "\n")


def _write_verification_report(task_path: Path, task: TaskRecord, result: VerificationResult) -> None:
    existing = (task_path / "result.md").read_text(encoding="utf-8") if (task_path / "result.md").exists() else ""
    if "\n## Verification\n" in existing:
        existing = existing.split("\n## Verification\n", 1)[0]
    verification = (
        "\n## Verification\n\n"
        f"Status: {result.status}\n\n"
        f"Task Status: {task.status}\n\n"
        f"Command:\n\n```bash\n{' '.join(result.command)}\n```\n\n"
        f"Exit Code: {result.exit_code if result.exit_code is not None else 'none'}\n\n"
        f"Log: {result.log_file}\n"
    )
    atomic_write_text(task_path / "result.md", existing.rstrip() + verification)


def _next_task_id(root: Path) -> str:
    existing = []
    if tasks_dir(root).exists():
        for path in tasks_dir(root).iterdir():
            if path.is_dir() and path.name.startswith("task-"):
                try:
                    existing.append(int(path.name.removeprefix("task-")))
                except ValueError:
                    continue
    return f"task-{(max(existing) if existing else 0) + 1:04d}"





def _resolve_task_workspace(root: Path, task: TaskRecord) -> Path:
    workspace = _absolute(root, task.workspace).resolve()
    if is_git_worktree_task(task):
        expected = worktree_path(root, task.id, worker_id_for_task(task)).resolve()
    else:
        expected = (workspaces_dir(root) / task.id).resolve()
    if workspace != expected:
        _refuse_workspace(root, task, workspace, expected)
    if not workspace.is_dir():
        _refuse_workspace(root, task, workspace, expected)
    return workspace


def _refuse_workspace(root: Path, task: TaskRecord, workspace: Path, expected: Path) -> None:
    record_task_update(
        root,
        task,
        event_type="workspace_refused",
        event_payload={"workspace": str(workspace), "expected_workspace": str(expected)},
        status="blocked",
        updated_at=utc_now(),
        write_readiness=False,
    )
    raise ValueError(f"Refusing unsafe task workspace: {workspace} (expected {expected})")


def _looks_destructive(command: list[str]) -> bool:
    text = " ".join(command).lower()
    blocked_fragments = ("rm -rf /", "rm -fr /", "mkfs", "diskutil erase", ":(){", "dd if=")
    return any(fragment in text for fragment in blocked_fragments)


ACCEPTABLE_PATCH_REVIEW_STATUSES = {"low_risk_candidate", "review_required"}
ACCEPTABLE_PATCH_DRY_RUN_STATUSES = {"would_apply_cleanly", "would_create_files", "would_modify_with_warnings"}


def apply_task_patch(
    root: Path,
    task_id: str,
    agent_id: str | None = None,
    run_id: str | None = None,
) -> TaskRecord:
    with task_mutation_lock(root, task_id, "apply-patch"):
        return _apply_task_patch_locked(root, task_id, agent_id, run_id)


def _apply_task_patch_locked(
    root: Path,
    task_id: str,
    agent_id: str | None = None,
    run_id: str | None = None,
) -> TaskRecord:
    task_path = task_dir(root, task_id)
    task = get_task(root, task_id)
    workspace = _resolve_task_workspace(root, task)

    agents_dir = task_path / "agents"
    local_runs_dir = task_path / "local-model-runs"
    if run_id is None and (not agents_dir.exists() or not list(agents_dir.iterdir())):
        raise PatchSelectionError(f"No patches found for task {task_id}")

    target_patch: Path | None = None
    selected_agent: str | None = None
    selected_run_id: str | None = run_id

    if run_id is not None and agent_id is None:
        run_patch = local_runs_dir / run_id / "proposal.patch"
        if not run_patch.exists():
            raise PatchSelectionError(f"No proposal.patch found for local model run {run_id}")
        target_patch = run_patch
    elif agent_id:
        agent_patch = agents_dir / agent_id / "proposal.patch"
        if not agent_patch.exists():
            raise PatchSelectionError(f"No patch found for agent {agent_id}")
        target_patch = agent_patch
        selected_agent = agent_id
    else:
        # Search for proposal.patch in all agent subdirectories
        found_patches: list[tuple[str, Path]] = []
        for child in agents_dir.iterdir():
            if child.is_dir() and (child / "proposal.patch").exists():
                found_patches.append((child.name, child / "proposal.patch"))
        
        if not found_patches:
            raise PatchSelectionError(f"No patches found under {agents_dir}")
        elif len(found_patches) > 1:
            agents_list = ", ".join(f"'{name}'" for name, _ in found_patches)
            raise PatchSelectionError(
                f"Multiple proposal patches found: {agents_list}. "
                "Please specify which one to apply using --agent."
            )
        else:
            selected_agent, target_patch = found_patches[0]

    # Compute SHA-256 hash of the proposal.patch
    patch_content = target_patch.read_text(encoding="utf-8")
    patch_hash = hashlib.sha256(patch_content.encode("utf-8")).hexdigest()
    review_gate = _require_patch_review_and_dry_run_gate(
        root,
        task_id,
        target_patch=target_patch,
        patch_hash=patch_hash,
        run_id=selected_run_id,
    )
    selected_run_id = review_gate["run_id"]

    # Idempotency check: check in events.jsonl
    events_file = task_path / "events.jsonl"
    if events_file.exists():
        for line in events_file.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                evt = json.loads(line)
                if evt.get("event") == "patch_applied" and evt.get("patch_hash") == patch_hash:
                    raise PatchApplicationError("Patch was already applied to this workspace")
            except json.JSONDecodeError:
                pass



    # Parse and apply patch
    patch_files = parse_unified_diff(patch_content)
    result = apply_patch_files(workspace, patch_files, patch_hash=patch_hash)
    
    # Structure changes payload
    changed_files_payload = [
        {"path": f.path, "operation": f.operation, "additions": f.additions, "deletions": f.deletions}
        for f in result.changed_files
    ]
    
    evidence_path = _write_patch_application_evidence(
        root,
        task_path,
        task,
        selected_agent,
        selected_run_id,
        target_patch,
        result.patch_hash,
        changed_files_payload,
        review_gate["patch_review_path"],
        review_gate["patch_dry_run_path"],
    )

    append_task_event(root, task_id, "patch_applied", {
        "agent_id": selected_agent,
        "run_id": selected_run_id,
        "patch_path": _relative(root, target_patch),
        "patch_hash": result.patch_hash,
        "patch_review_path": _relative(root, review_gate["patch_review_path"]),
        "patch_dry_run_path": _relative(root, review_gate["patch_dry_run_path"]),
        "patch_evidence_path": _relative(root, evidence_path),
        "changed_files": changed_files_payload,
    })

    patch_application = _read_patch_application_evidence(task_path) or {}
    return invalidate_verification_after_workspace_mutation(root, task, patch_application=patch_application)


def _write_patch_application_evidence(
    root: Path,
    task_path: Path,
    task: TaskRecord,
    agent_id: str | None,
    run_id: str | None,
    patch_path: Path,
    patch_hash: str,
    changed_files: list[dict[str, Any]],
    patch_review_path: Path,
    patch_dry_run_path: Path,
) -> Path:
    evidence = {
        "schema_version": TASK_SCHEMA_VERSION,
        "task_id": task.id,
        "agent_id": agent_id,
        "run_id": run_id,
        "patch_path": _relative(root, patch_path),
        "patch_hash": patch_hash,
        "patch_review_path": _relative(root, patch_review_path),
        "patch_dry_run_path": _relative(root, patch_dry_run_path),
        "workspace": task.workspace,
        "changed_files": changed_files,
        "operation_summary": {
            "created": sum(1 for item in changed_files if item.get("operation") == "created"),
            "modified": sum(1 for item in changed_files if item.get("operation") == "modified"),
            "deleted": sum(1 for item in changed_files if item.get("operation") == "deleted"),
        },
        "applied_at": utc_now().isoformat(),
    }
    patches_dir = task_path / "patches"
    evidence_path = patches_dir / f"{patch_hash}.json"
    body = json.dumps(evidence, indent=2, sort_keys=True) + "\n"
    atomic_write_text(evidence_path, body)
    atomic_write_text(task_path / "patch-application.json", body)
    return evidence_path


def _read_patch_application_evidence(task_path: Path) -> dict[str, Any] | None:
    path = task_path / "patch-application.json"
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _require_patch_review_and_dry_run_gate(
    root: Path,
    task_id: str,
    *,
    target_patch: Path,
    patch_hash: str,
    run_id: str | None,
) -> dict[str, Any]:
    task_path = task_dir(root, task_id)
    runs_dir = task_path / "local-model-runs"
    if not runs_dir.exists() or not runs_dir.is_dir():
        raise PatchApplicationError(
            "Patch application requires fresh acceptable patch-review and patch-dry-run evidence before mutating the workspace."
        )

    if run_id is not None:
        run_path = runs_dir / run_id
        if not run_path.exists() or not run_path.is_dir():
            raise PatchApplicationError(f"Local model run '{run_id}' not found for task '{task_id}'.")
        candidates = [run_path]
    else:
        candidates = sorted(path for path in runs_dir.iterdir() if path.is_dir())

    matching: list[Path] = []
    for run_path in candidates:
        proposal_path = run_path / "proposal.patch"
        if proposal_path.exists() and _file_sha256(proposal_path) == patch_hash:
            matching.append(run_path)

    if not matching:
        raise PatchApplicationError(
            "Patch application requires matching reviewed dry-run evidence for the selected patch."
        )

    errors: list[str] = []
    for run_path in reversed(matching):
        try:
            review_path, dry_run_path = _validate_patch_gate_run(root, task_id, run_path, target_patch)
            return {
                "run_id": run_path.name,
                "patch_review_path": review_path,
                "patch_dry_run_path": dry_run_path,
            }
        except PatchApplicationError as exc:
            errors.append(str(exc))

    details = f" Last checked: {errors[-1]}" if errors else ""
    raise PatchApplicationError(
        "Patch application requires fresh acceptable patch-review and patch-dry-run evidence before mutating the workspace."
        + details
    )


def _validate_patch_gate_run(root: Path, task_id: str, run_path: Path, target_patch: Path) -> tuple[Path, Path]:
    proposal_path = run_path / "proposal.patch"
    review_path = run_path / "patch-review.json"
    dry_run_path = run_path / "patch-dry-run.json"
    if not review_path.exists() or not dry_run_path.exists():
        raise PatchApplicationError("patch-review.json and patch-dry-run.json are both required.")

    try:
        review = json.loads(review_path.read_text(encoding="utf-8"))
        dry_run = json.loads(dry_run_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PatchApplicationError("Patch review or dry-run evidence is malformed.") from exc
    if not isinstance(review, dict) or not isinstance(dry_run, dict):
        raise PatchApplicationError("Patch review or dry-run evidence is malformed.")

    if str(review.get("task_id") or "") != task_id or str(dry_run.get("task_id") or "") != task_id:
        raise PatchApplicationError("Patch review and dry-run evidence must match the task id.")
    if str(review.get("run_id") or "") != run_path.name or str(dry_run.get("run_id") or "") != run_path.name:
        raise PatchApplicationError("Patch review and dry-run evidence must match the local model run id.")

    review_status = str(review.get("review_status") or "unknown")
    if review_status not in ACCEPTABLE_PATCH_REVIEW_STATUSES:
        raise PatchApplicationError(f"Patch review status is not acceptable: {review_status}")

    dry_run_status = str(dry_run.get("dry_run_status") or "unknown")
    if dry_run_status not in ACCEPTABLE_PATCH_DRY_RUN_STATUSES:
        raise PatchApplicationError(f"Patch dry-run status is not acceptable: {dry_run_status}")
    if int(dry_run.get("hunks_failed") or 0) != 0:
        raise PatchApplicationError("Patch dry-run evidence has failed hunks.")

    proposal_rel = _relative(root, proposal_path)
    review_rel = _relative(root, review_path)
    if str(dry_run.get("proposal_patch_path") or "") != proposal_rel:
        raise PatchApplicationError("Patch dry-run evidence does not reference the reviewed proposal.patch.")
    if str(dry_run.get("patch_review_path") or "") != review_rel:
        raise PatchApplicationError("Patch dry-run evidence does not reference the matching patch-review.json.")

    proposal_mtime = proposal_path.stat().st_mtime_ns
    if review_path.stat().st_mtime_ns < proposal_mtime or dry_run_path.stat().st_mtime_ns < proposal_mtime:
        raise PatchApplicationError("Patch review or dry-run evidence is stale for the selected proposal.patch.")

    target_rel = _relative(root, target_patch)
    review_patch_rel = str(review.get("patch_path") or "")
    if review_patch_rel and review_patch_rel not in {proposal_rel, target_rel}:
        raise PatchApplicationError("Patch review evidence references a different proposal.patch.")

    return review_path, dry_run_path


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
