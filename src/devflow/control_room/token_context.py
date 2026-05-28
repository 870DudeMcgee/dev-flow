from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from devflow.control_room.service import list_tasks


ContextMode = Literal["balanced", "review-graph", "debug-focused", "planning", "docs"]


MODE_KEYWORDS: tuple[tuple[ContextMode, tuple[str, ...], str], ...] = (
    ("review-graph", ("review", "audit", "risk", "regression"), "review/audit/risk/regression keyword matched"),
    ("debug-focused", ("debug", "failing", "error", "test", "tests", "traceback"), "debug/failing/error/test/traceback keyword matched"),
    (
        "planning",
        ("plan", "design", "architecture", "roadmap", "philosophy"),
        "plan/design/architecture/roadmap/philosophy keyword matched",
    ),
    ("docs", ("docs", "readme", "manual", "explain"), "docs/readme/manual/explain keyword matched"),
)


TOOL_MAPPING: dict[ContextMode, list[str]] = {
    "balanced": ["token-optimizer"],
    "review-graph": ["code-review-graph", "token-optimizer"],
    "debug-focused": ["token-optimizer"],
    "planning": ["intent-layer", "token-optimizer"],
    "docs": ["token-optimizer"],
}


@dataclass(frozen=True)
class ContextPlan:
    task_description: str
    context_mode: ContextMode
    recommended_tools: list[str]
    selection_reason: str
    repo_root: Path
    current_branch: str
    git_status: list[str]
    changed_files: list[str]
    tasks: list[str]
    packet_path: Path
    events_path: Path


def detect_context_mode(task_description: str) -> ContextMode:
    text = task_description.lower()
    for mode, keywords, _reason in MODE_KEYWORDS:
        if any(re.search(rf"\b{re.escape(keyword)}\b", text) for keyword in keywords):
            return mode
    return "balanced"


def recommended_tools_for_mode(mode: ContextMode) -> list[str]:
    return list(TOOL_MAPPING[mode])


def plan_context(start: Path, task_description: str) -> ContextPlan:
    repo = _repo_root(start)
    mode = detect_context_mode(task_description)
    packet_path = start / ".devflow" / "token-context" / "current.md"
    events_path = start / ".devflow" / "token-context" / "events.jsonl"
    return ContextPlan(
        task_description=task_description,
        context_mode=mode,
        recommended_tools=recommended_tools_for_mode(mode),
        selection_reason=_selection_reason(task_description, mode),
        repo_root=repo,
        current_branch=_current_branch(repo),
        git_status=_git_status(repo),
        changed_files=_changed_files(repo),
        tasks=_task_summaries(start),
        packet_path=packet_path,
        events_path=events_path,
    )


def write_context_packet(start: Path, task_description: str) -> ContextPlan:
    plan = plan_context(start, task_description)
    plan.packet_path.parent.mkdir(parents=True, exist_ok=True)
    plan.packet_path.write_text(render_current_md(plan), encoding="utf-8")
    _append_event(plan)
    return plan


def render_current_md(plan: ContextPlan) -> str:
    tools = ", ".join(plan.recommended_tools)
    git_status = _bullet_lines(plan.git_status, empty="clean")
    changed_files = _bullet_lines(plan.changed_files, empty="none")
    tasks = _bullet_lines(plan.tasks, empty="none detected")
    canonical_docs = _bullet_lines(_canonical_docs(plan.repo_root), empty="none detected")
    mode_instruction = _mode_instruction(plan.context_mode)

    return (
        "# Dev-Flow Token Context Packet\n\n"
        "This file is a visible context plan for an IDE agent. It recommends what to read; it does not run token tools, install hooks, or route coding work.\n\n"
        "## Task\n\n"
        f"{plan.task_description}\n\n"
        "## Routing\n\n"
        f"- Context Mode: {plan.context_mode}\n"
        f"- Recommended Tools: {tools}\n"
        f"- Selection Reason: {plan.selection_reason}\n"
        "- Tool Behavior: recommendations only. No token tools were executed by this command. Missing tools do not block this packet.\n\n"
        "## Repo State\n\n"
        f"- Repo Root: {plan.repo_root}\n"
        f"- Current Branch: {plan.current_branch}\n\n"
        "### Git Status\n\n"
        f"{git_status}\n\n"
        "### Changed Files\n\n"
        f"{changed_files}\n\n"
        "### Dev-Flow Tasks\n\n"
        f"{tasks}\n\n"
        "## Read First\n\n"
        "1. Read this token-context packet first.\n"
        "2. Read the current git diff next.\n"
        "3. Read changed files before expanding to neighboring files.\n"
        "4. Read directly related tests before broader test suites.\n"
        "5. Read canonical MVP/philosophy docs after the diff and changed files.\n"
        "6. Read neighboring files only when imports, failing tests, or direct call paths require them.\n\n"
        "### Canonical MVP/Philosophy Docs\n\n"
        f"{canonical_docs}\n\n"
        "## Do Not Read Unless Necessary\n\n"
        "- Do not read unrelated legacy files as authority.\n"
        "- Do not read archived workflow docs unless the current MVP docs explicitly point there for salvage context.\n"
        "- Do not expand context just because it is available.\n"
        "- Do not enable hooks, MCP integrations, command rewrites, global shell behavior, or hidden automation from this packet.\n\n"
        "## Agent Instructions\n\n"
        "- Use the smallest sufficient context.\n"
        "- For implementation tasks, produce the smallest safe patch.\n"
        "- For review tasks, review changed files and dependency-adjacent files first.\n"
        "- For debugging tasks, start with failing output, changed files, and relevant tests.\n"
        f"- {mode_instruction}\n"
    )


