from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class GoalLoopLane(BaseModel):
    slice_id: str
    title: str
    lane_state: str
    parallel_safe: bool
    risk: str
    execution_mode: str
    linked_task_ids: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    shared_files: list[str] = Field(default_factory=list)
    verification_policy: dict[str, Any] = Field(default_factory=dict)
    verification_scope: str = "none"
    verification_commands: list[str] = Field(default_factory=list)
    recommendation: str
    command: str | None = None


class GoalParallelBatch(BaseModel):
    batch_id: str
    lane_ids: list[str] = Field(default_factory=list)
    commands: list[str] = Field(default_factory=list)
    shared_files: list[str] = Field(default_factory=list)
    reason: str


class GoalVerificationItem(BaseModel):
    lane_id: str
    task_id: str
    command: str
    devflow_command: str


class GoalVerificationBatch(BaseModel):
    batch_id: str
    lane_ids: list[str] = Field(default_factory=list)
    task_ids: list[str] = Field(default_factory=list)
    items: list[GoalVerificationItem] = Field(default_factory=list)
    commands: list[str] = Field(default_factory=list)
    shared_files: list[str] = Field(default_factory=list)
    verification_scope: str
    reason: str


class GoalLoopState(BaseModel):
    goal_id: str
    title: str
    goal_state: str
    loop_state: str
    total_slices: int
    linked_task_count: int
    active_task_count: int
    completed_slice_count: int
    ready_parallel_lane_count: int
    ready_parallel_batch_count: int = 0
    conflicting_ready_lane_count: int = 0
    ready_verification_batch_count: int = 0
    verification_command_count: int = 0
    blocked_lane_count: int
    next_action: str
    lanes: list[GoalLoopLane] = Field(default_factory=list)
    parallel_batches: list[GoalParallelBatch] = Field(default_factory=list)
    verification_batches: list[GoalVerificationBatch] = Field(default_factory=list)


def build_goal_loop_states(
    root: Path,
    goal_ids: list[str],
    goal_slices: dict[str, list[dict[str, Any]]],
    linked_tasks: dict[str, dict[str, list[dict[str, Any]]]],
) -> list[GoalLoopState]:
    from devflow.control_room.goal_projection import build_goal_status_projection

    states: list[GoalLoopState] = []
    for goal_id in goal_ids:
        try:
            projection = build_goal_status_projection(root, goal_id)
            title = projection.title
            goal_state = projection.state
        except Exception:
            title = f"Goal {goal_id}"
            goal_state = "unknown"

        slices = goal_slices.get(goal_id, [])
        linked_by_slice = linked_tasks.get(goal_id, {})
        lanes = [
            _goal_loop_lane(goal_id, slice_data, linked_by_slice.get(str(slice_data.get("task_id") or ""), []))
            for slice_data in slices
            if slice_data.get("task_id")
        ]
        linked_task_count = sum(len(items) for items in linked_by_slice.values())
        active_task_count = sum(
            1
            for items in linked_by_slice.values()
            for task in items
            if task.get("status") not in {"closed", "promoted"}
        )
        completed_slice_count = sum(1 for lane in lanes if lane.lane_state == "complete")
        ready_parallel_lane_count = sum(1 for lane in lanes if lane.lane_state == "ready_to_create_task")
        parallel_batches = _parallel_batches(lanes)
        verification_batches = _verification_batches(lanes)
        conflicting_ready_lane_count = max(0, ready_parallel_lane_count - len(parallel_batches[0].lane_ids)) if parallel_batches else 0
        blocked_lane_count = sum(1 for lane in lanes if lane.lane_state in {"blocked", "needs_human_review"})
        loop_state = _goal_loop_state(
            goal_state=goal_state,
            total_slices=len(lanes),
            active_task_count=active_task_count,
            completed_slice_count=completed_slice_count,
            ready_parallel_lane_count=ready_parallel_lane_count,
            blocked_lane_count=blocked_lane_count,
        )
        states.append(
            GoalLoopState(
                goal_id=goal_id,
                title=title,
                goal_state=goal_state,
                loop_state=loop_state,
                total_slices=len(lanes),
                linked_task_count=linked_task_count,
                active_task_count=active_task_count,
                completed_slice_count=completed_slice_count,
                ready_parallel_lane_count=ready_parallel_lane_count,
                ready_parallel_batch_count=len(parallel_batches),
                conflicting_ready_lane_count=conflicting_ready_lane_count,
                ready_verification_batch_count=len(verification_batches),
                verification_command_count=sum(len(batch.commands) for batch in verification_batches),
                blocked_lane_count=blocked_lane_count,
                next_action=_goal_loop_next_action(goal_id, loop_state, lanes, parallel_batches),
                lanes=lanes,
                parallel_batches=parallel_batches,
                verification_batches=verification_batches,
            )
        )
    return states


