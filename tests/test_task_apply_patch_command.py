from __future__ import annotations

import json
from pathlib import Path

import pytest

from devflow.legacy.control_room.service import create_task
from devflow.legacy.control_room.task_apply_patch_command import (
    TaskApplyPatchCommandError,
    build_task_apply_patch_result,
    render_task_apply_patch_result,
)


def _task_path(root: Path, task_id: str) -> Path:
    return root / ".devflow" / "tasks" / task_id


def _workspace_path(root: Path, task_id: str) -> Path:
    return root / ".devflow" / "workspaces" / task_id


def _modify_patch(path: str, old: str, new: str) -> str:
    return (
        f"--- a/{path}\n"
        f"+++ b/{path}\n"
        "@@ -1 +1 @@\n"
        f"-{old}\n"
        f"+{new}\n"
    )


def _write_agent_patch(root: Path, task_id: str, agent_id: str, patch: str) -> None:
    agent_dir = _task_path(root, task_id) / "agents" / agent_id
    agent_dir.mkdir(parents=True, exist_ok=True)
    (agent_dir / "proposal.patch").write_text(patch, encoding="utf-8")


def _write_reviewed_dry_run(root: Path, task_id: str, patch: str, *, run_id: str = "run-1") -> None:
    run_path = _task_path(root, task_id) / "local-model-runs" / run_id
    run_path.mkdir(parents=True, exist_ok=True)
    patch_rel = f".devflow/tasks/{task_id}/local-model-runs/{run_id}/proposal.patch"
    review_rel = f".devflow/tasks/{task_id}/local-model-runs/{run_id}/patch-review.json"
    (run_path / "proposal.patch").write_text(patch, encoding="utf-8")
    (run_path / "patch-review.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "task_id": task_id,
                "run_id": run_id,
                "patch_path": patch_rel,
                "review_status": "low_risk_candidate",
                "risk": "low",
                "files_touched": ["hello.txt"],
                "hunk_count": 1,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (run_path / "patch-dry-run.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "task_id": task_id,
                "run_id": run_id,
                "proposal_patch_path": patch_rel,
                "patch_review_path": review_rel,
                "workspace_path": f".devflow/workspaces/{task_id}",
                "dry_run_status": "would_apply_cleanly",
                "risk": "low",
                "files_checked": ["hello.txt"],
                "files_missing": [],
                "files_would_create": [],
                "files_would_modify": ["hello.txt"],
                "files_would_delete": [],
                "hunks_checked": 1,
                "hunks_matched": 1,
                "hunks_failed": 0,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def test_build_task_apply_patch_result_renders_agent_patch_output(tmp_path: Path) -> None:
    task = create_task(tmp_path, "command module agent apply")
    hello_file = _workspace_path(tmp_path, task.id) / "hello.txt"
    hello_file.write_text("Hello World\n", encoding="utf-8")
    patch = _modify_patch("hello.txt", "Hello World", "Hello command module")
    _write_agent_patch(tmp_path, task.id, "agent-a", patch)
    _write_reviewed_dry_run(tmp_path, task.id, patch, run_id="agent-agent-a")

    result = build_task_apply_patch_result(tmp_path, task.id, agent_id="agent-a")
    lines = render_task_apply_patch_result(result)

    assert hello_file.read_text(encoding="utf-8") == "Hello command module\n"
    assert lines[0] == "Successfully applied patch from agent 'agent-a' to task workspace 'task-0001'."
    assert "Workspace: .devflow/workspaces/task-0001" in lines
    assert "Run ID: agent-agent-a" in lines
    assert any(line.startswith("Patch Hash: ") for line in lines)
    assert (
        "Patch Review: .devflow/tasks/task-0001/local-model-runs/agent-agent-a/patch-review.json"
        in lines
    )
    assert (
        "Patch Dry-run: .devflow/tasks/task-0001/local-model-runs/agent-agent-a/patch-dry-run.json"
        in lines
    )
    assert any(line.startswith("Patch Evidence: .devflow/tasks/task-0001/patches/") for line in lines)
    assert "Modified files:" in lines
    assert "  - hello.txt (modified)" in lines
    assert lines[-1] == '  devflow task verify task-0001 --shell "<command>"'


def test_build_task_apply_patch_result_renders_project_scoped_run_output(tmp_path: Path) -> None:
    task = create_task(tmp_path, "command module project apply")
    hello_file = _workspace_path(tmp_path, task.id) / "hello.txt"
    hello_file.write_text("Hello World\n", encoding="utf-8")
    patch = _modify_patch("hello.txt", "Hello World", "Hello project command")
    _write_reviewed_dry_run(tmp_path, task.id, patch, run_id="run-apply")

    result = build_task_apply_patch_result(
        tmp_path,
        task.id,
        run_id="run-apply",
        project_id="alpha-app",
    )
    lines = render_task_apply_patch_result(result)

    assert hello_file.read_text(encoding="utf-8") == "Hello project command\n"
    assert lines[0] == "Successfully applied patch from agent 'default' to task workspace 'alpha-app:task-0001'."
    assert f"project_root: {tmp_path}" in lines
    assert "Run ID: run-apply" in lines
    assert lines[-1] == '  devflow task verify task-0001 --project alpha-app --shell "<command>"'


def test_build_task_apply_patch_result_maps_patch_errors(tmp_path: Path) -> None:
    task = create_task(tmp_path, "command module missing patch")

    with pytest.raises(TaskApplyPatchCommandError, match=f"No patches found for task {task.id}"):
        build_task_apply_patch_result(tmp_path, task.id)
