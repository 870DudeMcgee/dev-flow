# Review Readiness Scorecard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a read-only review readiness scorecard that tells Dev-Flow which active tasks are ready for human review, which are not, and the safest next command.

**Status:** Implemented on 2026-06-12. Final checkpoint is intentionally deferred until unrelated dirty work in the checkout is resolved or explicitly included.

**Architecture:** Add one derived projection module in `src/devflow/control_room/review_readiness.py` and reuse it from the task CLI, freshness loop, and operating-layer snapshot. The projection reads existing task evidence and never runs verification, creates promotion previews, exports capsules, promotes, closes, or mutates canonical task state.

**Tech Stack:** Python 3, Typer CLI, Pydantic models, existing Dev-Flow control-room modules, pytest.

---

## Working Rules

- Keep all implementation under `src/devflow/control_room/` except CLI wiring in `src/devflow/cli.py` and tests under `tests/`.
- Preserve existing dirty work from other sessions. Before any checkpoint, run `devflow git status`; only use `devflow git checkpoint --message "..." --yes` when the dirty files are exactly the intended files for that checkpoint.
- Do not use raw `git push`, raw promotion merges, or conflict-resolution rebases.
- The new scorecard is read-only. Any test that runs `devflow task review-ready` should prove it does not create or modify task files.

## File Structure

- Create `src/devflow/control_room/review_readiness.py`
  - Owns `ReviewReadinessProjection`, `ReviewReadinessSummary`, projection builders, promotion-preview evidence detection, and text rendering.
- Modify `src/devflow/cli.py`
  - Adds `devflow task review-ready [<task_id>] --json [--project <project_id>]`.
  - Adds `--project` support to `devflow task capsule` so operating-layer project-scoped capsule commands are runnable.
- Modify `src/devflow/control_room/freshness.py`
  - Adds read-only aggregate review readiness counts to `FreshnessReport`, snapshot JSON, text rendering, freshness event payloads, and state hash.
- Modify `src/devflow/control_room/operating_layer.py`
  - Adds review readiness fields to `OperatingLayerTask` and populates them from the shared projection.
- Create `tests/test_review_readiness.py`
  - Covers core projection states, CLI JSON output, project-scoped command formatting, project-scoped capsule support, and read-only behavior.
- Modify `tests/test_freshness_loop.py`
  - Covers aggregate freshness counts.
- Modify `tests/test_operating_layer.py`
  - Covers operating-layer task fields. Coordinate with any existing dirty edits in this file before applying patches.

---

### Task 1: Add Failing Review Readiness Tests

**Files:**
- Create: `tests/test_review_readiness.py`

- [x] **Step 1: Write failing tests for core scorecard states and CLI behavior**

Create `tests/test_review_readiness.py` with:

```python
from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from devflow.cli import app
from devflow.control_room.persistence import get_task, save_task, utc_now


runner = CliRunner()


def _write_promotion_preview(root: Path, task_id: str, readiness: str = "ready") -> None:
    path = root / ".devflow" / "tasks" / task_id / "promotion-preview.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "task_id": task_id,
                "promotion_readiness": readiness,
                "human_approval_required": False,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _task_file_snapshot(root: Path, task_id: str) -> dict[str, bytes]:
    base = root / ".devflow" / "tasks" / task_id
    return {
        path.relative_to(base).as_posix(): path.read_bytes()
        for path in sorted(base.rglob("*"))
        if path.is_file()
    }


def _set_task_state(
    root: Path,
    task_id: str,
    *,
    status: str,
    verification_status: str = "not_run",
    verification_exit_code: int | None = None,
) -> None:
    task = get_task(root, task_id)
    task.status = status
    task.verification_status = verification_status
    task.verification_exit_code = verification_exit_code
    task.updated_at = utc_now()
    save_task(root / ".devflow" / "tasks" / task_id, task)


def test_review_ready_cli_reports_ready_for_review_and_is_read_only(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    assert runner.invoke(app, ["task", "create", "ready review"]).exit_code == 0
    assert runner.invoke(app, ["task", "run", "task-0001", "--shell", "echo ready > result.txt"]).exit_code == 0
    verify = runner.invoke(app, ["task", "verify", "task-0001", "--shell", "test -f result.txt"])
    assert verify.exit_code == 0, verify.output
    _write_promotion_preview(tmp_path, "task-0001")

    before = _task_file_snapshot(tmp_path, "task-0001")
    result = runner.invoke(app, ["task", "review-ready", "task-0001", "--json"])
    after = _task_file_snapshot(tmp_path, "task-0001")

    assert result.exit_code == 0, result.output
    assert before == after
    payload = json.loads(result.output)
    assert payload["task_id"] == "task-0001"
    assert payload["review_state"] == "ready_for_review"
    assert payload["score"] == 100
    assert payload["blockers"] == []
    assert payload["next_command"] == "devflow task capsule task-0001"
    assert ".devflow/tasks/task-0001/task.yaml" in payload["evidence"]
    assert ".devflow/tasks/task-0001/verification.json" in payload["evidence"]
    assert ".devflow/tasks/task-0001/promotion-preview.json" in payload["evidence"]


def test_review_ready_cli_reports_needs_verification_for_completed_worker_output(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    assert runner.invoke(app, ["task", "create", "needs verify"]).exit_code == 0
    run = runner.invoke(app, ["task", "run", "task-0001", "--shell", "echo done > result.txt"])
    assert run.exit_code == 0, run.output

    result = runner.invoke(app, ["task", "review-ready", "task-0001", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["review_state"] == "needs_verification"
    assert payload["score"] == 60
    assert payload["blockers"] == ["verification has not passed"]
    assert payload["next_command"] == 'devflow task verify task-0001 --shell "<command>"'


def test_review_ready_cli_reports_verification_failed(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    assert runner.invoke(app, ["task", "create", "failed verify"]).exit_code == 0
    assert runner.invoke(app, ["task", "run", "task-0001", "--shell", "echo done > result.txt"]).exit_code == 0
    verify = runner.invoke(app, ["task", "verify", "task-0001", "--shell", "exit 7"])
    assert verify.exit_code == 7, verify.output

    result = runner.invoke(app, ["task", "review-ready", "task-0001", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["review_state"] == "verification_failed"
    assert payload["score"] == 40
    assert payload["blockers"] == ["verification failed"]
    assert payload["next_command"] == "devflow task log task-0001 --verify --tail 80"


def test_review_ready_cli_reports_needs_promotion_preview(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    assert runner.invoke(app, ["task", "create", "preview missing"]).exit_code == 0
    assert runner.invoke(app, ["task", "run", "task-0001", "--shell", "echo done > result.txt"]).exit_code == 0
    verify = runner.invoke(app, ["task", "verify", "task-0001", "--shell", "test -f result.txt"])
    assert verify.exit_code == 0, verify.output

    result = runner.invoke(app, ["task", "review-ready", "task-0001", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["review_state"] == "needs_promotion_preview"
    assert payload["score"] == 80
    assert payload["blockers"] == ["promotion-preview.json is missing"]
    assert payload["next_command"] == "devflow task promote-preview task-0001"


def test_review_ready_cli_reports_blocked_worker_failed_and_running_states(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    assert runner.invoke(app, ["task", "create", "blocked"]).exit_code == 0
    assert runner.invoke(app, ["task", "create", "worker failed"]).exit_code == 0
    assert runner.invoke(app, ["task", "create", "running"]).exit_code == 0
    _set_task_state(tmp_path, "task-0001", status="blocked")
    _set_task_state(tmp_path, "task-0002", status="worker_failed")
    _set_task_state(tmp_path, "task-0003", status="running", verification_status="pending")

    result = runner.invoke(app, ["task", "review-ready", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    states = {item["task_id"]: item["review_state"] for item in payload["tasks"]}
    assert states == {
        "task-0001": "blocked",
        "task-0002": "worker_failed",
        "task-0003": "running",
    }


def test_review_ready_project_scope_and_capsule_project_option_are_runnable(
    tmp_path: Path,
    monkeypatch,
) -> None:
    projects_root = tmp_path / "projects"
    monkeypatch.setenv("DEVFLOW_PROJECTS_ROOT", projects_root.as_posix())
    monkeypatch.setenv("DEVFLOW_HOME", (tmp_path / "home" / ".devflow").as_posix())
    monkeypatch.chdir(tmp_path)

    created = runner.invoke(app, ["project", "create", "Demo App"])
    assert created.exit_code == 0, created.output
    project_root = projects_root / "demo-app"
    assert project_root.exists()

    task_created = runner.invoke(app, ["task", "create", "--project", "demo-app", "project ready"])
    assert task_created.exit_code == 0, task_created.output
    run = runner.invoke(app, ["task", "run", "task-0001", "--project", "demo-app", "--shell", "echo done > result.txt"])
    assert run.exit_code == 0, run.output
    verify = runner.invoke(app, ["task", "verify", "task-0001", "--project", "demo-app", "--shell", "test -f result.txt"])
    assert verify.exit_code == 0, verify.output
    _write_promotion_preview(project_root, "task-0001")

    result = runner.invoke(app, ["task", "review-ready", "task-0001", "--project", "demo-app", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["next_command"] == "devflow task capsule task-0001 --project demo-app"

    capsule = runner.invoke(app, ["task", "capsule", "task-0001", "--project", "demo-app"])
    assert capsule.exit_code == 0, capsule.output
    assert "REVIEW CAPSULE - task-0001" in capsule.output
```

