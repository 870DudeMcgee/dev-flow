"""Pipeline run persistence — filesystem-backed and boring.

All operations stay within ``.devflow/pipeline-runs/``. No database,
no async, no caching — just Path, json, and file append.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Minimum files created for each pipeline run (filesystem contract)
# ---------------------------------------------------------------------------
MINIMUM_RUN_FILES: Dict[str, str] = {
    "intent.md": "# Intent\n",
    "source.json": "{}",
    "brainstorm.md": "",
    "classification.json": "{}",
    "intent-summary.json": "{}",
    "readiness-packet.md": "",
    "loop-packet.md": "",
    "validation.json": "{}",
    "run-log.jsonl": "",
    "artifacts.json": "{}",
    "review.md": "",
}

RUN_LOG_FILE = "run-log.jsonl"
_LAST_RUN_ID_BASE = ""
_LAST_RUN_ID_COUNTER = 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def pipeline_runs_dir(root: Path | str) -> Path:
    """Return the absolute path to ``.devflow/pipeline-runs/`` under *root*."""
    return Path(root).resolve() / ".devflow" / "pipeline-runs"


def new_pipeline_run_id() -> str:
    """Produce a sortable unique run id.

    Format: ``20260706-143022`` with ``-001`` suffixes for same-second
    collisions — timestamp slug, simple and sortable.
    Collision-safe within the same second via an incrementing counter.
    """
    global _LAST_RUN_ID_BASE, _LAST_RUN_ID_COUNTER

    now = datetime.now(timezone.utc)
    base = now.strftime("%Y%m%d-%H%M%S")
    if base == _LAST_RUN_ID_BASE:
        _LAST_RUN_ID_COUNTER += 1
        return f"{base}-{_LAST_RUN_ID_COUNTER:03d}"

    _LAST_RUN_ID_BASE = base
    _LAST_RUN_ID_COUNTER = 0
    return base


def _ensure_relative_to(path: Path, base: Path) -> None:
    """Raise when *path* does not resolve under *base*."""
    try:
        path.resolve().relative_to(base.resolve())
    except ValueError as exc:
        msg = f"Security violation: resolved path {path.resolve()} is outside {base}"
        raise ValueError(msg) from exc


def _run_dir(root: Path | str, run_id: str) -> Path:
    """Resolve and validate the run directory path."""
    runs_dir = pipeline_runs_dir(root)
    run_dir = runs_dir / run_id
    _ensure_relative_to(run_dir, runs_dir)
    return run_dir


def _validate_write_path(run_dir: Path, file_name: str) -> Path:
    """Validate that *file_name* is one direct file in the run directory."""
    requested = Path(file_name)
    if requested.is_absolute() or requested.name != file_name:
        msg = f"Security violation: record file {file_name!r} is outside run directory"
        raise ValueError(msg)

    target = (run_dir / requested).resolve()
    _ensure_relative_to(target, run_dir)
    return target


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def create_pipeline_run(root: Path | str, source: dict) -> str:
    """Create a new pipeline run directory with all minimum files.

    *source* should contain at minimum keys such as ``repo``, ``branch``,
    ``obsidian_links``, or ``handoff_metadata``.  It is serialised into
    ``source.json``.

    Returns the new *run_id*.
    """
    for _attempt in range(1000):
        run_id = new_pipeline_run_id()
        run_dir = _run_dir(root, run_id)
        try:
            run_dir.mkdir(parents=True, exist_ok=False)
            break
        except FileExistsError:
            continue
    else:
        raise FileExistsError("Could not allocate a unique pipeline run id")

    for filename, default_content in MINIMUM_RUN_FILES.items():
        file_path = run_dir / filename
        if filename == "source.json":
            file_path.write_text(
                json.dumps(source, indent=2, sort_keys=True, ensure_ascii=False)
                + "\n",
                encoding="utf-8",
            )
        else:
            file_path.write_text(default_content, encoding="utf-8")

    return run_id


def load_pipeline_run(root: Path | str, run_id: str) -> Dict[str, Any]:
    """Load all files in a pipeline run directory into a flat dict.

    Returns a dict mapping ``file_name -> content``.
    JSON files (``*.json``) are parsed; other files are returned as raw text.
    """
    run_dir = _run_dir(root, run_id)
    if not run_dir.is_dir():
        raise FileNotFoundError(f"Pipeline run not found: {run_dir}")

    result: Dict[str, Any] = {}
    for child in sorted(run_dir.iterdir()):
        if not child.is_file():
            continue
        if child.suffix == ".json":
            result[child.name] = json.loads(child.read_text(encoding="utf-8"))
        elif child.suffix == ".jsonl":
            lines = child.read_text(encoding="utf-8").strip().splitlines()
            result[child.name] = [
                json.loads(line) for line in lines if line.strip()
            ]
        else:
            result[child.name] = child.read_text(encoding="utf-8")

    return result


def update_pipeline_run_record(
    root: Path | str,
    run_id: str,
    file_name: str,
    content: str | dict | list,
) -> None:
    """Write *content* to a named file inside the run directory.

    If *content* is a ``dict`` or ``list`` it is serialised as JSON;
    otherwise it is written as-is (string).
    """
    run_dir = _run_dir(root, run_id)
    if not run_dir.is_dir():
        raise FileNotFoundError(f"Pipeline run not found: {run_dir}")

    target = _validate_write_path(run_dir, file_name)

    if isinstance(content, (dict, list)):
        text = (
            json.dumps(content, indent=2, sort_keys=True, ensure_ascii=False)
            + "\n"
        )
    else:
        text = str(content)

    target.write_text(text, encoding="utf-8")


def append_pipeline_event(
    root: Path | str,
    run_id: str,
    event: dict,
) -> None:
    """Append a single JSON line to ``run-log.jsonl``.

    *event* is enriched with a ``timestamp`` field if one is not already
    present.
    """
    run_dir = _run_dir(root, run_id)
    if not run_dir.is_dir():
        raise FileNotFoundError(f"Pipeline run not found: {run_dir}")

    target = _validate_write_path(run_dir, RUN_LOG_FILE)

    record = dict(event)
    record.setdefault("timestamp", datetime.now(timezone.utc).isoformat())

    with open(str(target), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# Compact projection model for the operating layer snapshot
# ---------------------------------------------------------------------------

class PipelineRunProjection(BaseModel):
    """Compact pipeline run metadata for the snapshot — no large artifacts."""

    run_id: str | None = None
    stage: str | None = None
    chosen_preset: str | None = None
    validation_status: str | None = None
    hermes_run_status: str | None = None
    next_safe_action: str | None = None
    artifact_paths: dict[str, str] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Supervisor Intent Summary artifact
# ---------------------------------------------------------------------------
class IntentSummary(BaseModel):
    """Structured intent summary for the pipeline run.

    Bridge between messy human intent and the builder-judge readiness packet.
    Generated by rule-based heuristics or provided directly by the operator.
    """

    schema_version: int = 1
    user_wants: str = ""
    product_outcome: str = ""
    non_negotiables: list[str] = Field(default_factory=list)
    worker_misunderstandings: list[str] = Field(default_factory=list)
    what_done_feels_like: str = ""
    source: str = "generated"  # generated | manual | imported
