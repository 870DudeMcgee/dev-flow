from __future__ import annotations

from pathlib import Path
import os
import time
import json
import subprocess
from datetime import datetime
from typing import Any
from pydantic import BaseModel

from devflow.control_room.operator_readiness import OperatorReadinessSnapshot, build_operator_readiness_snapshot
from devflow.control_room.status_projection import (
    ProjectedNextAction,
    TaskStatusProjection,
    choose_task_dashboard_action,
    choose_task_focus_projection,
    list_task_status_projections,
)

# --- Dashboard State Models ---

class DashboardProject(BaseModel):
    root: str
    branch: str | None = None
    working_tree: str | None = None
    context_loaded: bool | None = None

class DashboardHealth(BaseModel):
    total_tasks: int
    active_tasks: int
    blocked_tasks: int
    needs_verification: int
    failed_verification: int
    verified_tasks: int
    ready_to_promote: int
    promoted_tasks: int
    worker_failed: int
    timeout: int

class DashboardNextAction(ProjectedNextAction):
    pass

class FocusTaskState(BaseModel):
    id: str
    title: str
    status: str
    display_status: str
    worker: str
    verification_status: str
    latest: str


class DashboardFocusGoal(BaseModel):
    goal_id: str
    state: str
    open_question_count: int
    task_slice_count: int
    context_risk: str | None = None


class DashboardGoals(BaseModel):
    total: int
    focus_goal: DashboardFocusGoal | None = None


class DashboardState(BaseModel):
    project: DashboardProject
    health: DashboardHealth
    focus_task: FocusTaskState | None = None
    blockers: list[TaskStatusProjection] = []
    needs_verification: list[TaskStatusProjection] = []
    failed_verification: list[TaskStatusProjection] = []
    ready_to_promote: list[TaskStatusProjection] = []
    recent_activity: list[dict[str, str]] = []
    next_action: DashboardNextAction
    tasks: list[TaskStatusProjection] = []
    goals: DashboardGoals | None = None
    operator_readiness: OperatorReadinessSnapshot | None = None

    model_config = {"arbitrary_types_allowed": True}


class MultiProjectDashboardItem(BaseModel):
    project_id: str
    name: str
    path: str
    status: str
    path_status: str
    source_control_mode: str
    branch: str | None = None
    working_tree: str | None = None
    total_tasks: int = 0
    active_tasks: int = 0
    needs_verification: int = 0
    ready_to_promote: int = 0
    detail: str | None = None


class MultiProjectDashboardState(BaseModel):
    registry_path: str
    projects_root: str
    total_projects: int
    active_projects: int
    missing_projects: int
    total_tasks: int
    active_tasks: int
    needs_verification: int
    ready_to_promote: int
    projects: list[MultiProjectDashboardItem]


# --- Git and Project Helpers ---

def _git_branch(root: Path) -> str | None:
    try:
        res = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=2
        )
        if res.returncode == 0:
            return res.stdout.strip() or None
    except Exception:
        pass
    return None

def _git_working_tree(root: Path) -> str | None:
    try:
        res = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=2
        )
        if res.returncode == 0:
            if not res.stdout.strip():
                return "clean"
            return "dirty"
    except Exception:
        pass
    return None

def _context_loaded(root: Path) -> bool:
    return (
        (root / ".devflow" / "project" / "project.yaml").exists() or 
        (root / ".devflow" / "context" / "active" / "README.md").exists()
    )

# --- Focus Task and Next Action Logic ---

def find_focus_task(projections: list[TaskStatusProjection]) -> TaskStatusProjection | None:
    return choose_task_focus_projection(projections)


def _dashboard_action(action: ProjectedNextAction) -> DashboardNextAction:
    return DashboardNextAction(**action.model_dump())

def choose_dashboard_next_action(state: DashboardState) -> DashboardNextAction:
    focus = state.focus_task
    if not focus:
        return DashboardNextAction(
            label="Create a task",
            task_id=None,
            command='devflow task create "<title>"',
            reason="No tasks found."
        )

    focus_proj = None
    for p in state.tasks:
        if p.task.id == focus.id:
            focus_proj = p
            break

    if not focus_proj:
        return DashboardNextAction(
            label="Inspect task",
            task_id=focus.id,
            command=f"devflow task show {focus.id}",
            reason="Focus task details not found."
        )

    return _dashboard_action(focus_proj.dashboard_next_action)


