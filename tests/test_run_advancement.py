"""Focused behavioral tests for deterministic Phase 4 packet advancement.

These exercise the real dispatch/heartbeat/complete/fail/cancel/release/
recovery/retry lifecycle against a fully seeded Phase 3 run, asserting the
append-only ledger, the one-active invariant, owner-only transitions, the
complete deterministic ready set, and immutable command/outcome replay.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
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
from devflow.loop.packet_dag import PacketState
from devflow.loop.run_advancement import (
    AdvanceAction,
    AdvanceCommand,

    AdvancementSnapshot,
    ClaimState,
    advance_run,
    load_advancement_snapshot,
    save_advancement_command,
)
from devflow.loop.source_snapshot import SnapshotRequest, create_source_snapshot
from devflow.loop.validator_service import ValidatorRequest, run_validator
from devflow.loop.workflow_ledger import (
    EvidenceReference,
    NodeReceipt,
    WorkflowEvent,
    record_node_outcome,
    replay_workflow_run,
)

UTC = timezone.utc


def _git(repo: Path, *args: str) -> str:
    import subprocess

    return subprocess.run(
        ["git", *args],
        cwd=str(repo),
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "dev@example.com")
    _git(repo, "config", "user.name", "Dev")
    _git(repo, "config", "commit.gpgsign", "false")
    (repo / ".gitignore").write_text(".devflow/\n", encoding="utf-8")
    (repo / "a.py").write_text("value = 1\n", encoding="utf-8")
    (repo / "b.py").write_text("value = 2\n", encoding="utf-8")
    (repo / "c.py").write_text("value = 3\n", encoding="utf-8")
    _git(repo, "add", ".gitignore", "a.py", "b.py", "c.py")
    _git(repo, "commit", "-q", "-m", "base")
    return repo


def _seed_run(tmp_path: Path, repo: Path) -> tuple[str, ExecutionPlan]:
    run_id, _ = create_run_with_state(repo, {"repo": str(repo)})
    plan = ExecutionPlan(
        target_files=["a.py", "b.py", "c.py"],
        packets=[
            ExecutionPacket(id="packet-a", target_files=["a.py"]),
            ExecutionPacket(id="packet-b", target_files=["b.py"], depends_on=["packet-a"]),
            ExecutionPacket(id="packet-c", target_files=["c.py"], depends_on=["packet-a"]),
        ],
        validators=[
            ExecutionValidator(
                id="syntax",
                argv=["python", "-m", "py_compile", "a.py", "b.py", "c.py"],
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
    validator_receipt = run_validator(
        repo,
        repo,
        ValidatorRequest(
            receipt_id="validator-syntax-1",
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
        validator_receipt_ids=[validator_receipt.receipt_id],
    )
    return run_id, plan


def _dispatch_cmd(run_id: str, packet: str, owner: str, *, command_id: str, lease: int = 300) -> AdvanceCommand:
    return AdvanceCommand(
        command_id=command_id,
        run_id=run_id,
        action=AdvanceAction.dispatch,
        owner_id=owner,
        packet_id=packet,
        lease_seconds=lease,
    )


def _write_evidence(root: Path, run_id: str, name: str) -> None:
    path = Path(root).resolve() / ".devflow" / "pipeline-runs" / run_id / name
    path.write_text("evidence\n", encoding="utf-8")


def _drive_workflow_to_build_judge(root: Path, run_id: str) -> None:
    steps = (
        ("idea", "idea-brief"),
        ("definition", "orientation-receipt"),
        ("spec", "spec"),
        ("planning", "execution-plan"),
        ("planning_judge", "planning-judge-report"),
        ("assignment", "approved-execution-plan"),
    )
    for index, (node_id, evidence_key) in enumerate(steps, start=1):
        evidence_name = f"workflow-{index}-{node_id}.txt"
        _write_evidence(root, run_id, evidence_name)
        receipt_id = f"workflow-receipt-{index}"
        record_node_outcome(
            root,
            run_id,
            receipt=NodeReceipt(
                receipt_id=receipt_id,
                node_id=node_id,
                outcome="success",
                evidence=(
                    EvidenceReference(key=evidence_key, reference=evidence_name),
                ),
            ),
            event=WorkflowEvent(
                event_id=f"workflow-event-{index}",
                node_id=node_id,
                outcome="success",
                receipt_id=receipt_id,
            ),
        )


# ---------------------------------------------------------------------------
# Command persistence / idempotency / conflict
# ---------------------------------------------------------------------------
def test_save_command_idempotent_and_conflicting_fails(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    run_id, _ = _seed_run(tmp_path, repo)
    cmd = _dispatch_cmd(run_id, "packet-a", "owner-1", command_id="cmd-1")
    first = save_advancement_command(repo, run_id, cmd)
    second = save_advancement_command(repo, run_id, cmd)
    assert first == second

    conflicting = cmd.model_copy(update={"owner_id": "owner-2"})
    with pytest.raises(ValueError, match="conflicting"):
        save_advancement_command(repo, run_id, conflicting)


# ---------------------------------------------------------------------------
# Dispatch: idempotency / conflicting command / records-before-start
# ---------------------------------------------------------------------------
def test_dispatch_idempotent_same_outcome(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    run_id, _ = _seed_run(tmp_path, repo)
    cmd = _dispatch_cmd(run_id, "packet-a", "owner-1", command_id="cmd-d1")
    save_advancement_command(repo, run_id, cmd)

    first = advance_run(repo, repo, run_id, "cmd-d1")
    second = advance_run(repo, repo, run_id, "cmd-d1")
    assert first == second
    assert first.status == "ok"
    assert first.claim_id == "claim-packet-a-1"
    assert first.attempt_id == "attempt-packet-a-1"

    snap = load_advancement_snapshot(repo, run_id)
    assert snap.active_claim_id == "claim-packet-a-1"
    assert snap.packet_state["packet-a"] is PacketState.pending


def test_dispatch_conflicting_command_fails_closed(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    run_id, _ = _seed_run(tmp_path, repo)
    c1 = _dispatch_cmd(run_id, "packet-a", "owner-1", command_id="cmd-c1")
    c2 = _dispatch_cmd(run_id, "packet-a", "owner-2", command_id="cmd-c1")
    save_advancement_command(repo, run_id, c1)
    with pytest.raises(ValueError, match="conflicting"):
        save_advancement_command(repo, run_id, c2)
    first = advance_run(repo, repo, run_id, "cmd-c1")
    assert first.status == "ok"
    # The deterministic sandbox receipt exists under its sandbox_id.
    from devflow.loop.git_sandbox import load_sandbox_receipt

    assert load_sandbox_receipt(repo, run_id, "packet-a-attempt-1").packet_id == "packet-a"


def test_dispatch_creates_records_before_started_outcome(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    run_id, _ = _seed_run(tmp_path, repo)
    cmd = _dispatch_cmd(run_id, "packet-a", "owner-1", command_id="cmd-s1")
    save_advancement_command(repo, run_id, cmd)
    outcome = advance_run(repo, repo, run_id, "cmd-s1")
    assert outcome.status == "ok"
    assert load_sandbox_receipt(repo, run_id, "packet-a-attempt-1").packet_id == "packet-a"
    snap = load_advancement_snapshot(repo, run_id)
    claim = next(c for c in snap.claims if c.claim_id == outcome.claim_id)
    attempt = next(a for a in snap.attempts if a.attempt_id == outcome.attempt_id)
    assert claim.state is ClaimState.active
    assert attempt.sandbox_id == "packet-a-attempt-1"
    assert attempt.sandbox_id == f"{attempt.packet_id}-attempt-{attempt.attempt_number}"

    import json

    events_path = repo / ".devflow" / "pipeline-runs" / run_id / "advancement-events.jsonl"
    events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines()]
    assert len(events) == 1
    assert events[0]["kind"] == "dispatch.start"
    assert events[0]["claim"]["attempt_id"] == events[0]["attempt"]["attempt_id"]


# ---------------------------------------------------------------------------
# Wrong auth / wrong snapshot / ref
# ---------------------------------------------------------------------------
def test_dispatch_wrong_snapshot_ref_fails_closed(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    run_id, _ = _seed_run(tmp_path, repo)
    # Committing/moving HEAD does not mutate the frozen snapshot ref. To force a
    # ref mismatch we must move the snapshot's own run-scoped ref off its commit.
    from devflow.loop.execution_authorization import load_execution_authorization
    from devflow.loop.source_snapshot import load_source_snapshot_receipt

    auth = load_execution_authorization(repo, run_id, "auth-1")
    snapshot = load_source_snapshot_receipt(repo, run_id, auth.snapshot_id)
    (repo / "d.py").write_text("value = 4\n", encoding="utf-8")
    _git(repo, "add", "d.py")
    _git(repo, "commit", "-q", "-m", "move head")
    _git(repo, "update-ref", snapshot.ref, "HEAD")
    cmd = _dispatch_cmd(run_id, "packet-a", "owner-1", command_id="cmd-r1")
    save_advancement_command(repo, run_id, cmd)
    with pytest.raises(ValueError, match="resolves to|snapshot ref"):
        advance_run(repo, repo, run_id, "cmd-r1")


# ---------------------------------------------------------------------------
# One active while complete ready set persisted
# ---------------------------------------------------------------------------
def test_one_active_while_ready_set_persisted(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    run_id, _ = _seed_run(tmp_path, repo)
    cmd = _dispatch_cmd(run_id, "packet-a", "owner-1", command_id="cmd-o1")
    save_advancement_command(repo, run_id, cmd)
    outcome = advance_run(repo, repo, run_id, "cmd-o1")
    assert outcome.status == "ok"
    snap = load_advancement_snapshot(repo, run_id)
    assert snap.active_claim_id == "claim-packet-a-1"
    assert "packet-a" in snap.ready_packet_ids

    cmd_b = _dispatch_cmd(run_id, "packet-b", "owner-2", command_id="cmd-o2")
    save_advancement_command(repo, run_id, cmd_b)
    outcome_b = advance_run(repo, repo, run_id, "cmd-o2")
    assert outcome_b.status == "rejected"
    assert "already active" in outcome_b.message

    _write_evidence(repo, run_id, "ev-a.json")
    cmd_c = AdvanceCommand(
        command_id="cmd-o3",
        run_id=run_id,
        action=AdvanceAction.complete,
        owner_id="owner-1",
        packet_id="packet-a",
        claim_id="claim-packet-a-1",
        evidence_reference="ev-a.json",
    )
    save_advancement_command(repo, run_id, cmd_c)
    oc = advance_run(repo, repo, run_id, "cmd-o3")
    assert oc.status == "ok"
    snap2 = load_advancement_snapshot(repo, run_id)
    assert snap2.packet_state["packet-a"] is PacketState.succeeded
    assert set(snap2.ready_packet_ids) == {"packet-b", "packet-c"}
    assert snap2.active_claim_id is None


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------
def test_dependency_not_ready_rejected(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    run_id, _ = _seed_run(tmp_path, repo)
    cmd = _dispatch_cmd(run_id, "packet-b", "owner-1", command_id="cmd-d1")
    save_advancement_command(repo, run_id, cmd)
    outcome = advance_run(repo, repo, run_id, "cmd-d1")
    assert outcome.status == "rejected"
    assert "not ready" in outcome.message


# ---------------------------------------------------------------------------
# Owner-only transitions
# ---------------------------------------------------------------------------
def test_owner_only_transitions(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    run_id, _ = _seed_run(tmp_path, repo)
    cmd = _dispatch_cmd(run_id, "packet-a", "owner-1", command_id="cmd-own1")
    save_advancement_command(repo, run_id, cmd)
    advance_run(repo, repo, run_id, "cmd-own1")

    _write_evidence(repo, run_id, "ev-hb.json")
    cmd_hb = AdvanceCommand(
        command_id="cmd-own2",
        run_id=run_id,
        action=AdvanceAction.heartbeat,
        owner_id="owner-9",
        packet_id="packet-a",
        claim_id="claim-packet-a-1",
    )
    save_advancement_command(repo, run_id, cmd_hb)
    out = advance_run(repo, repo, run_id, "cmd-own2")
    assert out.status == "rejected"
    assert "wrong owner" in out.message

    cmd_hb2 = cmd_hb.model_copy(update={"owner_id": "owner-1", "command_id": "cmd-own3"})
    save_advancement_command(repo, run_id, cmd_hb2)
    out2 = advance_run(repo, repo, run_id, "cmd-own3")
    assert out2.status == "ok"


def test_heartbeat_extends_lease_and_blocks_recovery(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    run_id, _ = _seed_run(tmp_path, repo)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    cmd = _dispatch_cmd(run_id, "packet-a", "owner-1", command_id="cmd-hb1", lease=300)
    save_advancement_command(repo, run_id, cmd)
    advance_run(repo, repo, run_id, "cmd-hb1", now=now)

    _write_evidence(repo, run_id, "ev-hb.json")
    cmd_hb = AdvanceCommand(
        command_id="cmd-hb2",
        run_id=run_id,
        action=AdvanceAction.heartbeat,
        owner_id="owner-1",
        packet_id="packet-a",
        claim_id="claim-packet-a-1",
    )
    save_advancement_command(repo, run_id, cmd_hb)
    advance_run(repo, repo, run_id, "cmd-hb2", now=now + timedelta(seconds=200))

    _write_evidence(repo, run_id, "ev-rec.json")
    cmd_rec = AdvanceCommand(
        command_id="cmd-hb3",
        run_id=run_id,
        action=AdvanceAction.recover,
        owner_id="owner-1",
        packet_id="packet-a",
        claim_id="claim-packet-a-1",
        evidence_reference="ev-rec.json",
    )
    save_advancement_command(repo, run_id, cmd_rec)
    out_rec = advance_run(repo, repo, run_id, "cmd-hb3", now=now + timedelta(seconds=350))
    assert out_rec.status == "rejected"
    assert "lease not yet expired" in out_rec.message


# ---------------------------------------------------------------------------
# Cancellation: durable/idempotent, never completable
# ---------------------------------------------------------------------------
def test_cancellation_durable_and_never_completable(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    run_id, _ = _seed_run(tmp_path, repo)
    cmd = _dispatch_cmd(run_id, "packet-a", "owner-1", command_id="cmd-cn1")
    save_advancement_command(repo, run_id, cmd)
    advance_run(repo, repo, run_id, "cmd-cn1")

    _write_evidence(repo, run_id, "ev-cancel.json")
    cmd_cancel = AdvanceCommand(
        command_id="cmd-cn2",
        run_id=run_id,
        action=AdvanceAction.cancel,
        owner_id="owner-1",
        packet_id="packet-a",
        claim_id="claim-packet-a-1",
        evidence_reference="ev-cancel.json",
    )
    save_advancement_command(repo, run_id, cmd_cancel)
    out_cancel = advance_run(repo, repo, run_id, "cmd-cn2")
    assert out_cancel.status == "ok"

    out_cancel2 = advance_run(repo, repo, run_id, "cmd-cn2")
    assert out_cancel2 == out_cancel

    _write_evidence(repo, run_id, "ev-done.json")
    cmd_done = AdvanceCommand(
        command_id="cmd-cn3",
        run_id=run_id,
        action=AdvanceAction.complete,
        owner_id="owner-1",
        packet_id="packet-a",
        claim_id="claim-packet-a-1",
        evidence_reference="ev-done.json",
    )
    save_advancement_command(repo, run_id, cmd_done)
    out_done = advance_run(repo, repo, run_id, "cmd-cn3")
    assert out_done.status == "rejected"
    assert "not active" in out_done.message
    snap = load_advancement_snapshot(repo, run_id)
    assert snap.packet_state["packet-a"] is PacketState.pending
    takeover = _dispatch_cmd(
        run_id,
        "packet-a",
        "owner-9",
        command_id="cmd-cn4",
    )
    save_advancement_command(repo, run_id, takeover)
    takeover_outcome = advance_run(repo, repo, run_id, "cmd-cn4")
    assert takeover_outcome.status == "rejected"
    assert "only owner-specific retry" in takeover_outcome.message


# ---------------------------------------------------------------------------
# Recovery after lease expiry, with receipt before release
# ---------------------------------------------------------------------------
def test_recovery_after_lease_expiry_creates_receipt(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    run_id, _ = _seed_run(tmp_path, repo)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    cmd = _dispatch_cmd(run_id, "packet-a", "owner-1", command_id="cmd-rc1", lease=300)
    save_advancement_command(repo, run_id, cmd)
    advance_run(repo, repo, run_id, "cmd-rc1", now=now)

    _write_evidence(repo, run_id, "ev-rec1.json")
    cmd_rec = AdvanceCommand(
        command_id="cmd-rc2",
        run_id=run_id,
        action=AdvanceAction.recover,
        owner_id="owner-1",
        packet_id="packet-a",
        claim_id="claim-packet-a-1",
        evidence_reference="ev-rec1.json",
    )
    save_advancement_command(repo, run_id, cmd_rec)
    out_early = advance_run(repo, repo, run_id, "cmd-rc2", now=now + timedelta(seconds=100))
    assert out_early.status == "rejected"

    cmd_rec3 = cmd_rec.model_copy(update={"command_id": "cmd-rc3"})
    save_advancement_command(repo, run_id, cmd_rec3)
    out = advance_run(repo, repo, run_id, "cmd-rc3", now=now + timedelta(seconds=400))
    assert out.status == "ok"
    assert out.recovery_id is not None
    assert (
        Path(repo) / ".devflow" / "pipeline-runs" / run_id / "advancement-recoveries" / f"{out.recovery_id}.json"
    ).is_file()
    snap = load_advancement_snapshot(repo, run_id)
    claim = next(c for c in snap.claims if c.claim_id == "claim-packet-a-1")
    assert claim.state is ClaimState.recovered
    takeover = _dispatch_cmd(
        run_id,
        "packet-a",
        "owner-9",
        command_id="cmd-rc4",
    )
    save_advancement_command(repo, run_id, takeover)
    takeover_outcome = advance_run(repo, repo, run_id, "cmd-rc4")
    assert takeover_outcome.status == "rejected"
    assert "only owner-specific retry" in takeover_outcome.message


# ---------------------------------------------------------------------------
# Retry same owner/route, preserves evidence
# ---------------------------------------------------------------------------
def test_retry_preserves_owner_route_and_evidence(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    run_id, _ = _seed_run(tmp_path, repo)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    cmd = _dispatch_cmd(run_id, "packet-a", "owner-1", command_id="cmd-rt1", lease=300)
    save_advancement_command(repo, run_id, cmd)
    advance_run(repo, repo, run_id, "cmd-rt1", now=now)

    _write_evidence(repo, run_id, "ev-fail.json")
    cmd_fail = AdvanceCommand(
        command_id="cmd-rt2",
        run_id=run_id,
        action=AdvanceAction.fail,
        owner_id="owner-1",
        packet_id="packet-a",
        claim_id="claim-packet-a-1",
        evidence_reference="ev-fail.json",
    )
    save_advancement_command(repo, run_id, cmd_fail)
    out_fail = advance_run(repo, repo, run_id, "cmd-rt2", now=now + timedelta(seconds=10))
    assert out_fail.status == "ok"
    snap = load_advancement_snapshot(repo, run_id)
    assert snap.packet_state["packet-a"] is PacketState.failed
    assert snap.active_claim_id is None

    cmd_retry_bad = AdvanceCommand(
        command_id="cmd-rt3",
        run_id=run_id,
        action=AdvanceAction.retry,
        owner_id="owner-2",
        packet_id="packet-a",
        retry_claim_id="claim-packet-a-1",
    )
    save_advancement_command(repo, run_id, cmd_retry_bad)
    out_bad = advance_run(repo, repo, run_id, "cmd-rt3", now=now + timedelta(seconds=20))
    assert out_bad.status == "rejected"
    assert "owner" in out_bad.message

    cmd_retry = cmd_retry_bad.model_copy(update={"owner_id": "owner-1", "command_id": "cmd-rt4"})
    save_advancement_command(repo, run_id, cmd_retry)
    out_retry = advance_run(repo, repo, run_id, "cmd-rt4", now=now + timedelta(seconds=20))
    assert out_retry.status == "ok"
    assert out_retry.claim_id == "claim-packet-a-2"
    assert out_retry.attempt_id == "attempt-packet-a-2"
    assert load_sandbox_receipt(repo, run_id, "packet-a-attempt-2").packet_id == "packet-a"
    snap2 = load_advancement_snapshot(repo, run_id)
    attempt = next(a for a in snap2.attempts if a.attempt_id == "attempt-packet-a-2")
    assert attempt.route == "owner-1"
    assert (Path(repo) / ".devflow" / "pipeline-runs" / run_id / "ev-fail.json").is_file()


def test_retry_requires_terminal_state(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    run_id, _ = _seed_run(tmp_path, repo)
    cmd = _dispatch_cmd(run_id, "packet-a", "owner-1", command_id="cmd-rt1")
    save_advancement_command(repo, run_id, cmd)
    advance_run(repo, repo, run_id, "cmd-rt1")

    cmd_retry = AdvanceCommand(
        command_id="cmd-rt2",
        run_id=run_id,
        action=AdvanceAction.retry,
        owner_id="owner-1",
        packet_id="packet-a",
        retry_claim_id="claim-packet-a-1",
    )
    save_advancement_command(repo, run_id, cmd_retry)
    out = advance_run(repo, repo, run_id, "cmd-rt2")
    assert out.status == "rejected"
    assert "terminal" in out.message


# ---------------------------------------------------------------------------
# Optional typed workflow receipt only path
# ---------------------------------------------------------------------------
def test_optional_typed_workflow_receipt_only_path(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    run_id, _ = _seed_run(tmp_path, repo)
    _drive_workflow_to_build_judge(repo, run_id)
    cmd = _dispatch_cmd(run_id, "packet-a", "owner-1", command_id="cmd-wf1")
    save_advancement_command(repo, run_id, cmd)
    advance_run(repo, repo, run_id, "cmd-wf1")

    _write_evidence(repo, run_id, "ev-wf.json")
    cmd_wf = AdvanceCommand(
        command_id="cmd-wf2",
        run_id=run_id,
        action=AdvanceAction.complete,
        owner_id="owner-1",
        packet_id="packet-a",
        claim_id="claim-packet-a-1",
        evidence_reference="ev-wf.json",
        workflow_receipt=NodeReceipt(
            receipt_id="wf-receipt-1",
            node_id="build_judge",
            outcome="success",
            evidence=(EvidenceReference(key="build-judge-report", reference="ev-wf.json"),),
        ),
        workflow_event=WorkflowEvent(
            event_id="wf-event-1",
            node_id="build_judge",
            outcome="success",
            receipt_id="wf-receipt-1",
        ),
    )
    save_advancement_command(repo, run_id, cmd_wf)
    out = advance_run(repo, repo, run_id, "cmd-wf2")
    assert out.status == "ok"
    assert out.recorded_workflow is True
    wf = replay_workflow_run(repo, run_id)
    assert "build_judge" in wf.completed_node_ids

    run_id2, _ = _seed_run(tmp_path, repo)
    cmd2 = _dispatch_cmd(run_id2, "packet-a", "owner-1", command_id="cmd-wf3")
    save_advancement_command(repo, run_id2, cmd2)
    advance_run(repo, repo, run_id2, "cmd-wf3")
    _write_evidence(repo, run_id2, "ev-wf2.json")
    cmd_wf2 = AdvanceCommand(
        command_id="cmd-wf4",
        run_id=run_id2,
        action=AdvanceAction.complete,
        owner_id="owner-1",
        packet_id="packet-a",
        claim_id="claim-packet-a-1",
        evidence_reference="ev-wf2.json",
    )
    save_advancement_command(repo, run_id2, cmd_wf2)
    out2 = advance_run(repo, repo, run_id2, "cmd-wf4")
    assert out2.status == "ok"
    assert out2.recorded_workflow is False
    wf2 = replay_workflow_run(repo, run_id2)
    assert "build_judge" not in wf2.completed_node_ids


# ---------------------------------------------------------------------------
# Old/unmarked run load API returns readable without migration
# ---------------------------------------------------------------------------
def test_old_run_load_returns_readable_without_migration(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    run_id, _ = _seed_run(tmp_path, repo)
    snap = load_advancement_snapshot(repo, run_id)
    assert isinstance(snap, AdvancementSnapshot)
    assert set(snap.packet_state) == {"packet-a", "packet-b", "packet-c"}
    assert all(s is PacketState.pending for s in snap.packet_state.values())
    assert snap.active_claim_id is None
    assert snap.event_sequence == 0
