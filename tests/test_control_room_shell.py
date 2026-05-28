from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import NoReturn

import pytest
from typer.testing import CliRunner

from devflow.cli import app
from devflow.control_room.service import get_task
from devflow.control_room.shell_worker import ShellWorkerAdapter
from devflow.control_room.worker_adapter import UnsupportedWorkerAdapter, get_worker_adapter


runner = CliRunner()


def test_frozen_shell_worker_mvp_contract() -> None:
    help_result = runner.invoke(app, ["--help"])
    assert help_result.exit_code == 0, help_result.output
    assert "Dev-Flow local control room" in help_result.output
    assert "task" in help_result.output

    task_help = runner.invoke(app, ["task", "--help"])
    assert task_help.exit_code == 0, task_help.output
    assert "create" in task_help.output
    assert "run" in task_help.output
    assert "verify" in task_help.output
    assert "list" in task_help.output
    assert "show" in task_help.output

    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            Path("project.txt").write_text("main checkout\n", encoding="utf-8")

            for title in ["example task", "fails", "times out"]:
                created = runner.invoke(app, ["task", "create", title])
                assert created.exit_code == 0, created.output

            assert Path(".devflow/tasks").is_dir()
            assert Path(".devflow/workspaces").is_dir()
            assert not Path(".devflow/devflow.db").exists()
            assert not Path(".devflow/worktrees").exists()

            first_yaml = Path(".devflow/tasks/task-0001/task.yaml").read_text(encoding="utf-8")
            assert 'status: "created"' in first_yaml
            assert 'workspace: ".devflow/workspaces/task-0001"' in first_yaml
            assert Path(".devflow/tasks/task-0001/events.jsonl").exists()
            assert Path(".devflow/tasks/task-0001/verification.json").exists()
            assert Path(".devflow/tasks/task-0001/logs/worker.log").exists()
            assert Path(".devflow/tasks/task-0001/logs/verify.log").exists()
            assert Path(".devflow/workspaces/task-0001/project.txt").read_text(encoding="utf-8") == "main checkout\n"

            success = runner.invoke(
                app,
                [
                    "task",
                    "run",
                    "task-0001",
                    "--shell",
                    "printf workspace > worker.txt && echo ok",
                ],
            )
            assert success.exit_code == 0, success.output
            assert Path(".devflow/workspaces/task-0001/worker.txt").read_text(encoding="utf-8") == "workspace"
            assert not Path("worker.txt").exists()

            verified = runner.invoke(
                app,
                [
                    "task",
                    "verify",
                    "task-0001",
                    "--shell",
                    "test -f worker.txt && echo verified",
                ],
            )
            assert verified.exit_code == 0, verified.output

            failure = runner.invoke(
                app,
                [
                    "task",
                    "run",
                    "task-0002",
                    "--shell",
                    "echo bad; exit 7",
                ],
            )
            assert failure.exit_code == 1, failure.output

            timeout = runner.invoke(
                app,
                [
                    "task",
                    "run",
                    "task-0003",
                    "--timeout-seconds",
                    "1",
                    "--shell",
                    "echo slow; sleep 5",
                ],
            )
            assert timeout.exit_code == 1, timeout.output

            assert get_task(Path.cwd(), "task-0001").status == "verified"
            assert get_task(Path.cwd(), "task-0001").verification_status == "passed"
            assert get_task(Path.cwd(), "task-0002").status == "worker_failed"
            assert get_task(Path.cwd(), "task-0003").status == "timeout"

            listing = runner.invoke(app, ["task", "list"])
            assert listing.exit_code == 0, listing.output
            assert "task-0001" in listing.output
            assert "verified" in listing.output
            assert "task-0002" in listing.output
            assert "worker_failed" in listing.output
            assert "task-0003" in listing.output
            assert "timeout" in listing.output

            show = runner.invoke(app, ["task", "show", "task-0001"])
            assert show.exit_code == 0, show.output
            assert "workspace: .devflow/workspaces/task-0001" in show.output
            assert "verification_status: passed" in show.output
            assert "last_event: verification_finished" in show.output

            verification = json.loads(Path(".devflow/tasks/task-0001/verification.json").read_text(encoding="utf-8"))
            assert verification["status"] == "passed"
            assert verification["task_status"] == "verified"
            assert Path(".devflow/tasks/task-0001/logs/worker.log").read_text(encoding="utf-8").strip().endswith("ok")
            assert Path(".devflow/tasks/task-0001/logs/verify.log").read_text(encoding="utf-8").strip().endswith("verified")

            events = [
                json.loads(line)
                for line in Path(".devflow/tasks/task-0001/events.jsonl").read_text(encoding="utf-8").splitlines()
            ]
            assert [event["event"] for event in events] == [
                "task_created",
                "worker_started",
                "worker_finished",
                "verification_started",
                "verification_finished",
            ]
        finally:
            os.chdir(old_cwd)


