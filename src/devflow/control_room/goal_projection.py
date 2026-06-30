from __future__ import annotations

import re
from pathlib import Path
from typing import Any
import yaml
from pydantic import BaseModel

from devflow.control_room.paths import goal_dir, goals_dir


class GoalNextAction(BaseModel):
    label: str
    command: str | None = None
    reason: str


class GoalStatusProjection(BaseModel):
    goal_id: str
    goal_path: str
    title: str
    summary: str
    state: str
    created_at: str | None = None
    updated_at: str | None = None
    open_question_count: int = 0
    implementation_blocked: bool = False
    task_slice_count: int = 0
    blocked_slice_count: int = 0
    afk_slice_count: int = 0
    hitl_slice_count: int = 0
    high_risk_slice_count: int = 0
    lifecycle: str = "missing"
    lifecycle_reason: str = ""
    lifecycle_missing: bool = False
    context_risk: str | None = None
    estimated_context_tokens: int | None = None
    required_context_count: int = 0
    optional_context_count: int = 0
    forbidden_context_count: int = 0
    stale_or_archived_context_count: int = 0
    next_action_label: str
    next_action_command: str | None = None
    next_action_reason: str
    latest_activity: str | None = None
    warnings: list[str] = []

    model_config = {"arbitrary_types_allowed": True}


def list_goal_status_projections(
    root: Path,
    *,
    warnings: list[str] | None = None,
) -> list[GoalStatusProjection]:
    """Scan and return status projections for all durable goals, ordered by ID."""
    dir_path = goals_dir(root)
    if not dir_path.exists():
        return []

    projections = []
    pattern = re.compile(r"^G-(\d{4})$")
    for item in sorted(dir_path.iterdir()):
        if item.is_dir() and pattern.match(item.name):
            try:
                proj = build_goal_status_projection(root, item.name)
                projections.append(proj)
                if warnings is not None:
                    warnings.extend(proj.warnings)
            except Exception as exc:
                if warnings is not None:
                    warnings.append(
                        f"warning: failed to project goal at {item.as_posix()}: {exc}"
                    )
                continue

    return projections


def _load_goal_yaml_mapping(
    path: Path,
    warnings: list[str],
    file_name: str,
) -> tuple[dict[str, Any], bool]:
    """Load a YAML file that is expected to be a mapping."""
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:
        warnings.append(f"warning: {file_name} is malformed: {exc}")
        return {}, False

    if data is None:
        return {}, True
    if not isinstance(data, dict):
        warnings.append(f"warning: {file_name} must be a mapping")
        return {}, False
    return data, True


