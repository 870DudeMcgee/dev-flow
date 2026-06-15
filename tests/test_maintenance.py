from __future__ import annotations

import os
import subprocess
from pathlib import Path

from typer.testing import CliRunner

from devflow.cli import app
from devflow.control_room.service import create_task, doctor


runner = CliRunner()


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)


def _init_repo_with_tracked_seed(root: Path) -> None:
    _git(root, "init", "-b", "main")
    _git(root, "config", "user.email", "maintenance@example.com")
    _git(root, "config", "user.name", "Maintenance Test")
    (root / ".gitignore").write_text(".devflow/\n", encoding="utf-8")
    (root / ".devflow" / "tasks").mkdir(parents=True)
    (root / ".devflow" / "config.yaml").write_text("version: 1\n", encoding="utf-8")
    (root / ".devflow" / "tasks" / "README.md").write_text("# Task seed\n", encoding="utf-8")
    _git(root, "add", ".gitignore")
    _git(root, "add", "-f", ".devflow/config.yaml", ".devflow/tasks/README.md")
    _git(root, "commit", "-m", "seed")


def test_doctor_reports_missing_baseline_artifacts(tmp_path: Path) -> None:
    task = create_task(tmp_path, "missing baseline")
    task_path = tmp_path / ".devflow" / "tasks" / task.id
    (task_path / "merge-readiness.json").unlink()
    (task_path / "logs" / "worker.log").unlink()

    failed = {name: detail for name, ok, detail in doctor(tmp_path) if not ok}

    assert failed[f"{task.id} baseline artifacts"] == "missing: logs/worker.log, merge-readiness.json"


def test_repair_state_restores_missing_artifacts_without_overwriting_evidence(tmp_path: Path) -> None:
    task = create_task(tmp_path, "repair baseline")
    task_path = tmp_path / ".devflow" / "tasks" / task.id
    worker_log = task_path / "logs" / "worker.log"
    worker_log.write_text("existing worker evidence\n", encoding="utf-8")
    (task_path / "result.md").unlink()
    (task_path / "verification.json").unlink()
    (task_path / "logs" / "verify.log").unlink()
    (task_path / "merge-readiness.json").unlink()

    old_cwd = Path.cwd()
    try:
        os.chdir(tmp_path)
        preview = runner.invoke(app, ["maintenance", "repair-state", "--preview"], catch_exceptions=False)
        assert not (task_path / "result.md").exists()
        repaired = runner.invoke(app, ["maintenance", "repair-state", "--yes"], catch_exceptions=False)
    finally:
        os.chdir(old_cwd)

    assert preview.exit_code == 0, preview.output
    assert "mode: preview" in preview.output
    assert f"would_repair: .devflow/tasks/{task.id}/result.md" in preview.output
    assert repaired.exit_code == 0, repaired.output
    assert "mode: apply" in repaired.output
    assert (task_path / "result.md").exists()
    assert (task_path / "verification.json").exists()
    assert (task_path / "logs" / "verify.log").exists()
    assert (task_path / "merge-readiness.json").exists()
    assert worker_log.read_text(encoding="utf-8") == "existing worker evidence\n"


def test_reset_dogfood_state_preview_lists_only_allowlisted_runtime_artifacts(tmp_path: Path) -> None:
    _init_repo_with_tracked_seed(tmp_path)
    runtime_paths = [
        ".devflow/tasks/task-0001",
        ".devflow/workspaces/task-0001",
        ".devflow/worktrees/task-0001",
        ".devflow/prune-runs",
        ".devflow/dogfood",
        ".devflow/agent-runs",
        ".devflow/knowledge",
        ".devflow/outcome-validations",
        ".devflow/release",
    ]
    for rel in runtime_paths:
        path = tmp_path / rel
        path.mkdir(parents=True, exist_ok=True)
        (path / "evidence.txt").write_text("runtime\n", encoding="utf-8")
    (tmp_path / ".devflow" / "artifacts").mkdir()
    (tmp_path / ".devflow" / "artifacts" / "keep.txt").write_text("keep\n", encoding="utf-8")

    old_cwd = Path.cwd()
    try:
        os.chdir(tmp_path)
        preview = runner.invoke(app, ["maintenance", "reset-dogfood-state", "--preview"], catch_exceptions=False)
    finally:
        os.chdir(old_cwd)

    assert preview.exit_code == 0, preview.output
    assert "mode: preview" in preview.output
    for rel in runtime_paths:
        assert f"would_remove: {rel}" in preview.output
        assert (tmp_path / rel).exists()
    assert ".devflow/artifacts" not in preview.output
    assert (tmp_path / ".devflow" / "config.yaml").exists()
    assert (tmp_path / ".devflow" / "tasks" / "README.md").exists()


def test_reset_dogfood_state_apply_deletes_runtime_and_preserves_tracked_seed(tmp_path: Path) -> None:
    _init_repo_with_tracked_seed(tmp_path)
    for rel in [".devflow/tasks/task-0001", ".devflow/workspaces/task-0001", ".devflow/dogfood"]:
        path = tmp_path / rel
        path.mkdir(parents=True, exist_ok=True)
        (path / "evidence.txt").write_text("runtime\n", encoding="utf-8")

    old_cwd = Path.cwd()
    try:
        os.chdir(tmp_path)
        applied = runner.invoke(app, ["maintenance", "reset-dogfood-state", "--yes"], catch_exceptions=False)
    finally:
        os.chdir(old_cwd)

    assert applied.exit_code == 0, applied.output
    assert "mode: apply" in applied.output
    assert not (tmp_path / ".devflow" / "tasks" / "task-0001").exists()
    assert not (tmp_path / ".devflow" / "workspaces" / "task-0001").exists()
    assert not (tmp_path / ".devflow" / "dogfood").exists()
    assert (tmp_path / ".devflow" / "config.yaml").read_text(encoding="utf-8") == "version: 1\n"
    assert (tmp_path / ".devflow" / "tasks" / "README.md").exists()


def test_reset_dogfood_state_refuses_symlink_escape(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep.txt").write_text("keep\n", encoding="utf-8")
    task_link = tmp_path / ".devflow" / "tasks" / "task-0001"
    task_link.parent.mkdir(parents=True)
    task_link.symlink_to(outside, target_is_directory=True)

    old_cwd = Path.cwd()
    try:
        os.chdir(tmp_path)
        result = runner.invoke(app, ["maintenance", "reset-dogfood-state", "--yes"], catch_exceptions=False)
    finally:
        os.chdir(old_cwd)

    assert result.exit_code == 1, result.output
    assert "refused: .devflow/tasks/task-0001 escapes .devflow" in result.output
    assert task_link.is_symlink()
    assert (outside / "keep.txt").exists()
