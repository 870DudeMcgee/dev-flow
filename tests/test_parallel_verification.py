from __future__ import annotations

import shlex
import sys
from pathlib import Path

import yaml
from typer.testing import CliRunner

from devflow.cli import app
from devflow.control_room.freshness import run_freshness_loop
from devflow.control_room.parallel_verification import run_parallel_verification_batch
from devflow.control_room.persistence import get_task
from tests.helpers import setup_temp_git_repo


def test_parallel_verification_batch_runs_task_processes_concurrently(tmp_path: Path, monkeypatch) -> None:
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    brief_path = tmp_path / "goal.md"
    brief_path.write_text("## Goal Brief\nVerify lanes in parallel.", encoding="utf-8")

    runner = CliRunner()
    assert runner.invoke(app, ["goal", "init", "--from", "goal.md"]).exit_code == 0

    command = _timestamp_command()
    slices_path = tmp_path / ".devflow" / "goals" / "G-0001" / "task-slices.yaml"
    slices_path.write_text(
        yaml.safe_dump(
            {
                "task_slices": [
                    {
                        "task_id": "TS-0001",
                        "title": "First verification lane",
                        "summary": "Records timestamps while verifying.",
                        "parallel_safe": True,
                        "shared_files": ["src/a.py"],
                        "risk": "low",
                        "execution_mode": "AFK",
                        "verification_policy": {"focused_commands": [command]},
                    },
                    {
                        "task_id": "TS-0002",
                        "title": "Second verification lane",
                        "summary": "Records timestamps while verifying.",
                        "parallel_safe": True,
                        "shared_files": ["src/b.py"],
                        "risk": "low",
                        "execution_mode": "AFK",
                        "verification_policy": {"focused_commands": [command]},
                    },
                ]
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    assert runner.invoke(app, ["goal", "create-task", "G-0001", "TS-0001"]).exit_code == 0
    assert runner.invoke(app, ["goal", "create-task", "G-0001", "TS-0002"]).exit_code == 0

    report = run_freshness_loop(tmp_path, write_snapshot=True)
    batch = report.goal_loop[0].verification_batches[0]

    run = run_parallel_verification_batch(tmp_path, batch, max_parallel=2, timeout_seconds=10)

    assert run.status == "passed"
    assert run.max_parallel == 2
    assert run.task_count == 2
    assert run.command_count == 2
    assert run.report_path is not None
    assert (tmp_path / run.report_path).is_file()
    assert {result.task_id: result.status for result in run.results} == {
        "task-0001": "passed",
        "task-0002": "passed",
    }

    first = get_task(tmp_path, "task-0001")
    second = get_task(tmp_path, "task-0002")
    assert first.verification_status == "passed"
    assert second.verification_status == "passed"

    first_start, first_end = _workspace_times(tmp_path, first.workspace)
    second_start, second_end = _workspace_times(tmp_path, second.workspace)
    assert max(first_start, second_start) < min(first_end, second_end)


def _timestamp_command() -> str:
    script = (
        "import pathlib,time; "
        "pathlib.Path('start.txt').write_text(str(time.time())); "
        "time.sleep(0.35); "
        "pathlib.Path('end.txt').write_text(str(time.time()))"
    )
    return f"{shlex.quote(sys.executable)} -c {shlex.quote(script)}"


def _workspace_times(root: Path, workspace: str) -> tuple[float, float]:
    path = root / workspace
    return (
        float((path / "start.txt").read_text(encoding="utf-8")),
        float((path / "end.txt").read_text(encoding="utf-8")),
    )