- [x] **Step 2: Run the new tests and verify they fail for missing command/module**

Run:

```bash
pytest tests/test_review_readiness.py -v
```

Expected: FAIL with import or CLI errors mentioning missing `review_readiness` or missing `task review-ready`.

---

### Task 2: Implement the Shared Review Readiness Projection

**Files:**
- Create: `src/devflow/control_room/review_readiness.py`

- [x] **Step 1: Add the projection module**

Create `src/devflow/control_room/review_readiness.py` with:

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from devflow.control_room.git_worktree import is_git_worktree_task, worker_id_for_task
from devflow.control_room.models import TaskRecord
from devflow.control_room.paths import relative_path, task_dir, task_worker_dir
from devflow.control_room.persistence import get_task, list_tasks
from devflow.control_room.status_projection import TaskStatusProjection, build_task_status_projection


ReviewState = Literal[
    "ready_for_review",
    "needs_verification",
    "verification_failed",
    "needs_promotion_preview",
    "blocked",
    "worker_failed",
    "running",
    "not_ready",
]

REVIEW_STATES: tuple[ReviewState, ...] = (
    "ready_for_review",
    "needs_verification",
    "verification_failed",
    "needs_promotion_preview",
    "blocked",
    "worker_failed",
    "running",
    "not_ready",
)


class ReviewReadinessProjection(BaseModel):
    task_id: str
    title: str
    status: str
    display_status: str
    verification_status: str
    review_state: ReviewState
    score: int
    blockers: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    next_command: str
    promotion_preview_path: str | None = None


class ReviewReadinessSummary(BaseModel):
    schema_version: int = 1
    total_tasks: int
    ready_for_review_count: int
    needs_verification_count: int
    review_blocked_count: int
    counts: dict[str, int] = Field(default_factory=dict)
    tasks: list[ReviewReadinessProjection] = Field(default_factory=list)


def build_review_readiness_projection(
    root: Path,
    task_id: str,
    *,
    task: TaskRecord | None = None,
    status_projection: TaskStatusProjection | None = None,
    project_id: str | None = None,
) -> ReviewReadinessProjection:
    record = task or get_task(root, task_id)
    projection = status_projection or build_task_status_projection(root, record.id, task=record)
    preview = _promotion_preview_state(root, record)
    evidence = _evidence_paths(root, projection, preview.path)

    state, score, blockers, next_command = _classify_review_readiness(projection, preview, project_id=project_id)
    return ReviewReadinessProjection(
        task_id=record.id,
        title=record.title,
        status=record.status,
        display_status=projection.display_status,
        verification_status=projection.verification_status,
        review_state=state,
        score=score,
        blockers=blockers,
        evidence=evidence,
        next_command=next_command,
        promotion_preview_path=preview.path,
    )


def list_review_readiness_projections(root: Path, *, project_id: str | None = None) -> list[ReviewReadinessProjection]:
    projections = [
        build_review_readiness_projection(root, task.id, task=task, project_id=project_id)
        for task in list_tasks(root)
        if task.status not in {"closed", "promoted"}
    ]
    return sorted(projections, key=lambda item: (-item.score, item.task_id))