def _selection_reason(task_description: str, mode: ContextMode) -> str:
    if mode == "balanced":
        return "no specialized routing keyword matched"
    text = task_description.lower()
    for candidate_mode, keywords, reason in MODE_KEYWORDS:
        if candidate_mode != mode:
            continue
        matched = [keyword for keyword in keywords if re.search(rf"\b{re.escape(keyword)}\b", text)]
        if matched:
            return f"{reason}: {', '.join(matched)}"
    return "specialized routing keyword matched"


def _repo_root(start: Path) -> Path:
    start_dir = start if start.is_dir() else start.parent
    result = _git(start_dir, ["rev-parse", "--show-toplevel"])
    if result:
        return Path(result[0]).resolve()
    return start_dir.resolve()


def _current_branch(repo: Path) -> str:
    branch = _git(repo, ["branch", "--show-current"])
    if branch and branch[0].strip():
        return branch[0].strip()
    head = _git(repo, ["rev-parse", "--short", "HEAD"])
    if head and head[0].strip():
        return f"detached:{head[0].strip()}"
    return "unknown"


def _git_status(repo: Path) -> list[str]:
    return _git(repo, ["status", "--short"]) or []


def _changed_files(repo: Path) -> list[str]:
    files: list[str] = []
    for line in _git_status(repo):
        if not line.strip():
            continue
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        files.append(path)
    return files


def _task_summaries(start: Path) -> list[str]:
    try:
        tasks = list_tasks(start)
    except Exception:
        return ["task state unreadable"]
    return [f"{task.id} {task.status}: {task.title}" for task in tasks]


def _canonical_docs(repo: Path) -> list[str]:
    candidates = [
        "PRODUCT_NORTH_STAR.md",
        "docs/control-room-mvp.md",
        "# CURRENT_MVP_5_28_26.md",
        "# DEVFLOW_PHILOSOPHY.md",
        "DEVFLOW_PHILOSOPHY.md",
    ]
    return [path for path in candidates if (repo / path).exists()]


def _mode_instruction(mode: ContextMode) -> str:
    if mode == "review-graph":
        return "Review mode: inspect changed files, dependency-adjacent files, and risk-bearing tests before broad repository reading."
    if mode == "debug-focused":
        return "Debug mode: start with failing output, changed files, and directly relevant tests."
    if mode == "planning":
        return "Planning mode: ground the plan in current MVP docs and existing task state before exploring neighboring architecture."
    if mode == "docs":
        return "Docs mode: read the target docs and adjacent source only when needed to verify accuracy."
    return "Balanced mode: read changed files and direct dependencies first, then stop when the patch is clear."


def _bullet_lines(values: list[str], empty: str) -> str:
    if not values:
        return f"- {empty}"
    return "\n".join(f"- {value}" for value in values)


def _append_event(plan: ContextPlan) -> None:
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": "token_context_planned",
        "task_description": plan.task_description,
        "context_mode": plan.context_mode,
        "recommended_tools": plan.recommended_tools,
        "selection_reason": plan.selection_reason,
        "repo_root": str(plan.repo_root),
        "current_branch": plan.current_branch,
        "changed_files": plan.changed_files,
        "packet_path": _relative(plan.repo_root, plan.packet_path),
    }
    plan.events_path.parent.mkdir(parents=True, exist_ok=True)
    with plan.events_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True) + "\n")


def _relative(root: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path)


def _git(cwd: Path, args: list[str]) -> list[str] | None:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            check=False,
            text=True,
            capture_output=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.splitlines()