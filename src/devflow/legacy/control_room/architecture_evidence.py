from __future__ import annotations

import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from devflow.legacy.control_room.architecture_audit import (
    DiagnosticStatus,
    GraphMetrics,
    parse_graph_report_metrics,
)


GRAPHIFY_REPORT_PATH = Path("graphify-out/GRAPH_REPORT.md")
GRAPHIFY_OUT_DIR = Path("graphify-out")
ARCHITECTURE_REFRESH_COMMAND = "devflow architecture audit --install-graphify --write-doc"

_VIEWER_CONTENT_TYPES = {
    "markdown": "text/markdown",
    "json": "application/json",
    "sandboxed_html": "text/html",
}


class ArchitectureEvidenceFreshness(BaseModel):
    status: str = "missing"
    built_commit: str | None = None
    head_commit: str | None = None
    report_date: str | None = None
    generated_at: str | None = None
    detail: str = "Graphify report is missing."


class ArchitectureEvidenceArtifact(BaseModel):
    artifact_id: str
    label: str
    path: str
    kind: str
    viewer: str = "markdown"
    content_type: str = "text/markdown"
    view_url: str = ""
    status: str = "available"


class ArchitectureEvidenceRefreshAction(BaseModel):
    label: str
    command: str
    requires_human_approval: bool = True
    safety_class: str = "approval_required_evidence_writing"



class ArchitectureEvidenceHotspot(BaseModel):
    label: str
    detail: str
    score: int | None = None
    source: str = "graphify_report"


class ArchitectureEvidenceQuestion(BaseModel):
    question: str
    reason: str = ""


class ArchitectureEvidenceProjection(BaseModel):
    schema_version: int = 1
    status: str = "missing"
    read_only: bool = True
    source_path: str = GRAPHIFY_REPORT_PATH.as_posix()
    summary: str = "Graphify report missing."
    freshness: ArchitectureEvidenceFreshness = Field(default_factory=ArchitectureEvidenceFreshness)
    metrics: GraphMetrics = Field(default_factory=GraphMetrics)
    diagnostic: DiagnosticStatus = Field(default_factory=DiagnosticStatus)
    artifacts: list[ArchitectureEvidenceArtifact] = Field(default_factory=list)
    artifact_count: int = 0
    refresh_action: ArchitectureEvidenceRefreshAction | None = None
    hotspots: list[ArchitectureEvidenceHotspot] = Field(default_factory=list)
    suggested_questions: list[ArchitectureEvidenceQuestion] = Field(default_factory=list)
    next_safe_action: str = "Run `devflow architecture audit --write-doc` when architecture cleanup is in scope."


def build_architecture_evidence(root: Path, *, head_commit: str | None = None) -> ArchitectureEvidenceProjection:
    """Project local Graphify artifacts into a bounded read-only operating-layer card."""
    root = root.resolve()
    report_path = root / GRAPHIFY_REPORT_PATH
    artifacts = _artifacts(root)
    refresh_action = _refresh_action()
    if not report_path.exists():
        return ArchitectureEvidenceProjection(
            artifacts=artifacts,
            artifact_count=len(artifacts),
            refresh_action=refresh_action,
            next_safe_action="Run `devflow architecture audit --write-doc` to create architecture evidence.",
        )

    text = report_path.read_text(encoding="utf-8", errors="replace")
    metrics = parse_graph_report_metrics(text)
    freshness = _freshness(
        report_path,
        text,
        head_commit=head_commit if head_commit is not None else _current_head_commit(root),
    )
    diagnostic = _diagnostic_from_report(text)
    status = "stale" if freshness.status == "stale" else "available"
    return ArchitectureEvidenceProjection(
        status=status,
        summary=_summary(metrics, freshness),
        freshness=freshness,
        metrics=metrics,
        diagnostic=diagnostic,
        artifacts=artifacts,
        artifact_count=len(artifacts),
        refresh_action=refresh_action,
        hotspots=_hotspots_from_report(text),
        suggested_questions=_questions_from_report(text),
        next_safe_action=_next_safe_action(freshness),
    )


def _refresh_action() -> ArchitectureEvidenceRefreshAction:
    return ArchitectureEvidenceRefreshAction(
        label="Refresh evidence",
        command=ARCHITECTURE_REFRESH_COMMAND,
        requires_human_approval=True,
        safety_class="approval_required_evidence_writing",
    )


