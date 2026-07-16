"""Markdown renderers for Obsidian Command Center projection (M1-S2).

Pure functions: each takes a :class:`~devflow.obsidian.projection.ProjectionState`
and returns a Markdown string. No I/O, no side effects, no canonical-state access.

The renderers produce five views following the blueprint's Appendix C format:

- :func:`render_overview`  — health hero, phase, progress, attention, next action
- :func:`render_workflow`  — node-by-node status table
- :func:`render_evidence`   — available receipts and verification results
- :func:`render_decisions`  — open and historical decisions
- :func:`render_history`    — chronological event summary
"""

from __future__ import annotations

from datetime import datetime

from devflow.loop.models import LoopStage
from devflow.obsidian.projection import ProjectionState, RunHealth

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

START_MARKER = "<!-- DEVFLOW-GENERATED:START -->"
END_MARKER = "<!-- DEVFLOW-GENERATED:END -->"

# Ordered chain for display (matches workflow_definition.py success chain).
_DISPLAY_CHAIN: tuple[str, ...] = (
    "idea",
    "definition",
    "spec",
    "planning",
    "planning_judge",
    "assignment",
    "build_judge",
    "verification",
    "human_decision",
)

_NODE_LABELS: dict[str, str] = {
    "idea": "Idea",
    "definition": "Definition",
    "spec": "Specification",
    "planning": "Planning",
    "planning_judge": "Planning Review",
    "assignment": "Assignment",
    "build_judge": "Build & Judge",
    "verification": "Verification",
    "human_decision": "Human Decision",
    "complete": "Complete",
    "blocked": "Blocked",
}

