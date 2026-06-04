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


def test_freshness_loop_projects_worker_batches_from_linked_tasks(
    tmp_path: Path,
    monkeypatch,
) -> None:
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    _project_worker_goal(
        tmp_path,
        [
            ("TS-0001", "src/a.py", "printf one > one.txt"),
            ("TS-0002", "src/b.py", "printf two > two.txt"),
            ("TS-0003", "src/a.py", "printf three > three.txt"),
        ],
    )

    result = CliRunner().invoke(app, ["freshness", "loop", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    goal_loop = payload["goal_loop"][0]
    assert goal_loop["ready_worker_batch_count"] == 2
    assert goal_loop["worker_command_count"] == 3
    assert goal_loop["worker_batches"][0]["lane_ids"] == ["TS-0001", "TS-0002"]
    assert goal_loop["worker_batches"][0]["commands"] == [
        "devflow task run task-0001 --worker shell -- printf one > one.txt",
        "devflow task run task-0002 --worker shell -- printf two > two.txt",
    ]
    assert goal_loop["worker_batches"][1]["lane_ids"] == ["TS-0003"]

    loop_state = json.loads((tmp_path / ".devflow" / "goals" / "G-0001" / "loop-state.json").read_text(encoding="utf-8"))
    assert loop_state["goal"]["ready_worker_batch_count"] == 2
    assert loop_state["goal"]["worker_command_count"] == 3

    event = json.loads((tmp_path / ".devflow" / "freshness" / "events.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert event["goal_loop"][0]["ready_worker_batch_count"] == 2
    assert event["goal_loop"][0]["worker_command_count"] == 3


def test_freshness_worker_batch_runs_task_processes_concurrently(
    tmp_path: Path,
    monkeypatch,
) -> None:
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    command = _timestamp_command()
    _project_worker_goal(
        tmp_path,
        [
            ("TS-0001", "src/a.py", command),
            ("TS-0002", "src/b.py", command),
        ],
    )
    _commit_all(tmp_path, "worker goal baseline")

    result = CliRunner().invoke(
        app,
        ["freshness", "worker-batch", "G-0001", "WB-0001", "--max-parallel", "2", "--timeout-seconds", "10", "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["status"] == "passed"
    assert payload["task_count"] == 2
    assert payload["command_count"] == 2
    assert (tmp_path / payload["report_path"]).is_file()

    first = get_task(tmp_path, "task-0001")
    second = get_task(tmp_path, "task-0002")
    assert first.status == "complete"
    assert second.status == "complete"
    first_start, first_end = _workspace_times(tmp_path, first.workspace)
    second_start, second_end = _workspace_times(tmp_path, second.workspace)
    assert max(first_start, second_start) < min(first_end, second_end)


def test_freshness_worker_batch_reports_failures_without_hiding_other_results(
    tmp_path: Path,
    monkeypatch,
) -> None:
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    _project_worker_goal(
        tmp_path,
        [
            ("TS-0001", "src/a.py", "printf ok > ok.txt"),
            ("TS-0002", "src/b.py", _failing_command()),
        ],
    )
    _commit_all(tmp_path, "worker goal baseline")

    result = CliRunner().invoke(
        app,
        ["freshness", "worker-batch", "G-0001", "WB-0001", "--max-parallel", "2", "--timeout-seconds", "10", "--json"],
    )

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["status"] == "failed"
    assert {item["task_id"]: item["status"] for item in payload["results"]} == {
        "task-0001": "complete",
        "task-0002": "worker_failed",
    }
    assert get_task(tmp_path, "task-0001").status == "complete"
    assert get_task(tmp_path, "task-0002").status == "worker_failed"


def test_freshness_run_executes_worker_batch_when_explicitly_allowed_then_reports_checkpoint(
    tmp_path: Path,
    monkeypatch,
) -> None:
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    _project_worker_goal(tmp_path, [("TS-0001", "src/a.py", "printf run > run.txt")])
    _commit_all(tmp_path, "worker goal baseline")

    result = CliRunner().invoke(
        app,
        ["freshness", "run", "--max-iterations", "3", "--execute-workers", "--timeout-seconds", "10", "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["status"] == "git_action_required"
    assert payload["execute_workers"] is True
    assert payload["iterations"][0]["worker_run"]["status"] == "passed"
    assert payload["iterations"][1]["loop_start_git_action"] == "checkpoint_before_more_work"
    task = get_task(tmp_path, "task-0001")
    assert task.status == "complete"
    assert (tmp_path / task.workspace / "run.txt").read_text(encoding="utf-8") == "run"


def _project_worker_goal(root: Path, lanes: list[tuple[str, str, str]]) -> None:
    brief_path = root / "goal.md"
    brief_path.write_text("## Goal Brief\nRun shell worker lanes.", encoding="utf-8")

    runner = CliRunner()
    assert runner.invoke(app, ["goal", "init", "--from", "goal.md"]).exit_code == 0
    slices_path = root / ".devflow" / "goals" / "G-0001" / "task-slices.yaml"
    slices_path.write_text(
        yaml.safe_dump(
            {
                "task_slices": [
                    {
                        "task_id": lane_id,
                        "title": f"{lane_id} worker lane",
                        "summary": "Runs a shell worker command in the isolated workspace.",
                        "parallel_safe": True,
                        "shared_files": [shared_file],
                        "risk": "low",
                        "execution_mode": "AFK",
                        "worker_policy": {"shell_commands": [command]},
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


def _timestamp_command() -> str:
    script = (
        "import pathlib,time; "
        "pathlib.Path('start.txt').write_text(str(time.time())); "
        "time.sleep(0.35); "
        "pathlib.Path('end.txt').write_text(str(time.time()))"
    )
    return f"{shlex.quote(sys.executable)} -c {shlex.quote(script)}"


def _failing_command() -> str:
    script = "import pathlib,sys; pathlib.Path('failed.txt').write_text('failed'); sys.exit(9)"
    return f"{shlex.quote(sys.executable)} -c {shlex.quote(script)}"


def _workspace_times(root: Path, workspace: str) -> tuple[float, float]:
    path = root / workspace
    return (
        float((path / "start.txt").read_text(encoding="utf-8")),
        float((path / "end.txt").read_text(encoding="utf-8")),
    )


def _commit_all(root: Path, message: str) -> None:
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-m", message], cwd=root, check=True)
