# Idea-To-Execution Bridge Implementation Plan

Status: implemented in task-0023; retained as historical implementation evidence. Do not use this as the next active plan.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add explicit `devflow idea create-goal` and `devflow idea create-task` commands that convert human-promoted ideas into linked Dev-Flow goal or task state without running workers or promotion.

**Architecture:** Keep Idea Foundry as the source intake record and add a small bridge service under `src/devflow/control_room/` that composes existing goal and task creation APIs. The bridge validates prior idea promotion, writes bidirectional link evidence, updates idea metadata, and leaves execution, verification, promotion, commits, and pushes to existing explicit commands.

**Tech Stack:** Python 3, Typer CLI, pytest, JSON metadata, YAML link evidence, Markdown briefs, existing Dev-Flow goal/task services, existing atomic write helpers.

---

## Working Rules

- Start from a clean synchronized `main`: `PYTHONPATH=src:. .venv/bin/devflow git status`.
- Create a Dev-Flow Git worktree task before implementation: `PYTHONPATH=src:. .venv/bin/devflow task create --git-worktree "Implement Idea-To-Execution Bridge"`.
- Do not edit `src/devflow/_legacy/`.
- Keep new product code inside `src/devflow/control_room/` plus CLI wiring in `src/devflow/cli.py`.
- Use TDD for each behavior: failing test, minimal code, passing test.
- Use `apply_patch` for manual edits.
- Do not add provider calls, model classification, autonomous routing, worker execution, verification execution, promotion automation, database state, or remote APIs.
- Checkpoint through Dev-Flow commands, not raw push or direct promotion.

## File Structure

- Modify: `src/devflow/control_room/idea_foundry.py`
  - Add optional creation metadata defaults for new captures.
  - Add a public helper to record created goal/task links and append creation events.
- Create: `src/devflow/control_room/idea_execution_bridge.py`
  - Validate idea promotion preconditions.
  - Render goal and task briefs.
  - Create linked goals and tasks through existing services.
  - Provide dry-run previews.
- Modify: `src/devflow/cli.py`
  - Add `idea create-goal` and `idea create-task` commands.
- Modify: `src/devflow/control_room/supervisor_surface.py`
  - Classify dry-run bridge commands as read-only and actual creation as approval-required task state.
- Create: `tests/test_idea_execution_bridge.py`
  - Service-level coverage for bridge preconditions, writes, dry-run behavior, and non-execution guarantees.
- Modify: `tests/test_idea_foundry.py`
  - CLI coverage for new idea commands and `idea show` created refs.
- Modify: `tests/test_supervisor_operating_surface.py`
  - Supervisor classification coverage.
- Modify docs after behavior is green:
  - `README.md`
  - `docs/control-room-mvp.md`
  - `docs/mvp-contract.md`
  - `docs/roadmap.md`
  - `docs/architecture/patch-evidence-ladder.md`

## Task 1: Write Bridge Service Failing Tests

**Files:**
- Create: `tests/test_idea_execution_bridge.py`

- [ ] **Step 1: Add service tests**

Create `tests/test_idea_execution_bridge.py` with this content:

```python
from __future__ import annotations

from pathlib import Path

import yaml

from devflow.control_room.idea_execution_bridge import (
    IdeaExecutionBridgeError,
    create_goal_from_idea,
    create_task_from_idea,
    preview_goal_from_idea,
    preview_task_from_idea,
)
from devflow.control_room.idea_foundry import capture_idea, classify_idea, promote_idea, show_idea


def _promoted_goal_idea(root: Path) -> str:
    item = capture_idea(
        root,
        "Build a release gate that checks docs, tests, dogfood evidence, and stale context.",
        title="Release gate",
        tags=["release"],
    )
    classify_idea(root, item["id"], maturity="goal_ready", note="Ready to become a goal.", tags=["release"])
    promote_idea(root, item["id"], target="goal", rationale="This is broad enough to track as a goal.")
    return item["id"]


def _promoted_task_idea(root: Path) -> str:
    item = capture_idea(
        root,
        "Add a command that prints the latest release readiness report path.",
        title="Release readiness report path",
        tags=["release"],
    )
    classify_idea(root, item["id"], maturity="task_ready", note="Narrow task.", tags=["release"])
    promote_idea(root, item["id"], target="task", rationale="This is ready as one task.")
    return item["id"]


def test_create_goal_from_promoted_idea_links_both_sides(tmp_path: Path) -> None:
    idea_id = _promoted_goal_idea(tmp_path)

    created = create_goal_from_idea(tmp_path, idea_id)

    assert created.target == "goal"
    assert created.created_id == "G-0001"
    goal_dir = tmp_path / ".devflow" / "goals" / "G-0001"
    assert (goal_dir / "goal.yaml").exists()
    assert (goal_dir / "goal.md").exists()
    link = yaml.safe_load((goal_dir / "idea-link.yaml").read_text(encoding="utf-8"))
    assert link["idea_id"] == idea_id
    assert link["promotion_target"] == "goal"
    assert link["created_from_idea"] is True

    metadata, raw, classification, promotion = show_idea(tmp_path, idea_id)
    assert metadata["created_goal_id"] == "G-0001"
    assert metadata["created_goal_path"] == ".devflow/goals/G-0001"
    assert metadata["created_task_id"] is None
    assert "release gate" in raw.lower()
    assert "Ready to become a goal" in classification
    assert "target: goal" in promotion
    assert (tmp_path / ".devflow" / "ideas" / idea_id / "goal-brief.md").exists()
    assert not (tmp_path / ".devflow" / "tasks").exists()


def test_create_task_from_promoted_idea_creates_task_without_running_worker(tmp_path: Path) -> None:
    idea_id = _promoted_task_idea(tmp_path)

    created = create_task_from_idea(tmp_path, idea_id)

    assert created.target == "task"
    assert created.created_id == "task-0001"
    task_dir = tmp_path / ".devflow" / "tasks" / "task-0001"
    assert (task_dir / "task.yaml").exists()
    assert (task_dir / "idea.md").exists()
    link = yaml.safe_load((task_dir / "idea-link.yaml").read_text(encoding="utf-8"))
    assert link["idea_id"] == idea_id
    assert link["promotion_target"] == "task"
    assert link["created_from_idea"] is True

    task_yaml = yaml.safe_load((task_dir / "task.yaml").read_text(encoding="utf-8"))
    assert task_yaml["status"] == "created"
    assert task_yaml["verification_status"] == "not_run"
    assert (task_dir / "logs" / "worker.log").read_text(encoding="utf-8") == ""
    assert (task_dir / "logs" / "verify.log").read_text(encoding="utf-8") == ""

    metadata, _, _, _ = show_idea(tmp_path, idea_id)
    assert metadata["created_task_id"] == "task-0001"
    assert metadata["created_task_path"] == ".devflow/tasks/task-0001"
    assert metadata["created_goal_id"] is None


def test_bridge_refuses_missing_promotion_wrong_target_and_duplicates(tmp_path: Path) -> None:
    item = capture_idea(tmp_path, "Loose thought", title="Loose thought")
    classify_idea(tmp_path, item["id"], maturity="goal_ready", note="Maybe later.")

    try:
        create_goal_from_idea(tmp_path, item["id"])
    except IdeaExecutionBridgeError as exc:
        assert "must be promoted to goal" in str(exc)
    else:
        raise AssertionError("expected unpromoted idea to be refused")

    promote_idea(tmp_path, item["id"], target="goal", rationale="Now ready.")

    try:
        create_task_from_idea(tmp_path, item["id"])
    except IdeaExecutionBridgeError as exc:
        assert "not task" in str(exc)
    else:
        raise AssertionError("expected wrong target to be refused")

    create_goal_from_idea(tmp_path, item["id"])

    try:
        create_goal_from_idea(tmp_path, item["id"])
    except IdeaExecutionBridgeError as exc:
        assert "already created goal G-0001" in str(exc)
    else:
        raise AssertionError("expected duplicate goal creation to be refused")


def test_dry_run_previews_do_not_write(tmp_path: Path) -> None:
    goal_idea = _promoted_goal_idea(tmp_path)
    task_idea = _promoted_task_idea(tmp_path)
    before = sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*") if path.is_file())

    goal_preview = preview_goal_from_idea(tmp_path, goal_idea)
    task_preview = preview_task_from_idea(tmp_path, task_idea, git_worktree=True)
    after = sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*") if path.is_file())

    assert goal_preview.target == "goal"
    assert goal_preview.would_create is True
    assert goal_preview.created_id == "G-0001"
    assert task_preview.target == "task"
    assert task_preview.would_create is True
    assert task_preview.git_worktree is True
    assert task_preview.created_id == "task-0001"
    assert before == after
```

