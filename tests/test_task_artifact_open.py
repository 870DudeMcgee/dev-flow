from __future__ import annotations

import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from devflow.legacy.control_room.service import create_task
from devflow.legacy.control_room.task_artifact_open import (
    TaskArtifactOpenError,
    open_task_artifact,
    render_task_open_candidates,
    select_task_open_artifact,
)


def test_selects_best_general_response_candidate(tmp_path: Path) -> None:
    task = create_task(tmp_path, "general response")
    workspace = tmp_path / ".devflow" / "workspaces" / task.id
    (workspace / "gemma-review.md").write_text("review", encoding="utf-8")
    (workspace / "qwen-response.md").write_text("response", encoding="utf-8")

    selection = select_task_open_artifact(tmp_path, task.id)

    assert selection.selected is not None
    assert selection.selected.relative_path == Path("qwen-response.md")
    assert render_task_open_candidates(selection) == [
        "Candidate output files in priority order:",
        "1. qwen-response.md",
        "2. gemma-review.md",
    ]


def test_worker_preference_and_raw_preference(tmp_path: Path) -> None:
    task = create_task(tmp_path, "worker response")
    workspace = tmp_path / ".devflow" / "workspaces" / task.id
    (workspace / "qwen-response.md").write_text("general", encoding="utf-8")
    worker_dir = workspace / "local-workers" / "gemma-reviewer"
    worker_dir.mkdir(parents=True)
    (worker_dir / "response.md").write_text("formatted", encoding="utf-8")
    (worker_dir / "response.raw.md").write_text("raw", encoding="utf-8")

    formatted = select_task_open_artifact(tmp_path, task.id, worker="gemma-reviewer")
    raw = select_task_open_artifact(tmp_path, task.id, worker="gemma-reviewer", raw=True)

    assert formatted.selected is not None
    assert formatted.selected.relative_path == Path("local-workers/gemma-reviewer/response.md")
    assert raw.selected is not None
    assert raw.selected.relative_path == Path("local-workers/gemma-reviewer/response.raw.md")


def test_no_candidate_selection_renders_non_error_list_message(tmp_path: Path) -> None:
    task = create_task(tmp_path, "empty workspace")

    selection = select_task_open_artifact(tmp_path, task.id)

    assert selection.candidates == ()
    assert selection.selected is None
    assert render_task_open_candidates(selection) == ["No candidate files found."]


def test_missing_task_and_workspace_errors_match_cli_messages(tmp_path: Path) -> None:
    with pytest.raises(TaskArtifactOpenError, match=r"Task 'task-9999' not found\."):
        select_task_open_artifact(tmp_path, "task-9999")

    task = create_task(tmp_path, "missing workspace")
    shutil.rmtree(tmp_path / ".devflow" / "workspaces" / task.id)

    with pytest.raises(TaskArtifactOpenError) as exc:
        select_task_open_artifact(tmp_path, task.id)
    assert str(exc.value).startswith("Task workspace not found at ")


def test_symlink_escape_is_filtered_from_candidates(tmp_path: Path) -> None:
    task = create_task(tmp_path, "symlink escape")
    workspace = tmp_path / ".devflow" / "workspaces" / task.id
    outside_file = tmp_path / "outside.md"
    outside_file.write_text("outside", encoding="utf-8")
    try:
        (workspace / "outside_link.md").symlink_to(outside_file)
    except OSError as exc:
        pytest.skip(f"symlinks unavailable: {exc}")

    selection = select_task_open_artifact(tmp_path, task.id)

    assert selection.candidates == ()
    assert selection.selected is None


def test_open_task_artifact_uses_platform_opener(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    artifact = tmp_path / "response.md"
    artifact.write_text("response", encoding="utf-8")
    monkeypatch.setattr("devflow.legacy.control_room.task_artifact_open.sys.platform", "linux")

    with patch("devflow.legacy.control_room.task_artifact_open.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)

        assert open_task_artifact(artifact) is True

    mock_run.assert_called_once_with(["xdg-open", str(artifact)], check=True)


def test_open_task_artifact_returns_false_on_open_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "response.md"
    artifact.write_text("response", encoding="utf-8")
    monkeypatch.setattr("devflow.legacy.control_room.task_artifact_open.sys.platform", "linux")

    with patch("devflow.legacy.control_room.task_artifact_open.subprocess.run", side_effect=Exception("boom")):
        assert open_task_artifact(artifact) is False