def choose_focus_goal_projection(goal_projections: list[Any], task_projections: list[Any]) -> Any | None:
    if not goal_projections:
        return None

    def get_sort_key(p: Any):
        ts = 0.0
        try:
            if p.updated_at:
                ts = datetime.fromisoformat(p.updated_at).timestamp()
            elif p.created_at:
                ts = datetime.fromisoformat(p.created_at).timestamp()
        except Exception:
            pass
        return (ts, p.goal_id)

    # 1. Goal with implementation_blocked=true
    tier1 = [p for p in goal_projections if p.implementation_blocked]
    if tier1:
        return max(tier1, key=get_sort_key)

    # 2. Goal with open questions
    tier2 = [p for p in goal_projections if p.open_question_count > 0]
    if tier2:
        return max(tier2, key=get_sort_key)

    # 3. Goal with task slices and no corresponding created tasks
    tier3 = [p for p in goal_projections if p.task_slice_count > 0 and len(task_projections) == 0]
    if tier3:
        return max(tier3, key=get_sort_key)

    # 4. Most recently modified goal
    # 5. Highest goal id
    return max(goal_projections, key=get_sort_key)


def choose_dashboard_next_action_v2(state: DashboardState, goal_projections: list[Any]) -> DashboardNextAction:
    task_action = choose_task_dashboard_action(state.tasks, max_priority=50)
    if task_action is not None:
        return _dashboard_action(task_action)

    # 1. Goal with implementation blocked / open questions
    blocked_goals = [g for g in goal_projections if g.state == "blocked"]
    if blocked_goals:
        def get_goal_sort_key(p: Any):
            ts = 0.0
            try:
                if p.updated_at:
                    ts = datetime.fromisoformat(p.updated_at).timestamp()
                elif p.created_at:
                    ts = datetime.fromisoformat(p.created_at).timestamp()
            except Exception:
                pass
            return (ts, p.goal_id)
        g = max(blocked_goals, key=get_goal_sort_key)
        return DashboardNextAction(
            label="Resolve goal blocker",
            task_id=None,
            command=f"devflow goal status {g.goal_id}",
            reason="Implementation is blocked on open questions."
        )

    # 2. Goal with task slices ready for review
    ready_goals = [g for g in goal_projections if g.state == "ready_for_task_creation"]
    if ready_goals:
        def get_goal_sort_key(p: Any):
            ts = 0.0
            try:
                if p.updated_at:
                    ts = datetime.fromisoformat(p.updated_at).timestamp()
                elif p.created_at:
                    ts = datetime.fromisoformat(p.created_at).timestamp()
            except Exception:
                pass
            return (ts, p.goal_id)
        g = max(ready_goals, key=get_goal_sort_key)
        return DashboardNextAction(
            label="Create or review task slice",
            task_id=None,
            command=f"devflow goal status {g.goal_id}",
            reason="Goal task slices are ready for review."
        )

    task_action = choose_task_dashboard_action(state.tasks)
    if task_action is not None:
        return _dashboard_action(task_action)

    # 3. No goals and no tasks
    if not goal_projections and not state.tasks:
        return DashboardNextAction(
            label="Create a task",
            task_id=None,
            command='devflow task create "<title>"',
            reason="No tasks found."
        )


    # Fallback to single task focus next action if no global matches but we have focus task
    if state.focus_task:
        return choose_dashboard_next_action(state)

    # Absolute fallback
    return DashboardNextAction(
        label="Create a task",
        task_id=None,
        command='devflow task create "<title>"',
        reason="No safer automated action was inferred."
    )


def _collect_recent_activity(projections: list[TaskStatusProjection]) -> list[dict[str, str]]:
    all_events = []
    for proj in projections:
        task_id = proj.task.id
        events_file = proj.task_path / "events.jsonl"
        if not events_file.exists():
            continue
        try:
            lines = events_file.read_text(encoding="utf-8").splitlines()
            for line in lines:
                if not line.strip():
                    continue
                try:
                    evt = json.loads(line)
                    if isinstance(evt, dict) and "event" in evt:
                        all_events.append({
                            "task_id": task_id,
                            "event": evt["event"],
                            "timestamp": evt.get("timestamp") or ""
                        })
                except Exception:
                    pass
        except Exception:
            pass

    def sort_key(e: dict[str, str]):
        t = e.get("timestamp") or ""
        return (t, e.get("task_id") or "")

    all_events.sort(key=sort_key, reverse=True)
    return all_events[:20]