- [ ] **Step 2: Run the new test and verify the expected missing module failure**

Run:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_idea_execution_bridge.py -v
```

Expected: collection fails with `ModuleNotFoundError: No module named 'devflow.control_room.idea_execution_bridge'`.

## Task 2: Extend Idea Metadata Helpers

**Files:**
- Modify: `src/devflow/control_room/idea_foundry.py`
- Test: `tests/test_idea_execution_bridge.py`

- [ ] **Step 1: Add creation fields to new idea metadata**

In `capture_idea`, add these fields to the `item` dictionary immediately after `archive_reason`:

```python
        "created_goal_id": None,
        "created_goal_path": None,
        "created_task_id": None,
        "created_task_path": None,
        "created_from_idea_at": None,
        "creation_command": None,
```

- [ ] **Step 2: Add a public creation-recording helper**

Add this function near `archive_idea`:

```python
def record_idea_creation(
    root: Path,
    idea_id: str,
    *,
    target: str,
    created_id: str,
    created_path: str,
    command: str,
) -> dict[str, Any]:
    if target not in ALLOWED_PROMOTION_TARGETS:
        raise IdeaFoundryError(f"Unsupported creation target: {target}")
    metadata = _get_idea(root, idea_id)
    now = utc_now().isoformat()
    if target == "goal":
        metadata["created_goal_id"] = created_id
        metadata["created_goal_path"] = created_path
    else:
        metadata["created_task_id"] = created_id
        metadata["created_task_path"] = created_path
    metadata["created_from_idea_at"] = now
    metadata["creation_command"] = command
    metadata["updated_at"] = now
    _write_idea(root, metadata)
    _append_idea_event(
        root,
        idea_id,
        f"{target}_created",
        {"created_at": now, "created_id": created_id, "created_path": created_path},
    )
    return metadata
```

- [ ] **Step 3: Update `render_idea_show` to display created refs**

In the `lines` list inside `render_idea_show`, add these lines after `promotion_target`:

```python
        f"created_goal_id: {metadata.get('created_goal_id') or ''}",
        f"created_task_id: {metadata.get('created_task_id') or ''}",
```

- [ ] **Step 4: Run the new test and verify only the bridge module remains missing**

Run:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_idea_execution_bridge.py -v
```

Expected: collection still fails until the bridge module exists.

## Task 3: Implement The Bridge Service

**Files:**
- Create: `src/devflow/control_room/idea_execution_bridge.py`
- Test: `tests/test_idea_execution_bridge.py`

- [ ] **Step 1: Create the bridge module**

