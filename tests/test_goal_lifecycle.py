from __future__ import annotations

import json
from pathlib import Path

import yaml
from typer.testing import CliRunner

from devflow.cli import app
from devflow.control_room.goal_lifecycle import (
    GoalLifecycleError,
    ensure_goal_lifecycle,
    read_goal_lifecycle,
    set_goal_lifecycle,
)
from devflow.control_room.goals import create_goal_from_markdown


runner = CliRunner()


def _goal(root: Path) -> str:
    brief = root / "brief.md"
    brief.write_text("# Build a bounded goal loop\n", encoding="utf-8")
    return create_goal_from_markdown(root, brief).id


def test_new_goal_lifecycle_can_be_created_and_read(tmp_path: Path) -> None:
    goal_id = _goal(tmp_path)

    state = ensure_goal_lifecycle(tmp_path, goal_id)

    assert state.goal_id == goal_id
    assert state.lifecycle == "active"
    path = tmp_path / ".devflow" / "goals" / goal_id / "goal-state.yaml"
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["lifecycle"] == "active"


def test_lifecycle_transitions_append_hash_chained_events(tmp_path: Path) -> None:
    goal_id = _goal(tmp_path)
    ensure_goal_lifecycle(tmp_path, goal_id)

    paused = set_goal_lifecycle(
        tmp_path,
        goal_id,
        lifecycle="paused",
        reason="waiting for review",
        command="devflow goal pause G-0001 --reason 'waiting for review'",
    )

    assert paused.lifecycle == "paused"
    assert paused.status_reason == "waiting for review"
    events_path = tmp_path / ".devflow" / "goals" / goal_id / "events.jsonl"
    events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines()]
    assert [event["event_index"] for event in events] == [0, 1]
    assert events[0]["event"] == "goal_lifecycle_created"
    assert events[1]["event"] == "goal_lifecycle_changed"
    assert events[1]["previous_event_hash"] == events[0]["event_hash"]


def test_lifecycle_refuses_unknown_goal_and_invalid_state(tmp_path: Path) -> None:
    try:
        ensure_goal_lifecycle(tmp_path, "G-9999")
    except GoalLifecycleError as exc:
        assert "Goal not found" in str(exc)
    else:
        raise AssertionError("expected missing goal to fail")

    goal_id = _goal(tmp_path)
    try:
        set_goal_lifecycle(tmp_path, goal_id, lifecycle="running", reason="bad", command="bad")
    except GoalLifecycleError as exc:
        assert "Unsupported goal lifecycle" in str(exc)
    else:
        raise AssertionError("expected invalid lifecycle to fail")


def test_missing_lifecycle_reads_as_missing_without_mutating(tmp_path: Path) -> None:
    goal_id = _goal(tmp_path)
    lifecycle_path = tmp_path / ".devflow" / "goals" / goal_id / "goal-state.yaml"
    lifecycle_path.unlink(missing_ok=True)

    state = read_goal_lifecycle(tmp_path, goal_id)

    assert state is None
    assert not lifecycle_path.exists()


def test_goal_command_group_lives_in_control_room_command_module() -> None:
    from devflow.control_room.goal_command import goal_app

    cli_source = Path("src/devflow/cli.py").read_text(encoding="utf-8")

    assert goal_app.info.help == "Manage goals and planning scaffolds"
    assert "@goal_app.command" not in cli_source


def test_goal_init_writes_active_lifecycle(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    brief = tmp_path / "brief.md"
    brief.write_text("# Ship goal loop\n", encoding="utf-8")

    result = runner.invoke(app, ["goal", "init", "G-0001", "--from", str(brief)])

    assert result.exit_code == 0, result.output
    state_path = tmp_path / ".devflow" / "goals" / "G-0001" / "goal-state.yaml"
    payload = yaml.safe_load(state_path.read_text(encoding="utf-8"))
    assert payload["lifecycle"] == "active"


def test_goal_lifecycle_cli_commands_write_state(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    brief = tmp_path / "brief.md"
    brief.write_text("# Ship goal loop\n", encoding="utf-8")
    runner.invoke(app, ["goal", "init", "G-0001", "--from", str(brief)])

    paused = runner.invoke(app, ["goal", "pause", "G-0001", "--reason", "waiting for review"])
    blocked = runner.invoke(app, ["goal", "block", "G-0001", "--reason", "needs answer"])
    active = runner.invoke(app, ["goal", "activate", "G-0001", "--reason", "answer received"])
    complete = runner.invoke(app, ["goal", "complete", "G-0001", "--reason", "all slices promoted"])
    archived = runner.invoke(app, ["goal", "archive", "G-0001", "--reason", "retained as history"])

    assert paused.exit_code == 0, paused.output
    assert "lifecycle: paused" in paused.output
    assert blocked.exit_code == 0, blocked.output
    assert "lifecycle: blocked" in blocked.output
    assert active.exit_code == 0, active.output
    assert "lifecycle: active" in active.output
    assert complete.exit_code == 0, complete.output
    assert "lifecycle: complete" in complete.output
    assert archived.exit_code == 0, archived.output
    assert "lifecycle: archived" in archived.output