def test_shell_worker_mvp_heartbeat_with_shell_command_option() -> None:
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            Path("main.txt").write_text("main checkout\n", encoding="utf-8")

            created = runner.invoke(app, ["task", "create", "example task"])
            assert created.exit_code == 0, created.output

            run = runner.invoke(app, ["task", "run", "task-0001", "--shell", "echo hello > result.txt"])
            assert run.exit_code == 0, run.output
            assert "task-0001: complete" in run.output
            assert "result_path: .devflow/tasks/task-0001/result.md" in run.output

            verify = runner.invoke(app, ["task", "verify", "task-0001", "--shell", "test -f result.txt"])
            assert verify.exit_code == 0, verify.output
            assert "task-0001: verification passed" in verify.output

            workspace_result = Path(".devflow/workspaces/task-0001/result.txt")
            assert workspace_result.read_text(encoding="utf-8") == "hello\n"
            assert not Path("result.txt").exists()
            assert not Path(".devflow/devflow.db").exists()
            assert not Path(".devflow/worktrees").exists()

            task_dir = Path(".devflow/tasks/task-0001")
            assert (task_dir / "task.yaml").exists()
            assert (task_dir / "logs" / "worker.log").exists()
            assert (task_dir / "logs" / "verify.log").exists()
            verification = json.loads((task_dir / "verification.json").read_text(encoding="utf-8"))
            assert verification["status"] == "passed"
            assert verification["task_status"] == "verified"

            events = [json.loads(line)["event"] for line in (task_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()]
            assert events == [
                "task_created",
                "worker_started",
                "worker_finished",
                "verification_started",
                "verification_finished",
            ]

            listing = runner.invoke(app, ["task", "list"])
            assert listing.exit_code == 0, listing.output
            assert "Task" in listing.output
            assert "Status" in listing.output
            assert "Verify" in listing.output
            assert "Updated" in listing.output
            assert "Title" in listing.output
            assert "task-0001" in listing.output
            assert "verified" in listing.output
            assert "passed" in listing.output
            assert "example task" in listing.output

            show = runner.invoke(app, ["task", "show", "task-0001"])
            assert show.exit_code == 0, show.output
            assert "title: example task" in show.output
            assert "status: verified" in show.output
            assert "workspace: .devflow/workspaces/task-0001" in show.output
            assert "result_path: .devflow/tasks/task-0001/result.md" in show.output
            assert "verification_status: passed" in show.output
            assert "verification_log_path: .devflow/tasks/task-0001/logs/verify.log" in show.output
            assert "latest_events:" in show.output
            assert "worker_finished" in show.output
            assert "verification_finished" in show.output
            assert "result_summary:" in show.output
            assert "Worker completed successfully" in show.output
        finally:
            os.chdir(old_cwd)


def test_unsupported_worker_adapter_values_are_refused() -> None:
    with pytest.raises(UnsupportedWorkerAdapter, match="Unsupported worker adapter 'codex'. Only 'shell' is available"):
        get_worker_adapter("codex")

    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            created = runner.invoke(app, ["task", "create", "adapter refusal"])
            assert created.exit_code == 0, created.output

            run = runner.invoke(
                app,
                ["task", "run", "task-0001", "--worker", "codex", "--shell", "echo should-not-run"],
            )
            assert run.exit_code == 1, run.output
            assert "Unsupported worker adapter 'codex'. Only 'shell' is available in the MVP." in run.output
            assert Path(".devflow/tasks/task-0001/logs/worker.log").read_text(encoding="utf-8") == ""
            assert get_task(Path.cwd(), "task-0001").status == "created"
        finally:
            os.chdir(old_cwd)


def test_verification_remains_devflow_owned_not_adapter_owned(monkeypatch: pytest.MonkeyPatch) -> None:
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            assert runner.invoke(app, ["task", "create", "verify owner"]).exit_code == 0
            run = runner.invoke(app, ["task", "run", "task-0001", "--shell", "echo hello > result.txt"])
            assert run.exit_code == 0, run.output

            def fail_if_adapter_runs(*_args: object, **_kwargs: object) -> NoReturn:
                raise AssertionError("verification must not run through worker adapters")

            monkeypatch.setattr(ShellWorkerAdapter, "run", fail_if_adapter_runs)

            verify = runner.invoke(app, ["task", "verify", "task-0001", "--shell", "test -f result.txt"])
            assert verify.exit_code == 0, verify.output

            task = get_task(Path.cwd(), "task-0001")
            assert task.status == "verified"
            assert task.verification_status == "passed"
            assert task.verification_log_path == ".devflow/tasks/task-0001/logs/verify.log"
            verification = json.loads(Path(".devflow/tasks/task-0001/verification.json").read_text(encoding="utf-8"))
            assert verification["status"] == "passed"
            assert Path(verification["log_path"]).read_text(encoding="utf-8").startswith("$ /bin/sh -c test -f result.txt")
        finally:
            os.chdir(old_cwd)


def test_failed_verification_updates_canonical_task_yaml() -> None:
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            assert runner.invoke(app, ["task", "create", "verify fails"]).exit_code == 0
            run = runner.invoke(app, ["task", "run", "task-0001", "--shell", "echo done"])
            assert run.exit_code == 0, run.output

            verify = runner.invoke(
                app,
                ["task", "verify", "task-0001", "--shell", "echo nope; exit 2"],
            )
            assert verify.exit_code == 1, verify.output
            task = get_task(Path.cwd(), "task-0001")
            assert task.status == "verification_failed"
            assert task.verification_status == "failed"
            assert task.verification_exit_code == 2
            assert task.verification_log_path == ".devflow/tasks/task-0001/logs/verify.log"
            assert Path(task.verification_log_path).read_text(encoding="utf-8").strip().endswith("nope")
            task_yaml = Path(".devflow/tasks/task-0001/task.yaml").read_text(encoding="utf-8")
            assert 'status: "verification_failed"' in task_yaml
            assert 'verification_status: "failed"' in task_yaml
        finally:
            os.chdir(old_cwd)


def test_obviously_destructive_shell_command_is_refused() -> None:
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            assert runner.invoke(app, ["task", "create", "blocked"]).exit_code == 0

            run = runner.invoke(app, ["task", "run", "task-0001", "--shell", "rm -rf /"])
            assert run.exit_code == 1, run.output
            assert "Refusing obviously destructive command" in run.output
            task = get_task(Path.cwd(), "task-0001")
            assert task.status == "blocked"
            assert "command_refused" in Path(".devflow/tasks/task-0001/events.jsonl").read_text(encoding="utf-8")
        finally:
            os.chdir(old_cwd)


def test_shell_worker_refuses_tampered_workspace_path() -> None:
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            assert runner.invoke(app, ["task", "create", "tampered"]).exit_code == 0
            _replace_workspace("task-0001", ".")

            run = runner.invoke(
                app,
                [
                    "task",
                    "run",
                    "task-0001",
                    "--shell",
                    "echo bad > main_checkout_write.txt",
                ],
            )
            assert run.exit_code == 1, run.output
            assert "Refusing unsafe task workspace" in run.output
            assert not Path("main_checkout_write.txt").exists()
            assert "workspace_refused" in Path(".devflow/tasks/task-0001/events.jsonl").read_text(encoding="utf-8")
        finally:
            os.chdir(old_cwd)


def test_verification_refuses_tampered_workspace_path() -> None:
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            assert runner.invoke(app, ["task", "create", "tampered verify"]).exit_code == 0
            _replace_workspace("task-0001", ".")

            verify = runner.invoke(
                app,
                [
                    "task",
                    "verify",
                    "task-0001",
                    "--shell",
                    "echo bad > main_checkout_verify.txt",
                ],
            )
            assert verify.exit_code == 1, verify.output
            assert "Refusing unsafe task workspace" in verify.output
            assert not Path("main_checkout_verify.txt").exists()
            assert "workspace_refused" in Path(".devflow/tasks/task-0001/events.jsonl").read_text(encoding="utf-8")
        finally:
            os.chdir(old_cwd)


def test_workspace_copy_skips_symlinks_without_following_them() -> None:
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            Path("outside.txt").write_text("outside\n", encoding="utf-8")
            Path("normal.txt").write_text("normal\n", encoding="utf-8")
            Path("outside-link.txt").symlink_to(Path.cwd() / "outside.txt")

            created = runner.invoke(app, ["task", "create", "symlink skip"])
            assert created.exit_code == 0, created.output

            workspace = Path(".devflow/workspaces/task-0001")
            assert (workspace / "normal.txt").read_text(encoding="utf-8") == "normal\n"
            assert not (workspace / "outside-link.txt").exists()
            assert not (workspace / "outside-link.txt").is_symlink()
            assert Path("outside.txt").read_text(encoding="utf-8") == "outside\n"

            run = runner.invoke(
                app,
                [
                    "task",
                    "run",
                    "task-0001",
                    "--shell",
                    "test ! -e outside-link.txt && test ! -L outside-link.txt && echo checked",
                ],
            )
            assert run.exit_code == 0, run.output
            assert Path("outside.txt").read_text(encoding="utf-8") == "outside\n"
            events = Path(".devflow/tasks/task-0001/events.jsonl").read_text(encoding="utf-8")
            assert "skipped_symlinks" in events
            assert "outside-link.txt" in events
        finally:
            os.chdir(old_cwd)


def _replace_workspace(task_id: str, workspace: str) -> None:
    yaml_path = Path(".devflow/tasks") / task_id / "task.yaml"
    lines = yaml_path.read_text(encoding="utf-8").splitlines()
    updated = [f'workspace: "{workspace}"' if line.startswith("workspace:") else line for line in lines]
    yaml_path.write_text("\n".join(updated) + "\n", encoding="utf-8")


def test_task_create_with_dirty_worktree() -> None:
    import subprocess
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            subprocess.run(["git", "init", "-b", "main"], check=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], check=True)
            subprocess.run(["git", "config", "user.name", "Test User"], check=True)

            Path("file.txt").write_text("commit content\n", encoding="utf-8")
            subprocess.run(["git", "add", "file.txt"], check=True)
            subprocess.run(["git", "commit", "-m", "first commit"], check=True)

            # Make a dirty change in the main worktree
            Path("file.txt").write_text("dirty content\n", encoding="utf-8")

            # Run devflow task create
            created = runner.invoke(app, ["task", "create", "dirty-test-task"])
            assert created.exit_code == 0, created.output
            assert "Warning: Main worktree has uncommitted changes" in created.output

            task = get_task(Path.cwd(), "task-0001")
            assert task.branch_name == "main"
            assert task.workspace_dirty is True
            assert task.workspace_commit is not None

            # The dirty content should be copied to the workspace
            assert Path(".devflow/workspaces/task-0001/file.txt").read_text(encoding="utf-8") == "dirty content\n"
        finally:
            os.chdir(old_cwd)


