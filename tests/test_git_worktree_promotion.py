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


def _write_hitl_goal_link(task_id: str = "task-0001") -> None:
    (Path(".devflow/tasks") / task_id / "goal-link.yaml").write_text(
        "\n".join(
            [
                "schema_version: 1",
                "goal_id: G-0001",
                "goal_path: .devflow/goals/G-0001",
                "slice_id: TS-0005",
                "execution_mode: HITL",
                "human_checkpoint_required: true",
                "checkpoint_reason: Integration combines parallel agent outputs.",
                "promotion_allowed: false",
                "risk: high",
                "created_from_goal_slice: true",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _create_orphan_worktree(branch: str = "devflow/task-9999/shell") -> Path:
    worktree = Path(".devflow/worktrees/task-9999/shell")
    worktree.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "worktree", "add", "-b", branch, str(worktree), "main"], check=True)
    return worktree


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


def test_git_worktree_promote_preview_prompts_for_hitl_goal_approval() -> None:
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            _init_git_repo()

            created = runner.invoke(app, ["task", "create", "--git-worktree", "hitl gate task"])
            assert created.exit_code == 0, created.output
            _write_hitl_goal_link()

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

            verify = runner.invoke(app, ["task", "verify", "task-0001", "--", "/bin/sh", "-c", "test -f worker.txt"])
            assert verify.exit_code == 0, verify.output

            preview = runner.invoke(app, ["task", "promote-preview", "task-0001"])
            assert preview.exit_code == 0, preview.output
            assert "promotion_readiness: ready" in preview.output
            assert "human_approval_required: yes" in preview.output
            assert "human_approval_reason: Integration combines parallel agent outputs." in preview.output
            assert "human_approval_prompt: Review HITL goal G-0001 / TS-0005 before promotion." in preview.output
            assert (
                "next_action: Human approval required; review this preview, then run "
                "'devflow task promote task-0001' and confirm the prompt."
            ) in preview.output
            assert "Decision needed:\nHuman approval required before promotion." in preview.output

            preview_evidence = json.loads(
                Path(".devflow/tasks/task-0001/workers/shell/promotion-preview.json").read_text(encoding="utf-8")
            )
            assert preview_evidence["human_approval_required"] is True
            assert preview_evidence["human_approval_reason"] == "Integration combines parallel agent outputs."
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


def test_doctor_strict_reports_shared_git_worker_branch_across_tasks() -> None:
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            _init_git_repo()
            assert runner.invoke(app, ["task", "create", "--git-worktree", "first git task"]).exit_code == 0
            assert runner.invoke(app, ["task", "create", "--git-worktree", "second git task"]).exit_code == 0

            task_yaml = Path(".devflow/tasks/task-0002/task.yaml")
            task_yaml.write_text(
                task_yaml.read_text(encoding="utf-8").replace(
                    'branch_name: "devflow/task-0002/shell"',
                    'branch_name: "devflow/task-0001/shell"',
                ),
                encoding="utf-8",
            )

            strict = runner.invoke(app, ["doctor", "--strict"])
            assert strict.exit_code == 1, strict.output
            assert "strict: unique Git worker branches" in strict.output
            assert "devflow/task-0001/shell shared by task-0001, task-0002" in strict.output
        finally:
            os.chdir(old_cwd)


def test_worktree_and_branch_inventory_show_owned_and_orphaned_resources() -> None:
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            _init_git_repo()
            assert runner.invoke(app, ["task", "create", "--git-worktree", "owned worktree"]).exit_code == 0
            _create_orphan_worktree()

            worktrees = runner.invoke(app, ["worktree", "list"])
            assert worktrees.exit_code == 0, worktrees.output
            assert ".devflow/worktrees/task-0001/shell" in worktrees.output
            assert "devflow/task-0001/shell" in worktrees.output
            assert "owned" in worktrees.output
            assert ".devflow/worktrees/task-9999/shell" in worktrees.output
            assert "devflow/task-9999/shell" in worktrees.output
            assert "orphan" in worktrees.output

            branches = runner.invoke(app, ["branch", "list"])
            assert branches.exit_code == 0, branches.output
            assert "devflow/task-0001/shell" in branches.output
            assert "owned" in branches.output
            assert "devflow/task-9999/shell" in branches.output
            assert "orphan" in branches.output
        finally:
            os.chdir(old_cwd)


def test_worktree_prune_is_dry_run_first_and_apply_removes_orphan_worktree() -> None:
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            _init_git_repo()
            worktree = _create_orphan_worktree()

            dry_run = runner.invoke(app, ["worktree", "prune", "--dry-run"])
            assert dry_run.exit_code == 0, dry_run.output
            assert "mode: dry-run" in dry_run.output
            assert "would_remove_worktree: .devflow/worktrees/task-9999/shell" in dry_run.output
            assert worktree.exists()
            assert _git(Path.cwd(), "rev-parse", "--verify", "devflow/task-9999/shell")

            applied = runner.invoke(app, ["worktree", "prune", "--apply"])
            assert applied.exit_code == 0, applied.output
            assert "removed_worktree: .devflow/worktrees/task-9999/shell" in applied.output
            assert not worktree.exists()
            assert _git(Path.cwd(), "rev-parse", "--verify", "devflow/task-9999/shell")
        finally:
            os.chdir(old_cwd)


def test_branch_archive_is_dry_run_first_and_apply_renames_orphan_branch() -> None:
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            _init_git_repo()
            subprocess.run(["git", "branch", "devflow/task-9999/shell"], check=True)

            dry_run = runner.invoke(app, ["branch", "archive", "devflow/task-9999/shell", "--dry-run"])
            assert dry_run.exit_code == 0, dry_run.output
            assert "mode: dry-run" in dry_run.output
            assert "would_archive_branch: devflow/task-9999/shell -> devflow/archive/task-9999/shell" in dry_run.output
            assert _git(Path.cwd(), "rev-parse", "--verify", "devflow/task-9999/shell")

            applied = runner.invoke(app, ["branch", "archive", "devflow/task-9999/shell", "--apply"])
            assert applied.exit_code == 0, applied.output
            assert "archived_branch: devflow/task-9999/shell -> devflow/archive/task-9999/shell" in applied.output
            assert _git(Path.cwd(), "rev-parse", "--verify", "devflow/archive/task-9999/shell")
            missing = subprocess.run(
                ["git", "rev-parse", "--verify", "devflow/task-9999/shell"],
                capture_output=True,
                text=True,
            )
            assert missing.returncode != 0
        finally:
            os.chdir(old_cwd)


def test_task_cleanup_dry_run_reports_git_worktree_resources() -> None:
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            _init_git_repo()
            assert runner.invoke(app, ["task", "create", "--git-worktree", "cleanup task"]).exit_code == 0

            dry_run = runner.invoke(app, ["task", "cleanup", "task-0001", "--dry-run"])
            assert dry_run.exit_code == 0, dry_run.output
            assert "mode: dry-run" in dry_run.output
            assert "task: task-0001" in dry_run.output
            assert "would_remove_worktree: .devflow/worktrees/task-0001/shell" in dry_run.output
            assert "would_archive_branch: devflow/task-0001/shell -> devflow/archive/task-0001/shell" in dry_run.output
            assert Path(".devflow/worktrees/task-0001/shell").exists()
            assert _git(Path.cwd(), "rev-parse", "--verify", "devflow/task-0001/shell")
        finally:
            os.chdir(old_cwd)


def test_task_cleanup_apply_after_promotion_removes_worktree_and_archives_branch() -> None:
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            _init_git_repo()
            assert runner.invoke(app, ["task", "create", "--git-worktree", "cleanup after promotion"]).exit_code == 0
            run = runner.invoke(
                app,
                [
                    "task",
                    "run",
                    "task-0001",
                    "--",
                    "/bin/sh",
                    "-c",
                    "printf 'done\n' > done.txt && git add done.txt && git commit -m done",
                ],
            )
            assert run.exit_code == 0, run.output
            verify = runner.invoke(app, ["task", "verify", "task-0001", "--", "/bin/sh", "-c", "test -f done.txt"])
            assert verify.exit_code == 0, verify.output
            promoted = runner.invoke(app, ["task", "promote", "task-0001"], input="y\n")
            assert promoted.exit_code == 0, promoted.output

            cleanup = runner.invoke(app, ["task", "cleanup", "task-0001", "--apply"])
            assert cleanup.exit_code == 0, cleanup.output
            assert "mode: apply" in cleanup.output
            assert "removed_worktree: .devflow/worktrees/task-0001/shell" in cleanup.output
            assert "archived_branch: devflow/task-0001/shell -> devflow/archive/task-0001/shell" in cleanup.output
            assert not Path(".devflow/worktrees/task-0001/shell").exists()
            assert _git(Path.cwd(), "rev-parse", "--verify", "devflow/archive/task-0001/shell")
            missing = subprocess.run(
                ["git", "rev-parse", "--verify", "devflow/task-0001/shell"],
                capture_output=True,
                text=True,
            )
            assert missing.returncode != 0
        finally:
            os.chdir(old_cwd)
