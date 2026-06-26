from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

from typer.testing import CliRunner

from devflow.cli import app
from devflow.control_room.finalizer import is_ignored_evidence

runner = CliRunner()


def _init_git_repo() -> str:
    subprocess.run(["git", "init", "-b", "main"], check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], check=True)
    Path("base.txt").write_text("base\n", encoding="utf-8")
    Path(".gitignore").write_text(".devflow/\n", encoding="utf-8")
    subprocess.run(["git", "add", "base.txt", ".gitignore"], check=True)
    subprocess.run(["git", "commit", "-m", "init"], check=True)
    return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()


def _git(cwd: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=cwd, text=True).strip()


def test_is_ignored_evidence() -> None:
    assert is_ignored_evidence(".devflow/tasks/task-0001/finalization.json") is True
    assert is_ignored_evidence("src/devflow/cli.py") is False
    assert is_ignored_evidence(".venv/bin/pytest") is True
    assert is_ignored_evidence("logs/app.log") is True
    assert is_ignored_evidence("__pycache__/foo.pyc") is True


def test_finalize_refuses_non_worktree_task() -> None:
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            _init_git_repo()

            # Create a non-worktree task
            res = runner.invoke(app, ["task", "create", "non-worktree task"])
            assert res.exit_code == 0

            # Finalizing should fail with FinalizationError / CLI exit code 1
            res_finalize = runner.invoke(app, ["task", "finalize", "task-0001"])
            assert res_finalize.exit_code == 1
            assert "Finalization is only supported for Git-worktree tasks" in res_finalize.output
            assert "git add <files> && git commit" in res_finalize.output
        finally:
            os.chdir(old_cwd)


def test_finalize_refuses_when_unrelated_dirty_files_exist() -> None:
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            _init_git_repo()

            # Create git worktree task
            res = runner.invoke(app, ["task", "create", "--git-worktree", "worktree task"])
            assert res.exit_code == 0

            # Run task and verify
            res_run = runner.invoke(app, ["task", "run", "task-0001", "--", "/bin/sh", "-c", "echo 'hello' > src_change.txt"])
            assert res_run.exit_code == 0

            res_verify = runner.invoke(app, ["task", "verify", "task-0001", "--", "/bin/sh", "-c", "true"])
            assert res_verify.exit_code == 0

            # Dirty a file in the main checkout (outside .devflow)
            Path("unrelated_dirty.txt").write_text("dirty content", encoding="utf-8")

            # Try finalizing
            res_finalize = runner.invoke(app, ["task", "finalize", "task-0001"])
            assert res_finalize.exit_code == 1
            assert "unrelated dirty changes exist in the main checkout" in res_finalize.output
            assert "unrelated_dirty.txt" in res_finalize.output
        finally:
            os.chdir(old_cwd)


def test_finalize_refuses_missing_or_stale_verification() -> None:
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            _init_git_repo()

            # Create git worktree task
            res = runner.invoke(app, ["task", "create", "--git-worktree", "worktree task"])
            assert res.exit_code == 0

            # Finalize without verification
            res_finalize = runner.invoke(app, ["task", "finalize", "task-0001"])
            assert res_finalize.exit_code == 1
            assert "Verification is missing for task task-0001" in res_finalize.output

            # Now run task and fail verification
            res_run = runner.invoke(app, ["task", "run", "task-0001", "--", "/bin/sh", "-c", "echo 'hello' > src_change.txt"])
            assert res_run.exit_code == 0

            runner.invoke(app, ["task", "verify", "task-0001", "--", "/bin/sh", "-c", "false"])  # Should fail verification

            res_finalize = runner.invoke(app, ["task", "finalize", "task-0001"])
            assert res_finalize.exit_code == 1
            assert "Verification is failed for task task-0001" in res_finalize.output
        finally:
            os.chdir(old_cwd)


def test_finalize_refuses_when_dirty_after_verification() -> None:
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            _init_git_repo()

            # Create git worktree task
            res = runner.invoke(app, ["task", "create", "--git-worktree", "worktree task"])
            assert res.exit_code == 0

            # Run task and verify
            res_run = runner.invoke(app, ["task", "run", "task-0001", "--", "/bin/sh", "-c", "echo 'hello' > src_change.txt"])
            assert res_run.exit_code == 0

            res_verify = runner.invoke(app, ["task", "verify", "task-0001", "--", "/bin/sh", "-c", "true"])
            assert res_verify.exit_code == 0

            # Sleep briefly to ensure filesystem mtime difference is measurable
            time.sleep(1.1)

            # Make a change inside worktree workspace after verification
            worktree_dir = Path(".devflow/worktrees/task-0001/shell")
            (worktree_dir / "after_verification.txt").write_text("another change", encoding="utf-8")

            res_finalize = runner.invoke(app, ["task", "finalize", "task-0001"])
            assert res_finalize.exit_code == 1
            assert "Verification is stale for task task-0001" in res_finalize.output
        finally:
            os.chdir(old_cwd)


