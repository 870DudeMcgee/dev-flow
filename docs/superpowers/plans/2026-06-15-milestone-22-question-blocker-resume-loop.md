# Milestone 22 Question & Blocker Resume Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add first-class question listing, answering, resolving, and resume recommendations so human-blocked worker tasks can be recovered through explicit Dev-Flow commands.

**Architecture:** Create a focused `question_resume.py` projection/evidence module under `src/devflow/control_room/` that derives deterministic question ids from existing worker/freshness evidence and persists only human answer/resolve records. Add a minimal `devflow question` CLI bridge, then thread question state into scheduler, supervisor, operating-layer, dogfood, and active docs. Question commands must never run workers, verification, promotion, providers, or background schedulers.

**Tech Stack:** Python 3, Typer CLI, Pydantic models, JSON/JSONL filesystem artifacts, existing Dev-Flow task/scheduler/supervisor/operating-layer modules, pytest.

---

## File Structure

- Create `src/devflow/control_room/question_resume.py`: question scan, deterministic ids, answer/resolve writers, renderers.
- Modify `src/devflow/cli.py`: add `question` Typer app and command bridge.
- Modify `src/devflow/control_room/scheduler_projection.py`: consume question records instead of raw question lines for open blocker state.
- Modify `src/devflow/control_room/supervisor_surface.py`: classify question commands and include compact question summary/evidence.
- Modify `src/devflow/control_room/operating_layer.py`: use question records for snapshot questions and inbox commands.
- Modify `src/devflow/control_room/dogfood.py`: add `question-blocker-resume-loop` case and score totals.
- Create `tests/test_question_resume.py`: question projection, answer, resolve, and CLI tests.
- Modify `tests/test_scheduler_projection.py`: answered question no longer blocks scheduler.
- Modify `tests/test_supervisor_operating_surface.py`: supervisor question summary/classification assertions.
- Modify `tests/test_operating_layer.py`: operating-layer question id/resume command assertions.
- Modify `tests/test_dogfood_harness.py`: dogfood case count, totals, and focused question case.
- Modify `docs/control-room-mvp.md`, `docs/mvp-contract.md`, `docs/agent-handoff.md`, and `docs/roadmap.md`: active contract and milestone status.
- Add implementation handoff under `docs/handoffs/` at completion.

## Guardrails

- Keep implementation logic under `src/devflow/control_room/`.
- `src/devflow/cli.py` may only wire commands to control-room functions.
- `question list` and `question show` must be read-only.
- `question answer` and `question resolve` may write only `.devflow/questions/<question_id>.json`, `.devflow/tasks/<task_id>/question-answers/<question_id>.json`, and task events.
- Do not edit or truncate worker `questions.jsonl`.
- Do not change task status from question commands.
- Do not execute resume commands from question commands.
- Do not add provider calls, autonomous routing, browser mutation expansion, databases, auto-verification, auto-promotion, commits, pushes, or pull requests.

---

### Task 1: Add Question Resume Tests First

**Files:**
- Create: `tests/test_question_resume.py`
- Read as needed: `tests/test_manual_proof_agent.py`, `tests/test_scheduler_projection.py`

- [ ] **Step 1: Create test file with helper setup**

Create `tests/test_question_resume.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from devflow.cli import app
from devflow.control_room.persistence import create_task, get_task, save_task
from devflow.control_room.question_resume import (
    answer_question,
    build_question_snapshot,
    question_id_for_source,
    resolve_question,
)
from tests.helpers import setup_temp_git_repo


runner = CliRunner()


def _init_repo(tmp_path: Path, monkeypatch) -> None:
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)


def _write_agent_question(root: Path, task_id: str, *, question: str = "Which API shape should I preserve?") -> Path:
    agent_dir = root / ".devflow" / "tasks" / task_id / "agents" / "devflow-manual-codex-worker"
    agent_dir.mkdir(parents=True, exist_ok=True)
    path = agent_dir / "questions.jsonl"
    payload = {
        "type": "blocked_question",
        "task_id": task_id,
        "agent_id": "devflow-manual-codex-worker",
        "question": question,
        "blocking_reason": "Two public call sites disagree.",
        "required_decision": "Choose the API shape to preserve.",
    }
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    return path
```

- [ ] **Step 2: Add deterministic list/projection test**

Append:

```python
def test_question_snapshot_lists_open_worker_question_with_stable_id(tmp_path: Path, monkeypatch) -> None:
    _init_repo(tmp_path, monkeypatch)
    task = create_task(tmp_path, "blocked manual worker")
    task.status = "blocked"
    save_task(tmp_path / ".devflow" / "tasks" / task.id, task)
    question_path = _write_agent_question(tmp_path, task.id)

    snapshot = build_question_snapshot(tmp_path)
    payload = snapshot.model_dump(mode="json")

    assert payload["counts"]["open"] == 1
    question = payload["questions"][0]
    assert question["question_id"].startswith(f"Q-{task.id}-")
    assert question["status"] == "open"
    assert question["task_id"] == task.id
    assert question["agent_id"] == "devflow-manual-codex-worker"
    assert question["source_path"] == ".devflow/tasks/task-0001/agents/devflow-manual-codex-worker/questions.jsonl"
    assert question["source_line"] == 1
    assert question["recommended_resume_command"] == f"devflow task next-action {task.id}"
    assert question_path.read_text(encoding="utf-8").count("Which API shape") == 1
```

