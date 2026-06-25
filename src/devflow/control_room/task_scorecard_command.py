from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from devflow.control_room.project_registry import project_task_ref
from devflow.control_room.scorecard import generate_scorecard, save_scorecard


class TaskScorecardCommandError(ValueError):
    """User-facing task scorecard command error."""


@dataclass(frozen=True)
class _TaskScorecardCommandResult:
    root: Path
    task_id: str
    task_ref: str
    project_id: str | None
    artifact_path: str
    scorecard: dict[str, Any]


def build_task_scorecard_result(
    root: Path,
    task_id: str,
    project_id: str | None = None,
) -> _TaskScorecardCommandResult:
    try:
        scorecard_data = generate_scorecard(root, task_id)
        saved_path = save_scorecard(root, task_id, scorecard_data)
        _update_runtime_profile_from_scorecard(root, scorecard_data)
    except Exception as exc:
        raise TaskScorecardCommandError(str(exc)) from exc

    return _TaskScorecardCommandResult(
        root=root,
        task_id=task_id,
        task_ref=project_task_ref(task_id, project_id),
        project_id=project_id,
        artifact_path=_relative(root, saved_path),
        scorecard=scorecard_data["scorecard"],
    )


def render_task_scorecard_lines(result: _TaskScorecardCommandResult) -> tuple[str, ...]:
    sc = result.scorecard
    lines = [
        f"Compiled routing-quality scorecard for task: {result.task_ref}",
        "-" * 50,
        f"Decision Mode:              {sc.get('decision_mode', 'unknown')}",
        f"Verification Passed:        {_format_scorecard_flag(sc.get('verification_passed'))}",
        f"Promotion Ready:            {_format_scorecard_flag(sc.get('promotion_ready'))}",
        f"Selected Roles:             {_format_scorecard_list(sc.get('selected_roles'))}",
        f"Unresolved Roles:           {_format_scorecard_list(sc.get('unresolved_roles'))}",
        f"State Mutation:             {sc.get('state_mutation', 'unknown')}",
        f"Overall Quality Rating:     {_format_scorecard_rating(sc.get('overall_quality_rating'))}",
        f"First-Run Verification Pass: {_format_scorecard_flag(sc.get('first_run_pass'))}",
        f"Boundary Violations:        {_format_scorecard_flag(sc.get('boundary_violations'))}",
        f"Frontier Escalation Needed: {_format_scorecard_flag(sc.get('frontier_escalation_needed'))}",
    ]

    if "frontier_escalation_avoided" in sc:
        lines.append(f"Frontier Escalation Avoided: {_format_scorecard_flag(sc.get('frontier_escalation_avoided'))}")

    lines.extend(
        [
            f"Context Ceiling Exceeded:   {_format_scorecard_flag(sc.get('context_limit_exceeded'))}",
            f"Review Mistakes Found:      {_format_scorecard_flag(sc.get('review_mistakes_found'))}",
            f"Latency:                    {sc.get('latency_seconds', 'unknown')} seconds",
            f"Cost Avoided:               {_format_scorecard_cost(sc.get('cost_avoided_usd'))}",
            "-" * 50,
            f"Wrote routing-quality-scorecard.yaml under .devflow/tasks/{result.task_id}/",
        ]
    )
    return tuple(lines)


def render_task_scorecard_json(result: _TaskScorecardCommandResult) -> str:
    payload = {
        "artifact_path": result.artifact_path,
        "scorecard": result.scorecard,
        "task_id": result.task_id,
    }
    return json.dumps(payload, indent=2, sort_keys=True)


def _update_runtime_profile_from_scorecard(root: Path, scorecard_data: dict[str, Any]) -> None:
    try:
        from devflow.control_room.model_runtime_profiles import update_from_scorecard

        sc = scorecard_data.get("scorecard", {})
        rd = scorecard_data.get("routing_decision", {})
        selected = rd.get("selected", {}) if isinstance(rd, dict) else {}
        worker_id = selected.get("worker") if isinstance(selected, dict) else None
        rs = scorecard_data.get("repo_scan", {})
        context_estimate = int(rs.get("total_context_estimate") or 0) if isinstance(rs, dict) else 0
        if worker_id:
            update_from_scorecard(
                root=root,
                scorecard=scorecard_data,
                model_id=worker_id,
                context_estimate=context_estimate,
                latency_seconds=sc.get("latency_seconds", 0),
            )
    except Exception:
        pass


def _format_scorecard_flag(value: object) -> str:
    if value is True:
        return "yes"
    if value is False:
        return "no"
    return "unknown" if value is None or value == "unknown" else str(value)


def _format_scorecard_rating(value: object) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{value * 100}%"
    return "unknown" if value is None or value == "unknown" else str(value)


def _format_scorecard_cost(value: object) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"${value:.2f} USD"
    return "unknown" if value is None or value == "unknown" else str(value)


def _format_scorecard_list(value: object) -> str:
    if value is None or value == "unknown":
        return "unknown"
    if isinstance(value, list):
        return ", ".join(str(item) for item in value) if value else "none"
    return str(value)


def _relative(root: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path)
