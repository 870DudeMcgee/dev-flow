from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest

from devflow.control_room.service import create_task, get_task
from devflow.control_room.task_evidence_summary import (
    TaskEvidenceSummaryError,
    build_task_evidence_summary,
    render_task_evidence_summary,
)


def test_task_evidence_summary_builds_and_renders_non_local_summary(tmp_path: Path) -> None:
    create_task(tmp_path, "module evidence task")
    task_path = tmp_path / ".devflow" / "tasks" / "task-0001"
    workspace = tmp_path / ".devflow" / "workspaces" / "task-0001"

    (task_path / "verification.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "task_id": "task-0001",
                "command": "pytest tests/test_task_evidence.py -q",
                "status": "passed",
                "exit_code": 0,
            }
        ),
        encoding="utf-8",
    )
    worker_dir = workspace / "local-workers" / "qwen-planner"
    worker_dir.mkdir(parents=True, exist_ok=True)
    (worker_dir / "run.json").write_text(
        json.dumps(
            {
                "task_id": "task-0001",
                "worker_name": "qwen-planner",
                "model": "qwen3.6:latest",
                "duration_seconds": 184.2,
                "status": "success",
                "response_path": "local-workers/qwen-planner/response.md",
            }
        ),
        encoding="utf-8",
    )
    (worker_dir / "response.md").write_text("Planner response content", encoding="utf-8")
    (workspace / "gemma-review.md").write_text("review", encoding="utf-8")

    summary = build_task_evidence_summary(tmp_path, "task-0001")
    lines = render_task_evidence_summary(summary)
    output = "\n".join(lines)

    assert summary.task_id == "task-0001"
    assert summary.verification is not None
    assert summary.verification.status == "passed"
    assert [run.name for run in summary.worker_runs] == ["qwen-planner"]
    assert "Task: task-0001 module evidence task" in output
    assert "passed  pytest tests/test_task_evidence.py -q" in output
    assert "qwen-planner" in output
    assert "184s" in output
    assert ".devflow/workspaces/task-0001/local-workers/qwen-planner/response.md" in output
    assert ".devflow/workspaces/task-0001/gemma-review.md" in output
    assert "unverified task" not in output
    assert "devflow task promote-preview task-0001" in output


def test_task_evidence_summary_local_uses_latest_run_without_response_bodies(tmp_path: Path) -> None:
    create_task(tmp_path, "local module summary task")
    workspace = tmp_path / ".devflow" / "workspaces" / "task-0001"
    older_run = _write_local_run(
        workspace,
        "qwopus-implementer",
        run_id="run_20260601_120000_old",
        response_text="OLDER RESPONSE BODY SHOULD NOT PRINT",
        raw_response_text="OLDER RAW BODY SHOULD NOT PRINT",
    )
    latest_run = _write_local_run(
        workspace,
        "qwopus-implementer",
        run_id="run_20260601_120500_latest",
        response_text="LATEST RESPONSE BODY SHOULD NOT PRINT",
        raw_response_text="LATEST RAW BODY SHOULD NOT PRINT",
    )
    os.utime(older_run / "run.json", (1, 1))
    os.utime(latest_run / "run.json", (2, 2))

    summary = build_task_evidence_summary(tmp_path, "task-0001", local=True)
    lines = render_task_evidence_summary(summary)
    output = "\n".join(lines)

    assert summary.local is True
    assert [item.run_id for item in summary.local_worker_summaries] == ["run_20260601_120500_latest"]
    assert "Local runs for task-0001" in output
    assert "latest run: run_20260601_120500_latest" in output
    assert ".devflow/workspaces/task-0001/local-workers/qwopus-implementer/run_20260601_120500_latest" in output
    assert "response.raw.md" not in output
    assert "LATEST RESPONSE BODY SHOULD NOT PRINT" not in output
    assert "LATEST RAW BODY SHOULD NOT PRINT" not in output
    assert "run_20260601_120000_old" not in output


def test_task_evidence_summary_missing_workspace_raises_user_facing_error(tmp_path: Path) -> None:
    create_task(tmp_path, "missing workspace module task")
    workspace = tmp_path / ".devflow" / "workspaces" / "task-0001"
    shutil.rmtree(workspace)

    with pytest.raises(TaskEvidenceSummaryError, match="Task workspace not found at"):
        build_task_evidence_summary(tmp_path, "task-0001")


def test_task_evidence_summary_builder_is_read_only(tmp_path: Path) -> None:
    create_task(tmp_path, "read only module summary task")
    task_yaml = tmp_path / ".devflow" / "tasks" / "task-0001" / "task.yaml"
    readiness_path = tmp_path / ".devflow" / "tasks" / "task-0001" / "merge-readiness.json"
    before_task = get_task(tmp_path, "task-0001")
    task_yaml_before = task_yaml.read_text(encoding="utf-8")
    readiness_before = readiness_path.read_text(encoding="utf-8")

    summary = build_task_evidence_summary(tmp_path, "task-0001")
    render_task_evidence_summary(summary)

    after_task = get_task(tmp_path, "task-0001")
    assert after_task.status == before_task.status
    assert after_task.verification_status == before_task.verification_status
    assert task_yaml.read_text(encoding="utf-8") == task_yaml_before
    assert readiness_path.read_text(encoding="utf-8") == readiness_before


def _write_local_run(
    workspace: Path,
    worker_name: str,
    *,
    run_id: str,
    response_text: str,
    raw_response_text: str,
) -> Path:
    evidence_dir = workspace / "local-workers" / worker_name / run_id
    evidence_dir.mkdir(parents=True, exist_ok=True)
    response_path = evidence_dir / "response.md"
    response_path.write_text(response_text, encoding="utf-8")
    (evidence_dir / "response.raw.md").write_text(raw_response_text, encoding="utf-8")
    (evidence_dir / "prompt.md").write_text("", encoding="utf-8")
    (evidence_dir / "run.json").write_text(
        json.dumps(
            {
                "task_id": "task-0001",
                "worker_name": worker_name,
                "model": "qwopus:latest",
                "status": "success",
                "exit_code": 0,
                "completed_at": "2026-06-01T12:05:00+00:00",
                "response_path": response_path.as_posix(),
                "evidence_path": evidence_dir.as_posix(),
                "run_id": run_id,
            }
        ),
        encoding="utf-8",
    )
    return evidence_dir
