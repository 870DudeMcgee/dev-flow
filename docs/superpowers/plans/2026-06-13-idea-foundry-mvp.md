# Idea Foundry MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a local-first Idea Foundry intake queue with capture, list, show, classify, promote-decision, and archive commands.

**Architecture:** Add a focused `idea_foundry.py` service under `src/devflow/control_room/` that mirrors the existing Knowledge Foundry pattern while storing project-local idea evidence under `.devflow/ideas/`. Wire a new Typer `idea` command group in `src/devflow/cli.py`, update supervisor classification, and align active docs only after tests prove behavior.

**Tech Stack:** Python 3, Typer CLI, JSON metadata, Markdown evidence files, JSONL event logs, pytest, existing Dev-Flow atomic write helpers.

---

## Working Rules

- Start from a clean, synchronized repo. Run `PYTHONPATH=src:. .venv/bin/devflow git status` before edits.
- Do not edit `src/devflow/_legacy/`.
- Use TDD: write failing tests before production code for each behavior.
- Keep all new product code under `src/devflow/control_room/` plus CLI wiring in `src/devflow/cli.py`.
- Do not implement provider calls, model classification, automatic goal creation, automatic task creation, dashboard changes, databases, vector search, or background routing.
- Use `apply_patch` for manual edits.
- Use Dev-Flow Git bridge commands for checkpointing.

## File Structure

- Modify: `src/devflow/control_room/paths.py`
  - Add `ideas_dir(root: Path) -> Path`.
- Create: `src/devflow/control_room/idea_foundry.py`
  - Own idea metadata, evidence files, events, state transitions, renderers, and validation.
- Modify: `src/devflow/cli.py`
  - Add `idea_app`.
  - Add `capture`, `list`, `show`, `classify`, `promote`, and `archive` commands.
- Modify: `src/devflow/control_room/supervisor_surface.py`
  - Add read-only and approval-required idea command classifications.
- Create: `tests/test_idea_foundry.py`
  - Service and CLI coverage for the first vertical slice.
- Modify: `tests/test_supervisor_operating_surface.py`
  - Supervisor classification coverage for idea commands.
- Modify docs after behavior is green:
  - `README.md`
  - `docs/control-room-mvp.md`
  - `docs/mvp-contract.md`
  - `docs/roadmap.md`
  - `docs/architecture/patch-evidence-ladder.md`

## Task 1: Add Service Tests For Idea Evidence

**Files:**
- Create: `tests/test_idea_foundry.py`

- [ ] **Step 1: Write failing capture/list/show/classify/promote/archive tests**

Create `tests/test_idea_foundry.py` with this initial content:

```python
from __future__ import annotations

import os
from pathlib import Path

from typer.testing import CliRunner

from devflow.cli import app
from devflow.control_room.idea_foundry import (
    IdeaFoundryError,
    archive_idea,
    capture_idea,
    classify_idea,
    list_ideas,
    promote_idea,
    show_idea,
)


runner = CliRunner()


def test_capture_creates_inbox_idea_with_raw_evidence(tmp_path: Path) -> None:
    item = capture_idea(
        tmp_path,
        "Build an intake queue for rough ideas before they become tasks.",
        title="Idea intake queue",
        source="chat",
        tags=["planning"],
    )

    assert item["schema_version"] == 1
    assert item["id"] == "I-0001"
    assert item["title"] == "Idea intake queue"
    assert item["status"] == "inbox"
    assert item["maturity"] == "spark"
    assert item["source"] == "chat"
    assert item["tags"] == ["planning"]
    idea_dir = tmp_path / ".devflow" / "ideas" / item["id"]
    assert (idea_dir / "idea.json").exists()
    assert (idea_dir / "raw.md").read_text(encoding="utf-8").startswith(
        "Build an intake queue"
    )
    assert '"event": "created"' in (idea_dir / "events.jsonl").read_text(encoding="utf-8")


def test_list_show_classify_promote_and_archive_idea(tmp_path: Path) -> None:
    item = capture_idea(tmp_path, "Turn release notes into a repeatable checklist.")

    listed = list_ideas(tmp_path)
    assert [entry["id"] for entry in listed] == [item["id"]]

    classified = classify_idea(
        tmp_path,
        item["id"],
        maturity="goal_ready",
        note="Worth shaping into a goal after release-readiness work.",
        tags=["release", "checklist"],
    )
    assert classified["status"] == "classified"
    assert classified["maturity"] == "goal_ready"
    assert classified["tags"] == ["release", "checklist"]

    shown, raw, classification, promotion = show_idea(tmp_path, item["id"])
    assert shown["id"] == item["id"]
    assert "release-readiness" in classification
    assert raw.startswith("Turn release notes")
    assert promotion == ""

    promoted = promote_idea(
        tmp_path,
        item["id"],
        target="goal",
        rationale="The idea is ready to become a reviewed goal brief.",
        title="Release notes checklist goal",
    )
    assert promoted["status"] == "promoted"
    assert promoted["promotion_target"] == "goal"
    assert not (tmp_path / ".devflow" / "goals").exists()
    assert not (tmp_path / ".devflow" / "tasks").exists()

    archived = archive_idea(tmp_path, item["id"], reason="Superseded by a written goal.")
    assert archived["status"] == "archived"
    assert (tmp_path / ".devflow" / "ideas" / item["id"] / "promotion.md").exists()
    assert (tmp_path / ".devflow" / "ideas" / item["id"] / "raw.md").exists()


def test_promote_requires_matching_maturity(tmp_path: Path) -> None:
    item = capture_idea(tmp_path, "This is only a loose concept.")
    classify_idea(tmp_path, item["id"], maturity="candidate", note="Not ready yet.")

    try:
        promote_idea(tmp_path, item["id"], target="goal", rationale="Too soon.")
    except IdeaFoundryError as exc:
        assert "goal_ready" in str(exc)
    else:
        raise AssertionError("expected promotion to fail")


def test_invalid_idea_id_fails_cleanly(tmp_path: Path) -> None:
    old_cwd = Path.cwd()
    try:
        os.chdir(tmp_path)
        result = runner.invoke(app, ["idea", "show", "../bad"])
    finally:
        os.chdir(old_cwd)

    assert result.exit_code == 1
    assert "Invalid idea id" in result.output
```

- [ ] **Step 2: Run tests and verify they fail for the missing module**

Run:

```bash
PYTHONPATH=src:. .venv/bin/pytest tests/test_idea_foundry.py -v
```

Expected: fail during collection with `ModuleNotFoundError: No module named 'devflow.control_room.idea_foundry'`.

## Task 2: Implement The Idea Foundry Service

**Files:**
- Modify: `src/devflow/control_room/paths.py`
- Create: `src/devflow/control_room/idea_foundry.py`
- Test: `tests/test_idea_foundry.py`

- [ ] **Step 1: Add the ideas path helper**

In `src/devflow/control_room/paths.py`, add this function after `knowledge_dir`:

```python
def ideas_dir(root: Path) -> Path:
    return devflow_dir(root) / "ideas"
```

- [ ] **Step 2: Implement `idea_foundry.py`**

Create `src/devflow/control_room/idea_foundry.py`:

