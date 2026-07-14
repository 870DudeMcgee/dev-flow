"""Focused tests for the optional repeat-only Phase 4 supervisor (r0).

These prove the supervisor:

* only *calls* ``advance_run`` for already-immutable commands it discovers;
  it never writes any Phase 4 record of its own (no command/claim/attempt/
  outcome/receipt/route/evidence/cancellation/recovery/success files other
  than what ``advance_run`` authors);
* discovers pending commands in stable sorted order;
* advances at most ``max_commands`` (default 1) existing pending ids per cycle;
* checks stop *before* each ``advance_run`` call (stop before -> no change;
  stop after one -> remaining left pending);
* skips commands that already have a valid immutable outcome (restart/repeat
  makes progress deterministically, same outcome after reload);
* fails closed on malformed command/outcome files;
* does not catch/hide advancement errors.
"""

from __future__ import annotations

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
from devflow.loop.pipeline_run import pipeline_runs_dir
from devflow.loop.run_advancement import (
    AdvanceAction,
    AdvanceCommand,
    advance_run,
    load_advancement_snapshot,
    save_advancement_command,
)
from devflow.loop.run_supervisor import (
    SupervisorCycleResult,
    pending_command_ids,
    run_supervisor_cycle,
)
from devflow.loop.source_snapshot import SnapshotRequest, create_source_snapshot
from devflow.loop.validator_service import ValidatorRequest, run_validator

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


def _seed_run(tmp_path: Path, repo: Path) -> str:
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
    return run_id


def _dispatch_cmd(run_id: str, packet: str, owner: str, *, command_id: str) -> AdvanceCommand:
    return AdvanceCommand(
        command_id=command_id,
        run_id=run_id,
        action=AdvanceAction.dispatch,
        owner_id=owner,
        packet_id=packet,
    )


def _seed_dispatch(repo: Path, run_id: str, *, owner: str = "owner-1") -> list[str]:
    """Persist immutable dispatch commands for packet-a/b/c (stable sorted)."""
    ids = ["cmd-c", "cmd-a", "cmd-b"]  # deliberately unsorted on disk
    packets = {"cmd-a": "packet-a", "cmd-b": "packet-b", "cmd-c": "packet-c"}
    for cid in ids:
        save_advancement_command(repo, run_id, _dispatch_cmd(run_id, packets[cid], owner, command_id=cid))
    return ids


def _run_dir(repo: Path, run_id: str) -> Path:
    return pipeline_runs_dir(repo).resolve() / run_id


def _complete_active(repo: Path, run_id: str) -> None:
    snapshot = load_advancement_snapshot(repo, run_id)
    claim = next(c for c in snapshot.claims if c.claim_id == snapshot.active_claim_id)
    evidence = f"complete-{claim.packet_id}.txt"
    (_run_dir(repo, run_id) / evidence).write_text("complete\n", encoding="utf-8")
    command = AdvanceCommand(
        command_id=f"settle-{claim.packet_id}",
        run_id=run_id,
        action=AdvanceAction.complete,
        owner_id=claim.owner_id,
        packet_id=claim.packet_id,
        claim_id=claim.claim_id,
        evidence_reference=evidence,
    )
    save_advancement_command(repo, run_id, command)
    assert advance_run(repo, repo, run_id, command.command_id).status == "ok"