_HEALTH_ICON: dict[RunHealth, str] = {
    RunHealth.healthy: "✅",
    RunHealth.running: "🔄",
    RunHealth.repairing: "🔧",
    RunHealth.awaiting_decision: "⏳",
    RunHealth.blocked: "🚫",
    RunHealth.verification_failed: "❌",
    RunHealth.completed: "✅",
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _wrap_generated(content: str) -> str:
    """Wrap content in START/END markers for safe atomic replacement."""
    return f"{START_MARKER}\n{content.rstrip()}\n{END_MARKER}"


def _progress_bar(percent: int) -> str:
    """Render a 20-character ASCII progress bar."""
    filled = round(percent / 5)
    bar = "█" * filled + "░" * (20 - filled)
    return f"{bar} {percent}%"


def _next_action(state: ProjectionState) -> str:
    """Derive the next-action guidance from health/stage."""
    if state.extraction_note == "not_canonical":
        return "> This run is not canonical. No projection available."
    if state.health == RunHealth.completed:
        return "> Run completed. Review the promotion packet for next steps."
    if state.health == RunHealth.awaiting_decision:
        return "> Awaiting operator decision (accept / reject / request changes)."
    if state.health == RunHealth.blocked:
        return "> Run is blocked. Review the blocker and decide whether to retry or escalate."
    if state.health == RunHealth.verification_failed:
        return "> Verification failed. Review evidence and decide whether to repair or escalate."
    if state.health == RunHealth.repairing:
        return "> Repair loop is active. Monitor progress."
    # Running
    return f"> Continue with the {state.current_phase.lower()} stage."


def _attention_lines(state: ProjectionState) -> list[str]:
    """Build the attention queue lines."""
    lines: list[str] = []
    if state.blocker_count > 0:
        lines.append(f"- **Blocker:** {state.blocker_count} item(s) preventing progress.")
    if state.decision_count > 0:
        lines.append(f"- **Decision:** {state.decision_count} decision(s) on record.")
    if state.handoff_count > 0:
        lines.append(f"- **Handoff:** {state.handoff_count} item(s) ready for review.")
    if not lines:
        lines.append("- No blockers · No pending decisions · No handoffs")
    return lines


# ---------------------------------------------------------------------------
# Public renderers
# ---------------------------------------------------------------------------

def render_front_matter(state: ProjectionState) -> str:
    """Render YAML front matter following Appendix C format."""
    return "\n".join([
        "---",
        "type: devflow-run",
        "project: DevFlow",
        f"run_id: {state.run_id}",
        f"workflow: {state.workflow_id}",
        f"status: {state.stage.value}",
        f"health: {state.health.value}",
        f"phase: {state.current_phase}",
        f"progress: {state.progress_percent}",
        f"blockers: {state.blocker_count}",
        f"decisions: {state.decision_count}",
        f"handoffs: {state.handoff_count}",
        f"updated: {state.updated_at}",
        f"canonical_state: {state.canonical_run_dir}",
        "---",
    ])


def render_overview(state: ProjectionState) -> str:
    """Render the Overview / Current Focus view.

    Health hero + phase + progress bar + attention queue + next action.
    """
    icon = _HEALTH_ICON.get(state.health, "❓")
    bar = _progress_bar(state.progress_percent)
    attention = "\n".join(_attention_lines(state))
    action = _next_action(state)

    body = "\n".join([
        render_front_matter(state),
        "",
        f"# DevFlow — Current Focus",
        "",
        f"> [!info] {icon} Health: **{state.health.value}** · Phase: **{state.current_phase}**",
        f"> {bar}",
        "",
        "## Attention",
        attention,
        "",
        "## Next Action",
        action,
        "",
        f"[[Workflow]] · [[Evidence]] · [[Decisions]] · [[History]]",
    ])
    return _wrap_generated(body)


def render_workflow(state: ProjectionState) -> str:
    """Render the Workflow view — node-by-node status table."""
    completed_set = set(state.completed_node_ids)
    current = state.current_node_id

    rows: list[str] = ["| Node | Stage | Status |", "|---|---|---|"]
    for node_id in _DISPLAY_CHAIN:
        label = _NODE_LABELS.get(node_id, node_id)
        stage_name = label  # Use the same label for display
        if node_id in completed_set:
            status = "✅ completed"
        elif node_id == current:
            status = "▶️ **current**"
        else:
            status = "⬚ pending"
        rows.append(f"| {label} | {stage_name} | {status} |")

    # Terminal nodes
    if state.stage == LoopStage.complete:
        rows.append(f"| Complete | Complete | ✅ reached |")
    elif state.stage == LoopStage.blocked:
        rows.append(f"| Blocked | Blocked | 🚫 reached |")

    body = "\n".join([
        render_front_matter(state),
        "",
        "# DevFlow — Workflow",
        "",
        f"> Workflow: `{state.workflow_id}` · Phase: **{state.current_phase}**",
        "",
        *rows,
        "",
        f"[[Overview]] · [[Evidence]] · [[Decisions]] · [[History]]",
    ])
    return _wrap_generated(body)


def render_evidence(state: ProjectionState) -> str:
    """Render the Evidence view — receipts, verification results, links."""
    completed = ", ".join(f"`{n}`" for n in state.completed_node_ids) or "—"

    body_lines = [
        render_front_matter(state),
        "",
        "# DevFlow — Evidence",
        "",
        f"> Run: `{state.run_id}` · {state.completed_node_ids.__len__()} node(s) completed",
        "",
        "## Completed Nodes",
        completed,
        "",
        "## Canonical State",
        f"All receipts and evidence are persisted under:",
        f"`{state.canonical_run_dir}`",
        "",
    ]

    if state.result_branch:
        body_lines.extend([
            "## Result Branch",
            f"A verified result branch exists: `refs/heads/devflow/results/{state.run_id}`",
            "",
        ])
    else:
        body_lines.extend([
            "## Result Branch",
            "No result branch has been created yet (requires operator `accept` decision).",
            "",
        ])

    body_lines.extend([
        "## Verification",
        "Detailed verification receipts are available in the canonical run directory.",
        "This view will be expanded as the evidence layer matures (blueprint §10.2).",
        "",
        f"[[Overview]] · [[Workflow]] · [[Decisions]] · [[History]]",
    ])
    return _wrap_generated("\n".join(body_lines))


def render_decisions(state: ProjectionState) -> str:
    """Render the Decisions view — open + historical decisions."""
    body_lines = [
        render_front_matter(state),
        "",
        "# DevFlow — Decisions",
        "",
        f"> {state.decision_count} decision(s) on record.",
        "",
    ]

    if state.open_decisions:
        body_lines.extend([
            "| Decision | Type | Actor | Promotion Eligible | Timestamp |",
            "|---|---|---|---|---|",
        ])
        for d in state.open_decisions:
            eligible = "✅ yes" if d.promotion_eligible else "—"
            body_lines.append(
                f"| `{d.decision_id}` | {d.decision_type} | {d.actor} | {eligible} | {d.created_at} |"
            )
        body_lines.append("")
    else:
        body_lines.extend([
            "No decisions have been recorded for this run yet.",
            "",
        ])

    body_lines.append(f"[[Overview]] · [[Workflow]] · [[Evidence]] · [[History]]")
    return _wrap_generated("\n".join(body_lines))


def render_history(state: ProjectionState) -> str:
    """Render the History view — chronological event summary."""
    body_lines = [
        render_front_matter(state),
        "",
        "# DevFlow — History",
        "",
        f"> Run `{state.run_id}` · Workflow `{state.workflow_id}`",
        "",
        "## Stage Progression",
    ]

    if state.completed_node_ids:
        for i, node_id in enumerate(state.completed_node_ids, start=1):
            label = _NODE_LABELS.get(node_id, node_id)
            body_lines.append(f"{i}. **{label}** — completed")
    else:
        body_lines.append("_No nodes completed yet._")

    if state.current_node_id:
        label = _NODE_LABELS.get(state.current_node_id, state.current_node_id)
        body_lines.append(f"- **{label}** — current")

    body_lines.extend([
        "",
        f"_Updated: {state.updated_at}_",
        "",
        f"[[Overview]] · [[Workflow]] · [[Evidence]] · [[Decisions]]",
    ])
    return _wrap_generated("\n".join(body_lines))


def render_all(state: ProjectionState) -> dict[str, str]:
    """Render all five views. Returns filename → markdown mapping."""
    return {
        "Overview.md": render_overview(state),
        "Workflow.md": render_workflow(state),
        "Evidence.md": render_evidence(state),
        "Decisions.md": render_decisions(state),
        "History.md": render_history(state),
    }


__all__ = [
    "END_MARKER",
    "START_MARKER",
    "render_all",
    "render_decisions",
    "render_evidence",
    "render_front_matter",
    "render_history",
    "render_overview",
    "render_workflow",
]
