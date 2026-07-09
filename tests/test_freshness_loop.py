from __future__ import annotations

import json
import shutil
import subprocess
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import yaml
from typer.testing import CliRunner

from devflow.cli import app
from devflow.legacy.control_room.freshness import FreshnessReport, LoopStartGitDecision
from devflow.legacy.control_room.multi_project_freshness import run_multi_project_freshness_loop
from devflow.legacy.control_room.persistence import get_task, save_task, utc_now
from tests.helpers import setup_temp_git_repo


runner = CliRunner()


def _devflow_home(tmp_path: Path, monkeypatch) -> Path:
    home = tmp_path / "home" / ".devflow"
    monkeypatch.setenv("DEVFLOW_HOME", home.as_posix())
    return home


def _project_parallel_goal(tmp_path: Path, slices: list[tuple[str, str]]) -> None:
    setup_temp_git_repo(tmp_path)
    brief_path = tmp_path / "my_goal.md"
    brief_path.write_text("## Goal Brief\nImplement goal loop lanes.", encoding="utf-8")
    result = runner.invoke(app, ["goal", "init", "G-0001", "--from", str(brief_path)])
    assert result.exit_code == 0, result.output
    task_slices = [
        {
            "task_id": slice_id,
            "title": f"Slice {slice_id}",
            "summary": "Create one linked task.",
            "blocked_by": [],
            "parallel_safe": True,
            "shared_files": [shared_file],
            "risk": "low",
            "execution_mode": "AFK",
        }
        for slice_id, shared_file in slices
    ]
    slices_path = tmp_path / ".devflow" / "goals" / "G-0001" / "task-slices.yaml"
    slices_path.write_text(yaml.safe_dump({"task_slices": task_slices}, sort_keys=False), encoding="utf-8")


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