Create `src/devflow/control_room/idea_execution_bridge.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from devflow.control_room.goals import create_goal_from_markdown, next_goal_id
from devflow.control_room.idea_foundry import IdeaFoundryError, record_idea_creation, show_idea
from devflow.control_room.paths import goal_dir, ideas_dir, tasks_dir
from devflow.control_room.persistence import atomic_write_text
from devflow.control_room.service import create_task


class IdeaExecutionBridgeError(ValueError):
    pass


@dataclass(frozen=True)
class IdeaBridgePreview:
    idea_id: str
    target: str
    title: str
    would_create: bool
    created_id: str
    created_path: str
    link_path: str
    next_command: str
    git_worktree: bool = False


@dataclass(frozen=True)
class IdeaBridgeResult:
    idea_id: str
    target: str
    title: str
    created_id: str
    created_path: str
    link_path: str
    next_command: str
    git_worktree: bool = False


def preview_goal_from_idea(root: Path, idea_id: str, *, title: str | None = None, goal_id: str | None = None) -> IdeaBridgePreview:
    metadata, _, _, _ = _require_promoted_idea(root, idea_id, "goal")
    resolved_id = goal_id or next_goal_id(root)
    if goal_dir(root, resolved_id).exists():
        raise IdeaExecutionBridgeError(f"Goal already exists: {resolved_id}")
    resolved_title = (title or metadata["title"]).strip()
    return IdeaBridgePreview(
        idea_id=idea_id,
        target="goal",
        title=resolved_title,
        would_create=True,
        created_id=resolved_id,
        created_path=f".devflow/goals/{resolved_id}",
        link_path=f".devflow/goals/{resolved_id}/idea-link.yaml",
        next_command=f"devflow goal show {resolved_id}",
    )


def preview_task_from_idea(root: Path, idea_id: str, *, title: str | None = None, git_worktree: bool = False) -> IdeaBridgePreview:
    metadata, _, _, _ = _require_promoted_idea(root, idea_id, "task")
    resolved_id = _next_task_id_preview(root)
    resolved_title = (title or metadata["title"]).strip()
    return IdeaBridgePreview(
        idea_id=idea_id,
        target="task",
        title=resolved_title,
        would_create=True,
        created_id=resolved_id,
        created_path=f".devflow/tasks/{resolved_id}",
        link_path=f".devflow/tasks/{resolved_id}/idea-link.yaml",
        next_command=f"devflow task show {resolved_id}",
        git_worktree=git_worktree,
    )


def create_goal_from_idea(root: Path, idea_id: str, *, title: str | None = None, goal_id: str | None = None) -> IdeaBridgeResult:
    metadata, raw, classification, promotion = _require_promoted_idea(root, idea_id, "goal")
    preview = preview_goal_from_idea(root, idea_id, title=title, goal_id=goal_id)
    brief_path = ideas_dir(root) / idea_id / "goal-brief.md"
    atomic_write_text(brief_path, _goal_brief(metadata, raw, classification, promotion, preview.title))
    record = create_goal_from_markdown(root, brief_path, goal_id=preview.created_id)
    link_path = root / ".devflow" / "goals" / record.id / "idea-link.yaml"
    atomic_write_text(link_path, yaml.safe_dump(_idea_link(metadata, "goal"), sort_keys=False))
    command = f"devflow idea create-goal {idea_id}"
    record_idea_creation(root, idea_id, target="goal", created_id=record.id, created_path=preview.created_path, command=command)
    return IdeaBridgeResult(
        idea_id=idea_id,
        target="goal",
        title=preview.title,
        created_id=record.id,
        created_path=preview.created_path,
        link_path=preview.link_path,
        next_command=preview.next_command,
    )


def create_task_from_idea(root: Path, idea_id: str, *, title: str | None = None, git_worktree: bool = False) -> IdeaBridgeResult:
    metadata, raw, classification, promotion = _require_promoted_idea(root, idea_id, "task")
    preview = preview_task_from_idea(root, idea_id, title=title, git_worktree=git_worktree)
    task = create_task(root, preview.title, git_worktree=git_worktree)
    task_path = root / ".devflow" / "tasks" / task.id
    brief = _task_brief(metadata, raw, classification, promotion, preview.title)
    atomic_write_text(ideas_dir(root) / idea_id / "task-brief.md", brief)
    atomic_write_text(task_path / "idea.md", brief)
    atomic_write_text(task_path / "idea-link.yaml", yaml.safe_dump(_idea_link(metadata, "task"), sort_keys=False))
    command = f"devflow idea create-task {idea_id}"
    record_idea_creation(root, idea_id, target="task", created_id=task.id, created_path=f".devflow/tasks/{task.id}", command=command)
    return IdeaBridgeResult(
        idea_id=idea_id,
        target="task",
        title=preview.title,
        created_id=task.id,
        created_path=f".devflow/tasks/{task.id}",
        link_path=f".devflow/tasks/{task.id}/idea-link.yaml",
        next_command=f"devflow task show {task.id}",
        git_worktree=git_worktree,
    )


def _require_promoted_idea(root: Path, idea_id: str, target: str) -> tuple[dict[str, Any], str, str, str]:
    try:
        metadata, raw, classification, promotion = show_idea(root, idea_id)
    except IdeaFoundryError as exc:
        raise IdeaExecutionBridgeError(str(exc)) from exc
    if metadata["status"] == "archived":
        raise IdeaExecutionBridgeError("Archived idea cannot create a goal or task.")
    if metadata["status"] != "promoted":
        raise IdeaExecutionBridgeError(f"Idea must be promoted to {target} before creation.")
    if metadata.get("promotion_target") != target:
        raise IdeaExecutionBridgeError(f"Idea promotion target is {metadata.get('promotion_target')}, not {target}.")
    required_maturity = "goal_ready" if target == "goal" else "task_ready"
    if metadata.get("maturity") != required_maturity:
        raise IdeaExecutionBridgeError(f"Creation requires maturity {required_maturity}.")
    if target == "goal" and metadata.get("created_goal_id"):
        raise IdeaExecutionBridgeError(f"Idea already created goal {metadata['created_goal_id']}.")
    if target == "task" and metadata.get("created_task_id"):
        raise IdeaExecutionBridgeError(f"Idea already created task {metadata['created_task_id']}.")
    return metadata, raw, classification, promotion


def _idea_link(metadata: dict[str, Any], target: str) -> dict[str, Any]:
    idea_id = metadata["id"]
    return {
        "schema_version": 1,
        "idea_id": idea_id,
        "idea_path": f".devflow/ideas/{idea_id}",
        "promotion_target": target,
        "maturity": metadata["maturity"],
        "source_raw_path": f".devflow/ideas/{idea_id}/raw.md",
        "source_classification_path": f".devflow/ideas/{idea_id}/classification.md",
        "source_promotion_path": f".devflow/ideas/{idea_id}/promotion.md",
        "created_from_idea": True,
    }


def _goal_brief(metadata: dict[str, Any], raw: str, classification: str, promotion: str, title: str) -> str:
    return _source_brief("Goal", metadata, raw, classification, promotion, title)


def _task_brief(metadata: dict[str, Any], raw: str, classification: str, promotion: str, title: str) -> str:
    return _source_brief("Task", metadata, raw, classification, promotion, title)


def _source_brief(kind: str, metadata: dict[str, Any], raw: str, classification: str, promotion: str, title: str) -> str:
    return "\n".join(
        [
            f"# {kind} From Idea: {title}",
            "",
            f"- idea_id: {metadata['id']}",
            f"- maturity: {metadata['maturity']}",
            f"- promotion_target: {metadata.get('promotion_target')}",
            "",
            "## Raw Idea",
            "",
            raw.strip(),
            "",
            "## Classification",
            "",
            classification.strip() or "No classification note supplied.",
            "",
            "## Promotion Decision",
            "",
            promotion.strip() or "No promotion note supplied.",
            "",
        ]
    )


def _next_task_id_preview(root: Path) -> str:
    existing: list[int] = []
    base = tasks_dir(root)
    if base.exists():
        for path in base.iterdir():
            if path.is_dir() and path.name.startswith("task-"):
                try:
                    existing.append(int(path.name.removeprefix("task-")))
                except ValueError:
                    continue
    return f"task-{(max(existing) if existing else 0) + 1:04d}"
```

