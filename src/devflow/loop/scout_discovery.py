"""Native V2 scout discovery — no legacy dependency.

Deterministic discovery for scout-first agent workflow packets. This is a
self-contained reimplementation of the orient/scout contract the V2 loop spine
consumes via ``devflow.loop.orient``. It replaces
``devflow.legacy.control_room.scout_discovery`` for the orient path.

Only the surfaces the orient step actually uses are implemented:
  - RepoScout.get_referenced_files / get_test_files / get_task_description
  - discover_agent_scout_context -> AgentScoutDiscovery
  - parse_handoff_doc / read_map_freshness / _extract_context_brief

The legacy original also pulled in persistence.get_task + paths.task_dir +
estimator.estimate_task_fit. For the orient path those only ever raised
KeyError (no task.yaml exists for a pipeline run_id) and were swallowed,
yielding empty scope. They are intentionally omitted here — native orient
does not depend on the legacy task workspace.

Public API mirrors the legacy contract 1:1 so ``devflow.loop.orient``
swaps with a one-line import change.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from typing import Any

VALID_AGENT_SCOUT_LANES = {
    "direct_tiny_edit",
    "deterministic_tool",
    "builder",
    "judge",
    "ask_user",
}
MAX_CONTEXT_BRIEF_SYMBOLS = 15
MAX_CONTEXT_BRIEF_IMPORTS = 10


def _extract_context_brief(root: Path, file_paths: list[str]) -> list[dict[str, Any]]:
    """Extract compact context for scoped files from the Context Map source index.

    Returns per-file: path, kind, module, symbols (names+types), imports, headings.
    This is the context firewall — the frontier reads this instead of raw source.
    """
    source_path = root / ".context-map" / "source-index.json"
    if not source_path.is_file():
        return []
    try:
        index_data = json.loads(source_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    files_list = index_data.get("files") if isinstance(index_data, dict) else None
    if not isinstance(files_list, list):
        return []
    by_path: dict[str, dict[str, Any]] = {}
    for entry in files_list:
        if isinstance(entry, dict) and "path" in entry:
            by_path[str(entry["path"])] = entry
    brief: list[dict[str, Any]] = []
    for rel_path in file_paths:
        entry = by_path.get(rel_path)
        if not entry:
            continue
        symbols = entry.get("symbols") or []
        imports = entry.get("imports") or []
        headings = entry.get("headings") or []
        compact_symbols: list[dict[str, str]] = []
        for sym in symbols[:MAX_CONTEXT_BRIEF_SYMBOLS]:
            if isinstance(sym, dict):
                compact_symbols.append(
                    {
                        "name": str(sym.get("name", "")),
                        "type": str(sym.get("type", sym.get("kind", ""))),
                        "line": str(sym.get("line", sym.get("start_line", ""))),
                    }
                )
            elif isinstance(sym, str):
                compact_symbols.append({"name": sym, "type": "", "line": ""})
        compact_imports = [str(imp) for imp in imports[:MAX_CONTEXT_BRIEF_IMPORTS] if imp]
        compact_headings = [str(h) for h in headings[:10] if h]
        brief.append(
            {
                "path": rel_path,
                "kind": str(entry.get("kind", "")),
                "module": str(entry.get("module") or ""),
                "symbols": compact_symbols,
                "imports": compact_imports,
                "headings": compact_headings,
            }
        )
    return brief


@dataclass(frozen=True)
class HandoffContext:
    """Compact facts parsed from a handoff markdown file."""

    path: str | None
    read: bool
    title: str
    task_text: str
    target_files: list[str]
    tests: list[str]
    verification: str | None
    constraints: list[str]


@dataclass(frozen=True)
class AgentScoutDiscovery:
    """Discovered ScoutPacket fields for `devflow agent scout`."""

    handoff_path: str | None
    handoff_read: bool
    files_to_touch: list[str]
    files_to_read_next: list[dict[str, str]]
    tests: list[str]
    risks: list[str]
    recommended_lane: str
    verification: str
    map_freshness: dict[str, str]
    evidence_paths: list[str]
    context_brief: list[dict[str, Any]]


def _relative(root: Path, path: Path | str) -> str:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = root / candidate
    try:
        return str(candidate.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(candidate)


def _section(markdown: str, heading: str) -> str:
    pattern = re.compile(
        rf"^##\s+{re.escape(heading)}\s*$\n(?P<body>.*?)(?=^##\s+|\Z)",
        re.IGNORECASE | re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(markdown)
    return match.group("body").strip() if match else ""


def _bullet_lines(section_text: str) -> list[str]:
    values: list[str] = []
    for line in section_text.splitlines():
        stripped = line.strip()
        if stripped.startswith(("-", "*")):
            values.append(stripped[1:].strip())
    return values


def _extract_path(text: str) -> str | None:
    cleaned = text.strip().strip("`")
    backticked = re.search(r"`([^`]+)`", cleaned)
    if backticked:
        return backticked.group(1).strip()
    match = re.search(
        r"((?:src|tests|docs|\.devflow|scripts)/[^\s,;)]+|[A-Z_]+\.md|AGENTS\.md|CONTEXT\.md)",
        cleaned,
    )
    if match:
        return match.group(1).strip().strip("`.,")
    first = cleaned.split(" (", 1)[0].split(" — ", 1)[0].split(" - ", 1)[0].strip()
    return first or None


def _extract_pytest_tests(command: str | None) -> list[str]:
    if not command:
        return []
    tests: list[str] = []
    for match in re.finditer(r"--pytest\s+(\"([^\"]+)\"|'([^']+)'|(\S+))", command):
        value = next(group for group in match.groups() if group)
        tests.extend(part for part in value.split() if part)
    return tests


def _extract_verification(commands_section: str) -> str | None:
    if not commands_section:
        return None
    normalized = re.sub(r"```(?:bash|shell|sh)?", "", commands_section)
    normalized = normalized.replace("```", "")
    normalized = re.sub(r"\\\n\s*", " ", normalized)
    candidates = [line.strip() for line in normalized.splitlines() if line.strip()]
    joined = " ".join(candidates)
    if "local_test_runner.py" in joined:
        before, _, after = joined.partition("local_test_runner.py")
        prefix = before.rsplit("python3", 1)[-1] if "python3" in before else before
        command = ("python3" + prefix + "local_test_runner.py" + after).strip()
        return re.sub(r"\s+", " ", command)
    for candidate in candidates:
        if "pytest" in candidate or "ruff" in candidate:
            return candidate
    return None


def parse_handoff_doc(root: Path | str, handoff: str | None) -> HandoffContext:
    """Parse the standard DevFlow handoff sections used by agent scouts."""
    repo_root = Path(root).resolve()
    if not handoff:
        return HandoffContext(None, False, "", "", [], [], None, [])
    path = (repo_root / handoff).resolve()
    if not path.is_file():
        return HandoffContext(_relative(repo_root, path), False, "", "", [], [], None, [])
    markdown = path.read_text(encoding="utf-8")
    title = next(
        (line.lstrip("# ").strip() for line in markdown.splitlines() if line.startswith("#")),
        "",
    )
    task_text = _section(markdown, "Task")
    target_files = [
        target for item in _bullet_lines(_section(markdown, "Target files"))
        if (target := _extract_path(item))
    ]
    commands = _section(markdown, "Commands")
    verification = _extract_verification(commands)
    tests = _extract_pytest_tests(verification)
    constraints = _bullet_lines(_section(markdown, "Constraints"))
    return HandoffContext(
        _relative(repo_root, path),
        True,
        title,
        task_text,
        target_files,
        tests,
        verification,
        constraints,
    )


def read_map_freshness(root: Path | str) -> dict[str, str]:
    """Return compact map freshness without exposing raw index contents."""
    repo_root = Path(root).resolve()
    source_index = "missing"
    graphify = "missing"

    source_path = repo_root / ".context-map" / "source-index.json"
    if source_path.is_file():
        try:
            source_data = json.loads(source_path.read_text(encoding="utf-8"))
            files = source_data.get("files") if isinstance(source_data, dict) else None
            source_index = "ok" if files else "empty"
        except (OSError, json.JSONDecodeError):
            source_index = "unreadable"

    graph_path = repo_root / ".context-map" / "graphify-freshness.json"
    if graph_path.is_file():
        try:
            graph_data = json.loads(graph_path.read_text(encoding="utf-8"))
            graphify = str(graph_data.get("status") or "ok") if isinstance(graph_data, dict) else "ok"
        except (OSError, json.JSONDecodeError):
            graphify = "unreadable"

    if source_index == "ok" and graphify not in {"missing", "unreadable"}:
        confidence = "high"
    elif source_index == "ok":
        confidence = "medium"
    else:
        confidence = "low"
    return {"source_index": source_index, "graphify": graphify, "confidence": confidence}


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _existing_paths(root: Path, values: list[str]) -> list[Path]:
    paths: list[Path] = []
    for value in values:
        candidate = root / value
        paths.append(candidate if candidate.exists() else Path(value))
    return paths


# ---------------------------------------------------------------------------
# Native RepoScout — only the methods the orient path consumes.
# ---------------------------------------------------------------------------
class RepoScout:
    """Repository scanning engine for the V2 orient step (native, no legacy deps)."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self._referenced_cache: dict[tuple[str, str], list[Path]] = {}
        self._test_files_cache: dict[str, list[Path]] = {}

    def get_referenced_files(self, title: str, description: str) -> list[Path]:
        """Scan title and description to extract referenced codebase file paths."""
        cache_key = (title, description)
        if cache_key in self._referenced_cache:
            return self._referenced_cache[cache_key]

        file_pattern = re.compile(r"\b[a-zA-Z0-9_\-./]+\.[a-zA-Z0-9]+\b")
        referenced_matches = file_pattern.findall(f"{title} {description}")

        referenced_files: list[Path] = []
        for match in referenced_matches:
            if match.startswith(".devflow"):
                continue
            candidate = self.root / match
            if candidate.exists() and candidate.is_file():
                if candidate not in referenced_files:
                    referenced_files.append(candidate)
            else:
                try:
                    for p in self.root.glob(f"**/{match}"):
                        if p.is_file() and not any(
                            part.startswith(".") for part in p.relative_to(self.root).parts
                        ):
                            if p not in referenced_files:
                                referenced_files.append(p)
                                break
                except Exception:
                    pass
        self._referenced_cache[cache_key] = referenced_files
        return referenced_files

    def get_test_files(self, relevant_files: list[Path]) -> list[Path]:
        """Find matching test coverage files for a list of relevant files."""
        test_files: list[Path] = []
        for f in relevant_files:
            if "test" in f.name.lower() or f.parent.name == "tests":
                if f not in test_files:
                    test_files.append(f)
                continue
            if f.suffix == ".py":
                t1 = self.root / "tests" / f"test_{f.name}"
                t2 = f.parent / f"test_{f.name}"
                if t1.exists() and t1.is_file() and t1 not in test_files:
                    test_files.append(t1)
                if t2.exists() and t2.is_file() and t2 not in test_files:
                    test_files.append(t2)
        return test_files

    def get_task_description(self, task_id: str) -> str:
        """Extract a task's full description from its task.yaml configuration.

        Native orient never provisions a task workspace for a pipeline run,
        so this returns "" unless a ``task.yaml`` genuinely exists at the
        legacy-style task dir. Kept for API parity with the original.
        """
        task_yaml_path = self.root / ".devflow" / "tasks" / task_id / "task.yaml"
        if task_yaml_path.exists():
            try:
                content = task_yaml_path.read_text(encoding="utf-8")
                desc_match = re.search(r"^description:\s*(.+)$", content, re.MULTILINE)
                if desc_match:
                    return desc_match.group(1).strip().strip("'\"")
            except Exception:
                pass
        return ""


