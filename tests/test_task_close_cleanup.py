from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

from typer.testing import CliRunner

from devflow.cli import app
from devflow.control_room.service import get_task


runner = CliRunner()


def _init_git_repo() -> None:
    subprocess.run(["git", "init", "-b", "main"], check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], check=True)
    Path("base.txt").write_text("base\n", encoding="utf-8")
    Path(".gitignore").write_text(".devflow/\n", encoding="utf-8")
    subprocess.run(["git", "add", "base.txt", ".gitignore"], check=True)
    subprocess.run(["git", "commit", "-m", "init"], check=True)


def _with_temp_cwd(callback) -> None:
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            callback(Path(tmp))
        finally:
            os.chdir(old_cwd)


def test_close_requires_outcome_and_reason() -> None:
    def scenario(_: Path) -> None:
        create = runner.invoke(app, ["task", "create", "close me"])
        assert create.exit_code == 0, create.output

        missing_outcome = runner.invoke(app, ["task", "close", "task-0001", "--reason", "done"])
        assert missing_outcome.exit_code != 0
        assert "outcome" in missing_outcome.output.lower()

        missing_reason = runner.invoke(app, ["task", "close", "task-0001", "--outcome", "abandoned"])
        assert missing_reason.exit_code != 0
        assert "reason" in missing_reason.output.lower()

    _with_temp_cwd(scenario)


def test_close_writes_closure_evidence_and_event() -> None:
    def scenario(_: Path) -> None:
        assert runner.invoke(app, ["task", "create", "close evidence"]).exit_code == 0

        close = runner.invoke(
            app,
            ["task", "close", "task-0001", "--outcome", "rejected", "--reason", "proposal was unsafe"],
        )
        assert close.exit_code == 0, close.output

        closure = json.loads(Path(".devflow/tasks/task-0001/closure.json").read_text(encoding="utf-8"))
        assert closure["task_id"] == "task-0001"
        assert closure["outcome"] == "rejected"
        assert closure["reason"] == "proposal was unsafe"
        assert closure["previous_status"] == "created"
        assert closure["worktree_exists"] is True
        assert closure["next_suggested_action"] == "devflow task cleanup task-0001 --preview"

        events = Path(".devflow/tasks/task-0001/events.jsonl").read_text(encoding="utf-8")
        assert '"event": "task_closed"' in events
        task = get_task(Path.cwd(), "task-0001")
        assert task.status == "closed"
        assert task.close_outcome == "rejected"

    _with_temp_cwd(scenario)


def test_task_show_closed_task_is_obvious_and_inactive() -> None:
    def scenario(_: Path) -> None:
        assert runner.invoke(app, ["task", "create", "show closed"]).exit_code == 0
        assert runner.invoke(
            app,
            ["task", "close", "task-0001", "--outcome", "evidence-only", "--reason", "kept for evidence"],
        ).exit_code == 0

        show = runner.invoke(app, ["task", "show", "task-0001"])
        assert show.exit_code == 0, show.output
        assert "closed: yes" in show.output
        assert "outcome: evidence-only" in show.output
        assert "reason: kept for evidence" in show.output
        assert "next_action: devflow task cleanup task-0001 --preview" in show.output
        assert "devflow task run task-0001" not in show.output
        assert "devflow task verify task-0001" not in show.output
        assert "devflow task promote task-0001" not in show.output

    _with_temp_cwd(scenario)


def test_close_preserves_logs_and_evidence() -> None:
    def scenario(_: Path) -> None:
        assert runner.invoke(app, ["task", "create", "preserve evidence"]).exit_code == 0
        log_path = Path(".devflow/tasks/task-0001/logs/worker.log")
        agent_path = Path(".devflow/tasks/task-0001/agents/qwopus-implementer/proposal.patch")
        log_path.write_text("log evidence\n", encoding="utf-8")
        agent_path.parent.mkdir(parents=True, exist_ok=True)
        agent_path.write_text("diff --git a/a b/a\n", encoding="utf-8")

        close = runner.invoke(
            app,
            ["task", "close", "task-0001", "--outcome", "rejected", "--reason", "unsafe patch"],
        )
        assert close.exit_code == 0, close.output
        assert log_path.read_text(encoding="utf-8") == "log evidence\n"
        assert agent_path.read_text(encoding="utf-8") == "diff --git a/a b/a\n"

    _with_temp_cwd(scenario)