```python
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from devflow.control_room.models import TASK_SCHEMA_VERSION
from devflow.control_room.paths import ideas_dir
from devflow.control_room.persistence import atomic_write_text, utc_now


ALLOWED_IDEA_STATUSES = {"inbox", "classified", "promoted", "archived"}
ALLOWED_IDEA_MATURITIES = {"spark", "concept", "candidate", "goal_ready", "task_ready"}
ALLOWED_PROMOTION_TARGETS = {"goal", "task"}


class IdeaFoundryError(ValueError):
    pass


def capture_idea(
    root: Path,
    text: str,
    *,
    title: str | None = None,
    source: str = "manual",
    tags: list[str] | None = None,
) -> dict[str, Any]:
    body = text.strip()
    if not body:
        raise IdeaFoundryError("Idea text cannot be empty.")
    idea_id = _next_idea_id(root)
    now = utc_now().isoformat()
    idea_title = (title or _derive_title(body)).strip()
    item = {
        "schema_version": TASK_SCHEMA_VERSION,
        "id": idea_id,
        "title": idea_title,
        "status": "inbox",
        "maturity": "spark",
        "tags": _clean_tags(tags or []),
        "source": source.strip() or "manual",
        "promotion_target": None,
        "created_at": now,
        "updated_at": now,
        "classified_at": None,
        "promoted_at": None,
        "archived_at": None,
        "raw_path": f".devflow/ideas/{idea_id}/raw.md",
        "classification_path": None,
        "promotion_path": None,
        "archive_reason": None,
    }
    item_dir = _idea_item_dir(root, idea_id)
    item_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_text(item_dir / "raw.md", body + "\n")
    _write_idea(root, item)
    _append_idea_event(root, idea_id, "created", {"created_at": now})
    return item


def list_ideas(root: Path, *, status: str | None = None) -> list[dict[str, Any]]:
    if status is not None and status not in ALLOWED_IDEA_STATUSES:
        raise IdeaFoundryError(f"Unsupported idea status: {status}")
    items = [_read_idea_file(path) for path in _idea_record_paths(root)]
    filtered = [item for item in items if item is not None]
    if status is not None:
        filtered = [item for item in filtered if item["status"] == status]
    return filtered


def show_idea(root: Path, idea_id: str) -> tuple[dict[str, Any], str, str, str]:
    metadata = _get_idea(root, idea_id)
    item_dir = _idea_item_dir(root, idea_id)
    raw = _read_optional_text(item_dir / "raw.md")
    classification = _read_optional_text(item_dir / "classification.md")
    promotion = _read_optional_text(item_dir / "promotion.md")
    return metadata, raw, classification, promotion


def classify_idea(
    root: Path,
    idea_id: str,
    *,
    maturity: str,
    note: str = "",
    tags: list[str] | None = None,
) -> dict[str, Any]:
    if maturity not in ALLOWED_IDEA_MATURITIES:
        raise IdeaFoundryError(f"Unsupported idea maturity: {maturity}")
    metadata = _get_idea(root, idea_id)
    if metadata["status"] == "archived":
        raise IdeaFoundryError(f"Archived idea cannot be classified: {idea_id}")
    now = utc_now().isoformat()
    metadata["status"] = "classified"
    metadata["maturity"] = maturity
    metadata["tags"] = _clean_tags(tags or metadata.get("tags") or [])
    metadata["updated_at"] = now
    metadata["classified_at"] = now
    metadata["classification_path"] = f".devflow/ideas/{idea_id}/classification.md"
    classification_note = _classification_note(metadata, note)
    atomic_write_text(_idea_item_dir(root, idea_id) / "classification.md", classification_note)
    _write_idea(root, metadata)
    _append_idea_event(root, idea_id, "classified", {"classified_at": now, "maturity": maturity})
    return metadata


def promote_idea(
    root: Path,
    idea_id: str,
    *,
    target: str,
    rationale: str,
    title: str | None = None,
) -> dict[str, Any]:
    if target not in ALLOWED_PROMOTION_TARGETS:
        raise IdeaFoundryError(f"Unsupported promotion target: {target}")
    metadata = _get_idea(root, idea_id)
    if metadata["status"] == "archived":
        raise IdeaFoundryError(f"Archived idea cannot be promoted: {idea_id}")
    required_maturity = "goal_ready" if target == "goal" else "task_ready"
    if metadata["maturity"] != required_maturity:
        raise IdeaFoundryError(f"Promotion to {target} requires maturity {required_maturity}.")
    decision = rationale.strip()
    if not decision:
        raise IdeaFoundryError("Promotion rationale cannot be empty.")
    now = utc_now().isoformat()
    metadata["status"] = "promoted"
    metadata["promotion_target"] = target
    metadata["updated_at"] = now
    metadata["promoted_at"] = now
    metadata["promotion_path"] = f".devflow/ideas/{idea_id}/promotion.md"
    promotion_note = _promotion_note(metadata, target=target, rationale=decision, title=title)
    atomic_write_text(_idea_item_dir(root, idea_id) / "promotion.md", promotion_note)
    _write_idea(root, metadata)
    _append_idea_event(root, idea_id, "promoted", {"promoted_at": now, "target": target})
    return metadata


def archive_idea(root: Path, idea_id: str, *, reason: str) -> dict[str, Any]:
    metadata = _get_idea(root, idea_id)
    now = utc_now().isoformat()
    metadata["status"] = "archived"
    metadata["updated_at"] = now
    metadata["archived_at"] = now
    metadata["archive_reason"] = reason.strip() or "No reason supplied."
    _write_idea(root, metadata)
    _append_idea_event(root, idea_id, "archived", {"archived_at": now, "reason": metadata["archive_reason"]})
    return metadata


def render_idea_list(items: list[dict[str, Any]]) -> str:
    if not items:
        return "No ideas found.\n"
    lines = [f"{'ID':<8} {'Status':<11} {'Maturity':<11} Title", "-" * 84]
    for item in items:
        lines.append(f"{item['id']:<8} {item['status']:<11} {item['maturity']:<11} {item['title']}")
    return "\n".join(lines) + "\n"


def render_idea_show(metadata: dict[str, Any], raw: str, classification: str, promotion: str) -> str:
    lines = [
        f"id: {metadata['id']}",
        f"status: {metadata['status']}",
        f"maturity: {metadata['maturity']}",
        f"title: {metadata['title']}",
        f"source: {metadata['source']}",
        f"promotion_target: {metadata.get('promotion_target') or ''}",
        f"created_at: {metadata['created_at']}",
        f"updated_at: {metadata['updated_at']}",
        "tags:",
    ]
    for tag in metadata.get("tags") or []:
        lines.append(f"  - {tag}")
    lines.extend(["", "raw:", raw.rstrip() or "(empty)"])
    lines.extend(["", "classification:", classification.rstrip() or "(empty)"])
    lines.extend(["", "promotion:", promotion.rstrip() or "(empty)"])
    return "\n".join(lines) + "\n"


def _derive_title(text: str) -> str:
    first_line = text.splitlines()[0].strip()
    return first_line[:72] if first_line else "Untitled idea"


def _clean_tags(tags: list[str]) -> list[str]:
    cleaned: list[str] = []
    for tag in tags:
        value = tag.strip()
        if value and value not in cleaned:
            cleaned.append(value)
    return cleaned


def _classification_note(metadata: dict[str, Any], note: str) -> str:
    lines = [
        "# Idea Classification",
        "",
        f"- idea_id: {metadata['id']}",
        f"- maturity: {metadata['maturity']}",
        "- tags:",
    ]
    lines.extend(f"  - {tag}" for tag in metadata.get("tags") or [])
    lines.extend(["", "## Note", "", note.strip() or "No classification note supplied."])
    return "\n".join(lines) + "\n"


def _promotion_note(metadata: dict[str, Any], *, target: str, rationale: str, title: str | None) -> str:
    suggested_title = (title or metadata["title"]).strip()
    next_command = (
        f'devflow goal init "{suggested_title}"'
        if target == "goal"
        else f'devflow task create "{suggested_title}"'
    )
    lines = [
        "# Idea Promotion Decision",
        "",
        f"- idea_id: {metadata['id']}",
        f"- target: {target}",
        f"- title: {suggested_title}",
        "- created_goal: no",
        "- created_task: no",
        "",
        "## Rationale",
        "",
        rationale,
        "",
        "## Suggested Next Manual Command",
        "",
        f"`{next_command}`",
    ]
    return "\n".join(lines) + "\n"


def _next_idea_id(root: Path) -> str:
    existing: list[int] = []
    for path in _idea_record_paths(root):
        match = re.match(r"I-(\d{4})$", path.parent.name)
        if match:
            existing.append(int(match.group(1)))
    return f"I-{(max(existing) if existing else 0) + 1:04d}"


def _idea_record_paths(root: Path) -> list[Path]:
    base = ideas_dir(root)
    if not base.exists():
        return []
    return sorted(path / "idea.json" for path in base.iterdir() if path.is_dir() and (path / "idea.json").exists())


def _idea_item_dir(root: Path, idea_id: str) -> Path:
    if not re.match(r"^I-\d{4}$", idea_id):
        raise IdeaFoundryError(f"Invalid idea id: {idea_id}")
    return ideas_dir(root) / idea_id


def _get_idea(root: Path, idea_id: str) -> dict[str, Any]:
    path = _idea_item_dir(root, idea_id) / "idea.json"
    if not path.exists():
        raise IdeaFoundryError(f"Idea not found: {idea_id}")
    item = _read_idea_file(path)
    if item is None:
        raise IdeaFoundryError(f"Idea item is malformed: {idea_id}")
    return item


def _read_idea_file(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    if data.get("schema_version") != TASK_SCHEMA_VERSION:
        return None
    if data.get("status") not in ALLOWED_IDEA_STATUSES:
        return None
    if data.get("maturity") not in ALLOWED_IDEA_MATURITIES:
        return None
    return data


def _write_idea(root: Path, metadata: dict[str, Any]) -> None:
    item_dir = _idea_item_dir(root, metadata["id"])
    item_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_text(item_dir / "idea.json", json.dumps(metadata, indent=2, sort_keys=True) + "\n")


def _append_idea_event(root: Path, idea_id: str, event: str, payload: dict[str, Any]) -> None:
    item_dir = _idea_item_dir(root, idea_id)
    event_payload = {
        "timestamp": utc_now().isoformat(),
        "idea_id": idea_id,
        "event": event,
        **payload,
    }
    events_path = item_dir / "events.jsonl"
    events_path.parent.mkdir(parents=True, exist_ok=True)
    with events_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event_payload, sort_keys=True) + "\n")


def _read_optional_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""
```

