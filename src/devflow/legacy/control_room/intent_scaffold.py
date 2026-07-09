from __future__ import annotations

import json
import re
import shlex
from pathlib import Path
from typing import Any

from devflow.legacy.control_room.idea_foundry import IdeaFoundryError, show_idea
from devflow.legacy.control_room.persistence import atomic_write_text, utc_now


INTENT_SCAFFOLD_SCHEMA_VERSION = 1

_GENERIC_REQUESTS = {
    "make it better",
    "make this better",
    "fix it",
    "improve it",
    "do the thing",
    "build it",
    "create it",
}

_AREA_KEYWORDS = {
    "cli": {"cli", "command", "commands", "devflow", "slash"},
    "plugin": {"plugin", "extension", "skill", "connector"},
    "tests": {"test", "tests", "pytest", "coverage", "verify", "verification"},
    "search": {"search", "find", "lookup", "index"},
    "control_room": {"control", "supervisor", "routing", "task", "goal", "idea"},
    "docs": {"doc", "docs", "documentation", "readme"},
}


def preview_scaffold_from_idea(root: Path, idea_id: str) -> dict[str, Any]:
    """Build a deterministic, read-only scaffold proposal from Idea Foundry evidence."""

    metadata, raw, _classification, _promotion = show_idea(root, idea_id)
    return preview_scaffold_from_text(
        raw or metadata.get("title", ""),
        idea_id=metadata["id"],
        idea_title=metadata.get("title") or "",
        idea_source=metadata.get("source") or "manual",
        idea_tags=list(metadata.get("tags") or []),
    )


def preview_scaffold_from_text(
    raw_text: str,
    *,
    idea_id: str | None = None,
    idea_title: str | None = None,
    idea_source: str = "manual",
    idea_tags: list[str] | None = None,
) -> dict[str, Any]:
    body = _strip_operator_prefix(raw_text)
    title = _title_from_text(idea_title or body)
    affected_areas = _affected_areas(body)
    questions = _questions_for(body)

    proposal: dict[str, Any] = {
        "schema_version": INTENT_SCAFFOLD_SCHEMA_VERSION,
        "status": "needs_questions" if questions else "ready_for_review",
        "source_idea": {
            "id": idea_id,
            "title": idea_title or title,
            "source": idea_source,
            "tags": list(idea_tags or []),
        },
        "normalized_intent": {
            "title": title,
            "raw_text": body,
            "request_type": "implementation",
            "summary": _summary_for(title, body),
        },
        "affected_areas": affected_areas,
        "questions": questions,
        "warnings": _warnings_for(body, affected_areas),
        "refusal_reasons": [],
        "proposed_goal": None,
        "task_slices": [],
        "next_commands": [],
    }

    if questions:
        if idea_id:
            proposal["next_commands"] = [f"devflow idea show {idea_id}"]
        return proposal

    proposal["proposed_goal"] = _proposed_goal(title, body, affected_areas)
    proposal["task_slices"] = _task_slices(title, affected_areas)
    if idea_id:
        proposal["next_commands"] = [
            f"devflow idea scaffold-goal {idea_id}",
            f"devflow idea promote {idea_id} --to goal --rationale \"human reviewed scaffold\"",
            f"devflow idea create-goal {idea_id}",
        ]
    return proposal


def write_scaffold_from_idea(root: Path, idea_id: str) -> dict[str, Any]:
    proposal = preview_scaffold_from_idea(root, idea_id)
    if proposal["status"] != "ready_for_review":
        return proposal

    idea_dir = root / ".devflow" / "ideas" / idea_id
    if not idea_dir.exists():
        raise IdeaFoundryError(f"Idea not found: {idea_id}")
    now = utc_now().isoformat()
    evidence = {
        **proposal,
        "created_at": now,
        "canonical": False,
        "source": "intent_scaffold",
    }
    atomic_write_text(
        idea_dir / "scaffold-goal.json",
        json.dumps(evidence, sort_keys=True, indent=2) + "\n",
    )
    atomic_write_text(idea_dir / "scaffold-goal.md", _render_scaffold_markdown(evidence))
    return evidence


def build_scaffold_pending_action(raw_text: str, *, source: str) -> dict[str, Any]:
    proposal = preview_scaffold_from_text(raw_text, idea_source=source, idea_tags=["intent"])
    body = proposal["normalized_intent"]["raw_text"]
    title = proposal["normalized_intent"]["title"]
    return {
        "schema_version": INTENT_SCAFFOLD_SCHEMA_VERSION,
        "kind": "intent_scaffold",
        "execute_once": True,
        "approval_required": True,
        "source": source,
        "approval_commands": [
            f"devflow idea capture {_quote(body)} --title {_quote(title)} --source operator-message --tag intent",
            "devflow idea scaffold-goal <idea_id>",
        ],
        "proposal": proposal,
    }


def _strip_operator_prefix(text: str) -> str:
    body = text.strip()
    body = re.sub(r"^/df\s+", "", body, flags=re.IGNORECASE)
    body = re.sub(r"^(please|pls)\s+", "", body, flags=re.IGNORECASE)
    return body.strip()


