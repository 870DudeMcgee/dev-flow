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


def test_freshness_run_all_projects_repeats_registered_project_scans(
    tmp_path: Path,
    monkeypatch,
) -> None:
    home = tmp_path / "home" / ".devflow"
    monkeypatch.setenv("DEVFLOW_HOME", home.as_posix())
    projects_root = tmp_path / "projects"
    runner = CliRunner()

    alpha = runner.invoke(app, ["project", "create", "Alpha App", "--projects-root", projects_root.as_posix()])
    beta = runner.invoke(app, ["project", "create", "Beta App", "--projects-root", projects_root.as_posix()])
    assert alpha.exit_code == 0, alpha.output
    assert beta.exit_code == 0, beta.output

    alpha_root = projects_root / "alpha-app"
    brief_path = alpha_root / "goal.md"
    brief_path.write_text("## Goal Brief\nCoordinate project scans.", encoding="utf-8")
    monkeypatch.chdir(alpha_root)
    assert runner.invoke(app, ["goal", "init", "--from", "goal.md"]).exit_code == 0

    result = runner.invoke(app, ["freshness", "run", "--all-projects", "--max-iterations", "3", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["status"] == "stable"
    assert payload["iterations"][-1]["projects_checked"] == 2
    assert len(payload["iterations"]) >= 2
    assert Path(payload["report_path"]).is_file()
    assert (home / "freshness" / "latest-all-projects.json").is_file()


def test_freshness_run_all_projects_rejects_dispatch_flags(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "home" / ".devflow"
    monkeypatch.setenv("DEVFLOW_HOME", home.as_posix())
    runner = CliRunner()

    result = runner.invoke(app, ["freshness", "run", "--all-projects", "--create-tasks"])

    assert result.exit_code == 1
    assert "read-mostly bounded runs only" in result.output


def test_active_goal_runs_through_create_worker_verify_without_auto_completion(
    tmp_path: Path,
    monkeypatch,
) -> None:
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    brief = tmp_path / "brief.md"
    brief.write_text("# Goal loop smoke\n", encoding="utf-8")
    init = runner.invoke(app, ["goal", "init", "G-0001", "--from", str(brief)])
    assert init.exit_code == 0, init.output
    slices_path = tmp_path / ".devflow" / "goals" / "G-0001" / "task-slices.yaml"
    slices_path.write_text(
        """
task_slices:
  - task_id: TS-0001
    title: "Write goal loop output"
    summary: "Create one output file and verify it."
    blocked_by: []
    parallel_safe: true
    shared_files:
      - result.txt
    risk: low
    execution_mode: AFK
    workspace_isolation_required: false
    promotion_allowed: false
    worker_policy:
      shell_commands:
        - "printf goal-loop > result.txt"
    verification_policy:
      focused_commands:
        - "test -f result.txt"
""".lstrip(),
        encoding="utf-8",
    )
    _commit_all(tmp_path, "goal loop baseline")

    created = runner.invoke(app, ["freshness", "run", "--max-iterations", "3", "--create-tasks", "--json"])
    assert created.exit_code == 0, created.output
    assert (tmp_path / ".devflow" / "tasks" / "task-0001" / "goal-link.yaml").exists()
    _commit_all(tmp_path, "created task")

    worker = runner.invoke(
        app,
        ["freshness", "worker-batch", "G-0001", "WB-0001", "--max-parallel", "1", "--timeout-seconds", "10", "--json"],
    )
    assert worker.exit_code == 0, worker.output
    assert (tmp_path / ".devflow" / "workspaces" / "task-0001" / "result.txt").read_text(encoding="utf-8") == "goal-loop"

    verified = runner.invoke(
        app,
        ["freshness", "verify-batch", "G-0001", "VB-0001", "--max-parallel", "1", "--timeout-seconds", "10", "--json"],
    )
    assert verified.exit_code == 0, verified.output
    verification = yaml.safe_load((tmp_path / ".devflow" / "tasks" / "task-0001" / "verification.json").read_text(encoding="utf-8"))
    assert verification["status"] == "passed"

    final_loop = runner.invoke(app, ["freshness", "loop", "--json"])
    assert final_loop.exit_code == 0, final_loop.output
    payload = json.loads(final_loop.output)
    assert payload["goal_loop"][0]["loop_state"] in {"active_work_in_progress", "needs_closure_decision"}
    state = yaml.safe_load((tmp_path / ".devflow" / "goals" / "G-0001" / "goal-state.yaml").read_text(encoding="utf-8"))
    assert state["lifecycle"] == "active"


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
