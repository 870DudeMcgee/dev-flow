from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from typer.testing import CliRunner

from devflow.cli import app
from devflow.control_room.service import get_task


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
