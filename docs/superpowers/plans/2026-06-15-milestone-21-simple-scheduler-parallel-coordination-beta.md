# Milestone 21 Simple Scheduler / Parallel Coordination Beta Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a read-only scheduler status projection plus explicit retry-request evidence so Dev-Flow can show ready, blocked, stale, retry, worker, and verification queues across multiple tasks without adding autonomous scheduling.

**Architecture:** Create a focused `scheduler_projection.py` module under `src/devflow/control_room/` that composes existing task, lock, question, freshness, goal-loop, worker-lane, local-worker-lane, and review-readiness evidence. Add a minimal CLI bridge for `devflow scheduler status` and `devflow scheduler retry`, then surface the projection through supervisor, operating-layer, dogfood, and active docs. Do not create a new executor; scheduler next actions point to existing `freshness` and `task` commands.

**Tech Stack:** Python 3, Typer CLI, Pydantic models, YAML/JSON filesystem artifacts, existing Dev-Flow task/freshness/operating-layer modules, pytest.

---

## File Structure

- Create `src/devflow/control_room/scheduler_projection.py`: derived scheduler snapshot, stale detection, retry request writer, text renderer.
- Modify `src/devflow/cli.py`: minimal `scheduler` Typer bridge only.
- Modify `src/devflow/control_room/supervisor_surface.py`: include compact scheduler status and evidence paths.
- Modify `src/devflow/control_room/operating_layer.py`: add scheduler models and include scheduler snapshot.
- Modify `src/devflow/control_room/operating_layer_script.py`: render scheduler queue/batch/retry block.
- Modify `src/devflow/control_room/operating_layer_styles.py`: add scheduler block styles.
- Modify `src/devflow/control_room/dogfood.py`: add `simple-scheduler-parallel-coordination` case and score totals.
- Create `tests/test_scheduler_projection.py`: scheduler projection and retry evidence unit tests.
- Modify `tests/test_supervisor_operating_surface.py`: supervisor scheduler packet assertions.
- Modify `tests/test_operating_layer.py`: operating-layer scheduler snapshot/assets assertions.
- Modify `tests/test_dogfood_harness.py`: dogfood case count, totals, and focused scheduler case test.
- Modify `docs/control-room-mvp.md` and `docs/agent-handoff.md`: active priority and next milestone status after implementation.
- Add implementation handoff under `docs/handoffs/` at completion.

## Guardrails

- Keep implementation logic under `src/devflow/control_room/`.
- `src/devflow/cli.py` may only wire commands to control-room functions.
- No remote provider execution.
- No autonomous routing.
- No background daemons.
- No automatic task creation, worker execution, verification, promotion, commit, push, or PR.
- No database.
- Scheduler status must be read-only.
- Scheduler retry may write only `.devflow/tasks/<task_id>/retry-request.json` plus a task event.

---

### Task 1: Add Scheduler Projection Tests First

**Files:**
- Create: `tests/test_scheduler_projection.py`
- Read as needed: `tests/test_freshness_loop.py`, `tests/test_parallel_worker.py`, `tests/test_parallel_verification.py`, `tests/test_manual_proof_agent.py`

- [ ] **Step 1: Create projection test helpers**

Add this file with helper setup:

```python
from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import yaml
from typer.testing import CliRunner

from devflow.cli import app
from devflow.control_room.persistence import get_task, save_task, utc_now
from devflow.control_room.scheduler_projection import (
    build_scheduler_snapshot,
    request_scheduler_retry,
)
from tests.helpers import setup_temp_git_repo


runner = CliRunner()


def _init_goal(tmp_path: Path, monkeypatch) -> None:
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    brief = tmp_path / "goal.md"
    brief.write_text("## Goal Brief\nCoordinate parallel work.\n", encoding="utf-8")
    result = runner.invoke(app, ["goal", "init", "--from", str(brief)])
    assert result.exit_code == 0, result.output


def _write_slices(root: Path, text: str) -> None:
    path = root / ".devflow" / "goals" / "G-0001" / "task-slices.yaml"
    path.write_text(text.lstrip(), encoding="utf-8")


def _task(root: Path, task_id: str):
    return get_task(root, task_id)
```

- [ ] **Step 2: Add ready/batch/blocker projection test**

Append:

```python
def test_scheduler_snapshot_projects_ready_batches_and_dependency_blockers(tmp_path: Path, monkeypatch) -> None:
    _init_goal(tmp_path, monkeypatch)
    _write_slices(
        tmp_path,
        """
        task_slices:
          - task_id: TS-0001
            title: First ready lane
            parallel_safe: true
            shared_files: [src/a.py]
            risk: low
            execution_mode: AFK
          - task_id: TS-0002
            title: Second ready lane
            parallel_safe: true
            shared_files: [src/b.py]
            risk: low
            execution_mode: AFK
          - task_id: TS-0003
            title: Blocked lane
            blocked_by: [TS-0001]
            parallel_safe: true
            shared_files: [src/c.py]
            risk: medium
            execution_mode: HITL
        """,
    )

    snapshot = build_scheduler_snapshot(tmp_path)
    payload = snapshot.model_dump(mode="json")

    assert payload["counts"]["ready"] == 2
    assert payload["counts"]["blocked"] == 1
    assert payload["status"] == "ready"
    assert payload["batches"][0]["batch_type"] == "task_creation"
    assert payload["batches"][0]["batch_id"] == "PB-0001"
    assert payload["batches"][0]["lane_ids"] == ["TS-0001", "TS-0002"]
    assert payload["blocked_dependencies"][0]["lane_id"] == "TS-0003"
    assert payload["blocked_dependencies"][0]["blocked_by"] == ["TS-0001"]
    assert payload["next_safe_action"] == "devflow freshness create-batch G-0001 PB-0001"
```

- [ ] **Step 3: Add stale running task test**

Append:

