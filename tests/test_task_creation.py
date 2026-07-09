from __future__ import annotations

import concurrent.futures
import json
import subprocess
from pathlib import Path

import pytest

from devflow.legacy.control_room.persistence import get_task
from devflow.legacy.control_room.project_models import ProjectMetadata
from devflow.legacy.control_room.service import create_task, init_control_room
from devflow.legacy.control_room.task_artifacts import BASELINE_TASK_ARTIFACTS
from devflow.legacy.control_room.task_creation import (
    create_control_room_task,
    initialize_control_room,
)


def _events(root: Path, task_id: str) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in (root / ".devflow" / "tasks" / task_id / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]


def _assert_complete_baseline(root: Path, task_id: str) -> None:
    task_path = root / ".devflow" / "tasks" / task_id
    missing = [name for name in BASELINE_TASK_ARTIFACTS if not (task_path / name).exists()]
    assert missing == []


def _run_git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _init_git_repo(root: Path) -> str:
    _run_git(root, "init", "-b", "main")
    _run_git(root, "config", "user.email", "test@example.com")
    _run_git(root, "config", "user.name", "Test User")
    (root / "tracked.txt").write_text("baseline\n", encoding="utf-8")
    _run_git(root, "add", "tracked.txt")
    _run_git(root, "commit", "-m", "baseline")
    return _run_git(root, "rev-parse", "HEAD")


def test_create_control_room_task_creates_workspace_baseline_and_event(tmp_path: Path) -> None:
    (tmp_path / "main.txt").write_text("main checkout\n", encoding="utf-8")
    (tmp_path / "outside.txt").write_text("outside\n", encoding="utf-8")
    (tmp_path / "outside-link.txt").symlink_to(tmp_path / "outside.txt")

    task = create_control_room_task(tmp_path, "direct module task")

    assert task.id == "task-0001"
    assert task.title == "direct module task"
    assert task.status == "created"
    assert task.workspace == ".devflow/workspaces/task-0001"
    assert task.workspace_path == ".devflow/workspaces/task-0001"
    assert task.workspace_kind == "directory"
    assert (tmp_path / ".devflow" / "workspaces" / task.id / "main.txt").read_text(encoding="utf-8") == "main checkout\n"
    assert not (tmp_path / ".devflow" / "workspaces" / task.id / "outside-link.txt").exists()
    _assert_complete_baseline(tmp_path, task.id)

    events = _events(tmp_path, task.id)
    assert [event["event"] for event in events] == ["task_created"]
    assert events[0]["title"] == "direct module task"
    assert events[0]["workspace"] == ".devflow/workspaces/task-0001"
    assert events[0]["workspace_kind"] == "directory"
    assert events[0]["definition_of_done"] is None
    assert events[0]["skipped_symlinks"] == ["outside-link.txt"]


def test_service_facades_delegate_to_task_creation_behavior(tmp_path: Path) -> None:
    init_control_room(tmp_path)

    task = create_task(tmp_path, "service facade task", definition_of_done="  All evidence is visible.  ")

    assert (tmp_path / ".devflow" / "config.yaml").is_file()
    assert task.id == "task-0001"
    assert task.definition_of_done == "All evidence is visible."
    assert get_task(tmp_path, task.id).definition_of_done == "All evidence is visible."
    _assert_complete_baseline(tmp_path, task.id)


@pytest.mark.parametrize(
    ("definition_of_done", "expected"),
    [
        (None, None),
        ("   ", None),
        ("  Verify the task evidence.  ", "Verify the task evidence."),
    ],
)
def test_definition_of_done_is_normalized(
    tmp_path: Path,
    definition_of_done: str | None,
    expected: str | None,
) -> None:
    task = create_control_room_task(
        tmp_path,
        "definition normalization",
        definition_of_done=definition_of_done,
    )

    assert task.definition_of_done == expected
    assert get_task(tmp_path, task.id).definition_of_done == expected
    assert _events(tmp_path, task.id)[0]["definition_of_done"] == expected


def test_concurrent_create_control_room_task_ids_are_unique(tmp_path: Path) -> None:
    initialize_control_room(tmp_path)

    def run_create(idx: int) -> str:
        return create_control_room_task(tmp_path, f"concurrent task {idx}").id

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        task_ids = list(executor.map(run_create, range(8)))

    assert sorted(task_ids) == [f"task-{idx:04d}" for idx in range(1, 9)]
    for task_id in task_ids:
        assert get_task(tmp_path, task_id).id == task_id
        assert (tmp_path / ".devflow" / "workspaces" / task_id).is_dir()


def test_managed_project_without_initial_git_baseline_refuses_task_creation(tmp_path: Path) -> None:
    _run_git(tmp_path, "init", "-b", "main")
    metadata = ProjectMetadata(
        id="baseline-required",
        project_id="baseline-required",
        name="Baseline Required",
        root_path=tmp_path.as_posix(),
    )
    initialize_control_room(tmp_path, project_seed=metadata)

    with pytest.raises(ValueError, match="Project local Git baseline is missing") as excinfo:
        create_control_room_task(tmp_path, "first task")

    assert 'devflow git checkpoint --message "chore: initialize project baseline" --yes' in str(excinfo.value)
    assert not (tmp_path / ".devflow" / "tasks" / "task-0001").exists()


def test_git_worktree_task_records_lane_metadata(tmp_path: Path) -> None:
    baseline = _init_git_repo(tmp_path)

    task = create_control_room_task(tmp_path, "git worktree task", git_worktree=True)

    assert task.workspace == ".devflow/worktrees/task-0001/shell"
    assert task.workspace_kind == "git_worktree"
    assert task.branch_name == "devflow/task-0001/shell"
    assert task.workspace_commit == baseline
    assert task.workspace_dirty is False
    assert task.git == {
        "base_ref": "main",
        "base_commit": baseline,
        "branch": "devflow/task-0001/shell",
        "workspace": ".devflow/worktrees/task-0001/shell",
    }

    git_evidence = json.loads(
        (tmp_path / ".devflow" / "tasks" / task.id / "workers" / "shell" / "git.json").read_text(encoding="utf-8")
    )
    assert git_evidence["task_id"] == task.id
    assert git_evidence["base_commit"] == baseline
    assert git_evidence["worker_branch"] == "devflow/task-0001/shell"
    assert git_evidence["worktree_path"] == ".devflow/worktrees/task-0001/shell"
