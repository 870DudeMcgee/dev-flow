from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

from devflow.control_room.persistence import get_task
from devflow.control_room.paths import task_dir
from devflow.control_room.estimator import estimate_task_fit, save_task_fit
from devflow.control_room.router import route_task, save_routing_decision
from devflow.control_room.agent_registry import load_agent_registry


def generate_scorecard(root: Path, task_id: str) -> dict[str, Any]:
    """Compile post-run routing and worker execution quality scorecard metrics."""
    # Ensure task-fit exists or compute it
    task_fit_file = task_dir(root, task_id) / "task-fit.yaml"
    if not task_fit_file.exists():
        fit_data = estimate_task_fit(root, task_id)
        save_task_fit(root, task_id, fit_data)
    else:
        fit_data = estimate_task_fit(root, task_id)

    # Ensure routing-decision exists or compute it
    routing_file = task_dir(root, task_id) / "routing-decision.yaml"
    if not routing_file.exists():
        decision_data = route_task(root, task_id)
        save_routing_decision(root, task_id, decision_data)
    else:
        # Re-run router to match actual registry
        decision_data = route_task(root, task_id)

    task = get_task(root, task_id)
    rd = decision_data.get("routing_decision", {})
    tf = fit_data.get("task_fit", {})
    rs = fit_data.get("repo_scan", {})

    selected = rd.get("selected", {})
    planner_agent_id = selected.get("planner", "deterministic-shell")
    worker_agent_id = selected.get("worker", "deterministic-shell")

    # Read events from events.jsonl
    events: list[dict[str, Any]] = []
    events_path = task_dir(root, task_id) / "events.jsonl"
    if events_path.exists():
        try:
            for line in events_path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    events.append(json.loads(line))
        except Exception:
            pass

    evidence: list[str] = []
    verify_finished_events = [e for e in events if e.get("event") == "verification_finished"]

    # 1. First run pass metrics
    has_verification = len(verify_finished_events) > 0 or task.verification_status != "not_run"
    if not has_verification:
        evidence.append("missing verification run")
        first_run_pass = "unknown"
    else:
        first_run_pass = False
        if len(verify_finished_events) <= 1:
            if task.status in ("verified", "complete") or task.verification_status == "passed" or task.last_exit_code == 0:
                first_run_pass = True

    # 2. Boundary violations metrics
    if task.status == "created" and not has_verification:
        boundary_violations = "unknown"
    else:
        boundary_violations = False
        from devflow.control_room.scout import RepoScout
        scout = RepoScout(root)
        changed_files = scout.get_changed_files()

        # Load worker agent rules
        registry = load_agent_registry(root)
        worker_agent = registry.agents.get(worker_agent_id)
        if worker_agent is not None:
            cannot_touch_patterns = worker_agent.cannot_touch
            for cf in changed_files:
                for pat in cannot_touch_patterns:
                    clean_pat = pat.replace("**", "").replace("*", "")
                    if cf.startswith(clean_pat):
                        boundary_violations = True
                        break

    # 3. Frontier escalation needed
    frontier_escalation_needed = False
    for e in events:
        if "escalate" in str(e).lower() or "escalation" in str(e).lower():
            frontier_escalation_needed = True

    # 4. Latency
    latency_seconds = 45 # default heuristic
    if task.started_at and task.finished_at:
        try:
            latency_seconds = int((task.finished_at - task.started_at).total_seconds())
        except Exception:
            pass

    # 5. Cost avoided
    registry = load_agent_registry(root)
    def _tier_cost(agent_id: str) -> float:
        agent = registry.agents.get(agent_id)
        if agent is None:
            return 0.0
        tier = agent.tier.lower()
        if tier == "local":
            return 0.0
        elif tier == "strong_local":
            return 0.07
        else:
            return 0.75

    planner_cost = _tier_cost(planner_agent_id)
    worker_cost = _tier_cost(worker_agent_id)
    total_cost = planner_cost + worker_cost
    cost_avoided = max(0.0, 1.50 - total_cost)

    # 6. Context limit exceeded
    context_limit_exceeded = False
    total_tokens = rs.get("total_context_estimate", 12000)
    if total_tokens > 32000:
        context_limit_exceeded = True

    # 7. Review mistakes found
    has_review = any(e.get("event") in ("review_approved", "review_rejected") for e in events) or (task_dir(root, task_id) / "result.md").exists()
    if not has_review:
        evidence.append("no review artifact")
        review_mistakes_found = "unknown"
    else:
        review_mistakes_found = False
        for e in events:
            if e.get("event") == "review_rejected" or "mistake" in str(e).lower() or "correction" in str(e).lower():
                review_mistakes_found = True

    # Overall rating & Confidence
    confidence = "high"
    if not has_verification or not has_review:
        confidence = "low"

    cost_avoided_usd = cost_avoided if (has_verification or has_review) else None

    if not has_verification and not has_review:
        overall_rating = "unknown"
    else:
        rating_val = 1.0
        if first_run_pass is False:
            rating_val -= 0.3
        if boundary_violations is True:
            rating_val -= 0.5
        if review_mistakes_found is True:
            rating_val -= 0.2
        overall_rating = max(0.1, min(1.0, round(rating_val, 2)))

    return {
        "scorecard": {
            "task_id": task_id,
            "first_run_pass": first_run_pass,
            "boundary_violations": boundary_violations,
            "frontier_escalation_needed": frontier_escalation_needed,
            "context_limit_exceeded": context_limit_exceeded,
            "review_mistakes_found": review_mistakes_found,
            "latency_seconds": latency_seconds,
            "cost_avoided_usd": cost_avoided_usd,
            "overall_quality_rating": overall_rating,
            "confidence": confidence,
            "evidence": evidence,
        }
    }


def save_scorecard(root: Path, task_id: str, scorecard_data: dict[str, Any]) -> None:
    """Save the quality scorecard data to scorecard.yaml inside the task directory."""
    task_directory = task_dir(root, task_id)
    task_directory.mkdir(parents=True, exist_ok=True)
    yaml_file = task_directory / "scorecard.yaml"

    lines = []
    lines.append("scorecard:")
    
    sc = scorecard_data.get("scorecard", {})
    lines.append(f"  task_id: {sc.get('task_id', '')}")

    for key in sorted(sc.keys()):
        if key == "task_id":
            continue
        val = sc[key]
        if isinstance(val, bool):
            val_str = "true" if val else "false"
            lines.append(f"  {key}: {val_str}")
        elif isinstance(val, (int, float)):
            lines.append(f"  {key}: {val}")
        elif val is None:
            lines.append(f"  {key}: null")
        elif isinstance(val, list):
            lines.append(f"  {key}:")
            if not val:
                lines.append("    - none")
            else:
                for item in val:
                    lines.append(f"    - {item}")
        else:
            lines.append(f"  {key}: {val}")

    yaml_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
