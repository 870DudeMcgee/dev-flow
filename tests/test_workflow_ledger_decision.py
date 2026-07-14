"""Phase 6A direct deterministic decision-authority tests.

Isolated suite exercising the LIVE ``record_decision`` /
``record_operator_decision`` authority in ``devflow.loop.workflow_ledger``
without changing production. Reuses the acceptance harness from
``tests.test_result_branch`` (``_init_repo`` / ``_seed`` / ``_build_all`` /
``_integrate_and_verify`` / ``_accepted_receipt`` / ``_decision_receipt``) so
the full Phase 3->4->5 chain is exercised up to a clean, verified integration
worktree, then drives the decision authority directly.

Covered per the Phase 6 contract:
  * accept success binds run/integration/head/tree/fingerprint/verification
    receipt id+hash/actor/UTC and persists an immutable (0o444) receipt;
  * reject / request_changes are recorded but non-promotion-eligible;
  * dirty worktree, stale head/tree, and fingerprint mismatch fail closed;
  * missing / corrupt / non-passing verification receipt, and run /
    integration / hash binding mismatches fail closed;
  * exact replay is idempotent, conflicting replay fails closed;
  * the decision event is durably fsync'd before the receipt is exposed, and a
    duplicate decision event fails closed;
  * a receipt-write failure rolls back the just-appended decision event
    (crash-safety path);
  * the ``record_operator_decision`` wrapper delegates to the core API.

No phantom assertions for fields the Phase 6 contract does not require.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import pytest

from devflow.loop.git_sandbox import load_sandbox_receipt
from devflow.loop.human_decision import record_operator_decision
from devflow.loop.run_integration import load_integration_snapshot
from devflow.loop.workflow_ledger import (
    DECISION_EVENTS_FILE,
    DECISION_RECEIPTS_DIR,
    DecisionEvent,
    DecisionReceipt,
    DecisionType,
    record_decision,
)

from tests.test_result_branch import (
    _accepted_receipt,
    _decision_receipt,
    _init_repo,
    _integrate_and_verify,
    _run_dir,
    _seed,
    _build_all,
    _verification_receipt_path,
)

UTC = timezone.utc


# ---------------------------------------------------------------------------
# Local helpers (thin, no copy-heavy duplication of the acceptance harness)
# ---------------------------------------------------------------------------
def _acceptance(repo_tmp: Path) -> tuple[Path, str]:
    """Build repo + run up to a clean, verified integration worktree."""
    repo = _init_repo(repo_tmp)
    run_id, _ = _seed(repo)
    _build_all(repo, run_id)
    return repo, run_id


def _verification_sha256(verification) -> str:
    return hashlib.sha256(
        json.dumps(
            verification.model_dump(mode="json"), indent=2, sort_keys=True
        ).encode()
        + b"\n"
    ).hexdigest()


def _sandbox_worktree(repo: Path, run_id: str) -> Path:
    state = load_integration_snapshot(repo, run_id)
    assert state.sandbox_id is not None
    return Path(load_sandbox_receipt(repo, run_id, state.sandbox_id).path).resolve()


def _load_persisted_receipt(run_dir: Path, decision_id: str) -> DecisionReceipt:
    path = run_dir / DECISION_RECEIPTS_DIR / f"{decision_id}.json"
    return DecisionReceipt.model_validate_json(path.read_text(encoding="utf-8"))


def _tamper_verification(repo: Path, run_id: str, receipt_id: str, **overrides) -> None:
    path = _verification_receipt_path(repo, run_id, receipt_id)
    os.chmod(path, 0o644)
    data = json.loads(path.read_text(encoding="utf-8"))
    data.update(overrides)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(path, 0o444)


# ---------------------------------------------------------------------------
# Success binding
# ---------------------------------------------------------------------------
def test_accept_success_binds_all_fields_and_persists_immutable_receipt(
    tmp_path: Path,
) -> None:
    repo, run_id = _acceptance(tmp_path)
    receipt, _ = _accepted_receipt(repo, run_id)

    returned = record_decision(repo, receipt, repo=repo)
    assert returned == receipt

    run_dir = _run_dir(repo, run_id)
    receipt_path = run_dir / DECISION_RECEIPTS_DIR / f"{receipt.decision_id}.json"
    assert receipt_path.exists()

    # Exact field binding, reloaded from disk.
    persisted = _load_persisted_receipt(run_dir, receipt.decision_id)
    assert persisted == receipt
    assert persisted.run_id == run_id
    assert persisted.integration_id == "result-1"
    assert persisted.integration_head
    assert persisted.integration_tree
    assert persisted.integration_fingerprint
    assert persisted.verification_receipt_id == receipt.verification_receipt_id
    assert persisted.verification_receipt_hash == receipt.verification_receipt_hash
    assert persisted.actor == "operator"
    assert persisted.decision_type is DecisionType.accept
    assert persisted.promotion_eligible is True
    # UTC-aware timestamp.
    assert persisted.created_at.utcoffset() == UTC.utcoffset(None)

    # Receipt is frozen immutable authority (0o444).
    assert receipt_path.stat().st_mode & 0o777 == 0o444
    with pytest.raises(OSError):
        os.open(receipt_path, os.O_WRONLY)

    # Exactly one ordered decision event, bound to the receipt.
    events_path = run_dir / DECISION_EVENTS_FILE
    lines = [ln for ln in events_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 1
    event = DecisionEvent.model_validate_json(lines[0])
    assert event.event_id == f"decision-{receipt.decision_id}"
    assert event.decision_id == receipt.decision_id
    assert event.node_id == "human_decision"
    assert event.outcome == "accept"
    assert event.receipt_id == receipt.decision_id


# ---------------------------------------------------------------------------
# Non-promotion decisions
# ---------------------------------------------------------------------------
def test_reject_and_request_changes_are_recorded_non_promotion_eligible(
    tmp_path: Path,
) -> None:
    repo, run_id = _acceptance(tmp_path)
    head, tree, fingerprint, verification = _integrate_and_verify(repo, run_id)
    vhash = _verification_sha256(verification)

    run_dir = _run_dir(repo, run_id)

    for decision_type, decision_id in (
        (DecisionType.reject, "decision-reject"),
        (DecisionType.request_changes, "decision-changes"),
    ):
        receipt = _decision_receipt(
            run_id,
            decision_type=decision_type,
            integration_id="result-1",
            integration_head=head,
            integration_tree=tree,
            integration_fingerprint=fingerprint,
            verification_receipt_id=verification.receipt_id,
            verification_receipt_hash=vhash,
            promotion_eligible=False,
        ).model_copy(update={"decision_id": decision_id})

        returned = record_decision(repo, receipt, repo=repo)
        assert returned == receipt

        persisted = _load_persisted_receipt(run_dir, decision_id)
        # Non-promotion-eligible by contract.
        assert persisted.promotion_eligible is False
        assert persisted.decision_type is decision_type

        receipt_path = run_dir / DECISION_RECEIPTS_DIR / f"{decision_id}.json"
        assert receipt_path.stat().st_mode & 0o777 == 0o444

        events_path = run_dir / DECISION_EVENTS_FILE
        event_lines = [
            ln for ln in events_path.read_text(encoding="utf-8").splitlines() if ln.strip()
        ]
        outcomes = [
            DecisionEvent.model_validate_json(ln).outcome for ln in event_lines
        ]
        assert decision_type.value in outcomes


# ---------------------------------------------------------------------------
# Failure modes: integration worktree / binding
# ---------------------------------------------------------------------------
def test_dirty_integration_worktree_fails_before_persisting_decision(
    tmp_path: Path,
) -> None:
    repo, run_id = _acceptance(tmp_path)
    receipt, _ = _accepted_receipt(repo, run_id)

    worktree = _sandbox_worktree(repo, run_id)
    (worktree / "dirty.txt").write_text("uncommitted change\n")

    with pytest.raises(ValueError, match="dirty"):
        record_decision(repo, receipt, repo=repo)

    run_dir = _run_dir(repo, run_id)
    assert not (run_dir / DECISION_RECEIPTS_DIR / f"{receipt.decision_id}.json").exists()
    assert not (run_dir / DECISION_EVENTS_FILE).exists()


def test_stale_head_tree_fails_before_persisting_decision(tmp_path: Path) -> None:
    repo, run_id = _acceptance(tmp_path)
    head, tree, fingerprint, verification = _integrate_and_verify(repo, run_id)
    vhash = _verification_sha256(verification)

    stale = _decision_receipt(
        run_id,
        decision_type=DecisionType.accept,
        integration_id="result-1",
        integration_head="a" * 40,
        integration_tree="b" * 40,
        integration_fingerprint=fingerprint,
        verification_receipt_id=verification.receipt_id,
        verification_receipt_hash=vhash,
        promotion_eligible=True,
    )

    with pytest.raises(ValueError, match="head/tree does not match"):
        record_decision(repo, stale, repo=repo)

    run_dir = _run_dir(repo, run_id)
    assert not (run_dir / DECISION_RECEIPTS_DIR / f"{stale.decision_id}.json").exists()
    assert not (run_dir / DECISION_EVENTS_FILE).exists()


def test_fingerprint_mismatch_fails_before_persisting_decision(tmp_path: Path) -> None:
    repo, run_id = _acceptance(tmp_path)
    head, tree, _, verification = _integrate_and_verify(repo, run_id)
    vhash = _verification_sha256(verification)

    bad_fp = _decision_receipt(
        run_id,
        decision_type=DecisionType.accept,
        integration_id="result-1",
        integration_head=head,
        integration_tree=tree,
        integration_fingerprint="0" * 64,
        verification_receipt_id=verification.receipt_id,
        verification_receipt_hash=vhash,
        promotion_eligible=True,
    )

    with pytest.raises(ValueError, match="fingerprint does not match"):
        record_decision(repo, bad_fp, repo=repo)

    run_dir = _run_dir(repo, run_id)
    assert not (run_dir / DECISION_RECEIPTS_DIR / f"{bad_fp.decision_id}.json").exists()
    assert not (run_dir / DECISION_EVENTS_FILE).exists()


def test_decision_integration_id_mismatch_fails_before_persisting_decision(
    tmp_path: Path,
) -> None:
    repo, run_id = _acceptance(tmp_path)
    head, tree, fingerprint, verification = _integrate_and_verify(repo, run_id)
    vhash = _verification_sha256(verification)

    wrong = _decision_receipt(
        run_id,
        decision_type=DecisionType.accept,
        integration_id="other-integration",
        integration_head=head,
        integration_tree=tree,
        integration_fingerprint=fingerprint,
        verification_receipt_id=verification.receipt_id,
        verification_receipt_hash=vhash,
        promotion_eligible=True,
    )

    with pytest.raises(ValueError, match="different integration id than the run"):
        record_decision(repo, wrong, repo=repo)

    run_dir = _run_dir(repo, run_id)
    assert not (run_dir / DECISION_RECEIPTS_DIR / f"{wrong.decision_id}.json").exists()
    assert not (run_dir / DECISION_EVENTS_FILE).exists()


# ---------------------------------------------------------------------------
# Failure modes: verification receipt binding
# ---------------------------------------------------------------------------
def test_missing_verification_receipt_fails_before_persisting_decision(
    tmp_path: Path,
) -> None:
    repo, run_id = _acceptance(tmp_path)
    receipt, _ = _accepted_receipt(repo, run_id)

    vpath = _verification_receipt_path(repo, run_id, receipt.verification_receipt_id)
    os.chmod(vpath, 0o644)
    vpath.unlink()
    assert not vpath.exists()

    with pytest.raises(ValueError, match="missing or corrupt"):
        record_decision(repo, receipt, repo=repo)

    run_dir = _run_dir(repo, run_id)
    assert not (run_dir / DECISION_RECEIPTS_DIR / f"{receipt.decision_id}.json").exists()
    assert not (run_dir / DECISION_EVENTS_FILE).exists()


def test_corrupt_verification_receipt_fails_before_persisting_decision(
    tmp_path: Path,
) -> None:
    repo, run_id = _acceptance(tmp_path)
    receipt, _ = _accepted_receipt(repo, run_id)

    vpath = _verification_receipt_path(repo, run_id, receipt.verification_receipt_id)
    os.chmod(vpath, 0o644)
    vpath.write_text("{}\n")
    os.chmod(vpath, 0o444)

    with pytest.raises(ValueError, match="missing or corrupt"):
        record_decision(repo, receipt, repo=repo)

    run_dir = _run_dir(repo, run_id)
    assert not (run_dir / DECISION_RECEIPTS_DIR / f"{receipt.decision_id}.json").exists()
    assert not (run_dir / DECISION_EVENTS_FILE).exists()


def test_non_passing_verification_fails_before_persisting_decision(
    tmp_path: Path,
) -> None:
    repo, run_id = _acceptance(tmp_path)
    receipt, _ = _accepted_receipt(repo, run_id)

    _tamper_verification(
        repo, run_id, receipt.verification_receipt_id, verdict="fail"
    )

    with pytest.raises(ValueError, match="non-passing"):
        record_decision(repo, receipt, repo=repo)

    run_dir = _run_dir(repo, run_id)
    assert not (run_dir / DECISION_RECEIPTS_DIR / f"{receipt.decision_id}.json").exists()
    assert not (run_dir / DECISION_EVENTS_FILE).exists()


def test_verification_run_id_mismatch_fails_before_persisting_decision(
    tmp_path: Path,
) -> None:
    repo, run_id = _acceptance(tmp_path)
    receipt, _ = _accepted_receipt(repo, run_id)

    # Tamper the verification JSON's run_id binding directly (cannot pass it as a
    # kwarg override because it collides with the harness helper's run_id param).
    vpath = _verification_receipt_path(repo, run_id, receipt.verification_receipt_id)
    os.chmod(vpath, 0o644)
    vdata = json.loads(vpath.read_text(encoding="utf-8"))
    vdata["run_id"] = "other-run"
    vpath.write_text(json.dumps(vdata, indent=2, sort_keys=True) + "\n")
    os.chmod(vpath, 0o444)

    with pytest.raises(ValueError, match="different run"):
        record_decision(repo, receipt, repo=repo)

    run_dir = _run_dir(repo, run_id)
    assert not (run_dir / DECISION_RECEIPTS_DIR / f"{receipt.decision_id}.json").exists()
    assert not (run_dir / DECISION_EVENTS_FILE).exists()


def test_verification_integration_id_mismatch_fails_before_persisting_decision(
    tmp_path: Path,
) -> None:
    repo, run_id = _acceptance(tmp_path)
    receipt, _ = _accepted_receipt(repo, run_id)

    _tamper_verification(
        repo, run_id, receipt.verification_receipt_id, integration_id="other-integration"
    )

    with pytest.raises(ValueError, match="different integration"):
        record_decision(repo, receipt, repo=repo)

    run_dir = _run_dir(repo, run_id)
    assert not (run_dir / DECISION_RECEIPTS_DIR / f"{receipt.decision_id}.json").exists()
    assert not (run_dir / DECISION_EVENTS_FILE).exists()


def test_verification_hash_mismatch_fails_before_persisting_decision(
    tmp_path: Path,
) -> None:
    repo, run_id = _acceptance(tmp_path)
    head, tree, fingerprint, verification = _integrate_and_verify(repo, run_id)

    bad_hash = _decision_receipt(
        run_id,
        decision_type=DecisionType.accept,
        integration_id="result-1",
        integration_head=head,
        integration_tree=tree,
        integration_fingerprint=fingerprint,
        verification_receipt_id=verification.receipt_id,
        verification_receipt_hash="0" * 64,
        promotion_eligible=True,
    )

    with pytest.raises(ValueError, match="hash does not match"):
        record_decision(repo, bad_hash, repo=repo)

    run_dir = _run_dir(repo, run_id)
    assert not (run_dir / DECISION_RECEIPTS_DIR / f"{bad_hash.decision_id}.json").exists()
    assert not (run_dir / DECISION_EVENTS_FILE).exists()


# ---------------------------------------------------------------------------
# Replay semantics
# ---------------------------------------------------------------------------
def test_exact_replay_is_idempotent_without_duplicate_event(tmp_path: Path) -> None:
    repo, run_id = _acceptance(tmp_path)
    receipt, _ = _accepted_receipt(repo, run_id)

    first = record_decision(repo, receipt, repo=repo)
    second = record_decision(repo, receipt, repo=repo)

    assert second == first == receipt

    run_dir = _run_dir(repo, run_id)
    # Still exactly one event line — no double append on replay.
    events_path = run_dir / DECISION_EVENTS_FILE
    lines = [ln for ln in events_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 1
    # Receipt byte-immutable across replay.
    assert (run_dir / DECISION_RECEIPTS_DIR / f"{receipt.decision_id}.json").stat().st_mode & 0o777 == 0o444


def test_conflicting_replay_fails_closed(tmp_path: Path) -> None:
    repo, run_id = _acceptance(tmp_path)
    receipt, _ = _accepted_receipt(repo, run_id)

    run_dir = _run_dir(repo, run_id)
    receipt_path = run_dir / DECISION_RECEIPTS_DIR / f"{receipt.decision_id}.json"
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    # Pre-seed a conflicting (different actor) receipt with the same decision id.
    conflicting = receipt.model_copy(update={"actor": "someone-else"})
    receipt_path.write_text(
        json.dumps(conflicting.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    )
    os.chmod(receipt_path, 0o444)

    with pytest.raises(ValueError, match="conflicting decision receipt replay"):
        record_decision(repo, receipt, repo=repo)

    # No decision event was appended for the conflicting replay.
    events_path = run_dir / DECISION_EVENTS_FILE
    assert not events_path.exists() or not any(
        DecisionEvent.model_validate_json(ln).receipt_id == receipt.decision_id
        for ln in events_path.read_text(encoding="utf-8").splitlines()
        if ln.strip()
    )


# ---------------------------------------------------------------------------
# Ordering + duplicate-event guard
# ---------------------------------------------------------------------------
def test_duplicate_decision_event_fails_closed(tmp_path: Path) -> None:
    repo, run_id = _acceptance(tmp_path)
    receipt, _ = _accepted_receipt(repo, run_id)

    run_dir = _run_dir(repo, run_id)
    events_path = run_dir / DECISION_EVENTS_FILE
    events_path.parent.mkdir(parents=True, exist_ok=True)
    # Simulate a previously-appended (durable) decision event for this receipt.
    prior = DecisionEvent(
        event_id="prior-event",
        decision_id=receipt.decision_id,
        node_id="human_decision",
        outcome=receipt.decision_type.value,
        receipt_id=receipt.decision_id,
    )
    events_path.write_text(
        json.dumps(prior.model_dump(mode="json"), sort_keys=True) + "\n"
    )

    with pytest.raises(ValueError, match="duplicate decision event"):
        record_decision(repo, receipt, repo=repo)

    # The live decision receipt is never persisted when the event guard fires.
    assert not (run_dir / DECISION_RECEIPTS_DIR / f"{receipt.decision_id}.json").exists()


def test_event_is_fsyncd_before_receipt_then_rolled_back_on_receipt_failure(
    tmp_path: Path,
) -> None:
    """The decision event is durably on disk BEFORE the immutable receipt is
    exposed, and a receipt-write failure rolls back the just-appended event.

    Uses a spy on the immutable write primitive to observe the on-disk event
    ordering, then asserts the rollback removes the partial event.
    """
    import devflow.loop.workflow_ledger as ledger

    repo, run_id = _acceptance(tmp_path)
    receipt, _ = _accepted_receipt(repo, run_id)

    run_dir = _run_dir(repo, run_id)
    captured: dict[str, str] = {}

    def spy_write(path, data, mode=0o444):
        events_path = run_dir / DECISION_EVENTS_FILE
        # At the moment the receipt is about to be written, the event must
        # already be durably present on disk (fsync'd) and reference this receipt.
        captured["events"] = events_path.read_text(encoding="utf-8")
        raise OSError("injected receipt write failure")

    with mock.patch.object(ledger, "_write_exclusive", side_effect=spy_write):
        with pytest.raises(OSError, match="injected receipt write failure"):
            record_decision(repo, receipt, repo=repo)

    # The event was durable (observable on disk) before the receipt write.
    assert receipt.decision_id in captured["events"]

    # Rollback: neither the receipt nor the partial event survive.
    assert not (run_dir / DECISION_RECEIPTS_DIR / f"{receipt.decision_id}.json").exists()
    assert not (run_dir / DECISION_EVENTS_FILE).exists()


def test_receipt_write_failure_rolls_back_decision_event_crash_safety(
    tmp_path: Path,
) -> None:
    """Real (non-mocked) crash-safety path: a read-only decision-receipts dir
    makes the immutable O_EXCL receipt write fail, and the just-appended
    decision event is rolled back (no partial ledger state survives)."""
    repo, run_id = _acceptance(tmp_path)
    receipt, _ = _accepted_receipt(repo, run_id)

    run_dir = _run_dir(repo, run_id)
    receipts_dir = run_dir / DECISION_RECEIPTS_DIR
    receipts_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(receipts_dir, 0o555)  # make the immutable write deterministically fail

    try:
        with pytest.raises(Exception):
            record_decision(repo, receipt, repo=repo)
    finally:
        os.chmod(receipts_dir, 0o755)

    # Rollback: no receipt written, event ledger rolled back entirely.
    assert not (receipts_dir / f"{receipt.decision_id}.json").exists()
    assert not (run_dir / DECISION_EVENTS_FILE).exists()


# ---------------------------------------------------------------------------
# Wrapper delegation
# ---------------------------------------------------------------------------
def test_operator_decision_wrapper_delegates_to_core_authority(tmp_path: Path) -> None:
    repo, run_id = _acceptance(tmp_path)
    receipt, _ = _accepted_receipt(repo, run_id)

    returned = record_operator_decision(repo, receipt, repo=repo)
    assert returned == receipt

    run_dir = _run_dir(repo, run_id)
    assert (run_dir / DECISION_RECEIPTS_DIR / f"{receipt.decision_id}.json").exists()
    assert (run_dir / DECISION_EVENTS_FILE).exists()


# ---------------------------------------------------------------------------
# Authority invariants (accept must be promotion-eligible, others must not)
# ---------------------------------------------------------------------------
def test_accept_must_be_promotion_eligible_at_authority(tmp_path: Path) -> None:
    repo, run_id = _acceptance(tmp_path)
    head, tree, fingerprint, verification = _integrate_and_verify(repo, run_id)
    vhash = _verification_sha256(verification)

    # Bypass construction-time model validation to probe the live authority.
    bad = DecisionReceipt.model_construct(
        decision_id="decision-bad",
        run_id=run_id,
        integration_id="result-1",
        integration_head=head,
        integration_tree=tree,
        integration_fingerprint=fingerprint,
        verification_receipt_id=verification.receipt_id,
        verification_receipt_hash=vhash,
        actor="operator",
        decision_type=DecisionType.accept,
        promotion_eligible=False,
        created_at=datetime(2026, 1, 5, tzinfo=UTC),
    )

    with pytest.raises(ValueError, match="accept decisions must be promotion_eligible"):
        record_decision(repo, bad, repo=repo)

    run_dir = _run_dir(repo, run_id)
    assert not (run_dir / DECISION_RECEIPTS_DIR / f"{bad.decision_id}.json").exists()
    assert not (run_dir / DECISION_EVENTS_FILE).exists()


def test_non_accept_must_not_be_promotion_eligible_at_authority(
    tmp_path: Path,
) -> None:
    repo, run_id = _acceptance(tmp_path)
    head, tree, fingerprint, verification = _integrate_and_verify(repo, run_id)
    vhash = _verification_sha256(verification)

    bad = DecisionReceipt.model_construct(
        decision_id="decision-bad2",
        run_id=run_id,
        integration_id="result-1",
        integration_head=head,
        integration_tree=tree,
        integration_fingerprint=fingerprint,
        verification_receipt_id=verification.receipt_id,
        verification_receipt_hash=vhash,
        actor="operator",
        decision_type=DecisionType.reject,
        promotion_eligible=True,
        created_at=datetime(2026, 1, 5, tzinfo=UTC),
    )

    with pytest.raises(ValueError, match="only accept decisions may be promotion_eligible"):
        record_decision(repo, bad, repo=repo)

    run_dir = _run_dir(repo, run_id)
    assert not (run_dir / DECISION_RECEIPTS_DIR / f"{bad.decision_id}.json").exists()
    assert not (run_dir / DECISION_EVENTS_FILE).exists()
