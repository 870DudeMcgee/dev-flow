from __future__ import annotations
from pathlib import Path
from typing import Any
import yaml
from pydantic import BaseModel, Field

from devflow.control_room.paths import goal_dir
from devflow.control_room.service import create_task


class GoalTaskSlice(BaseModel):
    task_id: str
    title: str
    summary: str
    slice_type: str | None = None
    acceptance_criteria: list[str] = Field(default_factory=list)
    required_artifacts: list[str] = Field(default_factory=list)
    blocked_by: list[str] = Field(default_factory=list)
    blocks: list[str] = Field(default_factory=list)
    parallel_safe: bool = False
    shared_files: list[str] = Field(default_factory=list)
    workspace_isolation_required: bool = False
    promotion_requires: Any = None
    risk: str = "medium"
    execution_mode: str = "HITL"
    context_budget: dict[str, Any] = Field(default_factory=dict)
    verification_policy: Any = Field(default_factory=dict)
    human_checkpoint_required: bool = False
    checkpoint_reason: str | None = None
    promotion_allowed: bool = False

    model_config = {"extra": "ignore"}


class CreatedGoalTask(BaseModel):
    goal_id: str
    slice_id: str
    task_id: str
    task_title: str
    task_path: str
    goal_path: str


def load_goal_task_slices(root: Path, goal_id: str) -> list[GoalTaskSlice]:
    """Load and parse task slices from a goal's task-slices.yaml."""
    g_dir = goal_dir(root, goal_id)
    if not g_dir.exists():
        raise KeyError(f"Goal not found: {goal_id}")

    slices_file = g_dir / "task-slices.yaml"
    if not slices_file.exists():
        raise FileNotFoundError(f"task-slices.yaml is missing for goal {goal_id}.")

    try:
        data = yaml.safe_load(slices_file.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"task-slices.yaml is malformed: {exc}")

    if not isinstance(data, dict):
        raise ValueError("task-slices.yaml content is not a mapping")

    slices_list = data.get("task_slices")
    if slices_list is None:
        return []

    if not isinstance(slices_list, list):
        raise ValueError("task_slices must be a list")

    parsed_slices = []
    for index, s in enumerate(slices_list):
        if not isinstance(s, dict):
            raise ValueError(f"Slice at index {index} is not a mapping")
        parsed_slices.append(GoalTaskSlice.model_validate(s))

    return parsed_slices


def get_goal_task_slice(root: Path, goal_id: str, slice_id: str) -> GoalTaskSlice:
    """Find a specific slice within a goal's parsed slices list."""
    slices = load_goal_task_slices(root, goal_id)
    for s in slices:
        if s.task_id == slice_id:
            return s
    raise ValueError(f"Slice ID '{slice_id}' not found in goal '{goal_id}'")


def render_goal_slices(root: Path, goal_id: str) -> str:
    """Format and render goal task slices in a compact reviewable format."""
    try:
        slices = load_goal_task_slices(root, goal_id)
    except KeyError as exc:
        # Match standard KeyErrors raised in other commands
        raise exc
    except Exception as exc:
        return f"Error: {exc}\n"

    if not slices:
        return (
            "No task slices found.\n"
            "Review:\n"
            f"  .devflow/goals/{goal_id}/task-slices.yaml\n"
        )

    lines = []
    lines.append(f"Task Slices for {goal_id}")
    lines.append("")
    lines.append(f"{'Slice':<10} {'Mode':<5} {'Risk':<7} {'Parallel':<8} {'Promotion':<10} Title")
    
    for s in slices:
        promo_status = "allowed" if s.promotion_allowed else "blocked"
        parallel_str = str(s.parallel_safe).lower()
        lines.append(
            f"{s.task_id:<10} {s.execution_mode:<5} {s.risk:<7} {parallel_str:<8} {promo_status:<10} {s.title}"
        )

    # Output detailed review cards for each slice
    for s in slices:
        lines.append("")
        lines.append("Details:")
        lines.append(f"  Summary: {s.summary}")
        lines.append("  Acceptance:")
        if s.acceptance_criteria:
            for ac in s.acceptance_criteria:
                lines.append(f"    - {ac}")
        else:
            lines.append("    - None")

        # Format Context
        ctx = s.context_budget or {}
        ctx_strat = ctx.get("strategy") or "focused_task_packet"
        ctx_risk = ctx.get("risk") or s.risk
        lines.append(f"  Context: {ctx_strat} / {ctx_risk}")

        # Format Verification
        vp = s.verification_policy
        if isinstance(vp, dict):
            vp_str = ", ".join(f"{k}={str(v).lower()}" for k, v in vp.items())
        else:
            vp_str = str(vp)
        lines.append(f"  Verification: {vp_str}")

    lines.append("")
    lines.append("Next:")
    lines.append(f"  devflow goal create-task {goal_id} {slices[0].task_id}")

    return "\n".join(lines) + "\n"


