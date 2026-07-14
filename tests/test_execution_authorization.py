from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from devflow.loop.adapter import create_run_with_state
from devflow.loop.execution_authorization import (
    authorize_execution,
    load_execution_authorization,
)
from devflow.loop.execution_plan import (
    ExecutionPacket,
    ExecutionPlan,
    ExecutionValidator,
    execution_plan_hash,
    save_execution_plan,
)
from devflow.loop.pipeline_run import create_pipeline_run, pipeline_runs_dir
from devflow.loop.source_snapshot import (
    SnapshotReceipt,
    SnapshotRequest,
    create_source_snapshot,
)
from devflow.loop.validator_service import ValidatorRequest, run_validator
from devflow.loop.workflow_ledger import replay_workflow_run


def _plan() -> ExecutionPlan:
    return ExecutionPlan(
        target_files=["src/a.py", "tests/test_a.py"],
        packets=[
            ExecutionPacket(id="packet-b", target_files=["tests/test_a.py"], depends_on=["packet-a"]),
            ExecutionPacket(id="packet-a", target_files=["src/a.py"]),
        ],
        validators=[
            ExecutionValidator(
                id="focused",
                argv=["python", "-m", "pytest", "tests/test_a.py", "-q"],
                evidence=["exit-code"],
            )
        ],
    )