- [ ] **Step 3: Add answer persistence test**

Append:

```python
def test_answer_question_writes_answer_records_and_preserves_source(tmp_path: Path, monkeypatch) -> None:
    _init_repo(tmp_path, monkeypatch)
    task = create_task(tmp_path, "answerable blocker")
    source = _write_agent_question(tmp_path, task.id)
    original_source = source.read_text(encoding="utf-8")
    question = build_question_snapshot(tmp_path).questions[0]

    answered = answer_question(
        tmp_path,
        question.question_id,
        answer="Preserve the v2 API shape and add a compatibility shim.",
        resume_command=f"devflow task next-action {task.id}",
    )

    assert answered.status == "answered"
    assert answered.answer == "Preserve the v2 API shape and add a compatibility shim."
    assert (tmp_path / answered.answer_path).exists()
    mirror = tmp_path / ".devflow" / "tasks" / task.id / "question-answers" / f"{question.question_id}.json"
    assert mirror.exists()
    assert source.read_text(encoding="utf-8") == original_source
    events = (tmp_path / ".devflow" / "tasks" / task.id / "events.jsonl").read_text(encoding="utf-8")
    assert "question_answered" in events

    snapshot = build_question_snapshot(tmp_path)
    assert snapshot.counts["open"] == 0
    assert snapshot.counts["answered"] == 1
```

- [ ] **Step 4: Add resolve test**

Append:

```python
def test_resolve_question_marks_question_resolved_without_deleting_source(tmp_path: Path, monkeypatch) -> None:
    _init_repo(tmp_path, monkeypatch)
    task = create_task(tmp_path, "stale blocker")
    source = _write_agent_question(tmp_path, task.id, question="Is this still relevant?")
    question = build_question_snapshot(tmp_path).questions[0]

    resolved = resolve_question(tmp_path, question.question_id, reason="Question superseded by new task scope.")

    assert resolved.status == "resolved"
    assert resolved.resolved_reason == "Question superseded by new task scope."
    assert source.exists()
    events = (tmp_path / ".devflow" / "tasks" / task.id / "events.jsonl").read_text(encoding="utf-8")
    assert "question_resolved" in events
    snapshot = build_question_snapshot(tmp_path)
    assert snapshot.counts["open"] == 0
    assert snapshot.counts["resolved"] == 1
```

- [ ] **Step 5: Add CLI smoke test**

Append:

```python
def test_question_cli_list_show_answer_and_resolve_json(tmp_path: Path, monkeypatch) -> None:
    _init_repo(tmp_path, monkeypatch)
    task = create_task(tmp_path, "cli blocker")
    _write_agent_question(tmp_path, task.id)

    listed = runner.invoke(app, ["question", "list", "--json"])
    assert listed.exit_code == 0, listed.output
    listed_payload = json.loads(listed.output)
    question_id = listed_payload["questions"][0]["question_id"]

    shown = runner.invoke(app, ["question", "show", question_id, "--json"])
    assert shown.exit_code == 0, shown.output
    assert json.loads(shown.output)["question_id"] == question_id

    answered = runner.invoke(
        app,
        ["question", "answer", question_id, "--answer", "Use the existing API.", "--json"],
    )
    assert answered.exit_code == 0, answered.output
    assert json.loads(answered.output)["status"] == "answered"

    resolved = runner.invoke(
        app,
        ["question", "resolve", question_id, "--reason", "Answer recorded and acknowledged.", "--json"],
    )
    assert resolved.exit_code == 0, resolved.output
    assert json.loads(resolved.output)["status"] == "resolved"
```

- [ ] **Step 6: Run tests and confirm failure**

Run:

```bash
PYTHONPATH=src:. /Users/josh/Desktop/Dev-Flow/.venv/bin/python -m pytest tests/test_question_resume.py -q
```

Expected: import failure for `devflow.control_room.question_resume` and missing `question` CLI command.

- [ ] **Step 7: Commit the red tests if using task commits**

```bash
git add tests/test_question_resume.py
git commit -m "test: add question blocker resume expectations"
```

Expected: commit succeeds only inside the implementation task branch or explicit Dev-Flow-managed planning branch.

---

### Task 2: Implement `question_resume.py`

**Files:**
- Create: `src/devflow/control_room/question_resume.py`
- Test: `tests/test_question_resume.py`

- [ ] **Step 1: Add models, paths, and deterministic ids**

Create `src/devflow/control_room/question_resume.py`:

```python
from __future__ import annotations

import hashlib
import json
from datetime import timezone, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from devflow.control_room.paths import relative_path, task_dir
from devflow.control_room.persistence import atomic_write_text, list_tasks
from devflow.control_room.task_lifecycle import append_task_event


QuestionStatus = Literal["open", "answered", "resolved"]


class QuestionRecord(BaseModel):
    schema_version: int = 1
    question_id: str
    status: QuestionStatus
    task_id: str
    agent_id: str | None = None
    source_path: str
    source_line: int | None = None
    question: str
    blocking_reason: str | None = None
    required_decision: str | None = None
    answer: str | None = None
    answered_at: str | None = None
    resolved_at: str | None = None
    resolved_reason: str | None = None
    recommended_resume_command: str
    answer_path: str | None = None
    evidence_paths: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class QuestionSnapshot(BaseModel):
    schema_version: int = 1
    generated_at: str
    counts: dict[str, int]
    questions: list[QuestionRecord] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    evidence_paths: list[str] = Field(default_factory=list)
    next_safe_action: str


def question_id_for_source(
    *,
    task_id: str,
    agent_id: str | None,
    source_path: str,
    source_line: int | None,
    question: str,
) -> str:
    raw = f"{task_id}|{agent_id or ''}|{source_path}|{source_line or 0}|{question}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
    return f"Q-{task_id}-{digest}"
```

- [ ] **Step 2: Add read-only snapshot scanning**

Append:

```python
def build_question_snapshot(root: Path) -> QuestionSnapshot:
    root = root.resolve()
    source_questions, warnings, evidence_paths = _scan_source_questions(root)
    persisted = _read_persisted_questions(root)
    by_id = {question.question_id: question for question in source_questions}

    for question in persisted:
        existing = by_id.get(question.question_id)
        if existing is None:
            question.warnings.append("source question evidence is missing")
            by_id[question.question_id] = question
            continue
        merged = existing.model_copy(update=question.model_dump(exclude={"evidence_paths", "warnings"}))
        merged.evidence_paths = _dedupe([*existing.evidence_paths, *question.evidence_paths])
        merged.warnings = _dedupe([*existing.warnings, *question.warnings])
        by_id[question.question_id] = merged

    questions = sorted(by_id.values(), key=lambda item: (item.status != "open", item.task_id, item.question_id))
    counts = {"open": 0, "answered": 0, "resolved": 0}
    for question in questions:
        counts[question.status] = counts.get(question.status, 0) + 1

    next_action = "devflow task list"
    first_open = next((question for question in questions if question.status == "open"), None)
    if first_open is not None:
        next_action = f'devflow question answer {first_open.question_id} --answer "<answer>"'

    return QuestionSnapshot(
        generated_at=datetime.now(timezone.utc).isoformat(),
        counts=counts,
        questions=questions,
        warnings=warnings,
        evidence_paths=_dedupe(evidence_paths + [path for q in questions for path in q.evidence_paths]),
        next_safe_action=next_action,
    )
```

- [ ] **Step 3: Add source scanners**

Append:

```python
def _scan_source_questions(root: Path) -> tuple[list[QuestionRecord], list[str], list[str]]:
    questions: list[QuestionRecord] = []
    warnings: list[str] = []
    evidence_paths: list[str] = []
    for task in list_tasks(root):
        task_root = task_dir(root, task.id)
        candidates = [task_root / "questions.jsonl"]
        agents_dir = task_root / "agents"
        if agents_dir.exists():
            candidates.extend(sorted(agents_dir.glob("*/questions.jsonl")))
        for path in candidates:
            if not path.exists():
                continue
            rel = relative_path(root, path)
            evidence_paths.append(rel)
            for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                if not raw_line.strip():
                    continue
                payload = _parse_question_line(raw_line, rel, line_number, warnings)
                if payload is None:
                    continue
                question_text = str(payload["question"]).strip()
                agent_id = payload.get("agent_id")
                question_id = question_id_for_source(
                    task_id=task.id,
                    agent_id=str(agent_id) if agent_id else None,
                    source_path=rel,
                    source_line=line_number,
                    question=question_text,
                )
                questions.append(
                    QuestionRecord(
                        question_id=question_id,
                        status="open",
                        task_id=task.id,
                        agent_id=str(agent_id) if agent_id else None,
                        source_path=rel,
                        source_line=line_number,
                        question=question_text,
                        blocking_reason=_optional_text(payload.get("blocking_reason")),
                        required_decision=_optional_text(payload.get("required_decision")),
                        recommended_resume_command=f"devflow task next-action {task.id}",
                        evidence_paths=[rel],
                    )
                )
    return questions, warnings, evidence_paths


def _parse_question_line(raw_line: str, source_path: str, line_number: int, warnings: list[str]) -> dict[str, object] | None:
    try:
        payload = json.loads(raw_line)
    except json.JSONDecodeError as exc:
        warnings.append(f"{source_path}:{line_number}: invalid JSON ({exc.msg})")
        return None
    if not isinstance(payload, dict):
        warnings.append(f"{source_path}:{line_number}: expected JSON object")
        return None
    if payload.get("type") != "blocked_question":
        warnings.append(f"{source_path}:{line_number}: type must be blocked_question")
        return None
    if not isinstance(payload.get("question"), str) or not payload["question"].strip():
        warnings.append(f"{source_path}:{line_number}: question is required")
        return None
    return payload
```

- [ ] **Step 4: Add persisted record readers and writers**

Append:

```python
def answer_question(root: Path, question_id: str, *, answer: str, resume_command: str | None = None) -> QuestionRecord:
    clean_answer = answer.strip()
    if not clean_answer:
        raise ValueError("Answer is required.")
    question = _find_question(root, question_id)
    command = (resume_command or question.recommended_resume_command).strip()
    if not command.startswith("devflow "):
        raise ValueError("Resume command must be a devflow command.")
    now = datetime.now(timezone.utc).isoformat()
    updated = question.model_copy(
        update={
            "status": "answered",
            "answer": clean_answer,
            "answered_at": now,
            "recommended_resume_command": command,
        }
    )
    return _write_question_record(root, updated, "question_answered", {"answer_path": _record_relpath(question_id)})


def resolve_question(root: Path, question_id: str, *, reason: str) -> QuestionRecord:
    clean_reason = reason.strip()
    if not clean_reason:
        raise ValueError("Resolve reason is required.")
    question = _find_question(root, question_id)
    now = datetime.now(timezone.utc).isoformat()
    updated = question.model_copy(
        update={
            "status": "resolved",
            "resolved_at": now,
            "resolved_reason": clean_reason,
        }
    )
    return _write_question_record(root, updated, "question_resolved", {"reason": clean_reason})


def _find_question(root: Path, question_id: str) -> QuestionRecord:
    for question in build_question_snapshot(root).questions:
        if question.question_id == question_id:
            return question
    raise ValueError(f"Unknown question id: {question_id}")


def _write_question_record(root: Path, question: QuestionRecord, event_name: str, details: dict[str, str]) -> QuestionRecord:
    root = root.resolve()
    project_path = root / _record_relpath(question.question_id)
    mirror_path = task_dir(root, question.task_id) / "question-answers" / f"{question.question_id}.json"
    rel_project = relative_path(root, project_path)
    rel_mirror = relative_path(root, mirror_path)
    updated = question.model_copy(
        update={
            "answer_path": rel_project,
            "evidence_paths": _dedupe([*question.evidence_paths, rel_project, rel_mirror]),
        }
    )
    payload = updated.model_dump_json(indent=2) + "\n"
    atomic_write_text(project_path, payload)
    atomic_write_text(mirror_path, payload)
    append_task_event(root, question.task_id, event_name, {"question_id": question.question_id, **details})
    return updated
```

- [ ] **Step 5: Add helper functions and renderer**

Append:

```python
def render_question_snapshot(snapshot: QuestionSnapshot) -> str:
    lines = [
        f"open_questions: {snapshot.counts.get('open', 0)}",
        f"answered_questions: {snapshot.counts.get('answered', 0)}",
        f"resolved_questions: {snapshot.counts.get('resolved', 0)}",
        f"next_safe_action: {snapshot.next_safe_action}",
    ]
    open_questions = [question for question in snapshot.questions if question.status == "open"]
    if open_questions:
        lines.append("questions:")
        for question in open_questions:
            lines.append(f"  - {question.question_id}: {question.question}")
            lines.append(f"    task: {question.task_id}")
            lines.append(f"    answer: devflow question answer {question.question_id} --answer \"<answer>\"")
    if snapshot.warnings:
        lines.append("warnings:")
        for warning in snapshot.warnings:
            lines.append(f"  - {warning}")
    return "\n".join(lines) + "\n"


def _read_persisted_questions(root: Path) -> list[QuestionRecord]:
    question_dir = root / ".devflow" / "questions"
    if not question_dir.exists():
        return []
    records: list[QuestionRecord] = []
    for path in sorted(question_dir.glob("*.json")):
        try:
            records.append(QuestionRecord.model_validate_json(path.read_text(encoding="utf-8")))
        except ValueError:
            continue
    return records


def _record_relpath(question_id: str) -> str:
    return f".devflow/questions/{question_id}.json"


def _optional_text(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result
```

- [ ] **Step 6: Run focused tests**

Run:

```bash
PYTHONPATH=src:. /Users/josh/Desktop/Dev-Flow/.venv/bin/python -m pytest tests/test_question_resume.py -q
```

Expected: tests still fail only on missing CLI commands after module behavior exists.

- [ ] **Step 7: Commit module if using task commits**

```bash
git add src/devflow/control_room/question_resume.py tests/test_question_resume.py
git commit -m "feat: add question resume evidence model"
```

---

### Task 3: Add `devflow question` CLI and Supervisor Classification

**Files:**
- Modify: `src/devflow/cli.py`
- Modify: `src/devflow/control_room/supervisor_surface.py`
- Test: `tests/test_question_resume.py`, `tests/test_supervisor_operating_surface.py`

- [ ] **Step 1: Add CLI imports and Typer app**

In `src/devflow/cli.py`, add imports near other control-room imports:

```python
from devflow.control_room.question_resume import (
    answer_question,
    build_question_snapshot,
    render_question_snapshot,
    resolve_question,
)
```

Add app declaration near other app declarations:

```python
question_app = typer.Typer(help="List, answer, and resolve human-blocking worker questions.")
```

Register it near other top-level app registrations:

```python
app.add_typer(question_app, name="question")
```

- [ ] **Step 2: Add CLI command implementations**

Add near scheduler/freshness command groups:

```python
@question_app.command("list")
def question_list(json_output: bool = typer.Option(False, "--json")) -> None:
    snapshot = build_question_snapshot(Path.cwd())
    if json_output:
        typer.echo(snapshot.model_dump_json(indent=2))
        return
    typer.echo(render_question_snapshot(snapshot), nl=False)


@question_app.command("show")
def question_show(question_id: str, json_output: bool = typer.Option(False, "--json")) -> None:
    snapshot = build_question_snapshot(Path.cwd())
    question = next((item for item in snapshot.questions if item.question_id == question_id), None)
    if question is None:
        typer.echo(f"Unknown question id: {question_id}", err=True)
        raise typer.Exit(code=1)
    if json_output:
        typer.echo(question.model_dump_json(indent=2))
        return
    typer.echo(f"question: {question.question_id}")
    typer.echo(f"status: {question.status}")
    typer.echo(f"task: {question.task_id}")
    typer.echo(f"question_text: {question.question}")
    typer.echo(f"resume: {question.recommended_resume_command}")


@question_app.command("answer")
def question_answer(
    question_id: str,
    answer: str = typer.Option(..., "--answer"),
    resume_command: str | None = typer.Option(None, "--resume-command"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    try:
        question = answer_question(Path.cwd(), question_id, answer=answer, resume_command=resume_command)
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    if json_output:
        typer.echo(question.model_dump_json(indent=2))
        return
    typer.echo(f"question: {question.question_id}")
    typer.echo(f"status: {question.status}")
    typer.echo(f"answer_path: {question.answer_path}")
    typer.echo(f"next_safe_action: {question.recommended_resume_command}")


@question_app.command("resolve")
def question_resolve(
    question_id: str,
    reason: str = typer.Option(..., "--reason"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    try:
        question = resolve_question(Path.cwd(), question_id, reason=reason)
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    if json_output:
        typer.echo(question.model_dump_json(indent=2))
        return
    typer.echo(f"question: {question.question_id}")
    typer.echo(f"status: {question.status}")
    typer.echo(f"answer_path: {question.answer_path}")
```

- [ ] **Step 3: Add supervisor classification tests**

In `tests/test_supervisor_operating_surface.py`, add:

```python
def test_question_commands_are_classified_by_supervisor_policy() -> None:
    assert classify_supervisor_command("devflow question list") == PURE_READ_ONLY
    assert classify_supervisor_command("devflow question show Q-task-0001-abc123") == PURE_READ_ONLY
    assert classify_supervisor_command('devflow question answer Q-task-0001-abc123 --answer "Use v2"') == APPROVAL_REQUIRED_EVIDENCE_WRITING
    assert classify_supervisor_command('devflow question resolve Q-task-0001-abc123 --reason "stale"') == APPROVAL_REQUIRED_EVIDENCE_WRITING
```

- [ ] **Step 4: Implement supervisor command categories**

In `src/devflow/control_room/supervisor_surface.py`, add to `PURE_READ_ONLY_COMMANDS`:

```python
"devflow question list",
"devflow question show",
```

Add to `APPROVAL_REQUIRED_EVIDENCE_WRITING_COMMANDS`:

```python
"devflow question answer",
"devflow question resolve",
```

In `_classify_supervisor_command`, add:

```python
if command_group == "question":
    if subcommand in {"list", "show"}:
        return PURE_READ_ONLY
    if subcommand in {"answer", "resolve"}:
        return APPROVAL_REQUIRED_EVIDENCE_WRITING
    return FORBIDDEN_FOR_SUPERVISOR
```

- [ ] **Step 5: Run CLI and supervisor tests**

Run:

```bash
PYTHONPATH=src:. /Users/josh/Desktop/Dev-Flow/.venv/bin/python -m pytest tests/test_question_resume.py tests/test_supervisor_operating_surface.py::test_question_commands_are_classified_by_supervisor_policy -q
```

Expected: all selected tests pass.

- [ ] **Step 6: Commit CLI/supervisor changes if using task commits**

```bash
git add src/devflow/cli.py src/devflow/control_room/supervisor_surface.py tests/test_question_resume.py tests/test_supervisor_operating_surface.py
git commit -m "feat: add question command surface"
```

---

### Task 4: Integrate Questions with Scheduler and Operating Layer

**Files:**
- Modify: `src/devflow/control_room/scheduler_projection.py`
- Modify: `src/devflow/control_room/operating_layer.py`
- Modify: `tests/test_scheduler_projection.py`
- Modify: `tests/test_operating_layer.py`

- [ ] **Step 1: Add scheduler test for answered question**

In `tests/test_scheduler_projection.py`, add:

```python
def test_scheduler_uses_question_answers_to_clear_open_question_blocker(tmp_path: Path, monkeypatch) -> None:
    _init_goal(tmp_path, monkeypatch)
    create = runner.invoke(app, ["task", "create", "blocked question"])
    assert create.exit_code == 0, create.output
    task = _task(tmp_path, "task-0001")
    task.status = "blocked"
    save_task(tmp_path / ".devflow" / "tasks" / task.id, task)
    agent_dir = tmp_path / ".devflow" / "tasks" / task.id / "agents" / "devflow-manual-codex-worker"
    agent_dir.mkdir(parents=True, exist_ok=True)
    (agent_dir / "questions.jsonl").write_text(
        json.dumps(
            {
                "type": "blocked_question",
                "task_id": task.id,
                "agent_id": "devflow-manual-codex-worker",
                "question": "Which API should I preserve?",
                "blocking_reason": "Need human API decision.",
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    before = build_scheduler_snapshot(tmp_path)
    blocker = [item for item in before.tasks if item.task_id == task.id][0]
    assert blocker.scheduler_state == "blocked"
    assert blocker.next_safe_action.startswith("devflow question answer ")

    question_id = blocker.next_safe_action.split()[3]
    answer = runner.invoke(app, ["question", "answer", question_id, "--answer", "Preserve v2.", "--json"])
    assert answer.exit_code == 0, answer.output

    after = build_scheduler_snapshot(tmp_path)
    resumed = [item for item in after.tasks if item.task_id == task.id][0]
    assert resumed.scheduler_state != "blocked"
    assert resumed.next_safe_action == f"devflow task next-action {task.id}"
```

