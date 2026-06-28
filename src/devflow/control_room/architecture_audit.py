from __future__ import annotations

import ast
import json
import re
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel, Field

from devflow.control_room.persistence import atomic_write_text

GRAPHIFY_REQUIREMENT = "graphifyy>=0.8.50,<0.9"
CHECKPOINT_PATH = Path("docs/architecture/control-room-architecture-audit.md")


class ArchitectureAuditError(Exception):
    """Raised when the architecture audit cannot complete safely."""


class GraphifyStatus(BaseModel):
    available: bool
    path: str | None = None
    install_status: str = "not_requested"
    requirement: str = GRAPHIFY_REQUIREMENT
    install_command: list[str] = Field(
        default_factory=lambda: [sys.executable, "-m", "pip", "install", GRAPHIFY_REQUIREMENT]
    )


class GraphMetrics(BaseModel):
    files: int | None = None
    approximate_words: int | None = None
    nodes: int | None = None
    edges: int | None = None
    communities: int | None = None
    shown_communities: int | None = None
    thin_omitted_communities: int | None = None
    extracted_edge_percent: int | None = None
    inferred_edge_percent: int | None = None
    ambiguous_edge_percent: int | None = None


class DiagnosticStatus(BaseModel):
    status: str = "not_run"
    issue_count: int | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class HotspotRow(BaseModel):
    path: str
    lines: int
    definition_count: int
    local_import_count: int
    score: int
    known_boundary_target: bool = False


class ArchitectureAuditResult(BaseModel):
    graphify: GraphifyStatus
    graph_metrics: GraphMetrics = Field(default_factory=GraphMetrics)
    diagnostic: DiagnosticStatus = Field(default_factory=DiagnosticStatus)
    hotspots: list[HotspotRow] = Field(default_factory=list)
    generated_artifact_paths: list[str] = Field(default_factory=list)
    recommended_cleanup_targets: list[str] = Field(default_factory=list)
    graphify_commands: list[list[str]] = Field(default_factory=list)
    checkpoint_path: Path | None = None


CommandRunner = Callable[[list[str]], subprocess.CompletedProcess[str]]
GraphifyFinder = Callable[[], Path | None]

_METRIC_FIELDS = {
    "files": "files",
    "approximate words": "approximate_words",
    "nodes": "nodes",
    "edges": "edges",
    "communities": "communities",
    "shown communities": "shown_communities",
    "thin omitted communities": "thin_omitted_communities",
    "extracted edges": "extracted_edge_percent",
    "inferred edges": "inferred_edge_percent",
    "ambiguous edges": "ambiguous_edge_percent",
}
_GENERATED_DIR_PARTS = {
    ".devflow",
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "graphify-out",
    "htmlcov",
    "node_modules",
    "scratch",
    "venv",
}
_KNOWN_BOUNDARY_TARGETS = {
    "src/devflow/cli.py",
    "src/devflow/control_room/agent_onboarding.py",
    "src/devflow/control_room/agent_registry.py",
    "src/devflow/control_room/dogfood.py",
    "src/devflow/control_room/loop_engine.py",
    "src/devflow/control_room/operating_layer_server.py",
    "src/devflow/control_room/service.py",
    "src/devflow/control_room/supervisor_surface.py",
    "src/devflow/control_room/task_packet.py",
}
_EXPECTED_GRAPHIFY_ARTIFACTS = (
    Path("graphify-out/GRAPH_REPORT.md"),
    Path("graphify-out/graph.json"),
    Path("graphify-out/GRAPH_TREE.html"),
)


