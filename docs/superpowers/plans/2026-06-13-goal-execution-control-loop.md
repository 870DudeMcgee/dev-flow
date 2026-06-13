# Goal Execution Control Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement Milestone 14 so goals have explicit lifecycle state and the existing freshness loop can drive a bounded idea-to-goal-to-task execution lane without automatic routing, promotion, or publication.

**Architecture:** Add a small canonical goal lifecycle service, wire it into goal projection and freshness-loop decisions, then expose lifecycle state through CLI, supervisor policy, and operating-layer snapshots. Reuse the existing goal task-slice, freshness batch, worker-batch, verification-batch, task verification, and promotion-readiness machinery instead of adding a new scheduler.

**Tech Stack:** Python 3.14, Typer CLI, Pydantic models, PyYAML, pytest, existing Dev-Flow filesystem artifacts under `.devflow/`.

---

## File Structure

- Create `src/devflow/control_room/goal_lifecycle.py`
  - Own canonical `goal-state.yaml` parsing/writing.
  - Own goal lifecycle event append/read helpers.
  - Provide lifecycle rendering and command-result models.
- Modify `src/devflow/control_room/goals.py`
  - Initialize `goal-state.yaml` for new goals created by `goal init` and `idea create-goal`.
- Modify `src/devflow/control_room/goal_projection.py`
  - Add lifecycle fields to `GoalStatusProjection`.
  - Make `goal status` and `goal next` lifecycle-aware.
- Modify `src/devflow/control_room/goal_loop.py`
  - Suppress dispatch batches for non-active goals.
  - Emit explicit closure-decision next action when all slices have promoted task evidence.
- Modify `src/devflow/control_room/freshness.py`
  - Add lifecycle findings and include lifecycle in freshness state hash.
- Modify `src/devflow/control_room/operating_layer.py`
  - Include lifecycle state/reason in goal board/spec board display payloads.
- Modify `src/devflow/control_room/supervisor_surface.py`
  - Classify goal lifecycle mutations as approval-required state changes.
- Modify `src/devflow/cli.py`
  - Wire `goal activate`, `pause`, `block`, `complete`, and `archive`.
- Add `tests/test_goal_lifecycle.py`
  - Lifecycle service and CLI tests.
- Modify `tests/test_goal_projection.py`
  - Lifecycle-aware status/next tests.
- Modify `tests/test_freshness_loop.py`
  - Lifecycle gate and closure-decision tests.
- Modify `tests/test_operating_layer.py`
  - Snapshot exposes lifecycle state.
- Modify `tests/test_supervisor_operating_surface.py`
  - Supervisor classification tests.
- Modify active docs after behavior is implemented:
  - `docs/roadmap.md`
  - `docs/control-room-mvp.md`
  - `docs/mvp-contract.md`
  - `docs/architecture/goal-control-loop.md`
  - final handoff under `docs/handoffs/`

## Guardrails

- Keep all runtime code inside `src/devflow/control_room/` except CLI wiring in `src/devflow/cli.py`.
- Do not add provider adapters, routing, memory, PR automation, background daemons, databases, or browser-side batch execution.
- Do not mark a goal complete automatically. The loop recommends `devflow goal complete ...`; the human runs it.
- Use Dev-Flow task/worktree commands for implementation and promotion. Do not raw-push or raw-merge to `main`.
- Run `devflow git status` before creating implementation work and before promotion/push decisions.

## Task 1: Add Canonical Goal Lifecycle Service

**Files:**
- Create: `src/devflow/control_room/goal_lifecycle.py`
- Test: `tests/test_goal_lifecycle.py`

- [ ] **Step 1: Write lifecycle service tests**

Create `tests/test_goal_lifecycle.py` with these tests:

```python
from __future__ import annotations

import json
from pathlib import Path

import yaml

from devflow.control_room.goal_lifecycle import (
    GoalLifecycleError,
    ensure_goal_lifecycle,
    read_goal_lifecycle,
    set_goal_lifecycle,
)
from devflow.control_room.goals import create_goal_from_markdown


def _goal(root: Path) -> str:
    brief = root / "brief.md"
    brief.write_text("# Build a bounded goal loop\n", encoding="utf-8")
    return create_goal_from_markdown(root, brief).id


def test_new_goal_lifecycle_can_be_created_and_read(tmp_path: Path) -> None:
    goal_id = _goal(tmp_path)

    state = ensure_goal_lifecycle(tmp_path, goal_id)

    assert state.goal_id == goal_id
    assert state.lifecycle == "active"
    path = tmp_path / ".devflow" / "goals" / goal_id / "goal-state.yaml"
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["lifecycle"] == "active"


def test_lifecycle_transitions_append_hash_chained_events(tmp_path: Path) -> None:
    goal_id = _goal(tmp_path)
    ensure_goal_lifecycle(tmp_path, goal_id)

    paused = set_goal_lifecycle(
        tmp_path,
        goal_id,
        lifecycle="paused",
        reason="waiting for review",
        command="devflow goal pause G-0001 --reason 'waiting for review'",
    )

    assert paused.lifecycle == "paused"
    assert paused.status_reason == "waiting for review"
    events_path = tmp_path / ".devflow" / "goals" / goal_id / "events.jsonl"
    events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines()]
    assert [event["event_index"] for event in events] == [0, 1]
    assert events[0]["event"] == "goal_lifecycle_created"
    assert events[1]["event"] == "goal_lifecycle_changed"
    assert events[1]["previous_event_hash"] == events[0]["event_hash"]


def test_lifecycle_refuses_unknown_goal_and_invalid_state(tmp_path: Path) -> None:
    try:
        ensure_goal_lifecycle(tmp_path, "G-9999")
    except GoalLifecycleError as exc:
        assert "Goal not found" in str(exc)
    else:
        raise AssertionError("expected missing goal to fail")

    goal_id = _goal(tmp_path)
    try:
        set_goal_lifecycle(tmp_path, goal_id, lifecycle="running", reason="bad", command="bad")
    except GoalLifecycleError as exc:
        assert "Unsupported goal lifecycle" in str(exc)
    else:
        raise AssertionError("expected invalid lifecycle to fail")


def test_missing_lifecycle_reads_as_missing_without_mutating(tmp_path: Path) -> None:
    goal_id = _goal(tmp_path)
    lifecycle_path = tmp_path / ".devflow" / "goals" / goal_id / "goal-state.yaml"
    lifecycle_path.unlink()

    state = read_goal_lifecycle(tmp_path, goal_id)

    assert state is None
    assert not lifecycle_path.exists()
```