- [ ] **Step 2: Update scheduler projection to use question snapshot**

In `src/devflow/control_room/scheduler_projection.py`, import:

```python
from devflow.control_room.question_resume import build_question_snapshot
```

Change the raw question blocker path so `_task_blockers` receives open question records. The implementation should build a dict:

```python
open_questions_by_task = {
    question.task_id: question
    for question in build_question_snapshot(root).questions
    if question.status == "open"
}
```

When a task has an open question:

```python
blockers.append(question.question)
evidence.extend(question.evidence_paths)
next_safe_action = f'devflow question answer {question.question_id} --answer "<answer>"'
```

When source question evidence is answered or resolved, do not count it as an open scheduler blocker. Preserve answered/resolved evidence paths in `SchedulerTask.evidence_paths`.

- [ ] **Step 3: Add operating-layer test**

In `tests/test_operating_layer.py`, add:

```python
def test_operating_layer_questions_include_answer_command(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    created = runner.invoke(app, ["task", "create", "operator question"])
    assert created.exit_code == 0, created.output
    task = get_task(tmp_path, "task-0001")
    task.status = "blocked"
    save_task(tmp_path / ".devflow" / "tasks" / task.id, task)
    agent_dir = tmp_path / ".devflow" / "tasks" / task.id / "agents" / "devflow-manual-codex-worker"
    agent_dir.mkdir(parents=True, exist_ok=True)
    (agent_dir / "questions.jsonl").write_text(
        '{"type":"blocked_question","task_id":"task-0001","agent_id":"devflow-manual-codex-worker","question":"Which path should I use?"}\n',
        encoding="utf-8",
    )

    payload = build_operating_layer_snapshot(tmp_path).model_dump(mode="json")

    assert payload["questions"][0]["question_id"].startswith("Q-task-0001-")
    assert payload["questions"][0]["command"].startswith("devflow question answer ")
    assert payload["inbox"][0]["kind"] == "question"
```

- [ ] **Step 4: Extend operating-layer model and question builder**

In `src/devflow/control_room/operating_layer.py`, update `OperatingLayerQuestion`:

```python
class OperatingLayerQuestion(BaseModel):
    question_id: str
    task_id: str
    title: str
    question: str
    command: str
```

Import:

```python
from devflow.control_room.question_resume import build_question_snapshot
```

Change `_questions(...)` to call `build_question_snapshot(root)` or pass a precomputed snapshot from `build_operating_layer_snapshot`. For each open question, emit:

```python
OperatingLayerQuestion(
    question_id=question.question_id,
    task_id=question.task_id,
    title=task_titles.get(question.task_id, question.task_id),
    question=question.question,
    command=f'devflow question answer {question.question_id} --answer "<answer>"',
)
```

Change question inbox items to use the same command and question id.

- [ ] **Step 5: Run integration tests**

Run:

```bash
PYTHONPATH=src:. /Users/josh/Desktop/Dev-Flow/.venv/bin/python -m pytest tests/test_question_resume.py tests/test_scheduler_projection.py::test_scheduler_uses_question_answers_to_clear_open_question_blocker tests/test_operating_layer.py::test_operating_layer_questions_include_answer_command -q
```

Expected: all selected tests pass.

- [ ] **Step 6: Commit scheduler/operating-layer integration if using task commits**

```bash
git add src/devflow/control_room/scheduler_projection.py src/devflow/control_room/operating_layer.py tests/test_scheduler_projection.py tests/test_operating_layer.py
git commit -m "feat: surface answered questions in scheduler and operating layer"
```

---

### Task 5: Add Supervisor Packet Summary

**Files:**
- Modify: `src/devflow/control_room/supervisor_surface.py`
- Modify: `tests/test_supervisor_operating_surface.py`

- [ ] **Step 1: Add supervisor packet test**

In `tests/test_supervisor_operating_surface.py`, add:

```python
def test_question_summary_reaches_supervisor_packet(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    task = create_task(tmp_path, "supervisor question")
    agent_dir = tmp_path / ".devflow" / "tasks" / task.id / "agents" / "devflow-manual-codex-worker"
    agent_dir.mkdir(parents=True, exist_ok=True)
    (agent_dir / "questions.jsonl").write_text(
        '{"type":"blocked_question","task_id":"task-0001","agent_id":"devflow-manual-codex-worker","question":"Which branch should I inspect?"}\n',
        encoding="utf-8",
    )

    packet = _read_json(_invoke_read_only(tmp_path, ["supervisor", "packet", "--json"]))

    assert packet["questions"]["counts"]["open"] == 1
    assert packet["questions"]["next_safe_action"].startswith("devflow question answer Q-task-0001-")
    assert ".devflow/tasks/task-0001/agents/devflow-manual-codex-worker/questions.jsonl" in packet["evidence_paths"]
```