def run_architecture_audit(
    root: Path,
    *,
    install_graphify: bool = False,
    write_doc: bool = False,
    graphify_finder: GraphifyFinder | None = None,
    command_runner: Callable[[list[str]], subprocess.CompletedProcess[str]] | None = None,
) -> ArchitectureAuditResult:
    """Run the Dev-Flow architecture audit and optionally write the checkpoint doc."""
    root = root.resolve()
    run_command = command_runner or _run_command

    install_status = "not_requested"
    if install_graphify:
        install_result = run_command([sys.executable, "-m", "pip", "install", GRAPHIFY_REQUIREMENT], cwd=root)
        if install_result.returncode != 0:
            detail = _command_failure_detail(install_result)
            raise ArchitectureAuditError(f"Failed to install Graphify with {GRAPHIFY_REQUIREMENT}. {detail}")
        graphify_path = _find_graphify_for_root(root, graphify_finder)
        if graphify_path is None:
            raise ArchitectureAuditError(
                f"Installed {GRAPHIFY_REQUIREMENT}, but the 'graphify' executable was not found on PATH, "
                "under the project virtualenv, or beside the active Python executable."
            )
        install_status = "installed"
    else:
        graphify_path = _find_graphify_for_root(root, graphify_finder)
        if graphify_path is None:
            raise ArchitectureAuditError(
                "Graphify is not installed. Default audit mode is read-only and will not mutate the environment. "
                f"Run 'devflow architecture audit --install-graphify' to install {GRAPHIFY_REQUIREMENT}, "
                "or install it manually in the active Python environment."
            )

    graphify_executable = graphify_path.as_posix()
    command_specs = [
        [graphify_executable, "update", "."],
        [graphify_executable, "export", "callflow-html"],
        [graphify_executable, "tree", "--label", "Dev-Flow"],
        [graphify_executable, "diagnose", "multigraph", "--json"],
    ]
    completed: list[subprocess.CompletedProcess[str]] = []
    for command in command_specs:
        completed.append(_run_graphify_command(command, root=root, command_runner=run_command))

    diagnostic = _diagnostic_from_process(completed[-1])
    report_path = root / "graphify-out" / "GRAPH_REPORT.md"
    graph_metrics = (
        parse_graph_report_metrics(report_path.read_text(encoding="utf-8")) if report_path.exists() else GraphMetrics()
    )
    hotspots = scan_architecture_hotspots(root)
    result = ArchitectureAuditResult(
        graphify=GraphifyStatus(
            available=True,
            path=graphify_executable,
            install_status=install_status,
        ),
        graph_metrics=graph_metrics,
        diagnostic=diagnostic,
        hotspots=hotspots,
        generated_artifact_paths=_generated_artifact_paths(root),
        recommended_cleanup_targets=recommend_cleanup_targets(hotspots),
        graphify_commands=command_specs,
    )
    if write_doc:
        target = root / CHECKPOINT_PATH
        atomic_write_text(target, render_architecture_audit_checkpoint(result))
        result = result.model_copy(update={"checkpoint_path": target})
    return result


def parse_graph_report_metrics(text: str) -> GraphMetrics:
    """Parse the concise metrics table from Graphify's GRAPH_REPORT.md."""
    values: dict[str, int] = {}
    for line in text.splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 2:
            continue
        key = cells[0].lower()
        if key not in _METRIC_FIELDS:
            continue
        values[_METRIC_FIELDS[key]] = _parse_metric_value(cells[1])

    for field, value in _parse_metric_fallback_lines(text).items():
        values.setdefault(field, value)
    return GraphMetrics(**values)


def scan_architecture_hotspots(root: Path, *, limit: int = 20) -> list[HotspotRow]:
    """Rank local Python files by size, definitions, local imports, and boundary-target weight."""
    root = root.resolve()
    rows: list[HotspotRow] = []
    for path in root.rglob("*.py"):
        rel_path = path.relative_to(root).as_posix()
        if _is_excluded_source_path(path.relative_to(root)):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        lines = len(text.splitlines())
        definition_count, local_import_count = _static_counts(text, filename=rel_path)
        known_boundary = _is_known_boundary_target(rel_path)
        score = lines + definition_count * 25 + local_import_count * 15 + (75 if known_boundary else 0)
        rows.append(
            HotspotRow(
                path=rel_path,
                lines=lines,
                definition_count=definition_count,
                local_import_count=local_import_count,
                score=score,
                known_boundary_target=known_boundary,
            )
        )
    return sorted(rows, key=lambda row: (-row.score, -row.lines, row.path))[:limit]


