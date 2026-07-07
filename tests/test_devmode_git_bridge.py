from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

from typer.testing import CliRunner

from devflow.cli import app
from devflow.control_room.devmode_bridge import detect_devmode
from devflow.control_room.service import create_task
from devflow.control_room.task_packet import build_task_packet, render_task_packet_text


runner = CliRunner()


def _git(cwd: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=cwd, text=True).strip()


def _run_git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True)


def _init_repo(path: Path) -> str:
    _run_git(path, "init", "-b", "main")
    _run_git(path, "config", "user.email", "test@example.com")
    _run_git(path, "config", "user.name", "Test User")
    (path / "base.txt").write_text("base\n", encoding="utf-8")
    _run_git(path, "add", "base.txt")
    _run_git(path, "commit", "-m", "init")
    return _git(path, "rev-parse", "HEAD")


def _init_repo_with_origin(tmp: Path) -> tuple[Path, Path]:
    origin = tmp / "origin.git"
    work = tmp / "work"
    _run_git(tmp, "init", "--bare", str(origin))
    work.mkdir()
    _init_repo(work)
    _run_git(work, "remote", "add", "origin", str(origin))
    _run_git(work, "push", "-u", "origin", "main")
    return work, origin


def _advance_origin(tmp: Path, origin: Path, filename: str = "remote.txt") -> str:
    clone = tmp / f"remote-{filename}"
    _run_git(tmp, "clone", str(origin), str(clone))
    _run_git(clone, "switch", "main")
    _run_git(clone, "config", "user.email", "test@example.com")
    _run_git(clone, "config", "user.name", "Test User")
    (clone / filename).write_text("remote\n", encoding="utf-8")
    _run_git(clone, "add", filename)
    _run_git(clone, "commit", "-m", f"remote {filename}")
    _run_git(clone, "push", "origin", "main")
    return _git(clone, "rev-parse", "HEAD")


def test_devmode_detection_reports_missing_and_present_skill_files() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        missing = detect_devmode(root)
        assert missing.detected is False
        assert all(not skill.present for skill in missing.skills)

        skill = root / "skills" / "using-devmode" / "SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text("name: using-devmode\n", encoding="utf-8")

        present = detect_devmode(root)
        assert present.detected is True
        assert present.skills[0].name == "using-devmode"
        assert present.skills[0].present is True
        assert present.task_packets_reference_devmode is True


def test_devmode_detection_ignores_agent_skill_duplicate() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        skill = root / ".agent" / "skills" / "using-devmode" / "SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text("name: using-devmode\n", encoding="utf-8")

        status = detect_devmode(root)

        assert status.detected is False
        assert all(not skill.present for skill in status.skills)


def test_generated_task_packet_includes_devmode_bridge_instructions() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        create_task(root, "packet devmode bridge")

        packet = build_task_packet("task-0001", root=root)
        rendered = render_task_packet_text(packet)

        assert "Before modifying files, follow `AGENTS.md` and the DevFlow workflow adapter." in packet.devmode_discipline
        assert "## DevMode Discipline" in rendered
        assert "Do not merge, promote, push, rebase, or resolve conflicts" in rendered


def test_git_status_detects_dirty_tree_and_operation_in_progress() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _init_repo(root)
        (root / "dirty.txt").write_text("dirty\n", encoding="utf-8")

        old_cwd = Path.cwd()
        try:
            os.chdir(root)
            dirty = runner.invoke(app, ["git", "status"], catch_exceptions=False)
            assert dirty.exit_code == 0, dirty.output
            assert "dirty_state: dirty" in dirty.output
            assert "untracked_count: 1" in dirty.output

            merge_head = Path(_git(root, "rev-parse", "--git-path", "MERGE_HEAD"))
            if not merge_head.is_absolute():
                merge_head = root / merge_head
            merge_head.write_text(_git(root, "rev-parse", "HEAD") + "\n", encoding="utf-8")

            operation = runner.invoke(app, ["git", "status"], catch_exceptions=False)
            assert operation.exit_code == 0, operation.output
            assert "operation_in_progress: merge" in operation.output
        finally:
            os.chdir(old_cwd)