- [ ] **Step 2: Run service tests and fix narrow failures**

Run:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_idea_execution_bridge.py -v
```

Expected: pass once imports, helper names, and existing service APIs line up.

## Task 4: Add CLI Commands And CLI Tests

**Files:**
- Modify: `src/devflow/cli.py`
- Modify: `tests/test_idea_foundry.py`
- Test: `tests/test_idea_foundry.py`, `tests/test_idea_execution_bridge.py`

- [ ] **Step 1: Add CLI tests**

Append these tests to `tests/test_idea_foundry.py`:

```python
def test_cli_create_goal_from_promoted_idea(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["idea", "capture", "Build release gate", "--title", "Release gate"])
    runner.invoke(app, ["idea", "classify", "I-0001", "--maturity", "goal_ready", "--note", "Ready"])
    runner.invoke(app, ["idea", "promote", "I-0001", "--to", "goal", "--rationale", "Goal-sized"])

    result = runner.invoke(app, ["idea", "create-goal", "I-0001"])

    assert result.exit_code == 0
    assert "created_goal_id: G-0001" in result.output
    assert "next: devflow goal show G-0001" in result.output
    assert (tmp_path / ".devflow" / "goals" / "G-0001" / "idea-link.yaml").exists()


def test_cli_create_task_from_promoted_idea_and_show_refs(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["idea", "capture", "Add release report command", "--title", "Release report command"])
    runner.invoke(app, ["idea", "classify", "I-0001", "--maturity", "task_ready", "--note", "Task-sized"])
    runner.invoke(app, ["idea", "promote", "I-0001", "--to", "task", "--rationale", "Task-sized"])

    result = runner.invoke(app, ["idea", "create-task", "I-0001"])
    shown = runner.invoke(app, ["idea", "show", "I-0001"])

    assert result.exit_code == 0
    assert "created_task_id: task-0001" in result.output
    assert "next: devflow task show task-0001" in result.output
    assert "created_task_id: task-0001" in shown.output
    assert (tmp_path / ".devflow" / "tasks" / "task-0001" / "idea-link.yaml").exists()


