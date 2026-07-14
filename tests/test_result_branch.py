"""Phase 6B result-branch promotion behavior.

Deterministic tests for ``devflow.loop.result_branch``: a REAL branch under
``refs/heads/devflow/results/<run_id>`` is created create-only for an accepted
promotion-eligible decision, never for reject/request_changes, with
ref-safe + ``git check-ref-format --branch`` validation, immutable
promotion command/receipt authority, replay/collision/crash recovery,
locking, and no main/unrelated-ref mutation.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import threading
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
from devflow.loop.pipeline_run import pipeline_runs_dir
from devflow.loop.result_branch import (
    PromotionError,
    PromotionOutcome,
    PromotionReceipt,
    create_result_ref,
    has_result_branch,
    load_promotion_command,
    result_branch_commit,
)
from devflow.loop.run_advancement import (
    AdvanceAction,
    AdvanceCommand,
    advance_run,
    load_advancement_snapshot,
    save_advancement_command,
)
from devflow.loop.run_integration import (
    IntegrationCommand,
    IntegrationVerificationRequest,
    PatchCaptureCommand,
    capture_packet_patch,
    integrate_run,
    load_integration_snapshot,
    record_integration_verification,
    save_integration_command,
    save_patch_capture_command,
)
from devflow.loop.source_snapshot import SnapshotRequest, create_source_snapshot
from devflow.loop.validator_service import ValidatorRequest, run_validator
from devflow.loop.workflow_ledger import (
    DecisionReceipt,
    DecisionType,
)

UTC = timezone.utc


# ---------------------------------------------------------------------------
# Repo + run harness (mirrors tests/test_run_integration.py)
# ---------------------------------------------------------------------------
def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "--initial-branch=main")
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


def _build_packet(repo: Path, run_id: str, packet_id: str, *, value: int, owner: str):
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
        model_family="builder-family",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    save_patch_capture_command(repo, capture)
    return capture_packet_patch(repo, repo, run_id, capture.command_id)


def _build_all(repo: Path, run_id: str):
    _build_packet(repo, run_id, "packet-a", value=10, owner="owner-a")
    _build_packet(repo, run_id, "packet-b", value=20, owner="owner-b")


def _advance_to_verification(repo: Path, run_id: str) -> None:
    from devflow.loop.workflow_ledger import (
        EvidenceReference,
        NodeReceipt,
        WorkflowEvent,
        record_node_outcome,
    )

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


def _integrate_and_verify(repo: Path, run_id: str):
    _advance_to_verification(repo, run_id)
    command = IntegrationCommand(
        command_id="integrate-1",
        run_id=run_id,
        integration_id="result-1",
        authorization_id="auth-1",
        created_at=datetime(2026, 1, 2, tzinfo=UTC),
    )
    save_integration_command(repo, command)
    outcome = integrate_run(repo, repo, run_id, command.command_id)
    assert outcome.status.value == "awaiting_verification"
    state = load_integration_snapshot(repo, run_id)
    head, tree, fingerprint = state.head, state.tree, state.fingerprint
    assert head and tree and fingerprint
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
    verification = record_integration_verification(repo, repo, request)
    assert verification.verdict == "pass"
    return head, tree, fingerprint, verification


def _decision_receipt(
    run_id: str,
    *,
    decision_type: DecisionType,
    integration_id: str,
    integration_head: str,
    integration_tree: str,
    integration_fingerprint: str,
    verification_receipt_id: str,
    verification_receipt_hash: str,
    promotion_eligible: bool,
) -> DecisionReceipt:
    return DecisionReceipt(
        decision_id="decision-1",
        run_id=run_id,
        integration_id=integration_id,
        integration_head=integration_head,
        integration_tree=integration_tree,
        integration_fingerprint=integration_fingerprint,
        verification_receipt_id=verification_receipt_id,
        verification_receipt_hash=verification_receipt_hash,
        actor="operator",
        decision_type=decision_type,
        promotion_eligible=promotion_eligible,
        created_at=datetime(2026, 1, 5, tzinfo=UTC),
    )


def _accepted_receipt(repo: Path, run_id: str):
    head, tree, fingerprint, verification = _integrate_and_verify(repo, run_id)
    verification_sha256 = hashlib.sha256(
        json.dumps(
            verification.model_dump(mode="json"), indent=2, sort_keys=True
        ).encode()
        + b"\n"
    ).hexdigest()
    receipt = _decision_receipt(
        run_id,
        decision_type=DecisionType.accept,
        integration_id="result-1",
        integration_head=head,
        integration_tree=tree,
        integration_fingerprint=fingerprint,
        verification_receipt_id=verification.receipt_id,
        verification_receipt_hash=verification_sha256,
        promotion_eligible=True,
    )
    return receipt, head


def _verification_receipt_path(repo: Path, run_id: str, receipt_id: str) -> Path:
    return (
        _run_dir(repo, run_id)
        / "integration-verification-receipts"
        / f"{receipt_id}.json"
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
def test_accepted_promotion_creates_real_result_branch(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    run_id, _ = _seed(repo)
    _build_all(repo, run_id)
    receipt, head = _accepted_receipt(repo, run_id)

    main_before = _git(repo, "rev-parse", "main")
    all_refs_before = set(_git(repo, "for-each-ref", "--format=%(refname)").splitlines())

    result = create_result_ref(repo, repo, receipt, promotion_id="promo-1", actor="operator")

    assert result.state == "committed"
    assert result.outcome is PromotionOutcome.committed
    assert result.branch == f"refs/heads/devflow/results/{run_id}"
    assert result.commit == head

    # REAL branch under refs/heads, resolves to the exact verified head.
    assert has_result_branch(repo, run_id)
    assert result_branch_commit(repo, run_id) == head
    assert _git(repo, "rev-parse", f"refs/heads/devflow/results/{run_id}") == head
    assert _git(repo, "rev-parse", "--verify", f"refs/heads/devflow/results/{run_id}") == head

    # Only the result branch ref was added; main and all other refs untouched.
    all_refs_after = set(_git(repo, "for-each-ref", "--format=%(refname)").splitlines())
    assert all_refs_after - all_refs_before == {f"refs/heads/devflow/results/{run_id}"}
    assert _git(repo, "rev-parse", "main") == main_before
    # Operator files in the repo were not mutated by promotion.
    assert (repo / "a.py").read_text() == "value = 1\n"


def test_reject_and_request_changes_create_no_branch(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    run_id, _ = _seed(repo)
    _build_all(repo, run_id)
    receipt, head = _accepted_receipt(repo, run_id)

    for decision_type, eligible in (
        (DecisionType.reject, False),
        (DecisionType.request_changes, False),
    ):
        bad = _decision_receipt(
            run_id,
            decision_type=decision_type,
            integration_id="result-1",
            integration_head=head,
            integration_tree=receipt.integration_tree,
            integration_fingerprint=receipt.integration_fingerprint,
            verification_receipt_id=receipt.verification_receipt_id,
            verification_receipt_hash=receipt.verification_receipt_hash,
            promotion_eligible=eligible,
        )
        with pytest.raises(PromotionError):
            create_result_ref(repo, repo, bad, promotion_id="promo-bad", actor="operator")
        assert not has_result_branch(repo, run_id)
        # No promotion files persisted for non-promoting decisions.
        run_dir = _run_dir(repo, run_id)
        assert not (run_dir / "promotion-promo-bad.json").exists()


def test_unsafe_run_id_with_colon_rejected_before_mutation(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    run_id, _ = _seed(repo)
    _build_all(repo, run_id)
    receipt, head = _accepted_receipt(repo, run_id)
    # A colon is ref-unsafe. The ref-safe validation rejects it before any branch
    # is created (the _ID_PATTERN gate fires first; 'run..double' exercises the
    # git check-ref-format --branch path directly). model_construct bypasses the
    # upstream DecisionReceipt pattern so the unsafe id reaches create_result_ref.
    bad = DecisionReceipt.model_construct(
        decision_id="decision-1",
        run_id="run:1",
        integration_id="result-1",
        integration_head=head,
        integration_tree=receipt.integration_tree,
        integration_fingerprint=receipt.integration_fingerprint,
        verification_receipt_id=receipt.verification_receipt_id,
        verification_receipt_hash=receipt.verification_receipt_hash,
        actor="operator",
        decision_type=DecisionType.accept,
        promotion_eligible=True,
        created_at=datetime(2026, 1, 5, tzinfo=UTC),
    )
    with pytest.raises(PromotionError):
        create_result_ref(repo, repo, bad, promotion_id="promo-x", actor="operator")
    # No result-branch ref created for the rejected unsafe id.
    refs = _git(repo, "for-each-ref", "--format=%(refname)").splitlines()
    assert not any(r.startswith("refs/heads/devflow/results/") for r in refs)


@pytest.mark.parametrize(
    "run_id",
    [
        "run/escape",
        "run..double",
        ".run-dot",
        "run/trailing/",
        "run~tilde",
        "run^caret",
        "run space",
        " RUN_UPPER",
    ],
)
def test_unsafe_run_id_ref_hazards_rejected(tmp_path: Path, run_id: str) -> None:
    repo = _init_repo(tmp_path)
    # The unsafe ids below are rejected by the upstream DecisionReceipt pattern
    # (and by git check-ref-format). model_construct bypasses the upstream
    # pattern so each unsafe id reaches create_result_ref's own ref-safe +
    # git check-ref-format validation, which must fail closed BEFORE any branch
    # is created. The hazards cover: ref path escapes (/), double-dot (..),
    # leading dot (.), tilde (~), caret (^), and whitespace.
    bad = DecisionReceipt.model_construct(
        decision_id="decision-x",
        run_id=run_id,
        integration_id="result-x",
        integration_head="a" * 40,
        integration_tree="b" * 40,
        integration_fingerprint="c" * 64,
        verification_receipt_id="verify-x",
        verification_receipt_hash="d" * 64,
        actor="operator",
        decision_type=DecisionType.accept,
        promotion_eligible=True,
        created_at=datetime(2026, 1, 5, tzinfo=UTC),
    )
    with pytest.raises(PromotionError):
        create_result_ref(repo, repo, bad, promotion_id="promo-x", actor="operator")
    # No ref created for any rejected run id.
    refs = _git(repo, "for-each-ref", "--format=%(refname)").splitlines()
    assert all(not r.startswith("refs/heads/devflow/results/") for r in refs)


def test_exact_replay_is_idempotent_without_moving_ref(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    run_id, _ = _seed(repo)
    _build_all(repo, run_id)
    receipt, head = _accepted_receipt(repo, run_id)

    first = create_result_ref(repo, repo, receipt, promotion_id="promo-1", actor="operator")
    assert first.state == "committed"
    assert first.commit == head

    run_dir = _run_dir(repo, run_id)
    cmd_path = run_dir / "promotion-command-promo-1.json"
    receipt_path = run_dir / "promotion-promo-1.json"

    # --- Empirical immutability baseline (BEFORE replay) ---
    cmd_bytes_before = cmd_path.read_bytes()
    receipt_bytes_before = receipt_path.read_bytes()
    cmd_sha_before = hashlib.sha256(cmd_bytes_before).hexdigest()
    receipt_sha_before = hashlib.sha256(receipt_bytes_before).hexdigest()
    receipt_mode_before = receipt_path.stat().st_mode & 0o777
    # Canonical committed receipt is frozen 0o444 authority.
    assert receipt_mode_before == 0o444
    # Committed authority records the committed state.
    receipt_committed = PromotionReceipt.model_validate_json(receipt_path.read_text())
    assert receipt_committed.state == "committed"

    # Identical replay — branch already at the exact head, no move.
    second = create_result_ref(repo, repo, receipt, promotion_id="promo-1", actor="operator")
    assert second.state == "replayed"
    assert second.outcome is PromotionOutcome.replayed
    assert second.commit == head
    assert result_branch_commit(repo, run_id) == head

    # --- Empirical immutability proof (AFTER replay) ---
    assert cmd_path.read_bytes() == cmd_bytes_before
    assert receipt_path.read_bytes() == receipt_bytes_before
    assert cmd_path.stat().st_size == os.path.getsize(cmd_path)
    assert receipt_path.stat().st_size == os.path.getsize(receipt_path)
    assert receipt_path.stat().st_mode & 0o777 == 0o444
    assert result_branch_commit(repo, run_id) == head
    # The canonical receipt on disk is immutable authority — it stays committed.
    second_view = PromotionReceipt.model_validate_json(receipt_path.read_text())
    assert second_view.state == "committed"  # on-disk canonical unchanged
    # (The in-memory replayed view is the returned `second`, asserted above.)
    assert receipt_committed.state == "committed"  # on-disk unchanged
    assert _git(repo, "rev-parse", f"refs/heads/devflow/results/{run_id}") == head
    # No extra files written beyond the two immutable promotion authority files.
    promoted_files_after = sorted(
        f.name
        for f in run_dir.glob("*")
        if f.is_file() and f.name.startswith("promotion-")
    )
    assert promoted_files_after == ["promotion-command-promo-1.json", "promotion-promo-1.json"]


def test_canonical_receipt_is_byte_immutable_across_replay(tmp_path: Path) -> None:
    """Regression test: canonical committed receipt must NOT be rewritten on
    any replay, regardless of replay count or actor."""
    repo = _init_repo(tmp_path)
    run_id, _ = _seed(repo)
    _build_all(repo, run_id)
    receipt, head = _accepted_receipt(repo, run_id)

    run_dir = _run_dir(repo, run_id)
    cmd_path = run_dir / "promotion-command-promo-1.json"
    receipt_path = run_dir / "promotion-promo-1.json"

    first = create_result_ref(repo, repo, receipt, promotion_id="promo-1", actor="operator")
    assert first.state == "committed"
    assert result_branch_commit(repo, run_id) == head

    # Capture immutable baseline (canonical receipt).
    canonical_bytes_before = receipt_path.read_bytes()
    canonical_sha_before = hashlib.sha256(canonical_bytes_before).hexdigest()
    canonical_mode_before = receipt_path.stat().st_mode & 0o777
    canonical_mtime_before = receipt_path.stat().st_mtime_ns
    assert canonical_mode_before == 0o444
    # Command file baseline (immutable across replays).
    cmd_bytes_before = cmd_path.read_bytes()

    # Three sequential replays — no mutation allowed.
    for i in range(3):
        replay = create_result_ref(repo, repo, receipt, promotion_id="promo-1", actor="replayer")
        assert replay.state == "replayed"
        assert replay.commit == head
        assert result_branch_commit(repo, run_id) == head
        assert _git(repo, "rev-parse", f"refs/heads/devflow/results/{run_id}") == head

        # Empirical immutability after each replay.
        canonical_bytes_after = receipt_path.read_bytes()
        canonical_sha_after = hashlib.sha256(canonical_bytes_after).hexdigest()
        canonical_mode_after = receipt_path.stat().st_mode & 0o777
        canonical_mtime_after = receipt_path.stat().st_mtime_ns

        assert canonical_sha_before == canonical_sha_after, \
            f"canonical receipt rewritten on replay {i+1}"
        assert canonical_mode_before == canonical_mode_after, \
            f"canonical receipt mode changed on replay {i+1}"
        assert canonical_mtime_before == canonical_mtime_after, \
            f"canonical receipt mtime changed on replay {i+1}"

    # Command file also immutable.
    assert cmd_path.read_bytes() == cmd_bytes_before


def test_conflicting_promotion_replay_fails_closed(tmp_path: Path) -> None:
    """A replay with different intent (branch/commit) for the same promotion
    id must fail closed — no silent force-move, no ref mutation."""
    repo = _init_repo(tmp_path)
    run_id, _ = _seed(repo)
    _build_all(repo, run_id)
    receipt, head = _accepted_receipt(repo, run_id)

    first = create_result_ref(repo, repo, receipt, promotion_id="promo-1", actor="operator")
    assert first.state == "committed"
    assert result_branch_commit(repo, run_id) == head

    run_dir = _run_dir(repo, run_id)
    receipt_path = run_dir / "promotion-promo-1.json"

    # Overwrite canonical receipt with conflicting branch/commit (a valid
    # PromotionReceipt shape, but a different commit/branch than the command
    # binds — exercises the receipt-level conflict path).
    os.chmod(receipt_path, 0o644)
    conflicting = first.model_dump(mode="json")
    conflicting["commit"] = "0" * 40
    conflicting["branch"] = "refs/heads/other/branch"
    conflicting["state"] = "committed"
    conflicting["outcome"] = "committed"
    receipt_path.write_text(json.dumps(conflicting, indent=2, sort_keys=True) + "\n")

    # Replay with conflicting intent — must raise, NOT silently force-move.
    with pytest.raises(PromotionError, match="conflicting"):
        create_result_ref(repo, repo, receipt, promotion_id="promo-1", actor="operator")

    # Branch position must be UNCHANGED — no silent force-move.
    assert result_branch_commit(repo, run_id) == head
    assert _git(repo, "rev-parse", f"refs/heads/devflow/results/{run_id}") == head


def test_crash_ref_before_receipt_recovers_missing_receipt_without_move(tmp_path: Path) -> None:
    """If a crash happens after the ref is written but before the receipt is
    persisted, promotion must recover by persisting the missing receipt without
    moving the ref — the ref remains at the original commit."""
    repo = _init_repo(tmp_path)
    run_id, _ = _seed(repo)
    _build_all(repo, run_id)
    receipt, head = _accepted_receipt(repo, run_id)

    run_dir = _run_dir(repo, run_id)
    cmd_path = run_dir / "promotion-command-promo-1.json"
    receipt_path = run_dir / "promotion-promo-1.json"

    # 1) Run the real promotion so a valid immutable command + ref are durable.
    #    Then simulate a crash that lost the canonical receipt (ref + command
    #    remain) by removing the 0o444 receipt file.
    first = create_result_ref(repo, repo, receipt, promotion_id="promo-1", actor="operator")
    assert first.state == "committed"
    assert result_branch_commit(repo, run_id) == head
    os.chmod(receipt_path, 0o644)
    receipt_path.unlink()
    assert not receipt_path.exists()

    # 2) Recovery via create_result_ref: persist the missing receipt without
    #    moving the ref — the ref remains at the original commit.
    recovery = create_result_ref(repo, repo, receipt, promotion_id="promo-1", actor="operator")
    assert recovery.state == "replayed"
    assert recovery.commit == head
    assert receipt_path.exists(), "crash recovery must persist the missing receipt"
    assert result_branch_commit(repo, run_id) == head
    assert _git(repo, "rev-parse", f"refs/heads/devflow/results/{run_id}") == head
    # Receipt is canonical-locked: 0o444, O_EXCL protected.
    assert receipt_path.stat().st_mode & 0o777 == 0o444
    # The recovered receipt carries the replayed outcome (missing receipt
    # persisted as a replayed copy; the ref is never force-moved).
    recovery_receipt = PromotionReceipt.model_validate_json(receipt_path.read_text())
    assert recovery_receipt.state == "replayed"
    assert recovery_receipt.commit == head


def test_promotion_lock_serializes_concurrent_promotion(tmp_path: Path) -> None:
    """Lock must serialize concurrent promotions — exactly 1 committed + rest
    replayed, ref at exact head, no corruption."""
    repo = _init_repo(tmp_path)
    run_id, _ = _seed(repo)
    _build_all(repo, run_id)
    receipt, head = _accepted_receipt(repo, run_id)

    results = {"committed": 0, "replayed": 0}
    errors: list[BaseException] = []
    lock = threading.Lock()
    barrier = threading.Barrier(4)

    def promote():
        barrier.wait()
        try:
            result = create_result_ref(repo, repo, receipt, promotion_id="promo-1", actor="worker")
            with lock:
                if result.state == "committed":
                    results["committed"] += 1
                else:
                    results["replayed"] += 1
        except BaseException as e:
            with lock:
                errors.append(e)

    threads = [threading.Thread(target=promote) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"unhandled errors: {errors}"
    assert results["committed"] == 1
    assert results["replayed"] >= 3
    assert result_branch_commit(repo, run_id) == head
    assert _git(repo, "rev-parse", f"refs/heads/devflow/results/{run_id}") == head


def test_dirty_integration_worktree_fails_before_mutation(tmp_path: Path) -> None:
    """Dirty worktree must raise PromotionError BEFORE any branch is created."""
    repo = _init_repo(tmp_path)
    run_id, _ = _seed(repo)
    _build_all(repo, run_id)
    receipt, head = _accepted_receipt(repo, run_id)

    # Dirty the INTEGRATION SANDBOX worktree — that is what the promotion
    # authority actually checks (not the repo root).
    state = load_integration_snapshot(repo, run_id)
    assert state.sandbox_id is not None
    sandbox = load_sandbox_receipt(repo, run_id, state.sandbox_id)
    (Path(sandbox.path) / "a.py").write_text("value = 999\n", encoding="utf-8")

    with pytest.raises(PromotionError, match="dirty"):
        create_result_ref(repo, repo, receipt, promotion_id="promo-1", actor="operator")
    # No branch created — dirty worktree must fail BEFORE any ref is written.
    refs = _git(repo, "for-each-ref", "--format=%(refname)").splitlines()
    assert not any(r.startswith("refs/heads/devflow/results/") for r in refs)


def test_stale_fingerprint_fails_before_mutation(tmp_path: Path) -> None:
    """Stale fingerprint must raise PromotionError BEFORE any branch is created."""
    repo = _init_repo(tmp_path)
    run_id, _ = _seed(repo)
    _build_all(repo, run_id)
    receipt, head = _accepted_receipt(repo, run_id)

    stale = _decision_receipt(
        run_id,
        decision_type=DecisionType.accept,
        integration_id="result-1",
        integration_head=head,
        integration_tree=receipt.integration_tree,
        integration_fingerprint="0" * 64,
        verification_receipt_id=receipt.verification_receipt_id,
        verification_receipt_hash=receipt.verification_receipt_hash,
        promotion_eligible=True,
    )

    with pytest.raises(PromotionError, match="fingerprint"):
        create_result_ref(repo, repo, stale, promotion_id="promo-1", actor="operator")
    # No branch created — stale fingerprint must fail BEFORE any ref is written.
    refs = _git(repo, "for-each-ref", "--format=%(refname)").splitlines()
    assert not any(r.startswith("refs/heads/devflow/results/") for r in refs)


def test_missing_verification_receipt_fails_before_mutation(tmp_path: Path) -> None:
    """Deleted verification receipt must raise PromotionError BEFORE any
    branch is created."""
    repo = _init_repo(tmp_path)
    run_id, _ = _seed(repo)
    _build_all(repo, run_id)
    receipt, head = _accepted_receipt(repo, run_id)

    vpath = _verification_receipt_path(repo, run_id, receipt.verification_receipt_id)
    os.chmod(vpath, 0o644)
    vpath.unlink()
    assert not vpath.exists()

    with pytest.raises(PromotionError, match="missing or corrupt"):
        create_result_ref(repo, repo, receipt, promotion_id="promo-1", actor="operator")
    # No branch created — missing verification receipt must fail BEFORE any ref.
    refs = _git(repo, "for-each-ref", "--format=%(refname)").splitlines()
    assert not any(r.startswith("refs/heads/devflow/results/") for r in refs)


def test_non_passing_verification_fails_before_mutation(tmp_path: Path) -> None:
    """Tampered non-passing verdict must raise PromotionError BEFORE any branch
    is created."""
    repo = _init_repo(tmp_path)
    run_id, _ = _seed(repo)
    _build_all(repo, run_id)
    receipt, head = _accepted_receipt(repo, run_id)

    vpath = _verification_receipt_path(repo, run_id, receipt.verification_receipt_id)
    os.chmod(vpath, 0o644)
    bad = json.loads(vpath.read_text())
    # Only change the verdict; keep all required IntegrationVerificationReceipt
    # fields so the receipt still validates structurally (extra fields are
    # forbidden) and the non-passing verdict path fires.
    bad["verdict"] = "fail"
    vpath.write_text(json.dumps(bad, indent=2, sort_keys=True))

    with pytest.raises(PromotionError, match="non-passing"):
        create_result_ref(repo, repo, receipt, promotion_id="promo-1", actor="operator")
    # No branch created — non-passing verdict must fail BEFORE any ref.
    refs = _git(repo, "for-each-ref", "--format=%(refname)").splitlines()
    assert not any(r.startswith("refs/heads/devflow/results/") for r in refs)


def test_mismatched_verification_hash_fails_before_mutation(tmp_path: Path) -> None:
    """Tampered hash must raise PromotionError BEFORE any branch is created."""
    repo = _init_repo(tmp_path)
    run_id, _ = _seed(repo)
    _build_all(repo, run_id)
    receipt, head = _accepted_receipt(repo, run_id)

    # Wrong hash — not even a SHA256 of the receipt.
    bad = _decision_receipt(
        run_id,
        decision_type=DecisionType.accept,
        integration_id="result-1",
        integration_head=head,
        integration_tree=receipt.integration_tree,
        integration_fingerprint=receipt.integration_fingerprint,
        verification_receipt_id=receipt.verification_receipt_id,
        verification_receipt_hash="0" * 64,
        promotion_eligible=True,
    )

    with pytest.raises(PromotionError, match="hash does not match"):
        create_result_ref(repo, repo, bad, promotion_id="promo-1", actor="operator")
    # No branch created — mismatched hash must fail BEFORE any ref.
    refs = _git(repo, "for-each-ref", "--format=%(refname)").splitlines()
    assert not any(r.startswith("refs/heads/devflow/results/") for r in refs)


def test_no_main_or_unrelated_ref_mutation_on_promotion(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    run_id, _ = _seed(repo)
    _build_all(repo, run_id)
    receipt, head = _accepted_receipt(repo, run_id)

    main_commit = _git(repo, "rev-parse", "main")
    before = _git(repo, "for-each-ref", "--format=%(refname) %(objectname)").splitlines()

    create_result_ref(repo, repo, receipt, promotion_id="promo-1", actor="operator")

    after = _git(repo, "for-each-ref", "--format=%(refname) %(objectname)").splitlines()
    before_map = dict(line.split(" ", 1) for line in before)
    after_map = dict(line.split(" ", 1) for line in after)
    # Every pre-existing ref is unchanged.
    for ref, obj in before_map.items():
        assert after_map.get(ref) == obj, f"ref {ref} mutated during promotion"
    # main never moved.
    assert _git(repo, "rev-parse", "main") == main_commit
    # Only the result branch namespace gained a ref.
    new_refs = set(after_map) - set(before_map)
    assert new_refs == {f"refs/heads/devflow/results/{run_id}"}


def test_promotion_requires_live_accepted_receipt(tmp_path: Path) -> None:
    """Promotion reuses the P6-A authority: a bare receipt whose integration
    head does not match the live worktree fails closed; the result branch is
    never created."""
    repo = _init_repo(tmp_path)
    run_id, _ = _seed(repo)
    _build_all(repo, run_id)
    _accepted_receipt(repo, run_id)

    stale = _decision_receipt(
        run_id,
        decision_type=DecisionType.accept,
        integration_id="result-1",
        integration_head="a" * 40,
        integration_tree="b" * 40,
        integration_fingerprint="c" * 64,
        verification_receipt_id="verify-pass",
        verification_receipt_hash="d" * 64,
        promotion_eligible=True,
    )
    with pytest.raises(PromotionError):
        create_result_ref(repo, repo, stale, promotion_id="promo-1", actor="operator")
    assert not has_result_branch(repo, run_id)


def test_preexisting_result_branch_at_other_commit_fails_closed(tmp_path: Path) -> None:
    """A result branch already pointing at a DIFFERENT commit must fail closed
    as ``colliding`` — no silent force-move — and remain unmoved at the
    original commit (req 11 / collision)."""
    repo = _init_repo(tmp_path)
    run_id, _ = _seed(repo)
    _build_all(repo, run_id)
    receipt, head = _accepted_receipt(repo, run_id)

    branch_ref = f"refs/heads/devflow/results/{run_id}"
    # A pre-existing, unrelated commit placed on the result branch (a fresh
    # commit sharing the same tree as head, but a different commit sha).
    other_tree = _git(repo, "rev-parse", f"{head}^{{tree}}")
    other_commit = _git(repo, "commit-tree", other_tree, "-m", "other-result")
    _git(repo, "update-ref", branch_ref, other_commit, "")

    assert result_branch_commit(repo, run_id) == other_commit

    # Promotion must refuse to force-move the existing branch.
    with pytest.raises(PromotionError, match="different commit|colliding"):
        create_result_ref(repo, repo, receipt, promotion_id="promo-1", actor="operator")

    # The existing branch is untouched and still points at the other commit.
    assert result_branch_commit(repo, run_id) == other_commit
    assert _git(repo, "rev-parse", "--verify", branch_ref) == other_commit
    # The colliding attempt is recorded as a frozen colliding receipt (and its
    # command), but the ref is never force-moved.
    run_dir = _run_dir(repo, run_id)
    colliding_receipt = PromotionReceipt.model_validate_json(
        (run_dir / "promotion-promo-1.json").read_text()
    )
    assert colliding_receipt.state == "colliding"
    assert colliding_receipt.commit == other_commit
    assert (run_dir / "promotion-command-promo-1.json").exists()


def test_wrong_verification_receipt_family_fails_before_mutation(tmp_path: Path) -> None:
    """A verification receipt of the WRONG structural family (e.g. a
    DecisionReceipt / arbitrary JSON) must fail closed as 'missing or corrupt'
    BEFORE any branch is created (req 22 / wrong-family)."""
    repo = _init_repo(tmp_path)
    run_id, _ = _seed(repo)
    _build_all(repo, run_id)
    receipt, head = _accepted_receipt(repo, run_id)

    vpath = _verification_receipt_path(repo, run_id, receipt.verification_receipt_id)
    os.chmod(vpath, 0o644)
    # Wrong structural family: an IntegrationVerificationReceipt is expected,
    # but a DecisionReceipt-shaped dict is written (extra/forbidden fields).
    wrong = {
        "decision_id": "decision-1",
        "run_id": run_id,
        "integration_id": "result-1",
        "integration_head": head,
        "integration_tree": receipt.integration_tree,
        "integration_fingerprint": receipt.integration_fingerprint,
        "verification_receipt_id": receipt.verification_receipt_id,
        "verification_receipt_hash": receipt.verification_receipt_hash,
        "actor": "operator",
        "decision_type": "accept",
        "promotion_eligible": True,
        "created_at": "2026-01-05T00:00:00+00:00",
    }
    vpath.write_text(json.dumps(wrong, indent=2, sort_keys=True))
    # Drop any stale 0o444 mode left over from the original receipt.
    os.chmod(vpath, 0o644)

    with pytest.raises(PromotionError, match="missing or corrupt"):
        create_result_ref(repo, repo, receipt, promotion_id="promo-1", actor="operator")
    # No branch created — wrong-family receipt must fail BEFORE any ref.
    refs = _git(repo, "for-each-ref", "--format=%(refname)").splitlines()
    assert not any(r.startswith("refs/heads/devflow/results/") for r in refs)


def test_conflicting_promotion_command_fails_closed(tmp_path: Path) -> None:
    """A replay carrying a DIFFERENT immutable command for the same promotion id
    must fail closed as ``conflicting`` BEFORE any ref mutation (command-level
    conflict path, fired before authority re-validation)."""
    repo = _init_repo(tmp_path)
    run_id, _ = _seed(repo)
    _build_all(repo, run_id)
    receipt, head = _accepted_receipt(repo, run_id)

    first = create_result_ref(repo, repo, receipt, promotion_id="promo-1", actor="operator")
    assert first.state == "committed"
    assert result_branch_commit(repo, run_id) == head

    run_dir = _run_dir(repo, run_id)
    cmd_path = run_dir / "promotion-command-promo-1.json"

    # Overwrite the immutable command with a conflicting head/tree/fingerprint,
    # keeping a valid PromotionCommand shape (no extra fields).
    os.chmod(cmd_path, 0o644)
    conflicting = load_promotion_command(repo, run_id, "promo-1").model_dump(mode="json")
    conflicting["integration_head"] = "0" * 40
    conflicting["integration_tree"] = "0" * 40
    conflicting["integration_fingerprint"] = "0" * 64
    cmd_path.write_text(json.dumps(conflicting, indent=2, sort_keys=True) + "\n")
    os.chmod(cmd_path, 0o444)

    # Replay with conflicting intent — must raise, NOT silently mutate.
    with pytest.raises(PromotionError, match="conflicting"):
        create_result_ref(repo, repo, receipt, promotion_id="promo-1", actor="operator")

    # Branch position must be UNCHANGED — no force-move occurs.
    assert result_branch_commit(repo, run_id) == head
    assert _git(repo, "rev-parse", f"refs/heads/devflow/results/{run_id}") == head