"""Phase 5 packet-patch and clean-integration behavior."""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from devflow.loop.adapter import create_run_with_state
from devflow.loop.execution_authorization import authorize_execution
from devflow.loop.execution_plan import (
    ExecutionPacket,
    ExecutionPlan,
    ExecutionValidator,
    execution_plan_hash,
    save_execution_plan,
)
from devflow.loop.git_sandbox import load_sandbox_receipt
from devflow.loop.pipeline_run import pipeline_runs_dir, update_pipeline_run_record
from devflow.loop.run_advancement import (
    AdvanceAction,
    AdvanceCommand,
    advance_run,
    load_advancement_snapshot,
    save_advancement_command,
)
from devflow.loop.run_integration import (
    IntegrationCommand,
    IntegrationError,
    IntegrationRepairCommand,
    IntegrationStatus,
    IntegrationVerificationRequest,
    PatchCaptureCommand,
    capture_packet_patch,
    integrate_run,
    load_integration_snapshot,
    load_packet_patch_receipt,
    record_integration_repair,
    record_integration_verification,
    save_integration_command,
    save_integration_repair_command,
    save_patch_capture_command,
)
from devflow.loop.run_supervisor import (
    pending_integration_command_ids,
    run_integration_supervisor_cycle,
)
from devflow.loop.source_snapshot import SnapshotRequest, create_source_snapshot
from devflow.loop.validator_service import ValidatorRequest, run_validator
from devflow.loop.workflow_ledger import (
    EvidenceReference,
    NodeReceipt,
    WorkflowEvent,
    record_node_outcome,
)

UTC = timezone.utc


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "dev@example.com")
    _git(repo, "config", "user.name", "Dev")
    _git(repo, "config", "commit.gpgsign", "false")
    (repo / ".gitignore").write_text(".devflow/\nignored.bin\n", encoding="utf-8")
    (repo / "a.py").write_text("value = 1\n", encoding="utf-8")
    (repo / "b.py").write_text("value = 2\n", encoding="utf-8")
    _git(repo, "add", ".gitignore", "a.py", "b.py")
    _git(repo, "commit", "-q", "-m", "base")
    return repo


def _seed(repo: Path) -> tuple[str, ExecutionPlan]:
    run_id, _ = create_run_with_state(repo, {"repo": str(repo)})
    plan = ExecutionPlan(
        target_files=["a.py", "b.py"],
        packets=[
            ExecutionPacket(id="packet-a", target_files=["a.py"]),
            ExecutionPacket(
                id="packet-b", target_files=["b.py"], depends_on=["packet-a"]
            ),
        ],
        validators=[
            ExecutionValidator(
                id="syntax",
                argv=["python", "-m", "py_compile", "a.py", "b.py"],
                evidence=["exit-code"],
            )
        ],
    )
    save_execution_plan(repo, run_id, plan)
    plan_hash = execution_plan_hash(plan)
    snapshot = create_source_snapshot(
        SnapshotRequest(
            repo=repo,
            root=repo,
            run_id=run_id,
            snapshot_id="snap-1",
            plan_hash=plan_hash,
            base_commit=_git(repo, "rev-parse", "HEAD"),
            selected_paths=plan.target_files,
        )
    )
    validator = run_validator(
        repo,
        repo,
        ValidatorRequest(
            receipt_id="prepare-syntax",
            run_id=run_id,
            snapshot_fingerprint=snapshot.fingerprint,
            execution_plan_hash=plan_hash,
            validator=plan.validators[0],
        ),
    )
    authorize_execution(
        repo,
        run_id,
        authorization_id="auth-1",
        snapshot_id=snapshot.snapshot_id,
        validator_receipt_ids=[validator.receipt_id],
    )
    return run_id, plan


def _run_dir(repo: Path, run_id: str) -> Path:
    return pipeline_runs_dir(repo) / run_id