- [ ] **Step 2: Implement packet summary**

In `src/devflow/control_room/supervisor_surface.py`, import:

```python
from devflow.control_room.question_resume import build_question_snapshot
```

In `build_control_room_status`, add:

```python
questions = build_question_snapshot(root)
```

Add to the returned dict:

```python
"questions": {
    "counts": questions.counts,
    "next_safe_action": questions.next_safe_action,
},
```

In `build_supervisor_packet`, add the same compact `questions` dict and merge `questions.evidence_paths` into the existing evidence path list.

- [ ] **Step 3: Run supervisor tests**

Run:

```bash
PYTHONPATH=src:. /Users/josh/Desktop/Dev-Flow/.venv/bin/python -m pytest tests/test_supervisor_operating_surface.py::test_question_commands_are_classified_by_supervisor_policy tests/test_supervisor_operating_surface.py::test_question_summary_reaches_supervisor_packet -q
```

Expected: both tests pass.

- [ ] **Step 4: Commit supervisor summary if using task commits**

```bash
git add src/devflow/control_room/supervisor_surface.py tests/test_supervisor_operating_surface.py
git commit -m "feat: add question summary to supervisor packet"
```

---

### Task 6: Dogfood Question Resume Loop

**Files:**
- Modify: `src/devflow/control_room/dogfood.py`
- Modify: `tests/test_dogfood_harness.py`

- [ ] **Step 1: Add dogfood harness test**

In `tests/test_dogfood_harness.py`, update the suite-count assertions from the current count to the current count plus one and add:

```python
def test_question_blocker_resume_loop_dogfood_case(tmp_path: Path) -> None:
    _init_dogfood_repo(tmp_path)

    result = run_dogfood_suite(tmp_path, case_ids=["question-blocker-resume-loop"])
    case_result = result["results"][0]

    assert case_result["status"] == "passed"
    assert case_result["score"] == case_result["max_score"]
    assert any("question list exposed deterministic open blocker" in lesson for lesson in case_result["lessons"])
    assert any("answer preserved source question evidence" in lesson for lesson in case_result["lessons"])
    assert any("no worker resume or provider call was executed by question commands" in lesson for lesson in case_result["lessons"])
```

- [ ] **Step 2: Add dogfood case definition**

In `src/devflow/control_room/dogfood.py`, add one case to `production_readiness_cases()`:

```python
{
    "id": "question-blocker-resume-loop",
    "title": "Question blocker resume loop",
    "category": "E_recovery_failure_handling",
    "scoring": {"B_pipeline_correctness": 2, "D_worker_artifact_quality": 2, "E_recovery_failure_handling": 4},
    "description": "Exercise explicit question answer evidence without running workers or providers.",
}
```

Increase `CATEGORY_MAX` by the same points.

- [ ] **Step 3: Add dogfood runner**

Add a runner function:

```python
def _case_question_blocker_resume_loop(root: Path, run_dir: Path) -> DogfoodCaseResult:
    task = create_task(root, "question blocker dogfood")
    agent_dir = root / ".devflow" / "tasks" / task.id / "agents" / "devflow-manual-codex-worker"
    agent_dir.mkdir(parents=True, exist_ok=True)
    source = agent_dir / "questions.jsonl"
    source.write_text(
        '{"type":"blocked_question","task_id":"task-0001","agent_id":"devflow-manual-codex-worker","question":"Which API should I preserve?","blocking_reason":"Need human decision."}\n'
        "{bad json}\n",
        encoding="utf-8",
    )
    before = source.read_text(encoding="utf-8")
    snapshot = build_question_snapshot(root)
    question = snapshot.questions[0]
    answered = answer_question(root, question.question_id, answer="Preserve the stable API.")
    scheduler = build_scheduler_snapshot(root)
    after = source.read_text(encoding="utf-8")
    checks = [
        snapshot.counts["open"] == 1,
        bool(snapshot.warnings),
        answered.status == "answered",
        before == after,
        scheduler.counts.get("blocked", 0) == 0,
    ]
    status = "passed" if all(checks) else "failed"
    return DogfoodCaseResult(
        case_id="question-blocker-resume-loop",
        status=status,
        score=8 if status == "passed" else 0,
        max_score=8,
        commands_run=[],
        artifacts=[relative_path(root, Path(answered.answer_path or ""))],
        lessons=[
            "question list exposed deterministic open blocker",
            "answer preserved source question evidence",
            "no worker resume or provider call was executed by question commands",
        ],
    )
```

Adapt names to the existing dogfood result helpers if the file uses dictionaries instead of `DogfoodCaseResult`.

- [ ] **Step 4: Register dogfood runner**

Add to the runner registry:

```python
"question-blocker-resume-loop": _case_question_blocker_resume_loop,
```

- [ ] **Step 5: Run dogfood tests**

Run:

```bash
PYTHONPATH=src:. /Users/josh/Desktop/Dev-Flow/.venv/bin/python -m pytest tests/test_dogfood_harness.py::test_case_schema_and_suite_totals tests/test_dogfood_harness.py::test_question_blocker_resume_loop_dogfood_case -q
```

Expected: both tests pass.

- [ ] **Step 6: Commit dogfood changes if using task commits**

