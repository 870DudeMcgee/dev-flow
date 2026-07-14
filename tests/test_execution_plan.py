from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from devflow.loop import pipeline_run as pr
from devflow.loop.execution_plan import (
    ExecutionPacket,
    ExecutionPlan,
    ExecutionValidator,
    execution_plan_hash,
    load_execution_plan,
    run_execution_validators,
    save_execution_plan,
)


def _valid_plan() -> ExecutionPlan:
    return ExecutionPlan(
        target_files=["src/a.py", "tests/test_a.py"],
        packets=[
            ExecutionPacket(id="packet-01", target_files=["src/a.py"]),
            ExecutionPacket(
                id="packet-02",
                target_files=["tests/test_a.py"],
                depends_on=["packet-01"],
            ),
        ],
        validators=[
            ExecutionValidator(
                id="focused-tests",
                argv=["python", "-m", "pytest", "tests/test_a.py", "-q"],
                cwd=".",
                timeout_seconds=120,
                evidence=["pytest-exit-code", "pytest-output"],
            )
        ],
    )


def test_execution_plan_round_trips_typed_authoritative_contract() -> None:
    plan = _valid_plan()

    restored = ExecutionPlan.model_validate_json(plan.model_dump_json())

    assert restored.schema_version == 1
    assert restored.workflow_id == "canonical_product_build@1"
    assert restored.target_files == ["src/a.py", "tests/test_a.py"]
    assert restored.packets[1].depends_on == ["packet-01"]
    assert restored.validators[0].argv[:3] == ["python", "-m", "pytest"]
    assert restored.validators[0].network == "forbid"
    assert execution_plan_hash(restored) == execution_plan_hash(plan)
    assert len(execution_plan_hash(plan)) == 64


def test_execution_plan_hash_changes_with_authoritative_content() -> None:
    original = _valid_plan()
    changed = original.model_copy(
        update={"validators": [original.validators[0].model_copy(update={"timeout_seconds": 121})]}
    )

    assert execution_plan_hash(changed) != execution_plan_hash(original)


def test_execution_plan_persists_as_authoritative_json(tmp_path: Path) -> None:
    run_id = pr.create_pipeline_run(tmp_path, {"title": "typed plan"})

    save_execution_plan(tmp_path, run_id, _valid_plan())

    records = pr.load_pipeline_run(tmp_path, run_id)
    assert records["execution-plan.json"]["workflow_id"] == "canonical_product_build@1"
    assert load_execution_plan(tmp_path, run_id) == _valid_plan()


def test_missing_authoritative_plan_fails_with_actionable_error(tmp_path: Path) -> None:
    run_id = pr.create_pipeline_run(tmp_path, {"title": "missing plan"})

    with pytest.raises(ValueError, match="authoritative execution-plan.json"):
        load_execution_plan(tmp_path, run_id)


def test_typed_validator_runs_argv_without_a_shell(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import subprocess

    captured: dict = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        captured.update(kwargs)
        return subprocess.CompletedProcess(argv, 0, stdout="1 passed", stderr="")

    monkeypatch.setattr("devflow.loop.execution_plan.subprocess.run", fake_run)
    validator = _valid_plan().validators[0]

    receipts = run_execution_validators(tmp_path, [validator])

    assert captured["argv"] == validator.argv
    assert captured["shell"] is False
    assert captured["cwd"] == tmp_path.resolve()
    assert captured["timeout"] == 120
    assert receipts[0].passed is True
    assert receipts[0].exit_code == 0


def test_typed_validator_rejects_unallowlisted_executable() -> None:
    with pytest.raises(ValidationError, match="allowlisted"):
        ExecutionValidator(
            id="destructive",
            argv=["rm", "-rf", "."],
            evidence=["exit-code"],
        )


@pytest.mark.parametrize(
    "update",
    [
        {"target_files": ["/etc/passwd"]},
        {"target_files": ["../secrets.txt"]},
        {
            "packets": [
                {"id": "packet-01", "target_files": ["src/a.py"]},
                {"id": "packet-01", "target_files": ["tests/test_a.py"]},
            ]
        },
        {
            "packets": [
                {
                    "id": "packet-01",
                    "target_files": ["src/a.py"],
                    "depends_on": ["missing-packet"],
                }
            ]
        },
        {
            "packets": [
                {
                    "id": "packet-01",
                    "target_files": ["src/a.py"],
                    "depends_on": ["packet-02"],
                },
                {
                    "id": "packet-02",
                    "target_files": ["tests/test_a.py"],
                    "depends_on": ["packet-01"],
                },
            ]
        },
        {"packets": [{"id": "packet-01", "target_files": ["other.py"]}]},
        {
            "validators": [
                {
                    "id": "unsafe-shell",
                    "kind": "command",
                    "argv": "python -m pytest",
                }
            ]
        },
        {"validators": []},
    ],
)
def test_execution_plan_rejects_malformed_contracts(update: dict) -> None:
    payload = _valid_plan().model_dump(mode="json")
    payload.update(update)

    with pytest.raises(ValidationError):
        ExecutionPlan.model_validate(payload)
