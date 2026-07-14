from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from devflow.loop.execution_plan import ExecutionValidator
from devflow.loop.pipeline_run import create_pipeline_run, pipeline_runs_dir
from devflow.loop.validator_service import (
    ValidatorOutcome,
    ValidatorRequest,
    load_validator_receipt,
    run_validator,
)


def _validator(**updates: object) -> ExecutionValidator:
    payload = {
        "id": "syntax",
        "argv": ["python", "-m", "py_compile", "a.py"],
        "cwd": ".",
        "timeout_seconds": 30,
        "network": "forbid",
        "permissions": [],
        "evidence": ["exit-code"],
    }
    payload.update(updates)
    return ExecutionValidator.model_validate(payload)


def _request(**updates: object) -> ValidatorRequest:
    payload = {
        "receipt_id": "validator-syntax-1",
        "run_id": "run-placeholder",
        "snapshot_fingerprint": "a" * 64,
        "execution_plan_hash": "b" * 64,
        "validator": _validator(),
    }
    payload.update(updates)
    return ValidatorRequest.model_validate(payload)


def test_validator_runs_typed_argv_with_shell_false_and_persists_immutable_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_id = create_pipeline_run(tmp_path, {"repo": "test"})
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    captured: dict[str, object] = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        captured.update(kwargs)
        return subprocess.CompletedProcess(argv, 0, stdout="ok", stderr="")

    monkeypatch.setattr("devflow.loop.validator_service.subprocess.run", fake_run)
    request = _request(run_id=run_id)
    receipt = run_validator(tmp_path, workspace, request)

    assert captured["argv"] == request.validator.argv
    assert captured["shell"] is False
    assert captured["cwd"] == workspace.resolve()
    assert captured["timeout"] == 30
    assert receipt.outcome is ValidatorOutcome.passed
    assert receipt.passed is True
    assert load_validator_receipt(tmp_path, run_id, request.receipt_id) == receipt

    path = pipeline_runs_dir(tmp_path) / run_id / "validator-receipts" / f"{request.receipt_id}.json"
    before = path.read_bytes()
    with pytest.raises(ValueError, match="conflicting validator receipt"):
        run_validator(tmp_path, workspace, request.model_copy(update={"snapshot_fingerprint": "c" * 64}))
    assert path.read_bytes() == before


def test_identical_validator_receipt_replay_is_idempotent_without_respawn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_id = create_pipeline_run(tmp_path, {"repo": "test"})
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    calls = 0

    def fake_run(argv, **kwargs):
        nonlocal calls
        calls += 1
        return subprocess.CompletedProcess(argv, 0, stdout="ok", stderr="")

    monkeypatch.setattr("devflow.loop.validator_service.subprocess.run", fake_run)
    request = _request(run_id=run_id)
    first = run_validator(tmp_path, workspace, request)
    second = run_validator(tmp_path, workspace, request)
    assert second == first
    assert calls == 1


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        ("spawn", ValidatorOutcome.spawn_error),
        ("timeout", ValidatorOutcome.timeout),
        ("nonzero", ValidatorOutcome.nonzero),
        ("malformed", ValidatorOutcome.malformed_evidence),
    ],
)
def test_validator_failures_are_explicit_and_never_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str, expected: ValidatorOutcome
) -> None:
    run_id = create_pipeline_run(tmp_path, {"repo": "test"})
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    def fake_run(argv, **kwargs):
        if mode == "spawn":
            raise OSError("missing")
        if mode == "timeout":
            raise subprocess.TimeoutExpired(argv, 30)
        if mode == "nonzero":
            return subprocess.CompletedProcess(argv, 2, stdout="", stderr="bad")
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr("devflow.loop.validator_service.subprocess.run", fake_run)
    validator = _validator(evidence=["output"] if mode == "malformed" else ["exit-code"])
    receipt = run_validator(tmp_path, workspace, _request(run_id=run_id, validator=validator))
    assert receipt.outcome is expected
    assert receipt.passed is False


def test_validator_rejects_missing_declared_output_stream(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_id = create_pipeline_run(tmp_path, {"repo": "test"})
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    def fake_run(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 0, stdout="only stdout", stderr="")

    monkeypatch.setattr("devflow.loop.validator_service.subprocess.run", fake_run)
    receipt = run_validator(
        tmp_path,
        workspace,
        _request(run_id=run_id, validator=_validator(evidence=["stderr"])),
    )
    assert receipt.outcome is ValidatorOutcome.malformed_evidence
    assert receipt.passed is False


def test_validator_rejects_cwd_escape_missing_directory_wrong_run_and_corrupt_receipt(
    tmp_path: Path,
) -> None:
    run_id = create_pipeline_run(tmp_path, {"repo": "test"})
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    request = _request(run_id=run_id, validator=_validator(cwd="missing"))
    receipt = run_validator(tmp_path, workspace, request)
    assert receipt.outcome is ValidatorOutcome.invalid_cwd
    assert not receipt.passed

    with pytest.raises(ValueError, match="does not match"):
        run_validator(tmp_path, workspace, _request(run_id="wrong-run"))

    receipts_dir = pipeline_runs_dir(tmp_path) / run_id / "validator-receipts"
    receipts_dir.mkdir(exist_ok=True)
    corrupt = receipts_dir / "corrupt.json"
    corrupt.write_text(json.dumps({"receipt_id": "corrupt"}))
    with pytest.raises(ValueError, match="missing or corrupt"):
        load_validator_receipt(tmp_path, run_id, "corrupt")
