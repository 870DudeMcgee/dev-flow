from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import yaml

from devflow.legacy.control_room.dogfood_case_catalog import CATEGORY_LABELS
from devflow.legacy.control_room.paths import dogfood_runs_dir, relative_path
from devflow.legacy.control_room.persistence import utc_now


def new_dogfood_run_id(root: Path) -> str:
    stamp = utc_now().strftime("%Y%m%dT%H%M%SZ")
    base = f"dogfood-{stamp}"
    runs = dogfood_runs_dir(root)
    candidate = base
    suffix = 2
    while (runs / candidate).exists():
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


def load_dogfood_run(root: Path, run_id: str) -> dict[str, Any]:
    resolved = _resolve_run_id(root, run_id)
    run_dir = dogfood_runs_dir(root) / resolved
    run_path = run_dir / "run.yaml"
    scorecard_path = run_dir / "scorecard.yaml"
    report_path = run_dir / "report.md"
    if not run_path.exists() or not scorecard_path.exists():
        raise KeyError(f"Dogfood run not found: {run_id}")
    return {
        "run_id": resolved,
        "run_dir": run_dir,
        "run": yaml.safe_load(run_path.read_text(encoding="utf-8")) or {},
        "scorecard": yaml.safe_load(scorecard_path.read_text(encoding="utf-8")) or {},
        "report": report_path.read_text(encoding="utf-8") if report_path.exists() else "",
    }


def render_dogfood_score(scorecard: dict[str, Any]) -> str:
    threshold = scorecard["threshold_result"]
    lines = [
        f"run_id: {scorecard['run_id']}",
        f"total_score: {scorecard['total_score']}/{scorecard['max_score']}",
        f"threshold: {threshold['achieved']}",
        f"silver_met: {'yes' if threshold['silver_met'] else 'no'}",
        "category_scores:",
    ]
    for category, item in scorecard["category_scores"].items():
        lines.append(
            f"  - {CATEGORY_LABELS.get(category, category)}: {item['score']}/{item['max']} ({item['percent']}%)"
        )
    if scorecard["failures"]:
        lines.append("failures:")
        lines.extend(f"  - {failure}" for failure in scorecard["failures"])
    if scorecard["warnings"]:
        lines.append("warnings:")
        lines.extend(f"  - {warning}" for warning in scorecard["warnings"])
    return "\n".join(lines) + "\n"


def prune_old_dogfood_runs(root: Path, *, keep_runs: int) -> list[str]:
    runs = dogfood_runs_dir(root)
    if not runs.exists():
        return []
    candidates = sorted(path for path in runs.iterdir() if path.is_dir())
    stale = candidates[:-keep_runs]
    pruned: list[str] = []
    for path in stale:
        shutil.rmtree(path)
        pruned.append(relative_path(root, path))
    return pruned


def _resolve_run_id(root: Path, run_id: str) -> str:
    if run_id != "latest":
        return run_id
    runs = dogfood_runs_dir(root)
    if not runs.exists():
        raise KeyError("No dogfood runs found.")
    candidates = sorted(path.name for path in runs.iterdir() if path.is_dir())
    if not candidates:
        raise KeyError("No dogfood runs found.")
    return candidates[-1]