def test_cli_create_dry_run_does_not_mutate(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["idea", "capture", "Build release gate", "--title", "Release gate"])
    runner.invoke(app, ["idea", "classify", "I-0001", "--maturity", "goal_ready", "--note", "Ready"])
    runner.invoke(app, ["idea", "promote", "I-0001", "--to", "goal", "--rationale", "Goal-sized"])
    before = sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*") if path.is_file())

    result = runner.invoke(app, ["idea", "create-goal", "I-0001", "--dry-run"])
    after = sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*") if path.is_file())

    assert result.exit_code == 0
    assert "would_create_goal: yes" in result.output
    assert "created_goal_id: G-0001" in result.output
    assert before == after
```

- [ ] **Step 2: Run CLI tests and verify missing command failure**

Run:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_idea_foundry.py::test_cli_create_goal_from_promoted_idea tests/test_idea_foundry.py::test_cli_create_task_from_promoted_idea_and_show_refs tests/test_idea_foundry.py::test_cli_create_dry_run_does_not_mutate -v
```

Expected: fail because `create-goal` and `create-task` are not wired.

- [ ] **Step 3: Wire `idea create-goal`**

Add this command after `idea_promote` in `src/devflow/cli.py`:

```python
@idea_app.command("create-goal")
def idea_create_goal(
    idea_id: str,
    title: str | None = typer.Option(None, "--title", help="Optional goal title override."),
    goal_id: str | None = typer.Option(None, "--goal-id", help="Optional explicit goal id."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without creating goal artifacts."),
) -> None:
    """Create a durable goal scaffold from a promoted goal-ready idea."""
    try:
        from devflow.control_room.idea_execution_bridge import (
            IdeaExecutionBridgeError,
            create_goal_from_idea,
            preview_goal_from_idea,
        )

        result = (
            preview_goal_from_idea(Path.cwd(), idea_id, title=title, goal_id=goal_id)
            if dry_run
            else create_goal_from_idea(Path.cwd(), idea_id, title=title, goal_id=goal_id)
        )
    except IdeaExecutionBridgeError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    if dry_run:
        typer.echo("would_create_goal: yes")
    typer.echo(f"idea_id: {result.idea_id}")
    typer.echo(f"created_goal_id: {result.created_id}")
    typer.echo(f"created_goal_path: {result.created_path}")
    typer.echo(f"link_path: {result.link_path}")
    typer.echo(f"next: {result.next_command}")
    typer.echo("worker_ran: no")
    typer.echo("verification_ran: no")
```

- [ ] **Step 4: Wire `idea create-task`**