```python
def test_scheduler_snapshot_marks_running_task_stale_from_passive_timestamp(tmp_path: Path, monkeypatch) -> None:
    _init_goal(tmp_path, monkeypatch)
    create = runner.invoke(app, ["task", "create", "stale runner"])
    assert create.exit_code == 0, create.output

    task = _task(tmp_path, "task-0001")
    now = utc_now()
    task.status = "running"
    task.started_at = now - timedelta(seconds=900)
    task.updated_at = task.started_at
    task.timeout_seconds = 60
    save_task(tmp_path / ".devflow" / "tasks" / task.id, task)

    snapshot = build_scheduler_snapshot(tmp_path)
    stale = [item for item in snapshot.tasks if item.task_id == "task-0001"][0]

    assert stale.scheduler_state == "stale"
    assert stale.stale is True
    assert stale.next_safe_action == "devflow task show task-0001"
    assert snapshot.counts["stale"] == 1
    assert "task-0001" in snapshot.stale_tasks
```

- [ ] **Step 4: Add retry evidence test**

Append:

```python
def test_scheduler_retry_writes_request_without_clearing_evidence(tmp_path: Path, monkeypatch) -> None:
    _init_goal(tmp_path, monkeypatch)
    create = runner.invoke(app, ["task", "create", "needs retry"])
    assert create.exit_code == 0, create.output

    task = _task(tmp_path, "task-0001")
    task.status = "verification_failed"
    task.verification_status = "failed"
    task.verification_command = "pytest tests/test_retry.py"
    save_task(tmp_path / ".devflow" / "tasks" / task.id, task)

    request = request_scheduler_retry(tmp_path, "task-0001", reason="rerun focused test after repair")

    path = tmp_path / request.retry_request_path
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["task_id"] == "task-0001"
    assert payload["reason"] == "rerun focused test after repair"
    assert payload["previous_status"] == "verification_failed"
    assert payload["previous_verification_status"] == "failed"
    assert payload["recommended_next_command"] == "devflow task next-action task-0001"

    unchanged = _task(tmp_path, "task-0001")
    assert unchanged.status == "verification_failed"
    assert unchanged.verification_status == "failed"
    assert unchanged.verification_command == "pytest tests/test_retry.py"
    events = (tmp_path / ".devflow/tasks/task-0001/events.jsonl").read_text(encoding="utf-8")
    assert "retry_requested" in events
```

- [ ] **Step 5: Add CLI status/retry smoke test**

Append:

```python
def test_scheduler_cli_status_and_retry_json(tmp_path: Path, monkeypatch) -> None:
    _init_goal(tmp_path, monkeypatch)
    create = runner.invoke(app, ["task", "create", "cli retry"])
    assert create.exit_code == 0, create.output
    task = _task(tmp_path, "task-0001")
    task.status = "worker_failed"
    save_task(tmp_path / ".devflow" / "tasks" / task.id, task)

    status = runner.invoke(app, ["scheduler", "status", "--json"])
    assert status.exit_code == 0, status.output
    status_payload = json.loads(status.output)
    assert status_payload["counts"]["needs_retry"] == 1

    retry = runner.invoke(app, ["scheduler", "retry", "task-0001", "--reason", "worker failed", "--json"])
    assert retry.exit_code == 0, retry.output
    retry_payload = json.loads(retry.output)
    assert retry_payload["task_id"] == "task-0001"
    assert retry_payload["retry_request_path"] == ".devflow/tasks/task-0001/retry-request.json"
```

- [ ] **Step 6: Run the new tests and confirm failure**

Run:

```bash
PYTHONPATH=src:. /Users/josh/Desktop/Dev-Flow/.venv/bin/python -m pytest tests/test_scheduler_projection.py -q
```

Expected: failures for missing `devflow.control_room.scheduler_projection` and missing `scheduler` CLI command.

---

### Task 2: Implement `scheduler_projection.py`

**Files:**
- Create: `src/devflow/control_room/scheduler_projection.py`
- Modify only if imports require: none
- Test: `tests/test_scheduler_projection.py`

- [ ] **Step 1: Create model and imports**

Create `src/devflow/control_room/scheduler_projection.py`:

```python
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from devflow.control_room.freshness import FreshnessReport, run_freshness_loop
from devflow.control_room.paths import relative_path, task_dir
from devflow.control_room.persistence import atomic_write_text, get_task, list_tasks, utc_now
from devflow.control_room.task_lifecycle import append_task_event


SchedulerTaskState = Literal[
    "ready",
    "running",
    "stale",
    "blocked",
    "needs_retry",
    "needs_review",
    "ready_to_verify",
    "ready_to_promote",
    "closed",
]


class SchedulerTask(BaseModel):
    task_id: str
    title: str
    status: str
    verification_status: str
    scheduler_state: SchedulerTaskState
    stale: bool = False
    stale_reason: str | None = None
    blockers: list[str] = Field(default_factory=list)
    evidence_paths: list[str] = Field(default_factory=list)
    next_safe_action: str


class SchedulerBatch(BaseModel):
    batch_type: Literal["task_creation", "worker", "verification"]
    goal_id: str
    batch_id: str
    lane_ids: list[str] = Field(default_factory=list)
    task_ids: list[str] = Field(default_factory=list)
    commands: list[str] = Field(default_factory=list)
    shared_files: list[str] = Field(default_factory=list)
    next_safe_action: str


class SchedulerDependencyBlocker(BaseModel):
    goal_id: str
    lane_id: str
    blocked_by: list[str] = Field(default_factory=list)
    title: str
    next_safe_action: str


class SchedulerRetryRequest(BaseModel):
    schema_version: int = 1
    task_id: str
    requested_at: str
    reason: str
    previous_status: str
    previous_verification_status: str
    recommended_next_command: str
    retry_request_path: str


class SchedulerSnapshot(BaseModel):
    schema_version: int = 1
    generated_at: str
    status: Literal["ready", "blocked", "stale", "idle"]
    counts: dict[str, int]
    max_parallel_recommendation: int
    tasks: list[SchedulerTask] = Field(default_factory=list)
    batches: list[SchedulerBatch] = Field(default_factory=list)
    blocked_dependencies: list[SchedulerDependencyBlocker] = Field(default_factory=list)
    stale_tasks: list[str] = Field(default_factory=list)
    retry_candidates: list[str] = Field(default_factory=list)
    next_safe_action: str
    evidence_paths: list[str] = Field(default_factory=list)
```

