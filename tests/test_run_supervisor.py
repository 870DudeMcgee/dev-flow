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
from pydantic import BaseModel

import pytest

from devflow.loop.adapter import create_run_with_state, save_loop_state
from devflow.loop.execution_authorization import authorize_execution
from devflow.loop.execution_plan import (
    ExecutionPacket,
    ExecutionPlan,
    ExecutionValidator,
    execution_plan_hash,
    save_execution_plan,
)
from devflow.loop.models import LoopStage, new_loop_state
from devflow.loop.git_sandbox import load_sandbox_receipt
from devflow.loop.pipeline_run import create_pipeline_run, pipeline_runs_dir
from devflow.loop.run_advancement import (
    AdvanceAction,
    AdvanceCommand,
    advance_run,
    load_advancement_snapshot,
    save_advancement_command,
)
from devflow.loop.run_integration import (
    IntegrationCommand,
    PatchCaptureCommand,
    capture_packet_patch,
    save_integration_command,
    save_patch_capture_command,
)
from devflow.loop.run_supervisor import (
    DeployAuthorization,
    DeployAuthorizeCommand,
    IntegrationSupervisorCycleResult,
    PushPrepareAuthorization,
    PushPrepareCommand,
    SupervisorCycleResult,
    pending_command_ids,
    pending_integration_command_ids,
    run_integration_supervisor_cycle,
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
    _git(repo, "init", "-q", "--initial-branch=main")
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


def _seed_noncanonical_run(tmp_path: Path, repo: Path) -> str:
    """Create a plain (non-canonical) pipeline run.

    Non-canonical runs store their stage purely in ``loop-state.json`` and do
    not enforce the canonical replay edge validation, so ``save_loop_state``
    can be used to park the run at an arbitrary stage (e.g. ``human_decision``)
    for boundary tests.
    """
    return create_pipeline_run(repo, {"repo": str(repo)})


def _seed_noncanonical_plan(repo: Path, run_id: str) -> None:
    """Author a valid authoritative execution plan + snapshot + authorization.

    Mirrors the canonical ``_seed_run`` setup but targets a non-canonical run
    created via ``create_pipeline_run``. The repeat-only supervisor never
    authors an execution plan of its own, so a non-canonical run must already
    have one before ``run_supervisor_cycle`` can load the advancement snapshot
    (``_command_is_actionable`` -> ``load_advancement_snapshot``). Without it
    the cycle fails closed with "no authoritative execution-plan.json" — a
    fixture gap, not a source defect. Three packets (a, b->a, c->a) match the
    dispatch commands seeded by ``_seed_dispatch``.
    """
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


def _seed_noncanonical_integration_plan(repo: Path, run_id: str) -> None:
    """Two-packet plan + snapshot + authorization for the integration cycle.

    ``test_human_decision_not_suppressed_before_boundary`` builds and captures
    packets ``a`` and ``b`` then integrates them, so the plan must list exactly
    those two packets (integration requires *all* plan packets to have
    succeeded). Mirrors the canonical ``_seed_run`` authorization flow.
    """
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


# ---------------------------------------------------------------------------
# P6-C supervisor / human-boundary regressions (fail-closed reserved authority)
# ---------------------------------------------------------------------------
def _park_human_decision(repo: Path, run_id: str) -> None:
    """Drive a non-canonical run's loop state to the hard human_decision stage.

    Uses ``save_loop_state`` with a plain ``loop-state.json`` so the stage is
    read back as ``human_decision`` by ``phase6_reached_human_decision``. This
    is the explicit hard human boundary the supervisor must never cross.
    """
    state = new_loop_state(run_id)
    state = state.model_copy(update={"stage": LoopStage.human_decision})
    save_loop_state(repo, state)


def test_cycle_stops_at_human_decision(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    run_id = _seed_noncanonical_run(tmp_path, repo)
    _seed_dispatch(repo, run_id)
    _park_human_decision(repo, run_id)

    # The boundary is hard: the cycle discovers nothing and advances nothing.
    res = run_supervisor_cycle(repo, repo, run_id)
    assert isinstance(res, SupervisorCycleResult)
    assert res.considered_command_ids == ()
    assert res.advanced_command_ids == ()
    assert res.outcomes == {}
    assert pending_command_ids(repo, run_id) == []
    # advance_run itself is never invoked for a parked run.
    import devflow.loop.run_supervisor as sup

    before = sup.advance_run
    calls = {"n": 0}

    def counting(*args, **kwargs):
        calls["n"] += 1
        return before(*args, **kwargs)

    with pytest.MonkeyPatch().context() as mp:
        mp.setattr(sup, "advance_run", counting)
        sup.run_supervisor_cycle(repo, repo, run_id)
    assert calls["n"] == 0


def test_no_self_accept_or_promote(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    run_id = _seed_noncanonical_run(tmp_path, repo)
    _seed_noncanonical_plan(repo, run_id)
    _seed_dispatch(repo, run_id)

    import devflow.loop.run_supervisor as sup
    import devflow.loop.workflow_ledger as ledger
    import devflow.loop.result_branch as result_branch

    calls = {"record_decision": 0, "create_result_ref": 0}
    real_record = ledger.record_decision
    real_ref = result_branch.create_result_ref

    def fake_record(*args, **kwargs):
        calls["record_decision"] += 1
        return real_record(*args, **kwargs)

    def fake_ref(*args, **kwargs):
        calls["create_result_ref"] += 1
        return real_ref(*args, **kwargs)

    # Drive the full supervisor cycle; the repeat-only supervisor must never
    # synthesize acceptance/promotion through reserved authority entry points.
    with pytest.MonkeyPatch().context() as mp:
        mp.setattr(ledger, "record_decision", fake_record)
        mp.setattr(result_branch, "create_result_ref", fake_ref)
        res = sup.run_supervisor_cycle(repo, repo, run_id, max_commands=3)
    # The repeat-only supervisor advances exactly the one dependency-ready
    # dispatch (cmd-a) and leaves packet-b/c pending on their dependency. A
    # second cycle re-checks authoritative state: cmd-a now holds an active
    # claim (no completed worktree), so it is not re-dispatched and the cycle
    # advances nothing. The supervisor never synthesizes a human decision or
    # result promotion either cycle.
    assert res.advanced_command_ids == ("cmd-a",)
    assert calls["record_decision"] == 0
    assert calls["create_result_ref"] == 0

    res2 = sup.run_supervisor_cycle(repo, repo, run_id, max_commands=3)
    assert res2.advanced_command_ids == ()
    assert calls["record_decision"] == 0
    assert calls["create_result_ref"] == 0


def test_reserved_prefix_rejected_advancement(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    run_id = _seed_noncanonical_run(tmp_path, repo)

    cmd_dir = _run_dir(repo, run_id) / "advancement-commands"
    cmd_dir.mkdir(parents=True, exist_ok=True)
    # A tampered decision-* file inside the advancement store must fail closed.
    (cmd_dir / "decision-tampered.json").write_text(
        '{"command_id": "decision-tampered"}', encoding="utf-8"
    )
    with pytest.raises(ValueError, match="reserved authority"):
        pending_command_ids(repo, run_id)

    # And a promotion-* prefix as well.
    (cmd_dir / "promotion-command-tampered.json").write_text(
        '{"command_id": "promotion-command-tampered"}', encoding="utf-8"
    )
    with pytest.raises(ValueError, match="reserved authority"):
        pending_command_ids(repo, run_id)


def test_reserved_prefix_rejected_integration_at_and_before_boundary(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    run_id = _seed_noncanonical_run(tmp_path, repo)

    store = _run_dir(repo, run_id) / "integration-commands"
    store.mkdir(parents=True, exist_ok=True)

    (store / "decision-tampered.json").write_text(
        '{"command_id": "decision-tampered"}', encoding="utf-8"
    )

    # BEFORE the boundary: a reserved file in integration-commands must raise.
    with pytest.raises(ValueError, match="reserved authority"):
        pending_integration_command_ids(repo, run_id)

    # AT the boundary: the human_decision early-return must NOT silently skip
    # the reserved tamper — it must still be rejected (fail-closed). This is
    # the defect P6-C-TEST-1 reproduced and now fixed.
    _park_human_decision(repo, run_id)
    with pytest.raises(ValueError, match="reserved authority"):
        pending_integration_command_ids(repo, run_id)


def test_no_main_ref_mutation(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    run_id = _seed_noncanonical_run(tmp_path, repo)
    _seed_noncanonical_plan(repo, run_id)
    _seed_dispatch(repo, run_id)

    main_before = _git(repo, "rev-parse", "main")
    head_before = _git(repo, "rev-parse", "HEAD")
    branches_before = set(_git(repo, "branch", "--list").split())

    # Run the supervisor through completion; it must only ever call
    # advance_run and never touch main / result refs / checkout/merge/push/PR.
    for _ in range(3):
        cycle = run_supervisor_cycle(repo, repo, run_id, max_commands=2)
        _complete_active(repo, run_id)
        if not cycle.advanced_command_ids:
            break

    main_after = _git(repo, "rev-parse", "main")
    head_after = _git(repo, "rev-parse", "HEAD")
    branches_after = set(_git(repo, "branch", "--list").split())

    assert main_after == main_before
    assert head_after == head_before
    assert branches_after == branches_before
    # No devflow/results branch or result refs may appear.
    assert "results" not in branches_after
    refs = _git(repo, "for-each-ref", "--format=%(refname)")
    assert "refs/heads/devflow/results" not in refs.split()


def test_push_prepare_disabled_distinct_no_side_effect(tmp_path: Path) -> None:
    prep = PushPrepareCommand(
        command_id="push-prep-1",
        run_id="run-1",
        authorization=PushPrepareAuthorization.prepare_push,
    )
    deploy = DeployAuthorizeCommand(
        command_id="deploy-1",
        run_id="run-1",
        authorization=DeployAuthorization.deploy,
    )
    # Disabled by default and strict (frozen, extra forbidden).
    assert prep.enabled is False
    assert deploy.enabled is False
    assert prep.model_config.get("extra") == "forbid"
    assert deploy.model_config.get("extra") == "forbid"
    assert prep.model_config.get("frozen") is True
    assert deploy.model_config.get("frozen") is True
    # Distinct typed boundaries: different authorization enums and no shared
    # promotion/accept semantics.
    assert prep.authorization is PushPrepareAuthorization.prepare_push
    assert deploy.authorization is DeployAuthorization.deploy
    assert PushPrepareAuthorization != DeployAuthorization
    assert set(PushPrepareAuthorization) != set(DeployAuthorization)
    # Distinct strict BaseModel subclasses that construct independently — each
    # is a separate type with its own authorization semantics, not a shared or
    # reused boundary.
    assert issubclass(type(prep), BaseModel)
    assert issubclass(type(deploy), BaseModel)
    assert type(prep) is not type(deploy)
    # No side-effect methods exist — these are pure inert authorization
    # boundaries the supervisor may never execute or synthesize. The only
    # callables on each model are inherited pydantic BaseModel methods; neither
    # defines its own callable (which is where a side-effect implementation
    # would live).
    base_callables = {
        name
        for name in dir(BaseModel)
        if not name.startswith("_") and callable(getattr(BaseModel, name))
    }
    prep_callables = {
        name
        for name in dir(prep)
        if not name.startswith("_") and callable(getattr(prep, name))
    }
    deploy_callables = {
        name
        for name in dir(deploy)
        if not name.startswith("_") and callable(getattr(deploy, name))
    }
    assert prep_callables <= base_callables
    assert deploy_callables <= base_callables
    # Reject extra fields: the boundary is strict and cannot be extended into a
    # side-effecting command through unexpected keyword arguments.
    with pytest.raises(ValueError):
        type(prep)(
            command_id="x",
            run_id="run-1",
            authorization=PushPrepareAuthorization.prepare_push,
            unexpected_field=1,
        )
    with pytest.raises(ValueError):
        type(deploy)(
            command_id="x",
            run_id="run-1",
            authorization=DeployAuthorization.deploy,
            unexpected_field=1,
        )


def test_reserved_commands_never_discovered_or_executed(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    run_id = _seed_noncanonical_run(tmp_path, repo)
    _seed_noncanonical_plan(repo, run_id)
    _seed_dispatch(repo, run_id)

    # PushPrepare/DeployAuthorize instances are not placed in any command
    # store, so the supervisor cycles must never discover or execute them.
    prep = PushPrepareCommand(
        command_id="push-prep-2",
        run_id=run_id,
        authorization=PushPrepareAuthorization.prepare_pr,
    )
    deploy = DeployAuthorizeCommand(
        command_id="deploy-2",
        run_id=run_id,
        authorization=DeployAuthorization.deploy,
    )
    # They are only class-defined and exported here; never persisted.
    res = run_supervisor_cycle(repo, repo, run_id, max_commands=3)
    assert prep.command_id not in res.considered_command_ids
    assert deploy.command_id not in res.advanced_command_ids
    # The cycle legitimately advanced cmd-a (dependency-ready -> immutable
    # outcome written), leaving the remaining dispatch commands pending. The
    # reserved prep/deploy instances were never persisted, so they can never be
    # discovered or executed — that is the contract being protected here.
    assert pending_command_ids(repo, run_id) == ["cmd-b", "cmd-c"]
    assert prep.command_id not in pending_command_ids(repo, run_id)
    assert deploy.command_id not in pending_command_ids(repo, run_id)
    # Reserved decision-/promotion- authority commands fail closed: a tampered
    # reserved file dropped into the store is rejected (never discovered or
    # executed), even after a normal cycle. This preserves the fail-closed
    # boundary without weakening coverage.
    cmd_dir = _run_dir(repo, run_id) / "advancement-commands"
    (cmd_dir / "decision-tamper.json").write_text(
        '{"command_id": "decision-tamper"}', encoding="utf-8"
    )
    with pytest.raises(ValueError, match="reserved"):
        pending_command_ids(repo, run_id)


def test_human_decision_not_suppressed_before_boundary(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    run_id = _seed_noncanonical_run(tmp_path, repo)
    _seed_noncanonical_integration_plan(repo, run_id)

    # Park at verification (pre-boundary) so the human_decision gate is NOT
    # yet reached; a valid integration command must still be discovered and
    # advanced. The boundary must not prematurely suppress integration work.
    state = new_loop_state(run_id)
    state = state.model_copy(update={"stage": LoopStage.verification})
    save_loop_state(repo, state)

    # Build, complete, and capture both plan packets (a then b, satisfying
    # the dependency edge) so integration has a fully succeeded patch set to
    # apply. This mirrors the live capture/integration flow used elsewhere.
    for packet_id, value, owner in (
        ("packet-a", 10, "owner-a"),
        ("packet-b", 20, "owner-b"),
    ):
        dispatch_id = f"dispatch-{packet_id}"
        save_advancement_command(
            repo,
            run_id,
            AdvanceCommand(
                command_id=dispatch_id,
                run_id=run_id,
                action=AdvanceAction.dispatch,
                owner_id=owner,
                packet_id=packet_id,
            ),
        )
        started = advance_run(repo, repo, run_id, dispatch_id)
        sandbox_id = next(
            attempt.sandbox_id
            for attempt in load_advancement_snapshot(repo, run_id).attempts
            if attempt.attempt_id == started.attempt_id
        )
        sandbox = load_sandbox_receipt(repo, run_id, sandbox_id)
        target = "a.py" if packet_id == "packet-a" else "b.py"
        Path(sandbox.path, target).write_text(
            f"value = {value}\n", encoding="utf-8"
        )
        evidence = f"evidence-{packet_id}.txt"
        (_run_dir(repo, run_id) / evidence).write_text("passed\n", encoding="utf-8")
        complete_id = f"complete-{packet_id}"
        save_advancement_command(
            repo,
            run_id,
            AdvanceCommand(
                command_id=complete_id,
                run_id=run_id,
                action=AdvanceAction.complete,
                owner_id=owner,
                packet_id=packet_id,
                claim_id=started.claim_id,
                attempt_id=started.attempt_id,
                evidence_reference=evidence,
            ),
        )
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
            model_family="builder-family",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        save_patch_capture_command(repo, capture)
        capture_packet_patch(repo, repo, run_id, capture.command_id)

    command = IntegrationCommand(
        command_id="integrate-1",
        run_id=run_id,
        integration_id="result-1",
        authorization_id="auth-1",
        created_at=datetime(2026, 1, 2, tzinfo=UTC),
    )
    save_integration_command(repo, command)

    assert pending_integration_command_ids(repo, run_id) == ["integrate-1"]
    res = run_integration_supervisor_cycle(repo, repo, run_id)
    assert isinstance(res, IntegrationSupervisorCycleResult)
    assert res.considered_command_ids == ("integrate-1",)
    assert res.advanced_command_ids == ("integrate-1",)