def test_cleanup_preview_refuses_active_task() -> None:
    def scenario(_: Path) -> None:
        assert runner.invoke(app, ["task", "create", "active cleanup"]).exit_code == 0

        cleanup = runner.invoke(app, ["task", "cleanup", "task-0001", "--preview"])
        assert cleanup.exit_code == 1
        assert "Refusing cleanup for unclosed task" in cleanup.output

    _with_temp_cwd(scenario)


def test_cleanup_preview_closed_task_lists_candidates_without_deleting() -> None:
    def scenario(_: Path) -> None:
        assert runner.invoke(app, ["task", "create", "preview cleanup"]).exit_code == 0
        workspace = Path(".devflow/workspaces/task-0001")
        workspace_file = workspace / "artifact.txt"
        workspace_file.write_text("runtime\n", encoding="utf-8")
        assert runner.invoke(
            app,
            ["task", "close", "task-0001", "--outcome", "abandoned", "--reason", "not needed"],
        ).exit_code == 0

        cleanup = runner.invoke(app, ["task", "cleanup", "task-0001", "--preview"])
        assert cleanup.exit_code == 0, cleanup.output
        assert "mode: preview" in cleanup.output
        assert "would_remove: .devflow/workspaces/task-0001" in cleanup.output
        assert "retained: .devflow/tasks/task-0001/task.yaml" in cleanup.output
        assert workspace_file.exists()

    _with_temp_cwd(scenario)


def test_cleanup_apply_refuses_unsafe_paths_outside_devflow() -> None:
    def scenario(tmp: Path) -> None:
        assert runner.invoke(app, ["task", "create", "unsafe cleanup"]).exit_code == 0
        assert runner.invoke(
            app,
            ["task", "close", "task-0001", "--outcome", "abandoned", "--reason", "unsafe path test"],
        ).exit_code == 0
        task_yaml = Path(".devflow/tasks/task-0001/task.yaml")
        task_yaml.write_text(
            task_yaml.read_text(encoding="utf-8").replace(
                'workspace: ".devflow/workspaces/task-0001"',
                f'workspace: "{(tmp / "outside-workspace").as_posix()}"',
            ),
            encoding="utf-8",
        )

        cleanup = runner.invoke(app, ["task", "cleanup", "task-0001", "--apply"])
        assert cleanup.exit_code == 1
        assert "escapes .devflow" in cleanup.output

    _with_temp_cwd(scenario)


def test_cleanup_apply_removes_safe_workspace_and_writes_evidence() -> None:
    def scenario(_: Path) -> None:
        assert runner.invoke(app, ["task", "create", "apply cleanup"]).exit_code == 0
        workspace = Path(".devflow/workspaces/task-0001")
        (workspace / "artifact.txt").write_text("runtime\n", encoding="utf-8")
        assert runner.invoke(
            app,
            ["task", "close", "task-0001", "--outcome", "evidence-only", "--reason", "runtime no longer needed"],
        ).exit_code == 0

        cleanup = runner.invoke(app, ["task", "cleanup", "task-0001", "--apply"])
        assert cleanup.exit_code == 0, cleanup.output
        assert "removed: .devflow/workspaces/task-0001" in cleanup.output
        assert not workspace.exists()
        assert Path(".devflow/tasks/task-0001/task.yaml").exists()
        assert Path(".devflow/tasks/task-0001/events.jsonl").exists()
        assert Path(".devflow/tasks/task-0001/closure.json").exists()

        evidence = json.loads(Path(".devflow/tasks/task-0001/cleanup.json").read_text(encoding="utf-8"))
        assert evidence["task_id"] == "task-0001"
        assert evidence["applied"] is True
        assert evidence["removed"] == [".devflow/workspaces/task-0001"]
        events = Path(".devflow/tasks/task-0001/events.jsonl").read_text(encoding="utf-8")
        assert '"event": "task_cleanup_applied"' in events

        show = runner.invoke(app, ["task", "show", "task-0001"])
        assert show.exit_code == 0, show.output
        assert "closed: yes" in show.output
        assert "next_action: none" in show.output
        assert "suggested_next_action: none" in show.output

    _with_temp_cwd(scenario)