def test_task_create_outside_git_repo() -> None:
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            created = runner.invoke(app, ["task", "create", "outside-git"])
            assert created.exit_code == 0, created.output
            assert "Warning:" not in created.output

            task = get_task(Path.cwd(), "task-0001")
            assert task.branch_name is None
            assert task.workspace_commit is None
            assert task.workspace_dirty is False

            show = runner.invoke(app, ["task", "show", "task-0001"])
            assert show.exit_code == 0, show.output
            assert "branch_name" not in show.output
            assert "workspace_commit" not in show.output
            assert "workspace_dirty: false" in show.output
        finally:
            os.chdir(old_cwd)


def test_task_create_new_git_repo_no_commits() -> None:
    import subprocess
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            subprocess.run(["git", "init", "-b", "main"], check=True)
            created = runner.invoke(app, ["task", "create", "new-git-no-commits"])
            assert created.exit_code == 0, created.output
            assert "Warning:" not in created.output

            task = get_task(Path.cwd(), "task-0001")
            assert task.branch_name == "main"
            assert task.workspace_commit is None
            assert task.workspace_dirty is False

            show = runner.invoke(app, ["task", "show", "task-0001"])
            assert show.exit_code == 0, show.output
            assert "branch_name: main" in show.output
            assert "workspace_commit" not in show.output
            assert "workspace_dirty: false" in show.output
        finally:
            os.chdir(old_cwd)


