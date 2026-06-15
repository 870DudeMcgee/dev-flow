from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from devflow.cli import app
from devflow.control_room.persistence import save_task
from devflow.control_room.question_resume import (
    answer_question,
    build_question_snapshot,
    resolve_question,
)
from devflow.control_room.service import create_task
from tests.helpers import setup_temp_git_repo


runner = CliRunner()


def _init_repo(tmp_path: Path, monkeypatch) -> None:
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)


def _write_agent_question(
    root: Path,
    task_id: str,
    *,
    question: str = "Which API shape should I preserve?",
) -> Path:
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
    assert answered.answer_path is not None
    assert (tmp_path / answered.answer_path).exists()
    mirror = tmp_path / ".devflow" / "tasks" / task.id / "question-answers" / f"{question.question_id}.json"
    assert mirror.exists()
    assert source.read_text(encoding="utf-8") == original_source
    events = (tmp_path / ".devflow" / "tasks" / task.id / "events.jsonl").read_text(encoding="utf-8")
    assert "question_answered" in events

    snapshot = build_question_snapshot(tmp_path)
    assert snapshot.counts["open"] == 0
    assert snapshot.counts["answered"] == 1


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