def recommend_cleanup_targets(hotspots: list[HotspotRow], *, limit: int = 10) -> list[str]:
    ranked = sorted(hotspots, key=lambda row: (not row.known_boundary_target, -row.score, -row.lines, row.path))
    return [row.path for row in ranked[:limit]]


def render_architecture_audit_checkpoint(result: ArchitectureAuditResult) -> str:
    metrics = result.graph_metrics
    lines = [
        "# Control-Room Architecture Audit",
        "",
        f"Date: {date.today().isoformat()}",
        "Status: Fresh architecture checkpoint generated by `devflow architecture audit --write-doc`",
        "",
        "Graphify is evidence, not authority. Use it to choose cleanup targets, then verify behavior with tests "
        "and Dev-Flow evidence before claiming architecture improvement.",
        "",
        "Generated Graphify artifacts are local by default and should stay under ignored `graphify-out/` unless "
        "a later task explicitly chooses specific outputs for versioning.",
        "",
        "## Snapshot Metrics",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Nodes | {_format_metric(metrics.nodes)} |",
        f"| Edges | {_format_metric(metrics.edges)} |",
        f"| Communities | {_format_metric(metrics.communities)} |",
        f"| Extracted edges | {_format_percent(metrics.extracted_edge_percent)} |",
        f"| Inferred edges | {_format_percent(metrics.inferred_edge_percent)} |",
        f"| Ambiguous edges | {_format_percent(metrics.ambiguous_edge_percent)} |",
        "",
        "## Graphify Artifacts",
        "",
    ]
    if result.generated_artifact_paths:
        lines.extend(f"- `{path}`" for path in result.generated_artifact_paths)
    else:
        lines.append("- No generated artifacts were found after the audit run.")
    lines.extend(
        [
            "",
            "## Diagnostic Status",
            "",
            f"- Status: `{result.diagnostic.status}`",
            f"- Issue count: `{_format_metric(result.diagnostic.issue_count)}`",
            "",
            "## Hotspots",
            "",
            "| Rank | Path | Lines | Definitions | Local imports | Boundary target |",
            "|---:|---|---:|---:|---:|---|",
        ]
    )
    for index, row in enumerate(result.hotspots[:10], start=1):
        boundary = "yes" if row.known_boundary_target else "no"
        lines.append(
            f"| {index} | `{row.path}` | {row.lines:,} | {row.definition_count:,} | "
            f"{row.local_import_count:,} | {boundary} |"
        )
    lines.extend(
        [
            "",
            "## Recommended Cleanup Targets",
            "",
        ]
    )
    if result.recommended_cleanup_targets:
        lines.extend(f"{index}. `{path}`" for index, path in enumerate(result.recommended_cleanup_targets, start=1))
    else:
        lines.append("No cleanup targets were ranked.")
    lines.extend(
        [
            "",
            "## Selection Rules",
            "",
            "Cleanup targets are selected from metric deltas, high-degree graph nodes, module size, local import "
            "fan-in, and boundary clarity. Actual refactors should be separate Dev-Flow tasks chosen from this "
            "evidence.",
            "",
        ]
    )
    return "\n".join(lines)


def render_architecture_audit_lines(result: ArchitectureAuditResult) -> list[str]:
    metrics = result.graph_metrics
    lines = [
        "Architecture audit completed.",
        f"graphify: {result.graphify.path} ({result.graphify.install_status})",
        f"metrics: nodes={_format_metric(metrics.nodes)} edges={_format_metric(metrics.edges)} "
        f"communities={_format_metric(metrics.communities)}",
        f"diagnostic: {result.diagnostic.status} issues={_format_metric(result.diagnostic.issue_count)}",
        "artifacts:",
    ]
    if result.generated_artifact_paths:
        lines.extend(f"  - {path}" for path in result.generated_artifact_paths)
    else:
        lines.append("  - none")
    lines.append("recommended cleanup targets:")
    if result.recommended_cleanup_targets:
        lines.extend(f"  {index}. {path}" for index, path in enumerate(result.recommended_cleanup_targets, start=1))
    else:
        lines.append("  - none")
    if result.checkpoint_path is not None:
        lines.append(f"checkpoint: {result.checkpoint_path}")
    return lines


