from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from devflow.control_room.freshness import FreshnessStatus, run_freshness_loop
from devflow.control_room.persistence import atomic_write_text
from devflow.control_room.project_registry import devflow_home, list_project_records


ProjectFreshnessStatus = Literal["ok", "stale", "needs_human_decision", "missing", "failed"]


class ProjectGoalLoopSummary(BaseModel):
    goal_id: str
    loop_state: str
    active_task_count: int
    completed_slice_count: int
    ready_parallel_lane_count: int
    ready_verification_batch_count: int = 0
    verification_command_count: int = 0
    next_action: str


class ProjectFreshnessSummary(BaseModel):
    project_id: str
    path: str
    path_status: str
    status: ProjectFreshnessStatus
    goals_checked: int = 0
    tasks_checked: int = 0
    linked_tasks_checked: int = 0
    active_task_count: int = 0
    ready_parallel_lane_count: int = 0
    ready_verification_batch_count: int = 0
    verification_command_count: int = 0
    checkpoint_opportunity: bool = False
    push_opportunity: bool = False
    snapshot_path: str | None = None
    next_action: str
    goals: list[ProjectGoalLoopSummary] = Field(default_factory=list)
    error: str | None = None


class MultiProjectFreshnessReport(BaseModel):
    schema_version: int = 1
    generated_at: str
    status: FreshnessStatus
    projects_checked: int
    missing_project_count: int
    failed_project_count: int
    stale_project_count: int
    needs_human_decision_project_count: int
    checkpoint_opportunity_count: int
    push_opportunity_count: int
    snapshot_path: str
    next_action: str
    projects: list[ProjectFreshnessSummary] = Field(default_factory=list)


def run_multi_project_freshness_loop(*, write_snapshot: bool = True) -> MultiProjectFreshnessReport:
    projects: list[ProjectFreshnessSummary] = []
    for record in list_project_records():
        root = Path(record.path).expanduser().resolve()
        if not root.is_dir():
            projects.append(
                ProjectFreshnessSummary(
                    project_id=record.project_id,
                    path=root.as_posix(),
                    path_status="missing",
                    status="missing",
                    next_action=f"Run `devflow project doctor {record.project_id}` and repair or archive the registry entry.",
                    error="project path is missing",
                )
            )
            continue
        try:
            report = run_freshness_loop(root, write_snapshot=write_snapshot)
        except Exception as exc:
            projects.append(
                ProjectFreshnessSummary(
                    project_id=record.project_id,
                    path=root.as_posix(),
                    path_status="present",
                    status="failed",
                    next_action=f"Run `devflow project doctor {record.project_id}` and inspect the project-local freshness inputs.",
                    error=str(exc),
                )
            )
            continue
        projects.append(_project_summary(record.project_id, root, report))

    status = _aggregate_status(projects)
    report = MultiProjectFreshnessReport(
        generated_at=datetime.now(timezone.utc).isoformat(),
        status=status,
        projects_checked=len(projects),
        missing_project_count=sum(1 for item in projects if item.status == "missing"),
        failed_project_count=sum(1 for item in projects if item.status == "failed"),
        stale_project_count=sum(1 for item in projects if item.status == "stale"),
        needs_human_decision_project_count=sum(1 for item in projects if item.status == "needs_human_decision"),
        checkpoint_opportunity_count=sum(1 for item in projects if item.checkpoint_opportunity),
        push_opportunity_count=sum(1 for item in projects if item.push_opportunity),
        snapshot_path=_aggregate_snapshot_path().as_posix(),
        next_action=_next_action(projects),
        projects=projects,
    )
    if write_snapshot:
        atomic_write_text(_aggregate_snapshot_path(), json.dumps(report.model_dump(), indent=2, sort_keys=True) + "\n")
    return report


def render_multi_project_freshness_report(report: MultiProjectFreshnessReport) -> str:
    lines = [
        "Multi-Project Freshness Loop",
        "",
        f"Status: {report.status}",
        f"Snapshot: {report.snapshot_path}",
        f"Projects: {report.projects_checked}",
        f"Checkpoint opportunities: {report.checkpoint_opportunity_count}",
        f"Push opportunities: {report.push_opportunity_count}",
        "",
        f"{'Project':<24} {'Status':<22} {'Goals':<5} {'Ready':<5} {'Verify':<6} {'Active':<6} Next",
        "-" * 96,
    ]
    if not report.projects:
        lines.append("No registered projects.")
    for project in report.projects:
        lines.append(
            f"{project.project_id:<24} {project.status:<22} {project.goals_checked:<5} "
            f"{project.ready_parallel_lane_count:<5} {project.ready_verification_batch_count:<6} "
            f"{project.active_task_count:<6} {project.next_action}"
        )
    lines.extend(["", "Next Action", f"  {report.next_action}"])
    return "\n".join(lines) + "\n"


def _project_summary(project_id: str, root: Path, report) -> ProjectFreshnessSummary:
    active_task_count = sum(goal.active_task_count for goal in report.goal_loop)
    ready_parallel_lane_count = sum(goal.ready_parallel_lane_count for goal in report.goal_loop)
    ready_verification_batch_count = sum(goal.ready_verification_batch_count for goal in report.goal_loop)
    verification_command_count = sum(goal.verification_command_count for goal in report.goal_loop)
    goals = [
        ProjectGoalLoopSummary(
            goal_id=goal.goal_id,
            loop_state=goal.loop_state,
            active_task_count=goal.active_task_count,
            completed_slice_count=goal.completed_slice_count,
            ready_parallel_lane_count=goal.ready_parallel_lane_count,
            ready_verification_batch_count=goal.ready_verification_batch_count,
            verification_command_count=goal.verification_command_count,
            next_action=goal.next_action,
        )
        for goal in report.goal_loop
    ]
    return ProjectFreshnessSummary(
        project_id=project_id,
        path=root.as_posix(),
        path_status="present",
        status=report.status,
        goals_checked=report.goals_checked,
        tasks_checked=report.tasks_checked,
        linked_tasks_checked=report.linked_tasks_checked,
        active_task_count=active_task_count,
        ready_parallel_lane_count=ready_parallel_lane_count,
        ready_verification_batch_count=ready_verification_batch_count,
        verification_command_count=verification_command_count,
        checkpoint_opportunity=report.loop_start_git.checkpoint_opportunity,
        push_opportunity=report.loop_start_git.push_opportunity,
        snapshot_path=report.snapshot_path,
        next_action=report.next_action,
        goals=goals,
    )


def _aggregate_snapshot_path() -> Path:
    return devflow_home() / "freshness" / "latest-all-projects.json"


def _aggregate_status(projects: list[ProjectFreshnessSummary]) -> FreshnessStatus:
    if any(project.status in {"needs_human_decision", "missing", "failed"} for project in projects):
        return "needs_human_decision"
    if any(project.status == "stale" for project in projects):
        return "stale"
    return "ok"


def _next_action(projects: list[ProjectFreshnessSummary]) -> str:
    for project in projects:
        if project.status in {"missing", "failed", "needs_human_decision"}:
            return project.next_action
    for project in projects:
        if project.push_opportunity:
            return f"Review `{project.project_id}` and run its approved push command if publication is allowed."
    for project in projects:
        if project.checkpoint_opportunity:
            return f"Review `{project.project_id}` and checkpoint verified work before spawning more tasks."
    return "Continue; registered project freshness has no detected blockers."
