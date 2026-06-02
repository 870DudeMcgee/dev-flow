from __future__ import annotations

import json
import os
from pathlib import Path

from typer.testing import CliRunner

from devflow.cli import app
from devflow.control_room.service import create_task
from devflow.control_room.worker_outcome import validate_worker_outcome_file


runner = CliRunner()


def _valid_outcome(task_id: str = "task-0001") -> dict:
    return {
        "schema_version": 1,
        "task_id": task_id,
        "worker": "shell",
        "source_kind": "shell_worker",
        "source_path": f".devflow/tasks/{task_id}/result.md",
        "outcome": "completed",
        "files_touched": ["src/devflow/control_room/example.py"],
        "commands_run": ["python -m pytest tests/test_example.py -q"],
        "tool_results": [{"tool": "shell", "status": "success_empty"}],
        "verification_status": "not_run",
        "retryable": False,
        "human_review_required": False,
        "notes": ["test fixture"],
        "created_at": "2026-06-02T00:00:00+00:00",
    }


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def test_valid_worker_outcome_passes_and_preserves_success_empty(tmp_path: Path) -> None:
    task = create_task(tmp_path, "Outcome validation")
    outcome_path = tmp_path / ".devflow" / "tasks" / task.id / "agents" / "shell" / "outcome.json"
    _write_json(outcome_path, _valid_outcome(task.id))

    result = validate_worker_outcome_file(tmp_path, outcome_path)

    assert result["status"] == "passed"
    assert result["observed_tool_statuses"] == ["success_empty"]
    validation_path = tmp_path / result["output_path"]
    assert validation_path.exists()
    assert validation_path.name == "worker-outcome-validation.json"


def test_missing_required_field_and_malformed_json_fail(tmp_path: Path) -> None:
    task = create_task(tmp_path, "Outcome validation")
    missing = _valid_outcome(task.id)
    missing.pop("worker")
    missing_path = tmp_path / "missing.json"
    _write_json(missing_path, missing)
    missing_result = validate_worker_outcome_file(tmp_path, missing_path)
    assert missing_result["status"] == "failed"
    assert any("missing required fields: worker" in error for error in missing_result["errors"])

    malformed_path = tmp_path / "malformed.json"
    malformed_path.write_text("{not json", encoding="utf-8")
    malformed_result = validate_worker_outcome_file(tmp_path, malformed_path)
    assert malformed_result["status"] == "failed"
    assert any("malformed JSON" in error for error in malformed_result["errors"])


def test_unknown_enums_and_tool_status_fail(tmp_path: Path) -> None:
    task = create_task(tmp_path, "Outcome validation")
    payload = _valid_outcome(task.id)
    payload["source_kind"] = "mystery"
    payload["outcome"] = "magic"
    payload["tool_results"] = [{"status": "sort_of_ok"}]
    path = tmp_path / "unknown.json"
    _write_json(path, payload)

    result = validate_worker_outcome_file(tmp_path, path)

    assert result["status"] == "failed"
    assert any("unknown source_kind" in error for error in result["errors"])
    assert any("unknown outcome" in error for error in result["errors"])
    assert any("unknown tool/result status" in error for error in result["errors"])


def test_unsafe_files_touched_paths_fail(tmp_path: Path) -> None:
    task = create_task(tmp_path, "Outcome validation")
    unsafe_values = [
        "/tmp/outside.py",
        "../outside.py",
        ".git/config",
        f".devflow/tasks/{task.id}/task.yaml",
    ]
    for value in unsafe_values:
        payload = _valid_outcome(task.id)
        payload["files_touched"] = [value]
        path = tmp_path / f"{value.replace('/', '_').replace('.', 'dot')}.json"
        _write_json(path, payload)

        result = validate_worker_outcome_file(tmp_path, path)

        assert result["status"] == "failed", value