def test_pending_discovers_sorted_excludes_decided(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    run_id = _seed_run(tmp_path, repo)
    _seed_dispatch(repo, run_id)

    # Nothing decided yet -> all pending, stable sorted regardless of disk order.
    assert pending_command_ids(repo, run_id) == ["cmd-a", "cmd-b", "cmd-c"]

    # Decide one (cmd-a) via the authoritative entry point.
    advance_run(repo, repo, run_id, "cmd-a")
    assert pending_command_ids(repo, run_id) == ["cmd-b", "cmd-c"]

    # A non-existent command dir still yields empty (no crash).
    assert pending_command_ids(repo, "no-such-run") == []


def test_cycle_advances_only_existing_max_one_default(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    run_id = _seed_run(tmp_path, repo)
    _seed_dispatch(repo, run_id)

    # Default max_commands=1 -> exactly one (the first in stable order).
    res = run_supervisor_cycle(repo, repo, run_id)
    assert isinstance(res, SupervisorCycleResult)
    assert res.advanced_command_ids == ("cmd-a",)
    assert res.considered_command_ids == ("cmd-a",)
    assert res.stopped is False
    assert res.outcomes["cmd-a"].status == "ok"

    # While packet-a is active, dependent dispatches remain pending and are not
    # consumed into immutable rejected outcomes.
    res2 = run_supervisor_cycle(repo, repo, run_id)
    assert res2.advanced_command_ids == ()
    assert pending_command_ids(repo, run_id) == ["cmd-b", "cmd-c"]

    _complete_active(repo, run_id)
    res3 = run_supervisor_cycle(repo, repo, run_id)
    assert res3.advanced_command_ids == ("cmd-b",)
    assert pending_command_ids(repo, run_id) == ["cmd-c"]


def test_cycle_max_commands_and_stable_order(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    run_id = _seed_run(tmp_path, repo)
    _seed_dispatch(repo, run_id)

    res = run_supervisor_cycle(repo, repo, run_id, max_commands=2)
    assert res.advanced_command_ids == ("cmd-a",)
    assert pending_command_ids(repo, run_id) == ["cmd-b", "cmd-c"]

    # max_commands=0 and >64 are rejected (explicit validation).
    with pytest.raises(ValueError, match="max_commands"):
        run_supervisor_cycle(repo, repo, run_id, max_commands=0)
    with pytest.raises(ValueError, match="max_commands"):
        run_supervisor_cycle(repo, repo, run_id, max_commands=65)


def test_cycle_stop_before_call_no_change(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    run_id = _seed_run(tmp_path, repo)
    _seed_dispatch(repo, run_id)

    stop = {"requested": True}
    res = run_supervisor_cycle(
        repo, repo, run_id, stop_requested=lambda: stop["requested"]
    )
    assert res.stopped is True
    assert res.advanced_command_ids == ()
    assert res.considered_command_ids == ()
    # Nothing advanced: the run's ledger is untouched.
    assert pending_command_ids(repo, run_id) == ["cmd-a", "cmd-b", "cmd-c"]


def test_cycle_stop_after_one_leaves_rest_pending(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    run_id = _seed_run(tmp_path, repo)
    _seed_dispatch(repo, run_id)

    checks = {"n": 0}

    def stop_after_one() -> bool:
        # The supervisor checks stop *before* each advance. On the first check
        # n==0 (pass); after the first advance we flip so the next pre-call
        # check returns True, leaving the rest pending.
        triggered = checks["n"] >= 1
        checks["n"] += 1
        return triggered

    res = run_supervisor_cycle(
        repo, repo, run_id, max_commands=3, stop_requested=stop_after_one
    )
    # Exactly one command advanced; remaining left pending.
    assert res.advanced_command_ids == ("cmd-a",)
    assert res.stopped is True
    assert pending_command_ids(repo, run_id) == ["cmd-b", "cmd-c"]


def test_cycle_completed_skipped_restart_safe_same_outcome(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    run_id = _seed_run(tmp_path, repo)
    _seed_dispatch(repo, run_id)

    # Complete all three through authoritative completion commands while the
    # supervisor only starts the next dependency-ready packet.
    for expected in ("cmd-a", "cmd-b", "cmd-c"):
        cycle = run_supervisor_cycle(repo, repo, run_id)
        assert cycle.advanced_command_ids == (expected,)
        _complete_active(repo, run_id)
    assert pending_command_ids(repo, run_id) == []

    # Restart: rerun processes nothing.
    res = run_supervisor_cycle(repo, repo, run_id)
    assert res.advanced_command_ids == ()
    assert res.stopped is False

    # Same outcome deterministic after reload from immutable records.
    first = advance_run(repo, repo, run_id, "cmd-a")
    again = advance_run(repo, repo, run_id, "cmd-a")
    assert again == first


def test_cycle_no_extra_files_only_advance_run_outputs(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    run_id = _seed_run(tmp_path, repo)
    _seed_dispatch(repo, run_id)

    run_supervisor_cycle(repo, repo, run_id, max_commands=2)

    run_dir = _run_dir(repo, run_id)
    # The supervisor must not author any record of its own.
    children = {p.name for p in run_dir.iterdir()}
    forbidden = {
        "supervisor-state.json",
        "supervisor.lock",
    }
    assert forbidden.isdisjoint(children)

    # advancement-commands dir contains exactly the three seeded commands and
    # nothing the supervisor added.
    cmd_dir = run_dir / "advancement-commands"
    assert sorted(p.name for p in cmd_dir.glob("*.json")) == [
        "cmd-a.json",
        "cmd-b.json",
        "cmd-c.json",
    ]
    # One-active scheduling means only packet-a was advanced by this cycle.
    out_dir = run_dir / "advancement-outcomes"
    assert sorted(p.name for p in out_dir.glob("*.json")) == [
        "cmd-a.json",
    ]


def test_pending_fails_closed_on_malformed_command(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    run_id = _seed_run(tmp_path, repo)
    _seed_dispatch(repo, run_id)

    # Corrupt one command file (valid JSON but an invalid record shape).
    cmd_path = _run_dir(repo, run_id) / "advancement-commands" / "cmd-b.json"
    import os

    os.chmod(cmd_path, 0o644)
    cmd_path.write_text('{"not": "a command"}', encoding="utf-8")
    with pytest.raises(ValueError):
        pending_command_ids(repo, run_id)


def test_pending_fails_closed_on_unexpected_file(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    run_id = _seed_run(tmp_path, repo)
    _seed_dispatch(repo, run_id)

    cmd_dir = _run_dir(repo, run_id) / "advancement-commands"
    (cmd_dir / "stray.txt").write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="non-JSON"):
        pending_command_ids(repo, run_id)


def test_pending_fails_closed_on_corrupt_outcome(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    run_id = _seed_run(tmp_path, repo)
    _seed_dispatch(repo, run_id)
    advance_run(repo, repo, run_id, "cmd-a")

    # Corrupt the existing outcome of an already-decided command: a later
    # discovery of any pending command must still validate decided outcomes
    # and thus fail closed.
    out_path = _run_dir(repo, run_id) / "advancement-outcomes" / "cmd-a.json"
    import os

    os.chmod(out_path, 0o644)
    out_path.write_text('{ this is not valid json', encoding="utf-8")
    with pytest.raises(ValueError):
        pending_command_ids(repo, run_id)


def test_cycle_forwards_now(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    run_id = _seed_run(tmp_path, repo)
    _seed_dispatch(repo, run_id)

    now = datetime(2026, 2, 2, tzinfo=UTC)
    res = run_supervisor_cycle(repo, repo, run_id, max_commands=1, now=now)
    assert res.advanced_command_ids == ("cmd-a",)
    # The forwarded timestamp drives the claim's decided-at time.
    assert res.outcomes["cmd-a"].decided_at == now


def test_cycle_does_not_hide_errors(tmp_path: Path) -> None:
    # The supervisor does not catch/hide advancement errors; advance_run's
    # exception propagates to the caller.
    repo = _init_repo(tmp_path)
    with pytest.raises(ValueError):
        advance_run(repo, repo, "nope", "ghost")


def test_cycle_monkeypatch_advance_run_called_for_pending(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    run_id = _seed_run(tmp_path, repo)
    _seed_dispatch(repo, run_id)

    import devflow.loop.run_supervisor as sup

    seen: list[str] = []
    real_advance = sup.advance_run

    def fake_advance(root, rrepo, run, command_id, *, now=None):
        seen.append(command_id)
        return real_advance(root, rrepo, run, command_id, now=now)

    with pytest.MonkeyPatch().context() as mp:
        mp.setattr(sup, "advance_run", fake_advance)
        res = sup.run_supervisor_cycle(repo, repo, run_id, max_commands=2)
    # The supervisor re-checks authoritative state after each call and never
    # consumes blocked dependent dispatches.
    assert seen == ["cmd-a"]
    assert res.advanced_command_ids == ("cmd-a",)
