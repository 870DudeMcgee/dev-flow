from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from typer.testing import CliRunner

from devflow.cli import app
from devflow.control_room.persistence import get_task, save_task, utc_now
from tests.helpers import setup_temp_git_repo


def _devflow_home(tmp_path: Path, monkeypatch) -> Path:
    home = tmp_path / "home" / ".devflow"
    monkeypatch.setenv("DEVFLOW_HOME", home.as_posix())
    return home


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
    assert "Goal Loop" in result.output
    snapshot_path = tmp_path / ".devflow" / "freshness" / "latest.json"
    assert snapshot_path.exists()
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    assert snapshot["status"] == "ok"
    assert snapshot["goals_checked"] == 1
    assert snapshot["loop_start_git"]["checkpoint_opportunity"] is True
    assert snapshot["loop_start_git"]["recommended_action"] == "checkpoint_before_more_work"
    goal_state_path = tmp_path / ".devflow" / "goals" / "G-0001" / "loop-state.json"
    assert goal_state_path.exists()
    goal_state = json.loads(goal_state_path.read_text(encoding="utf-8"))
    assert goal_state["canonical"] is False
    assert goal_state["source"] == "derived_freshness_loop"
    assert goal_state["goal"]["goal_id"] == "G-0001"
    assert goal_state["project_snapshot_path"] == ".devflow/freshness/latest.json"


def test_freshness_loop_appends_hash_chained_iteration_history(tmp_path: Path, monkeypatch) -> None:
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    brief_path = tmp_path / "my_goal.md"
    brief_path.write_text("## Goal Brief\nTrack loop history.", encoding="utf-8")

    runner = CliRunner()
    assert runner.invoke(app, ["goal", "init", "--from", "my_goal.md"]).exit_code == 0
    first = runner.invoke(app, ["freshness", "loop", "--json"])
    second = runner.invoke(app, ["freshness", "loop", "--json"])

    assert first.exit_code == 0
    assert second.exit_code == 0
    events_path = tmp_path / ".devflow" / "freshness" / "events.jsonl"
    events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines()]
    assert [event["event_index"] for event in events] == [0, 1]
    assert events[0]["previous_event_hash"] is None
    assert events[1]["previous_event_hash"] == events[0]["event_hash"]
    assert events[0]["event"] == "freshness_loop_iteration"
    assert events[0]["goal_loop"][0]["goal_id"] == "G-0001"


