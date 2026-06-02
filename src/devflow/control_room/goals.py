from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from pydantic import BaseModel

from devflow.control_room.paths import goal_dir, goals_dir


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class GoalRecord(BaseModel):
    id: str
    created_at: datetime
    updated_at: datetime
    source_brief_path: str


def next_goal_id(root: Path) -> str:
    """Scan existing goals to auto-generate the next G-XXXX ID."""
    dir_path = goals_dir(root)
    if not dir_path.exists():
        return "G-0001"

    max_id = 0
    pattern = re.compile(r"^G-(\d{4})$")
    for item in dir_path.iterdir():
        if item.is_dir():
            match = pattern.match(item.name)
            if match:
                val = int(match.group(1))
                if val > max_id:
                    max_id = val

    return f"G-{max_id + 1:04d}"


def create_goal_from_markdown(root: Path, source_path: Path, goal_id: str | None = None) -> GoalRecord:
    """Scaffold a new durable goal directory with all 10 standard planning and context artifacts."""
    if not source_path.exists():
        raise FileNotFoundError(f"Source brief not found: {source_path}")

    brief_content = source_path.read_text(encoding="utf-8")
    
    # 1. Resolve goal ID and dir
    resolved_id = goal_id or next_goal_id(root)
    g_dir = goal_dir(root, resolved_id)
    g_dir.mkdir(parents=True, exist_ok=True)

    now = utc_now()
    timestamp = now.isoformat()

    # 2. goal.md
    goal_md_content = (
        f"# Goal: {resolved_id}\n"
        f"- Created At: {timestamp}\n"
        f"- Source: {source_path.resolve().as_posix()}\n\n"
        f"{brief_content}"
    )
    (g_dir / "goal.md").write_text(goal_md_content, encoding="utf-8")

    # 3. grill.md
    grill_md_content = """# Drill & Grill Sessions

## Problem being solved
TBD

## Ambiguous/overloaded words
- None yet

## DevFlow concepts affected
- None

## Explicitly out of scope
- None

## Decisions not to reopen
- None

## Relevant files/docs
- None

## Stale/archived/forbidden files
- None

## Definition of done
TBD

## Risks for agent drift/context poisoning
- Medium risk

## AFK vs HITL classification
- HITL (Human-in-the-Loop)

## Human answers required before implementation
- None
"""
    (g_dir / "grill.md").write_text(grill_md_content, encoding="utf-8")

    # 4. prd.md
    prd_md_content = """# Product Requirement Document (PRD)

## Problem
TBD

## Desired behavior
TBD

## Non-goals
- No web dashboard
- No database

## Architectural constraints
- Local-first control room architecture

## Affected DevFlow concepts
- None

## Acceptance criteria
TBD

## Verification expectations
TBD

## Context rules
- Standard path isolation

## Promotion boundary
- Human-triggered merge/promote

## Risks
- Minor risk
"""
    (g_dir / "prd.md").write_text(prd_md_content, encoding="utf-8")

    # 5. decisions.yaml
    decisions_yaml_content = """decisions: []
do_not_reopen: []
adr_candidates: []
"""
    (g_dir / "decisions.yaml").write_text(decisions_yaml_content, encoding="utf-8")

    # 6. open-questions.yaml
    open_questions_yaml_content = """questions: []
implementation_blocked: false
"""
    (g_dir / "open-questions.yaml").write_text(open_questions_yaml_content, encoding="utf-8")

    # 7. out-of-scope.md
    out_of_scope_md_content = """# Out of Scope

The following items are strictly out of scope for this goal:
- No web dashboard
- No database
- No auto-merge
- No provider coupling
- No full local model adapter in this slice
"""
    (g_dir / "out-of-scope.md").write_text(out_of_scope_md_content, encoding="utf-8")

    # 8. context-pointers.yaml (scans workspace for active files, skipping archive/stale folders)
    required_context: list[str] = []
    stale_or_archived_context: list[str] = []
    warnings: list[str] = [
        "do_not_load_entire_repo",
        "do_not_load_all_historical_chats",
    ]

    docs_dir = root / "docs"
    if docs_dir.exists() and docs_dir.is_dir():
        for p in sorted(docs_dir.rglob("*")):
            if p.is_file() and p.suffix in (".md", ".yaml", ".json"):
                rel_path = p.relative_to(root).as_posix()
                if "archive" in rel_path.lower() or "stale" in rel_path.lower():
                    stale_or_archived_context.append(rel_path)
                    warnings.append(f"warning: docs path contains archive: {rel_path}")
                else:
                    required_context.append(rel_path)

    # Format context pointers yaml safely
    lines = []
    lines.append("context_budget:")
    lines.append("  estimated_tokens: null")
    lines.append("  risk: medium")
    lines.append("  strategy: focused_task_packet")
    
    lines.append("required_context:")
    for path in required_context:
        lines.append(f'  - "{path}"')
        
    lines.append("optional_context: []")
    
    lines.append("forbidden_context:")
    lines.append('  - "archived_docs"')
    lines.append('  - "previous_failed_attempts_unless_explicitly_relevant"')
    lines.append('  - "unrelated_brainstorming"')
    
    lines.append("stale_or_archived_context:")
    for path in stale_or_archived_context:
        lines.append(f'  - "{path}"')
        
    lines.append("warnings:")
    for w in warnings:
        lines.append(f'  - "{w}"')
        
    lines.append('useful_context_summary: ""')
    
    (g_dir / "context-pointers.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")

    # 9. task-slices.yaml
    task_slices_yaml_content = """task_slices:
  - task_id: TS-0001
    title: "Starter task slice"
    summary: "Initialize implementation baseline and verify environment constraints."
    slice_type: "scaffold"
    acceptance_criteria:
      - "Baseline environment check passes"
    required_artifacts:
      - "goal.md"
    blocked_by: []
    blocks: []
    parallel_safe: true
    shared_files: []
    workspace_isolation_required: true
    promotion_requires: "passing tests"
    risk: "low"
    execution_mode: "HITL"
    context_budget:
      estimated_tokens: 5000
      risk: "low"
      strategy: "focused_task_packet"
    verification_policy: "automated-test-only"
    human_checkpoint_required: true
    checkpoint_reason: "Verify baseline scaffold"
    promotion_allowed: false
"""
    (g_dir / "task-slices.yaml").write_text(task_slices_yaml_content, encoding="utf-8")

    # 10. risks.md
    risks_md_content = """# Goal Risks

## Agent drift risks
- Keep prompts highly focused on task slices.

## Context poisoning risks
- Do not import stale documentation.

## Shared-file risks
- Do not edit files across multiple parallel workers.

## Verification risks
- Verify all changes before promoting.

## Promotion risks
- Humans retain manual check/merge promotion.

## Local model/runtime risks
- Keep runtime isolated.
"""
    (g_dir / "risks.md").write_text(risks_md_content, encoding="utf-8")

    # 11. handoff.md
    handoff_md_content = f"""# Handoff: Goal {resolved_id}

## Current goal
- {resolved_id} initial scaffolding

## Purpose of next session
- Execute first vertical task slice

## Decisions already made
- Scaffold structured folders under `.devflow/goals/`

## Decisions not to reopen
- Keep goal folder accessible and transparent

## Relevant files
- `.devflow/goals/{resolved_id}/goal.md`

## Out-of-scope files
- Unrelated legacy code

## Verification status
- Scaffolding complete

## Open questions
- None

## Risks
- Minor

## Suggested next worker role
- Coder / Developer

## Context pointers
- `.devflow/goals/{resolved_id}/context-pointers.yaml`
"""
    (g_dir / "handoff.md").write_text(handoff_md_content, encoding="utf-8")

    # Write goal.yaml record
    record_lines = [
        f"id: {resolved_id}",
        f"created_at: {timestamp}",
        f"updated_at: {timestamp}",
        f"source_brief_path: {source_path.resolve().as_posix()}",
    ]
    (g_dir / "goal.yaml").write_text("\n".join(record_lines) + "\n", encoding="utf-8")

    return GoalRecord(
        id=resolved_id,
        created_at=now,
        updated_at=now,
        source_brief_path=str(source_path.resolve()),
    )


