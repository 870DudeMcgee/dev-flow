from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

from typer.testing import CliRunner

from devflow.cli import app
from devflow.control_room.status_projection import ReviewCapsuleProjection


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


def test_git_native_capsule_renders_small_added_file_inline_and_ready_state() -> None:
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            _init_git_repo()

            created = runner.invoke(app, ["task", "create", "--git-worktree", "capsule dogfood"])
            assert created.exit_code == 0, created.output

            worktree = Path(".devflow/worktrees/task-0001/shell")
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
                    "printf 'hello from git-native qwopus dogfood\\n' > dogfood-qwopus.txt && "
                    "git add dogfood-qwopus.txt && git commit -m dogfood",
                ],
            )
            assert run.exit_code == 0, run.output
            assert "REVIEW CAPSULE - task-0001" in run.output

            verify = runner.invoke(app, ["task", "verify", "task-0001", "--", "/bin/sh", "-c", "test -f dogfood-qwopus.txt"])
            assert verify.exit_code == 0, verify.output
            assert "REVIEW CAPSULE - task-0001" in verify.output

            preview = runner.invoke(app, ["task", "promote-preview", "task-0001"])
            assert preview.exit_code == 0, preview.output
            assert "promotion_readiness: ready" in preview.output
            assert "REVIEW CAPSULE - task-0001" in preview.output
            assert "Promotion readiness:\nready" in preview.output

            head = _git(worktree, "rev-parse", "HEAD")
            capsule = runner.invoke(app, ["task", "capsule", "task-0001"])
            assert capsule.exit_code == 0, capsule.output
            assert "REVIEW CAPSULE - task-0001" in capsule.output
            assert "Task title:\ncapsule dogfood" in capsule.output
            assert "Status:\nverified" in capsule.output
            assert "Worker:\nshell" in capsule.output
            assert "Workspace:\n.devflow/worktrees/task-0001/shell" in capsule.output
            assert "Branch:\ndevflow/task-0001/shell" in capsule.output
            assert f"Latest commit:\n{head}" in capsule.output
            assert "Promotion readiness:\nready" in capsule.output
            assert "Verification:\nPASS" in capsule.output
            assert "Promotion preview:\nPASS" in capsule.output
            assert "1. dogfood-qwopus.txt" in capsule.output
            assert "   status: added" in capsule.output
            assert "   contents:\n   hello from git-native qwopus dogfood" in capsule.output
            assert "Safe next actions:\n- promote task-0001\n- reject/close task-0001" in capsule.output
        finally:
            os.chdir(old_cwd)


def test_capsule_truncates_large_text_and_skips_binary_files() -> None:
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            assert runner.invoke(app, ["task", "create", "large and binary"]).exit_code == 0
            workspace = Path(".devflow/workspaces/task-0001")
            (workspace / "large.txt").write_text("a" * 5000, encoding="utf-8")
            (workspace / "asset.bin").write_bytes(b"\x00PNG-ish binary payload")

            capsule = runner.invoke(app, ["task", "capsule", "task-0001"])
            assert capsule.exit_code == 0, capsule.output
            assert "1. asset.bin" in capsule.output
            assert "   contents: [binary file not shown]" in capsule.output
            assert "2. large.txt" in capsule.output
            assert "... truncated after" in capsule.output
        finally:
            os.chdir(old_cwd)


def test_capsule_labels_missing_verification_and_promotion_preview() -> None:
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            _init_git_repo()
            assert runner.invoke(app, ["task", "create", "--git-worktree", "missing evidence"]).exit_code == 0
            Path(".devflow/tasks/task-0001/verification.json").unlink()

            capsule = runner.invoke(app, ["task", "capsule", "task-0001"])
            assert capsule.exit_code == 0, capsule.output
            assert "Verification:\nmissing (no verification.json)" in capsule.output
            assert "Promotion preview:\nmissing (run devflow task promote-preview task-0001)" in capsule.output
            assert "Decision needed:\nRun verification for this task." in capsule.output
        finally:
            os.chdir(old_cwd)


def test_capsule_renders_status_projection_decision_model(monkeypatch) -> None:
    def fake_projection(task, verification, verification_note, preview, preview_note):
        return ReviewCapsuleProjection(
            verification_text="PROJECTED VERIFY",
            promotion_readiness_text="PROJECTED READINESS",
            promotion_preview_text="PROJECTED PREVIEW",
            decision="Projected decision.",
            safe_next_actions=["projected action"],
        )

    monkeypatch.setattr("devflow.control_room.review_capsule.build_review_capsule_projection", fake_projection)

    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            assert runner.invoke(app, ["task", "create", "projected capsule"]).exit_code == 0

            capsule = runner.invoke(app, ["task", "capsule", "task-0001"])
            assert capsule.exit_code == 0, capsule.output
            assert "Decision needed:\nProjected decision." in capsule.output
            assert "Verification:\nPROJECTED VERIFY" in capsule.output
            assert "Promotion readiness:\nPROJECTED READINESS" in capsule.output
            assert "Promotion preview:\nPROJECTED PREVIEW" in capsule.output
            assert "Safe next actions:\n- projected action" in capsule.output
        finally:
            os.chdir(old_cwd)


def test_capsule_rejects_traversal_and_absolute_changed_paths() -> None:
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            assert runner.invoke(app, ["task", "create", "unsafe paths"]).exit_code == 0
            Path("secret.txt").write_text("do not read\n", encoding="utf-8")
            task_dir = Path(".devflow/tasks/task-0001")
            (task_dir / "promotion-preview.json").write_text(
                json.dumps(
                    {
                        "task_id": "task-0001",
                        "promotion_readiness": "not_ready",
                        "added": ["../secret.txt", "/tmp/absolute.txt"],
                        "modified": [],
                        "deleted": [],
                        "renamed": [],
                        "untracked": [],
                        "binary": [],
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            capsule = runner.invoke(app, ["task", "capsule", "task-0001"])
            assert capsule.exit_code == 0, capsule.output
            assert "1. ../secret.txt" in capsule.output
            assert "contents: [rejected unsafe path: path traversal is not allowed]" in capsule.output
            assert "2. /tmp/absolute.txt" in capsule.output
            assert "contents: [rejected unsafe path: absolute paths are not allowed]" in capsule.output
            assert "do not read" not in capsule.output
        finally:
            os.chdir(old_cwd)


def test_capsule_rendering_is_read_only_and_creates_no_review_markdown_by_default() -> None:
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            assert runner.invoke(app, ["task", "create", "read only"]).exit_code == 0
            Path(".devflow/workspaces/task-0001/result.txt").write_text("review me\n", encoding="utf-8")
            task_yaml = Path(".devflow/tasks/task-0001/task.yaml")
            events = Path(".devflow/tasks/task-0001/events.jsonl")
            verification = Path(".devflow/tasks/task-0001/verification.json")
            before = {
                "task": task_yaml.read_text(encoding="utf-8"),
                "events": events.read_text(encoding="utf-8"),
                "verification": verification.read_text(encoding="utf-8"),
            }

            capsule = runner.invoke(app, ["task", "capsule", "task-0001"])
            assert capsule.exit_code == 0, capsule.output

            after = {
                "task": task_yaml.read_text(encoding="utf-8"),
                "events": events.read_text(encoding="utf-8"),
                "verification": verification.read_text(encoding="utf-8"),
            }
            assert after == before
            assert not Path(".devflow/reviews").exists()
            assert not Path(".devflow/tasks/task-0001/review-capsule.md").exists()
        finally:
            os.chdir(old_cwd)