def create_task_from_goal_slice(root: Path, goal_id: str, slice_id: str) -> CreatedGoalTask:
    """Create a real DevFlow task folder and artifacts from a planning goal slice."""
    s = get_goal_task_slice(root, goal_id, slice_id)

    # 1. Create DevFlow task with workspaces/worktrees via existing service call
    task = create_task(root, title=s.title, git_worktree=s.workspace_isolation_required)
    task_id = task.id
    task_path = root / ".devflow" / "tasks" / task_id

    # 2. Write goal-link.yaml
    goal_link_path = task_path / "goal-link.yaml"
    goal_link_data = {
        "schema_version": 1,
        "goal_id": goal_id,
        "goal_path": f".devflow/goals/{goal_id}",
        "slice_id": slice_id,
        "slice_source_path": f".devflow/goals/{goal_id}/task-slices.yaml",
        "execution_mode": s.execution_mode,
        "human_checkpoint_required": s.human_checkpoint_required,
        "checkpoint_reason": s.checkpoint_reason or "",
        "promotion_allowed": s.promotion_allowed,
        "risk": s.risk,
        "context_strategy": (s.context_budget or {}).get("strategy") or "focused_task_packet",
        "created_from_goal_slice": True,
    }
    with open(goal_link_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(goal_link_data, f, default_flow_style=False, sort_keys=False)

    # 3. Write slice.md
    acceptance_list = "\n".join(f"  - {ac}" for ac in s.acceptance_criteria) if s.acceptance_criteria else "  - None"
    artifacts_list = "\n".join(f"  - {art}" for art in s.required_artifacts) if s.required_artifacts else "  - None"
    
    ctx = s.context_budget or {}
    ctx_strat = ctx.get("strategy") or "focused_task_packet"
    ctx_risk = ctx.get("risk") or s.risk
    ctx_tokens = ctx.get("estimated_tokens")
    tokens_str = str(ctx_tokens) if ctx_tokens is not None else "unknown"

    vp = s.verification_policy
    if isinstance(vp, dict):
        vp_str = ", ".join(f"{k}={str(v).lower()}" for k, v in vp.items())
    else:
        vp_str = str(vp)

    promo_req = s.promotion_requires
    if isinstance(promo_req, list):
        promo_req_str = ", ".join(promo_req)
    else:
        promo_req_str = str(promo_req) if promo_req is not None else "none"

    slice_md_content = f"""# Slice Details: {slice_id} (Goal: {goal_id})

- **Title**: {s.title}
- **Summary**: {s.summary}
- **Acceptance Criteria**:
{acceptance_list}
- **Required Artifacts**:
{artifacts_list}
- **Context Budget**:
  - Strategy: {ctx_strat}
  - Risk: {ctx_risk}
  - Estimated Tokens: {tokens_str}
- **Verification Policy**: {vp_str}
- **Human Checkpoint**:
  - Required: {s.human_checkpoint_required}
  - Reason: {s.checkpoint_reason or "none"}
- **Promotion Boundary**:
  - Allowed: {s.promotion_allowed}
  - Requires: {promo_req_str}
- **Source Pointers**:
  - .devflow/goals/{goal_id}/task-slices.yaml
"""
    (task_path / "slice.md").write_text(slice_md_content, encoding="utf-8")

    return CreatedGoalTask(
        goal_id=goal_id,
        slice_id=slice_id,
        task_id=task_id,
        task_title=s.title,
        task_path=f".devflow/tasks/{task_id}",
        goal_path=f".devflow/goals/{goal_id}",
    )
