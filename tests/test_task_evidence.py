"""Tests for `devflow task evidence` CLI command.

Tests:
1. task with qwen-planner run.json appears in evidence summary
2. task with qwen-planner and gemma-reviewer shows both
3. failed/timeout run prints warning
4. verified task shows verification status
5. missing workspace fails clearly
6. legacy qwen-response.md/gemma-review.md artifacts are discovered
7. command is read-only
"""
from __future__ import annotations

import os
import tempfile
import json
from pathlib import Path
from typing import Any

from typer.testing import CliRunner

from devflow.cli import app
from devflow.control_room.service import get_task

runner = CliRunner()


def test_task_evidence_qwen_run_json() -> None:
    """Verifies task with qwen-planner run.json appears in evidence summary."""
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)

            runner.invoke(app, ["task", "create", "test task 1"])
            
            # Create a run.json for qwen-planner
            worker_dir = Path(".devflow/workspaces/task-0001/local-workers/qwen-planner")
            worker_dir.mkdir(parents=True, exist_ok=True)
            
            run_data = {
                "task_id": "task-0001",
                "worker_name": "qwen-planner",
                "model": "qwen3.6:latest",
                "command": ["ollama", "run", "qwen3.6:latest"],
                "started_at": "2026-06-01T12:00:00Z",
                "finished_at": "2026-06-01T12:03:04Z",
                "duration_seconds": 184.2,
                "timeout_seconds": 600,
                "exit_code": 0,
                "status": "success",
                "response_path": ".devflow/workspaces/task-0001/local-workers/qwen-planner/response.md",
            }
            (worker_dir / "run.json").write_text(json.dumps(run_data), encoding="utf-8")
            (worker_dir / "response.md").write_text("Planner response content", encoding="utf-8")

            result = runner.invoke(app, ["task", "evidence", "task-0001"])
            assert result.exit_code == 0, result.output
            assert "Task: task-0001 test task 1" in result.output
            assert "Status: created" in result.output
            assert "Local workers:" in result.output
            assert "qwen-planner" in result.output
            assert "success" in result.output
            assert "184s" in result.output
            assert "response.md" in result.output
            assert "Artifacts:" in result.output
            assert ".devflow/workspaces/task-0001/local-workers/qwen-planner/response.md" in result.output
        finally:
            os.chdir(old_cwd)


def test_task_evidence_qwen_and_gemma() -> None:
    """Verifies task with qwen-planner and gemma-reviewer shows both."""
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)

            runner.invoke(app, ["task", "create", "test task 2"])
            
            # Setup qwen-planner
            qwen_dir = Path(".devflow/workspaces/task-0001/local-workers/qwen-planner")
            qwen_dir.mkdir(parents=True, exist_ok=True)
            qwen_data = {
                "task_id": "task-0001",
                "worker_name": "qwen-planner",
                "model": "qwen3.6:latest",
                "duration_seconds": 184.0,
                "status": "success",
                "response_path": "local-workers/qwen-planner/response.md",
            }
            (qwen_dir / "run.json").write_text(json.dumps(qwen_data), encoding="utf-8")
            (qwen_dir / "response.md").touch()

            # Setup gemma-reviewer
            gemma_dir = Path(".devflow/workspaces/task-0001/local-workers/gemma-reviewer")
            gemma_dir.mkdir(parents=True, exist_ok=True)
            gemma_data = {
                "task_id": "task-0001",
                "worker_name": "gemma-reviewer",
                "model": "gemma4:latest",
                "duration_seconds": 61.2,
                "status": "success",
                "response_path": "local-workers/gemma-reviewer/response.md",
            }
            (gemma_dir / "run.json").write_text(json.dumps(gemma_data), encoding="utf-8")
            (gemma_dir / "response.md").touch()

            result = runner.invoke(app, ["task", "evidence", "task-0001"])
            assert result.exit_code == 0, result.output
            assert "qwen-planner" in result.output
            assert "184s" in result.output
            assert "gemma-reviewer" in result.output
            assert "61s" in result.output
        finally:
            os.chdir(old_cwd)