def test_task_create_clean_git_repo() -> None:
    import subprocess
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            subprocess.run(["git", "init", "-b", "main"], check=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], check=True)
            subprocess.run(["git", "config", "user.name", "Test User"], check=True)

            Path("file.txt").write_text("clean content\n", encoding="utf-8")
            subprocess.run(["git", "add", "file.txt"], check=True)
            subprocess.run(["git", "commit", "-m", "first commit"], check=True)

            created = runner.invoke(app, ["task", "create", "clean-git"])
            assert created.exit_code == 0, created.output
            assert "Warning:" not in created.output

            task = get_task(Path.cwd(), "task-0001")
            assert task.branch_name == "main"
            assert task.workspace_commit is not None
            assert task.workspace_dirty is False

            show = runner.invoke(app, ["task", "show", "task-0001"])
            assert show.exit_code == 0, show.output
            assert "branch_name: main" in show.output
            assert "workspace_commit:" in show.output
            assert "workspace_dirty: false" in show.output
        finally:
            os.chdir(old_cwd)


def test_verification_result_rich_metadata() -> None:
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            # Create a task
            created = runner.invoke(app, ["task", "create", "verify rich metadata"])
            assert created.exit_code == 0, created.output

            # Check the initial verification.json
            init_json = json.loads(Path(".devflow/tasks/task-0001/verification.json").read_text(encoding="utf-8"))
            assert init_json["task_id"] == "task-0001"
            assert init_json["workspace"] == ".devflow/workspaces/task-0001"
            assert init_json["status"] == "not_run"
            assert init_json["task_status"] == "created"
            assert init_json["exit_code"] is None
            assert init_json["finished_at"] is None

            # Run task
            run = runner.invoke(app, ["task", "run", "task-0001", "--shell", "echo done"])
            assert run.exit_code == 0

            # Run verify (passed)
            verify = runner.invoke(app, ["task", "verify", "task-0001", "--shell", "echo passing; exit 0"])
            assert verify.exit_code == 0

            # Check verification.json for successful run
            pass_json = json.loads(Path(".devflow/tasks/task-0001/verification.json").read_text(encoding="utf-8"))
            assert pass_json["task_id"] == "task-0001"
            assert pass_json["workspace"] == ".devflow/workspaces/task-0001"
            assert pass_json["status"] == "passed"
            assert pass_json["task_status"] == "verified"
            assert pass_json["exit_code"] == 0
            assert pass_json["finished_at"] is not None

            # Validate ISO format of finished_at
            from datetime import datetime
            datetime.fromisoformat(pass_json["finished_at"])

            # Verify command serialization is stable
            assert pass_json["command"] == ["/bin/sh", "-c", "echo passing; exit 0"]

            assert pass_json["log_path"] == ".devflow/tasks/task-0001/logs/verify.log"
            # Verify that verify.log exists at the path written in verification.json
            assert Path(pass_json["log_path"]).exists()

            # Check that verification event is appended in events.jsonl
            events = [
                json.loads(line)
                for line in Path(".devflow/tasks/task-0001/events.jsonl").read_text(encoding="utf-8").splitlines()
            ]
            verify_events = [e for e in events if e["event"] == "verification_finished"]
            assert len(verify_events) == 1
            assert verify_events[0]["status"] == "passed"
            assert verify_events[0]["exit_code"] == 0
            assert verify_events[0]["log_path"] == ".devflow/tasks/task-0001/logs/verify.log"

            # Run verify (failed)
            verify_fail = runner.invoke(app, ["task", "verify", "task-0001", "--shell", "echo failing; exit 42"])
            assert verify_fail.exit_code == 1

            # Check verification.json for failed run
            fail_json = json.loads(Path(".devflow/tasks/task-0001/verification.json").read_text(encoding="utf-8"))
            assert fail_json["task_id"] == "task-0001"
            assert fail_json["status"] == "failed"
            assert fail_json["task_status"] == "verification_failed"
            assert fail_json["exit_code"] == 42
        finally:
            os.chdir(old_cwd)


