"""Brainstorm pipeline-run helpers — the Hermes-side toolkit for disciplined brainstorming.

Hermes (the frontier model conversation) IS the brainstorm surface now.
This module provides the functions Hermes calls via terminal/tools to write
brainstorm state into the V2 pipeline run filesystem.

No model calls happen here — the model IS the conversation. These are pure
filesystem persistence helpers that create and advance pipeline runs.

Flow:
  1. ``start_session`` → creates a pipeline run at ``LoopStage.idea``, writes intent
  2. ``append_brainstorm`` → appends transcript lines and updates brainstorm.md
  3. ``escalate_to_definition`` → advances the loop idea→definition (the gate)
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from devflow.loop.adapter import create_run_with_state, load_loop_state, save_loop_state
from devflow.loop.models import LoopStage, advance_stage
from devflow.loop.pipeline_run import (
    append_pipeline_event,
    load_pipeline_run,
    update_pipeline_run_record,
)
from devflow.loop.workflow_ledger import is_canonical_workflow_run

TRANSCRIPT_FILE = "transcript.jsonl"
SESSION_LINK_FILE = "pipeline-run-link.json"

_SESSION_COUNTER = 0


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _brainstorm_dir(root: Path) -> Path:
    return root.resolve() / ".devflow" / "brainstorms"


def _session_dir(root: Path, session_id: str) -> Path:
    brainstorm_dir = _brainstorm_dir(root)
    if (
        not session_id
        or session_id in {".", ".."}
        or "/" in session_id
        or "\\" in session_id
        or Path(session_id).is_absolute()
    ):
        raise ValueError(f"Invalid brainstorm session_id: {session_id!r}")
    session_dir = (brainstorm_dir / session_id).resolve()
    try:
        session_dir.relative_to(brainstorm_dir.resolve())
    except ValueError as exc:
        raise ValueError(f"Invalid brainstorm session_id: {session_id!r}") from exc
    return session_dir


def _transcript_path(root: Path, session_id: str) -> Path:
    return _session_dir(root, session_id) / TRANSCRIPT_FILE


def _new_session_id() -> str:
    global _SESSION_COUNTER
    _SESSION_COUNTER += 1
    return (
        datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        + f"-{_SESSION_COUNTER}"
    )


def _append_transcript_line(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(path), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def _read_transcript(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def _write_link(root: Path, session_id: str, run_id: str) -> None:
    link_path = _session_dir(root, session_id) / SESSION_LINK_FILE
    link_path.parent.mkdir(parents=True, exist_ok=True)
    link_path.write_text(
        json.dumps({"session_id": session_id, "run_id": run_id}, indent=2) + "\n",
        encoding="utf-8",
    )


def _read_link(root: Path, session_id: str) -> Optional[str]:
    link_path = _session_dir(root, session_id) / SESSION_LINK_FILE
    if not link_path.exists():
        return None
    try:
        payload = json.loads(link_path.read_text(encoding="utf-8"))
        return str(payload.get("run_id") or "")
    except (json.JSONDecodeError, OSError):
        return None


def _transcript_to_markdown(records: list[dict[str, Any]]) -> str:
    lines: list[str] = ["# Brainstorm Transcript", ""]
    for rec in records:
        role = rec.get("role", "unknown")
        content = rec.get("content", "")
        if not content:
            continue
        lines.append(f"## {role.title()}")
        lines.append("")
        lines.append(str(content))
        lines.append("")
    return "\n".join(lines).strip() + "\n"


# ---------------------------------------------------------------------------
# Public API — called by Hermes via terminal/tools
# ---------------------------------------------------------------------------

def start_session(
    root: Path | str,
    *,
    intent: str,
    repo: Optional[str] = None,
) -> tuple[str, str]:
    """Start a new brainstorm session. Returns (session_id, run_id).

    Creates a pipeline run at stage=idea, writes the intent, and links
    a brainstorm session directory to it.
    """
    root = Path(root).resolve()
    sid = _new_session_id()
    run_id, state = create_run_with_state(root, {
        "source": "brainstorm",
        "session_id": sid,
        "repo": repo or str(root),
    })
    # Persist so it stays at 'idea' even after we write brainstorm.md
    state = state.model_copy(update={"idea_brief_path": "brainstorm.md"})
    save_loop_state(root, state)
    _write_link(root, sid, run_id)

    update_pipeline_run_record(root, run_id, "intent.md", f"# Intent\n\n{intent}\n")
    append_pipeline_event(root, run_id, {
        "event": "brainstorm_started",
        "session_id": sid,
        "first_message": intent[:200],
    })

    # Initialize brainstorm.md with the intent
    _append_transcript_line(_transcript_path(root, sid), {
        "created_at": _now(),
        "role": "user",
        "kind": "message",
        "content": intent,
    })
    _sync_brainstorm_md(root, sid, run_id)

    return sid, run_id


def append_brainstorm(
    root: Path | str,
    *,
    session_id: str,
    role: str,
    content: str,
) -> None:
    """Append a line to the brainstorm transcript and sync to the pipeline run."""
    root = Path(root).resolve()
    transcript = _transcript_path(root, session_id)
    _append_transcript_line(transcript, {
        "created_at": _now(),
        "role": role,
        "kind": "message",
        "content": content,
    })
    run_id = _read_link(root, session_id)
    if run_id:
        _sync_brainstorm_md(root, session_id, run_id)


def _sync_brainstorm_md(root: Path, session_id: str, run_id: str) -> None:
    records = _read_transcript(_transcript_path(root, session_id))
    md = _transcript_to_markdown(records)
    update_pipeline_run_record(root, run_id, "brainstorm.md", md)


def escalate_to_definition(
    root: Path | str,
    *,
    session_id: str,
    title: Optional[str] = None,
    definition_of_done: Optional[str] = None,
) -> dict[str, Any]:
    """Gate: escalate brainstorm from idea → definition.

    Advances the pipeline run's loop state and writes definition artifacts.
    """
    root = Path(root).resolve()
    run_id = _read_link(root, session_id)
    if run_id is None:
        raise ValueError(f"Session '{session_id}' has no linked pipeline run.")

    state = load_loop_state(root, run_id)
    if state.stage != LoopStage.idea:
        raise ValueError(
            f"Session '{session_id}' is at stage '{state.stage.value}', not 'idea'."
        )

    if title:
        update_pipeline_run_record(root, run_id, "intent.md", f"# Intent\n\n{title}\n")
    if definition_of_done:
        update_pipeline_run_record(
            root, run_id, "readiness-packet.md",
            f"# Definition of Done\n\n{definition_of_done}\n",
        )

    if is_canonical_workflow_run(root, run_id):
        from devflow.loop.adapter import advance_loop_state

        state = advance_loop_state(
            root,
            state,
            LoopStage.definition,
            evidence={"idea-brief": "brainstorm.md"},
        )
    else:
        state = advance_stage(state, LoopStage.definition)
    save_loop_state(root, state)
    append_pipeline_event(root, run_id, {
        "event": "escalated_to_definition",
        "session_id": session_id,
        "title": title,
        "definition_of_done": definition_of_done,
    })

    return {
        "session_id": session_id,
        "run_id": run_id,
        "stage": state.stage.value,
        "message": "Escalated to Definition. Pipeline run is now in the disciplined loop.",
    }


def get_session_run_id(root: Path, session_id: str) -> Optional[str]:
    """Return the pipeline run_id linked to a brainstorm session, if any."""
    return _read_link(root, session_id)


def dispatch_to_planning(
    root: Path | str,
    *,
    session_id: str,
    topic: Optional[str] = None,
    target_files: Optional[list[str]] = None,
    max_rounds: int = 3,
    ensure_lane_on: bool = True,
) -> dict[str, Any]:
    """Code gate: dispatch the planner lane to produce spec + plan.

    This is the function the frontier model calls AFTER escalate_to_definition.
    It advances definition → planning_judge using the local planner lane
    (Agents-A1 Q4 at :8087), then runs the deterministic planning judge.

    The frontier model does NOT write the spec — the planner does.

    Returns a dict with the planning result and judge decision. If the judge
    approves, the run is ready for build. If it rejects or escalates, the
    frontier model handles the human judgment.
    """
    from devflow.loop.execution import run_planning_loop

    root = Path(root).resolve()
    run_id = _read_link(root, session_id)
    if run_id is None:
        raise ValueError(f"Session '{session_id}' has no linked pipeline run.")

    state = load_loop_state(root, run_id)

    from devflow.loop.orient import require_orientation_receipt

    require_orientation_receipt(root, run_id)

    # Advance through definition → spec → planning → planning_judge
    # The planner needs to be at planning_judge stage
    if state.stage == LoopStage.definition:
        if is_canonical_workflow_run(root, run_id):
            from devflow.loop.adapter import advance_loop_state

            state = advance_loop_state(
                root,
                state,
                LoopStage.spec,
                evidence={"orientation-receipt": "orient-result.json"},
            )
            save_loop_state(root, state)
        else:
            state = advance_stage(state, LoopStage.spec)
            save_loop_state(root, state)
            state = advance_stage(state, LoopStage.planning)
            save_loop_state(root, state)
            state = advance_stage(state, LoopStage.planning_judge)
            save_loop_state(root, state)

    expected_stages = (
        (LoopStage.spec, LoopStage.planning_judge)
        if is_canonical_workflow_run(root, run_id)
        else (LoopStage.planning_judge,)
    )
    if state.stage not in expected_stages:
        raise ValueError(
            f"Expected a planning-ready stage, got '{state.stage.value}'. "
            f"Call this right after escalate_to_definition."
        )

    # Read the topic from intent if not provided
    if not topic:
        data = load_pipeline_run(root, run_id)
        intent_raw = data.get("intent.md", "")
        lines = intent_raw.strip().splitlines()
        topic = "\n".join(lines[2:]).strip() if len(lines) > 2 else intent_raw.strip()

    planning_loop = run_planning_loop(
        root, run_id,
        topic=topic or "Untitled topic",
        target_files=target_files,
        max_rounds=max_rounds,
        worker_id="dispatch-from-brainstorm",
        ensure_lane_on=ensure_lane_on,
    )
    result = planning_loop["planner"]
    report = planning_loop["planning_report"]
    decision = planning_loop["planning_decision"]

    return {
        "session_id": session_id,
        "run_id": run_id,
        "stage": load_loop_state(root, run_id).stage.value,
        "planner_model": result.model if result else "unknown",
        "planner_content_length": len(result.content) if result else 0,
        "planning_decision": decision,
        "planning_rounds": len(planning_loop["planning_rounds"]),
        "planning_cap_exhausted": planning_loop["planning_cap_exhausted"],
        "planning_next_action": report.next_safe_action if report else "No planning report produced.",
        "planning_required_changes": report.required_changes if report else [],
        "spec_path": "spec.md",
        "plan_path": "plan.md",
        "message": f"Planner loop completed. Planning judge decision: {decision}.",
    }


def dispatch_to_build(
    root: Path | str,
    *,
    session_id: str,
    definition_of_done: str,
    target_files: Optional[list[str]] = None,
    verification_command: Optional[str] = None,
    max_rounds: int = 3,
    ensure_lane_on: bool = True,
    max_tokens: int = 16384,
) -> dict[str, Any]:
    """Code gate: dispatch builder + judge lanes after planning is approved.

    The frontier model calls this after dispatch_to_planning returns with
    an approved planning judge decision. It runs builder (Ornith 35B) then
    judge (Qwen 27B) and returns the results for human review.
    """
    from devflow.loop.execution import run_build_judge_verify
    from devflow.loop.execution_plan import load_execution_plan

    root = Path(root).resolve()
    run_id = _read_link(root, session_id)
    if run_id is None:
        raise ValueError(f"Session '{session_id}' has no linked pipeline run.")

    state = load_loop_state(root, run_id)

    if state.stage not in (LoopStage.assignment, LoopStage.build_judge):
        raise ValueError(
            f"Expected assignment or build_judge stage, got '{state.stage.value}'. "
            "Run dispatch_to_planning until the planning judge approves first."
        )

    # Read spec + plan (NOT loop-packet.md, which is the previous builder's raw output)
    data = load_pipeline_run(root, run_id)
    spec_text = data.get("spec.md", "")
    if not isinstance(spec_text, str):
        spec_text = str(spec_text)
    plan_text = data.get("plan.md", "")
    if not isinstance(plan_text, str):
        plan_text = str(plan_text)

    # The typed JSON plan is authoritative. Caller targets, Markdown parsing,
    # and the legacy shell-command parameter cannot override it.
    execution_plan = load_execution_plan(root, run_id)
    packet_1 = execution_plan.packets[0]
    packet_files = packet_1.target_files
    remaining_packet_ids = [packet.id for packet in execution_plan.packets[1:]]

    assignment = (
        f"# Spec\n{spec_text}\n\n"
        f"# Plan\n{plan_text}\n\n"
        f"# Packet\nDispatching packet {packet_1.id} "
        f"({len(packet_files)} of {len(execution_plan.target_files)} files). "
        f"Build ONLY the files listed below."
    )
    if state.stage == LoopStage.build_judge:
        summary = data.get("packet-consolidated-build-judge-summary.json")
        if isinstance(summary, dict):
            prior_feedback = str(summary.get("final_judge_rationale") or "").strip()
            if prior_feedback:
                assignment += (
                    "\n\n# Previous capped judge feedback\n"
                    f"{prior_feedback}\n"
                    "Correct this exact defect before making any other change."
                )

    result = run_build_judge_verify(
        root, run_id,
        assignment=assignment,
        definition_of_done=definition_of_done,
        target_files=packet_files,
        validators=execution_plan.validators,
        verification_command=None,
        max_rounds=max_rounds,
        worker_id="dispatch-from-brainstorm",
        ensure_lane_on=ensure_lane_on,
        max_tokens=max_tokens,
    )

    build = result.get("build")
    judge = result.get("judge")
    decision = result.get("decision")

    return {
        "session_id": session_id,
        "run_id": run_id,
        "stage": load_loop_state(root, run_id).stage.value,
        "builder_model": build.model if build else "unknown",
        "builder_content_length": len(build.content) if build else 0,
        "build_rounds": len(result.get("build_rounds") or []),
        "build_cap_exhausted": result.get("build_cap_exhausted", False),
        "judge_model": judge.model if judge else "unknown",
        "judge_decision": decision,
        "verification": result.get("verification"),
        "dispatched_packet_id": packet_1.id,
        "remaining_packet_ids": remaining_packet_ids,
        "plan_complete": False,
        "dispatch_status": (
            "awaiting_packet_scheduler"
            if remaining_packet_ids
            else "packet_complete_awaiting_integration"
        ),
        "message": f"Build+Judge completed. Decision: {decision}.",
    }