def build_goal_status_projection(root: Path, goal_id: str) -> GoalStatusProjection:
    """Build a stable read-only projection of a single goal and its artifacts."""
    g_dir = goal_dir(root, goal_id)
    goal_yaml_path = g_dir / "goal.yaml"
    
    # 1. Retrieve metadata
    created_at = None
    updated_at = None
    warnings: list[str] = []

    if goal_yaml_path.exists():
        try:
            yaml_lines = goal_yaml_path.read_text(encoding="utf-8").splitlines()
            for line in yaml_lines:
                if ":" in line:
                    k, v = line.split(":", 1)
                    k = k.strip()
                    v = v.strip()
                    if k == "created_at":
                        created_at = v
                    elif k == "updated_at":
                        updated_at = v
        except Exception as exc:
            warnings.append(f"warning: goal.yaml is unreadable: {exc}")
    else:
        warnings.append("warning: goal.yaml is missing")

    # 2. Load explicit lifecycle state without creating missing lifecycle artifacts.
    lifecycle = "missing"
    lifecycle_reason = ""
    lifecycle_missing = True
    try:
        from devflow.control_room.goal_lifecycle import read_goal_lifecycle

        lifecycle_state = read_goal_lifecycle(root, goal_id)
        if lifecycle_state is not None:
            lifecycle = lifecycle_state.lifecycle
            lifecycle_reason = lifecycle_state.status_reason
            lifecycle_missing = False
    except Exception as exc:
        lifecycle = "unknown"
        lifecycle_reason = str(exc)
        lifecycle_missing = False
        warnings.append(f"warning: goal-state.yaml is unreadable: {exc}")

    # 3. Parse title & summary from goal.md
    title = f"Goal {goal_id}"
    summary = ""
    goal_md_exists = False
    if (g_dir / "goal.md").exists():
        goal_md_exists = True
        try:
            content = (g_dir / "goal.md").read_text(encoding="utf-8")
            lines = [ln.strip() for ln in content.splitlines() if ln.strip()]
            if lines:
                title_line = lines[0]
                if title_line.startswith("# Goal:"):
                    title = title_line.replace("# Goal:", "").strip()
                elif title_line.startswith("#"):
                    title = title_line.lstrip("#").strip()
                
                body_lines = [ln for ln in lines if not ln.startswith("#") and not ln.startswith("-")][:3]
                if body_lines:
                    summary = " ".join(body_lines)[:100]
        except Exception as exc:
            warnings.append(f"warning: goal.md is unreadable: {exc}")
    else:
        warnings.append("warning: goal.md is missing")

    # 4. Parse open questions safely
    open_questions_data: dict[str, Any] = {}
    open_question_count = 0
    implementation_blocked = False
    if (g_dir / "open-questions.yaml").exists():
        open_questions_data, _ = _load_goal_yaml_mapping(
            g_dir / "open-questions.yaml",
            warnings,
            "open-questions.yaml",
        )
    
    questions = open_questions_data.get("questions")
    if isinstance(questions, list):
        open_question_count = len(questions)
    implementation_blocked = bool(open_questions_data.get("implementation_blocked", False))

    # 5. Parse task slices safely
    task_slices_data: dict[str, Any] = {}
    task_slices_is_mapping = False
    task_slice_count = 0
    blocked_slice_count = 0
    afk_slice_count = 0
    hitl_slice_count = 0
    high_risk_slice_count = 0

    if (g_dir / "task-slices.yaml").exists():
        task_slices_data, task_slices_is_mapping = _load_goal_yaml_mapping(
            g_dir / "task-slices.yaml",
            warnings,
            "task-slices.yaml",
        )

    if task_slices_is_mapping:
        slices = task_slices_data.get("task_slices")
        if isinstance(slices, list):
            task_slice_count = len(slices)
            for s in slices:
                if not isinstance(s, dict):
                    continue

                # Check blocked_by
                blocked_by = s.get("blocked_by")
                if isinstance(blocked_by, list) and len(blocked_by) > 0:
                    blocked_slice_count += 1

                # Check execution mode
                mode = str(s.get("execution_mode") or "").strip().upper()
                if mode == "AFK":
                    afk_slice_count += 1
                elif mode == "HITL":
                    hitl_slice_count += 1

                # Check risk
                risk = str(s.get("risk") or "").strip().lower()
                if risk == "high":
                    high_risk_slice_count += 1
        elif (g_dir / "task-slices.yaml").exists() and not isinstance(slices, list):
            warnings.append("warning: task-slices.yaml task_slices must be a list")

    # 6. Parse context pointers safely
    context_data: dict[str, Any] = {}
    context_risk = "medium"
    estimated_context_tokens = None
    required_context_count = 0
    optional_context_count = 0
    forbidden_context_count = 0
    stale_or_archived_context_count = 0

    if (g_dir / "context-pointers.yaml").exists():
        context_data, _ = _load_goal_yaml_mapping(
            g_dir / "context-pointers.yaml",
            warnings,
            "context-pointers.yaml",
        )
            
    budget = context_data.get("context_budget") or {}
    if isinstance(budget, dict):
        context_risk = budget.get("risk", "medium")
        estimated_context_tokens = budget.get("estimated_tokens")
        
    req = context_data.get("required_context")
    if isinstance(req, list):
        required_context_count = len(req)
    opt = context_data.get("optional_context")
    if isinstance(opt, list):
        optional_context_count = len(opt)
    forb = context_data.get("forbidden_context")
    if isinstance(forb, list):
        forbidden_context_count = len(forb)
    stale = context_data.get("stale_or_archived_context")
    if isinstance(stale, list):
        stale_or_archived_context_count = len(stale)

    # 7. Check other artifacts
    grill_md_exists = (g_dir / "grill.md").exists() and (g_dir / "grill.md").stat().st_size > 0
    prd_md_exists = (g_dir / "prd.md").exists() and (g_dir / "prd.md").stat().st_size > 0

    # 8. Infer Goal State
    # Check hierarchy: blocked, ready_for_task_creation, sliced, specced, grilled, draft_goal, unknown
    if any("malformed" in w for w in warnings):
        state = "unknown"
    elif implementation_blocked or open_question_count > 0:
        state = "blocked"
    elif task_slice_count > 0:
        # Check if at least one slice is unblocked
        unblocked_exists = False
        if isinstance(slices, list):
            for s in slices:
                if isinstance(s, dict):
                    blocked_by = s.get("blocked_by")
                    if not blocked_by:
                        unblocked_exists = True
                        break
        if unblocked_exists:
            state = "ready_for_task_creation"
        else:
            state = "blocked"
    elif (g_dir / "task-slices.yaml").exists():
        state = "sliced"
    elif prd_md_exists:
        state = "specced"
    elif grill_md_exists:
        state = "grilled"
    elif goal_md_exists:
        state = "draft_goal"
    else:
        state = "unknown"

    # Assemble dummy projection to compute next action
    temp_proj = GoalStatusProjection(
        goal_id=goal_id,
        goal_path=g_dir.as_posix(),
        title=title,
        summary=summary,
        state=state,
        created_at=created_at,
        updated_at=updated_at,
        open_question_count=open_question_count,
        implementation_blocked=implementation_blocked,
        task_slice_count=task_slice_count,
        blocked_slice_count=blocked_slice_count,
        afk_slice_count=afk_slice_count,
        hitl_slice_count=hitl_slice_count,
        high_risk_slice_count=high_risk_slice_count,
        lifecycle=lifecycle,
        lifecycle_reason=lifecycle_reason,
        lifecycle_missing=lifecycle_missing,
        context_risk=context_risk,
        estimated_context_tokens=estimated_context_tokens,
        required_context_count=required_context_count,
        optional_context_count=optional_context_count,
        forbidden_context_count=forbidden_context_count,
        stale_or_archived_context_count=stale_or_archived_context_count,
        next_action_label="",
        next_action_reason="",
        latest_activity=updated_at or created_at,
        warnings=warnings,
    )

    next_action = choose_goal_next_action(temp_proj)
    temp_proj.next_action_label = next_action.label
    temp_proj.next_action_command = next_action.command
    temp_proj.next_action_reason = next_action.reason

    return temp_proj


