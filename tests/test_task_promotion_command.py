from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from devflow.control_room.service import create_task, get_task, verify_task
from devflow.control_room.task_promotion_command import (
    TaskPromotionCommandError,
    TaskPromotionPreviewView,
    TaskPromotionRunView,
    build_task_promotion_preview_view,
    build_task_promotion_run_view,
    execute_task_promotion_run,
)
from tests.helpers import setup_temp_git_repo


def _git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=root, text=True).strip()


def _commit(root: Path, message: str, paths: list[str]) -> str:
    subprocess.run(["git", "add", *paths], cwd=root, check=True)
    subprocess.run(["git", "commit", "-m", message], cwd=root, check=True)
    return _git(root, "rev-parse", "HEAD")


def _commit_setup_docs(root: Path) -> None:
    docs_path = root / "docs" / "architecture.md"
    if docs_path.exists():
        _commit(root, "commit setup docs", ["docs/architecture.md"])


def test_preview_view_includes_baseline_next_action_changed_sections_and_diffs(tmp_path: Path) -> None:
    setup_temp_git_repo(tmp_path)
    (tmp_path / "modify.txt").write_text("old content\n", encoding="utf-8")
    (tmp_path / "delete.txt").write_text("delete me\n", encoding="utf-8")
    baseline = _commit(tmp_path, "add promotion fixtures", ["modify.txt", "delete.txt"])

    task = create_task(tmp_path, "preview module task")
    workspace = tmp_path / task.workspace
    (workspace / "added.txt").write_text("new file\n", encoding="utf-8")
    (workspace / "modify.txt").write_text("new content\n", encoding="utf-8")
    (workspace / "delete.txt").unlink()

    view = build_task_promotion_preview_view(tmp_path, task.id)
    output = "\n".join(view.lines)

    assert isinstance(view, TaskPromotionPreviewView)
    assert view.promotion_preview["task_id"] == task.id
    assert "preview_only: yes" in view.lines
    assert f"task_baseline_commit: {baseline}" in view.lines
    assert f"current_main_head: {baseline}" in view.lines
    assert "baseline_status: unchanged" in view.lines
    assert f"next_action: devflow task promote {task.id}" in view.lines
    assert "Added files:" in view.lines
    assert "  - added.txt" in view.lines
    assert "Modified files:" in view.lines
    assert "  - modify.txt" in view.lines
    assert "Deleted files:" in view.lines
    assert "  - delete.txt" in view.lines
    assert "--- Diffs ---" in view.lines
    assert "+++ b/added.txt" in output
    assert "+new file" in output
    assert "--- a/modify.txt" in output
    assert "+new content" in output
    assert "--- a/delete.txt" in output
    assert "-delete me" in output


def test_stale_baseline_refusal_raises_without_mutation(tmp_path: Path) -> None:
    setup_temp_git_repo(tmp_path)
    _commit_setup_docs(tmp_path)
    baseline = _git(tmp_path, "rev-parse", "HEAD")
    task = create_task(tmp_path, "stale module task")
    workspace = tmp_path / task.workspace
    (workspace / "worker-result.txt").write_text("worker result\n", encoding="utf-8")
    verify_task(tmp_path, task.id, ["true"])

    (tmp_path / "main-change.txt").write_text("main advanced\n", encoding="utf-8")
    current_head = _commit(tmp_path, "advance main", ["main-change.txt"])

    with pytest.raises(TaskPromotionCommandError) as excinfo:
        build_task_promotion_run_view(tmp_path, task.id)

    message = str(excinfo.value)
    assert "Refusing promotion: task baseline is stale." in message
    assert f"task_baseline_commit: {baseline}" in message
    assert f"current_main_head: {current_head}" in message
    assert not (tmp_path / "worker-result.txt").exists()
    assert not (tmp_path / ".devflow" / "tasks" / task.id / "promotion-preview.json").exists()
    assert get_task(tmp_path, task.id).status == "verified"


def test_run_view_requires_confirmation_for_git_promotion_or_apply_deletions(tmp_path: Path) -> None:
    setup_temp_git_repo(tmp_path)
    _commit_setup_docs(tmp_path)
    (tmp_path / "delete.txt").write_text("delete me\n", encoding="utf-8")
    _commit(tmp_path, "add deletion fixture", ["delete.txt"])
    deletion_task = create_task(tmp_path, "apply deletions module task")
    deletion_workspace = tmp_path / deletion_task.workspace
    (deletion_workspace / "delete.txt").unlink()
    verify_task(tmp_path, deletion_task.id, ["true"])

    deletion_view = build_task_promotion_run_view(
        tmp_path,
        deletion_task.id,
        apply_deletions=True,
    )

    assert isinstance(deletion_view, TaskPromotionRunView)
    assert deletion_view.requires_confirmation is True
    assert deletion_view.no_changes is False

    git_task = create_task(tmp_path, "git module task", git_worktree=True)
    git_workspace = tmp_path / git_task.workspace
    (git_workspace / "worker.txt").write_text("worker result\n", encoding="utf-8")
    subprocess.run(["git", "add", "worker.txt"], cwd=git_workspace, check=True)
    subprocess.run(["git", "commit", "-m", "worker result"], cwd=git_workspace, check=True)
    verify_task(tmp_path, git_task.id, ["test", "-f", "worker.txt"])

    git_view = build_task_promotion_run_view(tmp_path, git_task.id)

    assert isinstance(git_view, TaskPromotionRunView)
    assert git_view.requires_confirmation is True
    assert git_view.no_changes is False


def test_no_change_promotion_run_view_returns_no_changes(tmp_path: Path) -> None:
    task = create_task(tmp_path, "no changes module task")
    verify_task(tmp_path, task.id, ["true"])

    view = build_task_promotion_run_view(tmp_path, task.id)

    assert view.no_changes is True
    assert view.requires_confirmation is False
    assert view.lines == (f"task: {task.id}", "No changes to promote")
    assert get_task(tmp_path, task.id).status == "verified"


def test_execute_promotion_result_returns_completion_lines_and_updates_task(tmp_path: Path) -> None:
    task = create_task(tmp_path, "execute module task")
    workspace = tmp_path / task.workspace
    (workspace / "result.txt").write_text("promoted result\n", encoding="utf-8")
    verify_task(tmp_path, task.id, ["true"])

    result = execute_task_promotion_run(tmp_path, task.id)

    assert result.lines == ("Promotion complete.",)
    assert (tmp_path / "result.txt").read_text(encoding="utf-8") == "promoted result\n"
    updated = get_task(tmp_path, task.id)
    assert updated.status == "promoted"
    assert updated.last_event == "task_promoted"