def test_freshness_loop_includes_review_readiness_counts(tmp_path: Path, monkeypatch) -> None:
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    runner = CliRunner()
    assert runner.invoke(app, ["task", "create", "ready review"]).exit_code == 0
    assert runner.invoke(app, ["task", "run", "task-0001", "--shell", "echo ready > result.txt"]).exit_code == 0
    verify = runner.invoke(app, ["task", "verify", "task-0001", "--shell", "test -f result.txt"])
    assert verify.exit_code == 0, verify.output
    (tmp_path / ".devflow" / "tasks" / "task-0001" / "promotion-preview.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "task_id": "task-0001",
                "promotion_readiness": "ready",
                "human_approval_required": False,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    assert runner.invoke(app, ["task", "create", "needs verify"]).exit_code == 0
    run = runner.invoke(app, ["task", "run", "task-0002", "--shell", "echo done > result.txt"])
    assert run.exit_code == 0, run.output

    assert runner.invoke(app, ["task", "create", "blocked task"]).exit_code == 0
    blocked = get_task(tmp_path, "task-0003")
    blocked.status = "blocked"
    blocked.updated_at = utc_now()
    save_task(tmp_path / ".devflow" / "tasks" / "task-0003", blocked)

    result = runner.invoke(app, ["freshness", "loop", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["ready_for_review_count"] == 1
    assert payload["needs_verification_count"] == 1
    assert payload["review_blocked_count"] == 1
    snapshot = json.loads((tmp_path / ".devflow" / "freshness" / "latest.json").read_text(encoding="utf-8"))
    assert snapshot["ready_for_review_count"] == 1
    assert snapshot["needs_verification_count"] == 1
    assert snapshot["review_blocked_count"] == 1


def test_freshness_loop_state_hash_changes_when_review_readiness_counts_change(
    tmp_path: Path,
    monkeypatch,
) -> None:
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    runner = CliRunner()
    assert runner.invoke(app, ["task", "create", "hash readiness"]).exit_code == 0
    run = runner.invoke(app, ["task", "run", "task-0001", "--shell", "echo done > result.txt"])
    assert run.exit_code == 0, run.output

    first = runner.invoke(app, ["freshness", "loop", "--json"])
    assert first.exit_code == 0, first.output
    first_payload = json.loads(first.output)
    assert first_payload["needs_verification_count"] == 1
    assert first_payload["ready_for_review_count"] == 0

    verify = runner.invoke(app, ["task", "verify", "task-0001", "--shell", "test -f result.txt"])
    assert verify.exit_code == 0, verify.output
    preview = runner.invoke(app, ["task", "promote-preview", "task-0001"])
    assert preview.exit_code == 0, preview.output

    second = runner.invoke(app, ["freshness", "loop", "--json"])
    assert second.exit_code == 0, second.output
    second_payload = json.loads(second.output)
    assert second_payload["needs_verification_count"] == 0
    assert second_payload["ready_for_review_count"] == 1
    assert first_payload["state_hash"] != second_payload["state_hash"]


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
    assert projects["alpha-app"]["goals"][0]["ready_worker_batch_count"] == 0
    assert projects["alpha-app"]["ready_worker_batch_count"] == 0
    assert projects["alpha-app"]["worker_command_count"] == 0
    assert projects["alpha-app"]["goals"][0]["ready_verification_batch_count"] == 0
    assert projects["alpha-app"]["ready_verification_batch_count"] == 0
    assert projects["alpha-app"]["checkpoint_opportunity"] is True
    assert projects["beta-app"]["path_status"] == "missing"
    assert projects["beta-app"]["status"] == "missing"
    expected_missing_next_action = (
        "Run `devflow project doctor beta-app`, then explicitly repair/import the real root, "
        "archive the project, or remove the registry-only junk record."
    )
    assert projects["beta-app"]["next_action"] == expected_missing_next_action
    assert payload["next_action"] == expected_missing_next_action


def test_multi_project_freshness_scans_registered_projects_in_parallel(
    tmp_path: Path,
    monkeypatch,
) -> None:
    roots = [tmp_path / name for name in ("alpha", "beta", "gamma")]
    for root in roots:
        root.mkdir()
    records = [
        SimpleNamespace(project_id="alpha", path=roots[0].as_posix()),
        SimpleNamespace(project_id="beta", path=roots[1].as_posix()),
        SimpleNamespace(project_id="gamma", path=roots[2].as_posix()),
    ]
    lock = threading.Lock()
    active = 0
    max_active = 0

    def fake_scan(root: Path, *, write_snapshot: bool = True) -> FreshnessReport:
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.05)
        with lock:
            active -= 1
        return FreshnessReport(
            generated_at="2026-06-04T00:00:00+00:00",
            status="ok",
            state_hash=root.name,
            loop_start_git=LoopStartGitDecision(
                is_repo=True,
                branch="main",
                head_sha=root.name,
                clean=True,
                checkpoint_opportunity=False,
                push_opportunity=False,
                recommended_action="continue_loop",
                reason="test",
            ),
            goals_checked=0,
            tasks_checked=0,
            linked_tasks_checked=0,
            stale_count=0,
            needs_human_decision_count=0,
            snapshot_path=".devflow/freshness/latest.json",
            next_action="Continue.",
        )

    monkeypatch.setattr("devflow.legacy.control_room.multi_project_freshness.list_project_records", lambda: records)
    monkeypatch.setattr("devflow.legacy.control_room.multi_project_freshness.run_freshness_loop", fake_scan)

    report = run_multi_project_freshness_loop(write_snapshot=False, max_parallel=2)

    assert max_active == 2
    assert [project.project_id for project in report.projects] == ["alpha", "beta", "gamma"]
    assert report.status == "ok"


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


def test_freshness_loop_projects_parallel_verification_batches(tmp_path: Path, monkeypatch) -> None:
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    brief_path = tmp_path / "my_goal.md"
    brief_path.write_text("## Goal Brief\nRun verification in safe batches.", encoding="utf-8")

    runner = CliRunner()
    assert runner.invoke(app, ["goal", "init", "--from", "my_goal.md"]).exit_code == 0

    slices_path = tmp_path / ".devflow" / "goals" / "G-0001" / "task-slices.yaml"
    slices_path.write_text(
        """
task_slices:
  - task_id: TS-0001
    title: First verification lane
    summary: Has a focused command.
    parallel_safe: true
    shared_files: [src/a.py]
    risk: low
    execution_mode: AFK
    verification_policy:
      focused_tests_required: true
      focused_commands:
        - pytest tests/test_a.py
  - task_id: TS-0002
    title: Second verification lane
    summary: Can verify with TS-0001.
    parallel_safe: true
    shared_files: [src/b.py]
    risk: low
    execution_mode: AFK
    verification_policy:
      focused_tests_required: true
      focused_commands:
        - pytest tests/test_b.py
  - task_id: TS-0003
    title: Conflicting verification lane
    summary: Must not verify beside TS-0001.
    parallel_safe: true
    shared_files: [src/a.py]
    risk: low
    execution_mode: AFK
    verification_policy:
      focused_tests_required: true
      focused_commands:
        - pytest tests/test_a_alt.py
  - task_id: TS-0004
    title: Retry previous verification
    summary: Uses the task's existing verification command.
    parallel_safe: true
    shared_files: [src/c.py]
    risk: low
    execution_mode: AFK
""".lstrip(),
        encoding="utf-8",
    )

    assert runner.invoke(app, ["goal", "create-task", "G-0001", "TS-0001"]).exit_code == 0
    assert runner.invoke(app, ["goal", "create-task", "G-0001", "TS-0002"]).exit_code == 0
    assert runner.invoke(app, ["goal", "create-task", "G-0001", "TS-0003"]).exit_code == 0
    assert runner.invoke(app, ["goal", "create-task", "G-0001", "TS-0004"]).exit_code == 0
    retry = get_task(tmp_path, "task-0004")
    retry.status = "verification_failed"
    retry.verification_status = "failed"
    retry.verification_command = "pytest tests/test_retry.py"
    retry.updated_at = utc_now()
    save_task(tmp_path / ".devflow" / "tasks" / "task-0004", retry)

    result = runner.invoke(app, ["freshness", "loop", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    goal_loop = payload["goal_loop"][0]
    assert goal_loop["ready_verification_batch_count"] == 2
    assert goal_loop["verification_command_count"] == 4

    lanes = {lane["slice_id"]: lane for lane in goal_loop["lanes"]}
    assert lanes["TS-0001"]["verification_scope"] == "focused"
    assert lanes["TS-0001"]["verification_commands"] == ["pytest tests/test_a.py"]
    assert lanes["TS-0002"]["verification_commands"] == ["pytest tests/test_b.py"]
    assert lanes["TS-0003"]["verification_commands"] == ["pytest tests/test_a_alt.py"]
    assert lanes["TS-0004"]["verification_scope"] == "custom"
    assert lanes["TS-0004"]["verification_commands"] == ["pytest tests/test_retry.py"]

    verify_batches = goal_loop["verification_batches"]
    assert verify_batches[0]["batch_id"] == "VB-0001"
    assert verify_batches[0]["lane_ids"] == ["TS-0001", "TS-0002", "TS-0004"]
    assert verify_batches[0]["task_ids"] == ["task-0001", "task-0002", "task-0004"]
    assert verify_batches[0]["commands"] == [
        "devflow task verify task-0001 -- pytest tests/test_a.py",
        "devflow task verify task-0002 -- pytest tests/test_b.py",
        "devflow task verify task-0004 -- pytest tests/test_retry.py",
    ]
    assert verify_batches[0]["items"][0] == {
        "lane_id": "TS-0001",
        "task_id": "task-0001",
        "command": "pytest tests/test_a.py",
        "devflow_command": "devflow task verify task-0001 -- pytest tests/test_a.py",
    }
    assert verify_batches[0]["shared_files"] == ["src/a.py", "src/b.py", "src/c.py"]
    assert verify_batches[0]["verification_scope"] == "mixed"
    assert verify_batches[1]["lane_ids"] == ["TS-0003"]
    assert verify_batches[1]["commands"] == [
        "devflow task verify task-0003 -- pytest tests/test_a_alt.py",
    ]
    assert verify_batches[1]["shared_files"] == ["src/a.py"]


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


def test_freshness_loop_recommends_activation_when_goal_lifecycle_missing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _project_parallel_goal(tmp_path, [("TS-0001", "src/a.py")])
    (tmp_path / ".devflow" / "goals" / "G-0001" / "goal-state.yaml").unlink(missing_ok=True)

    result = runner.invoke(app, ["freshness", "loop", "--json"])

    assert result.exit_code == 2, result.output
    payload = json.loads(result.output)
    goal_loop = payload["goal_loop"][0]
    assert goal_loop["loop_state"] == "needs_lifecycle_activation"
    assert "devflow goal activate G-0001" in goal_loop["next_action"]
    assert goal_loop["ready_parallel_batch_count"] == 0


def test_freshness_loop_suppresses_dispatch_for_paused_goal(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _project_parallel_goal(tmp_path, [("TS-0001", "src/a.py")])
    pause = runner.invoke(app, ["goal", "pause", "G-0001", "--reason", "waiting"])
    assert pause.exit_code == 0, pause.output

    result = runner.invoke(app, ["freshness", "loop", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    goal_loop = payload["goal_loop"][0]
    assert goal_loop["goal_state"] == "paused"
    assert goal_loop["loop_state"] == "paused"
    assert goal_loop["ready_parallel_lane_count"] == 0
    assert goal_loop["parallel_batches"] == []


def test_freshness_loop_recommends_goal_completion_when_all_slices_promoted(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _project_parallel_goal(tmp_path, [("TS-0001", "src/a.py")])
    subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True, text=True, check=True)
    subprocess.run(["git", "commit", "-m", "goal baseline"], cwd=tmp_path, capture_output=True, text=True, check=True)
    created = runner.invoke(app, ["freshness", "create-batch", "G-0001", "PB-0001"])
    assert created.exit_code == 0, created.output
    task = get_task(tmp_path, "task-0001")
    task.status = "promoted"
    task.updated_at = utc_now()
    save_task(tmp_path / ".devflow" / "tasks" / "task-0001", task)

    result = runner.invoke(app, ["freshness", "loop", "--json"])

    assert result.exit_code == 2, result.output
    payload = json.loads(result.output)
    goal_loop = payload["goal_loop"][0]
    assert goal_loop["loop_state"] == "needs_closure_decision"
    assert "devflow goal complete G-0001" in goal_loop["next_action"]