- [ ] **Step 2: Implement snapshot builder**

Append:

```python
STATE_ORDER: list[SchedulerTaskState] = [
    "stale",
    "blocked",
    "needs_retry",
    "running",
    "ready_to_promote",
    "ready_to_verify",
    "needs_review",
    "ready",
    "closed",
]


def build_scheduler_snapshot(root: Path) -> SchedulerSnapshot:
    root = root.resolve()
    freshness = _try_freshness(root)
    tasks = [_scheduler_task(root, task) for task in list_tasks(root)]
    batches = _scheduler_batches(root, freshness)
    blocked_dependencies = _blocked_dependencies(freshness)
    evidence_paths = _dedupe(
        [
            ".devflow/freshness/latest.json",
            *[path for task in tasks for path in task.evidence_paths],
        ]
    )
    counts = {state: 0 for state in STATE_ORDER}
    for task in tasks:
        counts[task.scheduler_state] = counts.get(task.scheduler_state, 0) + 1
    for _item in blocked_dependencies:
        counts["blocked"] = counts.get("blocked", 0) + 1
    for batch in batches:
        if batch.batch_type in {"task_creation", "worker", "verification"}:
            counts["ready"] = counts.get("ready", 0) + len(batch.lane_ids)

    stale_tasks = [task.task_id for task in tasks if task.scheduler_state == "stale"]
    retry_candidates = [task.task_id for task in tasks if task.scheduler_state == "needs_retry"]
    status = _snapshot_status(counts)
    next_safe_action = _next_safe_action(batches, tasks, blocked_dependencies)
    return SchedulerSnapshot(
        generated_at=datetime.now(timezone.utc).isoformat(),
        status=status,
        counts=counts,
        max_parallel_recommendation=_max_parallel_recommendation(batches),
        tasks=sorted(tasks, key=lambda item: (STATE_ORDER.index(item.scheduler_state), item.task_id)),
        batches=batches,
        blocked_dependencies=blocked_dependencies,
        stale_tasks=stale_tasks,
        retry_candidates=retry_candidates,
        next_safe_action=next_safe_action,
        evidence_paths=evidence_paths,
    )


def _try_freshness(root: Path) -> FreshnessReport | None:
    try:
        return run_freshness_loop(root, write_snapshot=True)
    except Exception:
        return None
```

- [ ] **Step 3: Implement task classification**

Append:

```python
def _scheduler_task(root: Path, task) -> SchedulerTask:
    task_path = task_dir(root, task.id)
    stale, stale_reason = _is_stale(task, task_path)
    blockers = _task_blockers(task_path)
    retry_request = task_path / "retry-request.json"
    evidence_paths = [
        relative_path(root, task_path / "task.yaml"),
        relative_path(root, task_path / "events.jsonl"),
    ]
    if retry_request.exists():
        evidence_paths.append(relative_path(root, retry_request))
    state: SchedulerTaskState
    if stale:
        state = "stale"
    elif blockers:
        state = "blocked"
    elif retry_request.exists() or task.status in {"worker_failed", "timeout", "failed", "verification_failed"}:
        state = "needs_retry"
    elif task.status == "running":
        state = "running"
    elif task.status == "verified" or task.verification_status == "passed":
        state = "ready_to_promote"
    elif task.status == "complete" and task.verification_status != "passed":
        state = "ready_to_verify"
    elif task.status in {"closed", "promoted"}:
        state = "closed"
    else:
        state = "ready"
    return SchedulerTask(
        task_id=task.id,
        title=task.title,
        status=task.status,
        verification_status=task.verification_status,
        scheduler_state=state,
        stale=stale,
        stale_reason=stale_reason,
        blockers=blockers,
        evidence_paths=evidence_paths,
        next_safe_action=_task_next_action(task.id, state),
    )


def _is_stale(task, task_path: Path) -> tuple[bool, str | None]:
    if task.status != "running":
        return False, None
    started = task.started_at or task.updated_at
    age = (utc_now() - started).total_seconds()
    threshold = max(int(task.timeout_seconds or 120), 300)
    if age > threshold:
        return True, f"running for {int(age)}s, threshold {threshold}s"
    owner = task_path / ".lock" / "owner.json"
    if owner.exists():
        try:
            owner.read_text(encoding="utf-8")
        except OSError as exc:
            return True, f"lock owner unreadable: {exc}"
    return False, None


def _task_blockers(task_path: Path) -> list[str]:
    blockers: list[str] = []
    for questions_path in sorted((task_path / "agents").glob("*/questions.jsonl")) if (task_path / "agents").is_dir() else []:
        for line in questions_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except ValueError:
                blockers.append(f"invalid questions evidence: {questions_path}")
                continue
            if payload.get("type") == "blocked_question":
                blockers.append(str(payload.get("question") or payload.get("summary") or "blocked question"))
    return blockers


def _task_next_action(task_id: str, state: SchedulerTaskState) -> str:
    if state == "needs_retry":
        return f'devflow scheduler retry {task_id} --reason "<reason>"'
    if state == "ready_to_promote":
        return f"devflow task promote-preview {task_id}"
    if state == "ready_to_verify":
        return f'devflow task verify {task_id} --shell "<command>"'
    return f"devflow task show {task_id}"
```

- [ ] **Step 4: Implement batch and blocker normalization**

Append:

```python
def _scheduler_batches(root: Path, freshness: FreshnessReport | None) -> list[SchedulerBatch]:
    if not freshness:
        return []
    batches: list[SchedulerBatch] = []
    for goal in freshness.goal_loop:
        for batch in goal.parallel_batches:
            batches.append(
                SchedulerBatch(
                    batch_type="task_creation",
                    goal_id=goal.goal_id,
                    batch_id=batch.batch_id,
                    lane_ids=batch.lane_ids,
                    commands=batch.commands,
                    shared_files=batch.shared_files,
                    next_safe_action=f"devflow freshness create-batch {goal.goal_id} {batch.batch_id}",
                )
            )
        for batch in goal.worker_batches:
            batches.append(
                SchedulerBatch(
                    batch_type="worker",
                    goal_id=goal.goal_id,
                    batch_id=batch.batch_id,
                    lane_ids=batch.lane_ids,
                    task_ids=batch.task_ids,
                    commands=batch.commands,
                    shared_files=batch.shared_files,
                    next_safe_action=f"devflow freshness worker-batch {goal.goal_id} {batch.batch_id}",
                )
            )
        for batch in goal.verification_batches:
            batches.append(
                SchedulerBatch(
                    batch_type="verification",
                    goal_id=goal.goal_id,
                    batch_id=batch.batch_id,
                    lane_ids=batch.lane_ids,
                    task_ids=batch.task_ids,
                    commands=batch.commands,
                    shared_files=batch.shared_files,
                    next_safe_action=f"devflow freshness verify-batch {goal.goal_id} {batch.batch_id}",
                )
            )
    return batches


def _blocked_dependencies(freshness: FreshnessReport | None) -> list[SchedulerDependencyBlocker]:
    if not freshness:
        return []
    blockers: list[SchedulerDependencyBlocker] = []
    for goal in freshness.goal_loop:
        for lane in goal.lanes:
            if lane.blockers:
                blockers.append(
                    SchedulerDependencyBlocker(
                        goal_id=goal.goal_id,
                        lane_id=lane.slice_id,
                        blocked_by=lane.blockers,
                        title=lane.title,
                        next_safe_action=f"devflow goal status {goal.goal_id}",
                    )
                )
    return blockers
```

- [ ] **Step 5: Implement retry request and renderer**

Append:

```python
def request_scheduler_retry(root: Path, task_id: str, *, reason: str) -> SchedulerRetryRequest:
    if not reason.strip():
        raise ValueError("Retry reason is required.")
    task = get_task(root, task_id)
    task_path = task_dir(root, task_id)
    requested_at = datetime.now(timezone.utc).isoformat()
    path = task_path / "retry-request.json"
    request = SchedulerRetryRequest(
        task_id=task_id,
        requested_at=requested_at,
        reason=reason.strip(),
        previous_status=task.status,
        previous_verification_status=task.verification_status,
        recommended_next_command=f"devflow task next-action {task_id}",
        retry_request_path=relative_path(root, path),
    )
    atomic_write_text(path, request.model_dump_json(indent=2) + "\n")
    append_task_event(root, task_id, "retry_requested", {"reason": request.reason})
    return request


def render_scheduler_snapshot(snapshot: SchedulerSnapshot) -> str:
    lines = [
        f"scheduler_status: {snapshot.status}",
        f"next_safe_action: {snapshot.next_safe_action}",
        f"max_parallel_recommendation: {snapshot.max_parallel_recommendation}",
        "counts:",
    ]
    for key in STATE_ORDER:
        lines.append(f"  {key}: {snapshot.counts.get(key, 0)}")
    if snapshot.batches:
        lines.append("batches:")
        for batch in snapshot.batches[:8]:
            lines.append(f"  - {batch.batch_type} {batch.batch_id}: {batch.next_safe_action}")
    if snapshot.tasks:
        lines.append("tasks:")
        for task in snapshot.tasks[:12]:
            lines.append(f"  - {task.task_id}: {task.scheduler_state} -> {task.next_safe_action}")
    return "\n".join(lines) + "\n"


def _snapshot_status(counts: dict[str, int]) -> Literal["ready", "blocked", "stale", "idle"]:
    if counts.get("stale", 0):
        return "stale"
    if counts.get("ready", 0):
        return "ready"
    if counts.get("blocked", 0) or counts.get("needs_retry", 0):
        return "blocked"
    return "idle"


def _next_safe_action(
    batches: list[SchedulerBatch],
    tasks: list[SchedulerTask],
    blocked_dependencies: list[SchedulerDependencyBlocker],
) -> str:
    if batches:
        return batches[0].next_safe_action
    for state in ("stale", "needs_retry", "blocked", "ready_to_promote", "ready_to_verify"):
        for task in tasks:
            if task.scheduler_state == state:
                return task.next_safe_action
    if blocked_dependencies:
        return blocked_dependencies[0].next_safe_action
    return "devflow task list"


def _max_parallel_recommendation(batches: list[SchedulerBatch]) -> int:
    if not batches:
        return 4
    return max(1, min(4, max(len(batch.task_ids or batch.lane_ids) for batch in batches)))


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result
```

- [ ] **Step 6: Run projection tests**

Run:

```bash
PYTHONPATH=src:. /Users/josh/Desktop/Dev-Flow/.venv/bin/python -m pytest tests/test_scheduler_projection.py -q
```

Expected after Task 2: CLI smoke still fails until Task 3, projection-only tests pass.

---

### Task 3: Add Minimal CLI Bridge

**Files:**
- Modify: `src/devflow/cli.py`
- Test: `tests/test_scheduler_projection.py`

- [ ] **Step 1: Add scheduler Typer app**

Near existing app declarations, add:

```python
scheduler_app = typer.Typer(help="Inspect simple scheduler queue and retry evidence")
```

Near existing `app.add_typer(...)` calls, add:

```python
app.add_typer(scheduler_app, name="scheduler")
```