- [ ] **Step 3: Run service tests and verify they pass**

Run:

```bash
PYTHONPATH=src:. .venv/bin/pytest tests/test_idea_foundry.py -v
```

Expected: the service-level tests pass; CLI tests that need command wiring may still fail until Task 3.

## Task 3: Wire The Typer CLI

**Files:**
- Modify: `src/devflow/cli.py`
- Test: `tests/test_idea_foundry.py`

- [ ] **Step 1: Add CLI tests**

Append these tests to `tests/test_idea_foundry.py`:

```python
def test_idea_cli_capture_list_show_classify_promote_archive(tmp_path: Path) -> None:
    old_cwd = Path.cwd()
    try:
        os.chdir(tmp_path)
        captured = runner.invoke(
            app,
            [
                "idea",
                "capture",
                "Make release readiness easier to repeat.",
                "--title",
                "Release readiness repeatability",
                "--source",
                "chat",
                "--tag",
                "release",
            ],
        )
        assert captured.exit_code == 0, captured.output
        idea_id = captured.output.split("idea_id:", 1)[1].strip().splitlines()[0]

        listed = runner.invoke(app, ["idea", "list"])
        shown = runner.invoke(app, ["idea", "show", idea_id])
        classified = runner.invoke(
            app,
            [
                "idea",
                "classify",
                idea_id,
                "--maturity",
                "goal_ready",
                "--note",
                "Ready to become a goal brief.",
                "--tag",
                "checklist",
            ],
        )
        promoted = runner.invoke(
            app,
            [
                "idea",
                "promote",
                idea_id,
                "--to",
                "goal",
                "--rationale",
                "Human reviewed and ready for goal shaping.",
            ],
        )
        archived = runner.invoke(app, ["idea", "archive", idea_id, "--reason", "Recorded in a goal brief."])
    finally:
        os.chdir(old_cwd)

    assert listed.exit_code == 0, listed.output
    assert idea_id in listed.output
    assert shown.exit_code == 0, shown.output
    assert "Release readiness repeatability" in shown.output
    assert classified.exit_code == 0, classified.output
    assert "status: classified" in classified.output
    assert promoted.exit_code == 0, promoted.output
    assert "created_goal: no" in promoted.output
    assert "created_task: no" in promoted.output
    assert archived.exit_code == 0, archived.output
    assert "status: archived" in archived.output
```