Add this command after `idea_create_goal`:

```python
@idea_app.command("create-task")
def idea_create_task(
    idea_id: str,
    title: str | None = typer.Option(None, "--title", help="Optional task title override."),
    git_worktree: bool = typer.Option(False, "--git-worktree", help="Create the task with the existing Git-native worktree lane."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without creating task artifacts."),
) -> None:
    """Create a Dev-Flow task from a promoted task-ready idea."""
    try:
        from devflow.control_room.idea_execution_bridge import (
            IdeaExecutionBridgeError,
            create_task_from_idea,
            preview_task_from_idea,
        )

        result = (
            preview_task_from_idea(Path.cwd(), idea_id, title=title, git_worktree=git_worktree)
            if dry_run
            else create_task_from_idea(Path.cwd(), idea_id, title=title, git_worktree=git_worktree)
        )
    except IdeaExecutionBridgeError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    if dry_run:
        typer.echo("would_create_task: yes")
    typer.echo(f"idea_id: {result.idea_id}")
    typer.echo(f"created_task_id: {result.created_id}")
    typer.echo(f"created_task_path: {result.created_path}")
    typer.echo(f"link_path: {result.link_path}")
    typer.echo(f"git_worktree: {'yes' if result.git_worktree else 'no'}")
    typer.echo(f"next: {result.next_command}")
    typer.echo("worker_ran: no")
    typer.echo("verification_ran: no")
```

- [ ] **Step 5: Run focused CLI and service tests**

Run:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_idea_execution_bridge.py tests/test_idea_foundry.py -v
```

Expected: all Idea Foundry and bridge tests pass.

## Task 5: Update Supervisor Classification

**Files:**
- Modify: `src/devflow/control_room/supervisor_surface.py`
- Modify: `tests/test_supervisor_operating_surface.py`

- [ ] **Step 1: Add supervisor tests**

Update `tests/test_supervisor_operating_surface.py`:

```python
def test_idea_bridge_dry_run_commands_are_supervisor_safe() -> None:
    for command in (
        "devflow idea create-goal I-0001 --dry-run",
        "devflow idea create-task I-0001 --dry-run",
    ):
        classification = classify_supervisor_command(command)
        assert classification["safety_class"] == PURE_READ_ONLY
        assert classification["requires_human_approval"] is False
        assert classification["supervisor_may_auto_run"] is True


def test_idea_bridge_creation_commands_are_task_state_mutations() -> None:
    for command in (
        "devflow idea create-goal I-0001",
        "devflow idea create-task I-0001",
    ):
        classification = classify_supervisor_command(command)
        assert classification["safety_class"] == APPROVAL_REQUIRED_TASK_STATE
        assert classification["requires_human_approval"] is True
        assert classification["supervisor_may_auto_run"] is False
```

- [ ] **Step 2: Run the supervisor tests and verify they fail**

Run:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_supervisor_operating_surface.py::test_idea_bridge_dry_run_commands_are_supervisor_safe tests/test_supervisor_operating_surface.py::test_idea_bridge_creation_commands_are_task_state_mutations -v
```

Expected: fail until policy classification recognizes the new commands.

- [ ] **Step 3: Update supervisor policy lists**

In `src/devflow/control_room/supervisor_surface.py`, add:

```python
    "devflow idea create-goal --dry-run",
    "devflow idea create-task --dry-run",
```

to `PURE_READ_ONLY_COMMANDS`, and add:

```python
    "devflow idea create-goal",
    "devflow idea create-task",
```

to `APPROVAL_REQUIRED_TASK_STATE_COMMANDS`.

- [ ] **Step 4: Update command classifier branch**

In `_classify_supervisor_command`, update the `command_group == "idea"` branch so the logic is:

```python
    if command_group == "idea":
        if subcommand in {"list", "show"}:
            return PURE_READ_ONLY
        if subcommand in {"create-goal", "create-task"} and "--dry-run" in tokens:
            return PURE_READ_ONLY
        if subcommand in {"capture", "classify", "promote", "archive"}:
            return APPROVAL_REQUIRED_EVIDENCE_WRITING
        if subcommand in {"create-goal", "create-task"}:
            return APPROVAL_REQUIRED_TASK_STATE
        return FORBIDDEN_FOR_SUPERVISOR
```