def _goal_loop_lane(goal_id: str, slice_data: dict[str, Any], linked: list[dict[str, Any]]) -> GoalLoopLane:
    slice_id = str(slice_data.get("task_id") or "unknown-slice")
    title = str(slice_data.get("title") or slice_id)
    blockers = [str(item) for item in slice_data.get("blocked_by") or []]
    shared_files = sorted({str(item) for item in slice_data.get("shared_files") or [] if str(item).strip()})
    verification_policy = _normalize_verification_policy(slice_data.get("verification_policy"))
    verification_commands = _verification_commands_from_policy(verification_policy)
    risk = str(slice_data.get("risk") or "medium").lower()
    execution_mode = str(slice_data.get("execution_mode") or "HITL").upper()
    parallel_safe = bool(slice_data.get("parallel_safe"))
    linked_sorted = sorted(linked, key=lambda item: item.get("updated_at") or "")
    latest = linked_sorted[-1] if linked_sorted else None
    linked_task_ids = [str(item.get("task_id")) for item in linked_sorted if item.get("task_id")]

    if linked and any(item.get("status") == "promoted" for item in linked):
        lane_state = "complete"
        recommendation = "Slice already has promoted task evidence."
        command = None
    elif latest and latest.get("status") == "closed":
        lane_state = "closed"
        recommendation = "Slice has closed task evidence; review closure before creating new work."
        command = f"devflow task show {latest['task_id']}"
    elif blockers:
        lane_state = "blocked"
        recommendation = "Wait for blocker slices before creating more work."
        command = f"devflow goal status {goal_id}"
    elif latest and latest.get("status") == "running":
        lane_state = "running"
        recommendation = "Keep this active task visible; do not spawn a competing writer for the same slice."
        command = f"devflow task show {latest['task_id']}"
    elif latest and latest.get("verification_status") == "failed":
        lane_state = "repair_or_verify"
        recommendation = "Repair the existing task workspace, then rerun verification."
        command = f"devflow task next-action {latest['task_id']}"
    elif latest and (latest.get("status") == "verified" or latest.get("verification_status") == "passed"):
        lane_state = "ready_to_promote"
        recommendation = "Review promotion readiness for the verified task."
        command = f"devflow task promote-preview {latest['task_id']}"
    elif latest:
        lane_state = "ready_to_run_or_verify"
        recommendation = "Continue the existing linked task before creating another lane."
        command = f"devflow task next-action {latest['task_id']}"
    elif parallel_safe and risk != "high":
        lane_state = "ready_to_create_task"
        recommendation = "Safe candidate for parallel task creation in its own isolated workspace."
        command = f"devflow goal create-task {goal_id} {slice_id}"
    else:
        lane_state = "needs_human_review"
        recommendation = "Review sequential, high-risk, or non-parallel-safe slice before spawning work."
        command = f"devflow goal status {goal_id}"

    if not verification_commands and latest and lane_state in {"ready_to_run_or_verify", "repair_or_verify"}:
        verification_commands = _dedupe(_command_values(latest.get("verification_command")))
    verification_scope = _verification_scope(verification_policy)
    if verification_scope == "none" and verification_commands:
        verification_scope = "custom"

    return GoalLoopLane(
        slice_id=slice_id,
        title=title,
        lane_state=lane_state,
        parallel_safe=parallel_safe,
        risk=risk,
        execution_mode=execution_mode,
        linked_task_ids=linked_task_ids,
        blockers=blockers,
        shared_files=shared_files,
        verification_policy=verification_policy,
        verification_scope=verification_scope,
        verification_commands=verification_commands,
        recommendation=recommendation,
        command=command,
    )