- [ ] **Step 2: Run tests to verify the new module is missing**

Run:

```bash
PYTHONPATH=src:. <repo-root>/.venv/bin/python -m pytest tests/test_goal_lifecycle.py -v
```

Expected: fail with `ModuleNotFoundError: No module named 'devflow.control_room.goal_lifecycle'`.

- [ ] **Step 3: Implement `goal_lifecycle.py`**

Create `src/devflow/control_room/goal_lifecycle.py`:

```python
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel

from devflow.control_room.paths import goal_dir
from devflow.control_room.persistence import atomic_write_text, event_content_hash


GoalLifecycleValue = Literal["active", "paused", "blocked", "complete", "archived"]
ALLOWED_GOAL_LIFECYCLES = {"active", "paused", "blocked", "complete", "archived"}


class GoalLifecycleError(RuntimeError):
    pass


class GoalLifecycleState(BaseModel):
    schema_version: int = 1
    goal_id: str
    lifecycle: GoalLifecycleValue
    status_reason: str = ""
    created_at: str
    updated_at: str
    last_decision: str
    last_decision_command: str


class GoalLifecycleResult(BaseModel):
    goal_id: str
    lifecycle: GoalLifecycleValue
    status_reason: str
    goal_path: str
    state_path: str
    next_command: str


def read_goal_lifecycle(root: Path, goal_id: str) -> GoalLifecycleState | None:
    _require_goal(root, goal_id)
    path = _state_path(root, goal_id)
    if not path.exists():
        return None
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise GoalLifecycleError(f"goal-state.yaml is malformed for {goal_id}.")
    return GoalLifecycleState.model_validate(data)


def ensure_goal_lifecycle(root: Path, goal_id: str) -> GoalLifecycleState:
    existing = read_goal_lifecycle(root, goal_id)
    if existing is not None:
        return existing
    now = _now()
    state = GoalLifecycleState(
        goal_id=goal_id,
        lifecycle="active",
        status_reason="",
        created_at=now,
        updated_at=now,
        last_decision="activated",
        last_decision_command=f"devflow goal activate {goal_id}",
    )
    _write_state(root, state)
    _append_event(root, goal_id, "goal_lifecycle_created", state)
    return state


def set_goal_lifecycle(
    root: Path,
    goal_id: str,
    *,
    lifecycle: str,
    reason: str,
    command: str,
) -> GoalLifecycleState:
    _require_goal(root, goal_id)
    if lifecycle not in ALLOWED_GOAL_LIFECYCLES:
        raise GoalLifecycleError(f"Unsupported goal lifecycle: {lifecycle}")
    previous = read_goal_lifecycle(root, goal_id)
    now = _now()
    state = GoalLifecycleState(
        goal_id=goal_id,
        lifecycle=lifecycle,  # type: ignore[arg-type]
        status_reason=reason.strip(),
        created_at=previous.created_at if previous else now,
        updated_at=now,
        last_decision=_decision_for(lifecycle),
        last_decision_command=command,
    )
    _write_state(root, state)
    _append_event(root, goal_id, "goal_lifecycle_changed", state)
    return state


def lifecycle_result(root: Path, state: GoalLifecycleState) -> GoalLifecycleResult:
    return GoalLifecycleResult(
        goal_id=state.goal_id,
        lifecycle=state.lifecycle,
        status_reason=state.status_reason,
        goal_path=f".devflow/goals/{state.goal_id}",
        state_path=f".devflow/goals/{state.goal_id}/goal-state.yaml",
        next_command=_next_command(state),
    )


def render_lifecycle_result(result: GoalLifecycleResult) -> str:
    lines = [
        f"goal_id: {result.goal_id}",
        f"lifecycle: {result.lifecycle}",
        f"reason: {result.status_reason}",
        f"goal_path: {result.goal_path}",
        f"state_path: {result.state_path}",
        f"next: {result.next_command}",
    ]
    return "\n".join(lines) + "\n"


def _require_goal(root: Path, goal_id: str) -> None:
    if not (goal_dir(root, goal_id) / "goal.yaml").exists():
        raise GoalLifecycleError(f"Goal not found: {goal_id}")


def _state_path(root: Path, goal_id: str) -> Path:
    return goal_dir(root, goal_id) / "goal-state.yaml"


def _events_path(root: Path, goal_id: str) -> Path:
    return goal_dir(root, goal_id) / "events.jsonl"


def _write_state(root: Path, state: GoalLifecycleState) -> None:
    atomic_write_text(_state_path(root, state.goal_id), yaml.safe_dump(state.model_dump(), sort_keys=False))


def _append_event(root: Path, goal_id: str, event_name: str, state: GoalLifecycleState) -> None:
    path = _events_path(root, goal_id)
    previous_hash, next_index = _event_tail(path)
    event = {
        "timestamp": state.updated_at,
        "event": event_name,
        "event_index": next_index,
        "previous_event_hash": previous_hash,
        "goal_id": goal_id,
        "lifecycle": state.lifecycle,
        "status_reason": state.status_reason,
        "decision": state.last_decision,
        "command": state.last_decision_command,
    }
    event["event_hash"] = event_content_hash(event)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True) + "\n")


def _event_tail(path: Path) -> tuple[str | None, int]:
    if not path.exists():
        return None, 0
    previous_hash: str | None = None
    next_index = 0
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        if not raw_line.strip():
            continue
        try:
            event = json.loads(raw_line)
        except json.JSONDecodeError:
            break
        if not isinstance(event, dict):
            break
        previous_hash = event.get("event_hash") or event_content_hash(event)
        next_index += 1
    return previous_hash, next_index


def _decision_for(lifecycle: str) -> str:
    return {
        "active": "activated",
        "paused": "paused",
        "blocked": "blocked",
        "complete": "completed",
        "archived": "archived",
    }[lifecycle]


def _next_command(state: GoalLifecycleState) -> str:
    if state.lifecycle == "active":
        return f"devflow freshness loop"
    return f"devflow goal status {state.goal_id}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
```