- [ ] **Step 5: Run focused supervisor tests**

Run:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_supervisor_operating_surface.py -v
```

Expected: supervisor operating-surface tests pass.

## Task 6: Align Active Documentation

**Files:**
- Modify: `README.md`
- Modify: `docs/control-room-mvp.md`
- Modify: `docs/mvp-contract.md`
- Modify: `docs/roadmap.md`
- Modify: `docs/architecture/patch-evidence-ladder.md`

- [ ] **Step 1: Document current bridge behavior after tests are green**

Update stable command lists to include:

```bash
devflow idea create-goal <idea_id> --dry-run
devflow idea create-goal <idea_id>
devflow idea create-task <idea_id> --dry-run
devflow idea create-task <idea_id>
```

State that actual creation requires prior human promotion decision evidence and creates Dev-Flow state only.

- [ ] **Step 2: Keep non-goals explicit**

In each active doc touched, preserve this boundary:

```text
Idea creation commands do not run workers, call providers, verify, promote code, commit, push, open pull requests, or route models.
```

- [ ] **Step 3: Update roadmap status**

In `docs/roadmap.md`, mark Milestone 13 as implemented only after command behavior, tests, docs, and checkpoint are complete.

- [ ] **Step 4: Run stale-context scan**

Run:

```bash
rg -n "Idea Foundry should gain|idea create-goal.*future|idea create-task.*future|Current Priority.*Milestone 10|Milestone 13.*future-only" README.md docs/control-room-mvp.md docs/mvp-contract.md docs/roadmap.md docs/architecture/patch-evidence-ladder.md
```

Expected: no matches that describe implemented bridge commands as future-only or keep Milestone 10 as current priority. Matches in historical spec/plan files are acceptable only when they are clearly historical.

## Task 7: Final Verification, Checkpoint, And Handoff

**Files:**
- Modify or create a handoff under `docs/handoffs/`

- [ ] **Step 1: Run focused tests**

Run:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_idea_execution_bridge.py tests/test_idea_foundry.py tests/test_supervisor_operating_surface.py -v
```

Expected: all focused tests pass.

- [ ] **Step 2: Run CLI smoke checks**

Run:

```bash
PYTHONPATH=src:. .venv/bin/devflow idea --help
PYTHONPATH=src:. .venv/bin/devflow idea list
```

Expected: help lists `create-goal` and `create-task`; list still works on an empty idea queue.

- [ ] **Step 3: Run diff and stale-context verification**

Run:

```bash
git diff --check
rg -n "Idea Foundry should gain|idea create-goal.*future|idea create-task.*future|Current Priority.*Milestone 10|Milestone 13.*future-only" README.md docs/control-room-mvp.md docs/mvp-contract.md docs/roadmap.md docs/architecture/patch-evidence-ladder.md
```

Expected: `git diff --check` exits 0 and stale-context scan has no active-doc poison matches.

- [ ] **Step 4: Verify through Dev-Flow and finalize worker branch**

Run:

```bash
PYTHONPATH=src:. .venv/bin/devflow task verify <task_id> --shell 'PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_idea_execution_bridge.py tests/test_idea_foundry.py tests/test_supervisor_operating_surface.py -v' --timeout-seconds 120
PYTHONPATH=src:. .venv/bin/devflow task finalize <task_id> --commit
PYTHONPATH=src:. .venv/bin/devflow task promote-preview <task_id>
```

Expected: verification passes, finalization creates a worker branch commit, and promotion preview reports ready or a concrete repair action.

- [ ] **Step 5: Ask for promotion approval**

If preview is ready, ask Josh before running:

```bash
PYTHONPATH=src:. .venv/bin/devflow task promote <task_id>
```

Expected: no promotion without explicit human approval.

- [ ] **Step 6: Write final handoff**

Use `docs/handoff-template.md`. The next safe action must be one concrete command or approval request, not a broad backlog.