def _task_scope_text(scout: RepoScout, task_id: str) -> tuple[str, str, str | None]:
    """Return task-derived title, description, and verification.

    Native version: no legacy get_task/persistence dependency. Returns empty
    scope unless a real task.yaml exists (which it does not for orient runs).
    """
    description = scout.get_task_description(task_id)
    return "", description, None


def _scope_missing_risk(context: HandoffContext) -> str:
    if context.path and not context.read:
        return f"handoff path was provided but not readable: {context.path}"
    return "no scoped handoff, task record, referenced files, or explicit file override; dirty worktree was not used as implementation scope"


def _risks(
    context: HandoffContext,
    files_to_touch: list[str],
    tests: list[str],
    freshness: dict[str, str],
) -> list[str]:
    risks: list[str] = []
    if len(files_to_touch) > 1:
        risks.append("multi-file edit scope requires focused verification")
    if not tests:
        risks.append("no focused tests discovered")
    if freshness.get("confidence") == "low":
        risks.append("codebase map freshness is low or missing")
    risks.extend(context.constraints[:3])
    return _unique(risks or ["no major deterministic scout risks detected"])


def _lane(files_to_touch: list[str], tests: list[str], risks: list[str], requested: str | None) -> str:
    if requested and requested != "auto":
        return requested if requested in VALID_AGENT_SCOUT_LANES else "ask_user"
    if any("deterministic tool" in risk.lower() or "extract_module" in risk for risk in risks):
        return "deterministic_tool"
    if len(files_to_touch) <= 2 and tests:
        return "direct_tiny_edit"
    if len(files_to_touch) > 3:
        return "builder"
    return "direct_tiny_edit"