def test_task_merge_readiness_lifecycle() -> None:
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            # Create a task
            created = runner.invoke(app, ["task", "create", "readiness task"])
            assert created.exit_code == 0, created.output

            # 1. Check initial merge-readiness.json (not ready)
            mr_path = Path(".devflow/tasks/task-0001/merge-readiness.json")
            assert mr_path.exists()
            mr_data = json.loads(mr_path.read_text(encoding="utf-8"))
            assert mr_data["task_id"] == "task-0001"
            assert mr_data["ready"] is False
            assert "Task status is 'created', expected 'verified'" in mr_data["reasons"]
            assert "Verification status is 'not_run', expected 'passed'" in mr_data["reasons"]
            assert "Verification exit code is missing" in mr_data["reasons"]
            assert mr_data["verification_finished_at"] is None
            assert mr_data["generated_at"] is not None

            # Verify CLI show outputs readiness
            show = runner.invoke(app, ["task", "show", "task-0001"])
            assert show.exit_code == 0
            assert "merge_ready: no" in show.output
            assert "readiness_reasons:" in show.output
            assert "  - Task status is 'created', expected 'verified'" in show.output

            # Run task
            run = runner.invoke(app, ["task", "run", "task-0001", "--shell", "echo done"])
            assert run.exit_code == 0

            # 2. Run failed verification (not ready, exit_code recorded)
            verify_fail = runner.invoke(app, ["task", "verify", "task-0001", "--shell", "echo failing; exit 5"])
            assert verify_fail.exit_code == 1

            fail_data = json.loads(mr_path.read_text(encoding="utf-8"))
            assert fail_data["ready"] is False
            assert "Task status is 'verification_failed', expected 'verified'" in fail_data["reasons"]
            assert "Verification exit code is 5, expected 0" in fail_data["reasons"]
            assert fail_data["verification_exit_code"] == 5
            assert fail_data["verification_finished_at"] is not None
            assert fail_data["verification_log_path"] == ".devflow/tasks/task-0001/logs/verify.log"

            # 3. Run passed verification (ready!)
            verify_pass = runner.invoke(app, ["task", "verify", "task-0001", "--shell", "echo passing; exit 0"])
            assert verify_pass.exit_code == 0

            pass_data = json.loads(mr_path.read_text(encoding="utf-8"))
            assert pass_data["ready"] is True
            assert "Verification passed successfully" in pass_data["reasons"]
            assert pass_data["verification_exit_code"] == 0
            assert pass_data["verification_log_path"] == ".devflow/tasks/task-0001/logs/verify.log"
            # Verify POSIX relative log path
            assert "/" in pass_data["verification_log_path"]

            # Verify CLI show output for ready task
            show_ready = runner.invoke(app, ["task", "show", "task-0001"])
            assert show_ready.exit_code == 0
            assert "merge_ready: yes" in show_ready.output
            assert "readiness_reasons:" in show_ready.output
            assert "  - Verification passed successfully" in show_ready.output
        finally:
            os.chdir(old_cwd)


