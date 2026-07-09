from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel

from devflow.legacy.control_room.paths import goal_dir
from devflow.legacy.control_room.persistence import atomic_write_text, event_content_hash


GoalLifecycleValue = Literal["active", "paused", "blocked", "complete", "archived"]
ALLOWED_GOAL_LIFECYCLES = {"active", "paused", "blocked", "complete", "archived"}


class GoalLifecycleError(RuntimeError):
    pass


class GoalLifecycleState(BaseModel):
    schema_version: int = 1
    goal_id: str
    lifecycle: GoalLifecycleValue
    status_reason: str = ""
    created_at: str
    updated_at: str
    last_decision: str
    last_decision_command: str


class GoalLifecycleResult(BaseModel):
    goal_id: str
    lifecycle: GoalLifecycleValue
    status_reason: str
    goal_path: str
    state_path: str
    next_command: str


def read_goal_lifecycle(root: Path, goal_id: str) -> GoalLifecycleState | None:
    _require_goal(root, goal_id)
    path = _state_path(root, goal_id)
    if not path.exists():
        return None
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise GoalLifecycleError(f"goal-state.yaml is malformed for {goal_id}.")
    return GoalLifecycleState.model_validate(data)


def ensure_goal_lifecycle(root: Path, goal_id: str) -> GoalLifecycleState:
    existing = read_goal_lifecycle(root, goal_id)
    if existing is not None:
        return existing
    now = _now()
    state = GoalLifecycleState(
        goal_id=goal_id,
        lifecycle="active",
        status_reason="",
        created_at=now,
        updated_at=now,
        last_decision="activated",
        last_decision_command=f"devflow goal activate {goal_id}",
    )
    _write_state(root, state)
    _append_event(root, goal_id, "goal_lifecycle_created", state)
    return state


def set_goal_lifecycle(
    root: Path,
    goal_id: str,
    *,
    lifecycle: str,
    reason: str,
    command: str,
) -> GoalLifecycleState:
    _require_goal(root, goal_id)
    if lifecycle not in ALLOWED_GOAL_LIFECYCLES:
        raise GoalLifecycleError(f"Unsupported goal lifecycle: {lifecycle}")
    previous = read_goal_lifecycle(root, goal_id)
    now = _now()
    state = GoalLifecycleState(
        goal_id=goal_id,
        lifecycle=lifecycle,  # type: ignore[arg-type]
        status_reason=reason.strip(),
        created_at=previous.created_at if previous else now,
        updated_at=now,
        last_decision=_decision_for(lifecycle),
        last_decision_command=command,
    )
    _write_state(root, state)
    _append_event(root, goal_id, "goal_lifecycle_changed", state)
    return state


def lifecycle_result(root: Path, state: GoalLifecycleState) -> GoalLifecycleResult:
    return GoalLifecycleResult(
        goal_id=state.goal_id,
        lifecycle=state.lifecycle,
        status_reason=state.status_reason,
        goal_path=f".devflow/goals/{state.goal_id}",
        state_path=f".devflow/goals/{state.goal_id}/goal-state.yaml",
        next_command=_next_command(state),
    )


def render_lifecycle_result(result: GoalLifecycleResult) -> str:
    lines = [
        f"goal_id: {result.goal_id}",
        f"lifecycle: {result.lifecycle}",
        f"reason: {result.status_reason}",
        f"goal_path: {result.goal_path}",
        f"state_path: {result.state_path}",
        f"next: {result.next_command}",
    ]
    return "\n".join(lines) + "\n"


def _require_goal(root: Path, goal_id: str) -> None:
    if not (goal_dir(root, goal_id) / "goal.yaml").exists():
        raise GoalLifecycleError(f"Goal not found: {goal_id}")


def _state_path(root: Path, goal_id: str) -> Path:
    return goal_dir(root, goal_id) / "goal-state.yaml"


def _events_path(root: Path, goal_id: str) -> Path:
    return goal_dir(root, goal_id) / "events.jsonl"


def _write_state(root: Path, state: GoalLifecycleState) -> None:
    atomic_write_text(_state_path(root, state.goal_id), yaml.safe_dump(state.model_dump(), sort_keys=False))


def _append_event(root: Path, goal_id: str, event_name: str, state: GoalLifecycleState) -> None:
    path = _events_path(root, goal_id)
    previous_hash, next_index = _event_tail(path)
    event = {
        "timestamp": state.updated_at,
        "event": event_name,
        "event_index": next_index,
        "previous_event_hash": previous_hash,
        "goal_id": goal_id,
        "lifecycle": state.lifecycle,
        "status_reason": state.status_reason,
        "decision": state.last_decision,
        "command": state.last_decision_command,
    }
    event["event_hash"] = event_content_hash(event)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True) + "\n")


def _event_tail(path: Path) -> tuple[str | None, int]:
    if not path.exists():
        return None, 0
    previous_hash: str | None = None
    next_index = 0
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        if not raw_line.strip():
            continue
        try:
            event = json.loads(raw_line)
        except json.JSONDecodeError:
            break
        if not isinstance(event, dict):
            break
        previous_hash = event.get("event_hash") or event_content_hash(event)
        next_index += 1
    return previous_hash, next_index


def _decision_for(lifecycle: str) -> str:
    return {
        "active": "activated",
        "paused": "paused",
        "blocked": "blocked",
        "complete": "completed",
        "archived": "archived",
    }[lifecycle]


def _next_command(state: GoalLifecycleState) -> str:
    if state.lifecycle == "active":
        return "devflow freshness loop"
    return f"devflow goal status {state.goal_id}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
