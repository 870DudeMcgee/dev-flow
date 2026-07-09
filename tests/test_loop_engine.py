from __future__ import annotations

import json
import subprocess
from pathlib import Path

import yaml
from typer.testing import CliRunner

from devflow.cli import app
from devflow.legacy.control_room.persistence import get_task
from tests.helpers import setup_temp_git_repo


runner = CliRunner()


def test_loop_init_show_list_and_unknown_action_refusal(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    initialized = runner.invoke(app, ["loop", "init", "daily", "--template", "goal-autopilot"])
    assert initialized.exit_code == 0, initialized.output
    config_path = tmp_path / ".devflow" / "loops" / "daily" / "loop.yaml"
    assert config_path.exists()
    assert "template: goal-autopilot" in config_path.read_text(encoding="utf-8")

    shown = runner.invoke(app, ["loop", "show", "daily", "--json"])
    assert shown.exit_code == 0, shown.output
    payload = json.loads(shown.output)
    assert payload["loop_id"] == "daily"
    assert payload["template"] == "goal-autopilot"
    assert payload["policy"]["allow_promotion"] is False

    listed = runner.invoke(app, ["loop", "list", "--json"])
    assert listed.exit_code == 0, listed.output
    assert json.loads(listed.output)["loops"] == ["daily"]

    bad_dir = tmp_path / ".devflow" / "loops" / "bad"
    bad_dir.mkdir(parents=True)
    (bad_dir / "loop.yaml").write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "loop_id": "bad",
                "template": "goal-autopilot",
                "actions": ["run_provider_worker"],
                "policy": {},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    refused = runner.invoke(app, ["loop", "show", "bad"])
    assert refused.exit_code == 1
    assert "Unknown loop action" in refused.output


def test_loop_run_creates_runs_verifies_previews_and_promotes_when_explicitly_allowed(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_goal_with_slice(
        tmp_path,
        risk="low",
        promotion_allowed=True,
        worker_command="printf loop-ok > result.txt",
        verification_command="test -f result.txt",
    )
    _init_loop(tmp_path, allow_promotion=True)

    result = runner.invoke(
        app,
        [
            "loop",
            "run",
            "daily",
            "--max-iterations",
            "6",
            "--max-parallel",
            "1",
            "--worker-timeout-seconds",
            "10",
            "--allow-workers",
            "--allow-verify",
            "--allow-promote",
            "--json",
        ],
    )

    assert result.exit_code == 2, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "blocked"
    assert payload["tasks_created"] == 1
    assert payload["workers_run"] == 1
    assert payload["verification_results"]["passed"] == 1
    assert payload["promotions_completed"] == 1
    assert payload["stop_reason"] == "freshness_needs_human_decision"
    assert (tmp_path / payload["evidence_path"]).is_file()
    assert (tmp_path / "result.txt").read_text(encoding="utf-8") == "loop-ok"
    assert get_task(tmp_path, "task-0001").status == "promoted"


def test_loop_run_requires_config_and_run_flag_before_promotion(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_goal_with_slice(
        tmp_path,
        risk="low",
        promotion_allowed=True,
        worker_command="printf gated > result.txt",
        verification_command="test -f result.txt",
    )
    _init_loop(tmp_path, allow_promotion=False)

    result = runner.invoke(
        app,
        [
            "loop",
            "run",
            "daily",
            "--max-iterations",
            "6",
            "--max-parallel",
            "1",
            "--worker-timeout-seconds",
            "10",
            "--allow-workers",
            "--allow-verify",
            "--allow-promote",
            "--json",
        ],
    )

    assert result.exit_code == 2, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "promotion_blocked"
    assert payload["stop_reason"] == "promotion_not_allowed_by_loop_config"
    assert payload["promotions_completed"] == 0
    assert not (tmp_path / "result.txt").exists()
    assert get_task(tmp_path, "task-0001").status == "verified"


def test_loop_run_promotes_standalone_verified_tasks_when_explicitly_allowed(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _init_loop(tmp_path, allow_promotion=True)
    created = runner.invoke(app, ["task", "create", "standalone verified task"])
    assert created.exit_code == 0, created.output
    worker = runner.invoke(app, ["task", "run", "task-0001", "--shell", "printf standalone > standalone.txt"])
    assert worker.exit_code == 0, worker.output
    verified = runner.invoke(app, ["task", "verify", "task-0001", "--shell", "test -f standalone.txt"])
    assert verified.exit_code == 0, verified.output

    result = runner.invoke(app, ["loop", "run", "daily", "--allow-promote", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "completed"
    assert payload["promotions_completed"] == 1
    assert payload["stop_reason"] == "no_projected_work"
    assert (tmp_path / "standalone.txt").read_text(encoding="utf-8") == "standalone"
    assert get_task(tmp_path, "task-0001").status == "promoted"


def test_loop_run_stops_for_open_questions_and_blocked_goals(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _init_loop(tmp_path)
    created = runner.invoke(app, ["task", "create", "blocked worker question"])
    assert created.exit_code == 0, created.output
    question_dir = tmp_path / ".devflow" / "tasks" / "task-0001" / "agents" / "devflow-manual-codex-worker"
    question_dir.mkdir(parents=True)
    (question_dir / "questions.jsonl").write_text(
        json.dumps(
            {
                "type": "blocked_question",
                "task_id": "task-0001",
                "agent_id": "devflow-manual-codex-worker",
                "question": "Which API should the worker preserve?",
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    question_run = runner.invoke(app, ["loop", "run", "daily", "--json"])
    assert question_run.exit_code == 2, question_run.output
    question_payload = json.loads(question_run.output)
    assert question_payload["status"] == "open_questions"
    assert question_payload["stop_reason"] == "open_questions"

    _answer_first_question()
    _write_goal_with_slice(
        tmp_path,
        risk="low",
        promotion_allowed=True,
        worker_command="printf blocked > blocked.txt",
        verification_command="test -f blocked.txt",
        goal_id="G-0001",
    )
    blocked = runner.invoke(app, ["goal", "block", "G-0001", "--reason", "needs product decision"])
    assert blocked.exit_code == 0, blocked.output

    blocked_run = runner.invoke(app, ["loop", "run", "daily", "--json"])
    assert blocked_run.exit_code == 2, blocked_run.output
    blocked_payload = json.loads(blocked_run.output)
    assert blocked_payload["status"] == "blocked"
    assert blocked_payload["stop_reason"] == "blocked_goals"


def test_loop_run_stops_for_dirty_git_worker_failure_and_verification_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    _init_loop(tmp_path)
    (tmp_path / "dirty.txt").write_text("unsafe", encoding="utf-8")

    dirty = runner.invoke(app, ["loop", "run", "daily", "--json"])
    assert dirty.exit_code == 2, dirty.output
    dirty_payload = json.loads(dirty.output)
    assert dirty_payload["status"] == "unsafe_git_state"
    assert dirty_payload["stop_reason"] == "unsafe_dirty_git_state"

    (tmp_path / "dirty.txt").unlink()
    _commit_all(tmp_path, "clean loop baseline")
    _write_goal_with_slice(
        tmp_path,
        risk="low",
        promotion_allowed=True,
        worker_command="exit 7",
        verification_command="test -f result.txt",
    )
    _commit_all(tmp_path, "worker failure goal")

    worker_failed = runner.invoke(
        app,
        [
            "loop",
            "run",
            "daily",
            "--max-iterations",
            "4",
            "--allow-workers",
            "--allow-verify",
            "--worker-timeout-seconds",
            "10",
            "--json",
        ],
    )
    assert worker_failed.exit_code == 2, worker_failed.output
    worker_payload = json.loads(worker_failed.output)
    assert worker_payload["status"] == "worker_failed"
    assert worker_payload["workers_run"] == 1

    scratch = tmp_path.parent / f"{tmp_path.name}-verify-failure"
    scratch.mkdir()
    monkeypatch.chdir(scratch)
    _write_goal_with_slice(
        scratch,
        risk="low",
        promotion_allowed=True,
        worker_command="printf no-file > result.txt",
        verification_command="test -f missing.txt",
    )
    _init_loop(scratch)

    verify_failed = runner.invoke(
        app,
        [
            "loop",
            "run",
            "daily",
            "--max-iterations",
            "5",
            "--allow-workers",
            "--allow-verify",
            "--worker-timeout-seconds",
            "10",
            "--json",
        ],
    )
    assert verify_failed.exit_code == 2, verify_failed.output
    verify_payload = json.loads(verify_failed.output)
    assert verify_payload["status"] == "verification_failed"
    assert verify_payload["verification_results"]["failed"] == 1
    assert verify_payload["promotions_completed"] == 0


def test_loop_run_stops_for_high_risk_promotion_and_repeated_no_progress(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_goal_with_slice(
        tmp_path,
        risk="high",
        promotion_allowed=True,
        worker_command="printf risky > risky.txt",
        verification_command="test -f risky.txt",
    )
    _init_loop(tmp_path, allow_promotion=True)
    created = runner.invoke(app, ["goal", "create-task", "G-0001", "TS-0001"])
    assert created.exit_code == 0, created.output
    worker = runner.invoke(app, ["task", "run", "task-0001", "--shell", "printf risky > risky.txt"])
    assert worker.exit_code == 0, worker.output
    verified = runner.invoke(app, ["task", "verify", "task-0001", "--shell", "test -f risky.txt"])
    assert verified.exit_code == 0, verified.output

    high_risk = runner.invoke(app, ["loop", "run", "daily", "--allow-promote", "--json"])
    assert high_risk.exit_code == 2, high_risk.output
    high_risk_payload = json.loads(high_risk.output)
    assert high_risk_payload["status"] == "promotion_blocked"
    assert high_risk_payload["stop_reason"] == "high_risk_promotion_blocked"

    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.chdir(empty)
    _init_loop(empty)

    no_progress = runner.invoke(app, ["loop", "run", "daily", "--max-iterations", "3", "--json"])
    assert no_progress.exit_code == 2, no_progress.output
    no_progress_payload = json.loads(no_progress.output)
    assert no_progress_payload["status"] == "no_progress"
    assert no_progress_payload["stop_reason"] == "repeated_state_hash"


def _init_loop(root: Path, *, allow_promotion: bool = False) -> None:
    result = runner.invoke(app, ["loop", "init", "daily", "--template", "goal-autopilot"])
    assert result.exit_code == 0, result.output
    if allow_promotion:
        path = root / ".devflow" / "loops" / "daily" / "loop.yaml"
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        payload["policy"]["allow_promotion"] = True
        path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _write_goal_with_slice(
    root: Path,
    *,
    risk: str,
    promotion_allowed: bool,
    worker_command: str,
    verification_command: str,
    goal_id: str = "G-0001",
) -> None:
    brief = root / f"{goal_id}.md"
    brief.write_text(f"# {goal_id}\n", encoding="utf-8")
    init = runner.invoke(app, ["goal", "init", goal_id, "--from", str(brief)])
    if init.exit_code != 0 and "already exists" not in init.output:
        assert init.exit_code == 0, init.output
    slices_path = root / ".devflow" / "goals" / goal_id / "task-slices.yaml"
    slices_path.write_text(
        yaml.safe_dump(
            {
                "task_slices": [
                    {
                        "task_id": "TS-0001",
                        "title": "Loop engine slice",
                        "summary": "Exercise the loop engine.",
                        "parallel_safe": True,
                        "shared_files": ["result.txt"],
                        "risk": risk,
                        "execution_mode": "AFK",
                        "promotion_allowed": promotion_allowed,
                        "worker_policy": {"shell_commands": [worker_command]},
                        "verification_policy": {"focused_commands": [verification_command]},
                    }
                ]
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def _answer_first_question() -> None:
    listed = runner.invoke(app, ["question", "list", "--json"])
    assert listed.exit_code == 0, listed.output
    question_id = json.loads(listed.output)["questions"][0]["question_id"]
    answered = runner.invoke(app, ["question", "answer", question_id, "--answer", "Use the existing API.", "--json"])
    assert answered.exit_code == 0, answered.output


def _commit_all(root: Path, message: str) -> None:
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-m", message], cwd=root, check=True)