def test_doctor_allows_closed_task_after_workspace_cleanup() -> None:
    def scenario(_: Path) -> None:
        assert runner.invoke(app, ["task", "create", "closed doctor cleanup"]).exit_code == 0
        assert runner.invoke(
            app,
            ["task", "close", "task-0001", "--outcome", "evidence-only", "--reason", "runtime no longer needed"],
        ).exit_code == 0
        assert runner.invoke(app, ["task", "cleanup", "task-0001", "--apply"]).exit_code == 0

        doctor = runner.invoke(app, ["doctor"])

        assert doctor.exit_code == 0, doctor.output
        assert "ok: task-0001 workspace (closed task workspace not required: .devflow/workspaces/task-0001)" in doctor.output

    _with_temp_cwd(scenario)


def test_closed_outcomes_are_visible_in_task_list() -> None:
    def scenario(_: Path) -> None:
        assert runner.invoke(app, ["task", "create", "duplicate task"]).exit_code == 0
        assert runner.invoke(
            app,
            ["task", "close", "task-0001", "--outcome", "duplicate", "--reason", "same as another task"],
        ).exit_code == 0

        listing = runner.invoke(app, ["task", "list"])
        assert listing.exit_code == 0, listing.output
        assert "task-0001" in listing.output
        assert "closed/duplicate" in listing.output

        closed_only = runner.invoke(app, ["task", "list", "--closed"])
        assert closed_only.exit_code == 0, closed_only.output
        assert "task-0001" in closed_only.output

        active_only = runner.invoke(app, ["task", "list", "--active"])
        assert active_only.exit_code == 0, active_only.output
        assert "task-0001" not in active_only.output

    _with_temp_cwd(scenario)


def test_cleanup_apply_removes_git_worktree_directory_conservatively() -> None:
    def scenario(_: Path) -> None:
        _init_git_repo()
        create = runner.invoke(app, ["task", "create", "--git-worktree", "git cleanup"])
        assert create.exit_code == 0, create.output
        worktree = Path(".devflow/worktrees/task-0001/shell")
        assert worktree.exists()
        assert runner.invoke(
            app,
            ["task", "close", "task-0001", "--outcome", "rejected", "--reason", "not promoting"],
        ).exit_code == 0

        cleanup = runner.invoke(app, ["task", "cleanup", "task-0001", "--apply"])
        assert cleanup.exit_code == 0, cleanup.output
        assert "removed: .devflow/worktrees/task-0001/shell" in cleanup.output
        assert not worktree.exists()

    _with_temp_cwd(scenario)


def test_prune_closed_preview_lists_old_closed_evidence_without_deleting() -> None:
    def scenario(_: Path) -> None:
        assert runner.invoke(app, ["task", "create", "old closed evidence"]).exit_code == 0
        assert runner.invoke(
            app,
            ["task", "close", "task-0001", "--outcome", "evidence-only", "--reason", "preview pruning"],
        ).exit_code == 0

        prune = runner.invoke(app, ["task", "prune-closed", "--preview", "--older-than", "0s"])

        assert prune.exit_code == 0, prune.output
        assert "mode: preview" in prune.output
        assert "would_prune: .devflow/tasks/task-0001" in prune.output
        assert "audit: .devflow/prune-runs/" in prune.output
        assert Path(".devflow/tasks/task-0001/task.yaml").exists()

    _with_temp_cwd(scenario)