def summarize_review_readiness(root: Path, *, project_id: str | None = None) -> ReviewReadinessSummary:
    tasks = list_review_readiness_projections(root, project_id=project_id)
    counts = {state: 0 for state in REVIEW_STATES}
    for task in tasks:
        counts[task.review_state] = counts.get(task.review_state, 0) + 1
    review_blocked_count = (
        counts.get("blocked", 0)
        + counts.get("worker_failed", 0)
        + counts.get("verification_failed", 0)
    )
    return ReviewReadinessSummary(
        total_tasks=len(tasks),
        ready_for_review_count=counts.get("ready_for_review", 0),
        needs_verification_count=counts.get("needs_verification", 0),
        review_blocked_count=review_blocked_count,
        counts=counts,
        tasks=tasks,
    )


def render_review_readiness(projection: ReviewReadinessProjection | ReviewReadinessSummary) -> str:
    if isinstance(projection, ReviewReadinessSummary):
        lines = [
            "Review Readiness",
            f"  Total active tasks: {projection.total_tasks}",
            f"  Ready for review: {projection.ready_for_review_count}",
            f"  Needs verification: {projection.needs_verification_count}",
            f"  Review blocked: {projection.review_blocked_count}",
            "",
            "Tasks",
        ]
        if not projection.tasks:
            lines.append("  None")
        for task in projection.tasks:
            lines.append(f"  - {task.task_id}: {task.review_state} (score={task.score})")
            lines.append(f"    next: {task.next_command}")
            if task.blockers:
                lines.append(f"    blockers: {'; '.join(task.blockers)}")
        return "\n".join(lines) + "\n"

    lines = [
        f"task: {projection.task_id}",
        f"title: {projection.title}",
        f"status: {projection.status}",
        f"display_status: {projection.display_status}",
        f"verification_status: {projection.verification_status}",
        f"review_state: {projection.review_state}",
        f"score: {projection.score}",
        f"next_command: {projection.next_command}",
        "blockers:",
    ]
    if projection.blockers:
        lines.extend(f"  - {blocker}" for blocker in projection.blockers)
    else:
        lines.append("  - none")
    lines.append("evidence:")
    if projection.evidence:
        lines.extend(f"  - {path}" for path in projection.evidence)
    else:
        lines.append("  - none")
    return "\n".join(lines) + "\n"


class _PromotionPreviewState(BaseModel):
    available: bool
    path: str | None = None
    blocker: str | None = None


def _classify_review_readiness(
    projection: TaskStatusProjection,
    preview: _PromotionPreviewState,
    *,
    project_id: str | None,
) -> tuple[ReviewState, int, list[str], str]:
    task_id = projection.task.id
    if not projection.is_active:
        return "not_ready", 0, ["task is not active"], _task_command("show", task_id, project_id)
    if projection.is_blocked:
        blocker = projection.manual_agent_question or "task is blocked or awaiting human input"
        return "blocked", 30, [blocker], _task_command("show", task_id, project_id)
    if projection.is_worker_failed or projection.is_timeout:
        return "worker_failed", 20, ["worker failed before reviewable output"], _task_command(
            "log", task_id, project_id
        )
    if projection.task.status == "running":
        return "running", 35, ["task is still running"], _task_command("show", task_id, project_id)
    if projection.failed_verification:
        return "verification_failed", 40, ["verification failed"], _task_command(
            "log", task_id, project_id, suffix="--verify --tail 80"
        )
    if projection.needs_verification:
        command = projection.dashboard_next_action.command or _task_command(
            "verify", task_id, project_id, suffix='--shell "<command>"'
        )
        return "needs_verification", 60, ["verification has not passed"], _scope_task_command(command, project_id)
    if projection.is_verified:
        if preview.available:
            return "ready_for_review", 100, [], _task_command("capsule", task_id, project_id)
        return "needs_promotion_preview", 80, [preview.blocker or "promotion preview is missing"], _task_command(
            "promote-preview", task_id, project_id
        )
    return "not_ready", 10, ["no reviewable task output was found"], _task_command("show", task_id, project_id)