def render_goal_summary(root: Path, goal_id: str) -> str:
    """Generate a clean and concise text summary of a goal and its checklist."""
    g_dir = goal_dir(root, goal_id)
    goal_yaml_path = g_dir / "goal.yaml"
    if not goal_yaml_path.exists():
        raise KeyError(f"Goal not found: {goal_id}")

    lines = []
    lines.append(f"Goal ID:      {goal_id}")
    
    # Read goal metadata
    yaml_lines = goal_yaml_path.read_text(encoding="utf-8").splitlines()
    created_at = "Unknown"
    source = "Unknown"
    for line in yaml_lines:
        if ":" in line:
            k, v = line.split(":", 1)
            k = k.strip()
            v = v.strip()
            if k == "created_at":
                created_at = v
            elif k == "source_brief_path":
                source = v

    lines.append(f"Created At:   {created_at}")
    lines.append(f"Source Brief: {source}")
    lines.append(f"Directory:    .devflow/goals/{goal_id}/")
    lines.append("")
    lines.append("Scaffolded Artifacts:")
    for fn in [
        "goal.md", "grill.md", "prd.md", "decisions.yaml",
        "open-questions.yaml", "out-of-scope.md", "context-pointers.yaml",
        "task-slices.yaml", "risks.md", "handoff.md"
    ]:
        status = "exists" if (g_dir / fn).exists() else "missing"
        lines.append(f"  - {fn:<22} ({status})")
        
    return "\n".join(lines) + "\n"