def test_task_show_missing_and_malformed_readiness() -> None:
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            created = runner.invoke(app, ["task", "create", "test robustness"])
            assert created.exit_code == 0

            # 1. Test missing merge-readiness.json
            mr_path = Path(".devflow/tasks/task-0001/merge-readiness.json")
            assert mr_path.exists()
            mr_path.unlink()

            show_missing = runner.invoke(app, ["task", "show", "task-0001"])
            assert show_missing.exit_code == 0
            assert "merge_ready" not in show_missing.output

            # 2. Test malformed merge-readiness.json
            mr_path.write_text("invalid json contents", encoding="utf-8")
            show_malformed = runner.invoke(app, ["task", "show", "task-0001"])
            assert show_malformed.exit_code == 0
            assert "merge_ready" not in show_malformed.output
        finally:
            os.chdir(old_cwd)


def test_dirty_workspace_readiness() -> None:
    import subprocess
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            subprocess.run(["git", "init", "-b", "main"], check=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], check=True)
            subprocess.run(["git", "config", "user.name", "Test User"], check=True)

            Path("file.txt").write_text("commit content\n", encoding="utf-8")
            subprocess.run(["git", "add", "file.txt"], check=True)
            subprocess.run(["git", "commit", "-m", "first commit"], check=True)

            Path("file.txt").write_text("dirty content\n", encoding="utf-8")

            created = runner.invoke(app, ["task", "create", "dirty task"])
            assert created.exit_code == 0

            mr_path = Path(".devflow/tasks/task-0001/merge-readiness.json")
            mr_data = json.loads(mr_path.read_text(encoding="utf-8"))
            assert mr_data["workspace_dirty"] is True
            assert "Warning: Workspace was created from a dirty worktree (uncommitted changes)" in mr_data["reasons"]
            assert mr_data["ready"] is False

            run = runner.invoke(app, ["task", "run", "task-0001", "--shell", "echo done"])
            assert run.exit_code == 0

            verify = runner.invoke(app, ["task", "verify", "task-0001", "--shell", "echo passing; exit 0"])
            assert verify.exit_code == 0

            pass_data = json.loads(mr_path.read_text(encoding="utf-8"))
            assert pass_data["workspace_dirty"] is True
            assert pass_data["ready"] is True
            assert "Verification passed successfully" in pass_data["reasons"]
            assert "Warning: Workspace was created from a dirty worktree (uncommitted changes)" in pass_data["reasons"]

            from datetime import datetime
            datetime.fromisoformat(pass_data["generated_at"])
            datetime.fromisoformat(pass_data["verification_finished_at"])

            assert "\\" not in pass_data["verification_log_path"]
        finally:
            os.chdir(old_cwd)


