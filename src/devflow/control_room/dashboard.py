from __future__ import annotations

from pathlib import Path
import os
import time
import json
import subprocess
from datetime import datetime
from typing import Any
from pydantic import BaseModel

from devflow.control_room.status_projection import list_task_status_projections, TaskStatusProjection
from devflow.control_room.readiness import promotion_readiness_errors

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

class DashboardNextAction(BaseModel):
    label: str
    task_id: str | None = None
    command: str | None = None
    reason: str

class FocusTaskState(BaseModel):
    id: str
    title: str
    status: str
    display_status: str
    worker: str
    verification_status: str
    latest: str

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

    model_config = {"arbitrary_types_allowed": True}

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
    if not projections:
        return None

    def get_sort_key(p: TaskStatusProjection):
        ts = p.task.updated_at.timestamp() if p.task.updated_at else 0.0
        return (ts, p.task.id)

    # 1. Blocked task with human question/manual-agent blocker
    tier1 = [
        p for p in projections 
        if p.display_status in ("blocked", "blocked_question", "awaiting_human") or 
           p.manual_agent_state == "blocked" or 
           p.manual_agent_question is not None or 
           p.task.status == "blocked"
    ]
    if tier1:
        return max(tier1, key=get_sort_key)

    # 2. Verification failed task
    tier2 = [p for p in projections if p.task.status == "verification_failed" or p.verification_status == "failed"]
    if tier2:
        return max(tier2, key=get_sort_key)

    # 3. Complete task needing verification
    tier3 = [
        p for p in projections
        if p.task.status == "complete" or
           (p.manual_agent_state == "result_present" and p.verification_status != "passed") or
           (p.verification_status in ("not_run", "pending") and p.task.status not in ("promoted", "verified", "created"))
    ]
    if tier3:
        return max(tier3, key=get_sort_key)

    # 4. Verified task ready to promote
    def is_ready(p: TaskStatusProjection):
        return (
            (p.task.status == "verified" or p.verification_status == "passed") and 
            not promotion_readiness_errors(p.task, p.task_path)
        )

    tier4 = [p for p in projections if is_ready(p)]
    if tier4:
        return max(tier4, key=get_sort_key)

    # 5. Created task that has not run
    tier5 = [p for p in projections if p.task.status == "created"]
    if tier5:
        return max(tier5, key=get_sort_key)

    # 6. Running task
    tier6 = [p for p in projections if p.task.status == "running"]
    if tier6:
        return max(tier6, key=get_sort_key)

    # 7. Most recently updated non-promoted task
    tier7 = [p for p in projections if p.task.status != "promoted"]
    if tier7:
        return max(tier7, key=get_sort_key)

    # Fallback
    return max(projections, key=get_sort_key)