def test_finalize_preview_and_commit_behavior() -> None:
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            baseline = _init_git_repo()

            # Create git worktree task
            res = runner.invoke(app, ["task", "create", "--git-worktree", "worktree task"])
            assert res.exit_code == 0

            # Run task to make some changes
            worktree_dir = Path(".devflow/worktrees/task-0001/shell")
            res_run = runner.invoke(
                app,
                [
                    "task",
                    "run",
                    "task-0001",
                    "--",
                    "/bin/sh",
                    "-c",
                    "echo 'task work' > task_file.txt && mkdir -p .venv && echo 'evidence' > .venv/test.txt",
                ],
            )
            assert res_run.exit_code == 0

            res_verify = runner.invoke(app, ["task", "verify", "task-0001", "--", "/bin/sh", "-c", "test -f task_file.txt"])
            assert res_verify.exit_code == 0

            # 1. Finalize preview (dry-run by default)
            res_finalize_dry = runner.invoke(app, ["task", "finalize", "task-0001"])
            assert res_finalize_dry.exit_code == 0
            assert "staged:" in res_finalize_dry.output
            assert "  - task_file.txt" in res_finalize_dry.output
            assert "ignored:" in res_finalize_dry.output
            assert "  - .venv/" in res_finalize_dry.output
            assert "verification_status: passed" in res_finalize_dry.output
            assert "commit_hash: dry-run" in res_finalize_dry.output
            assert "next_action: devflow task finalize task-0001 --commit" in res_finalize_dry.output

            # Check finalization.json is written
            evidence_file = Path(".devflow/tasks/task-0001/finalization.json")
            assert evidence_file.exists()
            ev_data = json.loads(evidence_file.read_text(encoding="utf-8"))
            assert ev_data["task_id"] == "task-0001"
            assert "task_file.txt" in ev_data["staged_files"]
            assert ".venv/" in ev_data["ignored_evidence_files"]
            assert ev_data["verification_status"] == "passed"
            assert ev_data["commit_hash"] is None
            assert "finalize task-0001 --commit" in ev_data["next_suggested_action"]

            # Confirm no commit was actually created in worktree git history
            assert _git(worktree_dir, "rev-parse", "HEAD") == baseline

            # 2. Finalize with --commit
            res_finalize_commit = runner.invoke(app, ["task", "finalize", "task-0001", "--commit"])
            assert res_finalize_commit.exit_code == 0
            assert "staged:" in res_finalize_commit.output
            assert "  - task_file.txt" in res_finalize_commit.output
            assert "verification_status: passed" in res_finalize_commit.output
            assert "commit_hash:" in res_finalize_commit.output
            assert "next_action: devflow task promote-preview task-0001" in res_finalize_commit.output

            # Confirm a commit WAS created in the worktree git history
            new_head = _git(worktree_dir, "rev-parse", "HEAD")
            assert new_head != baseline

            # Verify deterministic commit message
            commit_msg = _git(worktree_dir, "log", "-1", "--pretty=%B")
            assert commit_msg.strip() == "chore(devflow): worktree task\n\nDev-Flow-Task: task-0001"

            # Check finalization.json has commit_hash recorded
            ev_data_commit = json.loads(evidence_file.read_text(encoding="utf-8"))
            assert ev_data_commit["commit_hash"] == new_head
            assert ev_data_commit["next_suggested_action"] == "devflow task promote-preview task-0001"

            # Clean untracked .venv evidence folder so git worktree status is fully clean
            for root, dirs, files in os.walk(str(worktree_dir / ".venv"), topdown=False):
                for name in files:
                    os.remove(os.path.join(root, name))
                for name in dirs:
                    os.rmdir(os.path.join(root, name))
            os.rmdir(str(worktree_dir / ".venv"))

            # Confirm we can run promote-preview after finalize commit
            res_preview = runner.invoke(app, ["task", "promote-preview", "task-0001"])
            assert res_preview.exit_code == 0, res_preview.output
            assert "promotion_readiness: ready" in res_preview.output

            # Confirm we can promote
            res_promote = runner.invoke(app, ["task", "promote", "task-0001"], input="y\n")
            assert res_promote.exit_code == 0, res_promote.output
            assert "Promotion complete." in res_promote.output
            assert Path("task_file.txt").exists()
        finally:
            os.chdir(old_cwd)