# --- Public API Functions ---

def collect_dashboard_state(repo_root: Path | None = None) -> DashboardState:
    root = (repo_root or Path.cwd()).resolve()
    projections = list_task_status_projections(root)
    operator_readiness = build_operator_readiness_snapshot(root)
    
    branch = _git_branch(root)
    working_tree = _git_working_tree(root)
    context_loaded = _context_loaded(root)
    project = DashboardProject(
        root=str(root),
        branch=branch,
        working_tree=working_tree,
        context_loaded=context_loaded
    )
    
    total_tasks = len(projections)
    active_tasks = 0
    blocked_tasks_count = 0
    needs_verification_count = 0
    failed_verification_count = 0
    verified_tasks_count = 0
    ready_to_promote_count = 0
    promoted_tasks_count = 0
    worker_failed_count = 0
    timeout_count = 0

    blockers: list[TaskStatusProjection] = []
    needs_verification: list[TaskStatusProjection] = []
    failed_verification: list[TaskStatusProjection] = []
    ready_to_promote: list[TaskStatusProjection] = []

    for proj in projections:
        task = proj.task

        if proj.is_active:
            active_tasks += 1

        if proj.is_blocked:
            blocked_tasks_count += 1
            blockers.append(proj)

        if proj.needs_verification:
            needs_verification_count += 1
            needs_verification.append(proj)

        if proj.failed_verification:
            failed_verification_count += 1
            failed_verification.append(proj)

        if proj.is_verified:
            verified_tasks_count += 1

        if proj.ready_to_promote:
            ready_to_promote_count += 1
            ready_to_promote.append(proj)

        if task.status == "promoted":
            promoted_tasks_count += 1

        if proj.is_worker_failed:
            worker_failed_count += 1

        if proj.is_timeout:
            timeout_count += 1

    health = DashboardHealth(
        total_tasks=total_tasks,
        active_tasks=active_tasks,
        blocked_tasks=blocked_tasks_count,
        needs_verification=needs_verification_count,
        failed_verification=failed_verification_count,
        verified_tasks=verified_tasks_count,
        ready_to_promote=ready_to_promote_count,
        promoted_tasks=promoted_tasks_count,
        worker_failed=worker_failed_count,
        timeout=timeout_count
    )

    focus_proj = find_focus_task(projections)
    focus_state = None
    if focus_proj:
        focus_state = FocusTaskState(
            id=focus_proj.task.id,
            title=focus_proj.task.title,
            status=focus_proj.task.status,
            display_status=focus_proj.display_status,
            worker=focus_proj.task.worker,
            verification_status=focus_proj.verification_status,
            latest=focus_proj.latest
        )

    recent_activity = _collect_recent_activity(projections)

    from devflow.control_room.goal_projection import list_goal_status_projections
    goal_projections = list_goal_status_projections(root)

    focus_goal_proj = choose_focus_goal_projection(goal_projections, projections)
    focus_goal = None
    if focus_goal_proj:
        focus_goal = DashboardFocusGoal(
            goal_id=focus_goal_proj.goal_id,
            state=focus_goal_proj.state,
            open_question_count=focus_goal_proj.open_question_count,
            task_slice_count=focus_goal_proj.task_slice_count,
            context_risk=focus_goal_proj.context_risk,
        )

    goals_state = DashboardGoals(
        total=len(goal_projections),
        focus_goal=focus_goal
    )

    dummy_next = DashboardNextAction(label="", reason="")
    state = DashboardState(
        project=project,
        health=health,
        focus_task=focus_state,
        blockers=blockers,
        needs_verification=needs_verification,
        failed_verification=failed_verification,
        ready_to_promote=ready_to_promote,
        recent_activity=recent_activity,
        next_action=dummy_next,
        tasks=projections,
        goals=goals_state,
        operator_readiness=operator_readiness,
    )
    
    state.next_action = choose_dashboard_next_action_v2(state, goal_projections)
    if (
        operator_readiness.next_safe_action.kind in {"repair_goal_lifecycle", "inspect_stale_directive"}
        and operator_readiness.next_safe_action.command
    ):
        state.next_action = DashboardNextAction(
            label="Operator readiness",
            command=operator_readiness.next_safe_action.command,
            reason=operator_readiness.next_safe_action.reason,
        )
    return state