def test_freshness_loop_records_continue_decision_when_git_is_clean(tmp_path: Path, monkeypatch) -> None:
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    brief_path = tmp_path / "my_goal.md"
    brief_path.write_text("## Goal Brief\nImplement durables.", encoding="utf-8")

    runner = CliRunner()
    assert runner.invoke(app, ["goal", "init", "--from", "my_goal.md"]).exit_code == 0

    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "goal baseline"], cwd=tmp_path, check=True)

    result = runner.invoke(app, ["freshness", "loop", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["loop_start_git"]["recommended_action"] == "continue_loop"
    assert payload["loop_start_git"]["checkpoint_opportunity"] is False
    assert payload["loop_start_git"]["push_opportunity"] is False


def test_freshness_loop_records_push_opportunity_when_main_is_ahead(
    tmp_path: Path,
    monkeypatch,
) -> None:
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    origin = tmp_path.parent / "origin.git"
    subprocess.run(["git", "init", "--bare", origin.as_posix()], check=True)
    subprocess.run(["git", "remote", "add", "origin", origin.as_posix()], cwd=tmp_path, check=True)
    subprocess.run(["git", "push", "-u", "origin", "main"], cwd=tmp_path, check=True)

    brief_path = tmp_path / "my_goal.md"
    brief_path.write_text("## Goal Brief\nImplement durables.", encoding="utf-8")

    runner = CliRunner()
    assert runner.invoke(app, ["goal", "init", "--from", "my_goal.md"]).exit_code == 0
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "goal baseline"], cwd=tmp_path, check=True)

    result = runner.invoke(app, ["freshness", "loop", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["loop_start_git"]["recommended_action"] == "push_main"
    assert payload["loop_start_git"]["push_opportunity"] is True
    assert payload["loop_start_git"]["command"] == "devflow push-main"


def test_freshness_loop_all_projects_updates_registered_project_snapshots(
    tmp_path: Path,
    monkeypatch,
) -> None:
    home = _devflow_home(tmp_path, monkeypatch)
    projects_root = tmp_path / "projects"
    runner = CliRunner()

    alpha = runner.invoke(app, ["project", "create", "Alpha App", "--projects-root", projects_root.as_posix()])
    beta = runner.invoke(app, ["project", "create", "Beta App", "--projects-root", projects_root.as_posix()])
    assert alpha.exit_code == 0, alpha.output
    assert beta.exit_code == 0, beta.output

    alpha_root = projects_root / "alpha-app"
    brief_path = alpha_root / "goal.md"
    brief_path.write_text("## Goal Brief\nCoordinate parallel project work.", encoding="utf-8")
    monkeypatch.chdir(alpha_root)
    assert runner.invoke(app, ["goal", "init", "--from", "goal.md"]).exit_code == 0
    (alpha_root / ".devflow" / "goals" / "G-0001" / "task-slices.yaml").write_text(
        """
task_slices:
  - task_id: TS-0001
    title: Parallel project slice
    summary: Safe project-local work.
    parallel_safe: true
    risk: low
    execution_mode: AFK
""".lstrip(),
        encoding="utf-8",
    )
    shutil.rmtree(projects_root / "beta-app")

    result = runner.invoke(app, ["freshness", "loop", "--all-projects", "--json"])

    assert result.exit_code == 2
    payload = json.loads(result.output)
    assert payload["status"] == "needs_human_decision"
    assert payload["projects_checked"] == 2
    assert payload["missing_project_count"] == 1
    assert payload["snapshot_path"] == (home / "freshness" / "latest-all-projects.json").as_posix()
    assert (home / "freshness" / "latest-all-projects.json").is_file()
    assert (alpha_root / ".devflow" / "freshness" / "latest.json").is_file()

    projects = {project["project_id"]: project for project in payload["projects"]}
    assert projects["alpha-app"]["path_status"] == "present"
    assert projects["alpha-app"]["goals"][0]["goal_id"] == "G-0001"
    assert projects["alpha-app"]["goals"][0]["ready_parallel_lane_count"] == 1
    assert projects["alpha-app"]["checkpoint_opportunity"] is True
    assert projects["beta-app"]["path_status"] == "missing"
    assert projects["beta-app"]["status"] == "missing"


def test_freshness_loop_projects_goal_parallel_lanes(tmp_path: Path, monkeypatch) -> None:
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    brief_path = tmp_path / "my_goal.md"
    brief_path.write_text("## Goal Brief\nImplement parallel loop lanes.", encoding="utf-8")

    runner = CliRunner()
    assert runner.invoke(app, ["goal", "init", "--from", "my_goal.md"]).exit_code == 0

    slices_path = tmp_path / ".devflow" / "goals" / "G-0001" / "task-slices.yaml"
    slices_path.write_text(
        """
task_slices:
  - task_id: TS-0001
    title: Ready parallel slice
    summary: Can start independently.
    parallel_safe: true
    shared_files: [src/a.py]
    risk: low
    execution_mode: AFK
  - task_id: TS-0002
    title: Second parallel slice
    summary: Can run with TS-0001.
    parallel_safe: true
    shared_files: [src/b.py]
    risk: low
    execution_mode: AFK
  - task_id: TS-0003
    title: Conflicting parallel slice
    summary: Must not run with TS-0001.
    parallel_safe: true
    shared_files: [src/a.py]
    risk: low
    execution_mode: AFK
  - task_id: TS-0004
    title: Blocked slice
    summary: Depends on TS-0005.
    blocked_by: [TS-0005]
    parallel_safe: true
    risk: medium
    execution_mode: HITL
  - task_id: TS-0005
    title: Verified linked slice
    summary: Already has verified work.
    parallel_safe: true
    risk: medium
    execution_mode: HITL
  - task_id: TS-0006
    title: Running linked slice
    summary: Already has active work.
    parallel_safe: true
    risk: medium
    execution_mode: HITL
  - task_id: TS-0007
    title: Closed linked slice
    summary: Has closed evidence, not active promotion work.
    parallel_safe: true
    risk: medium
    execution_mode: HITL
""".lstrip(),
        encoding="utf-8",
    )

    assert runner.invoke(app, ["goal", "create-task", "G-0001", "TS-0005"]).exit_code == 0
    verified = get_task(tmp_path, "task-0001")
    verified.status = "verified"
    verified.verification_status = "passed"
    verified.updated_at = utc_now()
    save_task(tmp_path / ".devflow" / "tasks" / "task-0001", verified)

    assert runner.invoke(app, ["goal", "create-task", "G-0001", "TS-0006"]).exit_code == 0
    running = get_task(tmp_path, "task-0002")
    running.status = "running"
    running.verification_status = "pending"
    running.updated_at = utc_now()
    save_task(tmp_path / ".devflow" / "tasks" / "task-0002", running)

    assert runner.invoke(app, ["goal", "create-task", "G-0001", "TS-0007"]).exit_code == 0
    closed = get_task(tmp_path, "task-0003")
    closed.status = "closed"
    closed.verification_status = "passed"
    closed.updated_at = utc_now()
    save_task(tmp_path / ".devflow" / "tasks" / "task-0003", closed)

    result = runner.invoke(app, ["freshness", "loop", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    goal_loop = payload["goal_loop"][0]
    assert goal_loop["goal_id"] == "G-0001"
    assert goal_loop["loop_state"] == "ready_for_parallel_task_creation"
    assert goal_loop["ready_parallel_lane_count"] == 3
    assert goal_loop["ready_parallel_batch_count"] == 2
    assert goal_loop["conflicting_ready_lane_count"] == 1
    assert goal_loop["active_task_count"] == 2
    assert "Parallel batch PB-0001" in goal_loop["next_action"]
    assert "devflow goal create-task G-0001 TS-0001" in goal_loop["next_action"]
    assert "devflow goal create-task G-0001 TS-0002" in goal_loop["next_action"]

    lanes = {lane["slice_id"]: lane for lane in goal_loop["lanes"]}
    assert lanes["TS-0001"]["lane_state"] == "ready_to_create_task"
    assert lanes["TS-0001"]["command"] == "devflow goal create-task G-0001 TS-0001"
    assert lanes["TS-0001"]["shared_files"] == ["src/a.py"]
    assert lanes["TS-0002"]["lane_state"] == "ready_to_create_task"
    assert lanes["TS-0003"]["lane_state"] == "ready_to_create_task"
    assert lanes["TS-0004"]["lane_state"] == "blocked"
    assert lanes["TS-0004"]["blockers"] == ["TS-0005"]
    assert lanes["TS-0005"]["lane_state"] == "ready_to_promote"
    assert lanes["TS-0005"]["command"] == "devflow task promote-preview task-0001"
    assert lanes["TS-0006"]["lane_state"] == "running"
    assert lanes["TS-0006"]["command"] == "devflow task show task-0002"
    assert lanes["TS-0007"]["lane_state"] == "closed"
    assert lanes["TS-0007"]["command"] == "devflow task show task-0003"
    assert goal_loop["parallel_batches"][0]["lane_ids"] == ["TS-0001", "TS-0002"]
    assert goal_loop["parallel_batches"][0]["shared_files"] == ["src/a.py", "src/b.py"]
    assert goal_loop["parallel_batches"][1]["lane_ids"] == ["TS-0003"]
    assert goal_loop["parallel_batches"][1]["shared_files"] == ["src/a.py"]


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
