from __future__ import annotations

import json
import os
from pathlib import Path

from typer.testing import CliRunner

from devflow.cli import app
from devflow.control_room.knowledge_foundry import (
    capture_from_task,
    capture_from_validation,
    promote_knowledge,
    reject_knowledge,
    search_knowledge,
)
from devflow.control_room.service import create_task


runner = CliRunner()


def _validation_artifact(root: Path, task_id: str = "task-0001", status: str = "failed") -> Path:
    path = root / ".devflow" / "tasks" / task_id / "worker-outcome-validation.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "output_path": f".devflow/tasks/{task_id}/worker-outcome-validation.json",
                "status": status,
                "errors": ["files_touched '../outside.py': parent traversal is rejected"] if status == "failed" else [],
                "warnings": [],
                "created_at": "2026-06-02T00:00:00+00:00",
                "input_path": f".devflow/tasks/{task_id}/agents/shell/outcome.json",
                "input_task_id": task_id,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def test_capture_from_task_creates_proposed_knowledge_item(tmp_path: Path) -> None:
    task = create_task(tmp_path, "Capture reusable lesson")

    item = capture_from_task(tmp_path, task.id)

    assert item["schema_version"] == 1
    assert item["id"] == "K-0001"
    assert item["status"] == "proposed"
    assert item["source_task"] == task.id
    assert item["source_paths"]
    assert f".devflow/tasks/{task.id}/task.yaml" in item["source_paths"]
    note = (tmp_path / ".devflow" / "knowledge" / item["id"] / "note.md").read_text(encoding="utf-8")
    assert "TODO: A human should write the reusable lesson" in note
    assert "No lesson was inferred automatically" in note


def test_capture_from_nonexistent_task_fails_cleanly(tmp_path: Path) -> None:
    result = runner.invoke(app, ["knowledge", "capture", "--from-task", "task-missing"])

    assert result.exit_code == 1
    assert "Task not found" in result.output


def test_list_show_promote_reject_and_search(tmp_path: Path) -> None:
    task = create_task(tmp_path, "Verification workflow pattern")
    first = capture_from_task(tmp_path, task.id)
    second = capture_from_task(tmp_path, task.id)
    promoted = promote_knowledge(tmp_path, first["id"])
    rejected = reject_knowledge(tmp_path, second["id"])

    assert promoted["status"] == "promoted"
    assert promoted["source_paths"] == first["source_paths"]
    assert rejected["status"] == "rejected"
    assert rejected["source_paths"] == second["source_paths"]

    old_cwd = Path.cwd()
    try:
        os.chdir(tmp_path)
        listed = runner.invoke(app, ["knowledge", "list"])
        shown = runner.invoke(app, ["knowledge", "show", first["id"]])
        searched = runner.invoke(app, ["knowledge", "search", "workflow"])
    finally:
        os.chdir(old_cwd)

    assert listed.exit_code == 0, listed.output
    assert first["id"] in listed.output
    assert "promoted" in listed.output
    assert second["id"] in listed.output
    assert "rejected" in listed.output
    assert shown.exit_code == 0, shown.output
    assert "source_paths:" in shown.output
    assert "note:" in shown.output
    assert searched.exit_code == 0, searched.output
    assert first["id"] in searched.output


def test_invalid_knowledge_id_fails_cleanly(tmp_path: Path) -> None:
    create_task(tmp_path, "Invalid id")
    old_cwd = Path.cwd()
    try:
        os.chdir(tmp_path)
        result = runner.invoke(app, ["knowledge", "show", "../bad"])
    finally:
        os.chdir(old_cwd)

    assert result.exit_code == 1
    assert "Invalid knowledge id" in result.output


def test_capture_from_validation_artifact_creates_proposed_item(tmp_path: Path) -> None:
    task = create_task(tmp_path, "Validation capture")
    validation_path = _validation_artifact(tmp_path, task.id)

    item = capture_from_validation(tmp_path, validation_path)

    assert item["status"] == "proposed"
    assert item["type"] == "mistake"
    assert item["source_task"] == task.id
    assert item["source_paths"] == [f".devflow/tasks/{task.id}/worker-outcome-validation.json"]
    note = (tmp_path / ".devflow" / "knowledge" / item["id"] / "note.md").read_text(encoding="utf-8")
    assert "validation_errors" in note


def test_capture_from_validation_missing_artifact_fails(tmp_path: Path) -> None:
    result = runner.invoke(app, ["knowledge", "capture", "--from-validation", "missing.json"])

    assert result.exit_code == 1
    assert "Validation artifact not found" in result.output


def test_knowledge_commands_do_not_modify_task_yaml_or_promote_patches(tmp_path: Path) -> None:
    task = create_task(tmp_path, "No task mutation")
    task_yaml = tmp_path / ".devflow" / "tasks" / task.id / "task.yaml"
    before = task_yaml.read_text(encoding="utf-8")
    workspace_file = tmp_path / ".devflow" / "workspaces" / task.id / "result.txt"
    workspace_file.write_text("workspace only\n", encoding="utf-8")

    old_cwd = Path.cwd()
    try:
        os.chdir(tmp_path)
        captured = runner.invoke(app, ["knowledge", "capture", "--from-task", task.id])
        assert captured.exit_code == 0, captured.output
        knowledge_id = captured.output.split("knowledge_id:", 1)[1].strip().splitlines()[0]
        promoted = runner.invoke(app, ["knowledge", "promote", knowledge_id])
        rejected = runner.invoke(app, ["knowledge", "reject", knowledge_id])
    finally:
        os.chdir(old_cwd)

    assert promoted.exit_code == 0, promoted.output
    assert rejected.exit_code == 0, rejected.output
    assert task_yaml.read_text(encoding="utf-8") == before
    assert not (tmp_path / "result.txt").exists()
    assert workspace_file.exists()


def test_search_finds_text_in_note_title_and_tags(tmp_path: Path) -> None:
    task = create_task(tmp_path, "Git discipline lesson")
    item = capture_from_task(tmp_path, task.id)
    note_path = tmp_path / ".devflow" / "knowledge" / item["id"] / "note.md"
    note_path.write_text(note_path.read_text(encoding="utf-8") + "\nunique-review-token\n", encoding="utf-8")

    assert [match["id"] for match in search_knowledge(tmp_path, "unique-review-token")] == [item["id"]]