def _find_graphify_for_root(root: Path, graphify_finder: GraphifyFinder | None) -> Path | None:
    if graphify_finder is not None:
        return graphify_finder()
    return _find_graphify(root)


def _find_graphify(root: Path | None = None) -> Path | None:
    executable_path = Path(sys.executable)
    executable_dirs = [executable_path.parent]
    resolved_executable_dir = executable_path.resolve().parent
    if resolved_executable_dir not in executable_dirs:
        executable_dirs.append(resolved_executable_dir)

    candidates: list[Path] = []
    if root is not None:
        candidates.extend(
            [
                root / ".venv" / "bin" / "graphify",
                root / ".venv" / "Scripts" / "graphify.exe",
                root / "venv" / "bin" / "graphify",
                root / "venv" / "Scripts" / "graphify.exe",
            ]
        )
    for executable_dir in executable_dirs:
        candidates.extend([executable_dir / "graphify", executable_dir / "graphify.exe"])

    seen: set[Path] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        if candidate.exists():
            return candidate
    discovered = shutil.which("graphify")
    return Path(discovered) if discovered else None


def _run_command(command: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False)


def _run_graphify_command(
    command: list[str],
    *,
    root: Path,
    command_runner: Callable[[list[str]], subprocess.CompletedProcess[str]],
) -> subprocess.CompletedProcess[str]:
    completed = command_runner(command, cwd=root)
    if completed.returncode != 0:
        raise ArchitectureAuditError(
            f"Graphify command failed: {' '.join(command)}. {_command_failure_detail(completed)}"
        )
    return completed


def _command_failure_detail(completed: subprocess.CompletedProcess[str]) -> str:
    pieces = [f"exit_code={completed.returncode}"]
    if completed.stderr.strip():
        pieces.append(f"stderr={completed.stderr.strip()}")
    if completed.stdout.strip():
        pieces.append(f"stdout={completed.stdout.strip()}")
    return "; ".join(pieces)


def _diagnostic_from_process(completed: subprocess.CompletedProcess[str]) -> DiagnosticStatus:
    raw_text = completed.stdout.strip()
    if not raw_text:
        return DiagnosticStatus(status="ok", issue_count=0, raw={})
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        return DiagnosticStatus(status="ok", issue_count=None, raw={"stdout": raw_text})
    if not isinstance(parsed, dict):
        return DiagnosticStatus(status="ok", issue_count=None, raw={"diagnostic": parsed})
    status = str(parsed.get("status") or parsed.get("result") or "ok")
    issue_count = _diagnostic_issue_count(parsed)
    return DiagnosticStatus(status=status, issue_count=issue_count, raw=parsed)


def _diagnostic_issue_count(payload: dict[str, Any]) -> int | None:
    for key in ("issue_count", "issues_count", "errors_count", "error_count"):
        value = payload.get(key)
        if isinstance(value, int):
            return value
    issues = payload.get("issues")
    if isinstance(issues, list):
        return len(issues)
    count = 0
    found_issue_list = False
    for value in payload.values():
        if isinstance(value, list) and value and all(isinstance(item, (str, dict)) for item in value):
            found_issue_list = True
            count += len(value)
    return count if found_issue_list else None


def _parse_metric_value(raw: str) -> int:
    cleaned = raw.strip().rstrip("%").replace(",", "")
    match = re.search(r"-?\d+", cleaned)
    return int(match.group(0)) if match else 0