def collect_multi_project_dashboard_state(*, include_archived: bool = False) -> MultiProjectDashboardState:
    from devflow.control_room.project_registry import load_registry, registry_path

    registry = load_registry()
    records = [
        record for record in registry.projects
        if include_archived or record.status != "archived"
    ]
    projects: list[MultiProjectDashboardItem] = []
    for record in records:
        root = Path(record.path)
        if not root.exists():
            projects.append(
                MultiProjectDashboardItem(
                    project_id=record.project_id,
                    name=record.name,
                    path=record.path,
                    status=record.status,
                    path_status="missing",
                    source_control_mode=record.source_control_mode,
                    detail="project path is missing",
                )
            )
            continue
        try:
            state = collect_dashboard_state(root)
            projects.append(
                MultiProjectDashboardItem(
                    project_id=record.project_id,
                    name=record.name,
                    path=record.path,
                    status=record.status,
                    path_status="present",
                    source_control_mode=record.source_control_mode,
                    branch=state.project.branch,
                    working_tree=state.project.working_tree,
                    total_tasks=state.health.total_tasks,
                    active_tasks=state.health.active_tasks,
                    needs_verification=state.health.needs_verification,
                    ready_to_promote=state.health.ready_to_promote,
                )
            )
        except Exception as exc:
            projects.append(
                MultiProjectDashboardItem(
                    project_id=record.project_id,
                    name=record.name,
                    path=record.path,
                    status=record.status,
                    path_status="present",
                    source_control_mode=record.source_control_mode,
                    detail=f"dashboard unavailable: {exc}",
                )
            )

    return MultiProjectDashboardState(
        registry_path=registry_path().as_posix(),
        projects_root=registry.projects_root,
        total_projects=len(projects),
        active_projects=sum(1 for project in projects if project.status == "active" and project.path_status == "present"),
        missing_projects=sum(1 for project in projects if project.path_status == "missing"),
        total_tasks=sum(project.total_tasks for project in projects),
        active_tasks=sum(project.active_tasks for project in projects),
        needs_verification=sum(project.needs_verification for project in projects),
        ready_to_promote=sum(project.ready_to_promote for project in projects),
        projects=projects,
    )


def render_multi_project_dashboard(*, include_archived: bool = False) -> str:
    state = collect_multi_project_dashboard_state(include_archived=include_archived)
    lines = [
        "Dev-Flow Multi-Project Control Room",
        "",
        "Registry",
        f"  Path: {state.registry_path}",
        f"  Projects root: {state.projects_root}",
        "",
        "Project Health",
        f"  Total projects: {state.total_projects}",
        f"  Active projects: {state.active_projects}",
        f"  Missing projects: {state.missing_projects}",
        f"  Total tasks: {state.total_tasks}",
        f"  Active tasks: {state.active_tasks}",
        f"  Needs verification: {state.needs_verification}",
        f"  Ready to promote: {state.ready_to_promote}",
        "",
        f"{'Project':<24} {'Status':<10} {'Path':<8} {'Tasks':<6} {'Active':<6} {'Verify':<6} {'Promote':<7} Branch",
        "-" * 104,
    ]
    if not state.projects:
        lines.append("No projects registered.")
    for project in state.projects:
        lines.append(
            f"{project.project_id:<24} {project.status:<10} {project.path_status:<8} "
            f"{project.total_tasks:<6} {project.active_tasks:<6} "
            f"{project.needs_verification:<6} {project.ready_to_promote:<7} {project.branch or 'unknown'}"
        )
        if project.detail:
            lines.append(f"  detail: {project.detail}")
        lines.append(f"  root: {project.path}")
    return "\n".join(lines) + "\n"


def render_multi_project_dashboard_json(*, include_archived: bool = False) -> str:
    state = collect_multi_project_dashboard_state(include_archived=include_archived)
    return json.dumps(state.model_dump(mode="json"), sort_keys=True, indent=2) + "\n"


