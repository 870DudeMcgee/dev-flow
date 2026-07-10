"""Native V2 pipeline run persistence — no legacy dependency.

Filesystem-backed, deterministic, and intentionally boring: just Path, json,
and file append. The public API mirrors the original
the previous pipeline-run contract exactly so the V2 loop
adapters can switch to native execution with a one-line import swap.

Contract (must stay byte-compatible with adapter.infer_stage):
  - Runs live under ``.devflow/pipeline-runs/<run_id>/``.
  - create_pipeline_run writes MINIMUM_RUN_FILES (same names as legacy).
  - load_pipeline_run returns file_name -> content (JSON parsed for *.json).
  - update_pipeline_run_record writes a named record (dict/list -> JSON).
  - append_pipeline_event appends a JSON line to run-log.jsonl.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

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
WORKER_FEED_FILE = "worker-feed.jsonl"
WORKER_LIVE_FILE = "worker-live.json"
EXECUTION_CONTROL_FILE = "execution-control.json"
_LAST_RUN_ID_BASE = ""
_LAST_RUN_ID_COUNTER = 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def pipeline_runs_dir(root: Path | str) -> Path:
    """Return the absolute path to `.devflow/pipeline-runs/` under *root*."""
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
    ``obsidian_links``, or ``handoff_metadata``. It is serialised into
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


def append_worker_feed_entry(
    root: Path | str,
    run_id: str,
    entry: dict,
) -> None:
    """Append a JSON line to ``worker-feed.jsonl``.

    Worker feed entries capture actual model outputs — the content, role,
    model, prompt, and status — so the status board can show what each worker
    is actually thinking and producing, not just that it's "active".
    """
    run_dir = _run_dir(root, run_id)
    if not run_dir.is_dir():
        raise FileNotFoundError(f"Pipeline run not found: {run_dir}")

    target = _validate_write_path(run_dir, WORKER_FEED_FILE)

    record = dict(entry)
    record.setdefault("timestamp", datetime.now(timezone.utc).isoformat())

    with open(str(target), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def write_worker_live_output(
    root: Path | str,
    run_id: str,
    payload: dict,
) -> None:
    """Atomically publish the bounded in-flight output for one active role."""
    run_dir = _run_dir(root, run_id)
    if not run_dir.is_dir():
        raise FileNotFoundError(f"Pipeline run not found: {run_dir}")
    target = _validate_write_path(run_dir, WORKER_LIVE_FILE)
    temp = _validate_write_path(run_dir, f"{WORKER_LIVE_FILE}.tmp")
    record = dict(payload)
    record.setdefault("updated_at", datetime.now(timezone.utc).isoformat())
    content = str(record.get("content") or "")
    record["content"] = content[-64000:]
    temp.write_text(
        json.dumps(record, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temp.replace(target)


def clear_worker_live_output(root: Path | str, run_id: str) -> None:
    """Remove the transient live snapshot after its final feed receipt exists."""
    run_dir = _run_dir(root, run_id)
    target = _validate_write_path(run_dir, WORKER_LIVE_FILE)
    target.unlink(missing_ok=True)


def read_execution_control(root: Path | str, run_id: str) -> dict:
    """Return persisted execution ownership/cancellation state for a run."""
    run_dir = _run_dir(root, run_id)
    target = _validate_write_path(run_dir, EXECUTION_CONTROL_FILE)
    if not target.is_file():
        return {}
    try:
        value = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def update_execution_control(
    root: Path | str,
    run_id: str,
    **changes: Any,
) -> dict:
    """Merge and atomically persist execution ownership and operator intent."""
    current = read_execution_control(root, run_id)
    current.update(changes)
    current["updated_at"] = datetime.now(timezone.utc).isoformat()
    update_pipeline_run_record(root, run_id, EXECUTION_CONTROL_FILE, current)
    return current


def cancellation_requested(root: Path | str, run_id: str) -> bool:
    control = read_execution_control(root, run_id)
    return str(control.get("status") or "") in {"cancelling", "cancelled"}