def _promotion_preview_state(root: Path, task: TaskRecord) -> _PromotionPreviewState:
    for path in _promotion_preview_candidates(root, task):
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            return _PromotionPreviewState(
                available=False,
                path=relative_path(root, path),
                blocker=f"promotion-preview.json is invalid JSON: {exc.msg}",
            )
        except OSError as exc:
            return _PromotionPreviewState(
                available=False,
                path=relative_path(root, path),
                blocker=f"promotion-preview.json is unreadable: {exc}",
            )
        if not isinstance(payload, dict):
            return _PromotionPreviewState(
                available=False,
                path=relative_path(root, path),
                blocker="promotion-preview.json is not an object",
            )
        return _PromotionPreviewState(available=True, path=relative_path(root, path))
    return _PromotionPreviewState(available=False, blocker="promotion-preview.json is missing")


def _promotion_preview_candidates(root: Path, task: TaskRecord) -> list[Path]:
    candidates: list[Path] = []
    if is_git_worktree_task(task):
        candidates.append(task_worker_dir(root, task.id, worker_id_for_task(task)) / "promotion-preview.json")
    candidates.append(task_dir(root, task.id) / "promotion-preview.json")
    return candidates


def _evidence_paths(root: Path, projection: TaskStatusProjection, preview_path: str | None) -> list[str]:
    task_path = projection.task_path
    paths = [
        relative_path(root, task_path / "task.yaml"),
        relative_path(root, task_path / "events.jsonl"),
    ]
    verification_path = task_path / "verification.json"
    if verification_path.exists():
        paths.append(relative_path(root, verification_path))
    if preview_path:
        paths.append(preview_path)
    for value in (
        projection.task.log_path,
        projection.task.result_path,
        projection.verification_log_path,
    ):
        if value:
            paths.append(_display_path(root, value))
    return _dedupe(paths)


def _display_path(root: Path, value: str) -> str:
    path = Path(value)
    if path.is_absolute():
        try:
            return relative_path(root, path)
        except ValueError:
            return path.as_posix()
    return value


def _task_command(action: str, task_id: str, project_id: str | None, *, suffix: str | None = None) -> str:
    command = f"devflow task {action} {task_id}"
    if project_id:
        command = f"{command} --project {project_id}"
    if suffix:
        command = f"{command} {suffix}"
    return command


def _scope_task_command(command: str, project_id: str | None) -> str:
    if not project_id or "--project" in command or not command.startswith("devflow task "):
        return command
    before_separator, separator, after_separator = command.partition(" -- ")
    scoped = f"{before_separator} --project {project_id}"
    if separator:
        return f"{scoped}{separator}{after_separator}"
    return scoped


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result
```

- [x] **Step 2: Run focused module tests and confirm CLI still fails**

Run:

```bash
pytest tests/test_review_readiness.py -v
```

Expected: FAIL because `devflow task review-ready` and `task capsule --project` are not wired yet.

---

### Task 3: Wire the Task CLI

**Files:**
- Modify: `src/devflow/cli.py`

- [x] **Step 1: Import the review readiness helpers**

Add this import near the other control-room imports:

```python
from devflow.control_room.review_readiness import (
    build_review_readiness_projection,
    list_review_readiness_projections,
    render_review_readiness,
    summarize_review_readiness,
)
```

- [x] **Step 2: Add the `review-ready` task command**

Add this command after `task_next_action_command` and before `task_review_command`:

```python
@task_app.command("review-ready")
def task_review_ready(
    task_id: str | None = typer.Argument(None, help="Task ID to inspect. Omit to inspect all active tasks."),
    json_output: bool = typer.Option(False, "--json", help="Print review readiness as JSON."),
    project: str | None = typer.Option(None, "--project", help="Inspect tasks from a registered project root."),
) -> None:
    """Render read-only review readiness from existing task evidence."""
    scope = _resolve_task_project_root(project)
    try:
        if task_id:
            projection = build_review_readiness_projection(scope.root, task_id, project_id=scope.project_id)
            if json_output:
                typer.echo(json.dumps(projection.model_dump(), indent=2, sort_keys=True))
            else:
                typer.echo(render_review_readiness(projection), nl=False)
            return

        summary = summarize_review_readiness(scope.root, project_id=scope.project_id)
        if json_output:
            typer.echo(json.dumps(summary.model_dump(), indent=2, sort_keys=True))
        else:
            typer.echo(render_review_readiness(summary), nl=False)
    except KeyError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