def _goal_loop_state(
    *,
    goal_state: str,
    total_slices: int,
    active_task_count: int,
    completed_slice_count: int,
    ready_parallel_lane_count: int,
    blocked_lane_count: int,
) -> str:
    if goal_state == "blocked":
        return "blocked"
    if total_slices and completed_slice_count == total_slices:
        return "needs_closure_decision"
    if ready_parallel_lane_count:
        return "ready_for_parallel_task_creation"
    if active_task_count:
        return "active_work_in_progress"
    if total_slices and blocked_lane_count == total_slices:
        return "blocked"
    if total_slices:
        return "planning_review"
    return goal_state


def _parallel_batches(lanes: list[GoalLoopLane]) -> list[GoalParallelBatch]:
    batches: list[dict[str, object]] = []
    ready = [lane for lane in lanes if lane.lane_state == "ready_to_create_task"]
    for lane in ready:
        lane_files = set(lane.shared_files)
        selected: dict[str, object] | None = None
        for batch in batches:
            batch_files = batch["shared_files_set"]
            if not lane_files or not batch_files or lane_files.isdisjoint(batch_files):  # type: ignore[arg-type]
                selected = batch
                break
        if selected is None:
            selected = {"lanes": [], "commands": [], "shared_files_set": set()}
            batches.append(selected)
        selected["lanes"].append(lane)  # type: ignore[union-attr]
        if lane.command:
            selected["commands"].append(lane.command)  # type: ignore[union-attr]
        selected["shared_files_set"].update(lane_files)  # type: ignore[union-attr]

    return [
        GoalParallelBatch(
            batch_id=f"PB-{index:04d}",
            lane_ids=[lane.slice_id for lane in batch["lanes"]],  # type: ignore[index]
            commands=list(batch["commands"]),  # type: ignore[arg-type]
            shared_files=sorted(batch["shared_files_set"]),  # type: ignore[arg-type]
            reason="Lanes in this batch have no declared shared file conflicts.",
        )
        for index, batch in enumerate(batches, start=1)
    ]


def _verification_batches(lanes: list[GoalLoopLane]) -> list[GoalVerificationBatch]:
    batches: list[dict[str, object]] = []
    ready = [
        lane
        for lane in lanes
        if lane.lane_state in {"ready_to_run_or_verify", "repair_or_verify"}
        and lane.linked_task_ids
        and lane.verification_commands
    ]
    for lane in ready:
        lane_files = set(lane.shared_files)
        selected: dict[str, object] | None = None
        for batch in batches:
            batch_files = batch["shared_files_set"]
            if not lane_files or not batch_files or lane_files.isdisjoint(batch_files):  # type: ignore[arg-type]
                selected = batch
                break
        if selected is None:
            selected = {"lanes": [], "items": [], "commands": [], "shared_files_set": set(), "scopes": set()}
            batches.append(selected)

        task_id = lane.linked_task_ids[-1]
        selected["lanes"].append(lane)  # type: ignore[union-attr]
        for command in lane.verification_commands:
            devflow_command = f"devflow task verify {task_id} -- {command}"
            selected["items"].append(  # type: ignore[union-attr]
                GoalVerificationItem(
                    lane_id=lane.slice_id,
                    task_id=task_id,
                    command=command,
                    devflow_command=devflow_command,
                )
            )
            selected["commands"].append(devflow_command)  # type: ignore[union-attr]
        selected["shared_files_set"].update(lane_files)  # type: ignore[union-attr]
        selected["scopes"].add(lane.verification_scope)  # type: ignore[union-attr]

    return [
        GoalVerificationBatch(
            batch_id=f"VB-{index:04d}",
            lane_ids=[lane.slice_id for lane in batch["lanes"]],  # type: ignore[index]
            task_ids=[lane.linked_task_ids[-1] for lane in batch["lanes"]],  # type: ignore[index]
            items=list(batch["items"]),  # type: ignore[arg-type]
            commands=list(batch["commands"]),  # type: ignore[arg-type]
            shared_files=sorted(batch["shared_files_set"]),  # type: ignore[arg-type]
            verification_scope=_batch_scope(batch["scopes"]),  # type: ignore[arg-type]
            reason="Verification commands in this batch have no declared shared file conflicts.",
        )
        for index, batch in enumerate(batches, start=1)
    ]