def test_task_evidence_failed_timeout_warning() -> None:
    """Verifies failed/timeout runs print warnings and missing input worker logs."""
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)

            runner.invoke(app, ["task", "create", "test task 3"])
            
            # Setup a failed planner
            qwen_dir = Path(".devflow/workspaces/task-0001/local-workers/qwen-planner")
            qwen_dir.mkdir(parents=True, exist_ok=True)
            qwen_data = {
                "task_id": "task-0001",
                "worker_name": "qwen-planner",
                "model": "qwen3.6:latest",
                "duration_seconds": 10.0,
                "status": "failed",
                "response_path": "local-workers/qwen-planner/response.md",
                "error_message": "Exit code 1",
            }
            (qwen_dir / "run.json").write_text(json.dumps(qwen_data), encoding="utf-8")
            (qwen_dir / "response.md").touch()

            # Setup a timeout gemma-reviewer
            gemma_dir = Path(".devflow/workspaces/task-0001/local-workers/gemma-reviewer")
            gemma_dir.mkdir(parents=True, exist_ok=True)
            gemma_data = {
                "task_id": "task-0001",
                "worker_name": "gemma-reviewer",
                "model": "gemma4:latest",
                "duration_seconds": 600.0,
                "status": "timeout",
                "response_path": "local-workers/gemma-reviewer/response.md",
                "error_message": "Local worker 'gemma-reviewer' timed out after 600 seconds. Missing input worker output: qwen-planner",
            }
            (gemma_dir / "run.json").write_text(json.dumps(gemma_data), encoding="utf-8")
            (gemma_dir / "response.md").touch()

            result = runner.invoke(app, ["task", "evidence", "task-0001"])
            assert result.exit_code == 0, result.output
            assert "Warnings:" in result.output
            assert "- failed worker run: qwen-planner" in result.output
            assert "- timeout worker run: gemma-reviewer" in result.output
            assert "- missing input-worker output for: gemma-reviewer" in result.output
        finally:
            os.chdir(old_cwd)


def test_task_evidence_verified_status() -> None:
    """Verifies verified task shows verification status and command."""
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)

            runner.invoke(app, ["task", "create", "test task 4"])
            
            # Setup a passed verification
            t_dir = Path(".devflow/tasks/task-0001")
            t_dir.mkdir(parents=True, exist_ok=True)
            verification_data = {
                "schema_version": 1,
                "task_id": "task-0001",
                "command": "pytest tests/test_task_open.py -q",
                "status": "passed",
                "exit_code": 0,
            }
            (t_dir / "verification.json").write_text(json.dumps(verification_data), encoding="utf-8")

            # Need to touch workspace so checking it passes
            ws_dir = Path(".devflow/workspaces/task-0001")
            ws_dir.mkdir(parents=True, exist_ok=True)

            result = runner.invoke(app, ["task", "evidence", "task-0001"])
            assert result.exit_code == 0, result.output
            assert "Verification:" in result.output
            assert "passed  pytest tests/test_task_open.py -q" in result.output
            assert "unverified task" not in result.output
        finally:
            os.chdir(old_cwd)


def test_task_evidence_missing_workspace() -> None:
    """Verifies missing workspace fails clearly."""
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)

            runner.invoke(app, ["task", "create", "test task 5"])
            
            # Remove workspace folder
            import shutil
            shutil.rmtree(".devflow/workspaces/task-0001")

            result = runner.invoke(app, ["task", "evidence", "task-0001"])
            assert result.exit_code == 1, result.output
            assert "Error: Task workspace not found at" in result.output
        finally:
            os.chdir(old_cwd)


def test_task_evidence_legacy_artifacts() -> None:
    """Verifies legacy qwen-response.md/gemma-review.md artifacts are discovered and prioritized."""
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)

            runner.invoke(app, ["task", "create", "test task 6"])
            
            ws_dir = Path(".devflow/workspaces/task-0001")
            ws_dir.mkdir(parents=True, exist_ok=True)
            
            # Legacy files
            (ws_dir / "qwen-response.md").write_text("qwen response", encoding="utf-8")
            (ws_dir / "gemma-review.md").write_text("gemma review", encoding="utf-8")

            result = runner.invoke(app, ["task", "evidence", "task-0001"])
            assert result.exit_code == 0, result.output
            assert "Artifacts:" in result.output
            assert "qwen-response.md" in result.output
            assert "gemma-review.md" in result.output
        finally:
            os.chdir(old_cwd)