def _parse_metric_fallback_lines(text: str) -> dict[str, int]:
    values: dict[str, int] = {}
    for label, field in _METRIC_FIELDS.items():
        pattern = re.compile(rf"\b{re.escape(label)}\b\s*:\s*([0-9,]+%?)", re.IGNORECASE)
        match = pattern.search(text)
        if match:
            values[field] = _parse_metric_value(match.group(1))
    corpus_match = re.search(
        r"(?P<files>[0-9,]+)\s+files\s*[\u00b7\u2022]\s*~?(?P<words>[0-9,]+)\s+words",
        text,
        re.IGNORECASE,
    )
    if corpus_match:
        values["files"] = _parse_metric_value(corpus_match.group("files"))
        values["approximate_words"] = _parse_metric_value(corpus_match.group("words"))
    summary_match = re.search(
        r"(?P<nodes>[0-9,]+)\s+nodes\s*[\u00b7\u2022]\s*"
        r"(?P<edges>[0-9,]+)\s+edges\s*[\u00b7\u2022]\s*"
        r"(?P<communities>[0-9,]+)\s+communities\s*"
        r"\((?P<shown>[0-9,]+)\s+shown,\s*(?P<thin>[0-9,]+)\s+thin omitted\)",
        text,
        re.IGNORECASE,
    )
    if summary_match:
        values["nodes"] = _parse_metric_value(summary_match.group("nodes"))
        values["edges"] = _parse_metric_value(summary_match.group("edges"))
        values["communities"] = _parse_metric_value(summary_match.group("communities"))
        values["shown_communities"] = _parse_metric_value(summary_match.group("shown"))
        values["thin_omitted_communities"] = _parse_metric_value(summary_match.group("thin"))
    extraction_match = re.search(
        r"Extraction:\s*(?P<extracted>[0-9,]+)%\s+EXTRACTED\s*[\u00b7\u2022]\s*"
        r"(?P<inferred>[0-9,]+)%\s+INFERRED\s*[\u00b7\u2022]\s*"
        r"(?P<ambiguous>[0-9,]+)%\s+AMBIGUOUS",
        text,
        re.IGNORECASE,
    )
    if extraction_match:
        values["extracted_edge_percent"] = _parse_metric_value(extraction_match.group("extracted"))
        values["inferred_edge_percent"] = _parse_metric_value(extraction_match.group("inferred"))
        values["ambiguous_edge_percent"] = _parse_metric_value(extraction_match.group("ambiguous"))
    return values


def _is_excluded_source_path(path: Path) -> bool:
    parts = set(path.parts)
    if parts & _GENERATED_DIR_PARTS:
        return True
    return path.as_posix().startswith("src/devflow/_legacy/")


def _static_counts(text: str, *, filename: str) -> tuple[int, int]:
    try:
        tree = ast.parse(text, filename=filename)
    except SyntaxError:
        return 0, _regex_local_import_count(text)
    definitions = sum(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) for node in ast.walk(tree)
    )
    imports = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(alias.name == "devflow" or alias.name.startswith("devflow.") for alias in node.names):
                imports += 1
        elif isinstance(node, ast.ImportFrom):
            if node.level > 0 or (node.module and (node.module == "devflow" or node.module.startswith("devflow."))):
                imports += 1
    return definitions, imports


def _regex_local_import_count(text: str) -> int:
    count = 0
    for line in text.splitlines():
        stripped = line.strip()
        if (
            stripped.startswith("from .")
            or stripped.startswith("from devflow")
            or stripped.startswith("import devflow")
        ):
            count += 1
    return count


def _is_known_boundary_target(rel_path: str) -> bool:
    if rel_path in _KNOWN_BOUNDARY_TARGETS:
        return True
    return rel_path.startswith("src/devflow/control_room/operating_layer") and rel_path.endswith(".py")


def _generated_artifact_paths(root: Path) -> list[str]:
    paths: list[str] = []
    for path in _EXPECTED_GRAPHIFY_ARTIFACTS[:2]:
        if (root / path).exists():
            paths.append(path.as_posix())
    paths.extend(
        path.relative_to(root).as_posix()
        for path in sorted((root / "graphify-out").glob("*-callflow.html"))
        if path.is_file()
    )
    for path in _EXPECTED_GRAPHIFY_ARTIFACTS[2:]:
        if (root / path).exists():
            paths.append(path.as_posix())
    return paths


def _format_metric(value: int | None) -> str:
    return "unknown" if value is None else f"{value:,}"


def _format_percent(value: int | None) -> str:
    return "unknown" if value is None else f"{value}%"