def choose_dashboard_next_action(state: DashboardState) -> DashboardNextAction:
    focus = state.focus_task
    if not focus:
        return DashboardNextAction(
            label="Create a task",
            task_id=None,
            command='devflow task create "<title>"',
            reason="No tasks found."
        )

    # Find the projection for the focus task
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

    task_id = focus.id
    status = focus_proj.task.status
    disp_status = focus_proj.display_status

    # Blocked
    if (disp_status in ("blocked", "blocked_question", "awaiting_human") or 
        focus_proj.manual_agent_question is not None or 
        status == "blocked"):
        return DashboardNextAction(
            label="Resolve blocker",
            task_id=task_id,
            command=f"devflow task show {task_id}",
            reason="Manual worker blocked on a question."
        )

    # Verification failed
    if status == "verification_failed" or focus_proj.verification_status == "failed":
        return DashboardNextAction(
            label="Inspect verification failure",
            task_id=task_id,
            command=f"devflow task log {task_id} --verify --tail 80",
            reason="Verification failed and needs inspection before rerun."
        )

    # Complete / Needs verification
    if (status == "complete" or 
        (focus_proj.manual_agent_state == "result_present" and focus_proj.verification_status != "passed") or 
        (focus_proj.verification_status in ("not_run", "pending") and status not in ("promoted", "verified", "created"))):
        return DashboardNextAction(
            label="Run verification",
            task_id=task_id,
            command=f"devflow task verify {task_id} --shell \"<command>\"",
            reason="Worker completed but verification has not passed."
        )

    # Verified and ready to promote
    is_ready_to_promote = (
        (status == "verified" or focus_proj.verification_status == "passed") and 
        not promotion_readiness_errors(focus_proj.task, focus_proj.task_path)
    )
    if is_ready_to_promote:
        return DashboardNextAction(
            label="Preview promotion",
            task_id=task_id,
            command=f"devflow task promote-preview {task_id}",
            reason="Verification passed; user should review promotion before promote."
        )

    # Created
    if status == "created":
        return DashboardNextAction(
            label="Run task",
            task_id=task_id,
            command=f"devflow task run {task_id} --worker shell -- <command>",
            reason="Task exists but no worker has run."
        )

    # Running
    if status == "running":
        return DashboardNextAction(
            label="Inspect task",
            task_id=task_id,
            command=f"devflow task show {task_id}",
            reason="Task is running or in progress."
        )

    # Worker failed
    if status == "worker_failed" or disp_status == "worker_failed":
        return DashboardNextAction(
            label="Inspect worker failure",
            task_id=task_id,
            command=f"devflow task log {task_id} --tail 80",
            reason="Worker failed and logs should be inspected."
        )

    # Timeout
    if status == "timeout":
        return DashboardNextAction(
            label="Inspect timeout",
            task_id=task_id,
            command=f"devflow task log {task_id} --tail 80",
            reason="Worker timed out."
        )

    # Fallback
    return DashboardNextAction(
        label="Inspect task",
        task_id=task_id,
        command=f"devflow task show {task_id}",
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
        disp_status = proj.display_status
        verification_status = proj.verification_status

        if task.status not in ("promoted", "verified"):
            active_tasks += 1

        is_blocked = (disp_status in ("blocked", "blocked_question", "awaiting_human") or task.status == "blocked")
        if is_blocked:
            blocked_tasks_count += 1
            blockers.append(proj)

        is_needs_verify = (
            task.status == "complete" or
            (verification_status in ("not_run", "pending") and task.status != "promoted" and task.status != "created") or
            (task.worker == "devflow-manual-codex-worker" and proj.manual_agent_state == "result_present" and verification_status != "passed")
        )
        if is_needs_verify:
            needs_verification_count += 1
            needs_verification.append(proj)

        is_failed_verify = (task.status == "verification_failed" or verification_status == "failed")
        if is_failed_verify:
            failed_verification_count += 1
            failed_verification.append(proj)

        is_verified = (task.status == "verified" or verification_status == "passed")
        if is_verified:
            verified_tasks_count += 1

        is_ready = is_verified and len(promotion_readiness_errors(task, proj.task_path)) == 0
        if is_ready:
            ready_to_promote_count += 1
            ready_to_promote.append(proj)

        if task.status == "promoted":
            promoted_tasks_count += 1

        if task.status == "worker_failed" or disp_status == "worker_failed":
            worker_failed_count += 1

        if task.status == "timeout":
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
        tasks=projections
    )
    
    state.next_action = choose_dashboard_next_action(state)
    return state

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
    
    lines.append("Current Focus")
    if state.focus_task:
        lines.append(f"  {state.focus_task.id:<10} {state.focus_task.title}")
        lines.append(f"  Status: {state.focus_task.status}")
        lines.append(f"  Worker: {state.focus_task.worker}")
        lines.append(f"  Verify: {state.focus_task.verification_status}")
        lines.append(f"  Latest: {state.focus_task.latest}")
        lines.append(f"  Next: {state.next_action.command or 'None'}")
    else:
        lines.append("  None")
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
    
    lines.append("Recommended Next Command")
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