def test_finalize_commit_stages_tracked_worktree_modifications() -> None:
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            baseline = _init_git_repo()

            created = runner.invoke(app, ["task", "create", "--git-worktree", "tracked file task"])
            assert created.exit_code == 0, created.output

            worktree_dir = Path(".devflow/worktrees/task-0001/shell")
            run = runner.invoke(
                app,
                ["task", "run", "task-0001", "--", "/bin/sh", "-c", "printf 'updated\\n' > base.txt"],
            )
            assert run.exit_code == 0, run.output

            verify = runner.invoke(app, ["task", "verify", "task-0001", "--", "/bin/sh", "-c", "grep -q updated base.txt"])
            assert verify.exit_code == 0, verify.output

            finalize_preview = runner.invoke(app, ["task", "finalize", "task-0001"])
            assert finalize_preview.exit_code == 0, finalize_preview.output
            assert "  - base.txt" in finalize_preview.output

            finalize_commit = runner.invoke(app, ["task", "finalize", "task-0001", "--commit"])
            assert finalize_commit.exit_code == 0, finalize_commit.output
            new_head = _git(worktree_dir, "rev-parse", "HEAD")
            assert new_head != baseline
            assert _git(worktree_dir, "status", "--porcelain") == ""
            assert _git(worktree_dir, "show", "--pretty=", "--name-only", "HEAD").splitlines() == ["base.txt"]

            merge_readiness = json.loads(Path(".devflow/tasks/task-0001/merge-readiness.json").read_text(encoding="utf-8"))
            assert merge_readiness["ready"] is True
            assert merge_readiness["workspace_dirty"] is False
            assert "worker worktree is dirty after verification" not in merge_readiness["reasons"]
        finally:
            os.chdir(old_cwd)


def test_git_worktree_finalize_to_promote_workflow_is_explicit_and_clean() -> None:
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            baseline = _init_git_repo()

            created = runner.invoke(app, ["task", "create", "--git-worktree", "task-0019 dogfood"])
            assert created.exit_code == 0

            run = runner.invoke(
                app,
                [
                    "task",
                    "run",
                    "task-0001",
                    "--",
                    "/bin/sh",
                    "-c",
                    "echo 'task-0019 result' > task_0019_result.txt && mkdir -p .devflow/dogfood && echo artifact > .devflow/dogfood/artifact.txt",
                ],
            )
            assert run.exit_code == 0, run.output

            verify = runner.invoke(app, ["task", "verify", "task-0001", "--", "/bin/sh", "-c", "test -f task_0019_result.txt"])
            assert verify.exit_code == 0, verify.output

            finalize_preview = runner.invoke(app, ["task", "finalize", "task-0001"])
            assert finalize_preview.exit_code == 0, finalize_preview.output
            assert "next_action: devflow task finalize task-0001 --commit" in finalize_preview.output
            assert _git(Path.cwd(), "rev-parse", "HEAD") == baseline

            finalize_commit = runner.invoke(app, ["task", "finalize", "task-0001", "--commit"])
            assert finalize_commit.exit_code == 0, finalize_commit.output
            assert "commit_location: task worker branch" in finalize_commit.output
            assert "worker_branch: devflow/task-0001/shell" in finalize_commit.output
            assert "main_changed: no" in finalize_commit.output
            assert "next_action: devflow task promote-preview task-0001" in finalize_commit.output
            assert _git(Path.cwd(), "rev-parse", "HEAD") == baseline

            worktree_dir = Path(".devflow/worktrees/task-0001/shell")
            finalized_commit = _git(worktree_dir, "rev-parse", "HEAD")
            assert finalized_commit != baseline

            show = runner.invoke(app, ["task", "show", "task-0001"])
            assert show.exit_code == 0, show.output
            assert f"finalized_commit: {finalized_commit}" in show.output
            assert f"worker_branch_commit: {finalized_commit}" in show.output
            assert "promotion_status: main not promoted yet" in show.output
            assert "suggested_next_action: devflow task promote-preview task-0001" in show.output

            promote_preview = runner.invoke(app, ["task", "promote-preview", "task-0001"])
            assert promote_preview.exit_code == 0, promote_preview.output
            assert "preview_only: yes" in promote_preview.output
            assert "main_changed: no" in promote_preview.output
            assert "next_action: devflow task promote task-0001" in promote_preview.output
            assert "promotion_readiness: ready" in promote_preview.output
            assert _git(Path.cwd(), "rev-parse", "HEAD") == baseline
            assert _git(Path.cwd(), "status", "--porcelain") == ""

            promote = runner.invoke(app, ["task", "promote", "task-0001"], input="y\n")
            assert promote.exit_code == 0, promote.output
            assert "Promotion complete." in promote.output
            assert "main_changed: yes" in promote.output
            assert "staged_changes_left: no" in promote.output
            assert Path("task_0019_result.txt").read_text(encoding="utf-8") == "task-0019 result\n"
            assert _git(Path.cwd(), "rev-parse", "HEAD") != baseline
            assert _git(Path.cwd(), "status", "--porcelain") == ""
        finally:
            os.chdir(old_cwd)