- [ ] **Step 4: Run lifecycle tests**

Run:

```bash
PYTHONPATH=src:. <repo-root>/.venv/bin/python -m pytest tests/test_goal_lifecycle.py -v
```

Expected: all lifecycle service tests pass.

## Task 2: Initialize Lifecycle State And Wire CLI Commands

**Files:**
- Modify: `src/devflow/control_room/goals.py`
- Modify: `src/devflow/cli.py`
- Test: `tests/test_goal_lifecycle.py`

- [ ] **Step 1: Add CLI tests for lifecycle commands**

Append to `tests/test_goal_lifecycle.py`:

```python
from typer.testing import CliRunner

from devflow.cli import app


runner = CliRunner()


def test_goal_init_writes_active_lifecycle(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    brief = tmp_path / "brief.md"
    brief.write_text("# Ship goal loop\n", encoding="utf-8")

    result = runner.invoke(app, ["goal", "init", "G-0001", "--from", str(brief)])

    assert result.exit_code == 0, result.output
    payload = yaml.safe_load((tmp_path / ".devflow" / "goals" / "G-0001" / "goal-state.yaml").read_text(encoding="utf-8"))
    assert payload["lifecycle"] == "active"


def test_goal_lifecycle_cli_commands_write_state(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    brief = tmp_path / "brief.md"
    brief.write_text("# Ship goal loop\n", encoding="utf-8")
    runner.invoke(app, ["goal", "init", "G-0001", "--from", str(brief)])

    paused = runner.invoke(app, ["goal", "pause", "G-0001", "--reason", "waiting for review"])
    blocked = runner.invoke(app, ["goal", "block", "G-0001", "--reason", "needs answer"])
    active = runner.invoke(app, ["goal", "activate", "G-0001", "--reason", "answer received"])
    complete = runner.invoke(app, ["goal", "complete", "G-0001", "--reason", "all slices promoted"])
    archived = runner.invoke(app, ["goal", "archive", "G-0001", "--reason", "retained as history"])

    assert paused.exit_code == 0, paused.output
    assert "lifecycle: paused" in paused.output
    assert blocked.exit_code == 0, blocked.output
    assert "lifecycle: blocked" in blocked.output
    assert active.exit_code == 0, active.output
    assert "lifecycle: active" in active.output
    assert complete.exit_code == 0, complete.output
    assert "lifecycle: complete" in complete.output
    assert archived.exit_code == 0, archived.output
    assert "lifecycle: archived" in archived.output
```

- [ ] **Step 2: Run tests to verify CLI commands are missing**

Run:

```bash
PYTHONPATH=src:. <repo-root>/.venv/bin/python -m pytest tests/test_goal_lifecycle.py -v
```

Expected: fail because `goal pause`, `goal block`, `goal activate`, `goal complete`, or `goal archive` commands are not registered.

- [ ] **Step 3: Initialize lifecycle from `goals.py`**

In `src/devflow/control_room/goals.py`, import the lifecycle helper:

```python
from devflow.control_room.goal_lifecycle import ensure_goal_lifecycle
```

At the end of `create_goal_from_markdown`, after writing `goal.yaml` and before returning `GoalRecord`, add:

```python
    ensure_goal_lifecycle(root, resolved_id)
```

- [ ] **Step 4: Add CLI command helper and commands**

In `src/devflow/cli.py`, near other `goal_app` commands, add:

```python
def _set_goal_lifecycle_command(goal_id: str, lifecycle: str, reason: str) -> None:
    from devflow.control_room.goal_lifecycle import (
        GoalLifecycleError,
        lifecycle_result,
        render_lifecycle_result,
        set_goal_lifecycle,
    )

    command = f"devflow goal {lifecycle if lifecycle != 'active' else 'activate'} {goal_id}"
    if reason:
        command = f"{command} --reason {reason!r}"
    try:
        state = set_goal_lifecycle(Path.cwd(), goal_id, lifecycle=lifecycle, reason=reason, command=command)
    except GoalLifecycleError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(render_lifecycle_result(lifecycle_result(Path.cwd(), state)), nl=False)
```

Then add commands:

```python
@goal_app.command("activate")
def goal_activate(goal_id: str, reason: str = typer.Option("", "--reason", help="Reason for activating this goal.")) -> None:
    """Mark a goal active for freshness-loop projection."""
    _set_goal_lifecycle_command(goal_id, "active", reason)


@goal_app.command("pause")
def goal_pause(goal_id: str, reason: str = typer.Option(..., "--reason", help="Reason for pausing this goal.")) -> None:
    """Pause goal execution without deleting evidence."""
    _set_goal_lifecycle_command(goal_id, "paused", reason)


@goal_app.command("block")
def goal_block(goal_id: str, reason: str = typer.Option(..., "--reason", help="Blocking reason.")) -> None:
    """Block goal execution until a human decision or external repair."""
    _set_goal_lifecycle_command(goal_id, "blocked", reason)


@goal_app.command("complete")
def goal_complete(goal_id: str, reason: str = typer.Option(..., "--reason", help="Evidence-backed completion reason.")) -> None:
    """Record human-approved goal completion."""
    _set_goal_lifecycle_command(goal_id, "complete", reason)


@goal_app.command("archive")
def goal_archive(goal_id: str, reason: str = typer.Option(..., "--reason", help="Archive reason.")) -> None:
    """Archive a goal while preserving its evidence."""
    _set_goal_lifecycle_command(goal_id, "archived", reason)
```

- [ ] **Step 5: Run lifecycle CLI tests**

Run:

```bash
PYTHONPATH=src:. <repo-root>/.venv/bin/python -m pytest tests/test_goal_lifecycle.py -v
```

Expected: all lifecycle tests pass.

## Task 3: Make Goal Status And Next Lifecycle-Aware

**Files:**
- Modify: `src/devflow/control_room/goal_projection.py`
- Test: `tests/test_goal_projection.py`

- [ ] **Step 1: Add projection tests**

Append to `tests/test_goal_projection.py`:

```python
def test_goal_status_includes_lifecycle_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    _create_goal(tmp_path)

    result = runner.invoke(app, ["goal", "status", "G-0001"])

    assert result.exit_code == 0, result.output
    assert "Lifecycle: active" in result.output


def test_goal_next_recommends_activation_when_lifecycle_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    _create_goal(tmp_path)
    (tmp_path / ".devflow" / "goals" / "G-0001" / "goal-state.yaml").unlink()

    result = runner.invoke(app, ["goal", "next", "G-0001"])

    assert result.exit_code == 0, result.output
    assert "devflow goal activate G-0001" in result.output


def test_goal_next_stops_on_paused_lifecycle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    _create_goal(tmp_path)
    runner.invoke(app, ["goal", "pause", "G-0001", "--reason", "waiting"])

    result = runner.invoke(app, ["goal", "next", "G-0001"])

    assert result.exit_code == 0, result.output
    assert "Goal is paused" in result.output
    assert "devflow freshness" not in result.output
```

Use the existing local helper in that test file if it already creates goal scaffolds; do not duplicate helpers if `_create_goal` already exists.

- [ ] **Step 2: Run projection tests to see lifecycle assertions fail**

Run:

```bash
PYTHONPATH=src:. <repo-root>/.venv/bin/python -m pytest tests/test_goal_projection.py -v
```

Expected: fail on missing lifecycle output or next-action behavior.

- [ ] **Step 3: Extend `GoalStatusProjection`**

In `GoalStatusProjection`, add:

```python
    lifecycle: str = "missing"
    lifecycle_reason: str = ""
    lifecycle_missing: bool = False
```

In `build_goal_status_projection`, after reading goal metadata, load lifecycle:

```python
    from devflow.control_room.goal_lifecycle import read_goal_lifecycle

    lifecycle = "missing"
    lifecycle_reason = ""
    lifecycle_missing = True
    try:
        lifecycle_state = read_goal_lifecycle(root, goal_id)
        if lifecycle_state is not None:
            lifecycle = lifecycle_state.lifecycle
            lifecycle_reason = lifecycle_state.status_reason
            lifecycle_missing = False
    except Exception as exc:
        lifecycle = "unknown"
        lifecycle_reason = str(exc)
        lifecycle_missing = False
        warnings.append(f"warning: goal-state.yaml is unreadable: {exc}")
```

Pass those fields into the `GoalStatusProjection`.

- [ ] **Step 4: Make next-action lifecycle-aware**

Find the helper that computes `GoalNextAction` in `goal_projection.py`. Add these checks before artifact-derived recommendations:

```python
    if proj.lifecycle_missing:
        return GoalNextAction(
            label="Activate goal",
            command=f"devflow goal activate {proj.goal_id} --reason 'ready to execute'",
            reason="Lifecycle state is missing; activate the goal before execution dispatch.",
        )
    if proj.lifecycle == "paused":
        return GoalNextAction(
            label="Goal is paused",
            command=f"devflow goal status {proj.goal_id}",
            reason=proj.lifecycle_reason or "Goal execution is paused.",
        )
    if proj.lifecycle == "blocked":
        return GoalNextAction(
            label="Goal is blocked",
            command=f"devflow goal status {proj.goal_id}",
            reason=proj.lifecycle_reason or "Goal execution is blocked.",
        )
    if proj.lifecycle in {"complete", "archived"}:
        return GoalNextAction(
            label=f"Goal is {proj.lifecycle}",
            command=f"devflow goal status {proj.goal_id}",
            reason=proj.lifecycle_reason or f"Goal lifecycle is {proj.lifecycle}.",
        )
```

If the existing helper does not receive the projection object, pass lifecycle fields into it directly.

- [ ] **Step 5: Render lifecycle in status output**

In `render_goal_status`, add lines near state/title:

```python
        f"Lifecycle: {projection.lifecycle}",
        f"Lifecycle reason: {projection.lifecycle_reason or '-'}",
```

- [ ] **Step 6: Run projection tests**

Run:

```bash
PYTHONPATH=src:. <repo-root>/.venv/bin/python -m pytest tests/test_goal_projection.py -v
```

Expected: projection tests pass.

## Task 4: Gate Freshness Loop By Goal Lifecycle And Add Closure Decision

**Files:**
- Modify: `src/devflow/control_room/goal_loop.py`
- Modify: `src/devflow/control_room/freshness.py`
- Test: `tests/test_freshness_loop.py`

- [ ] **Step 1: Add freshness lifecycle tests**

Append to `tests/test_freshness_loop.py`:

```python
def test_freshness_loop_recommends_activation_when_goal_lifecycle_missing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _project_parallel_goal(tmp_path, [("TS-0001", "src/a.py")])
    (tmp_path / ".devflow" / "goals" / "G-0001" / "goal-state.yaml").unlink(missing_ok=True)

    result = runner.invoke(app, ["freshness", "loop", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    goal_loop = payload["goal_loop"][0]
    assert goal_loop["loop_state"] == "needs_lifecycle_activation"
    assert "devflow goal activate G-0001" in goal_loop["next_action"]
    assert goal_loop["ready_parallel_batch_count"] == 0


def test_freshness_loop_suppresses_dispatch_for_paused_goal(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _project_parallel_goal(tmp_path, [("TS-0001", "src/a.py")])
    runner.invoke(app, ["goal", "pause", "G-0001", "--reason", "waiting"])

    result = runner.invoke(app, ["freshness", "loop", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    goal_loop = payload["goal_loop"][0]
    assert goal_loop["goal_state"] == "paused"
    assert goal_loop["loop_state"] == "paused"
    assert goal_loop["ready_parallel_lane_count"] == 0
    assert goal_loop["parallel_batches"] == []


def test_freshness_loop_recommends_goal_completion_when_all_slices_promoted(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _project_parallel_goal(tmp_path, [("TS-0001", "src/a.py")])
    runner.invoke(app, ["freshness", "create-batch", "G-0001", "PB-0001"])
    task_yaml = tmp_path / ".devflow" / "tasks" / "task-0001" / "task.yaml"
    data = yaml.safe_load(task_yaml.read_text(encoding="utf-8"))
    data["status"] = "promoted"
    task_yaml.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    result = runner.invoke(app, ["freshness", "loop", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    goal_loop = payload["goal_loop"][0]
    assert goal_loop["loop_state"] == "needs_closure_decision"
    assert "devflow goal complete G-0001" in goal_loop["next_action"]
```

Use existing imports and helpers from the file. If `_project_parallel_goal` currently creates a goal through raw files without `goal-state.yaml`, update the helper to create lifecycle explicitly or let individual tests unlink it when testing missing lifecycle.

- [ ] **Step 2: Run freshness tests to verify failures**

Run:

```bash
PYTHONPATH=src:. <repo-root>/.venv/bin/python -m pytest tests/test_freshness_loop.py -v
```

Expected: fail on lifecycle gating and closure next-action behavior.

- [ ] **Step 3: Pass lifecycle data into goal loop state builder**

In `src/devflow/control_room/freshness.py`, load lifecycle state per goal before `build_goal_loop_states`:

```python
from devflow.control_room.goal_lifecycle import read_goal_lifecycle

lifecycle_by_goal: dict[str, dict[str, str | bool]] = {}
for goal_id in goals:
    try:
        lifecycle = read_goal_lifecycle(root, goal_id)
    except Exception as exc:
        findings.append(
            FreshnessFinding(
                id=f"{goal_id}-lifecycle-unreadable",
                severity="needs_human_decision",
                scope=goal_id,
                path=f".devflow/goals/{goal_id}/goal-state.yaml",
                message=f"Goal lifecycle state is unreadable: {exc}",
                suggested_action=f"devflow goal status {goal_id}",
            )
        )
        lifecycle_by_goal[goal_id] = {"lifecycle": "unknown", "reason": str(exc), "missing": False}
        continue
    if lifecycle is None:
        findings.append(
            FreshnessFinding(
                id=f"{goal_id}-lifecycle-missing",
                severity="needs_human_decision",
                scope=goal_id,
                path=f".devflow/goals/{goal_id}/goal-state.yaml",
                message="Goal lifecycle state is missing.",
                suggested_action=f"devflow goal activate {goal_id} --reason 'ready to execute'",
            )
        )
        lifecycle_by_goal[goal_id] = {"lifecycle": "missing", "reason": "", "missing": True}
    else:
        lifecycle_by_goal[goal_id] = {
            "lifecycle": lifecycle.lifecycle,
            "reason": lifecycle.status_reason,
            "missing": False,
        }
```

