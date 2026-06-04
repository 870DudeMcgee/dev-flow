from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field

from devflow.control_room.goal_loop import GoalLoopState, build_goal_loop_states
from devflow.control_room.paths import devflow_dir, goal_dir, goals_dir, relative_path, task_dir
from devflow.control_room.persistence import atomic_write_text, list_tasks


FreshnessStatus = Literal["ok", "stale", "needs_human_decision"]
FindingSeverity = Literal["info", "stale", "needs_human_decision"]


class FreshnessFinding(BaseModel):
    id: str
    severity: FindingSeverity
    scope: str
    path: str
    message: str
    evidence: dict[str, Any] = Field(default_factory=dict)
    question: str | None = None
    suggested_action: str


class LoopStartGitDecision(BaseModel):
    is_repo: bool
    branch: str | None = None
    head_sha: str | None = None
    clean: bool
    checkpoint_opportunity: bool
    push_opportunity: bool
    recommended_action: str
    command: str | None = None
    reason: str
    changed_file_count: int = 0
    main_ahead_origin_main: int | None = None
    main_behind_origin_main: int | None = None


class FreshnessReport(BaseModel):
    schema_version: int = 1
    generated_at: str
    status: FreshnessStatus
    state_hash: str
    loop_start_git: LoopStartGitDecision
    goal_loop: list[GoalLoopState] = Field(default_factory=list)
    goals_checked: int
    tasks_checked: int
    linked_tasks_checked: int
    stale_count: int
    needs_human_decision_count: int
    findings: list[FreshnessFinding] = Field(default_factory=list)
    snapshot_path: str
    next_action: str


def run_freshness_loop(root: Path, *, write_snapshot: bool = True) -> FreshnessReport:
    """Run one freshness-control iteration and update derived freshness state."""
    findings: list[FreshnessFinding] = []
    loop_start_git = _loop_start_git_decision(root)
    linked_tasks = _linked_tasks_by_goal_slice(root, findings)
    goals = _goal_ids(root)
    goal_slices = {goal_id: _load_goal_slices(root, goal_id, findings) for goal_id in goals}

    for goal_id in goals:
        _check_goal_against_linked_tasks(
            root,
            goal_id,
            linked_tasks.get(goal_id, {}),
            goal_slices.get(goal_id, []),
            findings,
        )

    status = _status_for(findings)
    goal_loop = build_goal_loop_states(root, goals, goal_slices, linked_tasks)
    state_hash = _state_hash(root, goals, linked_tasks, findings, goal_loop)
    report = FreshnessReport(
        generated_at=datetime.now(timezone.utc).isoformat(),
        status=status,
        state_hash=state_hash,
        loop_start_git=loop_start_git,
        goal_loop=goal_loop,
        goals_checked=len(goals),
        tasks_checked=len(list_tasks(root)),
        linked_tasks_checked=sum(len(tasks) for slices in linked_tasks.values() for tasks in slices.values()),
        stale_count=sum(1 for finding in findings if finding.severity == "stale"),
        needs_human_decision_count=sum(1 for finding in findings if finding.severity == "needs_human_decision"),
        findings=findings,
        snapshot_path=relative_path(root, _freshness_snapshot_path(root)),
        next_action=_next_action_for(status),
    )
    if write_snapshot:
        atomic_write_text(
            _freshness_snapshot_path(root),
            json.dumps(report.model_dump(), indent=2, sort_keys=True) + "\n",
        )
    return report