def _seed_gates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[str, str]:
    run_id = create_pipeline_run(tmp_path, {"repo": "test"})
    plan = _plan()
    plan_hash = execution_plan_hash(plan)
    save_execution_plan(tmp_path, run_id, plan)
    snapshot = SnapshotReceipt(
        snapshot_id="snap-1",
        run_id=run_id,
        plan_hash=plan_hash,
        base_commit="a" * 40,
        selected_paths=plan.target_files,
        file_hashes={path: "b" * 64 for path in plan.target_files},
        tree="c" * 40,
        commit="d" * 40,
        ref=f"refs/devflow/snapshots/{run_id}/snap-1",
        fingerprint="e" * 64,
    )
    snapshot_path = pipeline_runs_dir(tmp_path) / run_id / "snapshot-snap-1.json"
    snapshot_path.write_text(
        json.dumps(snapshot.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    def fake_run(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 0, stdout="ok", stderr="")

    monkeypatch.setattr("devflow.loop.validator_service.subprocess.run", fake_run)
    validator = plan.validators[0]
    run_validator(
        tmp_path,
        workspace,
        ValidatorRequest(
            receipt_id="validator-focused-1",
            run_id=run_id,
            snapshot_fingerprint=snapshot.fingerprint,
            execution_plan_hash=plan_hash,
            validator=validator,
        ),
    )
    return run_id, plan_hash


def test_authorization_is_deterministic_host_receipt_after_exact_gates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_id, plan_hash = _seed_gates(tmp_path, monkeypatch)

    first = authorize_execution(
        tmp_path,
        run_id,
        authorization_id="auth-1",
        snapshot_id="snap-1",
        validator_receipt_ids=["validator-focused-1"],
    )
    second = authorize_execution(
        tmp_path,
        run_id,
        authorization_id="auth-1",
        snapshot_id="snap-1",
        validator_receipt_ids=["validator-focused-1"],
    )

    assert first == second
    assert first.authorized is True
    assert first.execution_plan_hash == plan_hash
    assert first.packet_ids == ("packet-a", "packet-b")
    assert first.ready_packet_ids == ("packet-a",)
    assert first.validator_receipt_ids == ("validator-focused-1",)
    assert load_execution_authorization(tmp_path, run_id, "auth-1") == first


@pytest.mark.parametrize("failure", ["missing", "stale", "wrong-run", "nonpass", "corrupt-plan", "corrupt-receipt"])
def test_missing_stale_wrong_run_nonpassing_or_corrupt_evidence_blocks_authorization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    run_id, _ = _seed_gates(tmp_path, monkeypatch)
    run_dir = pipeline_runs_dir(tmp_path) / run_id
    receipt_ids = ["validator-focused-1"]
    snapshot_id = "snap-1"
    if failure == "missing":
        receipt_ids = ["missing"]
    elif failure == "stale":
        snapshot = json.loads((run_dir / "snapshot-snap-1.json").read_text())
        snapshot["plan_hash"] = "f" * 64
        (run_dir / "snapshot-snap-1.json").write_text(json.dumps(snapshot))
    elif failure == "wrong-run":
        snapshot = json.loads((run_dir / "snapshot-snap-1.json").read_text())
        snapshot["run_id"] = "other-run"
        (run_dir / "snapshot-snap-1.json").write_text(json.dumps(snapshot))
    elif failure == "nonpass":
        receipt = run_dir / "validator-receipts" / "validator-focused-1.json"
        data = json.loads(receipt.read_text())
        data.update({"outcome": "nonzero", "passed": False, "exit_code": 2})
        receipt.chmod(0o644)
        receipt.write_text(json.dumps(data))
    elif failure == "corrupt-plan":
        (run_dir / "execution-plan.json").write_text("{\n")
    else:
        receipt = run_dir / "validator-receipts" / "validator-focused-1.json"
        receipt.chmod(0o644)
        receipt.write_text("{}\n")

    with pytest.raises(ValueError):
        authorize_execution(
            tmp_path,
            run_id,
            authorization_id=f"auth-{failure}",
            snapshot_id=snapshot_id,
            validator_receipt_ids=receipt_ids,
        )
    assert not (run_dir / "execution-authorizations" / f"auth-{failure}.json").exists()


def test_full_phase_three_gate_chain_preserves_canonical_ledger_and_operator_state(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(
        ["git", "config", "user.email", "dev@example.com"], cwd=repo, check=True
    )
    subprocess.run(["git", "config", "user.name", "Dev"], cwd=repo, check=True)
    (repo / ".gitignore").write_text(".devflow/\n", encoding="utf-8")
    (repo / "a.py").write_text("value = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", ".gitignore", "a.py"], cwd=repo, check=True)
    subprocess.run(
        ["git", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "base"],
        cwd=repo,
        check=True,
    )
    base_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()
    run_id, _ = create_run_with_state(repo, {"repo": str(repo)})
    (repo / "a.py").write_text("value = 2\n", encoding="utf-8")
    plan = ExecutionPlan(
        target_files=["a.py"],
        packets=[ExecutionPacket(id="packet-a", target_files=["a.py"])],
        validators=[
            ExecutionValidator(
                id="syntax",
                argv=["python", "-m", "py_compile", "a.py"],
                evidence=["exit-code"],
            )
        ],
    )
    save_execution_plan(repo, run_id, plan)
    plan_hash = execution_plan_hash(plan)
    branch_before = base_commit
    index_before = subprocess.run(
        ["git", "write-tree"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()

    snapshot = create_source_snapshot(
        SnapshotRequest(
            repo=repo,
            root=repo,
            run_id=run_id,
            snapshot_id="snap-e2e",
            plan_hash=plan_hash,
            base_commit=base_commit,
            selected_paths=plan.target_files,
        )
    )
    validator_receipt = run_validator(
        repo,
        repo,
        ValidatorRequest(
            receipt_id="validator-syntax-e2e",
            run_id=run_id,
            snapshot_fingerprint=snapshot.fingerprint,
            execution_plan_hash=plan_hash,
            validator=plan.validators[0],
        ),
    )
    authorization = authorize_execution(
        repo,
        run_id,
        authorization_id="auth-e2e",
        snapshot_id=snapshot.snapshot_id,
        validator_receipt_ids=[validator_receipt.receipt_id],
    )

    assert authorization.authorized is True
    assert replay_workflow_run(repo, run_id).current_node_id == "idea"
    assert subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip() == branch_before
    assert subprocess.run(
        ["git", "write-tree"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip() == index_before
    assert (repo / "a.py").read_text(encoding="utf-8") == "value = 2\n"


def test_conflicting_authorization_replay_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_id, _ = _seed_gates(tmp_path, monkeypatch)
    authorize_execution(
        tmp_path,
        run_id,
        authorization_id="auth-1",
        snapshot_id="snap-1",
        validator_receipt_ids=["validator-focused-1"],
    )
    path = pipeline_runs_dir(tmp_path) / run_id / "execution-authorizations" / "auth-1.json"
    before = path.read_bytes()

    with pytest.raises(ValueError, match="conflicting execution authorization"):
        authorize_execution(
            tmp_path,
            run_id,
            authorization_id="auth-1",
            snapshot_id="snap-1",
            validator_receipt_ids=[],
        )
    assert path.read_bytes() == before