def choose_goal_next_action(projection: GoalStatusProjection) -> GoalNextAction:
    """Determine the next action for a goal based on its current inferred state."""
    goal_id = projection.goal_id
    state = projection.state

    if projection.lifecycle_missing:
        return GoalNextAction(
            label="Activate goal",
            command=f"devflow goal activate {goal_id} --reason 'ready to execute'",
            reason="Lifecycle state is missing; activate the goal before execution dispatch.",
        )
    if projection.lifecycle == "paused":
        return GoalNextAction(
            label="Goal is paused",
            command=f"devflow goal status {goal_id}",
            reason=projection.lifecycle_reason or "Goal execution is paused.",
        )
    if projection.lifecycle == "blocked":
        return GoalNextAction(
            label="Goal is blocked",
            command=f"devflow goal status {goal_id}",
            reason=projection.lifecycle_reason or "Goal execution is blocked.",
        )
    if projection.lifecycle in {"complete", "archived"}:
        return GoalNextAction(
            label=f"Goal is {projection.lifecycle}",
            command=f"devflow goal status {goal_id}",
            reason=projection.lifecycle_reason or f"Goal lifecycle is {projection.lifecycle}.",
        )

    if state == "blocked":
        return GoalNextAction(
            label="Resolve goal questions",
            command=f"devflow goal status {goal_id}",
            reason="Implementation is blocked on open questions."
        )
    elif state == "ready_for_task_creation":
        return GoalNextAction(
            label="Create or review the first task slice",
            command=f"devflow goal status {goal_id}",
            reason="Create or review the first task slice."
        )
    elif state == "draft_goal":
        return GoalNextAction(
            label="Complete goal grilling",
            command=f"devflow goal status {goal_id}",
            reason="Goal is in draft state. Complete grilling/PRD sessions."
        )
    elif state == "grilled":
        return GoalNextAction(
            label="Complete PRD spec",
            command=f"devflow goal status {goal_id}",
            reason="Grilling complete; draft the PRD."
        )
    elif state == "specced":
        return GoalNextAction(
            label="Slice goal into tasks",
            command=f"devflow goal status {goal_id}",
            reason="PRD drafted; slice requirements into task slices."
        )
    elif state == "sliced":
        return GoalNextAction(
            label="Review task slices",
            command=f"devflow goal status {goal_id}",
            reason="Task slices generated; ready for review."
        )
    
    return GoalNextAction(
        label="Inspect goal",
        command=f"devflow goal status {goal_id}",
        reason="Check goal status for next step."
    )