def discover_agent_scout_context(
    root: Path | str,
    task_id: str,
    *,
    handoff: str | None = None,
    files_to_touch: list[str] | None = None,
    files_to_read_next: list[dict[str, str]] | None = None,
    tests: list[str] | None = None,
    risks: list[str] | None = None,
    recommended_lane: str | None = None,
    verification: str | None = None,
) -> AgentScoutDiscovery:
    """Use repo-local deterministic scouts to build a compact ScoutPacket."""
    repo_root = Path(root).resolve()
    scout = RepoScout(repo_root)
    context = parse_handoff_doc(repo_root, handoff)
    freshness = read_map_freshness(repo_root)

    task_title, task_description, task_verification = _task_scope_text(scout, task_id)
    scope_title = context.title or task_title
    description = "\n".join(
        part
        for part in [context.task_text, "\n".join(context.constraints), task_description]
        if part
    )
    has_scope = bool(files_to_touch or context.read or task_title or task_description)
    discovered_files = list(context.target_files)
    if not discovered_files:
        discovered_files.extend(
            _relative(repo_root, path) for path in scout.get_referenced_files(scope_title, description)
        )
    resolved_files = _unique(files_to_touch or discovered_files)

    relevant_paths = _existing_paths(repo_root, resolved_files)
    discovered_tests = [
        *_extract_pytest_tests(context.verification),
        *(_relative(repo_root, path) for path in scout.get_test_files(relevant_paths)),
    ]
    resolved_tests = _unique(tests or discovered_tests)

    resolved_read_next = list(files_to_read_next or [])
    if not resolved_read_next:
        resolved_read_next = [
            {"path": path, "reason": "scout-discovered implementation target"}
            for path in resolved_files[:5]
        ]

    resolved_verification = verification or context.verification or task_verification
    if not resolved_verification:
        if resolved_files:
            pytest_arg = " ".join(resolved_tests) if resolved_tests else "tests"
            resolved_verification = (
                "python3 ~/.hermes/skills/software-development/local-fleet-efficiency/scripts/local_test_runner.py "
                f'--pytest "{pytest_arg}" --project-root . --python .venv/bin/python --task-id {task_id}'
            )
        else:
            resolved_verification = f"blocked: provide scoped --handoff or --file-to-touch before verifying {task_id}"

    resolved_risks = _unique(risks or _risks(context, resolved_files, resolved_tests, freshness))
    if not has_scope or not resolved_files:
        resolved_risks = _unique([_scope_missing_risk(context), *resolved_risks])
        lane = "ask_user" if recommended_lane in {None, "auto"} else _lane(
            resolved_files, resolved_tests, resolved_risks, recommended_lane
        )
    else:
        lane = _lane(resolved_files, resolved_tests, resolved_risks, recommended_lane)

    evidence_paths = [f".devflow/evidence/scout-{task_id}.json"]
    if context.path:
        evidence_paths.append(context.path)

    context_brief = _extract_context_brief(repo_root, resolved_files)

    return AgentScoutDiscovery(
        handoff_path=context.path,
        handoff_read=context.read,
        files_to_touch=resolved_files,
        files_to_read_next=resolved_read_next,
        tests=resolved_tests,
        risks=resolved_risks,
        recommended_lane=lane,
        verification=resolved_verification,
        map_freshness=freshness,
        evidence_paths=evidence_paths,
        context_brief=context_brief,
    )