- [ ] **Step 2: Add status command**

Add near the `freshness` commands:

```python
@scheduler_app.command("status")
def scheduler_status(
    json_output: bool = typer.Option(False, "--json", help="Print scheduler status as JSON."),
) -> None:
    """Show the derived simple scheduler projection."""
    from devflow.control_room.scheduler_projection import build_scheduler_snapshot, render_scheduler_snapshot

    snapshot = build_scheduler_snapshot(Path.cwd())
    if json_output:
        typer.echo(json.dumps(snapshot.model_dump(mode="json"), indent=2, sort_keys=True))
    else:
        typer.echo(render_scheduler_snapshot(snapshot), nl=False)
```

- [ ] **Step 3: Add retry command**

Add:

```python
@scheduler_app.command("retry")
def scheduler_retry(
    task_id: str = typer.Argument(..., help="Task ID to mark for manual retry."),
    reason: str = typer.Option(..., "--reason", help="Human-readable retry reason."),
    json_output: bool = typer.Option(False, "--json", help="Print retry request as JSON."),
) -> None:
    """Write explicit retry-request evidence without rerunning work."""
    from devflow.control_room.scheduler_projection import request_scheduler_retry

    try:
        request = request_scheduler_retry(Path.cwd(), task_id, reason=reason)
    except ValueError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1)
    if json_output:
        typer.echo(json.dumps(request.model_dump(mode="json"), indent=2, sort_keys=True))
    else:
        typer.echo(f"retry_request: {request.retry_request_path}")
        typer.echo(f"next_safe_action: {request.recommended_next_command}")
```

- [ ] **Step 4: Run CLI tests**

Run:

```bash
PYTHONPATH=src:. /Users/josh/Desktop/Dev-Flow/.venv/bin/python -m pytest tests/test_scheduler_projection.py -q
```

Expected: all scheduler projection tests pass.

---

### Task 4: Surface Scheduler In Supervisor And Operating Layer

**Files:**
- Modify: `src/devflow/control_room/supervisor_surface.py`
- Modify: `src/devflow/control_room/operating_layer.py`
- Modify: `src/devflow/control_room/operating_layer_script.py`
- Modify: `src/devflow/control_room/operating_layer_styles.py`
- Modify: `tests/test_supervisor_operating_surface.py`
- Modify: `tests/test_operating_layer.py`

- [ ] **Step 1: Add supervisor packet test**

In `tests/test_supervisor_operating_surface.py`, add a test after the local worker lane supervisor test:

```python
def test_scheduler_summary_reaches_supervisor_packet(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    create_task(tmp_path, "scheduler retry")
    task = get_task(tmp_path, "task-0001")
    task.status = "worker_failed"
    save_task(tmp_path / ".devflow" / "tasks" / task.id, task)

    packet = _read_json(_invoke_read_only(tmp_path, ["supervisor", "packet", "--json"]))

    assert packet["scheduler"]["counts"]["needs_retry"] == 1
    assert packet["scheduler"]["next_safe_action"] == 'devflow scheduler retry task-0001 --reason "<reason>"'
    assert ".devflow/tasks/task-0001/task.yaml" in packet["evidence_paths"]
```

Also import `get_task` and `save_task` if not already present.

- [ ] **Step 2: Implement supervisor compact scheduler**

In `src/devflow/control_room/supervisor_surface.py`, import:

```python
from devflow.control_room.scheduler_projection import build_scheduler_snapshot
```

In the supervisor packet builder, add:

```python
scheduler = build_scheduler_snapshot(root)
packet["scheduler"] = {
    "status": scheduler.status,
    "counts": scheduler.counts,
    "next_safe_action": scheduler.next_safe_action,
    "max_parallel_recommendation": scheduler.max_parallel_recommendation,
}
packet["evidence_paths"] = _dedupe_preserve_order(packet.get("evidence_paths", []) + scheduler.evidence_paths)
```

Use the exact local variable names from the existing packet function. Do not add scheduler data to forbidden supervisor command classification.

- [ ] **Step 3: Add operating-layer snapshot test**

In `tests/test_operating_layer.py`, add:

```python
def test_operating_layer_snapshot_includes_scheduler_summary(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    created = runner.invoke(app, ["task", "create", "scheduler retry"])
    assert created.exit_code == 0, created.output
    task = get_task(tmp_path, "task-0001")
    task.status = "worker_failed"
    save_task(tmp_path / ".devflow" / "tasks" / task.id, task)

    payload = build_operating_layer_snapshot(tmp_path).model_dump(mode="json")

    assert payload["scheduler"]["counts"]["needs_retry"] == 1
    assert payload["scheduler"]["next_safe_action"] == 'devflow scheduler retry task-0001 --reason "<reason>"'
```

Also extend the asset facade test:

```python
assert ".scheduler-block" in APP_CSS
assert "renderSchedulerBlock" in APP_JS
```

- [ ] **Step 4: Implement operating-layer models**

In `src/devflow/control_room/operating_layer.py`, add:

```python
class OperatingLayerScheduler(BaseModel):
    status: str
    counts: dict[str, int] = Field(default_factory=dict)
    max_parallel_recommendation: int
    next_safe_action: str
    stale_tasks: list[str] = Field(default_factory=list)
    retry_candidates: list[str] = Field(default_factory=list)
    batch_count: int = 0
```

Add to `OperatingLayerSnapshot`:

```python
scheduler: OperatingLayerScheduler | None = None
```

In `build_operating_layer_snapshot`, compute:

```python
from devflow.control_room.scheduler_projection import build_scheduler_snapshot

scheduler = build_scheduler_snapshot(root)
```

Pass:

```python
scheduler=_scheduler_card(scheduler),
```

Add helper:

```python
def _scheduler_card(snapshot) -> OperatingLayerScheduler:
    return OperatingLayerScheduler(
        status=snapshot.status,
        counts=snapshot.counts,
        max_parallel_recommendation=snapshot.max_parallel_recommendation,
        next_safe_action=snapshot.next_safe_action,
        stale_tasks=snapshot.stale_tasks,
        retry_candidates=snapshot.retry_candidates,
        batch_count=len(snapshot.batches),
    )
```

- [ ] **Step 5: Render scheduler block**

In `src/devflow/control_room/operating_layer_script.py`, add:

```javascript
function renderSchedulerBlock() {
  const scheduler = snapshot.scheduler;
  if (!scheduler) return "";
  const counts = scheduler.counts || {};
  const rows = [
    ["Ready", counts.ready || 0],
    ["Blocked", counts.blocked || 0],
    ["Stale", counts.stale || 0],
    ["Retry", counts.needs_retry || 0],
    ["Batches", scheduler.batch_count || 0],
  ];
  return `
    <section class="scheduler-block" aria-label="Scheduler">
      <div class="panel-heading">
        <span>Scheduler</span>
        <strong>${escapeHtml(scheduler.status)}</strong>
      </div>
      <div class="scheduler-grid">
        ${rows.map(([label, value]) => `<div><span>${label}</span><strong>${value}</strong></div>`).join("")}
      </div>
      <div class="next-action">${escapeHtml(scheduler.next_safe_action || "devflow task list")}</div>
    </section>
  `;
}
```

Call it in the main render path near freshness/goal board content:

```javascript
html += renderSchedulerBlock();
```

Use the existing local render composition style; do not create nested cards.

- [ ] **Step 6: Add scheduler styles**

In `src/devflow/control_room/operating_layer_styles.py`, add:

```css
.scheduler-block {
  border-top: 1px solid var(--border);
  padding: 12px 0;
}

.scheduler-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(92px, 1fr));
  gap: 8px;
}

.scheduler-grid div {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 8px;
}
```

- [ ] **Step 7: Run surface tests**

Run:

```bash
PYTHONPATH=src:. /Users/josh/Desktop/Dev-Flow/.venv/bin/python -m pytest tests/test_scheduler_projection.py tests/test_supervisor_operating_surface.py tests/test_operating_layer.py -q
```

Expected: all selected tests pass.

---

### Task 5: Add Production-Readiness Dogfood Case

**Files:**
- Modify: `src/devflow/control_room/dogfood.py`
- Modify: `tests/test_dogfood_harness.py`

- [ ] **Step 1: Update dogfood schema tests**

In `tests/test_dogfood_harness.py`, update the case count from `13` to `14`, add `"simple-scheduler-parallel-coordination"` to the expected ID set, and add:

```python
def test_simple_scheduler_dogfood_case_exercises_parallel_coordination(tmp_path: Path) -> None:
    _init_dogfood_repo(tmp_path)

    result = run_dogfood_suite(tmp_path, case_ids=["simple-scheduler-parallel-coordination"])
    case_result = result["results"][0]

    assert case_result["status"] == "passed"
    assert case_result["score"] == case_result["max_score"]
    assert any("scheduler exposed ready blocked stale and retry work" in lesson for lesson in case_result["lessons"])
    assert any("retry request preserved prior task evidence" in lesson for lesson in case_result["lessons"])
    assert any("no background scheduler or provider calls were introduced" in lesson for lesson in case_result["lessons"])
```

- [ ] **Step 2: Update dogfood category totals**

In `src/devflow/control_room/dogfood.py`, add 10 points total to `CATEGORY_MAX`:

```python
"B_pipeline_correctness": 24,
"D_worker_artifact_quality": 21,
"E_recovery_failure_handling": 23,
```

Keep other categories unchanged.

- [ ] **Step 3: Add case definition**

In `production_readiness_cases()`, add:

```python
_case_definition(
    case_id="simple-scheduler-parallel-coordination",
    title="Simple scheduler parallel coordination",
    category="B_pipeline_correctness",
    task_type="scheduler_projection",
    risk_level="medium",
    purpose="Prove scheduler status coordinates ready, blocked, stale, retry, and batch evidence without autonomous execution.",
    expected_behavior=[
        "project ready parallel batches from goal slice evidence",
        "surface dependency-blocked and question-blocked work",
        "mark stale running tasks without cleaning locks or rerunning work",
        "write explicit retry-request evidence without clearing old logs",
        "avoid provider calls, background scheduling, auto-verification, auto-promotion, commits, pushes, databases, and hidden memory",
    ],
    command_sequence=[
        "write deterministic goal slices and task evidence",
        "devflow scheduler status --json",
        "devflow scheduler retry <task-id> --reason '<reason>' --json",
    ],
    success_criteria=[
        "scheduler exposes ready, blocked, stale, and retry counts",
        "next action points to an explicit existing Dev-Flow command",
        "retry evidence preserves prior task state",
    ],
    scoring={
        "B_pipeline_correctness": 2,
        "D_worker_artifact_quality": 3,
        "E_recovery_failure_handling": 5,
    },
),
```

- [ ] **Step 4: Implement dogfood runner**

Import scheduler helpers:

```python
from datetime import timedelta
from devflow.control_room.scheduler_projection import build_scheduler_snapshot, request_scheduler_retry
```

Extend the persistence import:

```python
from devflow.control_room.persistence import atomic_write_text, get_task, list_tasks, save_task, utc_now
```

Add runner:

```python
def _case_simple_scheduler_parallel_coordination(
    root: Path, run_id: str, case: dict[str, Any], case_dir: Path, shared: dict[str, Any]
) -> dict[str, Any]:
    state = _new_case_state(root, run_id, case, case_dir)
    scratch = case_dir / "artifacts" / "simple-scheduler-repo"
    _init_git_native_dogfood_repo(scratch)
    init_control_room(scratch)
    state["artifacts_created"].append(relative_path(root, scratch))
    _record_command(state, "git init scratch simple-scheduler dogfood repo", status="passed", output=relative_path(root, scratch))

    goal_dir = scratch / ".devflow" / "goals" / "G-0001"
    goal_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_text(goal_dir / "goal.yaml", "id: G-0001\ntitle: Scheduler dogfood\nstate: active\n")
    atomic_write_text(
        goal_dir / "goal-state.yaml",
        "schema_version: 1\ngoal_id: G-0001\nlifecycle: active\nreason: dogfood scheduler case\n",
    )
    atomic_write_text(
        goal_dir / "task-slices.yaml",
        """
task_slices:
  - task_id: TS-0001
    title: Ready scheduler lane one
    summary: Can start independently.
    parallel_safe: true
    shared_files: [src/a.py]
    risk: low
    execution_mode: AFK
  - task_id: TS-0002
    title: Ready scheduler lane two
    summary: Can start independently beside TS-0001.
    parallel_safe: true
    shared_files: [src/b.py]
    risk: low
    execution_mode: AFK
  - task_id: TS-0003
    title: Dependency blocked scheduler lane
    summary: Waits for TS-0001.
    blocked_by: [TS-0001]
    parallel_safe: true
    shared_files: [src/c.py]
    risk: medium
    execution_mode: HITL
""".lstrip(),
    )
    atomic_write_text(goal_dir / "linked-tasks.yaml", "linked_tasks: {}\n")

    retry_task = create_task(scratch, "Dogfood scheduler retry task")
    retry_record = get_task(scratch, retry_task.id)
    retry_record.status = "verification_failed"
    retry_record.verification_status = "failed"
    retry_record.verification_command = "pytest tests/test_retry.py"
    retry_record.updated_at = utc_now()
    save_task(scratch / ".devflow" / "tasks" / retry_record.id, retry_record)

    stale_task = create_task(scratch, "Dogfood scheduler stale running task")
    stale_record = get_task(scratch, stale_task.id)
    stale_record.status = "running"
    stale_record.started_at = utc_now() - timedelta(seconds=900)
    stale_record.updated_at = stale_record.started_at
    stale_record.timeout_seconds = 60
    save_task(scratch / ".devflow" / "tasks" / stale_record.id, stale_record)

    blocked_task = create_task(scratch, "Dogfood scheduler blocked question task")
    agent_dir = scratch / ".devflow" / "tasks" / blocked_task.id / "agents" / "devflow-manual-codex-worker"
    agent_dir.mkdir(parents=True, exist_ok=True)
    with (agent_dir / "questions.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "type": "blocked_question",
                    "task_id": blocked_task.id,
                    "agent_id": "devflow-manual-codex-worker",
                    "question": "Which retry path should this dogfood task use?",
                },
                sort_keys=True,
            )
            + "\n"
        )

    snapshot_before = build_scheduler_snapshot(scratch)
    retry = request_scheduler_retry(scratch, retry_task.id, reason="dogfood retry evidence")
    snapshot_after = build_scheduler_snapshot(scratch)
    summary = {
        "before": snapshot_before.model_dump(mode="json"),
        "retry": retry.model_dump(mode="json"),
        "after": snapshot_after.model_dump(mode="json"),
    }
    summary_path = case_dir / "artifacts" / "simple-scheduler-summary.json"
    atomic_write_text(summary_path, json.dumps(summary, indent=2, sort_keys=True) + "\n")
    state["artifacts_created"].append(relative_path(root, summary_path))
    _record_command(state, "devflow scheduler status --json (fixture)", status="passed", output=relative_path(root, summary_path))
    _record_command(state, "devflow scheduler retry <task-id> --reason 'dogfood retry evidence' --json", status="passed")

    scores: dict[str, int] = {}
    failures: list[str] = []
    counts = snapshot_after.counts
    _award(
        state,
        scores,
        failures,
        "B_pipeline_correctness",
        2,
        counts.get("ready", 0) >= 2,
        "scheduler exposed ready parallel work",
    )
    _award(
        state,
        scores,
        failures,
        "D_worker_artifact_quality",
        3,
        counts.get("blocked", 0) >= 1 and counts.get("stale", 0) >= 1,
        "scheduler exposed blocked and stale work",
    )
    _award(
        state,
        scores,
        failures,
        "E_recovery_failure_handling",
        5,
        counts.get("needs_retry", 0) >= 1 and (scratch / retry.retry_request_path).exists(),
        "retry request preserved prior task evidence",
    )
    state["lessons"].extend(
        [
            "scheduler exposed ready blocked stale and retry work",
            "retry request preserved prior task evidence",
            "no background scheduler or provider calls were introduced",
        ]
    )
    return _finalize_case(root, case, state, scores, failures)
```

- [ ] **Step 5: Register runner**

Add to `_RUNNERS`:

```python
"simple-scheduler-parallel-coordination": _case_simple_scheduler_parallel_coordination,
```

- [ ] **Step 6: Run dogfood tests**

Run:

```bash
PYTHONPATH=src:. /Users/josh/Desktop/Dev-Flow/.venv/bin/python -m pytest tests/test_dogfood_harness.py -q
```

Expected: all dogfood harness tests pass.

---

### Task 6: Update Active Docs And Handoff

**Files:**
- Modify: `docs/control-room-mvp.md`
- Modify: `docs/agent-handoff.md`
- Add: `docs/handoffs/2026-06-15-milestone-21-simple-scheduler-parallel-coordination-beta-implementation.md`

- [ ] **Step 1: Update current priority after implementation**

In `docs/control-room-mvp.md`, replace the current priority paragraph with wording that says:

```markdown
Milestone 21 Simple Scheduler / Parallel Coordination Beta is implemented in the active branch: Dev-Flow now projects ready, blocked, stale, retry, worker-batch, and verification-batch scheduler state from existing filesystem evidence while keeping dispatch explicit through current `freshness` and `task` commands.
```