def render_goal_status(root: Path, goal_id: str) -> str:
    """Render a detailed status dashboard card for a single goal."""
    try:
        proj = build_goal_status_projection(root, goal_id)
    except Exception as exc:
        return f"Error building goal status projection for {goal_id}: {exc}\n"

    g_dir = Path(proj.goal_path)
    lines = []
    lines.append("Goal Status")
    lines.append("")
    lines.append(f"{proj.goal_id} — {proj.title}")
    lines.append("")
    lines.append(f"State: {proj.state}")
    lines.append(f"Lifecycle: {proj.lifecycle}")
    lines.append(f"Lifecycle reason: {proj.lifecycle_reason or '-'}")
    lines.append(f"Path: .devflow/goals/{proj.goal_id}")
    lines.append("")
    
    lines.append("Planning Artifacts")
    for fn in [
        "goal.md", "grill.md", "prd.md", "decisions.yaml",
        "open-questions.yaml", "context-pointers.yaml",
        "task-slices.yaml", "handoff.md"
    ]:
        status = "present" if (g_dir / fn).exists() else "missing"
        # If any parsing warning mentions this file, we can optionally mark it,
        # but matching requested shape exactly:
        lines.append(f"  {fn}: {status}")

    lines.append("")
    lines.append("Questions")
    lines.append(f"  Open: {proj.open_question_count}")
    blocked_str = "true" if proj.implementation_blocked else "false"
    lines.append(f"  Implementation blocked: {blocked_str}")

    lines.append("")
    lines.append("Task Slices")
    lines.append(f"  Total: {proj.task_slice_count}")
    lines.append(f"  Blocked: {proj.blocked_slice_count}")
    lines.append(f"  AFK: {proj.afk_slice_count}")
    lines.append(f"  HITL: {proj.hitl_slice_count}")
    lines.append(f"  High risk: {proj.high_risk_slice_count}")

    lines.append("")
    lines.append("Context")
    lines.append(f"  Risk: {proj.context_risk or 'medium'}")
    tokens_str = str(proj.estimated_context_tokens) if proj.estimated_context_tokens is not None else "unknown"
    lines.append(f"  Estimated tokens: {tokens_str}")
    lines.append(f"  Required pointers: {proj.required_context_count}")
    lines.append(f"  Optional pointers: {proj.optional_context_count}")
    lines.append(f"  Forbidden pointers: {proj.forbidden_context_count}")
    lines.append(f"  Stale/archive pointers: {proj.stale_or_archived_context_count}")

    lines.append("")
    lines.append("Next Action")
    lines.append(f"  {proj.next_action_reason}")
    lines.append("  Command:")
    lines.append(f"    {proj.next_action_command or 'None'}")

    if proj.warnings:
        lines.append("")
        lines.append("Warnings")
        for w in proj.warnings:
            lines.append(f"  - {w}")

    return "\n".join(lines) + "\n"


def render_goal_list(root: Path) -> str:
    """Render a compact table of all durable goals."""
    projections = list_goal_status_projections(root)
    if not projections:
        return "No goals found.\nCreate one with:\n  devflow goal init --from <goal.md>\n"

    lines = []
    lines.append("Goals")
    lines.append("")
    lines.append(f"{'Goal':<8} {'State':<22} {'Questions':<10} {'Slices':<7} {'Context':<8} Next")
    for proj in projections:
        # Match expected:
        # G-0001   ready_for_task_creation 0          1       medium   devflow goal status G-0001
        lines.append(
            f"{proj.goal_id:<8} {proj.state:<22} {proj.open_question_count:<10} "
            f"{proj.task_slice_count:<7} {proj.context_risk or 'medium':<8} {proj.next_action_command or 'None'}"
        )

    return "\n".join(lines) + "\n"