def test_task_summary_file_lifecycle() -> None:
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)

            # 1. Summary exists after task creation
            created = runner.invoke(app, ["task", "create", "summary test task"])
            assert created.exit_code == 0, created.output

            summary_path = Path(".devflow/tasks/task-0001/summary.json")
            assert summary_path.exists()

            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            assert summary["task_id"] == "task-0001"
            assert summary["title"] == "summary test task"
            assert summary["status"] == "created"
            assert summary["workspace_path"] == ".devflow/workspaces/task-0001"
            assert summary["workspace_dirty"] is False
            assert summary["workspace_branch"] is None
            assert summary["workspace_commit"] is None
            assert summary["latest_verification_status"] == "not_run"
            assert summary["latest_verification_exit_code"] is None
            assert summary["latest_verification_log_path"] is None
            assert summary["merge_ready"] is False
            assert len(summary["merge_readiness_reasons"]) > 0
            assert "Task status is 'created', expected 'verified'" in summary["merge_readiness_reasons"]
            assert summary["updated_at"] is not None

            # 2. Summary updates after shell task execution
            run = runner.invoke(
                app,
                [
                    "task",
                    "run",
                    "task-0001",
                    "--shell",
                    "echo 'hello world' > file.txt",
                ],
            )
            assert run.exit_code == 0, run.output

            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            assert summary["status"] == "complete"
            assert summary["latest_verification_status"] == "not_run"
            assert summary["merge_ready"] is False

            # 3. Summary updates after failed verification
            verify_fail = runner.invoke(
                app,
                [
                    "task",
                    "verify",
                    "task-0001",
                    "--shell",
                    "test -f non_existent_file.txt && echo verify_ok",
                ],
            )
            assert verify_fail.exit_code == 1, verify_fail.output

            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            assert summary["status"] == "verification_failed"
            assert summary["latest_verification_status"] == "failed"
            assert summary["latest_verification_exit_code"] is not None
            assert summary["latest_verification_exit_code"] != 0
            assert summary["latest_verification_log_path"] == ".devflow/tasks/task-0001/logs/verify.log"
            assert summary["merge_ready"] is False
            assert any("Verification exit code is" in reason for reason in summary["merge_readiness_reasons"])

            # 4. Summary updates after passed verification
            verify_pass = runner.invoke(
                app,
                [
                    "task",
                    "verify",
                    "task-0001",
                    "--shell",
                    "test -f file.txt && echo verify_ok",
                ],
            )
            assert verify_pass.exit_code == 0, verify_pass.output

            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            assert summary["status"] == "verified"
            assert summary["latest_verification_status"] == "passed"
            assert summary["latest_verification_exit_code"] == 0
            assert summary["latest_verification_log_path"] == ".devflow/tasks/task-0001/logs/verify.log"
            assert summary["merge_ready"] is True
            assert "Verification passed successfully" in summary["merge_readiness_reasons"]

            summary_path.write_text(
                json.dumps(
                    {
                        "task_id": "task-0001",
                        "status": "worker_failed",
                        "latest_verification_status": "failed",
                        "latest_verification_exit_code": 99,
                        "latest_verification_log_path": ".devflow/tasks/task-0001/logs/not-real.log",
                        "merge_ready": False,
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            listing = runner.invoke(app, ["task", "list"])
            assert listing.exit_code == 0, listing.output
            assert "task-0001" in listing.output
            assert "verified" in listing.output
            assert "passed" in listing.output

            show = runner.invoke(app, ["task", "show", "task-0001"])
            assert show.exit_code == 0, show.output
            assert "status: verified" in show.output
            assert "verification_status: passed" in show.output
            assert "verification_log_path: .devflow/tasks/task-0001/logs/verify.log" in show.output

            # 5. Dashboard state exposes canonical fields even if summary.json is stale or tampered.
            dash = runner.invoke(app, ["dashboard"])
            assert dash.exit_code == 0, dash.output
            assert "task-0001" in dash.output
            assert "verified" in dash.output
            assert "passed" in dash.output
            assert "verification_exit_code: 0" in dash.output
            assert "verification_log: .devflow/tasks/task-0001/logs/verify.log" in dash.output
            assert "merge_ready: yes" in dash.output
            assert "worker_failed" not in dash.output
            assert "not-real.log" not in dash.output

            # 6. Handles missing or malformed readiness files gracefully (by still rewriting summary from task.yaml/record)
            mr_path = Path(".devflow/tasks/task-0001/merge-readiness.json")
            mr_path.unlink()

            # Save or view dashboard again to verify robustness
            dash_missing = runner.invoke(app, ["dashboard"])
            assert dash_missing.exit_code == 0, dash_missing.output
            assert "verification_exit_code: 0" in dash_missing.output
        finally:
            os.chdir(old_cwd)


def test_task_summary_hardening_and_fallbacks() -> None:
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)

            created = runner.invoke(app, ["task", "create", "robust task"])
            assert created.exit_code == 0

            # Ensure task creation generates files
            summary_path = Path(".devflow/tasks/task-0001/summary.json")
            mr_path = Path(".devflow/tasks/task-0001/merge-readiness.json")
            v_path = Path(".devflow/tasks/task-0001/verification.json")

            assert summary_path.exists()
            assert mr_path.exists()
            assert v_path.exists()

            # 1. updated_at is a valid parseable ISO-8601 string
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            from datetime import datetime
            dt = datetime.fromisoformat(summary["updated_at"])
            assert dt is not None

            # 2. paths are POSIX-normalized (using forward slashes)
            assert "\\" not in summary["workspace_path"]
            if summary["latest_verification_log_path"]:
                assert "\\" not in summary["latest_verification_log_path"]

            # 3. Dashboard renders properly when summary.json is missing
            summary_path.unlink()
            listing_no_summary = runner.invoke(app, ["task", "list"])
            assert listing_no_summary.exit_code == 0
            assert "task-0001" in listing_no_summary.output

            show_no_summary = runner.invoke(app, ["task", "show", "task-0001"])
            assert show_no_summary.exit_code == 0
            assert "status: created" in show_no_summary.output

            dash_no_summary = runner.invoke(app, ["dashboard"])
            assert dash_no_summary.exit_code == 0
            assert "Task" in dash_no_summary.output
            assert "task-0001" in dash_no_summary.output

            # 4. Dashboard renders properly when summary.json is malformed
            summary_path.write_text("NOT A VALID JSON", encoding="utf-8")
            listing_malformed_summary = runner.invoke(app, ["task", "list"])
            assert listing_malformed_summary.exit_code == 0
            assert "task-0001" in listing_malformed_summary.output

            show_malformed_summary = runner.invoke(app, ["task", "show", "task-0001"])
            assert show_malformed_summary.exit_code == 0
            assert "status: created" in show_malformed_summary.output

            dash_malformed_summary = runner.invoke(app, ["dashboard"])
            assert dash_malformed_summary.exit_code == 0
            assert "task-0001" in dash_malformed_summary.output

            # 5. summary.json falls back/generates cleanly when verification.json is missing or malformed
            v_path.unlink()
            run = runner.invoke(app, ["task", "run", "task-0001", "--shell", "echo ok"])
            assert run.exit_code == 0

            # Recreate malformed verification.json
            v_path.write_text("{invalid json", encoding="utf-8")

            verify_pass = runner.invoke(app, ["task", "verify", "task-0001", "--shell", "echo verify_ok"])
            assert verify_pass.exit_code == 0

            # 6. summary values match verification.json and merge-readiness.json after passed verification
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            mr_data = json.loads(mr_path.read_text(encoding="utf-8"))
            v_data = json.loads(v_path.read_text(encoding="utf-8"))

            assert summary["latest_verification_status"] == v_data["status"]
            assert summary["latest_verification_exit_code"] == v_data["exit_code"]
            assert summary["latest_verification_log_path"] == v_data["log_path"]

            assert summary["merge_ready"] == mr_data["ready"]
            assert summary["merge_readiness_reasons"] == mr_data["reasons"]
            assert summary["workspace_branch"] == mr_data["workspace_branch"]
            assert summary["workspace_commit"] == mr_data["workspace_commit"]
            assert summary["workspace_dirty"] == mr_data["workspace_dirty"]

            # 7. Dashboard renders robustly when merge-readiness.json is malformed
            mr_path.write_text("{bad", encoding="utf-8")
            dash_malformed_mr = runner.invoke(app, ["dashboard"])
            assert dash_malformed_mr.exit_code == 0
            assert "task-0001" in dash_malformed_mr.output
        finally:
            os.chdir(old_cwd)


def test_task_run_writes_packet_json() -> None:
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            Path("project.txt").write_text("hello main\n", encoding="utf-8")

            # Create task with a secret in the title
            task_title = "task with Bearer ghp_supersecretgithubtoken12345"
            created = runner.invoke(app, ["task", "create", task_title])
            assert created.exit_code == 0, created.output

            # Verify that packet.json does not exist yet
            packet_path = Path(".devflow/tasks/task-0001/packet.json")
            assert not packet_path.exists()

            # Run the task
            run = runner.invoke(app, ["task", "run", "task-0001", "--shell", "echo 'done' > output.txt"])
            assert run.exit_code == 0, run.output

            # Proving 1: devflow task run <id> --shell ... writes packet.json
            assert packet_path.exists()

            # Proving 2: packet.json is valid JSON
            content = packet_path.read_text(encoding="utf-8")
            packet_data = json.loads(content)

            # Proving 3: packet.json includes expected TaskPacket fields
            assert packet_data["task_id"] == "task-0001"
            assert "workspace_path" in packet_data
            assert "constraints" in packet_data
            assert "task" in packet_data
            assert "recent_events" in packet_data

            # Proving 4: packet.json uses virtualized paths
            assert packet_data["workspace_path"] == "<workspace>"
            assert packet_data["task"]["workspace"] == "<workspace>"

            # Proving 5: packet.json redacts obvious secrets if fixture data includes them
            # The title of the task should have been redacted in the packet data
            assert "ghp_supersecretgithubtoken12345" not in packet_data["title"]
            assert "[REDACTED]" in packet_data["title"]

            # Proving 6: shell command still runs in the task workspace
            assert Path(".devflow/workspaces/task-0001/output.txt").exists()
            assert not Path("output.txt").exists()

            # Proving 7: canonical state files remain authoritative
            task_yaml_path = Path(".devflow/tasks/task-0001/task.yaml")
            assert task_yaml_path.exists()
            task_yaml_content = task_yaml_path.read_text(encoding="utf-8")
            assert 'status: "complete"' in task_yaml_content
            # packet.json itself is not canonical and does not overwrite or update task.yaml canonical properties
            assert "ghp_supersecretgithubtoken12345" in task_yaml_content  # Canonical file retains original title without redaction
        finally:
            os.chdir(old_cwd)
