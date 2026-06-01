from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

from typer.testing import CliRunner

from devflow.cli import app


runner = CliRunner()


def _init_git_repo() -> str:
    subprocess.run(["git", "init", "-b", "main"], check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], check=True)
    Path("base.txt").write_text("base\n", encoding="utf-8")
    subprocess.run(["git", "add", "base.txt"], check=True)
    subprocess.run(["git", "commit", "-m", "init"], check=True)
    return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()


def _git(cwd: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=cwd, text=True).strip()


def test_git_worktree_task_runs_verifies_previews_and_promotes() -> None:
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            baseline = _init_git_repo()

            created = runner.invoke(app, ["task", "create", "--git-worktree", "git-native task"])
            assert created.exit_code == 0, created.output
            assert "workspace: .devflow/worktrees/task-0001/shell" in created.output

            worktree = Path(".devflow/worktrees/task-0001/shell")
            assert worktree.is_dir()
            assert _git(worktree, "branch", "--show-current") == "devflow/task-0001/shell"

            git_evidence_path = Path(".devflow/tasks/task-0001/workers/shell/git.json")
            git_evidence = json.loads(git_evidence_path.read_text(encoding="utf-8"))
            assert git_evidence["task_id"] == "task-0001"
            assert git_evidence["worker_id"] == "shell"
            assert git_evidence["base_branch"] == "main"
            assert git_evidence["base_commit"] == baseline
            assert git_evidence["worker_branch"] == "devflow/task-0001/shell"
            assert git_evidence["worktree_path"] == ".devflow/worktrees/task-0001/shell"
            assert git_evidence["head_commit"] == baseline
            assert git_evidence["dirty"] is False

            run = runner.invoke(
                app,
                [
                    "task",
                    "run",
                    "task-0001",
                    "--worker",
                    "shell",
                    "--",
                    "/bin/sh",
                    "-c",
                    "printf 'worker result\\n' > worker.txt && git add worker.txt && git commit -m worker-result",
                ],
            )
            assert run.exit_code == 0, run.output

            worker_head = _git(worktree, "rev-parse", "HEAD")
            assert worker_head != baseline

            verify = runner.invoke(app, ["task", "verify", "task-0001", "--", "/bin/sh", "-c", "test -f worker.txt"])
            assert verify.exit_code == 0, verify.output

            verification = json.loads(Path(".devflow/tasks/task-0001/verification.json").read_text(encoding="utf-8"))
            assert verification["worker_id"] == "shell"
            assert verification["branch"] == "devflow/task-0001/shell"
            assert verification["base_commit"] == baseline
            assert verification["verified_commit"] == worker_head
            assert verification["dirty_at_verification"] is False
            assert verification["status"] == "passed"

            preview = runner.invoke(app, ["task", "promote-preview", "task-0001"])
            assert preview.exit_code == 0, preview.output
            assert f"base_commit: {baseline}" in preview.output
            assert f"worker_branch_head: {worker_head}" in preview.output
            assert "worker_id: shell" in preview.output
            assert "baseline_stale: no" in preview.output
            assert "conflict_prediction: clean" in preview.output
            assert "promotion_readiness: ready" in preview.output
            assert "Added files:" in preview.output
            assert "  - worker.txt" in preview.output

            preview_evidence = json.loads(
                Path(".devflow/tasks/task-0001/workers/shell/promotion-preview.json").read_text(encoding="utf-8")
            )
            assert preview_evidence["worker_branch_head"] == worker_head
            assert preview_evidence["conflict_prediction"] == "clean"

            promoted = runner.invoke(app, ["task", "promote", "task-0001"], input="y\n")
            assert promoted.exit_code == 0, promoted.output
            assert "Promotion complete." in promoted.output
            assert Path("worker.txt").read_text(encoding="utf-8") == "worker result\n"
        finally:
            os.chdir(old_cwd)


def test_git_worktree_promotion_refuses_when_head_changed_after_verification() -> None:
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            _init_git_repo()
            assert runner.invoke(app, ["task", "create", "--git-worktree", "stale verified commit"]).exit_code == 0
            run = runner.invoke(
                app,
                [
                    "task",
                    "run",
                    "task-0001",
                    "--",
                    "/bin/sh",
                    "-c",
                    "printf 'one\\n' > file.txt && git add file.txt && git commit -m one",
                ],
            )
            assert run.exit_code == 0, run.output
            verify = runner.invoke(app, ["task", "verify", "task-0001", "--", "/bin/sh", "-c", "test -f file.txt"])
            assert verify.exit_code == 0, verify.output

            worktree = Path(".devflow/worktrees/task-0001/shell")
            subprocess.run(
                ["/bin/sh", "-c", "printf 'two\\n' > second.txt && git add second.txt && git commit -m two"],
                cwd=worktree,
                check=True,
            )

            promoted = runner.invoke(app, ["task", "promote", "task-0001"], input="y\n")
            assert promoted.exit_code == 1, promoted.output
            assert "worker HEAD differs from verified commit" in promoted.output
            assert not Path("file.txt").exists()
            assert not Path("second.txt").exists()
        finally:
            os.chdir(old_cwd)


def test_doctor_strict_reports_git_worktree_integrity_gaps() -> None:
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            _init_git_repo()
            assert runner.invoke(app, ["task", "create", "--git-worktree", "doctor git"] ).exit_code == 0

            task_yaml = Path(".devflow/tasks/task-0001/task.yaml")
            task_yaml.write_text(
                task_yaml.read_text(encoding="utf-8").replace(
                    'branch_name: "devflow/task-0001/shell"',
                    'branch_name: "devflow/task-0001/missing-worker"',
                ),
                encoding="utf-8",
            )

            strict = runner.invoke(app, ["doctor", "--strict"])
            assert strict.exit_code == 1, strict.output
            assert "strict: task-0001 worker branch" in strict.output
            assert "missing branch devflow/task-0001/missing-worker" in strict.output
        finally:
            os.chdir(old_cwd)