Keep the explicit exclusions for provider execution, autonomous routing, auto-promotion, auto-commit, auto-push, PRs, databases, and worker-owned verification.

- [ ] **Step 2: Update agent handoff**

In `docs/agent-handoff.md`, update the latest milestone section so it says:

```markdown
Milestone 20 Registry-Backed Local Worker Runtime Hardening is promoted and pushed on `main`.

Milestone 21 Simple Scheduler / Parallel Coordination Beta is implemented in the active branch. It adds a derived scheduler projection and explicit retry-request evidence over existing task, freshness, goal, question, lock, worker, and verification state without adding a background scheduler or autonomous execution. Artifacts:
```

List the Milestone 21 spec, plan, planning handoff, and implementation handoff.

- [ ] **Step 3: Add implementation handoff**

Create `docs/handoffs/2026-06-15-milestone-21-simple-scheduler-parallel-coordination-beta-implementation.md` using this structure:

```markdown
## Status

needs-review

## Files Changed

- `src/devflow/control_room/scheduler_projection.py` (derived scheduler projection and retry evidence writer)
- `src/devflow/cli.py` (minimal scheduler command bridge)
- `src/devflow/control_room/supervisor_surface.py` (scheduler summary/evidence in supervisor packet)
- `src/devflow/control_room/operating_layer.py`, `operating_layer_script.py`, `operating_layer_styles.py` (scheduler snapshot/UI block)
- `src/devflow/control_room/dogfood.py` (production-readiness scheduler case)
- `tests/test_scheduler_projection.py`, `tests/test_supervisor_operating_surface.py`, `tests/test_operating_layer.py`, `tests/test_dogfood_harness.py` (focused coverage)
- `docs/control-room-mvp.md`, `docs/agent-handoff.md` (active milestone status)

## Verification

- `PYTHONPATH=src:. /Users/josh/Desktop/Dev-Flow/.venv/bin/python -m pytest tests/test_scheduler_projection.py tests/test_freshness_loop.py tests/test_parallel_worker.py tests/test_parallel_verification.py tests/test_supervisor_operating_surface.py tests/test_operating_layer.py tests/test_dogfood_harness.py -q`: record the actual pass/fail line from the implementation run
- `PYTHONPATH=src:. /Users/josh/Desktop/Dev-Flow/.venv/bin/devflow dogfood run --suite production-readiness`: record the actual score, threshold, and warning lines from the implementation run
- `PATH=/Users/josh/Desktop/Dev-Flow/.venv/bin:$PATH ./scripts/release-check.sh`: record the actual full-suite, packaging, and smoke-install result from the implementation run

## Risks

- State concrete residual risks found during implementation, or write `None identified` if verification and review find none.

## Next Safe Action

- `PYTHONPATH=src:. .venv/bin/devflow task promote-preview "$TASK_ID"`
```

- [ ] **Step 4: Run stale-context scan**

Run:

```bash
rg -n "Milestone 20.*active branch|task-0038.*until reviewed|background scheduler|autonomous scheduler|provider-backed execution is active|auto-promotion" docs README.md AGENTS.md -S
```

Expected: no stale active guidance except intentional historical references or the scan command itself.

---

### Task 7: Verification, Commit, And Promotion Preparation

**Files:**
- No new files beyond previous tasks

- [ ] **Step 1: Run focused milestone suite**

Run:

```bash
PYTHONPATH=src:. /Users/josh/Desktop/Dev-Flow/.venv/bin/python -m pytest tests/test_scheduler_projection.py tests/test_freshness_loop.py tests/test_parallel_worker.py tests/test_parallel_verification.py tests/test_supervisor_operating_surface.py tests/test_operating_layer.py tests/test_dogfood_harness.py -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Run production-readiness dogfood**

Run:

```bash
PYTHONPATH=src:. /Users/josh/Desktop/Dev-Flow/.venv/bin/devflow dogfood run --suite production-readiness
```

Expected: Silver-or-better score and no scheduler autonomy/provider-call warnings.

- [ ] **Step 3: Run full release check**

Run:

```bash
PATH=/Users/josh/Desktop/Dev-Flow/.venv/bin:$PATH ./scripts/release-check.sh
```

Expected: compileall, full pytest, CLI smoke, package build, twine check, and fresh wheel smoke pass.

- [ ] **Step 4: Check whitespace and git status**

Run:

```bash
git diff --check
PYTHONPATH=src:. /Users/josh/Desktop/Dev-Flow/.venv/bin/devflow git status
```

Expected: `git diff --check` has no output; Dev-Flow git status is clean after finalization.

- [ ] **Step 5: Finalize task branch**

Run from the main checkout:

```bash
TASK_ID=task-0041
PYTHONPATH=src:. .venv/bin/devflow task finalize "$TASK_ID" --commit
```

Expected: commit lands on the task worker branch and main remains unchanged.

- [ ] **Step 6: Preview promotion**

Run from the main checkout:

```bash
TASK_ID=task-0041
PYTHONPATH=src:. .venv/bin/devflow task promote-preview "$TASK_ID"
```

Expected: `promotion_readiness: ready`, `conflict_prediction: clean`, and next action `devflow task promote "$TASK_ID"` after substituting the active implementation task ID.

---

## Implementation Notes For The Next Agent

- Start from a fresh task/worktree based on pushed `main`.
- Keep scheduler projection read-only except for `scheduler retry`.
- Prefer using existing freshness batch models rather than duplicating conflict detection.
- If exact implementation names differ, preserve the public contract:
  - `devflow scheduler status --json`
  - `devflow scheduler retry <task_id> --reason "<reason>" --json`
  - supervisor `scheduler` packet field
  - operating-layer `scheduler` snapshot field
  - production-readiness dogfood case
- If the scheduler projection becomes too large, split helper-only internals into `src/devflow/control_room/scheduler_state.py`; keep public CLI imports from `scheduler_projection.py`.