Update the `build_goal_loop_states(...)` call to pass `lifecycle_by_goal`.

- [ ] **Step 4: Update `build_goal_loop_states` signature**

In `goal_loop.py`, change the signature:

```python
def build_goal_loop_states(
    root: Path,
    goal_ids: list[str],
    goal_slices: dict[str, list[dict[str, Any]]],
    linked_tasks: dict[str, dict[str, list[dict[str, Any]]]],
    lifecycle_by_goal: dict[str, dict[str, Any]] | None = None,
) -> list[GoalLoopState]:
```

At the start of each goal iteration:

```python
        lifecycle_info = (lifecycle_by_goal or {}).get(goal_id, {})
        lifecycle = str(lifecycle_info.get("lifecycle") or goal_state)
        lifecycle_reason = str(lifecycle_info.get("reason") or "")
        lifecycle_missing = bool(lifecycle_info.get("missing"))
```

Before building batches, if missing or non-active, force no dispatch:

```python
        if lifecycle_missing:
            loop_state = "needs_lifecycle_activation"
            states.append(
                GoalLoopState(
                    goal_id=goal_id,
                    title=title,
                    goal_state="missing_lifecycle",
                    loop_state=loop_state,
                    total_slices=len(lanes),
                    linked_task_count=linked_task_count,
                    active_task_count=active_task_count,
                    completed_slice_count=completed_slice_count,
                    ready_parallel_lane_count=0,
                    ready_parallel_batch_count=0,
                    conflicting_ready_lane_count=0,
                    ready_verification_batch_count=0,
                    verification_command_count=0,
                    ready_worker_batch_count=0,
                    worker_command_count=0,
                    blocked_lane_count=blocked_lane_count,
                    next_action=f"Activate lifecycle before dispatch: devflow goal activate {goal_id} --reason 'ready to execute'",
                    lanes=[lane.model_copy(update={"lane_state": "needs_human_review", "command": f"devflow goal activate {goal_id} --reason 'ready to execute'"}) for lane in lanes],
                    parallel_batches=[],
                    worker_batches=[],
                    verification_batches=[],
                )
            )
            continue
        if lifecycle in {"paused", "blocked", "complete", "archived"}:
            states.append(
                GoalLoopState(
                    goal_id=goal_id,
                    title=title,
                    goal_state=lifecycle,
                    loop_state=lifecycle,
                    total_slices=len(lanes),
                    linked_task_count=linked_task_count,
                    active_task_count=active_task_count,
                    completed_slice_count=completed_slice_count,
                    ready_parallel_lane_count=0,
                    ready_parallel_batch_count=0,
                    conflicting_ready_lane_count=0,
                    ready_verification_batch_count=0,
                    verification_command_count=0,
                    ready_worker_batch_count=0,
                    worker_command_count=0,
                    blocked_lane_count=blocked_lane_count,
                    next_action=lifecycle_reason or f"Goal lifecycle is {lifecycle}.",
                    lanes=lanes,
                    parallel_batches=[],
                    worker_batches=[],
                    verification_batches=[],
                )
            )
            continue
```

- [ ] **Step 5: Make closure decision next action explicit**

Update `_goal_loop_next_action` so `needs_closure_decision` returns:

```python
    if loop_state == "needs_closure_decision":
        return f"All slices have promoted task evidence. Review goal evidence, then run: devflow goal complete {goal_id} --reason 'all task slices promoted and reviewed'"
```

If `_goal_loop_next_action` lacks that branch, add it before generic status fallbacks.

- [ ] **Step 6: Include lifecycle in state hash**

In `freshness.py`, pass `lifecycle_by_goal` into `_state_hash` or include it in the payload used by `_state_hash`:

```python
"lifecycle_by_goal": lifecycle_by_goal,
```

Expected: changing a lifecycle state changes `FreshnessReport.state_hash`.

- [ ] **Step 7: Run freshness tests**

Run:

```bash
PYTHONPATH=src:. <repo-root>/.venv/bin/python -m pytest tests/test_freshness_loop.py -v
```

Expected: freshness tests pass.

## Task 5: Expose Lifecycle In Operating Layer And Supervisor Policy

**Files:**
- Modify: `src/devflow/control_room/operating_layer.py`
- Modify: `src/devflow/control_room/supervisor_surface.py`
- Test: `tests/test_operating_layer.py`
- Test: `tests/test_supervisor_operating_surface.py`

- [ ] **Step 1: Add operating-layer lifecycle test**

Append to `tests/test_operating_layer.py`:

```python
def test_operating_layer_goal_board_exposes_lifecycle(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _create_goal(tmp_path)
    runner.invoke(app, ["goal", "pause", "G-0001", "--reason", "waiting"])

    snapshot = build_operating_layer_snapshot(tmp_path)

    assert snapshot.goal_board[0].goal_id == "G-0001"
    assert snapshot.goal_board[0].lifecycle == "paused"
    assert snapshot.goal_board[0].lifecycle_reason == "waiting"
```

