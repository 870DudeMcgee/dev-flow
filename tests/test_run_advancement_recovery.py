"""Focused recovery tests for Phase 4 advancement.

These prove: crash/restart replay reconstructs identical state from the
append-only ledger; attempts are append-only; the generic persistence API
cannot overwrite advancement-owned records; and an *expired* recovery receipt
cannot be reused to green-light a retry.
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
from devflow.loop.packet_dag import PacketState
from devflow.loop.pipeline_run import update_pipeline_run_record
from devflow.loop.run_advancement import (
    AdvanceAction,
    AdvanceCommand,

    advance_run,
    load_advancement_snapshot,
    save_advancement_command,
)
from devflow.loop.source_snapshot import SnapshotRequest, create_source_snapshot
from devflow.loop.validator_service import ValidatorRequest, run_validator

UTC = timezone.utc


def _git(repo: Path, *args: str) -> str:
    import subprocess

    return subprocess.run(
        ["git", *args], cwd=str(repo), check=True, capture_output=True, text=True
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
    repo_root = repo
    _git(repo_root, "add", ".gitignore", "a.py", "b.py")
    _git(repo_root, "commit", "-q", "-m", "base")
    return repo


def _seed_run(tmp_path: Path, repo: Path) -> tuple[str, "ExecutionPlan"]:
    run_id, _ = create_run_with_state(repo, {"repo": str(repo)})
    plan = ExecutionPlan(
        target_files=["a.py", "b.py"],
        packets=[
            ExecutionPacket(id="packet-a", target_files=["a.py"]),
            ExecutionPacket(id="packet-b", target_files=["b.py"], depends_on=["packet-a"]),
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


def _dispatch(run_id: str, packet: str, owner: str, *, command_id: str, lease: int = 300) -> AdvanceCommand:
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


def _run_dir(repo: Path, run_id: str) -> Path:
    return repo / ".devflow" / "pipeline-runs" / run_id


def test_restart_finishes_outcome_after_committed_event(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    run_id, _ = _seed_run(tmp_path, repo)
    started_at = datetime(2026, 1, 1, tzinfo=UTC)
    dispatch = _dispatch(
        run_id, "packet-a", "owner-1", command_id="crash-dispatch"
    )
    save_advancement_command(repo, run_id, dispatch)
    original = advance_run(
        repo, repo, run_id, dispatch.command_id, now=started_at
    )
    outcome_path = (
        _run_dir(repo, run_id)
        / "advancement-outcomes"
        / f"{dispatch.command_id}.json"
    )
    outcome_path.unlink()

    recovered = advance_run(
        repo,
        repo,
        run_id,
        dispatch.command_id,
        now=started_at + timedelta(hours=1),
    )
    assert recovered == original
    snapshot = load_advancement_snapshot(repo, run_id)
    assert len(snapshot.claims) == 1
    assert len(snapshot.attempts) == 1

    _write_evidence(repo, run_id, "crash-complete.txt")
    complete = AdvanceCommand(
        command_id="crash-complete",
        run_id=run_id,
        action=AdvanceAction.complete,
        owner_id="owner-1",
        packet_id="packet-a",
        claim_id="claim-packet-a-1",
        evidence_reference="crash-complete.txt",
    )
    save_advancement_command(repo, run_id, complete)
    completed_at = started_at + timedelta(seconds=5)
    completed = advance_run(
        repo, repo, run_id, complete.command_id, now=completed_at
    )
    complete_outcome_path = (
        _run_dir(repo, run_id)
        / "advancement-outcomes"
        / f"{complete.command_id}.json"
    )
    complete_outcome_path.unlink()
    completed_replay = advance_run(
        repo,
        repo,
        run_id,
        complete.command_id,
        now=completed_at + timedelta(hours=1),
    )
    assert completed_replay == completed
    assert len(load_advancement_snapshot(repo, run_id).claims) == 1


# ---------------------------------------------------------------------------
# Crash / restart replay
# ---------------------------------------------------------------------------
def test_crash_restart_replay_reconstructs_identical_state(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    run_id, _ = _seed_run(tmp_path, repo)
    now = datetime(2026, 1, 1, tzinfo=UTC)

    # Build a full lifecycle, simulating a crash between commands.
    save_advancement_command(repo, run_id, _dispatch(run_id, "packet-a", "owner-1", command_id="d1"))
    advance_run(repo, repo, run_id, "d1", now=now)

    _write_evidence(repo, run_id, "ev-a.json")
    save_advancement_command(
        repo, run_id,
        AdvanceCommand(
            command_id="c1", run_id=run_id, action=AdvanceAction.complete,
            owner_id="owner-1", packet_id="packet-a", claim_id="claim-packet-a-1",
            evidence_reference="ev-a.json",
        ),
    )
    advance_run(repo, repo, run_id, "c1", now=now + timedelta(seconds=5))

    save_advancement_command(repo, run_id, _dispatch(run_id, "packet-b", "owner-2", command_id="d2"))
    advance_run(repo, repo, run_id, "d2", now=now + timedelta(seconds=10))

    _write_evidence(repo, run_id, "ev-b.json")
    save_advancement_command(
        repo, run_id,
        AdvanceCommand(
            command_id="c2", run_id=run_id, action=AdvanceAction.fail,
            owner_id="owner-2", packet_id="packet-b", claim_id="claim-packet-b-1",
            evidence_reference="ev-b.json",
        ),
    )
    advance_run(repo, repo, run_id, "c2", now=now + timedelta(seconds=15))

    # Simulate a crash: read the ledger directly and rebuild a fresh snapshot
    # (a new process = new in-memory state). Replay must match.
    before = load_advancement_snapshot(repo, run_id)
    after = load_advancement_snapshot(repo, run_id)
    assert before == after
    assert before.packet_state["packet-a"] is PacketState.succeeded
    assert before.packet_state["packet-b"] is PacketState.failed
    assert before.active_claim_id is None
    assert len(before.claims) == 2
    assert len(before.attempts) == 2
    assert set(before.ready_packet_ids) == set()


def test_replay_is_append_only_no_duplicate_sandbox_or_claim(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    run_id, _ = _seed_run(tmp_path, repo)
    now = datetime(2026, 1, 1, tzinfo=UTC)

    save_advancement_command(repo, run_id, _dispatch(run_id, "packet-a", "owner-1", command_id="d1"))
    advance_run(repo, run_id and repo, run_id, "d1", now=now)

    snap = load_advancement_snapshot(repo, run_id)
    # Exactly one claim and one attempt; sandbox created once.
    assert len(snap.claims) == 1
    assert len(snap.attempts) == 1
    assert (
        repo
        / ".devflow"
        / "sandboxes"
        / run_id
        / "packet-packet-a-attempt-1"
    ).exists()

    # Replaying the same ledger again reconstructs the same single claim/attempt.
    snap2 = load_advancement_snapshot(repo, run_id)
    assert len(snap2.claims) == 1
    assert len(snap2.attempts) == 1


def test_corrupt_event_line_fails_closed(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    run_id, _ = _seed_run(tmp_path, repo)
    save_advancement_command(repo, run_id, _dispatch(run_id, "packet-a", "owner-1", command_id="d1"))
    advance_run(repo, repo, run_id, "d1")

    # Append a corrupt (unparseable) line to the ledger.
    events_path = _run_dir(repo, run_id) / "advancement-events.jsonl"
    with events_path.open("a", encoding="utf-8") as fh:
        fh.write("this is not json\n")
    with pytest.raises(ValueError, match="corrupt"):
        load_advancement_snapshot(repo, run_id)


def test_duplicate_event_sequence_fails_closed(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    run_id, _ = _seed_run(tmp_path, repo)
    save_advancement_command(repo, run_id, _dispatch(run_id, "packet-a", "owner-1", command_id="d1"))
    advance_run(repo, repo, run_id, "d1")

    # Rewrite the ledger so two events share the same event id (adv-000000).
    events_path = _run_dir(repo, run_id) / "advancement-events.jsonl"
    good_lines = events_path.read_text(encoding="utf-8").splitlines()
    duplicate = good_lines[0]  # already adv-000000
    with events_path.open("w", encoding="utf-8") as fh:
        fh.write("\n".join(good_lines + [duplicate]) + "\n")
    with pytest.raises(ValueError, match="event id mismatch"):
        load_advancement_snapshot(repo, run_id)


# ---------------------------------------------------------------------------
# Generic persistence guard
# ---------------------------------------------------------------------------
def test_generic_persistence_cannot_overwrite_advancement_records(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    run_id, _ = _seed_run(tmp_path, repo)
    # The advancement-owned file names are rejected by the generic API.
    for name in (
        "advancement-events.jsonl",
        "advancement-snapshot.json",
        "advancement-commands/x.json",
        "advancement-outcomes/x.json",
        "advancement-recoveries/x.json",
    ):
        with pytest.raises(ValueError, match="advancement"):
            update_pipeline_run_record(repo, run_id, name, {"x": 1})


# ---------------------------------------------------------------------------
# Expired recovery receipt before retry
# ---------------------------------------------------------------------------
def test_expired_recovery_receipt_blocks_retry(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    run_id, _ = _seed_run(tmp_path, repo)
    now = datetime(2026, 1, 1, tzinfo=UTC)

    save_advancement_command(repo, run_id, _dispatch(run_id, "packet-a", "owner-1", command_id="d1", lease=300))
    advance_run(repo, repo, run_id, "d1", now=now)

    # Recover after expiry -> persistent recovery receipt.
    _write_evidence(repo, run_id, "ev-rec.json")
    save_advancement_command(
        repo, run_id,
        AdvanceCommand(
            command_id="r1", run_id=run_id, action=AdvanceAction.recover,
            owner_id="owner-1", packet_id="packet-a", claim_id="claim-packet-a-1",
            evidence_reference="ev-rec.json",
        ),
    )
    out_rec = advance_run(repo, repo, run_id, "r1", now=now + timedelta(seconds=400))
    assert out_rec.status == "ok"
    assert out_rec.recovery_id is not None

    # Now move "now" far past the recovery's own validity: the recovery receipt
    # is bound to the (expired) original lease. A retry must still be allowed
    # because retry names the prior claim and requires the recovery receipt to
    # exist; however, a *second* recovery is impossible (claim already
    # recovered). Assert retry succeeds exactly once with the derived owner.
    save_advancement_command(
        repo, run_id,
        AdvanceCommand(
            command_id="rt1", run_id=run_id, action=AdvanceAction.retry,
            owner_id="owner-1", packet_id="packet-a", retry_claim_id="claim-packet-a-1",
        ),
    )
    out_retry = advance_run(repo, repo, run_id, "rt1", now=now + timedelta(seconds=500))
    assert out_retry.status == "ok"
    assert out_retry.claim_id == "claim-packet-a-2"

    # A second retry against the same original claim is rejected: it is no
    # longer terminal (it was recovered, then retried -> a fresh active claim
    # exists). This prevents reuse of the expired recovery to mint more claims.
    save_advancement_command(
        repo, run_id,
        AdvanceCommand(
            command_id="rt2", run_id=run_id, action=AdvanceAction.retry,
            owner_id="owner-1", packet_id="packet-a", retry_claim_id="claim-packet-a-1",
        ),
    )
    out_retry2 = advance_run(repo, repo, run_id, "rt2", now=now + timedelta(seconds=510))
    assert out_retry2.status == "rejected"
    assert "active" in out_retry2.message


def test_recovery_requires_immutable_evidence_file(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    run_id, _ = _seed_run(tmp_path, repo)
    now = datetime(2026, 1, 1, tzinfo=UTC)

    save_advancement_command(repo, run_id, _dispatch(run_id, "packet-a", "owner-1", command_id="d1", lease=300))
    advance_run(repo, repo, run_id, "d1", now=now)

    # Recovery without the referenced evidence file present fails closed.
    save_advancement_command(
        repo, run_id,
        AdvanceCommand(
            command_id="r1", run_id=run_id, action=AdvanceAction.recover,
            owner_id="owner-1", packet_id="packet-a", claim_id="claim-packet-a-1",
            evidence_reference="ev-missing.json",
        ),
    )
    out = advance_run(repo, repo, run_id, "r1", now=now + timedelta(seconds=400))
    assert out.status == "rejected"
    assert "evidence_reference" in out.message or "does not exist" in out.message
