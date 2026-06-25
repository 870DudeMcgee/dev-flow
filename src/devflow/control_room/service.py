from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from devflow.control_room.models import TaskRecord
from devflow.control_room.locks import TASK_LOCK_STALE_AFTER_SECONDS, task_mutation_lock
from devflow.control_room.paths import (
    absolute_path,
    relative_path,
    config_path,
    devflow_dir,
    system_dir,
    system_events_path,
    task_dir,
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
)
from devflow.control_room.promotion import (
    _get_relative_files,
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
    record_task_update,
    write_task_state,
)
from devflow.control_room.task_artifacts import (
    ensure_task_baseline_artifacts,
    missing_task_baseline_artifacts,
)
from devflow.control_room.task_patch_application import apply_task_patch_command
from devflow.control_room.task_verification import verify_task_command
from devflow.control_room.task_worker_run import run_task_worker
from devflow.control_room.task_workspace import validated_task_workspace
from devflow.control_room.workspace import create_workspace
from devflow.control_room.local_ollama_worker import (
    LocalOllamaRunResult,
    get_local_worker_definition,
    run_local_ollama_worker,
)
from devflow.control_room.log_sanitizer import DEFAULT_LATEST_LOG_LINE_MAX_CHARS, latest_visible_log_line

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


def create_task(
    root: Path,
    title: str,
    git_worktree: bool = False,
    worker_id: str = "shell",
    definition_of_done: str | None = None,
) -> TaskRecord:
    init_control_room(root)
    _require_managed_project_git_baseline(root)
    done_text = str(definition_of_done).strip() if definition_of_done is not None else None

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
        definition_of_done=done_text or None,
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
        "definition_of_done": record.definition_of_done,
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
    return run_task_worker(
        root,
        task_id,
        command,
        timeout_seconds=timeout_seconds,
        worker_adapter=worker_adapter,
        env=env,
    )


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
    workspace = validated_task_workspace(root, task)
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
    return verify_task_command(root, task_id, command, timeout_seconds=timeout_seconds)


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


def _local_worker_latest_line(result: LocalOllamaRunResult) -> str | None:
    if result.error_message:
        return result.error_message
    if not result.stderr_path.exists():
        return None
    latest = latest_visible_log_line(result.stderr_path, max_chars=DEFAULT_LATEST_LOG_LINE_MAX_CHARS)
    return latest or None


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

def apply_task_patch(
    root: Path,
    task_id: str,
    agent_id: str | None = None,
    run_id: str | None = None,
) -> TaskRecord:
    return apply_task_patch_command(root, task_id, agent_id=agent_id, run_id=run_id)