def _title_from_text(text: str) -> str:
    body = _strip_operator_prefix(text).splitlines()[0].strip()
    body = re.sub(r"\s+", " ", body)
    body = re.sub(r"^(build|create|add|make|implement)\s+an?\s+", r"\1 ", body, flags=re.IGNORECASE)
    if not body:
        return "Untitled scaffold"
    return body[0].upper() + body[1:]


def _questions_for(text: str) -> list[str]:
    lower = text.strip().lower()
    words = re.findall(r"[a-z0-9]+", lower)
    if lower in _GENERIC_REQUESTS or len(words) < 4:
        return [
            "What should change, and what user-visible behavior should define success?",
            "Which files, commands, or product surface should this affect?",
        ]
    return []


def _affected_areas(text: str) -> list[str]:
    lower = text.lower()
    areas: list[str] = []
    for area, keywords in _AREA_KEYWORDS.items():
        if any(keyword in lower for keyword in keywords):
            areas.append(area)
    if "build" in lower or "create" in lower or "implement" in lower:
        for area in ("cli", "tests"):
            if area not in areas:
                areas.append(area)
    return areas or ["control_room", "tests"]


def _summary_for(title: str, body: str) -> str:
    if body:
        return f"Turn the operator request '{body}' into a reviewed Dev-Flow goal/task scaffold."
    return f"Turn '{title}' into a reviewed Dev-Flow goal/task scaffold."


def _warnings_for(text: str, affected_areas: list[str]) -> list[str]:
    warnings = [
        "Scaffold evidence is review-only until explicit human promotion and creation commands run.",
        "Do not run workers, verification, promotion, git publication, or provider calls from this scaffold.",
    ]
    if "plugin" in affected_areas:
        warnings.append("Confirm the plugin boundary and install/publish path before implementation work starts.")
    return warnings


def _proposed_goal(title: str, body: str, affected_areas: list[str]) -> dict[str, Any]:
    return {
        "title": title,
        "summary": _summary_for(title, body),
        "acceptance_criteria": [
            f"{title} has a reviewed goal brief and task slices before any worker execution.",
            "The proposed slices include clear acceptance criteria, context pointers, and verification commands.",
            "Canonical goal/task state is created only after explicit human approval.",
        ],
        "affected_areas": affected_areas,
        "context_pointers": [
            "docs/DEVFLOW_SOURCE_OF_TRUTH.md",
            "docs/README.md",
            "docs/local-worker-policy.md",
        ],
    }


def _task_slices(title: str, affected_areas: list[str]) -> list[dict[str, Any]]:
    shared_files = _shared_files_for(affected_areas)
    return [
        {
            "id": "TS-0001",
            "title": f"Design {title.lower()} scaffold contract",
            "description": "Define the deterministic inputs, review evidence, warnings, and approval gates.",
            "acceptance_criteria": [
                "The scaffold proposal captures normalized intent, affected areas, risks, and open questions.",
                "Ambiguous requests stop at questions without canonical goal/task writes.",
            ],
            "dependencies": [],
            "risk": "medium",
            "shared_files": shared_files,
            "context_pointers": [
                "docs/DEVFLOW_SOURCE_OF_TRUTH.md",
                "docs/README.md",
            ],
            "verification_policy": {
                "commands": ["PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_intent_scaffold.py -q"],
            },
        },
        {
            "id": "TS-0002",
            "title": f"Implement {title.lower()} scaffold path",
            "description": "Create reviewable scaffold evidence and bridge it to explicit approval commands.",
            "acceptance_criteria": [
                "The scaffold can be previewed without mutating goals, tasks, workers, or git state.",
                "Approval commands are explicit and do not imply worker execution.",
            ],
            "dependencies": ["TS-0001"],
            "risk": "medium",
            "shared_files": shared_files,
            "context_pointers": [
                "src/devflow/control_room/idea_foundry.py",
                "src/devflow/control_room/idea_execution_bridge.py",
            ],
            "verification_policy": {
                "commands": [
                    "PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_intent_scaffold.py tests/test_idea_execution_bridge.py -q"
                ],
            },
        },
    ]


def _shared_files_for(affected_areas: list[str]) -> list[str]:
    files = ["src/devflow/control_room/intent_scaffold.py", "tests/test_intent_scaffold.py"]
    if "plugin" in affected_areas or "cli" in affected_areas:
        files.append("src/devflow/cli.py")
    if "control_room" in affected_areas:
        files.append("src/devflow/control_room/idea_execution_bridge.py")
    return files


def _quote(value: str) -> str:
    return shlex.quote(value)


def _render_scaffold_markdown(proposal: dict[str, Any]) -> str:
    goal = proposal.get("proposed_goal") or {}
    lines = [
        "# Intent Scaffold Proposal",
        "",
        f"- status: {proposal['status']}",
        f"- source_idea: {proposal['source_idea'].get('id') or ''}",
        f"- title: {proposal['normalized_intent']['title']}",
        "",
        "## Acceptance Criteria",
    ]
    lines.extend(f"- {item}" for item in goal.get("acceptance_criteria") or [])
    lines.extend(["", "## Task Slices"])
    for item in proposal.get("task_slices") or []:
        lines.append(f"- {item['id']}: {item['title']}")
    lines.extend(["", "## Next Commands"])
    for command in proposal.get("next_commands") or []:
        lines.append(f"- `{shlex.quote(command)}`")
    return "\n".join(lines) + "\n"