- [ ] **Step 2: Run the CLI test and verify it fails for missing command group**

Run:

```bash
PYTHONPATH=src:. .venv/bin/pytest tests/test_idea_foundry.py::test_idea_cli_capture_list_show_classify_promote_archive -v
```

Expected: fail because `idea` is not a registered command.

- [ ] **Step 3: Add the `idea_app` command group**

In `src/devflow/cli.py`, add the Typer app near the other app declarations:

```python
idea_app = typer.Typer(help="Capture and review raw ideas before they become goals or tasks")
```

Add it near the other `add_typer` calls:

```python
app.add_typer(idea_app, name="idea")
```

- [ ] **Step 4: Add CLI command functions**

Add these command functions near the Knowledge Foundry commands:

```python
@idea_app.command("capture")
def idea_capture(
    text: str,
    title: str | None = typer.Option(None, "--title", help="Optional title override."),
    source: str = typer.Option("manual", "--source", help="Source label for this idea."),
    tag: list[str] = typer.Option([], "--tag", help="Repeatable idea tag."),
) -> None:
    """Capture a raw idea as local, human-reviewed intake evidence."""
    try:
        from devflow.control_room.idea_foundry import IdeaFoundryError, capture_idea

        item = capture_idea(Path.cwd(), text, title=title, source=source, tags=tag)
    except IdeaFoundryError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"idea_id: {item['id']}")
    typer.echo(f"status: {item['status']}")
    typer.echo(f"maturity: {item['maturity']}")
    typer.echo(f"path: .devflow/ideas/{item['id']}/idea.json")
    typer.echo("created_goal: no")
    typer.echo("created_task: no")


@idea_app.command("list")
def idea_list(
    status: str | None = typer.Option(None, "--status", help="Filter by idea status."),
) -> None:
    """List local Idea Foundry items."""
    try:
        from devflow.control_room.idea_foundry import IdeaFoundryError, list_ideas, render_idea_list

        typer.echo(render_idea_list(list_ideas(Path.cwd(), status=status)), nl=False)
    except IdeaFoundryError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc


@idea_app.command("show")
def idea_show(idea_id: str) -> None:
    """Show one Idea Foundry item and its evidence notes."""
    try:
        from devflow.control_room.idea_foundry import IdeaFoundryError, render_idea_show, show_idea

        metadata, raw, classification, promotion = show_idea(Path.cwd(), idea_id)
    except IdeaFoundryError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(render_idea_show(metadata, raw, classification, promotion), nl=False)


@idea_app.command("classify")
def idea_classify(
    idea_id: str,
    maturity: str = typer.Option(..., "--maturity", help="spark, concept, candidate, goal_ready, or task_ready."),
    note: str = typer.Option("", "--note", help="Human classification note."),
    tag: list[str] = typer.Option([], "--tag", help="Repeatable replacement tag."),
) -> None:
    """Classify an idea with human-supplied maturity and tags."""
    try:
        from devflow.control_room.idea_foundry import IdeaFoundryError, classify_idea

        item = classify_idea(Path.cwd(), idea_id, maturity=maturity, note=note, tags=tag)
    except IdeaFoundryError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"idea_id: {item['id']}")
    typer.echo(f"status: {item['status']}")
    typer.echo(f"maturity: {item['maturity']}")
    typer.echo("model_called: no")


@idea_app.command("promote")
def idea_promote(
    idea_id: str,
    target: str = typer.Option(..., "--to", help="Promotion target: goal or task."),
    rationale: str = typer.Option(..., "--rationale", help="Human rationale for the promotion decision."),
    title: str | None = typer.Option(None, "--title", help="Optional suggested goal/task title."),
) -> None:
    """Record a human promotion decision without creating goals or tasks."""
    try:
        from devflow.control_room.idea_foundry import IdeaFoundryError, promote_idea

        item = promote_idea(Path.cwd(), idea_id, target=target, rationale=rationale, title=title)
    except IdeaFoundryError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"idea_id: {item['id']}")
    typer.echo(f"status: {item['status']}")
    typer.echo(f"promotion_target: {item['promotion_target']}")
    typer.echo("created_goal: no")
    typer.echo("created_task: no")


@idea_app.command("archive")
def idea_archive(
    idea_id: str,
    reason: str = typer.Option("No reason supplied.", "--reason", help="Human archive reason."),
) -> None:
    """Archive an idea while preserving its evidence."""
    try:
        from devflow.control_room.idea_foundry import IdeaFoundryError, archive_idea

        item = archive_idea(Path.cwd(), idea_id, reason=reason)
    except IdeaFoundryError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"idea_id: {item['id']}")
    typer.echo(f"status: {item['status']}")
    typer.echo("evidence_deleted: no")
```

