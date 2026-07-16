"""Per-run metrics aggregator (M5-S3).

Reads reliability reports, repair events, lifecycle events, and review events
to produce an aggregated :class:`WorkflowMetrics` summary. Read-only — never
mutates canonical state. Consumed by the promotion packet generator.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from devflow.loop.pipeline_run import pipeline_runs_dir

RELIABILITY_FILE = "reliability-report.json"
REPAIR_EVENTS_FILE = "repair-events.jsonl"
LIFECYCLE_EVENTS_FILE = "node-lifecycle-events.jsonl"
REVIEW_EVENTS_FILE = "review-events.jsonl"
WORKFLOW_DEFINITION_FILE = "workflow-definition.json"


class WorkflowMetrics(BaseModel):
    """Aggregated per-run workflow metrics."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str = Field(min_length=1)
    total_duration_seconds: float = 0.0
    total_tokens: int = 0
    role_routes: tuple[str, ...] = ()
    retry_count: int = 0
    repair_rounds: int = 0
    human_interventions: int = 0
    reliability_safe: bool | None = None
    reliability_breaches: tuple[str, ...] = ()
    workflow_version: str = ""


def _run_dir(root: Path | str, run_id: str) -> Path:
    return pipeline_runs_dir(root) / run_id


def _read_json(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _count_jsonl(path: Path) -> int:
    if not path.is_file():
        return 0
    count = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            count += 1
    return count


def _extract_retries(path: Path) -> int:
    """Count lifecycle transitions where to_state = 'retrying'."""
    if not path.is_file():
        return 0
    count = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            data = json.loads(line)
        except Exception:
            continue
        if data.get("to_state") == "retrying":
            count += 1
    return count


def aggregate_metrics(
    root: Path | str,
    run_id: str,
) -> WorkflowMetrics:
    """Aggregate per-run metrics from all available sources.

    Reads:
    - ``reliability-report.json`` for safety/breaches/duration/tokens
    - ``repair-events.jsonl`` for repair round count
    - ``node-lifecycle-events.jsonl`` for retry count
    - ``review-events.jsonl`` for human intervention count
    - ``workflow-definition.json`` for workflow version

    Never mutates canonical state. Missing files produce zeros.
    """
    root_path = Path(root).resolve()
    run_dir = _run_dir(root_path, run_id)

    # Reliability
    reliability = _read_json(run_dir / RELIABILITY_FILE) or {}
    safe = reliability.get("safe")
    breaches = reliability.get("breaches", [])
    if not isinstance(breaches, list):
        breaches = []
    metrics = reliability.get("metrics", {})
    if not isinstance(metrics, dict):
        metrics = {}

    duration = metrics.get("total_duration_seconds", 0.0)
    try:
        duration = float(duration)
    except (TypeError, ValueError):
        duration = 0.0

    tokens = metrics.get("total_tokens", 0)
    try:
        tokens = int(tokens)
    except (TypeError, ValueError):
        tokens = 0

    # Repair rounds
    repair_rounds = _count_jsonl(run_dir / REPAIR_EVENTS_FILE)

    # Lifecycle retries
    retry_count = _extract_retries(run_dir / LIFECYCLE_EVENTS_FILE)

    # Review events (human interventions = review count)
    human_interventions = _count_jsonl(run_dir / REVIEW_EVENTS_FILE)

    # Workflow version
    wf_def = _read_json(run_dir / WORKFLOW_DEFINITION_FILE) or {}
    workflow_version = wf_def.get("workflow_id", "")

    # Capability routes from reliability metrics if present
    routes: list[str] = []
    raw_routes = metrics.get("capability_routes", [])
    if isinstance(raw_routes, list):
        routes = [str(r) for r in raw_routes]

    return WorkflowMetrics(
        run_id=run_id,
        total_duration_seconds=duration,
        total_tokens=tokens,
        role_routes=tuple(routes),
        retry_count=retry_count,
        repair_rounds=repair_rounds,
        human_interventions=human_interventions,
        reliability_safe=safe if isinstance(safe, bool) else None,
        reliability_breaches=tuple(str(b) for b in breaches),
        workflow_version=workflow_version,
    )


def format_metrics_section(metrics: WorkflowMetrics) -> str:
    """Format metrics as a human-readable Markdown section."""
    lines: list[str] = ["## Workflow Metrics"]
    lines.append("")

    duration_min = metrics.total_duration_seconds / 60.0
    lines.append(f"- Total duration: {duration_min:.1f} minutes")
    lines.append(f"- Total tokens: {metrics.total_tokens:,}")
    lines.append(f"- Retries: {metrics.retry_count}")
    lines.append(f"- Repair rounds: {metrics.repair_rounds}")
    lines.append(f"- Human interventions: {metrics.human_interventions}")

    if metrics.reliability_safe is True:
        lines.append("- Reliability: **safe**")
    elif metrics.reliability_safe is False:
        lines.append("- Reliability: **unsafe**")
    else:
        lines.append("- Reliability: _not available_")

    if metrics.role_routes:
        lines.append(f"- Capability routes: {', '.join(metrics.role_routes)}")

    if metrics.workflow_version:
        lines.append(f"- Workflow: `{metrics.workflow_version}`")

    return "\n".join(lines)


__all__ = [
    "WorkflowMetrics",
    "aggregate_metrics",
    "format_metrics_section",
]