Use the existing snapshot helper names in the file. If the file uses `build_snapshot`, adapt only the call name, not the assertion intent.

- [ ] **Step 2: Add supervisor policy tests**

Append to `tests/test_supervisor_operating_surface.py`:

```python
def test_goal_lifecycle_commands_are_approval_required_state_changes() -> None:
    for command in (
        "devflow goal activate G-0001 --reason ready",
        "devflow goal pause G-0001 --reason waiting",
        "devflow goal block G-0001 --reason blocked",
        "devflow goal complete G-0001 --reason done",
        "devflow goal archive G-0001 --reason superseded",
    ):
        classification = classify_supervisor_command(command)
        assert classification["safety_class"] == APPROVAL_REQUIRED_TASK_STATE
        assert classification["requires_human_approval"] is True
        assert classification["supervisor_may_auto_run"] is False
```

- [ ] **Step 3: Run target tests to verify failures**

Run:

```bash
PYTHONPATH=src:. <repo-root>/.venv/bin/python -m pytest tests/test_operating_layer.py tests/test_supervisor_operating_surface.py -v
```

Expected: fail on missing lifecycle fields and supervisor classifications.

- [ ] **Step 4: Add lifecycle fields to operating-layer goal models**

In `operating_layer.py`, find the goal board/spec board model used for goals. Add fields:

```python
    lifecycle: str = "missing"
    lifecycle_reason: str = ""
```

When building each goal board item from `GoalStatusProjection`, set:

```python
lifecycle=projection.lifecycle,
lifecycle_reason=projection.lifecycle_reason,
```

Do not parse `goal-state.yaml` again in the operating layer; use `goal_projection`.

- [ ] **Step 5: Classify lifecycle commands**

In `supervisor_surface.py`, add these to `APPROVAL_REQUIRED_TASK_STATE_COMMANDS`:

```python
    "devflow goal activate",
    "devflow goal pause",
    "devflow goal block",
    "devflow goal complete",
    "devflow goal archive",
```

In `_classify_supervisor_command`, update goal command classification:

```python
    if command_group == "goal":
        if subcommand in {"list", "show", "status", "next", "slices"}:
            return PURE_READ_ONLY
        if subcommand in {"init", "create-task", "activate", "pause", "block", "complete", "archive"}:
            return APPROVAL_REQUIRED_TASK_STATE
        return FORBIDDEN_FOR_SUPERVISOR
```

Preserve existing classifications for current goal commands.

- [ ] **Step 6: Run target tests**

Run:

```bash
PYTHONPATH=src:. <repo-root>/.venv/bin/python -m pytest tests/test_operating_layer.py tests/test_supervisor_operating_surface.py -v
```

Expected: target tests pass.

## Task 6: Add End-To-End Goal Loop Dogfood Test

**Files:**
- Test: `tests/test_goal_lifecycle.py` or `tests/test_freshness_runner.py`

- [ ] **Step 1: Add an end-to-end test**

Add this test to the most appropriate existing file. Prefer `tests/test_freshness_runner.py` if it already covers `freshness run`; otherwise use `tests/test_goal_lifecycle.py`.

```python
def test_active_goal_runs_through_create_worker_verify_without_auto_completion(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    brief = tmp_path / "brief.md"
    brief.write_text("# Goal loop smoke\n", encoding="utf-8")
    runner.invoke(app, ["goal", "init", "G-0001", "--from", str(brief)])
    slices_path = tmp_path / ".devflow" / "goals" / "G-0001" / "task-slices.yaml"
    slices_path.write_text(
        """
task_slices:
  - task_id: TS-0001
    title: "Write goal loop output"
    summary: "Create one output file and verify it."
    blocked_by: []
    parallel_safe: true
    shared_files:
      - result.txt
    risk: low
    execution_mode: AFK
    workspace_isolation_required: false
    promotion_allowed: false
    worker_policy:
      shell_commands:
        - "printf goal-loop > result.txt"
    verification_policy:
      focused_commands:
        - "test -f result.txt"
""".lstrip(),
        encoding="utf-8",
    )

    created = runner.invoke(app, ["freshness", "run", "--max-iterations", "3", "--create-tasks", "--json"])
    assert created.exit_code == 0, created.output
    assert (tmp_path / ".devflow" / "tasks" / "task-0001" / "goal-link.yaml").exists()

    worker = runner.invoke(
        app,
        ["freshness", "worker-batch", "G-0001", "WB-0001", "--max-parallel", "1", "--timeout-seconds", "10", "--json"],
    )
    assert worker.exit_code == 0, worker.output
    assert (tmp_path / ".devflow" / "workspaces" / "task-0001" / "result.txt").read_text(encoding="utf-8") == "goal-loop"

    verified = runner.invoke(
        app,
        ["freshness", "verify-batch", "G-0001", "VB-0001", "--max-parallel", "1", "--timeout-seconds", "10", "--json"],
    )
    assert verified.exit_code == 0, verified.output
    verification = yaml.safe_load((tmp_path / ".devflow" / "tasks" / "task-0001" / "verification.json").read_text(encoding="utf-8"))
    assert verification["status"] == "passed"

    final_loop = runner.invoke(app, ["freshness", "loop", "--json"])
    assert final_loop.exit_code == 0, final_loop.output
    payload = json.loads(final_loop.output)
    assert payload["goal_loop"][0]["loop_state"] in {"active_work_in_progress", "needs_closure_decision"}
    state = yaml.safe_load((tmp_path / ".devflow" / "goals" / "G-0001" / "goal-state.yaml").read_text(encoding="utf-8"))
    assert state["lifecycle"] == "active"
```