- [ ] **Step 5: Run idea tests**

Run:

```bash
PYTHONPATH=src:. .venv/bin/pytest tests/test_idea_foundry.py -v
```

Expected: all idea tests pass.

## Task 4: Add Supervisor Classification

**Files:**
- Modify: `src/devflow/control_room/supervisor_surface.py`
- Modify: `tests/test_supervisor_operating_surface.py`

- [ ] **Step 1: Add failing supervisor tests**

In `tests/test_supervisor_operating_surface.py`, extend `test_evidence_writing_commands_are_not_pure_read_only` with:

```python
        "devflow idea capture rough idea",
        "devflow idea classify I-0001 --maturity goal_ready",
        "devflow idea promote I-0001 --to goal --rationale reviewed",
        "devflow idea archive I-0001 --reason superseded",
```

Add a focused read-only assertion near the supervisor packet/policy tests:

```python
def test_idea_read_only_commands_are_supervisor_safe() -> None:
    for command in (
        "devflow idea list",
        "devflow idea show I-0001",
    ):
        classification = classify_supervisor_command(command)
        assert classification["requires_human_approval"] is False
        assert classification["supervisor_may_auto_run"] is True
```

- [ ] **Step 2: Run supervisor tests and verify they fail**

Run:

```bash
PYTHONPATH=src:. .venv/bin/pytest tests/test_supervisor_operating_surface.py -v
```