def test_human_review_required_for_ambiguous_failed_and_no_useful_results(tmp_path: Path) -> None:
    task = create_task(tmp_path, "Outcome validation")
    cases = [
        {"outcome": "completed", "tool_results": [{"status": "ambiguous_needs_human"}]},
        {"outcome": "verification_failed", "tool_results": [{"status": "success_with_result"}]},
        {"outcome": "no_useful_result", "tool_results": [{"status": "success_empty"}]},
    ]
    for index, update in enumerate(cases):
        payload = _valid_outcome(task.id)
        payload.update(update)
        payload["human_review_required"] = False
        path = tmp_path / f"needs-review-{index}.json"
        _write_json(path, payload)

        result = validate_worker_outcome_file(tmp_path, path)

        assert result["status"] == "failed"
        assert any("human_review_required must be true" in error for error in result["errors"])


def test_source_path_task_id_mismatch_fails(tmp_path: Path) -> None:
    task = create_task(tmp_path, "Outcome validation")
    payload = _valid_outcome(task.id)
    payload["source_path"] = ".devflow/tasks/task-9999/result.md"
    path = tmp_path / "mismatch.json"
    _write_json(path, payload)

    result = validate_worker_outcome_file(tmp_path, path)

    assert result["status"] == "failed"
    assert any("source_path task id mismatch" in error for error in result["errors"])


def test_orchestration_plan_outcome_is_restricted(tmp_path: Path) -> None:
    task = create_task(tmp_path, "Outcome validation")
    payload = _valid_outcome(task.id)
    payload["source_kind"] = "orchestration_plan"
    payload["outcome"] = "completed"
    payload["human_review_required"] = False
    path = tmp_path / "orchestration-outcome.json"
    _write_json(path, payload)

    result = validate_worker_outcome_file(tmp_path, path)

    assert result["status"] == "failed"
    assert any("orchestration_plan source_kind" in error for error in result["errors"])


def test_local_patch_runtime_patch_proposed_requires_patch_evidence(tmp_path: Path) -> None:
    task = create_task(tmp_path, "Outcome validation")
    payload = _valid_outcome(task.id)
    payload["source_kind"] = "local_patch_runtime"
    payload["outcome"] = "patch_proposed"
    payload["human_review_required"] = False
    path = tmp_path / ".devflow" / "tasks" / task.id / "agents" / "qwopus-implementer" / "outcome.json"
    payload["source_path"] = f".devflow/tasks/{task.id}/agents/qwopus-implementer/outcome.json"
    _write_json(path, payload)

    missing_result = validate_worker_outcome_file(tmp_path, path)
    assert missing_result["status"] == "failed"
    assert any("proposal.patch evidence" in error for error in missing_result["errors"])

    (path.parent / "proposal.patch").write_text("--- a/a.py\n+++ b/a.py\n", encoding="utf-8")
    passed_result = validate_worker_outcome_file(tmp_path, path)
    assert passed_result["status"] == "passed"


def test_cli_writes_validation_without_mutating_task_yaml_or_source_files(tmp_path: Path) -> None:
    task = create_task(tmp_path, "Outcome validation")
    source = tmp_path / "src" / "devflow" / "control_room" / "example.py"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("original\n", encoding="utf-8")
    task_yaml = tmp_path / ".devflow" / "tasks" / task.id / "task.yaml"
    task_before = task_yaml.read_text(encoding="utf-8")
    source_before = source.read_text(encoding="utf-8")
    outcome_path = tmp_path / ".devflow" / "tasks" / task.id / "agents" / "shell" / "outcome.json"
    _write_json(outcome_path, _valid_outcome(task.id))

    old_cwd = Path.cwd()
    try:
        os.chdir(tmp_path)
        result = runner.invoke(app, ["worker", "validate-outcome", str(outcome_path)])
    finally:
        os.chdir(old_cwd)

    assert result.exit_code == 0, result.output
    assert "verification_run: no" in result.output
    assert "promotion_run: no" in result.output
    assert "provider_calls: none" in result.output
    assert task_yaml.read_text(encoding="utf-8") == task_before
    assert source.read_text(encoding="utf-8") == source_before
