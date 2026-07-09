from __future__ import annotations

import json
import shlex
import sys
from pathlib import Path

import yaml
from typer.testing import CliRunner

from devflow.cli import app
from devflow.legacy.control_room.freshness import run_freshness_loop
from devflow.legacy.control_room.parallel_verification import run_parallel_verification_batch
from devflow.legacy.control_room.persistence import get_task
from tests.helpers import setup_temp_git_repo


def test_parallel_verification_batch_runs_task_processes_concurrently(tmp_path: Path, monkeypatch) -> None:
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    command = _timestamp_command()
    _project_verification_goal(
        tmp_path,
        [
            ("TS-0001", "src/a.py", command),
            ("TS-0002", "src/b.py", command),
        ],
    )

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


def test_freshness_verify_batch_cli_respects_max_parallel(tmp_path: Path, monkeypatch) -> None:
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    command = _timestamp_command()
    _project_verification_goal(
        tmp_path,
        [
            ("TS-0001", "src/a.py", command),
            ("TS-0002", "src/b.py", command),
        ],
    )

    result = CliRunner().invoke(
        app,
        ["freshness", "verify-batch", "G-0001", "VB-0001", "--max-parallel", "1", "--timeout-seconds", "10", "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["status"] == "passed"
    assert payload["max_parallel"] == 1
    assert payload["task_count"] == 2

    first = get_task(tmp_path, "task-0001")
    second = get_task(tmp_path, "task-0002")
    first_start, first_end = _workspace_times(tmp_path, first.workspace)
    second_start, second_end = _workspace_times(tmp_path, second.workspace)
    assert first_end <= second_start or second_end <= first_start


def test_freshness_verify_batch_cli_reports_failures_and_preserves_task_evidence(
    tmp_path: Path,
    monkeypatch,
) -> None:
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    _project_verification_goal(
        tmp_path,
        [
            ("TS-0001", "src/a.py", _write_file_command("passed.txt")),
            ("TS-0002", "src/b.py", _failing_command()),
        ],
    )
    goal_yaml_before = (tmp_path / ".devflow" / "goals" / "G-0001" / "goal.yaml").read_text(encoding="utf-8")

    result = CliRunner().invoke(
        app,
        ["freshness", "verify-batch", "G-0001", "VB-0001", "--max-parallel", "2", "--timeout-seconds", "10", "--json"],
    )

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["status"] == "failed"
    assert {item["task_id"]: item["status"] for item in payload["results"]} == {
        "task-0001": "passed",
        "task-0002": "failed",
    }
    assert (tmp_path / payload["report_path"]).is_file()

    first = get_task(tmp_path, "task-0001")
    second = get_task(tmp_path, "task-0002")
    assert first.verification_status == "passed"
    assert second.verification_status == "failed"
    assert (tmp_path / ".devflow" / "tasks" / "task-0001" / "verification.json").is_file()
    assert (tmp_path / ".devflow" / "tasks" / "task-0002" / "verification.json").is_file()
    assert "verification_finished" in (tmp_path / ".devflow" / "tasks" / "task-0002" / "events.jsonl").read_text(
        encoding="utf-8"
    )
    assert (tmp_path / ".devflow" / "goals" / "G-0001" / "goal.yaml").read_text(encoding="utf-8") == goal_yaml_before


def test_freshness_verify_batch_cli_rejects_unprojected_batches(tmp_path: Path, monkeypatch) -> None:
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    _project_verification_goal(tmp_path, [("TS-0001", "src/a.py", _write_file_command("ok.txt"))])

    result = CliRunner().invoke(app, ["freshness", "verify-batch", "G-0001", "VB-9999"])

    assert result.exit_code == 1
    assert "is not projected" in result.output


def _project_verification_goal(root: Path, lanes: list[tuple[str, str, str]]) -> None:
    brief_path = root / "goal.md"
    brief_path.write_text("## Goal Brief\nVerify lanes in parallel.", encoding="utf-8")

    runner = CliRunner()
    assert runner.invoke(app, ["goal", "init", "--from", "goal.md"]).exit_code == 0
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


def _timestamp_command() -> str:
    script = (
        "import pathlib,time; "
        "pathlib.Path('start.txt').write_text(str(time.time())); "
        "time.sleep(0.35); "
        "pathlib.Path('end.txt').write_text(str(time.time()))"
    )
    return f"{shlex.quote(sys.executable)} -c {shlex.quote(script)}"


def _write_file_command(filename: str) -> str:
    script = f"import pathlib; pathlib.Path({filename!r}).write_text('ok')"
    return f"{shlex.quote(sys.executable)} -c {shlex.quote(script)}"


def _failing_command() -> str:
    script = "import pathlib,sys; pathlib.Path('failed.txt').write_text('failed'); sys.exit(7)"
    return f"{shlex.quote(sys.executable)} -c {shlex.quote(script)}"


def _workspace_times(root: Path, workspace: str) -> tuple[float, float]:
    path = root / workspace
    return (
        float((path / "start.txt").read_text(encoding="utf-8")),
        float((path / "end.txt").read_text(encoding="utf-8")),
    )