def _artifacts(root: Path) -> list[ArchitectureEvidenceArtifact]:
    candidates: list[tuple[str, str, Path, str, str]] = [
        ("graph-report", "Graph report", Path("graphify-out/GRAPH_REPORT.md"), "report", "markdown"),
        ("graph-json", "Knowledge graph JSON", Path("graphify-out/graph.json"), "graph_json", "json"),
        ("graph-tree", "Graph tree", Path("graphify-out/GRAPH_TREE.html"), "html", "sandboxed_html"),
    ]
    callflow_paths = sorted((root / "graphify-out").glob("*-callflow.html"))
    for path in callflow_paths[:3]:
        stem_slug = _slugify(path.stem)
        candidates.append(
            (f"callflow-{stem_slug}", "Callflow HTML", path.relative_to(root), "html", "sandboxed_html")
        )
    artifacts: list[ArchitectureEvidenceArtifact] = []
    seen_ids: set[str] = set()
    for artifact_id, label, rel_path, kind, viewer in candidates:
        if artifact_id in seen_ids:
            continue
        if not (root / rel_path).exists():
            continue
        seen_ids.add(artifact_id)
        content_type = _VIEWER_CONTENT_TYPES.get(viewer, "text/plain")
        artifacts.append(
            ArchitectureEvidenceArtifact(
                artifact_id=artifact_id,
                label=label,
                path=rel_path.as_posix(),
                kind=kind,
                viewer=viewer,
                content_type=content_type,
                view_url=f"/architecture/artifact?id={artifact_id}",
            )
        )
    return artifacts[:6]


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "callflow"


class ArtifactResolutionError(Exception):
    """Raised when an artifact id cannot be safely served from graphify-out."""

    def __init__(self, message: str, *, status: int = 404) -> None:
        super().__init__(message)
        self.status = status


class ResolvedArtifact(BaseModel):
    artifact_id: str
    absolute_path: str
    content_type: str
    viewer: str


def resolve_architecture_artifact(root: Path, artifact_id: str) -> ResolvedArtifact:
    """Resolve an artifact id to a safe absolute path inside root/graphify-out.

    This rebuilds the current projection and matches by ``artifact_id`` only.
    It rejects unknown ids, unavailable artifacts, absolute paths, path
    traversal, symlink escapes, and anything outside ``root/graphify-out``.
    """
    root = root.resolve()
    if not isinstance(artifact_id, str) or not artifact_id.strip():
        raise ArtifactResolutionError("artifact id is required", status=400)

    projection = build_architecture_evidence(root)
    artifact = next(
        (item for item in projection.artifacts if item.artifact_id == artifact_id),
        None,
    )
    if artifact is None:
        raise ArtifactResolutionError(f"unknown architecture artifact id: {artifact_id}", status=404)

    rel_path = Path(artifact.path)
    if rel_path.is_absolute():
        raise ArtifactResolutionError("artifact path must be relative", status=400)

    graphify_root = (root / GRAPHIFY_OUT_DIR).resolve()
    # Resolve symlinks fully so a symlink escape cannot point outside graphify-out.
    try:
        resolved = (root / rel_path).resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ArtifactResolutionError("artifact is unavailable", status=404) from exc

    if not _is_within(resolved, graphify_root):
        raise ArtifactResolutionError("artifact path escapes graphify-out", status=400)
    if not resolved.is_file():
        raise ArtifactResolutionError("artifact is unavailable", status=404)

    return ResolvedArtifact(
        artifact_id=artifact.artifact_id,
        absolute_path=resolved.as_posix(),
        content_type=artifact.content_type,
        viewer=artifact.viewer,
    )


def _is_within(candidate: Path, parent: Path) -> bool:
    try:
        candidate.relative_to(parent)
        return True
    except ValueError:
        return False



def _freshness(report_path: Path, text: str, *, head_commit: str | None) -> ArchitectureEvidenceFreshness:
    built_commit = _built_commit(text)
    report_date = _report_date(text)
    generated_at = datetime.fromtimestamp(report_path.stat().st_mtime, tz=timezone.utc).isoformat()
    if not built_commit:
        return ArchitectureEvidenceFreshness(
            status="unknown",
            head_commit=head_commit,
            report_date=report_date,
            generated_at=generated_at,
            detail="Report does not declare the commit it was built from.",
        )
    if not head_commit:
        return ArchitectureEvidenceFreshness(
            status="unknown",
            built_commit=built_commit,
            report_date=report_date,
            generated_at=generated_at,
            detail=f"Built from {built_commit}; current HEAD could not be read.",
        )
    fresh = head_commit.startswith(built_commit) or built_commit.startswith(head_commit)
    status = "fresh" if fresh else "stale"
    detail = (
        f"Built from current HEAD {built_commit}."
        if fresh
        else f"Built from {built_commit}; current HEAD is {head_commit}."
    )
    return ArchitectureEvidenceFreshness(
        status=status,
        built_commit=built_commit,
        head_commit=head_commit,
        report_date=report_date,
        generated_at=generated_at,
        detail=detail,
    )


