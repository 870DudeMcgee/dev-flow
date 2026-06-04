from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from devflow.cli import app
from devflow.control_room.persistence import get_task, save_task, utc_now
from tests.helpers import setup_temp_git_repo


def test_freshness_loop_writes_clean_snapshot(tmp_path: Path, monkeypatch) -> None:
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    brief_path = tmp_path / "my_goal.md"
    brief_path.write_text("## Goal Brief\nImplement durables.", encoding="utf-8")

    runner = CliRunner()
    assert runner.invoke(app, ["goal", "init", "--from", "my_goal.md"]).exit_code == 0

    result = runner.invoke(app, ["freshness", "loop"])

    assert result.exit_code == 0
    assert "Freshness Loop" in result.output
    assert "Status: ok" in result.output
    snapshot_path = tmp_path / ".devflow" / "freshness" / "latest.json"
    assert snapshot_path.exists()
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    assert snapshot["status"] == "ok"
    assert snapshot["goals_checked"] == 1


def test_freshness_loop_asks_when_goal_handoff_contradicts_promoted_task(
    tmp_path: Path,
    monkeypatch,
) -> None:
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    brief_path = tmp_path / "my_goal.md"
    brief_path.write_text("## Goal Brief\nImplement durables.", encoding="utf-8")

    runner = CliRunner()
    assert runner.invoke(app, ["goal", "init", "--from", "my_goal.md"]).exit_code == 0
    assert runner.invoke(app, ["goal", "create-task", "G-0001", "TS-0001"]).exit_code == 0

    task_path = tmp_path / ".devflow" / "tasks" / "task-0001"
    task = get_task(tmp_path, "task-0001")
    task.status = "promoted"
    task.verification_status = "passed"
    task.updated_at = utc_now()
    save_task(task_path, task)

    handoff_path = tmp_path / ".devflow" / "goals" / "G-0001" / "handoff.md"
    handoff_path.write_text(
        "Promotion to `main` is still pending human approval.\n"
        "task-0001 is promotion-preview ready and not promoted.\n",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["freshness", "loop", "--json"])

    assert result.exit_code == 2
    payload = json.loads(result.output)
    assert payload["status"] == "needs_human_decision"
    finding_ids = {finding["id"] for finding in payload["findings"]}
    assert "goal_completion_unclear_after_promoted_slices" in finding_ids
    assert "goal_handoff_contradicts_promoted_task" in finding_ids
    assert payload["snapshot_path"] == ".devflow/freshness/latest.json"
    snapshot = json.loads((tmp_path / ".devflow" / "freshness" / "latest.json").read_text(encoding="utf-8"))
    assert snapshot["status"] == "needs_human_decision"
