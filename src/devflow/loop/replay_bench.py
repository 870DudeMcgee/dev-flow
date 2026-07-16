"""Replay benchmark suite (M7-S1, blueprint §12.5/§13).

Replays all canonical pipeline runs, verifies that the replayed snapshot
matches the stored snapshot byte/semantically, and records route-quality
history. Read-only — never mutates canonical state.

This is the frozen-corpus replay proof: any ledger/schema change must keep
existing runs replaying identically.
"""

from __future__ import annotations

import itertools
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from devflow.loop.pipeline_run import pipeline_runs_dir
from devflow.loop.workflow_ledger import (
    WORKFLOW_SNAPSHOT_FILE,
    WorkflowSnapshot,
    replay_workflow_run,
)

_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"
_bench_counter = itertools.count(1)


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

class RunReplayResult(BaseModel):
    """Result of replaying one run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str = Field(min_length=1)
    replay_succeeded: bool
    snapshot_matches: bool
    duration_seconds: float = 0.0
    error_message: str = ""


class ReplayBenchmarkResult(BaseModel):
    """Aggregate result of replaying all runs."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    total_runs: int = Field(ge=0)
    successful_replays: int = Field(ge=0)
    failed_replays: int = Field(ge=0)
    mismatched_snapshots: int = Field(ge=0)
    results: tuple[RunReplayResult, ...] = ()
    benchmark_id: str = Field(min_length=1)
    benchmarked_at: str = Field(min_length=1)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _bench_id() -> str:
    return f"bench-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{next(_bench_counter):04d}"


# ---------------------------------------------------------------------------
# Run discovery
# ---------------------------------------------------------------------------

def discover_canonical_runs(
    root: Path | str,
) -> tuple[str, ...]:
    """Find all run IDs that have workflow snapshots.

    Only runs with a ``workflow-snapshot.json`` are canonical — those without
    it are noncanonical/historical and not replayable.
    """
    runs_dir = pipeline_runs_dir(root)
    if not runs_dir.is_dir():
        return ()

    run_ids: list[str] = []
    for child in sorted(runs_dir.iterdir()):
        if not child.is_dir():
            continue
        snapshot_path = child / WORKFLOW_SNAPSHOT_FILE
        if snapshot_path.is_file():
            run_ids.append(child.name)

    return tuple(run_ids)


# ---------------------------------------------------------------------------
# Benchmark
# ---------------------------------------------------------------------------

def _replay_one(
    root: Path,
    run_id: str,
) -> RunReplayResult:
    """Replay a single run and compare against stored snapshot."""
    start = time.monotonic()

    try:
        replayed = replay_workflow_run(root, run_id)
    except Exception as exc:
        duration = time.monotonic() - start
        return RunReplayResult(
            run_id=run_id,
            replay_succeeded=False,
            snapshot_matches=False,
            duration_seconds=round(duration, 6),
            error_message=str(exc),
        )

    duration = time.monotonic() - start

    # Compare against stored snapshot
    run_dir = pipeline_runs_dir(root) / run_id
    snapshot_path = run_dir / WORKFLOW_SNAPSHOT_FILE
    matches = False

    if snapshot_path.is_file():
        try:
            stored_data = json.loads(snapshot_path.read_text(encoding="utf-8"))
            stored = WorkflowSnapshot.model_validate(stored_data)
            matches = replayed == stored
        except Exception:
            matches = False
    else:
        # No stored snapshot to compare — replay succeeded but can't verify
        matches = False

    return RunReplayResult(
        run_id=run_id,
        replay_succeeded=True,
        snapshot_matches=matches,
        duration_seconds=round(duration, 6),
    )


def run_replay_benchmark(
    root: Path | str,
) -> ReplayBenchmarkResult:
    """Replay all canonical pipeline runs and verify snapshot identity.

    Returns an aggregate :class:`ReplayBenchmarkResult`. Never mutates
    canonical state.
    """
    root_path = Path(root).resolve()
    run_ids = discover_canonical_runs(root_path)

    results: list[RunReplayResult] = []
    successful = 0
    failed = 0
    mismatched = 0

    for run_id in run_ids:
        result = _replay_one(root_path, run_id)
        results.append(result)
        if result.replay_succeeded:
            successful += 1
            if not result.snapshot_matches:
                mismatched += 1
        else:
            failed += 1

    return ReplayBenchmarkResult(
        total_runs=len(run_ids),
        successful_replays=successful,
        failed_replays=failed,
        mismatched_snapshots=mismatched,
        results=tuple(results),
        benchmark_id=_bench_id(),
        benchmarked_at=_now_iso(),
    )


__all__ = [
    "ReplayBenchmarkResult",
    "RunReplayResult",
    "discover_canonical_runs",
    "run_replay_benchmark",
]