def test_prune_closed_apply_deletes_only_eligible_closed_evidence() -> None:
    def scenario(_: Path) -> None:
        assert runner.invoke(app, ["task", "create", "closed prune apply"]).exit_code == 0
        assert runner.invoke(
            app,
            ["task", "close", "task-0001", "--outcome", "abandoned", "--reason", "delete old evidence"],
        ).exit_code == 0
        assert runner.invoke(app, ["task", "create", "active survives pruning"]).exit_code == 0

        prune = runner.invoke(app, ["task", "prune-closed", "--apply", "--older-than", "0s"])

        assert prune.exit_code == 0, prune.output
        assert "mode: apply" in prune.output
        assert "pruned: .devflow/tasks/task-0001" in prune.output
        assert "refused: task-0002 active task" in prune.output
        assert not Path(".devflow/tasks/task-0001").exists()
        assert Path(".devflow/tasks/task-0002/task.yaml").exists()
        audit_files = list(Path(".devflow/prune-runs").glob("*.json"))
        assert len(audit_files) == 1
        audit = json.loads(audit_files[0].read_text(encoding="utf-8"))
        assert audit["applied"] is True
        assert audit["pruned"] == [".devflow/tasks/task-0001"]

    _with_temp_cwd(scenario)


def test_prune_closed_skips_recently_closed_tasks() -> None:
    def scenario(_: Path) -> None:
        assert runner.invoke(app, ["task", "create", "recent closed evidence"]).exit_code == 0
        assert runner.invoke(
            app,
            ["task", "close", "task-0001", "--outcome", "evidence-only", "--reason", "too recent"],
        ).exit_code == 0

        prune = runner.invoke(app, ["task", "prune-closed", "--apply", "--older-than", "3650d"])

        assert prune.exit_code == 0, prune.output
        assert "skipped: task-0001 recently closed" in prune.output
        assert "pruned:" not in prune.output
        assert Path(".devflow/tasks/task-0001/task.yaml").exists()

    _with_temp_cwd(scenario)


def test_prune_closed_refuses_missing_closure_metadata() -> None:
    def scenario(_: Path) -> None:
        assert runner.invoke(app, ["task", "create", "missing closure"]).exit_code == 0
        assert runner.invoke(
            app,
            ["task", "close", "task-0001", "--outcome", "evidence-only", "--reason", "metadata test"],
        ).exit_code == 0
        Path(".devflow/tasks/task-0001/closure.json").unlink()

        prune = runner.invoke(app, ["task", "prune-closed", "--apply", "--older-than", "0s"])

        assert prune.exit_code == 0, prune.output
        assert "refused: task-0001 missing closure metadata" in prune.output
        assert Path(".devflow/tasks/task-0001/task.yaml").exists()

    _with_temp_cwd(scenario)


def test_prune_closed_refuses_unsafe_task_evidence_paths() -> None:
    def scenario(tmp: Path) -> None:
        assert runner.invoke(app, ["task", "create", "unsafe prune path"]).exit_code == 0
        assert runner.invoke(
            app,
            ["task", "close", "task-0001", "--outcome", "evidence-only", "--reason", "unsafe path test"],
        ).exit_code == 0
        unsafe_target = tmp / "outside-task-evidence"
        Path(".devflow/tasks/task-0001").rename(unsafe_target)
        Path(".devflow/tasks/task-0001").symlink_to(unsafe_target, target_is_directory=True)

        prune = runner.invoke(app, ["task", "prune-closed", "--apply", "--older-than", "0s"])

        assert prune.exit_code == 0, prune.output
        assert "refused: task-0001 unsafe task evidence path" in prune.output
        assert (unsafe_target / "task.yaml").exists()
        assert Path(".devflow/tasks/task-0001").is_symlink()

    _with_temp_cwd(scenario)
