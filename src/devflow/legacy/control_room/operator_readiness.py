from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field

from devflow.legacy.control_room.goal_lifecycle import read_goal_lifecycle
from devflow.legacy.control_room.goal_projection import list_goal_status_projections
from devflow.legacy.control_room.goal_tasks import GoalTaskSlice, load_goal_task_slices
from devflow.legacy.control_room.persistence import list_tasks
from devflow.legacy.control_room.project_registry import load_project_metadata
from devflow.legacy.control_room.paths import task_dir


ReadinessState = Literal["worker_ready", "blocked", "in_progress", "closed", "needs_attention"]


class OperatorProjectIdentity(BaseModel):
    project_id: str | None = None
    display_name: str
    root_path: str


class OperatorDisplayIdentity(BaseModel):
    primary: str
    secondary: str
    raw_title: str
    ids: dict[str, str] = Field(default_factory=dict)


class OperatorBlocker(BaseModel):
    code: str
    message: str
    goal_id: str | None = None
    task_id: str | None = None
    slice_id: str | None = None


class OperatorTaskReadiness(BaseModel):
    state: ReadinessState
    worker_ready: bool
    blocked_by: list[OperatorBlocker] = Field(default_factory=list)


class OperatorTaskProjection(BaseModel):
    task_id: str
    goal_id: str | None = None
    slice_id: str | None = None
    display: OperatorDisplayIdentity
    readiness: OperatorTaskReadiness


class OperatorWarning(BaseModel):
    code: str
    message: str
    goal_id: str | None = None
    slice_id: str | None = None
    task_id: str | None = None
    blocked_by: str | None = None
    stale_command: str | None = None


class OperatorNextSafeAction(BaseModel):
    kind: str
    command: str | None = None
    reason: str


class OperatorReadinessSnapshot(BaseModel):
    schema_version: int = 1
    project: OperatorProjectIdentity
    counts: dict[str, int]
    tasks: list[OperatorTaskProjection] = Field(default_factory=list)
    warnings: list[OperatorWarning] = Field(default_factory=list)
    next_safe_action: OperatorNextSafeAction


def build_operator_readiness_snapshot(root: Path) -> OperatorReadinessSnapshot:
    """Build a read-only operator-facing projection from canonical filesystem state."""
    root = root.resolve()
    project = _project_identity(root)
    tasks = [
        _task_projection(root, task)
        for task in list_tasks(root)
    ]
    warnings = [
        *_goal_lifecycle_warnings(root, tasks),
        *_stale_freshness_warnings(root, tasks),
    ]
    counts = _counts(tasks, warnings)
    return OperatorReadinessSnapshot(
        project=project,
        counts=counts,
        tasks=tasks,
        warnings=warnings,
        next_safe_action=_next_safe_action(tasks, warnings),
    )


def _project_identity(root: Path) -> OperatorProjectIdentity:
    try:
        metadata = load_project_metadata(root)
        return OperatorProjectIdentity(
            project_id=metadata.project_id,
            display_name=metadata.name,
            root_path=metadata.root_path,
        )
    except Exception:
        return OperatorProjectIdentity(display_name=root.name, root_path=root.as_posix())


def _task_projection(root: Path, task: Any) -> OperatorTaskProjection:
    link = _goal_link(root, task.id)
    goal_id = _string_or_none(link.get("goal_id"))
    slice_id = _string_or_none(link.get("slice_id"))
    goal_slice = _goal_slice(root, goal_id, slice_id)
    display = _display_identity(task.id, task.title, goal_id, slice_id, goal_slice)
    readiness = _task_readiness(root, task, goal_id, slice_id)
    return OperatorTaskProjection(
        task_id=task.id,
        goal_id=goal_id,
        slice_id=slice_id,
        display=display,
        readiness=readiness,
    )


def _goal_link(root: Path, task_id: str) -> dict[str, Any]:
    path = task_dir(root, task_id) / "goal-link.yaml"
    if not path.exists():
        return {}
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _goal_slice(root: Path, goal_id: str | None, slice_id: str | None) -> GoalTaskSlice | None:
    if not goal_id or not slice_id:
        return None
    try:
        for item in load_goal_task_slices(root, goal_id):
            if item.task_id == slice_id:
                return item
    except Exception:
        return None
    return None


