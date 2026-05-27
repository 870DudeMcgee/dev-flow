from __future__ import annotations

import sys
import os
import subprocess
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from devflow.cli import app
from devflow.control_room.dashboard import create_app
from devflow.control_room.service import get_task


runner = CliRunner()


def test_shell_control_room_acceptance_gauntlet() -> None:
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            result = runner.invoke(app, ["init"])
            assert result.exit_code == 0, result.output
            assert Path(".devflow/devflow.db").exists()
            assert Path(".devflow/config.yaml").exists()
            assert Path(".devflow/tasks").is_dir()
            assert Path(".devflow/worktrees").is_dir()

            titles = ["succeeds", "fails", "times out"]
            for title in titles:
                result = runner.invoke(app, ["task", "create", title])
                assert result.exit_code == 0, result.output

            success = runner.invoke(
                app,
                [
                    "task",
                    "run",
                    "task-0001",
                    "--worker",
                    "shell",
                    "--",
                    sys.executable,
                    "-c",
                    "print('ok')",
                ],
            )
            assert success.exit_code == 0, success.output

            verified = runner.invoke(
                app,
                [
                    "task",
                    "verify",
                    "task-0001",
                    "--",
                    sys.executable,
                    "-c",
                    "print('verified')",
                ],
            )
            assert verified.exit_code == 0, verified.output

            failure = runner.invoke(
                app,
                [
                    "task",
                    "run",
                    "task-0002",
                    "--worker",
                    "shell",
                    "--",
                    sys.executable,
                    "-c",
                    "import sys; print('bad'); sys.exit(7)",
                ],
            )
            assert failure.exit_code == 1, failure.output

            timeout = runner.invoke(
                app,
                [
                    "task",
                    "run",
                    "task-0003",
                    "--worker",
                    "shell",
                    "--timeout-seconds",
                    "1",
                    "--",
                    sys.executable,
                    "-c",
                    "import time; print('slow'); time.sleep(5)",
                ],
            )
            assert timeout.exit_code == 1, timeout.output

            listing = runner.invoke(app, ["task", "list"])
            assert listing.exit_code == 0, listing.output
            assert "task-0001" in listing.output
            assert "complete" in listing.output
            assert "task-0002" in listing.output
            assert "worker_failed" in listing.output
            assert "task-0003" in listing.output
            assert "timeout" in listing.output

            assert get_task(Path.cwd(), "task-0001").status == "complete"
            assert get_task(Path.cwd(), "task-0001").verification_status == "passed"
            assert get_task(Path.cwd(), "task-0001").merge_ready is True
            assert get_task(Path.cwd(), "task-0002").status == "worker_failed"
            assert get_task(Path.cwd(), "task-0003").status == "timeout"

            for task_id in ["task-0001", "task-0002", "task-0003"]:
                show = runner.invoke(app, ["task", "show", task_id])
                assert show.exit_code == 0, show.output
                assert "log_path:" in show.output
                assert "result_path:" in show.output
                assert Path(f".devflow/tasks/{task_id}/logs/worker.log").exists()
                assert Path(f".devflow/tasks/{task_id}/result.md").exists()
            assert Path(".devflow/tasks/task-0001/logs/verify.log").read_text(encoding="utf-8").strip().endswith("verified")

            ready_show = runner.invoke(app, ["task", "show", "task-0001"])
            assert ready_show.exit_code == 0, ready_show.output
            assert "verification_status: passed" in ready_show.output
            assert "merge_ready: yes" in ready_show.output

            dashboard = TestClient(create_app(Path.cwd())).get("/")
            assert dashboard.status_code == 200
            assert "task-0001" in dashboard.text
            assert "complete" in dashboard.text
            assert "passed" in dashboard.text
            assert "worker_failed" in dashboard.text
            assert "timeout" in dashboard.text
            assert "worker.log" in dashboard.text
        finally:
            os.chdir(old_cwd)


def test_shell_task_uses_git_worktree_when_repo_has_head() -> None:
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            subprocess.run(["git", "init"], check=True, stdout=subprocess.DEVNULL)
            subprocess.run(["git", "config", "user.email", "tests@example.com"], check=True)
            subprocess.run(["git", "config", "user.name", "Devflow Tests"], check=True)
            Path("main.txt").write_text("main\n", encoding="utf-8")
            subprocess.run(["git", "add", "main.txt"], check=True)
            subprocess.run(["git", "commit", "-m", "init"], check=True, stdout=subprocess.DEVNULL)

            assert runner.invoke(app, ["init"]).exit_code == 0
            created = runner.invoke(app, ["task", "create", "isolated"])
            assert created.exit_code == 0, created.output

            task = get_task(Path.cwd(), "task-0001")
            assert task.workspace_kind == "git_worktree"
            assert task.branch_name == "devflow/task-0001"
            assert task.workspace_path is not None
            workspace = Path(task.workspace_path)
            assert (workspace / "main.txt").exists()

            run = runner.invoke(
                app,
                [
                    "task",
                    "run",
                    "task-0001",
                    "--worker",
                    "shell",
                    "--",
                    sys.executable,
                    "-c",
                    "from pathlib import Path; Path('worker.txt').write_text('workspace')",
                ],
            )
            assert run.exit_code == 0, run.output
            assert (workspace / "worker.txt").read_text(encoding="utf-8") == "workspace"
            assert not Path("worker.txt").exists()

            show = runner.invoke(app, ["task", "show", "task-0001"])
            assert show.exit_code == 0, show.output
            assert "workspace_kind: git_worktree" in show.output
            assert "branch_name: devflow/task-0001" in show.output

            verify = runner.invoke(
                app,
                [
                    "task",
                    "verify",
                    "task-0001",
                    "--",
                    sys.executable,
                    "-c",
                    "from pathlib import Path; assert Path('worker.txt').exists(); print('workspace verified')",
                ],
            )
            assert verify.exit_code == 0, verify.output
            task = get_task(Path.cwd(), "task-0001")
            assert task.verification_status == "passed"
            assert task.merge_ready is True
            assert task.verification_log_path is not None
            assert Path(task.verification_log_path).read_text(encoding="utf-8").strip().endswith("workspace verified")
        finally:
            os.chdir(old_cwd)


def test_failed_verification_blocks_merge_readiness() -> None:
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            assert runner.invoke(app, ["init"]).exit_code == 0
            assert runner.invoke(app, ["task", "create", "verify fails"]).exit_code == 0
            run = runner.invoke(app, ["task", "run", "task-0001", "--worker", "shell", "--", sys.executable, "-c", "print('done')"])
            assert run.exit_code == 0, run.output

            verify = runner.invoke(
                app,
                ["task", "verify", "task-0001", "--", sys.executable, "-c", "import sys; print('nope'); sys.exit(2)"],
            )
            assert verify.exit_code == 1, verify.output
            task = get_task(Path.cwd(), "task-0001")
            assert task.verification_status == "failed"
            assert task.verification_exit_code == 2
            assert task.merge_ready is False
            assert task.verification_log_path is not None
            assert Path(task.verification_log_path).read_text(encoding="utf-8").strip().endswith("nope")
        finally:
            os.chdir(old_cwd)
