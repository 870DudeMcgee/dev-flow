from __future__ import annotations

import json
import subprocess
from pathlib import Path

import yaml
from typer.testing import CliRunner

from devflow.cli import app
from devflow.legacy.control_room.persistence import get_task
from tests.helpers import setup_temp_git_repo


def test_freshness_create_batch_creates_only_selected_safe_parallel_batch(
    tmp_path: Path,
    monkeypatch,
) -> None:
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    _project_parallel_goal(
        tmp_path,
        [
            ("TS-0001", "src/a.py"),
            ("TS-0002", "src/b.py"),
            ("TS-0003", "src/a.py"),
        ],
    )
    _commit_all(tmp_path, "parallel goal baseline")

    result = CliRunner().invoke(app, ["freshness", "create-batch", "G-0001", "PB-0001", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["status"] == "created"
    assert payload["lane_count"] == 2
    assert payload["created_task_count"] == 2
    assert [item["lane_id"] for item in payload["results"]] == ["TS-0001", "TS-0002"]
    assert (tmp_path / payload["report_path"]).is_file()

    first = get_task(tmp_path, "task-0001")
    second = get_task(tmp_path, "task-0002")
    assert first.title == "TS-0001 implementation lane"
    assert second.title == "TS-0002 implementation lane"
    assert (tmp_path / ".devflow" / "tasks" / "task-0001" / "goal-link.yaml").read_text(encoding="utf-8").find(
        "slice_id: TS-0001"
    ) >= 0
    assert not (tmp_path / ".devflow" / "tasks" / "task-0003").exists()


def test_freshness_create_batch_refuses_when_git_has_non_loop_dirty_state(
    tmp_path: Path,
    monkeypatch,
) -> None:
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    _project_parallel_goal(tmp_path, [("TS-0001", "src/a.py")])
    _commit_all(tmp_path, "parallel goal baseline")
    (tmp_path / "source-change.txt").write_text("dirty", encoding="utf-8")

    result = CliRunner().invoke(app, ["freshness", "create-batch", "G-0001", "PB-0001"])

    assert result.exit_code == 1
    assert "Git action is required before task creation dispatch" in result.output
    assert not (tmp_path / ".devflow" / "tasks" / "task-0001").exists()


def test_freshness_run_can_create_projected_task_batch_when_explicitly_allowed(
    tmp_path: Path,
    monkeypatch,
) -> None:
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    _project_parallel_goal(tmp_path, [("TS-0001", "src/a.py"), ("TS-0002", "src/b.py")])
    _commit_all(tmp_path, "parallel goal baseline")

    result = CliRunner().invoke(app, ["freshness", "run", "--max-iterations", "3", "--create-tasks", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["status"] == "git_action_required"
    assert payload["create_tasks"] is True
    assert payload["iterations"][0]["task_creation_run"]["created_task_count"] == 2
    assert payload["iterations"][1]["loop_start_git_action"] == "checkpoint_before_more_work"
    assert get_task(tmp_path, "task-0001").title == "TS-0001 implementation lane"
    assert get_task(tmp_path, "task-0002").title == "TS-0002 implementation lane"


def _project_parallel_goal(root: Path, lanes: list[tuple[str, str]]) -> None:
    brief_path = root / "goal.md"
    brief_path.write_text("## Goal Brief\nCreate parallel task lanes.", encoding="utf-8")

    runner = CliRunner()
    assert runner.invoke(app, ["goal", "init", "--from", "goal.md"]).exit_code == 0
    slices_path = root / ".devflow" / "goals" / "G-0001" / "task-slices.yaml"
    slices_path.write_text(
        yaml.safe_dump(
            {
                "task_slices": [
                    {
                        "task_id": lane_id,
                        "title": f"{lane_id} implementation lane",
                        "summary": "Create an isolated task workspace.",
                        "parallel_safe": True,
                        "shared_files": [shared_file],
                        "risk": "low",
                        "execution_mode": "AFK",
                    }
                    for lane_id, shared_file in lanes
                ]
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def _commit_all(root: Path, message: str) -> None:
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-m", message], cwd=root, check=True)
