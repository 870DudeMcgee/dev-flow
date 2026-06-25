from __future__ import annotations

import json
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
    git_branch_sharing_checks,
    git_doctor_checks,
    git_worktree_readiness_errors,
    is_git_worktree_task,
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
from devflow.control_room.readiness import format_promotion_refusal, promotion_readiness_errors
from devflow.control_room.seed import validate_seed_contract
from devflow.control_room.task_creation import (
    create_control_room_task,
    initialize_control_room,
)
from devflow.control_room.task_lifecycle import (
    append_task_event,
    record_task_update,
)
from devflow.control_room.task_artifacts import (
    ensure_task_baseline_artifacts,
    missing_task_baseline_artifacts,
)
from devflow.control_room.task_patch_application import apply_task_patch_command
from devflow.control_room.task_verification import verify_task_command
from devflow.control_room.task_local_worker_run import run_task_local_worker
from devflow.control_room.task_worker_run import run_task_worker
from devflow.control_room.local_ollama_worker import LocalOllamaRunResult

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
    initialize_control_room(root, project_seed=project_seed)


def create_task(
    root: Path,
    title: str,
    git_worktree: bool = False,
    worker_id: str = "shell",
    definition_of_done: str | None = None,
) -> TaskRecord:
    return create_control_room_task(
        root,
        title,
        git_worktree=git_worktree,
        worker_id=worker_id,
        definition_of_done=definition_of_done,
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
    return run_task_local_worker(
        root,
        task_id,
        worker_name,
        input_worker=input_worker,
        timeout_seconds=timeout_seconds,
    )


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

def apply_task_patch(
    root: Path,
    task_id: str,
    agent_id: str | None = None,
    run_id: str | None = None,
) -> TaskRecord:
    return apply_task_patch_command(root, task_id, agent_id=agent_id, run_id=run_id)