def test_task_evidence_read_only() -> None:
    """Verifies devflow task evidence is read-only and task info is unchanged."""
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)

            runner.invoke(app, ["task", "create", "test task 7"])
            
            ws_dir = Path(".devflow/workspaces/task-0001")
            ws_dir.mkdir(parents=True, exist_ok=True)

            yaml_path = Path(".devflow/tasks/task-0001/task.yaml")
            mtime_before = yaml_path.stat().st_mtime

            result = runner.invoke(app, ["task", "evidence", "task-0001"])
            assert result.exit_code == 0, result.output

            mtime_after = yaml_path.stat().st_mtime
            # Ensure task.yaml was not modified
            assert mtime_before == mtime_after
        finally:
            os.chdir(old_cwd)


def _write_local_run(
    workspace: Path,
    worker_name: str,
    *,
    run_id: str | None = None,
    model: str = "test-model:latest",
    status: str = "success",
    exit_code: int | None = 0,
    completed_at: str = "2026-06-01T12:00:00+00:00",
    response_text: str = "response body",
    raw_response_text: str = "raw response body",
    prompt_text: str | None = None,
    extra_run_data: dict[str, object] | None = None,
) -> Path:
    worker_dir = workspace / "local-workers" / worker_name
    evidence_dir = worker_dir / run_id if run_id is not None else worker_dir
    evidence_dir.mkdir(parents=True, exist_ok=True)

    response_path = evidence_dir / "response.md"
    response_path.write_text(response_text, encoding="utf-8")
    (evidence_dir / "response.raw.md").write_text(raw_response_text, encoding="utf-8")
    (evidence_dir / "prompt.md").write_text(prompt_text or "", encoding="utf-8")
    (evidence_dir / "stderr.log").write_text("", encoding="utf-8")

    run_data: dict[str, object] = {
        "task_id": "task-0001",
        "worker_name": worker_name,
        "model": model,
        "status": status,
        "exit_code": exit_code,
        "completed_at": completed_at,
        "response_path": response_path.as_posix(),
        "evidence_path": evidence_dir.as_posix(),
    }
    if run_id is not None:
        run_data["run_id"] = run_id
    if extra_run_data:
        run_data.update(extra_run_data)
    (evidence_dir / "run.json").write_text(json.dumps(run_data), encoding="utf-8")
    return evidence_dir


def test_task_evidence_local_summary_displays_latest_qwopus_run_id_and_evidence_dir(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["task", "create", "local summary task"])
    workspace = Path(".devflow/workspaces/task-0001")

    older_run = _write_local_run(
        workspace,
        "qwopus-implementer",
        run_id="run_20260601_120000_aaaa",
        model="qwopus:latest",
        completed_at="2026-06-01T12:00:00+00:00",
    )
    latest_run = _write_local_run(
        workspace,
        "qwopus-implementer",
        run_id="run_20260601_120500_bbbb",
        model="qwopus:latest",
        completed_at="2026-06-01T12:05:00+00:00",
    )
    os.utime(older_run / "run.json", (1, 1))
    os.utime(latest_run / "run.json", (2, 2))

    result = runner.invoke(app, ["task", "evidence", "task-0001", "--local"])

    assert result.exit_code == 0, result.output
    assert "Local runs for task-0001" in result.output
    assert "qwopus-implementer" in result.output
    assert "latest run: run_20260601_120500_bbbb" in result.output
    assert ".devflow/workspaces/task-0001/local-workers/qwopus-implementer/run_20260601_120500_bbbb" in result.output
    assert "run_20260601_120000_aaaa" not in result.output