def _built_commit(text: str) -> str | None:
    match = re.search(r"Built from commit:\s*`?([0-9a-fA-F]{7,40})`?", text)
    return match.group(1) if match else None


def _report_date(text: str) -> str | None:
    match = re.search(r"# Graph Report[^\n]*\((\d{4}-\d{2}-\d{2})\)", text)
    return match.group(1) if match else None


def _current_head_commit(root: Path) -> str | None:
    completed = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return None
    return completed.stdout.strip() or None


def _diagnostic_from_report(text: str) -> DiagnosticStatus:
    warnings: list[str] = []
    isolated_match = re.search(r"\*\*(?P<count>[0-9,]+) isolated node\(s\):", text)
    if isolated_match:
        warnings.append(f"{isolated_match.group('count')} isolated nodes")
    thin_match = re.search(r"\*\*(?P<count>[0-9,]+) thin communities", text)
    if thin_match:
        warnings.append(f"{thin_match.group('count')} thin communities omitted")
    if not warnings:
        return DiagnosticStatus(status="report_summary", issue_count=0, raw={"source": GRAPHIFY_REPORT_PATH.as_posix()})
    return DiagnosticStatus(
        status="report_attention",
        issue_count=len(warnings),
        raw={"source": GRAPHIFY_REPORT_PATH.as_posix(), "warnings": warnings},
    )


def _hotspots_from_report(text: str, *, limit: int = 6) -> list[ArchitectureEvidenceHotspot]:
    section = _section(text, "## God Nodes", "## ")
    rows: list[ArchitectureEvidenceHotspot] = []
    for line in section.splitlines():
        match = re.match(r"\s*\d+\.\s+`([^`]+)`\s+-\s+([0-9,]+)\s+edges", line)
        if not match:
            continue
        edge_count = int(match.group(2).replace(",", ""))
        rows.append(
            ArchitectureEvidenceHotspot(
                label=_compact_text(match.group(1), 80),
                detail=f"{edge_count:,} graph edges",
                score=edge_count,
            )
        )
    return rows[:limit]


def _questions_from_report(text: str, *, limit: int = 5) -> list[ArchitectureEvidenceQuestion]:
    section = _section(text, "## Suggested Questions", "## ")
    rows: list[ArchitectureEvidenceQuestion] = []
    pending: str | None = None
    for raw_line in section.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        question_match = re.match(r"- \*\*(.+?)\*\*", line)
        if question_match:
            if pending is not None:
                rows.append(ArchitectureEvidenceQuestion(question=_compact_text(pending, 220)))
            pending = question_match.group(1)
            continue
        if pending and line.startswith("_"):
            reason = line.strip("_")
            rows.append(
                ArchitectureEvidenceQuestion(
                    question=_compact_text(pending, 220),
                    reason=_compact_text(reason, 160),
                )
            )
            pending = None
        if len(rows) >= limit:
            break
    if pending is not None and len(rows) < limit:
        rows.append(ArchitectureEvidenceQuestion(question=_compact_text(pending, 220)))
    return rows[:limit]


def _section(text: str, heading: str, next_heading_prefix: str) -> str:
    start = text.find(heading)
    if start < 0:
        return ""
    body_start = start + len(heading)
    next_heading = text.find(next_heading_prefix, body_start)
    if next_heading < 0:
        return text[body_start:]
    return text[body_start:next_heading]


def _summary(metrics: GraphMetrics, freshness: ArchitectureEvidenceFreshness) -> str:
    pieces = []
    if metrics.nodes is not None:
        pieces.append(f"{metrics.nodes:,} nodes")
    if metrics.edges is not None:
        pieces.append(f"{metrics.edges:,} edges")
    if metrics.communities is not None:
        pieces.append(f"{metrics.communities:,} communities")
    metric_summary = " · ".join(pieces) if pieces else "Graph metrics unavailable"
    return f"{metric_summary}. Freshness: {freshness.status}."


def _next_safe_action(freshness: ArchitectureEvidenceFreshness) -> str:
    if freshness.status == "stale":
        return "Refresh with `devflow architecture audit --write-doc` before architecture cleanup."
    if freshness.status == "fresh":
        return "Use `graphify-out/GRAPH_REPORT.md` as evidence, then open a focused cleanup task."
    return "Run `devflow architecture audit --write-doc` when architecture cleanup is in scope."


def _compact_text(value: Any, limit: int) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "..."
