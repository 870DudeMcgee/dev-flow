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
    recommendation: str
    command: str | None = None


class GoalParallelBatch(BaseModel):
    batch_id: str
    lane_ids: list[str] = Field(default_factory=list)
    commands: list[str] = Field(default_factory=list)
    shared_files: list[str] = Field(default_factory=list)
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
    blocked_lane_count: int
    next_action: str
    lanes: list[GoalLoopLane] = Field(default_factory=list)
    parallel_batches: list[GoalParallelBatch] = Field(default_factory=list)


def build_goal_loop_states(
    root: Path,
    goal_ids: list[str],
    goal_slices: dict[str, list[dict[str, Any]]],
    linked_tasks: dict[str, dict[str, list[dict[str, str]]]],
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
                blocked_lane_count=blocked_lane_count,
                next_action=_goal_loop_next_action(goal_id, loop_state, lanes, parallel_batches),
                lanes=lanes,
                parallel_batches=parallel_batches,
            )
        )
    return states


def _goal_loop_lane(goal_id: str, slice_data: dict[str, Any], linked: list[dict[str, str]]) -> GoalLoopLane:
    slice_id = str(slice_data.get("task_id") or "unknown-slice")
    title = str(slice_data.get("title") or slice_id)
    blockers = [str(item) for item in slice_data.get("blocked_by") or []]
    shared_files = sorted({str(item) for item in slice_data.get("shared_files") or [] if str(item).strip()})
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
