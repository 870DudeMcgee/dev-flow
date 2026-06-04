from __future__ import annotations

import json
import shlex
import subprocess
import sys
from pathlib import Path

import yaml
from typer.testing import CliRunner

from devflow.cli import app
from devflow.control_room.persistence import get_task
from tests.helpers import setup_temp_git_repo


def test_freshness_run_repeats_until_state_is_stable(tmp_path: Path, monkeypatch) -> None:
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    _project_goal(tmp_path, [])
    _commit_all(tmp_path, "goal baseline")

    result = CliRunner().invoke(app, ["freshness", "run", "--max-iterations", "3", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["status"] == "stable"
    assert len(payload["iterations"]) == 2
    assert payload["iterations"][0]["loop_start_git_action"] == "continue_loop"
    assert payload["iterations"][1]["state_hash"] == payload["iterations"][0]["state_hash"]
    assert (tmp_path / payload["report_path"]).is_file()


def test_freshness_run_does_not_dispatch_verification_without_explicit_flag(
    tmp_path: Path,
    monkeypatch,
) -> None:
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    _project_goal(tmp_path, [("TS-0001", "src/a.py", _write_file_command("verified.txt"))])
    _commit_all(tmp_path, "goal and task baseline")

    result = CliRunner().invoke(app, ["freshness", "run", "--max-iterations", "2", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["status"] == "stable"
    assert all(iteration["verification_run"] is None for iteration in payload["iterations"])
    task = get_task(tmp_path, "task-0001")
    assert task.verification_status == "not_run"
    assert not (tmp_path / task.workspace / "verified.txt").exists()


def test_freshness_run_executes_verification_when_explicitly_allowed_then_reports_checkpoint(
    tmp_path: Path,
    monkeypatch,
) -> None:
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    _project_goal(tmp_path, [("TS-0001", "src/a.py", _write_file_command("verified.txt"))])
    _commit_all(tmp_path, "goal and task baseline")

    result = CliRunner().invoke(
        app,
        [
            "freshness",
            "run",
            "--max-iterations",
            "3",
            "--execute-verification",
            "--max-parallel",
            "1",
            "--timeout-seconds",
            "10",
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["status"] == "git_action_required"
    assert len(payload["iterations"]) == 2
    assert payload["iterations"][0]["verification_run"]["status"] == "passed"
    assert payload["iterations"][1]["loop_start_git_action"] == "checkpoint_before_more_work"
    assert payload["next_action"] == "devflow git checkpoint --message 'chore: checkpoint verified work'"

    task = get_task(tmp_path, "task-0001")
    assert task.verification_status == "passed"
    assert (tmp_path / task.workspace / "verified.txt").is_file()


def _project_goal(root: Path, lanes: list[tuple[str, str, str]]) -> None:
    brief_path = root / "goal.md"
    brief_path.write_text("## Goal Brief\nRun bounded control loop.", encoding="utf-8")

    runner = CliRunner()
    assert runner.invoke(app, ["goal", "init", "--from", "goal.md"]).exit_code == 0
    if not lanes:
        return

    slices_path = root / ".devflow" / "goals" / "G-0001" / "task-slices.yaml"
    slices_path.write_text(
        yaml.safe_dump(
            {
                "task_slices": [
                    {
                        "task_id": lane_id,
                        "title": f"{lane_id} verification lane",
                        "summary": "Runs a projected verification command.",
                        "parallel_safe": True,
                        "shared_files": [shared_file],
                        "risk": "low",
                        "execution_mode": "AFK",
                        "verification_policy": {"focused_commands": [command]},
                    }
                    for lane_id, shared_file, command in lanes
                ]
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    for lane_id, _shared_file, _command in lanes:
        assert runner.invoke(app, ["goal", "create-task", "G-0001", lane_id]).exit_code == 0


def _write_file_command(filename: str) -> str:
    script = f"import pathlib; pathlib.Path({filename!r}).write_text('ok')"
    return f"{shlex.quote(sys.executable)} -c {shlex.quote(script)}"


def _commit_all(root: Path, message: str) -> None:
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-m", message], cwd=root, check=True)