def _display_identity(
    task_id: str,
    raw_title: str,
    goal_id: str | None,
    slice_id: str | None,
    goal_slice: GoalTaskSlice | None,
) -> OperatorDisplayIdentity:
    primary = raw_title
    if goal_slice and _looks_generated_title(raw_title, goal_id):
        primary = goal_slice.title
    ids = {"task_id": task_id}
    if goal_id:
        ids["goal_id"] = goal_id
    if slice_id:
        ids["slice_id"] = slice_id
    return OperatorDisplayIdentity(
        primary=primary,
        secondary=" · ".join(ids.values()),
        raw_title=raw_title,
        ids=ids,
    )


def _looks_generated_title(title: str, goal_id: str | None) -> bool:
    if goal_id and title.strip().startswith(goal_id):
        return True
    return bool(re.search(r"\bG-\d+\b.*\bSlice\s+\d+\b", title))


def _task_readiness(root: Path, task: Any, goal_id: str | None, slice_id: str | None) -> OperatorTaskReadiness:
    blockers: list[OperatorBlocker] = []
    if goal_id:
        try:
            lifecycle = read_goal_lifecycle(root, goal_id)
        except Exception as exc:
            blockers.append(
                OperatorBlocker(
                    code="goal_lifecycle_unreadable",
                    message=f"Goal lifecycle state for {goal_id} is unreadable: {exc}",
                    goal_id=goal_id,
                    task_id=task.id,
                    slice_id=slice_id,
                )
            )
        else:
            if lifecycle is None:
                blockers.append(
                    OperatorBlocker(
                        code="goal_lifecycle_missing",
                        message=f"Goal {goal_id} lifecycle state is missing; repair it before worker dispatch.",
                        goal_id=goal_id,
                        task_id=task.id,
                        slice_id=slice_id,
                    )
                )
            elif lifecycle.lifecycle in {"paused", "blocked", "complete", "archived"}:
                blockers.append(
                    OperatorBlocker(
                        code=f"goal_lifecycle_{lifecycle.lifecycle}",
                        message=f"Goal {goal_id} lifecycle is {lifecycle.lifecycle}; do not dispatch new worker work.",
                        goal_id=goal_id,
                        task_id=task.id,
                        slice_id=slice_id,
                    )
                )
    if blockers:
        return OperatorTaskReadiness(state="blocked", worker_ready=False, blocked_by=blockers)
    if task.status in {"closed", "promoted"}:
        return OperatorTaskReadiness(state="closed", worker_ready=False)
    if task.status == "running":
        return OperatorTaskReadiness(state="in_progress", worker_ready=False)
    if task.status in {"failed", "worker_failed", "timeout", "verification_failed", "blocked"}:
        return OperatorTaskReadiness(state="needs_attention", worker_ready=False)
    return OperatorTaskReadiness(state="worker_ready", worker_ready=True)


def _stale_freshness_warnings(root: Path, tasks: list[OperatorTaskProjection]) -> list[OperatorWarning]:
    snapshot = _read_freshness_snapshot(root)
    if not snapshot:
        return []
    missing_lifecycle = {
        (blocker.goal_id, task.slice_id): task
        for task in tasks
        for blocker in task.readiness.blocked_by
        if blocker.code == "goal_lifecycle_missing" and blocker.goal_id and task.slice_id
    }
    warnings: list[OperatorWarning] = []
    for goal in _list(snapshot.get("goal_loop")):
        goal_id = _string_or_none(goal.get("goal_id"))
        for batch in _list(goal.get("parallel_batches")):
            commands = [str(command) for command in _list(batch.get("commands"))]
            for command in commands:
                command_goal, command_slice = _goal_create_task_command(command)
                key = (command_goal or goal_id, command_slice)
                task = missing_lifecycle.get(key)
                if task is None:
                    continue
                warnings.append(
                    OperatorWarning(
                        code="stale_freshness_directive",
                        message=(
                            f"Stale freshness directive points at {task.display.primary}, "
                            "but its goal lifecycle is missing."
                        ),
                        goal_id=key[0],
                        slice_id=key[1],
                        task_id=task.task_id,
                        blocked_by="goal_lifecycle_missing",
                        stale_command=command,
                    )
                )
    return warnings