def render_freshness_report(report: FreshnessReport) -> str:
    lines = [
        "Freshness Loop",
        "",
        f"Status: {report.status}",
        f"Snapshot: {report.snapshot_path}",
        f"State hash: {report.state_hash}",
        "",
        "Loop Start Git Decision",
        f"  Recommended: {report.loop_start_git.recommended_action}",
        f"  Reason: {report.loop_start_git.reason}",
        f"  Clean: {'yes' if report.loop_start_git.clean else 'no'}",
        f"  Checkpoint opportunity: {'yes' if report.loop_start_git.checkpoint_opportunity else 'no'}",
        f"  Push opportunity: {'yes' if report.loop_start_git.push_opportunity else 'no'}",
    ]
    if report.loop_start_git.command:
        lines.append(f"  Command: {report.loop_start_git.command}")
    lines.extend(
        [
            "",
            "State Tested",
            f"  Goals: {report.goals_checked}",
            f"  Tasks: {report.tasks_checked}",
            f"  Linked tasks: {report.linked_tasks_checked}",
            f"  Stale findings: {report.stale_count}",
            f"  Human decisions: {report.needs_human_decision_count}",
            "",
            "Goal Loop",
        ]
    )
    if report.goal_loop:
        for goal in report.goal_loop:
            lines.append(
                f"  - {goal.goal_id}: {goal.loop_state} "
                f"(ready_parallel={goal.ready_parallel_lane_count}, active={goal.active_task_count}, complete={goal.completed_slice_count}/{goal.total_slices})"
            )
            lines.append(f"    next: {goal.next_action}")
    else:
        lines.append("  None")
    lines.append("")
    if report.findings:
        lines.append("Findings")
        for finding in report.findings:
            lines.append(f"  - [{finding.severity}] {finding.id}")
            lines.append(f"    scope: {finding.scope}")
            lines.append(f"    path: {finding.path}")
            lines.append(f"    message: {finding.message}")
            if finding.question:
                lines.append(f"    question: {finding.question}")
            lines.append(f"    next: {finding.suggested_action}")
        lines.append("")
    else:
        lines.append("Findings")
        lines.append("  None")
        lines.append("")

    lines.append("Next Action")
    lines.append(f"  {report.next_action}")
    return "\n".join(lines) + "\n"


def _freshness_snapshot_path(root: Path) -> Path:
    return devflow_dir(root) / "freshness" / "latest.json"


def _loop_start_git_decision(root: Path) -> LoopStartGitDecision:
    from devflow.control_room.git_state import inspect_git_state

    state = inspect_git_state(root)
    if not state.is_repo:
        return LoopStartGitDecision(
            is_repo=False,
            clean=True,
            checkpoint_opportunity=False,
            push_opportunity=False,
            recommended_action="skip_git",
            reason="This project is not inside a Git repository.",
        )

    changed_count = state.counts.staged + state.counts.unstaged + state.counts.untracked + len(state.conflicted_files)

    base = {
        "is_repo": True,
        "branch": state.branch,
        "head_sha": state.head_sha,
        "clean": not state.dirty,
        "changed_file_count": changed_count,
        "main_ahead_origin_main": state.main_ahead_origin_main,
        "main_behind_origin_main": state.main_behind_origin_main,
    }
    if state.operation_in_progress:
        return LoopStartGitDecision(
            **base,
            checkpoint_opportunity=False,
            push_opportunity=False,
            recommended_action="resolve_git_operation",
            reason=f"Git {state.operation_in_progress} is in progress.",
        )
    if state.conflicted_files:
        return LoopStartGitDecision(
            **base,
            checkpoint_opportunity=False,
            push_opportunity=False,
            recommended_action="resolve_conflicts",
            reason="Conflicted files are present.",
        )
    if state.branch != "main":
        return LoopStartGitDecision(
            **base,
            checkpoint_opportunity=False,
            push_opportunity=False,
            recommended_action="return_to_main_before_checkpoint",
            reason=f"Current branch is {state.branch or 'detached'}, so Dev-Flow will not checkpoint or push main.",
        )
    if state.main_diverged_origin_main:
        return LoopStartGitDecision(
            **base,
            checkpoint_opportunity=False,
            push_opportunity=False,
            recommended_action="resolve_main_divergence",
            reason="Local main and origin/main have diverged.",
        )
    if state.main_behind_origin_main and state.main_behind_origin_main > 0:
        return LoopStartGitDecision(
            **base,
            checkpoint_opportunity=False,
            push_opportunity=False,
            recommended_action="sync_main",
            command="devflow sync-main",
            reason="origin/main is ahead of local main.",
        )
    if state.dirty:
        return LoopStartGitDecision(
            **base,
            checkpoint_opportunity=True,
            push_opportunity=False,
            recommended_action="checkpoint_before_more_work",
            command="devflow git checkpoint --message 'chore: checkpoint verified work'",
            reason="The working tree has local changes; decide whether they are verified and should become a checkpoint before starting more loop work.",
        )
    if state.safe_for_push and state.main_ahead_origin_main and state.main_ahead_origin_main > 0:
        return LoopStartGitDecision(
            **base,
            checkpoint_opportunity=False,
            push_opportunity=True,
            recommended_action="push_main",
            command="devflow push-main",
            reason="Local main is clean and ahead of origin/main.",
        )
    return LoopStartGitDecision(
        **base,
        checkpoint_opportunity=False,
        push_opportunity=False,
        recommended_action="continue_loop",
        reason="Main is clean and has no immediate checkpoint or push opportunity.",
    )