def _build_packet(
    repo: Path,
    run_id: str,
    packet_id: str,
    *,
    value: int,
    owner: str,
    family: str = "builder-family",
):
    dispatch_id = f"dispatch-{packet_id}"
    dispatch = AdvanceCommand(
        command_id=dispatch_id,
        run_id=run_id,
        action=AdvanceAction.dispatch,
        owner_id=owner,
        packet_id=packet_id,
    )
    save_advancement_command(repo, run_id, dispatch)
    started = advance_run(repo, repo, run_id, dispatch_id)
    sandbox_id = next(
        attempt.sandbox_id
        for attempt in load_advancement_snapshot(repo, run_id).attempts
        if attempt.attempt_id == started.attempt_id
    )
    sandbox = load_sandbox_receipt(repo, run_id, sandbox_id)
    target = "a.py" if packet_id == "packet-a" else "b.py"
    Path(sandbox.path, target).write_text(f"value = {value}\n", encoding="utf-8")
    evidence = f"evidence-{packet_id}.txt"
    (_run_dir(repo, run_id) / evidence).write_text("passed\n", encoding="utf-8")
    complete_id = f"complete-{packet_id}"
    complete = AdvanceCommand(
        command_id=complete_id,
        run_id=run_id,
        action=AdvanceAction.complete,
        owner_id=owner,
        packet_id=packet_id,
        claim_id=started.claim_id,
        attempt_id=started.attempt_id,
        evidence_reference=evidence,
    )
    save_advancement_command(repo, run_id, complete)
    assert advance_run(repo, repo, run_id, complete_id).status == "ok"
    capture = PatchCaptureCommand(
        command_id=f"capture-{packet_id}",
        run_id=run_id,
        packet_id=packet_id,
        claim_id=started.claim_id,
        attempt_id=started.attempt_id,
        owner_id=owner,
        route=owner,
        provider="local",
        model="builder-model",
        model_family=family,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    save_patch_capture_command(repo, capture)
    return capture_packet_patch(repo, repo, run_id, capture.command_id)


def _build_all(repo: Path, run_id: str):
    first = _build_packet(repo, run_id, "packet-a", value=10, owner="owner-a")
    second = _build_packet(repo, run_id, "packet-b", value=20, owner="owner-b")
    return first, second


def test_capture_is_binary_safe_immutable_and_idempotent(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    run_id, _ = _seed(repo)
    receipt = _build_packet(repo, run_id, "packet-a", value=10, owner="owner-a")
    again = capture_packet_patch(repo, repo, run_id, "capture-packet-a")
    assert again == receipt
    patch = (_run_dir(repo, run_id) / receipt.patch_path).read_bytes()
    assert hashlib.sha256(patch).hexdigest() == receipt.patch_sha256
    assert receipt.changed_paths == ("a.py",)
    assert receipt.base_tree != receipt.result_tree
    assert load_packet_patch_receipt(repo, run_id, "packet-a") == receipt


def test_complete_opt_in_captures_patch_and_recovers_missing_outcome(
    tmp_path: Path,
) -> None:
    repo = _init_repo(tmp_path)
    run_id, _ = _seed(repo)
    dispatch = AdvanceCommand(
        command_id="dispatch-auto",
        run_id=run_id,
        action=AdvanceAction.dispatch,
        owner_id="owner-a",
        packet_id="packet-a",
    )
    save_advancement_command(repo, run_id, dispatch)
    started = advance_run(repo, repo, run_id, dispatch.command_id)
    sandbox = load_sandbox_receipt(repo, run_id, "packet-a-attempt-1")
    Path(sandbox.path, "a.py").write_text("value = 11\n", encoding="utf-8")
    evidence = "auto-complete.txt"
    (_run_dir(repo, run_id) / evidence).write_text("pass\n", encoding="utf-8")
    complete = AdvanceCommand(
        command_id="complete-auto",
        run_id=run_id,
        action=AdvanceAction.complete,
        owner_id="owner-a",
        packet_id="packet-a",
        claim_id=started.claim_id,
        evidence_reference=evidence,
        patch_provider="local",
        patch_model="builder-model",
        patch_model_family="builder-family",
    )
    save_advancement_command(repo, run_id, complete)
    first = advance_run(repo, repo, run_id, complete.command_id)
    assert first.packet_patch_receipt_id == "patch-packet-a"
    outcome_path = _run_dir(repo, run_id) / "advancement-outcomes" / "complete-auto.json"
    outcome_path.unlink()
    recovered = advance_run(repo, repo, run_id, complete.command_id)
    assert recovered == first
    assert load_packet_patch_receipt(repo, run_id, "packet-a").receipt_id == first.packet_patch_receipt_id


def test_capture_rejects_out_of_plan_and_preserves_no_receipt(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    run_id, _ = _seed(repo)
    dispatch = AdvanceCommand(
        command_id="dispatch-packet-a",
        run_id=run_id,
        action=AdvanceAction.dispatch,
        owner_id="owner-a",
        packet_id="packet-a",
    )
    save_advancement_command(repo, run_id, dispatch)
    started = advance_run(repo, repo, run_id, dispatch.command_id)
    sandbox = load_sandbox_receipt(repo, run_id, "packet-a-attempt-1")
    Path(sandbox.path, "a.py").write_text("value = 10\n", encoding="utf-8")
    Path(sandbox.path, "outside.txt").write_text("no\n", encoding="utf-8")
    evidence = "packet-a.txt"
    (_run_dir(repo, run_id) / evidence).write_text("pass\n", encoding="utf-8")
    complete = AdvanceCommand(
        command_id="complete-packet-a",
        run_id=run_id,
        action=AdvanceAction.complete,
        owner_id="owner-a",
        packet_id="packet-a",
        claim_id=started.claim_id,
        evidence_reference=evidence,
    )
    save_advancement_command(repo, run_id, complete)
    advance_run(repo, repo, run_id, complete.command_id)
    capture = PatchCaptureCommand(
        command_id="capture-packet-a",
        run_id=run_id,
        packet_id="packet-a",
        claim_id=started.claim_id,
        attempt_id=started.attempt_id,
        owner_id="owner-a",
        route="owner-a",
        provider="local",
        model="builder-model",
        model_family="builder-family",
    )
    save_patch_capture_command(repo, capture)
    with pytest.raises(IntegrationError, match="outside approved targets"):
        capture_packet_patch(repo, repo, run_id, capture.command_id)
    assert not (_run_dir(repo, run_id) / "packet-patch-receipts" / "packet-a.json").exists()


def test_dependency_ordered_clean_integration_and_replay(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    run_id, _ = _seed(repo)
    first, second = _build_all(repo, run_id)
    operator_before = (repo / "a.py").read_bytes(), (repo / "b.py").read_bytes()
    command = IntegrationCommand(
        command_id="integrate-1",
        run_id=run_id,
        integration_id="result-1",
        authorization_id="auth-1",
        created_at=datetime(2026, 1, 2, tzinfo=UTC),
    )
    save_integration_command(repo, command)
    outcome = integrate_run(repo, repo, run_id, command.command_id)
    assert outcome.status is IntegrationStatus.awaiting_verification
    assert outcome.applied_packet_ids == ("packet-a", "packet-b")
    assert integrate_run(repo, repo, run_id, command.command_id) == outcome
    state = load_integration_snapshot(repo, run_id)
    assert state.applied_packet_ids == ("packet-a", "packet-b")
    assert state.patch_hashes == (first.patch_sha256, second.patch_sha256)
    worktree = Path(load_sandbox_receipt(repo, run_id, state.sandbox_id).path)
    assert (worktree / "a.py").read_text() == "value = 10\n"
    assert (worktree / "b.py").read_text() == "value = 20\n"
    assert _git(worktree, "status", "--porcelain") == ""
    assert ((repo / "a.py").read_bytes(), (repo / "b.py").read_bytes()) == operator_before


def test_patch_hash_tamper_fails_before_integration(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    run_id, _ = _seed(repo)
    first, _ = _build_all(repo, run_id)
    patch_path = _run_dir(repo, run_id) / first.patch_path
    patch_path.chmod(0o644)
    patch_path.write_bytes(patch_path.read_bytes() + b"tamper")
    command = IntegrationCommand(
        command_id="integrate-1",
        run_id=run_id,
        integration_id="result-1",
        authorization_id="auth-1",
    )
    save_integration_command(repo, command)
    with pytest.raises(IntegrationError, match="hash revalidation"):
        integrate_run(repo, repo, run_id, command.command_id)
    assert not (_run_dir(repo, run_id) / "integration-events.jsonl").exists()


def test_conflict_receipt_and_bounded_repair_resume_without_rewriting_patch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _init_repo(tmp_path)
    run_id, _ = _seed(repo)
    _, second = _build_all(repo, run_id)
    command = IntegrationCommand(
        command_id="integrate-conflict",
        run_id=run_id,
        integration_id="result-1",
        authorization_id="auth-1",
        created_at=datetime(2026, 1, 2, tzinfo=UTC),
    )
    save_integration_command(repo, command)
    import devflow.loop.run_integration as integration_module

    real_git = integration_module._git

    def conflict_second(worktree, *args, **kwargs):
        if (
            args[:2] == ("apply", "--check")
            and str(args[-1]).endswith(f"{second.patch_sha256}.patch")
        ):
            return subprocess.CompletedProcess(
                ["git", *args], 1, stdout=b"", stderr=b"patch failed: b.py\n"
            )
        return real_git(worktree, *args, **kwargs)

    monkeypatch.setattr(integration_module, "_git", conflict_second)
    outcome = integrate_run(repo, repo, run_id, command.command_id)
    assert outcome.status is IntegrationStatus.conflict
    state = load_integration_snapshot(repo, run_id)
    assert state.applied_packet_ids == ("packet-a",)
    assert state.conflict_id is not None
    worktree = Path(load_sandbox_receipt(repo, run_id, state.sandbox_id).path)
    (worktree / "b.py").write_text("value = 20\n", encoding="utf-8")
    evidence = "repair-evidence.txt"
    (_run_dir(repo, run_id) / evidence).write_text("resolved\n", encoding="utf-8")
    repair = IntegrationRepairCommand(
        command_id="repair-1",
        run_id=run_id,
        integration_id="result-1",
        conflict_id=state.conflict_id,
        owner_id="repair-owner",
        route="repair-route",
        provider="local",
        model="repair-model",
        model_family="repair-family",
        evidence_reference=evidence,
        created_at=datetime(2026, 1, 3, tzinfo=UTC),
    )
    save_integration_repair_command(repo, repair)
    receipt = record_integration_repair(repo, repo, run_id, repair.command_id)
    assert receipt.packet_id == "packet-b"
    assert receipt.attempt_number == 1
    state = load_integration_snapshot(repo, run_id)
    assert state.applied_packet_ids == ("packet-a", "packet-b")
    monkeypatch.setattr(integration_module, "_git", real_git)
    resume = IntegrationCommand(
        command_id="integrate-resume",
        run_id=run_id,
        integration_id="result-1",
        authorization_id="auth-1",
        created_at=datetime(2026, 1, 4, tzinfo=UTC),
    )
    save_integration_command(repo, resume)
    resumed = integrate_run(repo, repo, run_id, resume.command_id)
    assert resumed.status is IntegrationStatus.awaiting_verification
    assert load_packet_patch_receipt(repo, run_id, "packet-b") == second


def test_repeat_only_integration_supervisor_discovers_existing_command(
    tmp_path: Path,
) -> None:
    repo = _init_repo(tmp_path)
    run_id, _ = _seed(repo)
    _build_all(repo, run_id)
    command = IntegrationCommand(
        command_id="integrate-supervised",
        run_id=run_id,
        integration_id="result-1",
        authorization_id="auth-1",
    )
    save_integration_command(repo, command)
    assert pending_integration_command_ids(repo, run_id) == [command.command_id]
    cycle = run_integration_supervisor_cycle(repo, repo, run_id)
    assert cycle.advanced_command_ids == (command.command_id,)
    assert (
        cycle.outcomes[command.command_id].status
        is IntegrationStatus.awaiting_verification
    )
    assert pending_integration_command_ids(repo, run_id) == []
    assert (
        run_integration_supervisor_cycle(repo, repo, run_id).advanced_command_ids
        == ()
    )


def test_independence_gate_rejects_builder_family_and_accepts_distinct_fail_verdict(
    tmp_path: Path,
) -> None:
    repo = _init_repo(tmp_path)
    run_id, _ = _seed(repo)
    _build_all(repo, run_id)
    command = IntegrationCommand(
        command_id="integrate-1",
        run_id=run_id,
        integration_id="result-1",
        authorization_id="auth-1",
    )
    save_integration_command(repo, command)
    integrate_run(repo, repo, run_id, command.command_id)
    dod = hashlib.sha256(b"definition of done").hexdigest()
    same = IntegrationVerificationRequest(
        receipt_id="verify-same",
        run_id=run_id,
        integration_id="result-1",
        provider="local",
        model="builder-model",
        model_family="builder-family",
        route="same-family",
        verdict="fail",
        definition_of_done_sha256=dod,
    )
    with pytest.raises(IntegrationError, match="not independent"):
        record_integration_verification(repo, repo, same)
    distinct = same.model_copy(
        update={
            "receipt_id": "verify-distinct",
            "model": "judge-model",
            "model_family": "judge-family",
            "route": "independent-judge",
            "findings": ("one finding",),
        }
    )
    receipt = record_integration_verification(repo, repo, distinct)
    assert receipt.verdict == "fail"
    assert receipt.independent_from_model_families == ("builder-family",)
    state = load_integration_snapshot(repo, run_id)
    assert state.sandbox_id is not None
    worktree = Path(load_sandbox_receipt(repo, run_id, state.sandbox_id).path)
    (worktree / "a.py").write_text("value = 999\n", encoding="utf-8")
    with pytest.raises(IntegrationError, match="stale"):
        record_integration_verification(repo, repo, distinct)


def test_passing_independent_verification_advances_only_verification_node(
    tmp_path: Path,
) -> None:
    repo = _init_repo(tmp_path)
    run_id, _ = _seed(repo)
    _build_all(repo, run_id)
    steps = (
        ("idea", "idea-brief"),
        ("definition", "orientation-receipt"),
        ("spec", "spec"),
        ("planning", "execution-plan"),
        ("planning_judge", "planning-judge-report"),
        ("assignment", "approved-execution-plan"),
        ("build_judge", "build-judge-report"),
    )
    for index, (node, key) in enumerate(steps):
        evidence = f"workflow-{index}.txt"
        (_run_dir(repo, run_id) / evidence).write_text("ok\n", encoding="utf-8")
        record_node_outcome(
            repo,
            run_id,
            receipt=NodeReceipt(
                receipt_id=f"wf-r-{index}",
                node_id=node,
                outcome="success",
                evidence=(EvidenceReference(key=key, reference=evidence),),
            ),
            event=WorkflowEvent(
                event_id=f"wf-e-{index}",
                node_id=node,
                outcome="success",
                receipt_id=f"wf-r-{index}",
            ),
        )
    command = IntegrationCommand(
        command_id="integrate-1",
        run_id=run_id,
        integration_id="result-1",
        authorization_id="auth-1",
    )
    save_integration_command(repo, command)
    integrate_run(repo, repo, run_id, command.command_id)
    request = IntegrationVerificationRequest(
        receipt_id="verify-pass",
        run_id=run_id,
        integration_id="result-1",
        provider="local",
        model="judge-model",
        model_family="judge-family",
        route="independent-judge",
        verdict="pass",
        definition_of_done_sha256=hashlib.sha256(b"dod").hexdigest(),
    )
    receipt = record_integration_verification(repo, repo, request)
    assert receipt.verdict == "pass"
    from devflow.loop.workflow_ledger import replay_workflow_run

    assert replay_workflow_run(repo, run_id).current_node_id == "human_decision"


def test_generic_persistence_cannot_overwrite_phase5_records(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    run_id, _ = _seed(repo)
    for name in (
        "packet-patch-commands.json",
        "packet-patches.json",
        "integration-events.jsonl",
        "integration-outcomes.json",
    ):
        with pytest.raises(ValueError, match="integration"):
            update_pipeline_run_record(repo, run_id, name, {})


def test_corrupt_or_reordered_integration_ledger_fails_closed(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    run_id, _ = _seed(repo)
    path = _run_dir(repo, run_id) / "integration-events.jsonl"
    path.write_text(
        json.dumps(
            {
                "event_id": "int-000001",
                "sequence": 1,
                "kind": "integration.started",
                "command_id": "x",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(IntegrationError, match="sequence"):
        load_integration_snapshot(repo, run_id)
