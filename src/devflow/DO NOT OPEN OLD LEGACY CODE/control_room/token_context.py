from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal



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
    from devflow.legacy.control_room.scout import RepoScout
    scout = RepoScout(repo)
    return scout.get_git_status()


def _changed_files(repo: Path) -> list[str]:
    from devflow.legacy.control_room.scout import RepoScout
    scout = RepoScout(repo)
    return scout.get_changed_files()


def _task_summaries(start: Path, limit: int = 5) -> list[str]:
    try:
        tasks_dir = start / ".devflow" / "tasks"
        if not tasks_dir.exists():
            return []

        task_infos = []

        for path in sorted(tasks_dir.iterdir()):
            if not path.is_dir():
                continue

            yaml_path = path / "task.yaml"
            if not yaml_path.exists():
                continue

            # 1. Parse and validate canonical task.yaml first to guarantee authority
            task_yaml_valid = False
            yaml_id = None
            yaml_status = None
            yaml_title = None
            yaml_updated = None

            try:
                content = yaml_path.read_text(encoding="utf-8")
                id_match = re.search(r"^id:\s*(.+)$", content, re.MULTILINE)
                status_match = re.search(r"^status:\s*(.+)$", content, re.MULTILINE)
                title_match = re.search(r"^title:\s*(.+)$", content, re.MULTILINE)
                updated_match = re.search(r"^updated_at:\s*(.+)$", content, re.MULTILINE)

                if id_match and status_match and title_match and updated_match:
                    def _clean(val: str) -> str:
                        val = val.strip()
                        if val.startswith('"') and val.endswith('"'):
                            return val[1:-1]
                        if val.startswith("'") and val.endswith("'"):
                            return val[1:-1]
                        return val

                    yaml_id = _clean(id_match.group(1))
                    yaml_status = _clean(status_match.group(1))
                    yaml_title = _clean(title_match.group(1))
                    yaml_updated = _clean(updated_match.group(1))
                    task_yaml_valid = True
            except Exception:
                pass

            if not task_yaml_valid:
                raise ValueError("task state unreadable")

            # 2. Attempt to load summary.json for token efficiency (only if task.yaml is valid)
            task_id = yaml_id
            task_status = yaml_status
            task_title = yaml_title
            updated_at_str = yaml_updated

            summary_path = path / "summary.json"
            if summary_path.exists():
                try:
                    data = json.loads(summary_path.read_text(encoding="utf-8"))
                    # Hardened check: Verify task_id matches folder name and canonical values
                    if (isinstance(data.get("task_id"), str) and
                        data.get("task_id") == path.name and
                        data.get("task_id") == yaml_id and
                        isinstance(data.get("status"), str) and
                        data.get("status") == yaml_status and
                        isinstance(data.get("title"), str) and
                        isinstance(data.get("updated_at"), str)):
                        task_id = data["task_id"]
                        task_status = data["status"]
                        task_title = data["title"]
                        updated_at_str = data["updated_at"]
                except Exception:
                    pass

            try:
                clean_ts = updated_at_str.replace("Z", "+00:00")
                updated_at_dt = datetime.fromisoformat(clean_ts)
            except Exception:
                updated_at_dt = datetime.min.replace(tzinfo=timezone.utc)

            task_infos.append({
                "id": task_id,
                "status": task_status,
                "title": task_title,
                "updated_at": updated_at_dt
            })

        if not task_infos:
            return []

        # Sort tasks by most recently updated first
        task_infos.sort(key=lambda t: t["updated_at"], reverse=True)

        total_tasks = len(task_infos)
        truncated = task_infos[:limit]

        lines = [f"{task['id']} {task['status']}: {task['title']}" for task in truncated]

        if total_tasks > limit:
            lines.append(f"... and {total_tasks - limit} more task(s) omitted")

        return lines
    except Exception:
        return ["task state unreadable"]


def _canonical_docs(repo: Path) -> list[str]:
    candidates = [
        "docs/DEVFLOW_SOURCE_OF_TRUTH.md",
        "docs/README.md",
        "docs/local-worker-policy.md",
        "docs/verification-ledger.md",
    ]
    return [path for path in candidates if (repo / path).exists()]


def _mode_instruction(mode: ContextMode) -> str:
    if mode == "review-graph":
        return "Review mode: inspect changed files, dependency-adjacent files, and risk-bearing tests before broad repository reading."
    if mode == "debug-focused":
        return "Debug mode: start with failing output, changed files, and directly relevant tests."
    if mode == "planning":
        return "Planning mode: ground the plan in the active DevFlow source of truth and existing task state before exploring neighboring architecture."
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
