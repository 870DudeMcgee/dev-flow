from __future__ import annotations

import json
from pathlib import Path

import pytest

from devflow.legacy.control_room.service import create_task
from devflow.legacy.control_room.task_patch_gate_command import (
    TaskPatchGateCommandError,
    build_task_patch_dry_run_result,
    build_task_patch_review_result,
    render_task_patch_dry_run_lines,
    render_task_patch_review_lines,
)


def _task_path(root: Path, task_id: str = "task-0001") -> Path:
    return root / ".devflow" / "tasks" / task_id


def _workspace_path(root: Path, task_id: str = "task-0001") -> Path:
    return root / ".devflow" / "workspaces" / task_id


def _run_path(root: Path, run_id: str = "run-1") -> Path:
    path = _task_path(root) / "local-model-runs" / run_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def _modify_patch(path: str, old: str = "old", new: str = "new") -> str:
    return f"""diff --git a/{path} b/{path}
--- a/{path}
+++ b/{path}
@@ -1 +1 @@
-{old}
+{new}
"""


def _write_agent_patch(root: Path, agent_id: str, patch: str) -> None:
    agent_dir = _task_path(root) / "agents" / agent_id
    agent_dir.mkdir(parents=True, exist_ok=True)
    (agent_dir / "proposal.patch").write_text(patch, encoding="utf-8")


def _write_reviewed_run(
    root: Path,
    *,
    run_id: str = "run-1",
    patch: str,
    review_status: str = "low_risk_candidate",
    risk: str = "low",
    warnings: list[str] | None = None,
    high_risk_files: list[str] | None = None,
) -> None:
    run_path = _run_path(root, run_id)
    (run_path / "proposal.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "task_id": "task-0001",
                "run_id": run_id,
                "classification": "patch_candidate",
                "has_patch_candidate": True,
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    (run_path / "proposal.patch").write_text(patch, encoding="utf-8")
    (run_path / "patch-review.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "task_id": "task-0001",
                "run_id": run_id,
                "review_status": review_status,
                "risk": risk,
                "files_touched": [],
                "hunk_count": 1,
                "warnings": warnings or [],
                "high_risk_files": high_risk_files or [],
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def _write_workspace_file(root: Path, path: str, text: str) -> None:
    file_path = _workspace_path(root) / path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(text, encoding="utf-8")


def test_patch_review_command_module_renders_agent_project_output(tmp_path: Path) -> None:
    task = create_task(tmp_path, "command module review")
    _write_agent_patch(tmp_path, "qwopus-implementer", _modify_patch("docs/agent.md"))

    result = build_task_patch_review_result(
        tmp_path,
        task.id,
        agent_id="qwopus-implementer",
        project_id="alpha-app",
    )
    lines = render_task_patch_review_lines(result)

    assert lines == (
        "Patch Review for alpha-app:task-0001",
        f"project_root: {tmp_path}",
        "",
        "Run: agent-qwopus-implementer",
        "Proposal classification: patch_candidate",
        "Patch candidate: yes",
        "Review status: low_risk_candidate",
        "Risk: low",
        "",
        "Files touched:",
        "- docs/agent.md",
        "",
        "Artifacts:",
        "patch_review: .devflow/tasks/task-0001/local-model-runs/agent-qwopus-implementer/patch-review.md",
        "patch_review_json: .devflow/tasks/task-0001/local-model-runs/agent-qwopus-implementer/patch-review.json",
        "",
        "Next:",
        "devflow task show task-0001 --project alpha-app",
    )
    assert (_run_path(tmp_path, "agent-qwopus-implementer") / "patch-review.json").is_file()


def test_patch_dry_run_command_module_renders_findings_warnings_and_artifacts(tmp_path: Path) -> None:
    task = create_task(tmp_path, "command module dry-run")
    _write_workspace_file(tmp_path, "src/devflow/cli.py", "old\n")
    _write_reviewed_run(
        tmp_path,
        patch=_modify_patch("src/devflow/cli.py"),
        review_status="review_required",
        risk="high",
        warnings=["manual warning"],
        high_risk_files=["src/devflow/cli.py"],
    )

    result = build_task_patch_dry_run_result(tmp_path, task.id, run_id="run-1", project_id="alpha-app")
    lines = render_task_patch_dry_run_lines(result)

    assert lines == (
        "Patch Dry-run Preview for alpha-app:task-0001",
        f"project_root: {tmp_path}",
        "",
        "Run: run-1",
        "Patch review status: review_required",
        "Dry-run status: would_modify_with_warnings",
        "Risk: high",
        "",
        "Files checked:",
        "- src/devflow/cli.py",
        "",
        "Hunks:",
        "checked: 1",
        "matched: 1",
        "failed: 0",
        "",
        "Findings:",
        "- All checked hunks matched workspace content.",
        "",
        "Warnings:",
        "- manual warning",
        "- Patch review marked one or more files as high risk.",
        "",
        "Artifacts:",
        "dry_run: .devflow/tasks/task-0001/local-model-runs/run-1/patch-dry-run.md",
        "dry_run_json: .devflow/tasks/task-0001/local-model-runs/run-1/patch-dry-run.json",
        "",
        "Next:",
        "Review dry-run evidence manually. Do not apply anything automatically.",
    )
    assert (_run_path(tmp_path) / "patch-dry-run.json").is_file()
    assert (_workspace_path(tmp_path) / "src/devflow/cli.py").read_text(encoding="utf-8") == "old\n"


def test_patch_gate_command_module_maps_review_errors(tmp_path: Path) -> None:
    task = create_task(tmp_path, "command module missing run")

    with pytest.raises(TaskPatchGateCommandError, match=f"No local model runs found for task '{task.id}'"):
        build_task_patch_review_result(tmp_path, task.id)