def test_sync_main_refuses_dirty_tree_and_diverged_main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        work, origin = _init_repo_with_origin(base)
        (work / "dirty.txt").write_text("dirty\n", encoding="utf-8")

        old_cwd = Path.cwd()
        try:
            os.chdir(work)
            dirty = runner.invoke(app, ["sync-main"])
            assert dirty.exit_code == 1, dirty.output
            assert "Refusing sync-main: working tree is dirty" in dirty.output

            (work / "dirty.txt").unlink()
            (work / "local.txt").write_text("local\n", encoding="utf-8")
            _run_git(work, "add", "local.txt")
            _run_git(work, "commit", "-m", "local")
            _advance_origin(base, origin)

            diverged = runner.invoke(app, ["sync-main"])
            assert diverged.exit_code == 1, diverged.output
            assert "local main and origin/main have diverged" in diverged.output
        finally:
            os.chdir(old_cwd)


def test_push_main_refuses_non_main_and_origin_ahead() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        work, origin = _init_repo_with_origin(base)
        _run_git(work, "switch", "-c", "feature")

        old_cwd = Path.cwd()
        try:
            os.chdir(work)
            non_main = runner.invoke(app, ["push-main"])
            assert non_main.exit_code == 1, non_main.output
            assert "current branch is feature, expected main" in non_main.output

            _run_git(work, "switch", "main")
            _advance_origin(base, origin)

            ahead = runner.invoke(app, ["push-main"])
            assert ahead.exit_code == 1, ahead.output
            assert "origin/main is ahead of local main" in ahead.output
        finally:
            os.chdir(old_cwd)


def test_git_checkpoint_previews_then_commits_dirty_tree() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _init_repo(root)
        base_head = _git(root, "rev-parse", "HEAD")
        (root / "checkpoint.txt").write_text("checkpoint\n", encoding="utf-8")

        old_cwd = Path.cwd()
        try:
            os.chdir(root)
            preview = runner.invoke(app, ["git", "checkpoint", "--message", "chore: checkpoint local work"])
            assert preview.exit_code == 0, preview.output
            assert "preview_only: yes" in preview.output
            assert "checkpoint.txt" in preview.output
            assert _git(root, "rev-parse", "HEAD") == base_head
            assert "?? checkpoint.txt" in _git(root, "status", "--short")

            committed = runner.invoke(
                app,
                ["git", "checkpoint", "--message", "chore: checkpoint local work", "--yes"],
            )
            assert committed.exit_code == 0, committed.output
            assert "checkpoint: committed" in committed.output
            assert "clean: yes" in committed.output
            assert _git(root, "status", "--short") == ""
            assert _git(root, "log", "-1", "--pretty=%s") == "chore: checkpoint local work"
            assert _git(root, "rev-parse", "HEAD") != base_head
        finally:
            os.chdir(old_cwd)


def test_git_checkpoint_refuses_conflicted_or_empty_tree() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _init_repo(root)

        old_cwd = Path.cwd()
        try:
            os.chdir(root)
            empty = runner.invoke(app, ["git", "checkpoint", "--message", "chore: empty", "--yes"])
            assert empty.exit_code == 1, empty.output
            assert "No changes to checkpoint" in empty.output

            merge_head = Path(_git(root, "rev-parse", "--git-path", "MERGE_HEAD"))
            if not merge_head.is_absolute():
                merge_head = root / merge_head
            merge_head.write_text(_git(root, "rev-parse", "HEAD") + "\n", encoding="utf-8")

            operation = runner.invoke(app, ["git", "checkpoint", "--message", "chore: blocked", "--yes"])
            assert operation.exit_code == 1, operation.output
            assert "Git merge is in progress" in operation.output
        finally:
            os.chdir(old_cwd)