```

- [x] **Step 3: Make `task capsule` project-aware**

Replace the existing `task_capsule` function with:

```python
@task_app.command("capsule")
def task_capsule(
    task_id: str,
    export_md: bool = typer.Option(False, "--export-md", help="Write one explicit markdown export under the task evidence folder."),
    project: str | None = typer.Option(None, "--project", help="Render a capsule from a registered project root."),
) -> None:
    """Render a read-only Review Capsule from existing task evidence."""
    scope = _resolve_task_project_root(project)
    root = scope.root
    try:
        capsule = render_review_capsule(root, task_id)
    except (KeyError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(capsule, nl=False)
    if export_md:
        export_path = export_review_capsule_markdown(root, task_id, capsule)
        typer.echo(f"export_path: {_relative(root, export_path)}")
```

- [x] **Step 4: Run the CLI tests**

Run:

```bash
pytest tests/test_review_readiness.py -v
```

Expected: PASS.

- [x] **Step 5: Checkpoint only if the worktree contains no unrelated changes**

Run:

```bash
devflow git status
```

Expected before checkpoint: dirty files are `src/devflow/control_room/review_readiness.py`, `src/devflow/cli.py`, and `tests/test_review_readiness.py`, plus any previously approved spec/plan docs if they have not been checkpointed.

If unrelated dirty files are present, stop and report the checkpoint blocker. If the dirty files are exactly intended, run:

```bash
devflow git checkpoint --message "feat: add review readiness task cli" --yes
```

Expected: local checkpoint commit succeeds.

---

### Task 4: Add Freshness Aggregate Counts

**Files:**
- Modify: `src/devflow/control_room/freshness.py`
- Modify: `tests/test_freshness_loop.py`

- [x] **Step 1: Add failing freshness aggregate test**

Append this test to `tests/test_freshness_loop.py`:

```python
def test_freshness_loop_includes_review_readiness_counts(tmp_path: Path, monkeypatch) -> None:
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    runner = CliRunner()
    assert runner.invoke(app, ["task", "create", "ready review"]).exit_code == 0
    assert runner.invoke(app, ["task", "run", "task-0001", "--shell", "echo ready > result.txt"]).exit_code == 0
    assert runner.invoke(app, ["task", "verify", "task-0001", "--shell", "test -f result.txt"]).exit_code == 0
    (tmp_path / ".devflow/tasks/task-0001/promotion-preview.json").write_text(
        json.dumps({"schema_version": 1, "task_id": "task-0001", "promotion_readiness": "ready"}) + "\n",
        encoding="utf-8",
    )

    assert runner.invoke(app, ["task", "create", "needs verification"]).exit_code == 0
    assert runner.invoke(app, ["task", "run", "task-0002", "--shell", "echo done > result.txt"]).exit_code == 0

    assert runner.invoke(app, ["task", "create", "blocked review"]).exit_code == 0
    blocked = get_task(tmp_path, "task-0003")
    blocked.status = "blocked"
    blocked.updated_at = utc_now()
    save_task(tmp_path / ".devflow/tasks/task-0003", blocked)

    result = runner.invoke(app, ["freshness", "loop", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["ready_for_review_count"] == 1
    assert payload["needs_verification_count"] == 1
    assert payload["review_blocked_count"] == 1

    snapshot = json.loads((tmp_path / ".devflow/freshness/latest.json").read_text(encoding="utf-8"))
    assert snapshot["ready_for_review_count"] == 1
    assert snapshot["needs_verification_count"] == 1
    assert snapshot["review_blocked_count"] == 1
```

- [x] **Step 2: Run the new test and verify it fails**

Run:

```bash
pytest tests/test_freshness_loop.py::test_freshness_loop_includes_review_readiness_counts -v
```

Expected: FAIL because `FreshnessReport` does not expose the new count fields.

- [x] **Step 3: Add fields and compute counts in `freshness.py`**

Add the import:

```python
from devflow.control_room.review_readiness import ReviewReadinessSummary, summarize_review_readiness
```

Add fields to `FreshnessReport`:

```python
    ready_for_review_count: int = 0
    needs_verification_count: int = 0
    review_blocked_count: int = 0
```

In `run_freshness_loop`, compute the summary before the state hash:

```python
    review_readiness = summarize_review_readiness(root)
    state_hash = _state_hash(root, goals, linked_tasks, findings, goal_loop, review_readiness)
```

Set the new fields when constructing `FreshnessReport`:

```python
        ready_for_review_count=review_readiness.ready_for_review_count,
        needs_verification_count=review_readiness.needs_verification_count,
        review_blocked_count=review_readiness.review_blocked_count,
```

Update `_state_hash` signature and payload:

```python
def _state_hash(
    root: Path,
    goal_ids: list[str],
    linked_tasks: dict[str, dict[str, list[dict[str, Any]]]],
    findings: list[FreshnessFinding],
    goal_loop: list[GoalLoopState],
    review_readiness: ReviewReadinessSummary,
) -> str:
    payload = {
        "goal_ids": goal_ids,
        "linked_tasks": linked_tasks,
        "findings": [finding.model_dump() for finding in findings],
        "goal_loop": [goal.model_dump() for goal in goal_loop],
        "review_readiness": review_readiness.model_dump(),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
```

In `render_freshness_report`, add these lines under `State Tested`:

```python
            f"  Ready for review: {report.ready_for_review_count}",
            f"  Needs verification: {report.needs_verification_count}",
            f"  Review blocked: {report.review_blocked_count}",
```

In `_append_freshness_event`, add these event fields:

```python
        "ready_for_review_count": report.ready_for_review_count,
        "needs_verification_count": report.needs_verification_count,
        "review_blocked_count": report.review_blocked_count,
```

- [x] **Step 4: Run freshness tests**

Run:

```bash
pytest tests/test_freshness_loop.py::test_freshness_loop_includes_review_readiness_counts tests/test_freshness_loop.py::test_freshness_loop_writes_clean_snapshot -v
```

Expected: PASS.

- [x] **Step 5: Checkpoint only if the worktree contains no unrelated changes**

Run:

```bash
devflow git status
```

If the dirty files are exactly intended for this task, run:

```bash
devflow git checkpoint --message "feat: add review readiness freshness counts" --yes
```

Expected: local checkpoint commit succeeds.

---

### Task 5: Add Operating-Layer Readiness Fields

**Files:**
- Modify: `src/devflow/control_room/operating_layer.py`
- Modify: `tests/test_operating_layer.py`

- [x] **Step 1: Add failing operating-layer assertions**

In `test_operating_layer_snapshot_json_is_read_only_contract`, add these assertions after the existing task assertions:

```python
    assert payload["tasks"][0]["review_state"] == "not_ready"
    assert payload["tasks"][0]["review_score"] == 10
    assert payload["tasks"][0]["review_blockers"] == ["no reviewable task output was found"]
    assert payload["tasks"][0]["review_next_command"] == "devflow task show task-0001"
    assert ".devflow/tasks/task-0001/task.yaml" in payload["tasks"][0]["review_evidence"]
```

In `test_operating_layer_groups_verification_and_promotion_lanes`, add these assertions after `snapshot.tasks[0].next_action.command`:

```python
    assert snapshot.tasks[0].review_state == "needs_verification"
    assert snapshot.tasks[0].review_score == 60
    assert snapshot.tasks[0].review_blockers == ["verification has not passed"]
    assert snapshot.tasks[0].review_next_command == 'devflow task verify task-0001 --shell "<command>"'
```

- [x] **Step 2: Run the operating-layer tests and verify they fail**

Run:

```bash
pytest tests/test_operating_layer.py::test_operating_layer_snapshot_json_is_read_only_contract tests/test_operating_layer.py::test_operating_layer_groups_verification_and_promotion_lanes -v
```

Expected: FAIL because `OperatingLayerTask` does not expose the review readiness fields.

- [x] **Step 3: Wire the shared projection into `operating_layer.py`**

Add the import:

```python
from devflow.control_room.review_readiness import build_review_readiness_projection
```

Add fields to `OperatingLayerTask`:

```python
    review_state: str = "not_ready"
    review_score: int = 0
    review_blockers: list[str] = Field(default_factory=list)
    review_next_command: str | None = None
    review_evidence: list[str] = Field(default_factory=list)
```

In `_task_card`, compute readiness after `next_action` is scoped:

```python
    review_readiness = build_review_readiness_projection(
        root,
        task.id,
        task=task,
        status_projection=projection,
        project_id=project_id,
    )
```

Add these arguments to the `OperatingLayerTask(...)` constructor:

```python
        review_state=review_readiness.review_state,
        review_score=review_readiness.score,
        review_blockers=review_readiness.blockers,
        review_next_command=review_readiness.next_command,
        review_evidence=review_readiness.evidence,
```

- [x] **Step 4: Run operating-layer tests**

Run:

```bash
pytest tests/test_operating_layer.py::test_operating_layer_snapshot_json_is_read_only_contract tests/test_operating_layer.py::test_operating_layer_groups_verification_and_promotion_lanes -v
```

Expected: PASS.

- [x] **Step 5: Checkpoint only if the worktree contains no unrelated changes**

Run:

```bash
devflow git status
```

If the dirty files are exactly intended for this task, run:

```bash
devflow git checkpoint --message "feat: surface review readiness in operating layer" --yes
```

Expected: local checkpoint commit succeeds.

---

### Task 6: Final Verification And Handoff

**Files:**
- Verify all files touched by Tasks 1-5.

- [x] **Step 1: Run focused verification**

Run:

```bash
pytest tests/test_review_readiness.py tests/test_freshness_loop.py::test_freshness_loop_includes_review_readiness_counts tests/test_operating_layer.py::test_operating_layer_snapshot_json_is_read_only_contract tests/test_operating_layer.py::test_operating_layer_groups_verification_and_promotion_lanes -v
```

Expected: PASS.

- [x] **Step 2: Run adjacent regression tests**

Run:

```bash
pytest tests/test_status_projection.py tests/test_review_capsule.py tests/test_control_room_dashboard.py tests/test_freshness_loop.py tests/test_operating_layer.py -v
```

Expected: PASS.

- [x] **Step 3: Verify scorecard command output manually**

Run:

```bash
devflow task review-ready --json
```

Expected: JSON object with `schema_version`, `total_tasks`, `ready_for_review_count`, `needs_verification_count`, `review_blocked_count`, `counts`, and `tasks`.

- [x] **Step 4: Confirm checkpoint safety**

Run:

```bash
devflow git status
```

Expected: either clean after previous checkpoints, or dirty only with the intended review-readiness files.

If clean, no checkpoint is needed. If dirty only with intended review-readiness files, run:

```bash
devflow git checkpoint --message "feat: add review readiness scorecard" --yes
```

Expected: local checkpoint commit succeeds.

If unrelated dirty files are present, do not checkpoint. Report the blocker and list the unrelated paths.

- [x] **Step 5: Final handoff**

Use this format:

```markdown
## Status

complete

## Files Changed

- src/devflow/control_room/review_readiness.py (read-only review readiness projection)
- src/devflow/cli.py (task review-ready command and project-aware capsule command)
- src/devflow/control_room/freshness.py (aggregate readiness counts)
- src/devflow/control_room/operating_layer.py (snapshot readiness fields)
- tests/test_review_readiness.py (projection and CLI tests)
- tests/test_freshness_loop.py (freshness aggregate tests)
- tests/test_operating_layer.py (snapshot field tests)

## Verification

- `pytest tests/test_review_readiness.py tests/test_freshness_loop.py::test_freshness_loop_includes_review_readiness_counts tests/test_operating_layer.py::test_operating_layer_snapshot_json_is_read_only_contract tests/test_operating_layer.py::test_operating_layer_groups_verification_and_promotion_lanes -v`: pass
- `pytest tests/test_status_projection.py tests/test_review_capsule.py tests/test_control_room_dashboard.py tests/test_freshness_loop.py tests/test_operating_layer.py -v`: pass
- `devflow task review-ready --json`: pass

## Risks

- The scorecard is a readiness signal only; it does not approve promotion.
- `devflow git checkpoint --yes` stages every unignored dirty file, so checkpointing must wait if unrelated dirty files remain.

## Next Safe Action

- Use `devflow task review-ready --json` to inspect active review readiness, then choose one ready task and run `devflow task capsule <task_id>` for human review.
```