def _normalize_verification_policy(raw_policy: Any) -> dict[str, Any]:
    if isinstance(raw_policy, dict):
        return {str(key): value for key, value in raw_policy.items()}
    if isinstance(raw_policy, str) and raw_policy.strip():
        return {"policy_type": raw_policy.strip()}
    return {}


def _verification_commands_from_policy(policy: dict[str, Any]) -> list[str]:
    keys = (
        "commands",
        "verification_commands",
        "test_commands",
        "focused_commands",
        "focused_test_commands",
        "targeted_commands",
        "targeted_tests",
        "broad_commands",
        "broad_test_commands",
        "full_commands",
    )
    commands: list[str] = []
    for key in keys:
        commands.extend(_command_values(policy.get(key)))
    return _dedupe(commands)


def _command_values(value: Any) -> list[str]:
    if isinstance(value, str):
        stripped = value.strip()
        return [stripped] if stripped else []
    if isinstance(value, list):
        commands: list[str] = []
        for item in value:
            if isinstance(item, dict):
                commands.extend(_command_values(item.get("command")))
            else:
                commands.extend(_command_values(item))
        return commands
    return []


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            deduped.append(value)
    return deduped


def _verification_scope(policy: dict[str, Any]) -> str:
    if not policy:
        return "none"
    has_focused = bool(
        policy.get("focused_tests_required")
        or policy.get("test_first_required")
        or policy.get("red_green_required")
        or _command_values(policy.get("focused_commands"))
        or _command_values(policy.get("focused_test_commands"))
        or _command_values(policy.get("targeted_commands"))
        or _command_values(policy.get("targeted_tests"))
    )
    has_broad = bool(
        policy.get("broad_boundary_tests_required")
        or _command_values(policy.get("broad_commands"))
        or _command_values(policy.get("broad_test_commands"))
        or _command_values(policy.get("full_commands"))
    )
    if has_focused and has_broad:
        return "focused_and_broad"
    if has_broad:
        return "broad"
    if has_focused:
        return "focused"
    if _verification_commands_from_policy(policy):
        return "custom"
    return "policy_only"


def _batch_scope(scopes: set[str]) -> str:
    normalized = {scope for scope in scopes if scope and scope != "none"}
    if not normalized:
        return "none"
    if len(normalized) == 1:
        return next(iter(normalized))
    return "mixed"


def _goal_loop_next_action(
    goal_id: str,
    loop_state: str,
    lanes: list[GoalLoopLane],
    parallel_batches: list[GoalParallelBatch],
) -> str:
    if loop_state == "ready_for_parallel_task_creation":
        if parallel_batches:
            return "Parallel batch PB-0001: " + "; ".join(parallel_batches[0].commands)
        ready = [lane for lane in lanes if lane.lane_state == "ready_to_create_task"]
        commands = [lane.command for lane in ready if lane.command]
        return "Parallel candidates: " + "; ".join(commands)
    if loop_state == "needs_closure_decision":
        return f"Ask whether {goal_id} is complete or needs another slice."
    if loop_state == "active_work_in_progress":
        active = [lane.command for lane in lanes if lane.command and lane.lane_state != "ready_to_create_task"]
        return active[0] if active else f"devflow goal status {goal_id}"
    if loop_state == "blocked":
        return f"devflow goal status {goal_id}"
    return f"devflow goal status {goal_id}"