def test_promote_preview_detects_origin_main_stale_task_base() -> None:
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            base = Path(tmp)
            work, origin = _init_repo_with_origin(base)
            os.chdir(work)
            created = runner.invoke(app, ["task", "create", "--git-worktree", "origin stale"])
            assert created.exit_code == 0, created.output
            _advance_origin(base, origin)
            _run_git(work, "fetch", "origin")

            preview = runner.invoke(app, ["task", "promote-preview", "task-0001"])
            assert preview.exit_code == 0, preview.output
            assert "origin_baseline_status: changed" in preview.output
            assert "origin_baseline_stale: yes" in preview.output
            assert "promotion_readiness: not_ready" in preview.output
        finally:
            os.chdir(old_cwd)


def test_force_stale_baseline_allows_clean_git_task_after_origin_main_advanced() -> None:
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            base = Path(tmp)
            work, origin = _init_repo_with_origin(base)
            os.chdir(work)
            created = runner.invoke(app, ["task", "create", "--git-worktree", "clean stale origin"])
            assert created.exit_code == 0, created.output
            _advance_origin(base, origin)
            _run_git(work, "fetch", "origin")
            _run_git(work, "merge", "--ff-only", "origin/main")

            worktree = work / ".devflow/worktrees/task-0001/shell"
            (worktree / "worker.txt").write_text("worker result\n", encoding="utf-8")
            _run_git(worktree, "add", "worker.txt")
            _run_git(worktree, "commit", "-m", "worker result")
            _run_git(worktree, "merge", "--no-edit", "main")

            verified = runner.invoke(app, ["task", "verify", "task-0001", "--", "/bin/sh", "-c", "test -f worker.txt"])
            assert verified.exit_code == 0, verified.output

            preview = runner.invoke(app, ["task", "promote-preview", "task-0001"])
            assert preview.exit_code == 0, preview.output
            assert "origin_baseline_stale: yes" in preview.output
            assert "conflict_prediction: clean" in preview.output
            assert "promotion_readiness: not_ready" in preview.output

            promoted = runner.invoke(app, ["task", "promote", "task-0001", "--force-stale-baseline"], input="y\n")
            assert promoted.exit_code == 0, promoted.output
            assert "Warning: Forcing promotion with stale task baseline." in promoted.output
            assert "Promotion complete." in promoted.output
            assert (work / "worker.txt").read_text(encoding="utf-8") == "worker result\n"
        finally:
            os.chdir(old_cwd)


def test_promote_stops_on_conflict_and_writes_report() -> None:
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            root = Path(tmp)
            os.chdir(root)
            _init_repo(root)
            Path("base.txt").write_text("main base\n", encoding="utf-8")
            _run_git(root, "add", "base.txt")
            _run_git(root, "commit", "-m", "main base")

            created = runner.invoke(app, ["task", "create", "--git-worktree", "conflict task"])
            assert created.exit_code == 0, created.output
            worktree = root / ".devflow/worktrees/task-0001/shell"
            (worktree / "base.txt").write_text("worker change\n", encoding="utf-8")
            _run_git(worktree, "add", "base.txt")
            _run_git(worktree, "commit", "-m", "worker change")

            verified = runner.invoke(app, ["task", "verify", "task-0001", "--", "/bin/sh", "-c", "test -f base.txt"])
            assert verified.exit_code == 0, verified.output

            Path("base.txt").write_text("main conflict\n", encoding="utf-8")
            _run_git(root, "add", "base.txt")
            _run_git(root, "commit", "-m", "main conflict")

            promoted = runner.invoke(app, ["task", "promote", "task-0001", "--force-stale-baseline"], input="y\n")
            assert promoted.exit_code == 1, promoted.output
            assert "promotion refused: merge conflict predicted" in promoted.output
            report = root / ".devflow/tasks/task-0001/workers/shell/conflict-report.md"
            assert report.exists()
            assert "base.txt" in report.read_text(encoding="utf-8")
        finally:
            os.chdir(old_cwd)
