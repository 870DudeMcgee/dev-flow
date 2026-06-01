from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from devflow.control_room.persistence import get_task
from devflow.control_room.paths import task_dir
from devflow.control_room.estimator import estimate_task_fit, save_task_fit
from devflow.control_room.agent_registry import load_agent_registry, AgentDefinition


def route_task(root: Path, task_id: str) -> dict[str, Any]:
    """Conservative agent role routing matching engine based on task-fit, risks, and capability tiers."""
    # Ensure task-fit exists or compute it
    task_fit_file = task_dir(root, task_id) / "task-fit.yaml"
    if not task_fit_file.exists():
        fit_data = estimate_task_fit(root, task_id)
        save_task_fit(root, task_id, fit_data)
    else:
        fit_data = estimate_task_fit(root, task_id)

    task = get_task(root, task_id)
    tf = fit_data.get("task_fit", {})
    rs = fit_data.get("repo_scan", {})

    recommended_planner_tier = tf.get("recommended_planner_tier", "frontier")
    recommended_worker_tier = tf.get("recommended_worker_tier", "strong_local")
    recommended_reviewer_tier = tf.get("recommended_reviewer_tier", "frontier")

    # Load agents registry
    registry = load_agent_registry(root)
    enabled_agents = [
        agent
        for agent in registry.enabled_agents()
        if agent.adapter != "manual" and agent.execution_mode != "human_launched_agent"
    ]

    # Cost mapping for tiers
    tier_costs = {
        "local": 1,
        "strong_local": 2,
        "frontier": 3,
    }

    def _resolve_tier_cost(tier: str) -> int:
        return tier_costs.get(tier.lower(), 3)

    # Resolution helpers for role matching
    selected: dict[str, str] = {}
    rejected: list[dict[str, str]] = []
    reasons: list[str] = []

    # Compile reasons
    reasons.append(f"context estimate ({rs.get('total_context_estimate', 0)} tokens) is {tf.get('context_requirement', 'medium')}")
    reasons.append(f"architectural risk is {tf.get('architectural_risk', 'medium')}")
    reasons.append(f"code edit risk is {tf.get('code_edit_risk', 'medium')}")

    def _match_agent(role_name: str, recommended_tier: str, keyword_filters: list[str]) -> str:
        eligible: list[AgentDefinition] = []
        
        # 1. Filter enabled agents by role capabilities or description keywords
        for agent in enabled_agents:
            agent_role = agent.role.lower()
            agent_id = agent.id.lower()
            
            # Check if role matches filter keywords
            if any(kf in agent_role or kf in agent_id for kf in keyword_filters):
                eligible.append(agent)

        if not eligible:
            if not enabled_agents:
                # Extreme fallback if registry is completely empty
                return "deterministic-shell"
            reasons.append(
                f"no enabled {role_name} agent matched keywords {keyword_filters}; "
                "falling back to an enabled local agent"
            )
            eligible = list(enabled_agents)

        if not eligible:
            # Extreme fallback if registry is empty
            return "deterministic-shell"

        # 2. Filter by tier compatibility: agent must have tier >= recommended_tier
        compat_tier_cost = _resolve_tier_cost(recommended_tier)
        compat_agents = [a for a in eligible if _resolve_tier_cost(a.tier) >= compat_tier_cost]

        if not compat_agents:
            # Fallback to any eligible agents if tier constraints are too tight
            compat_agents = eligible

        # 3. Pick cheapest agent
        compat_agents.sort(key=lambda a: _resolve_tier_cost(a.tier))
        chosen_agent = compat_agents[0]

        # Record rejected agents with precise rejection reasons
        for a in enabled_agents:
            if a.id == chosen_agent.id:
                continue

            matches_keywords = any(kf in a.role.lower() or kf in a.id.lower() for kf in keyword_filters)
            if not matches_keywords:
                rejected.append({
                    "agent": a.id,
                    "reason": f"role mismatch (role and ID keywords do not match {role_name} filters: {keyword_filters})"
                })
                continue

            total_context = rs.get("total_context_estimate", 0)
            max_context_ceiling = 32000 if a.tier == "local" else (48000 if a.tier == "strong_local" else 128000)
            if total_context > max_context_ceiling:
                rejected.append({
                    "agent": a.id,
                    "reason": f"context-window mismatch (context estimate {total_context} exceeds tier {a.tier} ceiling {max_context_ceiling})"
                })
                continue

            task_risk_high = tf.get("code_edit_risk", "low") in ("high", "critical") or tf.get("architectural_risk", "low") in ("high", "critical")
            if task_risk_high and a.tier == "local":
                rejected.append({
                    "agent": a.id,
                    "reason": f"risk mismatch (high task risk requires strong local or frontier tier, got local agent {a.id})"
                })
                continue

            chosen_cost = _resolve_tier_cost(chosen_agent.tier)
            agent_cost = _resolve_tier_cost(a.tier)
            recommended_cost = _resolve_tier_cost(recommended_tier)
            if agent_cost < recommended_cost:
                rejected.append({
                    "agent": a.id,
                    "reason": f"tier mismatch (agent tier {a.tier} is below recommended {recommended_tier})"
                })
            else:
                rejected.append({
                    "agent": a.id,
                    "reason": f"cost ceiling (agent tier {a.tier} exceeds chosen {chosen_agent.tier})"
                })

        return chosen_agent.id

    selected["planner"] = _match_agent("planner", recommended_planner_tier, ["planner", "architect", "archetype", "lead"])
    selected["worker"] = _match_agent("worker", recommended_worker_tier, ["worker", "developer", "coder"])
    selected["reviewer"] = _match_agent("reviewer", recommended_reviewer_tier, ["reviewer", "editor", "audit"])
    selected["verifier"] = "deterministic-shell"

    # Save to yaml exactly matching docs
    return {
        "routing_decision": {
            "task_id": task_id,
            "policy_version": 1,
            "task_fit_profile_path": f".devflow/tasks/{task_id}/task-fit.yaml",
            "selected": selected,
            "reason": reasons,
            "rejected": rejected,
        }
    }


def save_routing_decision(root: Path, task_id: str, decision_data: dict[str, Any]) -> None:
    """Save the routing decision data to routing-decision.yaml inside the task directory."""
    task_directory = task_dir(root, task_id)
    task_directory.mkdir(parents=True, exist_ok=True)
    yaml_file = task_directory / "routing-decision.yaml"

    lines = []
    lines.append("routing_decision:")
    
    rd = decision_data.get("routing_decision", {})
    lines.append(f"  task_id: {rd.get('task_id', '')}")
    lines.append(f"  policy_version: {rd.get('policy_version', 1)}")
    lines.append(f"  task_fit_profile_path: {rd.get('task_fit_profile_path', '')}")

    lines.append("  selected:")
    selected = rd.get("selected", {})
    for key in sorted(selected.keys()):
        lines.append(f"    {key}: {selected[key]}")

    lines.append("  reason:")
    for reason in rd.get("reason", []):
        lines.append(f"    - {reason}")

    lines.append("  rejected:")
    rejected = rd.get("rejected", [])
    if not rejected:
        lines.append("    - none")
    else:
        for rej in rejected:
            lines.append("    - agent: " + rej.get("agent", ""))
            lines.append("      reason: " + rej.get("reason", ""))

    yaml_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
