from __future__ import annotations

import json
import os
import tempfile
import hashlib
from pathlib import Path
from typer.testing import CliRunner

from devflow.cli import app
from devflow.control_room.persistence import get_task, load_task

runner = CliRunner()

def test_dashboard_shows_empty_state() -> None:
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            # Run devflow dashboard when there are no tasks
            res = runner.invoke(app, ["dashboard"])
            assert res.exit_code == 0, res.output
            assert "Dev-Flow Control Room" in res.output
            assert "Total: 0" in res.output
            assert "No tasks found" in res.output
            
            # Check next action recommended command
            res_next = runner.invoke(app, ["next"])
            assert res_next.exit_code == 0, res_next.output
            assert "devflow task create" in res_next.output
        finally:
            os.chdir(old_cwd)

def test_status_alias_matches_dashboard_essentials() -> None:
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            # Create a task
            assert runner.invoke(app, ["task", "create", "test task"]).exit_code == 0
            
            dash = runner.invoke(app, ["dashboard"])
            status = runner.invoke(app, ["status"])
            
            assert dash.exit_code == 0, dash.output
            assert status.exit_code == 0, status.output
            
            # Essentials matching
            assert "Dev-Flow Control Room" in dash.output
            assert "Dev-Flow Control Room" in status.output
            assert "task-0001" in dash.output
            assert "task-0001" in status.output
            assert "test task" in dash.output
            assert "test task" in status.output
        finally:
            os.chdir(old_cwd)

def test_dashboard_json_is_machine_readable() -> None:
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            assert runner.invoke(app, ["task", "create", "json task"]).exit_code == 0
            
            res = runner.invoke(app, ["dashboard", "--json"])
            assert res.exit_code == 0, res.output
            
            data = json.loads(res.output)
            assert "project" in data
            assert "health" in data
            assert "focus_task" in data
            assert "next_action" in data
            assert "tasks" in data
            
            assert data["health"]["total_tasks"] == 1
            assert data["next_action"]["command"] is not None
            
            # Verify no Path objects serialized directly (should be strings)
            # Path serialization check is implicitly handled by json.loads working successfully.
        finally:
            os.chdir(old_cwd)

def test_dashboard_shows_needs_verification() -> None:
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            assert runner.invoke(app, ["task", "create", "needs verify task"]).exit_code == 0
            
            # Run task successfully so status is complete
            run_res = runner.invoke(app, ["task", "run", "task-0001", "--shell", "echo done"])
            assert run_res.exit_code == 0, run_res.output
            
            # Do not verify yet
            dash = runner.invoke(app, ["dashboard"])
            assert dash.exit_code == 0, dash.output
            assert "Needs verification: 1" in dash.output
            assert "task-0001  needs verification" in dash.output
            assert "devflow task verify task-0001 --shell" in dash.output
        finally:
            os.chdir(old_cwd)

def test_dashboard_shows_failed_verification() -> None:
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            assert runner.invoke(app, ["task", "create", "failing verify task"]).exit_code == 0
            assert runner.invoke(app, ["task", "run", "task-0001", "--shell", "echo done"]).exit_code == 0
            
            # Run verification with failing command
            verify_res = runner.invoke(app, ["task", "verify", "task-0001", "--shell", "exit 3"])
            assert verify_res.exit_code == 3, verify_res.output
            
            dash = runner.invoke(app, ["dashboard"])
            assert dash.exit_code == 0, dash.output
            assert "Failed verification: 1" in dash.output
            assert "task-0001  verification failed" in dash.output
            assert "devflow task log task-0001 --verify --tail 80" in dash.output
        finally:
            os.chdir(old_cwd)

def test_dashboard_shows_ready_to_promote_after_verification() -> None:
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            assert runner.invoke(app, ["task", "create", "promote task"]).exit_code == 0
            assert runner.invoke(app, ["task", "run", "task-0001", "--shell", "echo done"]).exit_code == 0
            
            # Verify successfully
            verify_res = runner.invoke(app, ["task", "verify", "task-0001", "--shell", "echo verified"])
            assert verify_res.exit_code == 0, verify_res.output
            
            dash = runner.invoke(app, ["dashboard"])
            assert dash.exit_code == 0, dash.output
            assert "Ready to promote: 1" in dash.output
            assert "task-0001  ready to promote" in dash.output
            assert "devflow task promote-preview task-0001" in dash.output
        finally:
            os.chdir(old_cwd)

def test_devflow_next_prints_one_action() -> None:
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            assert runner.invoke(app, ["task", "create", "next task"]).exit_code == 0
            
            res = runner.invoke(app, ["next"])
            assert res.exit_code == 0, res.output
            assert "Next Action" in res.output
            # Check exactly one command line
            assert "devflow task run task-0001 --worker shell" in res.output
        finally:
            os.chdir(old_cwd)

def test_task_history_renders_events() -> None:
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            assert runner.invoke(app, ["task", "create", "history task"]).exit_code == 0
            assert runner.invoke(app, ["task", "run", "task-0001", "--shell", "echo run"]).exit_code == 0
            assert runner.invoke(app, ["task", "verify", "task-0001", "--shell", "echo verify"]).exit_code == 0
            
            res = runner.invoke(app, ["task", "history", "task-0001"])
            assert res.exit_code == 0, res.output
            assert "Task History" in res.output
            assert "task_created" in res.output
            assert "worker_started" in res.output
            assert "worker_finished" in res.output
            assert "verification_started" in res.output
            assert "verification_finished" in res.output
        finally:
            os.chdir(old_cwd)

def test_dashboard_status_next_history_are_read_only() -> None:
    def get_dir_hashes(d: Path) -> dict[Path, str]:
        hashes = {}
        for p in d.rglob("*"):
            if p.is_file():
                hashes[p] = hashlib.sha256(p.read_bytes()).hexdigest()
        return hashes

    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            assert runner.invoke(app, ["task", "create", "readonly task"]).exit_code == 0
            assert runner.invoke(app, ["task", "run", "task-0001", "--shell", "echo run"]).exit_code == 0
            
            task_dir = Path(".devflow/tasks/task-0001")
            hashes_before = get_dir_hashes(task_dir)
            
            # Invoke all read-only dashboard/status/next/history commands
            assert runner.invoke(app, ["dashboard"]).exit_code == 0
            assert runner.invoke(app, ["dashboard", "--json"]).exit_code == 0
            assert runner.invoke(app, ["status"]).exit_code == 0
            assert runner.invoke(app, ["next"]).exit_code == 0
            assert runner.invoke(app, ["task", "history", "task-0001"]).exit_code == 0
            
            hashes_after = get_dir_hashes(task_dir)
            
            # Assert they are absolutely byte-for-byte identical
            assert hashes_before == hashes_after
        finally:
            os.chdir(old_cwd)

def test_no_database_or_web_artifacts_created() -> None:
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            assert runner.invoke(app, ["task", "create", "artifacts task"]).exit_code == 0
            
            # Invoke commands
            runner.invoke(app, ["dashboard"])
            runner.invoke(app, ["dashboard", "--json"])
            runner.invoke(app, ["status"])
            runner.invoke(app, ["next"])
            runner.invoke(app, ["task", "history", "task-0001"])
            
            # Check db doesn't exist
            assert not Path(".devflow/devflow.db").exists()
            # Assert no new persistent artifacts/web directories are created under workspace
            for root, dirs, files in os.walk(".devflow"):
                for d in dirs:
                    assert d not in ("web", "ui", "server", "db")
        finally:
            os.chdir(old_cwd)