This test intentionally stops before promotion or `goal complete`.

- [ ] **Step 2: Run the end-to-end test**

Run:

```bash
PYTHONPATH=src:. <repo-root>/.venv/bin/python -m pytest tests/test_freshness_runner.py tests/test_goal_lifecycle.py -v
```

Expected: pass. If the selected file does not contain the test, run the file where the test was added.

## Task 7: Docs, Verification, Checkpoint, And Handoff

**Files:**
- Modify: `docs/roadmap.md`
- Modify: `docs/control-room-mvp.md`
- Modify: `docs/mvp-contract.md`
- Modify: `docs/architecture/goal-control-loop.md`
- Create: `docs/handoffs/2026-06-13-goal-execution-control-loop-complete.md`

- [ ] **Step 1: Update active docs**

After implementation passes focused tests, update docs to say:

- Milestone 14 goal execution control loop is implemented.
- Goal lifecycle state is canonical under `.devflow/goals/<goal_id>/goal-state.yaml`.
- `goal activate/pause/block/complete/archive` are current commands.
- Freshness loop gates dispatch on lifecycle state.
- Completion is human-controlled and evidence-backed.

Keep this boundary text:

```text
Goal lifecycle and freshness execution commands do not call providers, route models, auto-promote, auto-commit, auto-push, open pull requests, or mark goals complete without explicit human command evidence.
```

- [ ] **Step 2: Run focused tests**

Run:

```bash
PYTHONPATH=src:. <repo-root>/.venv/bin/python -m pytest \
  tests/test_goal_lifecycle.py \
  tests/test_goal_projection.py \
  tests/test_freshness_loop.py \
  tests/test_freshness_runner.py \
  tests/test_operating_layer.py \
  tests/test_supervisor_operating_surface.py \
  -v
```

Expected: all selected tests pass.

- [ ] **Step 3: Run CLI smoke checks in a temp directory**

Run:

```bash
TMPDIR="$(mktemp -d)"
printf '# Smoke goal\n' > "$TMPDIR/brief.md"
cd "$TMPDIR"
PYTHONPATH=<repo-root>/src:<repo-root> <repo-root>/.venv/bin/devflow goal init G-9998 --from "$TMPDIR/brief.md"
PYTHONPATH=<repo-root>/src:<repo-root> <repo-root>/.venv/bin/devflow goal status G-9998
PYTHONPATH=<repo-root>/src:<repo-root> <repo-root>/.venv/bin/devflow goal pause G-9998 --reason "smoke pause"
PYTHONPATH=<repo-root>/src:<repo-root> <repo-root>/.venv/bin/devflow freshness loop --json
```

Expected: commands exit 0, status prints lifecycle, pause writes `lifecycle: paused`, and freshness JSON does not project dispatch batches for the paused goal.

- [ ] **Step 4: Run stale-context and diff checks**

Run from repo root:

```bash
git diff --check
rg -n "\*\*Current Priority\*\*: Milestone 13|Milestone 14 goal execution control loop is current behavior|goal lifecycle.*future-only|goal activate.*future|goal complete.*future" README.md docs/control-room-mvp.md docs/mvp-contract.md docs/roadmap.md docs/architecture/goal-control-loop.md docs/handoffs
```

Expected: `git diff --check` exits 0. Stale-context scan has no active-doc matches that describe implemented Milestone 14 commands as future-only or keep Milestone 13 as the next implementation priority. Matches in historical spec/plan files are acceptable only when clearly labeled historical.

- [ ] **Step 5: Verify through Dev-Flow and promote**

Use a Dev-Flow task worktree for implementation. After focused tests pass, run:

```bash
PYTHONPATH=src:. .venv/bin/devflow task verify <task_id> --shell 'PYTHONPATH=src:. <repo-root>/.venv/bin/python -m pytest tests/test_goal_lifecycle.py tests/test_goal_projection.py tests/test_freshness_loop.py tests/test_freshness_runner.py tests/test_operating_layer.py tests/test_supervisor_operating_surface.py -v' --timeout-seconds 180
PYTHONPATH=src:. .venv/bin/devflow task finalize <task_id> --commit
PYTHONPATH=src:. .venv/bin/devflow task promote-preview <task_id>
```

Expected: verification passes and promote-preview reports readiness or a concrete repair action. Ask Josh before running `devflow task promote <task_id>`.

- [ ] **Step 6: Write final handoff**

Use `docs/handoff-template.md`. The next safe action must be exactly one action, usually approval for `devflow push-main` after promotion and checkpoint.

## Self-Review Checklist

- Spec coverage: lifecycle service, CLI, projections, freshness gating, operating layer, supervisor policy, dogfood path, and docs are covered.
- Placeholder scan: no implementation steps use placeholder terms or ask for unspecified tests.
- Type consistency: lifecycle values are `active`, `paused`, `blocked`, `complete`, `archived`; file path is `.devflow/goals/<goal_id>/goal-state.yaml`; event file is `.devflow/goals/<goal_id>/events.jsonl`.
- Scope check: no provider adapters, routing, memory, PR automation, database, daemon, or browser worker execution is included.
