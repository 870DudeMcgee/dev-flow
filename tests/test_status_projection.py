from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from devflow.cli import app
from devflow.legacy.control_room.dashboard import collect_dashboard_state
from devflow.legacy.control_room.service import create_task
from devflow.legacy.control_room.status_projection import (
    choose_task_dashboard_action,
    choose_task_focus_projection,
    list_task_status_projections,
)
from devflow.legacy.control_room.task_closure import close_task
from tests.helpers import git_commit, init_test_git_repo, setup_temp_repo


runner = CliRunner()


def test_closed_failed_verification_is_not_active_dashboard_work(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    task = create_task(tmp_path, "Dogfood failed verification recovery")
    assert runner.invoke(app, ["task", "run", task.id, "--shell", "printf actual > recovery.txt"]).exit_code == 0
    verify = runner.invoke(app, ["task", "verify", task.id, "--shell", 'test "$(cat recovery.txt)" = expected'])
    assert verify.exit_code == 1, verify.output
    close_task(tmp_path, task.id, outcome="evidence-only", reason="dogfood evidence captured")

    projection = list_task_status_projections(tmp_path)[0]
    assert projection.display_status == "closed/evidence-only"
    assert projection.is_active is False
    assert projection.failed_verification is False
    assert choose_task_dashboard_action([projection]) is None

    state = collect_dashboard_state(tmp_path)
    assert state.health.active_tasks == 0
    assert state.health.failed_verification == 0


def test_projection_prioritizes_manual_blocker_before_failed_and_ready_tasks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    manual = create_task(tmp_path, "Manual blocker")
    assert runner.invoke(app, ["task", "run", manual.id, "--worker", "devflow-manual-codex-worker"]).exit_code == 0

    failed = create_task(tmp_path, "Failed verification")
    assert runner.invoke(app, ["task", "run", failed.id, "--shell", "echo done"]).exit_code == 0
    verify_failed = runner.invoke(app, ["task", "verify", failed.id, "--shell", "exit 3"])
    assert verify_failed.exit_code == 3, verify_failed.output

    ready = create_task(tmp_path, "Ready promotion")
    assert runner.invoke(app, ["task", "run", ready.id, "--shell", "echo done"]).exit_code == 0
    verify_ready = runner.invoke(app, ["task", "verify", ready.id, "--shell", "echo verified"])
    assert verify_ready.exit_code == 0, verify_ready.output

    projections = list_task_status_projections(tmp_path)
    focus = choose_task_focus_projection(projections)
    action = choose_task_dashboard_action(projections)

    assert focus is not None
    assert action is not None
    assert focus.task.id == manual.id
    assert action.task_id == manual.id
    assert action.label == "Resolve blocker"


def test_projection_manual_agent_states_drive_dashboard_actions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    task = create_task(tmp_path, "Manual states")
    assert runner.invoke(app, ["task", "run", task.id, "--worker", "devflow-manual-codex-worker"]).exit_code == 0
    agent_dir = tmp_path / ".devflow/tasks" / task.id / "agents" / "devflow-manual-codex-worker"

    projections = list_task_status_projections(tmp_path)
    projection = projections[0]
    action = choose_task_dashboard_action(projections)
    assert projection.display_status == "awaiting_human"
    assert projection.is_blocked
    assert action is not None
    assert action.label == "Resolve blocker"
    assert action.command == f"devflow task show {task.id}"

    with (agent_dir / "questions.jsonl").open("a", encoding="utf-8") as file_obj:
        file_obj.write(
            json.dumps(
                {
                    "type": "blocked_question",
                    "task_id": task.id,
                    "agent_id": "devflow-manual-codex-worker",
                    "question": "Which API shape should I preserve?",
                    "blocking_reason": "Two incompatible call sites exist.",
                }
            )
            + "\n"
        )

    projection = list_task_status_projections(tmp_path)[0]
    action = choose_task_dashboard_action([projection])
    assert projection.display_status == "blocked_question"
    assert projection.is_blocked
    assert projection.manual_agent_question == "Which API shape should I preserve?"
    assert action is not None
    assert action.label == "Resolve blocker"

    (agent_dir / "questions.jsonl").unlink()
    (agent_dir / "result.md").write_text(
        "# Result\n\nstatus: complete\nsummary: Workspace edits are ready.\n",
        encoding="utf-8",
    )

    projection = list_task_status_projections(tmp_path)[0]
    action = choose_task_dashboard_action([projection])
    assert projection.display_status == "result_present"
    assert projection.needs_verification
    assert action is not None
    assert action.label == "Run verification"

    state = collect_dashboard_state(tmp_path)
    assert state.next_action.task_id == task.id
    assert state.next_action.label == "Run verification"
    assert state.health.needs_verification == 1


def test_closed_tasks_are_not_selected_as_focus_when_control_room_is_clean(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    task = create_task(tmp_path, "closed only")
    close_task(tmp_path, task.id, outcome="evidence-only", reason="no active work")

    projections = list_task_status_projections(tmp_path)
    state = collect_dashboard_state(tmp_path)

    assert choose_task_focus_projection(projections) is None
    assert state.focus_task is None
    assert state.next_action.label == "Create a task"


def test_stale_verified_directory_task_is_not_global_promotion_candidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    init_test_git_repo(tmp_path)

    created = runner.invoke(app, ["task", "create", "stale verified directory task"])
    assert created.exit_code == 0, created.output

    (tmp_path / "main-change.txt").write_text("main advanced\n", encoding="utf-8")
    subprocess.run(["git", "add", "main-change.txt"], cwd=tmp_path, check=True)
    current_head = git_commit(tmp_path, message="advance main", add_all=False)

    run = runner.invoke(app, ["task", "run", "task-0001", "--shell", "printf done > worker.txt"])
    assert run.exit_code == 0, run.output
    verify = runner.invoke(app, ["task", "verify", "task-0001", "--shell", "test -f worker.txt"])
    assert verify.exit_code == 0, verify.output

    projection = list_task_status_projections(tmp_path)[0]
    action = choose_task_dashboard_action([projection])

    assert projection.task.workspace_commit != current_head
    assert projection.is_verified
    assert projection.promotion_ready is False
    assert projection.ready_to_promote is False
    assert any("current main checkout HEAD differs" in reason for reason in projection.promotion_blockers)
    assert action is not None
    assert action.label == "Inspect task"
    assert action.command == "devflow task show task-0001"


def test_collect_dashboard_state_collects_goal_projection_warnings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    setup_temp_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    goal_md = tmp_path / "my_goal.md"
    goal_md.write_text("## Goal Brief\nImplement durables.", encoding="utf-8")
    init_res = runner.invoke(app, ["goal", "init", "--from", goal_md.name])
    assert init_res.exit_code == 0, init_res.output

    from devflow.legacy.control_room import goal_projection

    original = goal_projection.build_goal_status_projection

    def _broken(root: Path, goal_id: str) -> Any:
        if goal_id == "G-0001":
            raise RuntimeError("projection is intentionally broken")
        return original(root, goal_id)

    monkeypatch.setattr(goal_projection, "build_goal_status_projection", _broken)

    warnings: list[str] = []
    collect_dashboard_state(tmp_path, task_projection_warnings=warnings)

    assert any("failed to project goal" in warning for warning in warnings)