def _goal_lifecycle_warnings(root: Path, tasks: list[OperatorTaskProjection]) -> list[OperatorWarning]:
    task_blocked_goal_ids = {
        blocker.goal_id
        for task in tasks
        for blocker in task.readiness.blocked_by
        if blocker.code.startswith("goal_lifecycle_") and blocker.goal_id
    }
    warnings: list[OperatorWarning] = []
    for goal in list_goal_status_projections(root):
        if goal.goal_id in task_blocked_goal_ids:
            continue
        if goal.lifecycle_missing:
            warnings.append(
                OperatorWarning(
                    code="goal_lifecycle_missing",
                    message=f"Goal {goal.goal_id} lifecycle state is missing; repair it before worker dispatch.",
                    goal_id=goal.goal_id,
                    blocked_by="goal_lifecycle_missing",
                )
            )
        elif goal.lifecycle in {"paused", "blocked", "complete", "archived", "unknown"}:
            warnings.append(
                OperatorWarning(
                    code=f"goal_lifecycle_{goal.lifecycle}",
                    message=f"Goal {goal.goal_id} lifecycle is {goal.lifecycle}; do not dispatch new worker work.",
                    goal_id=goal.goal_id,
                    blocked_by=f"goal_lifecycle_{goal.lifecycle}",
                )
            )
    return warnings


def _read_freshness_snapshot(root: Path) -> dict[str, Any] | None:
    path = root / ".devflow" / "freshness" / "latest.json"
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _goal_create_task_command(command: str) -> tuple[str | None, str | None]:
    parts = command.split()
    if len(parts) >= 5 and parts[:3] == ["devflow", "goal", "create-task"]:
        return parts[3], parts[4]
    return None, None


def _counts(tasks: list[OperatorTaskProjection], warnings: list[OperatorWarning]) -> dict[str, int]:
    lifecycle_blocked_goal_ids = {
        blocker.goal_id
        for task in tasks
        for blocker in task.readiness.blocked_by
        if blocker.code.startswith("goal_lifecycle_") and blocker.goal_id
    }
    lifecycle_blocked_goal_ids.update(
        warning.goal_id
        for warning in warnings
        if warning.code.startswith("goal_lifecycle_") and warning.goal_id
    )
    return {
        "total_tasks": len(tasks),
        "worker_ready": sum(1 for task in tasks if task.readiness.worker_ready),
        "blocked": sum(1 for task in tasks if task.readiness.state == "blocked"),
        "lifecycle_blocked": len(lifecycle_blocked_goal_ids),
        "warnings": len(warnings),
    }


def _next_safe_action(tasks: list[OperatorTaskProjection], warnings: list[OperatorWarning]) -> OperatorNextSafeAction:
    lifecycle_blocker = next(
        (
            blocker
            for task in tasks
            for blocker in task.readiness.blocked_by
            if blocker.code.startswith("goal_lifecycle_") and blocker.goal_id
        ),
        None,
    )
    if lifecycle_blocker:
        goal_id = lifecycle_blocker.goal_id
        return OperatorNextSafeAction(
            kind="repair_goal_lifecycle",
            command=f"devflow goal activate {goal_id} --reason 'ready to execute'",
            reason=f"Repair goal lifecycle state for {goal_id} before dispatching worker tasks.",
        )
    lifecycle_warning = next(
        (
            warning
            for warning in warnings
            if warning.code.startswith("goal_lifecycle_") and warning.goal_id
        ),
        None,
    )
    if lifecycle_warning:
        goal_id = lifecycle_warning.goal_id
        return OperatorNextSafeAction(
            kind="repair_goal_lifecycle",
            command=f"devflow goal activate {goal_id} --reason 'ready to execute'",
            reason=f"Repair goal lifecycle state for {goal_id} before dispatching worker tasks.",
        )
    stale = next((warning for warning in warnings if warning.code == "stale_freshness_directive"), None)
    if stale:
        return OperatorNextSafeAction(
            kind="inspect_stale_directive",
            command="devflow freshness loop --json",
            reason="Refresh stale operator guidance before dispatching worker tasks.",
        )
    worker_ready = next((task for task in tasks if task.readiness.worker_ready), None)
    if worker_ready:
        return OperatorNextSafeAction(
            kind="dispatch_worker",
            command=f"devflow task run {worker_ready.task_id} --worker shell -- <command>",
            reason=f"{worker_ready.display.primary} is ready for explicit worker dispatch.",
        )
    return OperatorNextSafeAction(
        kind="inspect",
        command="devflow task list",
        reason="No worker-ready task is available; inspect current task state.",
    )


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