def _goal_ids(root: Path) -> list[str]:
    directory = goals_dir(root)
    if not directory.exists():
        return []
    pattern = re.compile(r"^G-\d{4}$")
    return [item.name for item in sorted(directory.iterdir()) if item.is_dir() and pattern.match(item.name)]


def _linked_tasks_by_goal_slice(
    root: Path,
    findings: list[FreshnessFinding],
) -> dict[str, dict[str, list[dict[str, str]]]]:
    linked: dict[str, dict[str, list[dict[str, str]]]] = {}
    for task in list_tasks(root):
        link_path = task_dir(root, task.id) / "goal-link.yaml"
        if not link_path.exists():
            continue
        try:
            link = yaml.safe_load(link_path.read_text(encoding="utf-8")) or {}
        except Exception as exc:
            findings.append(
                FreshnessFinding(
                    id="malformed_goal_link",
                    severity="needs_human_decision",
                    scope=task.id,
                    path=relative_path(root, link_path),
                    message=f"Task goal-link.yaml could not be parsed: {exc}",
                    evidence={"task_id": task.id},
                    question=f"Should {task.id} be detached from its goal or should goal-link.yaml be repaired?",
                    suggested_action=f"Inspect {relative_path(root, link_path)} and repair or remove the invalid link.",
                )
            )
            continue
        goal_id = str(link.get("goal_id") or "").strip()
        slice_id = str(link.get("slice_id") or "").strip()
        if not goal_id or not slice_id:
            findings.append(
                FreshnessFinding(
                    id="incomplete_goal_link",
                    severity="needs_human_decision",
                    scope=task.id,
                    path=relative_path(root, link_path),
                    message="Task goal-link.yaml is missing goal_id or slice_id.",
                    evidence={"task_id": task.id, "goal_id": goal_id, "slice_id": slice_id},
                    question=f"Which goal slice should {task.id} belong to?",
                    suggested_action=f"Update or remove {relative_path(root, link_path)}.",
                )
            )
            continue
        linked.setdefault(goal_id, {}).setdefault(slice_id, []).append(
            {
                "task_id": task.id,
                "status": task.status,
                "verification_status": task.verification_status,
                "updated_at": task.updated_at.isoformat(),
            }
        )
    return linked