def render_dashboard(repo_root: Path | None = None) -> str:
    state = collect_dashboard_state(repo_root)
    lines = []
    
    lines.append("Dev-Flow Control Room")
    lines.append("")
    
    lines.append("Project")
    lines.append(f"  Root: {state.project.root}")
    lines.append(f"  Branch: {state.project.branch or 'unknown'}")
    lines.append(f"  Working tree: {state.project.working_tree or 'unknown'}")
    context_str = "loaded" if state.project.context_loaded else "not loaded"
    lines.append(f"  Context: {context_str}")
    lines.append("")
    
    lines.append("Goals")
    if state.goals:
        lines.append(f"  Total: {state.goals.total}")
        if state.goals.focus_goal:
            fg = state.goals.focus_goal
            lines.append(f"  Active: {fg.goal_id}")
            lines.append(f"  State: {fg.state}")
            lines.append(f"  Open questions: {fg.open_question_count}")
            lines.append(f"  Task slices: {fg.task_slice_count}")
            lines.append(f"  Context risk: {fg.context_risk or 'medium'}")
        else:
            lines.append("  Active: None")
    else:
        lines.append("  Total: 0")
        lines.append("  Active: None")
    lines.append("")

    lines.append("Task Health")
    lines.append(f"  Total: {state.health.total_tasks}")
    lines.append(f"  Active: {state.health.active_tasks}")
    lines.append(f"  Blocked: {state.health.blocked_tasks}")
    lines.append(f"  Needs verification: {state.health.needs_verification}")
    lines.append(f"  Failed verification: {state.health.failed_verification}")
    lines.append(f"  Verified: {state.health.verified_tasks}")
    lines.append(f"  Ready to promote: {state.health.ready_to_promote}")
    lines.append(f"  Promoted: {state.health.promoted_tasks}")
    lines.append("")

    if state.operator_readiness:
        operator_counts = state.operator_readiness.counts
        lines.append("Operator Readiness")
        lines.append(f"  Worker ready: {operator_counts.get('worker_ready', 0)}")
        lines.append(f"  Lifecycle blocked: {operator_counts.get('lifecycle_blocked', 0)}")
        lines.append(f"  Warnings: {operator_counts.get('warnings', 0)}")
        lines.append(f"  Next: {state.operator_readiness.next_safe_action.command or 'None'}")
        lines.append("")
    
    lines.append("Current Focus")
    goal_str = state.goals.focus_goal.goal_id if (state.goals and state.goals.focus_goal) else "None"
    lines.append(f"  Goal: {goal_str}")
    if state.focus_task:
        lines.append(f"  Task: {state.focus_task.id} — {state.focus_task.title}")
        lines.append(f"  Status: {state.focus_task.status}")
        lines.append(f"  Worker: {state.focus_task.worker}")
        lines.append(f"  Verify: {state.focus_task.verification_status}")
        lines.append(f"  Latest: {state.focus_task.latest}")
        lines.append(f"  Next: {state.next_action.command or 'None'}")
    else:
        lines.append("  Task: None")
    lines.append("")

    
    lines.append("Blockers")
    if state.blockers:
        for proj in state.blockers:
            reason = proj.manual_agent_question or proj.latest or proj.suggested_next_action
            lines.append(f"  {proj.task.id:<10} {proj.display_status:<17} {reason}")
    else:
        lines.append("  None")
    lines.append("")
    
    lines.append("Verification")
    has_verification = False
    for proj in state.failed_verification:
        lines.append(f"  {proj.task.id:<10} verification failed")
        has_verification = True
    for proj in state.needs_verification:
        lines.append(f"  {proj.task.id:<10} needs verification")
        has_verification = True
    if not has_verification:
        lines.append("  None")
    lines.append("")
    
    lines.append("Promotion Readiness")
    if state.ready_to_promote:
        for proj in state.ready_to_promote:
            lines.append(f"  {proj.task.id:<10} ready to promote")
    else:
        lines.append("  None")
    lines.append("")
    
    lines.append("Recent Activity")
    if state.recent_activity:
        for act in state.recent_activity[:10]:
            lines.append(f"  {act['task_id']:<10} {act['event']}")
    else:
        lines.append("  None")
    lines.append("")
    
    lines.append("Next Action")
    lines.append(f"  {state.next_action.command or 'None'}")
    lines.append("")


    # --- Render backward compatible Tasks List with 2-spaces indentation ---
    lines.append(f"{'Task':<10} {'Status':<20} {'Verify':<12} {'Worker':<8} Latest")
    lines.append("-" * 82)
    if not state.tasks:
        lines.append("No tasks found.")
    for projection in state.tasks:
        task = projection.task
        lines.append(
            f"{task.id:<10} {projection.display_status:<20} {projection.verification_status:<12} "
            f"{task.worker:<8} {projection.latest}"
        )
        lines.append(f"  workspace: {task.workspace}")
        if task.log_path:
            lines.append(f"  log: {task.log_path}")
        if task.result_path:
            lines.append(f"  result: {task.result_path}")
        if projection.manual_agent_state:
            lines.append(f"  manual_agent_state: {projection.manual_agent_state}")
            if projection.manual_agent_handoff_path:
                lines.append(f"  manual_agent_handoff: {projection.manual_agent_handoff_path}")
            if projection.manual_agent_question:
                lines.append(f"  manual_agent_question: {projection.manual_agent_question}")
            if projection.manual_agent_failure:
                lines.append(f"  manual_agent_failure: {projection.manual_agent_failure}")
        if projection.verification_exit_code is not None:
            lines.append(f"  verification_exit_code: {projection.verification_exit_code}")
        if projection.verification_log_path:
            lines.append(f"  verification_log: {projection.verification_log_path}")
        if projection.merge_ready is not None:
            merge_ready = "yes" if projection.merge_ready else "no"
            lines.append(f"  merge_ready: {merge_ready}")
    
    return "\n".join(lines) + "\n"