```bash
git add src/devflow/control_room/dogfood.py tests/test_dogfood_harness.py
git commit -m "test: dogfood question blocker resume loop"
```

---

### Task 7: Active Docs, Handoff, and Verification

**Files:**
- Modify: `docs/control-room-mvp.md`
- Modify: `docs/mvp-contract.md`
- Modify: `docs/agent-handoff.md`
- Modify: `docs/roadmap.md`
- Add: `docs/handoffs/2026-06-15-milestone-22-question-blocker-resume-loop-implementation.md`

- [ ] **Step 1: Update active docs**

Update docs to list stable commands:

```bash
devflow question list
devflow question list --json
devflow question show <question_id>
devflow question show <question_id> --json
devflow question answer <question_id> --answer "use the existing API"
devflow question resolve <question_id> --reason "superseded by updated scope"
```

Update current-priority text so Milestone 22 is implemented only after the code lands. During implementation, use this wording:

```text
Milestone 22 Question & Blocker Resume Loop is implemented in the active branch to make worker questions listable, answerable, resolvable, and visible to scheduler/supervisor/operating-layer projections without auto-resuming work.
```

- [ ] **Step 2: Add implementation handoff**

Create `docs/handoffs/2026-06-15-milestone-22-question-blocker-resume-loop-implementation.md` with the standard headings:

```markdown
## Status

needs-review

## Files Changed

- `src/devflow/control_room/question_resume.py` (question projection and answer/resolve evidence)
- `src/devflow/cli.py` (question command bridge)
- `src/devflow/control_room/scheduler_projection.py` (question-aware blocker/resume state)
- `src/devflow/control_room/supervisor_surface.py` (question summary and command classification)
- `src/devflow/control_room/operating_layer.py` (question ids and answer commands in snapshot/inbox)
- `src/devflow/control_room/dogfood.py` (question resume dogfood case)
- `tests/test_question_resume.py`, scheduler/supervisor/operating-layer/dogfood tests
- active docs and milestone handoff

## Verification

- `<focused pytest command>`: pass, `<actual output>`
- `PYTHONPATH=src:. /Users/josh/Desktop/Dev-Flow/.venv/bin/devflow dogfood run --suite production-readiness`: pass, `<actual score>`
- `PATH=/Users/josh/Desktop/Dev-Flow/.venv/bin:$PATH ./scripts/release-check.sh`: pass, `<actual output>`

## Risks

- None identified after verification.

## Next Safe Action

- `PYTHONPATH=src:. .venv/bin/devflow task promote-preview <task_id>`
```

Replace placeholders with actual command output before finalizing.

- [ ] **Step 3: Run focused suite**

Run:

```bash
PYTHONPATH=src:. /Users/josh/Desktop/Dev-Flow/.venv/bin/python -m pytest tests/test_question_resume.py tests/test_scheduler_projection.py tests/test_supervisor_operating_surface.py tests/test_operating_layer.py tests/test_dogfood_harness.py -q
```

Expected: all selected tests pass.

- [ ] **Step 4: Run production dogfood**

Run:

```bash
PYTHONPATH=src:. /Users/josh/Desktop/Dev-Flow/.venv/bin/devflow dogfood run --suite production-readiness
```

Expected: Silver threshold remains met or better.

- [ ] **Step 5: Run stale-context scan**

Run:

```bash
rg -n "question answering.*future-only|question resume.*later|Milestone 22.*planned next|auto-resume is active|provider-backed question execution|browser question answer mutation" docs README.md AGENTS.md -S
```

Expected: no active docs claim implemented question answering is still future-only. Historical plan/spec hits are acceptable when clearly non-authoritative.

- [ ] **Step 6: Finalize and verify release gate**

After focused tests and dogfood pass, finalize the task branch through Dev-Flow. Then run:

```bash
PATH=/Users/josh/Desktop/Dev-Flow/.venv/bin:$PATH ./scripts/release-check.sh
```

Expected: full suite, package build, twine check, and fresh wheel smoke pass.

- [ ] **Step 7: Promotion flow**

Run:

```bash
PYTHONPATH=src:. .venv/bin/devflow task promote-preview <task_id>
```

Expected: `conflict_prediction: clean`, `promotion_readiness: ready`.

After human approval, run:

```bash
PYTHONPATH=src:. .venv/bin/devflow task promote <task_id>
```

Expected: `Promotion complete`, main checkout changed, no staged leftovers.

- [ ] **Step 8: Final main verification**

Run on promoted `main`:

```bash
PATH=/Users/josh/Desktop/Dev-Flow/.venv/bin:$PATH ./scripts/release-check.sh
PYTHONPATH=src:. .venv/bin/devflow git status
```

Expected: release check passes; `main` is clean and ahead of origin until `devflow push-main` is explicitly approved.

---

## Final Handoff

When implementation is complete, final response must use:

```markdown
## Status

complete | needs-review | blocked | failed

## Files Changed

- path (summary)

## Verification

- `command`: pass/fail + actual output

## Risks

- concrete risks or `None identified`

## Next Safe Action

- one exact command
```

Do not push unless the human explicitly asks. The expected next safe action after a clean promoted main is:

```bash
PYTHONPATH=src:. .venv/bin/devflow push-main
```