def _check_goal_against_linked_tasks(
    root: Path,
    goal_id: str,
    linked_slices: dict[str, list[dict[str, str]]],
    slices: list[dict[str, Any]],
    findings: list[FreshnessFinding],
) -> None:
    slices_path = goal_dir(root, goal_id) / "task-slices.yaml"
    slice_ids = [slice_data["task_id"] for slice_data in slices if slice_data.get("task_id")]
    promoted_slice_ids = [
        slice_id
        for slice_id in slice_ids
        if any(task.get("status") == "promoted" for task in linked_slices.get(slice_id, []))
    ]
    missing_slice_ids = sorted(set(linked_slices) - set(slice_ids))
    if missing_slice_ids:
        findings.append(
            FreshnessFinding(
                id="linked_task_points_to_missing_goal_slice",
                severity="needs_human_decision",
                scope=goal_id,
                path=relative_path(root, slices_path),
                message="One or more linked tasks point to slices that are no longer present in task-slices.yaml.",
                evidence={"missing_slice_ids": missing_slice_ids},
                question=f"Should the missing slices be restored for {goal_id}, or should linked tasks be marked historical?",
                suggested_action=f"Review {relative_path(root, slices_path)} against linked task goal-link.yaml files.",
            )
        )

    if slice_ids and len(promoted_slice_ids) == len(slice_ids):
        findings.append(
            FreshnessFinding(
                id="goal_completion_unclear_after_promoted_slices",
                severity="needs_human_decision",
                scope=goal_id,
                path=relative_path(root, goal_dir(root, goal_id)),
                message="Every declared goal slice has a promoted linked task, but the goal has no explicit closure state.",
                evidence={"slice_ids": slice_ids, "promoted_slice_ids": promoted_slice_ids},
                question=f"Is {goal_id} complete and ready to close, or should a new slice be added?",
                suggested_action=f"Ask the operator whether to close {goal_id} or add a follow-up slice.",
            )
        )

    handoff_path = goal_dir(root, goal_id) / "handoff.md"
    if promoted_slice_ids and handoff_path.exists():
        text = handoff_path.read_text(encoding="utf-8", errors="replace")
        if _handoff_mentions_pending_promotion(text):
            findings.append(
                FreshnessFinding(
                    id="goal_handoff_contradicts_promoted_task",
                    severity="needs_human_decision",
                    scope=goal_id,
                    path=relative_path(root, handoff_path),
                    message="Goal handoff still describes promotion as pending even though linked task slices are promoted.",
                    evidence={"promoted_slice_ids": promoted_slice_ids},
                    question=f"Should {relative_path(root, handoff_path)} be rewritten as historical closure evidence?",
                    suggested_action=f"Ask the operator before rewriting {relative_path(root, handoff_path)}.",
                )
            )


def _load_goal_slices(root: Path, goal_id: str, findings: list[FreshnessFinding]) -> list[dict[str, Any]]:
    slices_path = goal_dir(root, goal_id) / "task-slices.yaml"
    if not slices_path.exists():
        return []
    try:
        data = yaml.safe_load(slices_path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        findings.append(
            FreshnessFinding(
                id="malformed_goal_slices",
                severity="needs_human_decision",
                scope=goal_id,
                path=relative_path(root, slices_path),
                message=f"Goal task-slices.yaml could not be parsed: {exc}",
                evidence={},
                question=f"Should {goal_id} task slices be repaired from task history or rewritten by hand?",
                suggested_action=f"Repair {relative_path(root, slices_path)} before creating or closing goal tasks.",
            )
        )
        return []
    slices = data.get("task_slices")
    if not isinstance(slices, list):
        findings.append(
            FreshnessFinding(
                id="invalid_goal_slices_shape",
                severity="needs_human_decision",
                scope=goal_id,
                path=relative_path(root, slices_path),
                message="Goal task-slices.yaml does not contain a task_slices list.",
                evidence={"type": type(slices).__name__},
                question=f"What are the intended slices for {goal_id}?",
                suggested_action=f"Rewrite {relative_path(root, slices_path)} with a task_slices list.",
            )
        )
        return []
    return [item for item in slices if isinstance(item, dict)]


def _handoff_mentions_pending_promotion(text: str) -> bool:
    lowered = text.lower()
    patterns = [
        "promotion to `main` is still pending",
        "promotion to main is still pending",
        "promotion-preview ready",
        "not promoted",
        "pending human approval",
    ]
    return any(pattern in lowered for pattern in patterns)


def _status_for(findings: list[FreshnessFinding]) -> FreshnessStatus:
    if any(finding.severity == "needs_human_decision" for finding in findings):
        return "needs_human_decision"
    if any(finding.severity == "stale" for finding in findings):
        return "stale"
    return "ok"


def _next_action_for(status: FreshnessStatus) -> str:
    if status == "needs_human_decision":
        return "Ask the operator to choose the correct repair before mutating goal or handoff artifacts."
    if status == "stale":
        return "Run a freshness repair preview before applying any cleanup."
    return "Continue; canonical goal/task state has no detected freshness contradictions."


def _state_hash(
    root: Path,
    goal_ids: list[str],
    linked_tasks: dict[str, dict[str, list[dict[str, str]]]],
    findings: list[FreshnessFinding],
    goal_loop: list[GoalLoopState],
) -> str:
    payload = {
        "goal_ids": goal_ids,
        "linked_tasks": linked_tasks,
        "findings": [finding.model_dump() for finding in findings],
        "goal_loop": [goal.model_dump() for goal in goal_loop],
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