def test_task_evidence_local_summary_uses_preferred_worker_order(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["task", "create", "ordered local summary task"])
    workspace = Path(".devflow/workspaces/task-0001")

    _write_local_run(workspace, "zeta-worker", run_id="run_20260601_120000_zeta")
    _write_local_run(
        workspace,
        "gemma-reviewer",
        run_id="run_20260601_120000_gemma",
        model="gemma4:latest",
        prompt_text="Input worker: qwopus-implementer\nSource: .devflow/workspaces/task-0001/local-workers/qwopus-implementer/run_20260601_120000_qwopus/response.md\n",
    )
    _write_local_run(workspace, "qwen-implementer", run_id="run_20260601_120000_qwenimpl", model="qwen3.6:latest")
    _write_local_run(workspace, "qwopus-implementer", run_id="run_20260601_120000_qwopus", model="qwopus:latest")
    _write_local_run(workspace, "qwen-planner", run_id="run_20260601_120000_qwen", model="qwen3.6:latest")

    result = runner.invoke(app, ["task", "evidence", "task-0001", "--local"])

    assert result.exit_code == 0, result.output
    planner_index = result.output.index("qwen-planner")
    qwopus_index = result.output.index("qwopus-implementer")
    qwen_impl_index = result.output.index("qwen-implementer")
    gemma_index = result.output.index("gemma-reviewer")
    zeta_index = result.output.index("zeta-worker")
    assert planner_index < qwopus_index < qwen_impl_index < gemma_index < zeta_index
    assert "reviewed: qwopus-implementer" in result.output


def test_task_evidence_local_summary_handles_no_local_evidence(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["task", "create", "empty local summary task"])

    result = runner.invoke(app, ["task", "evidence", "task-0001", "--local"])

    assert result.exit_code == 0, result.output
    assert "Local runs for task-0001" in result.output
    assert "No local AI evidence found." in result.output


def test_task_evidence_local_summary_handles_legacy_flat_worker_folder(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["task", "create", "legacy local summary task"])
    workspace = Path(".devflow/workspaces/task-0001")
    worker_dir = workspace / "local-workers" / "qwen-planner"
    worker_dir.mkdir(parents=True, exist_ok=True)
    (worker_dir / "response.md").write_text("legacy response", encoding="utf-8")

    result = runner.invoke(app, ["task", "evidence", "task-0001", "--local"])

    assert result.exit_code == 0, result.output
    assert "qwen-planner" in result.output
    assert "latest run: legacy" in result.output
    assert "model: unknown" in result.output
    assert ".devflow/workspaces/task-0001/local-workers/qwen-planner" in result.output


def test_task_evidence_local_summary_does_not_print_raw_or_full_response(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["task", "create", "quiet local summary task"])
    workspace = Path(".devflow/workspaces/task-0001")
    _write_local_run(
        workspace,
        "qwopus-implementer",
        run_id="run_20260601_120000_quiet",
        model="qwopus:latest",
        response_text="FULL RESPONSE BODY SHOULD NOT PRINT",
        raw_response_text="RAW MODEL BODY SHOULD NOT PRINT",
    )

    result = runner.invoke(app, ["task", "evidence", "task-0001", "--local"])

    assert result.exit_code == 0, result.output
    assert "FULL RESPONSE BODY SHOULD NOT PRINT" not in result.output
    assert "RAW MODEL BODY SHOULD NOT PRINT" not in result.output
    assert "response.raw.md" not in result.output


def test_task_evidence_local_summary_does_not_change_task_state(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["task", "create", "read only local summary task"])
    workspace = Path(".devflow/workspaces/task-0001")
    _write_local_run(workspace, "qwen-planner", run_id="run_20260601_120000_readonly", model="qwen3.6:latest")

    task_before = get_task(tmp_path, "task-0001")
    readiness_path = Path(".devflow/tasks/task-0001/merge-readiness.json")
    readiness_before = readiness_path.read_text(encoding="utf-8")

    result = runner.invoke(app, ["task", "evidence", "task-0001", "--local"])

    task_after = get_task(tmp_path, "task-0001")
    assert result.exit_code == 0, result.output
    assert task_after.status == task_before.status
    assert task_after.verification_status == task_before.verification_status
    assert readiness_path.read_text(encoding="utf-8") == readiness_before