def render_dashboard_json(repo_root: Path | None = None) -> str:
    state = collect_dashboard_state(repo_root)
    data = state.model_dump(mode="json")
    
    def clean_obj(obj: Any) -> Any:
        if isinstance(obj, Path):
            return str(obj)
        elif isinstance(obj, dict):
            return {k: clean_obj(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [clean_obj(x) for x in obj]
        return obj

    cleaned_data = clean_obj(data)
    return json.dumps(cleaned_data, sort_keys=True, indent=2) + "\n"

def render_next_action(repo_root: Path | None = None) -> str:
    state = collect_dashboard_state(repo_root)
    na = state.next_action
    lines = [
        f"Next Action: {na.label}",
        f"Command: {na.command or 'None'}",
        f"Reason: {na.reason}",
    ]
    return "\n".join(lines) + "\n"

def render_task_history(repo_root: Path, task_id: str, limit: int = 20) -> str:
    task_dir_path = repo_root / ".devflow" / "tasks" / task_id
    events_file = task_dir_path / "events.jsonl"
    
    lines = [
        f"Task History: {task_id}",
        "-" * 50,
    ]
    
    if not events_file.exists():
        lines.append("No history found. Events file does not exist.")
        return "\n".join(lines) + "\n"
        
    try:
        content = events_file.read_text(encoding="utf-8")
    except Exception as exc:
        lines.append(f"Error reading history file: {exc}")
        return "\n".join(lines) + "\n"
        
    raw_lines = content.splitlines()
    events = []
    
    for raw_line in raw_lines:
        if not raw_line.strip():
            continue
        try:
            evt = json.loads(raw_line)
            if isinstance(evt, dict):
                events.append(evt)
            else:
                events.append({"event": "malformed_event", "detail": "Event is not a JSON object"})
        except json.JSONDecodeError:
            events.append({"event": "malformed_event", "detail": "Invalid JSON line"})
            
    if not events:
        lines.append("No history found. Events file is empty.")
        return "\n".join(lines) + "\n"
        
    events = events[-limit:]
    
    for evt in events:
        t = evt.get("timestamp") or ""
        name = evt.get("event") or "unknown_event"
        
        extra = []
        for key in ("status", "exit_code", "error_message", "detail", "worker", "command"):
            if key in evt and evt[key] is not None:
                extra.append(f"{key}={evt[key]}")
        
        extra_str = f" ({', '.join(extra)})" if extra else ""
        lines.append(f"  {t:<30} {name}{extra_str}")
        
    return "\n".join(lines) + "\n"

# --- Keep existing runner working ---

def run_dashboard(refresh_seconds: int = 0) -> None:
    while True:
        if refresh_seconds:
            os.system("clear")
        print(render_dashboard(Path.cwd()), end="")
        if not refresh_seconds:
            return
        time.sleep(refresh_seconds)