Expected: fail because idea commands are not classified yet.

- [ ] **Step 3: Update supervisor command lists**

In `src/devflow/control_room/supervisor_surface.py`, add to `PURE_READ_ONLY_COMMANDS`:

```python
    "devflow idea list",
    "devflow idea show",
```

Add to `APPROVAL_REQUIRED_EVIDENCE_WRITING_COMMANDS`:

```python
    "devflow idea capture",
    "devflow idea classify",
    "devflow idea promote",
    "devflow idea archive",
```

In the operator-layer approval list, add `idea capture and review`.

- [ ] **Step 4: Run supervisor tests**

Run:

```bash
PYTHONPATH=src:. .venv/bin/pytest tests/test_supervisor_operating_surface.py -v
```

Expected: pass.

## Task 5: Align Active Docs

**Files:**
- Modify: `README.md`
- Modify: `docs/control-room-mvp.md`
- Modify: `docs/mvp-contract.md`
- Modify: `docs/roadmap.md`
- Modify: `docs/architecture/patch-evidence-ladder.md`

- [ ] **Step 1: Update stable command docs**

Add these commands to active stable command lists after Knowledge Foundry or Project Orientation entries:

```bash
devflow idea capture "raw idea"
devflow idea list
devflow idea show <idea_id>
devflow idea classify <idea_id> --maturity goal_ready
devflow idea promote <idea_id> --to goal --rationale "human reviewed"
devflow idea archive <idea_id> --reason "superseded"
```

- [ ] **Step 2: Add the Idea Foundry contract paragraph**

Use this paragraph in `docs/control-room-mvp.md` and `docs/mvp-contract.md`:

```markdown
The Idea Foundry form is `devflow idea capture/list/show/classify/promote/archive`. It stores project-local intake evidence under `.devflow/ideas/<idea_id>/`, keeps raw ideas separate from goals and tasks, and records human classification and promotion decisions. Idea promotion does not create goals, create tasks, run workers, call providers, verify, commit, push, or promote code; it only writes reviewable intake evidence and suggested next manual commands.
```

- [ ] **Step 3: Update roadmap status**

In `docs/roadmap.md`, change Milestone 12 status to:

```markdown
Status: implemented in the first local intake slice. Capture, list, show, classify, promote-decision, and archive commands are current; automatic goal/task creation remains out of scope.
```

Replace the next priority with the next safe follow-up:

```markdown
> [!IMPORTANT]
> **Next Priority**: Decide whether Idea Foundry should gain explicit `idea create-goal` / `idea create-task` commands or stay as decision evidence only. Do not add automatic creation, provider-backed classification, or routing without a new design.
```

- [ ] **Step 4: Update patch-evidence ladder**

Change the Idea Foundry section from future-only to current local intake. Keep automatic creation and provider classification deferred.

- [ ] **Step 5: Run stale-context search**

Run:

```bash
rg -n "Idea Foundry.*future|future idea commands|devflow idea.*do not exist|Milestone 12.*future|Next Priority.*Milestone 12 Idea Foundry MVP design" README.md docs/control-room-mvp.md docs/mvp-contract.md docs/roadmap.md docs/architecture/patch-evidence-ladder.md
```

Expected: no matches that describe the implemented command slice as future-only. Matches that explicitly keep automatic creation or provider classification future/deferred are acceptable.

## Task 6: Final Verification And Checkpoint

**Files:**
- All files touched by this implementation.

- [ ] **Step 1: Run focused tests**

Run:

```bash
PYTHONPATH=src:. .venv/bin/pytest tests/test_idea_foundry.py tests/test_supervisor_operating_surface.py -v
```

Expected: all selected tests pass.

- [ ] **Step 2: Run CLI help smoke checks**

Run:

```bash
PYTHONPATH=src:. .venv/bin/devflow idea --help
PYTHONPATH=src:. .venv/bin/devflow idea list
```

Expected: `idea --help` lists the six commands. `idea list` exits 0 and prints `No ideas found.` unless local idea evidence already exists.

- [ ] **Step 3: Run whitespace and stale-context checks**

Run:

```bash
git diff --check
rg -n "Idea Foundry.*future|future idea commands|devflow idea.*do not exist|Milestone 12.*future|Next Priority.*Milestone 12 Idea Foundry MVP design" README.md docs/control-room-mvp.md docs/mvp-contract.md docs/roadmap.md docs/architecture/patch-evidence-ladder.md
```

Expected: `git diff --check` exits 0. The stale-context search has no future-only matches for the implemented command slice.

- [ ] **Step 4: Inspect final diff**

Run:

```bash
git diff -- src/devflow/control_room/paths.py src/devflow/control_room/idea_foundry.py src/devflow/cli.py src/devflow/control_room/supervisor_surface.py tests/test_idea_foundry.py tests/test_supervisor_operating_surface.py README.md docs/control-room-mvp.md docs/mvp-contract.md docs/roadmap.md docs/architecture/patch-evidence-ladder.md
```

Expected: diff is limited to Idea Foundry service, CLI, supervisor classification, tests, and active docs.

- [ ] **Step 5: Checkpoint through Dev-Flow**

Run:

```bash
PYTHONPATH=src:. .venv/bin/devflow git status
PYTHONPATH=src:. .venv/bin/devflow git checkpoint --message "feat: add idea foundry intake" --yes
PYTHONPATH=src:. .venv/bin/devflow git status
```

Expected: checkpoint succeeds and final status is clean. Ask Josh before `PYTHONPATH=src:. .venv/bin/devflow push-main`.

## Handoff Template

Use this final response format:

```markdown
## Status

complete

## Files Changed

- src/devflow/control_room/paths.py (added ideas directory helper)
- src/devflow/control_room/idea_foundry.py (Idea Foundry service and renderers)
- src/devflow/cli.py (idea command group)
- src/devflow/control_room/supervisor_surface.py (idea command safety classification)
- tests/test_idea_foundry.py (service and CLI coverage)
- tests/test_supervisor_operating_surface.py (supervisor policy coverage)
- README.md (Idea Foundry stable-command alignment)
- docs/control-room-mvp.md (current behavior alignment)
- docs/mvp-contract.md (stable command contract alignment)
- docs/roadmap.md (Milestone 12 status and next priority)
- docs/architecture/patch-evidence-ladder.md (current Idea Foundry intake wording)

## Verification

- `PYTHONPATH=src:. .venv/bin/pytest tests/test_idea_foundry.py tests/test_supervisor_operating_surface.py -v`: pass/fail + summary
- `PYTHONPATH=src:. .venv/bin/devflow idea --help`: pass/fail + summary
- `PYTHONPATH=src:. .venv/bin/devflow idea list`: pass/fail + summary
- `git diff --check`: pass/fail + summary
- stale-context `rg`: pass/fail + summary
- `PYTHONPATH=src:. .venv/bin/devflow git status`: pass/fail + clean/ahead status

## Risks

- Note that `idea promote` records a decision but still creates no goals or tasks.
- Note whether the checkpoint is pushed or local.

## Next Safe Action

- Ask Josh before running `PYTHONPATH=src:. .venv/bin/devflow push-main`.
```
