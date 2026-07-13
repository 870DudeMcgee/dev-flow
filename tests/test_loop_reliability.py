"""Focused fail-closed and recovery tests for the run reliability gate."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from devflow.loop.adapter import load_loop_state, save_loop_state
from devflow.loop.human_decision import (
    HumanDecision,
    HumanDecisionRecord,
    record_final_decision,
    record_human_decision,
)
from devflow.loop.local_audition_host_gates import (
    FinalDecisionInputs,
    IdentityEvidenceInput,
    ReliabilityResultInput,
    ReviewResultInput,
    VerificationTestReceiptInput,
)
from devflow.loop.models import LoopStage
from devflow.loop.pipeline_run import (
    append_worker_feed_entry,
    create_pipeline_run,
    read_execution_control,
    update_execution_control,
    update_pipeline_run_record,
)
from devflow.loop.reliability import (
    ReliabilityThresholds,
    evaluate_run_reliability,
    migrate_legacy_receipt_attestations,
    recover_interrupted_run,
)
from devflow.loop.verification import (
    VerificationReceipt,
    VerificationStatus,
    record_verification_receipt,
)


def _receipt(run_id: str, *, status: VerificationStatus = VerificationStatus.passed):
    return VerificationReceipt(
        run_id=run_id,
        receipt_id="verified",
        status=status,
        command="python -m pytest tests/test_feature.py -q",
        summary="focused verification passed",
        exit_code=0 if status == VerificationStatus.passed else 1,
        created_at=datetime.now(timezone.utc).isoformat(),
    )


def _ready_run(tmp_path):
    run_id = create_pipeline_run(tmp_path, {"test": "reliability"})
    state = load_loop_state(tmp_path, run_id).model_copy(
        update={"stage": LoopStage.verification, "builder_judge_passed": True}
    )
    save_loop_state(tmp_path, state)
    record_verification_receipt(tmp_path, _receipt(run_id))
    return tmp_path, run_id


def _worker_event(
    root,
    run_id,
    event,
    role,
    model="free-code-fleet",
    *,
    actual_model="",
):
    append_worker_feed_entry(root, run_id, {
        "event": event,
        "role": role,
        "model": model,
        "content": "{}",
        "usage": {"actual_model": actual_model} if actual_model else {},
    })


def test_attested_receipt_passes_and_tampering_blocks_acceptance(tmp_path):
    root, run_id = _ready_run(tmp_path)

    assert evaluate_run_reliability(root, run_id).safe is True

    receipt_path = (
        root / ".devflow" / "pipeline-runs" / run_id
        / "verification-receipt-verified.json"
    )
    tampered = json.loads(receipt_path.read_text(encoding="utf-8"))
    tampered["summary"] = "tampered after verification"
    receipt_path.write_text(json.dumps(tampered), encoding="utf-8")

    report = evaluate_run_reliability(root, run_id)
    assert report.safe is False
    assert report.action == "rollback"
    assert "verification receipt integrity failed" in report.breaches

    decision = HumanDecisionRecord(
        run_id=run_id,
        decision_id="accept-tampered",
        decision=HumanDecision.accept,
        summary="accept",
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    record_final_decision(
        root,
        run_id,
        FinalDecisionInputs(
            test_receipt=VerificationTestReceiptInput(
                "verification-receipt-verified.json", 0, 0, 0, "passed"
            ),
            review_result=ReviewResultInput("builder-judge-gate", "passed"),
            reliability_result=ReliabilityResultInput("reliability-report.json", "unsafe"),
            identity_evidence=IdentityEvidenceInput(
                "identity-gate", "deterministic-host", "deterministic-host", True
            ),
        ),
    )
    with pytest.raises(ValueError, match="deterministic final decision"):
        record_human_decision(root, decision)
    decision_path = (
        root / ".devflow" / "pipeline-runs" / run_id
        / "human-decision-accept-tampered.json"
    )
    assert not decision_path.exists()


def test_conflicting_receipt_replay_is_rejected_without_overwrite(tmp_path):
    root, run_id = _ready_run(tmp_path)
    original_path = (
        root / ".devflow" / "pipeline-runs" / run_id
        / "verification-receipt-verified.json"
    )
    original = original_path.read_text(encoding="utf-8")

    with pytest.raises(ValueError, match="Conflicting verification receipt replay"):
        record_verification_receipt(
            root,
            _receipt(run_id, status=VerificationStatus.failed),
        )

    assert original_path.read_text(encoding="utf-8") == original
    assert evaluate_run_reliability(root, run_id).safe is True


def test_concurrent_role_ownership_exceeds_rollback_threshold(tmp_path):
    root, run_id = _ready_run(tmp_path)
    _worker_event(root, run_id, "started", "builder")
    _worker_event(root, run_id, "started", "judge", "free-review-fleet")
    _worker_event(root, run_id, "completed", "judge", "free-review-fleet")
    _worker_event(root, run_id, "completed", "builder")

    report = evaluate_run_reliability(root, run_id)

    assert report.metrics["concurrent_role_starts"] == 1
    assert report.action == "rollback"
    assert "concurrent role ownership threshold exceeded" in report.breaches


def test_routing_drift_is_visible_and_fails_closed(tmp_path):
    root, run_id = _ready_run(tmp_path)
    for model in ("free-code-fleet", "unexpected-builder"):
        _worker_event(root, run_id, "started", "builder", model)
        _worker_event(root, run_id, "completed", "builder", model)

    report = evaluate_run_reliability(root, run_id)

    assert report.metrics["routing_drifts"] == 1
    assert report.thresholds.max_routing_drifts == 0
    assert report.action == "rollback"


def test_provider_fault_threshold_is_explicit(tmp_path):
    root, run_id = _ready_run(tmp_path)
    for _ in range(3):
        _worker_event(root, run_id, "started", "builder")
        _worker_event(root, run_id, "failed", "builder")

    report = evaluate_run_reliability(root, run_id)

    assert report.metrics["provider_faults"] == 3
    assert report.thresholds == ReliabilityThresholds(max_provider_faults=2)
    assert "provider fault threshold exceeded" in report.breaches
    assert report.action == "rollback"


def test_provider_actual_model_must_belong_to_configured_fleet(tmp_path):
    root, run_id = _ready_run(tmp_path)
    _worker_event(root, run_id, "started", "builder")
    _worker_event(
        root,
        run_id,
        "completed",
        "builder",
        actual_model="unapproved/provider-model:free",
    )

    report = evaluate_run_reliability(root, run_id)

    assert report.metrics["provider_route_violations"] == 1
    assert report.action == "rollback"
    assert "provider actual-model route threshold exceeded" in report.breaches


def test_free_cloud_completion_requires_actual_model_evidence(tmp_path):
    root, run_id = _ready_run(tmp_path)
    _worker_event(root, run_id, "started", "builder")
    _worker_event(root, run_id, "completed", "builder")

    report = evaluate_run_reliability(root, run_id)

    assert report.metrics["missing_actual_models"] == 1
    assert report.thresholds.max_missing_actual_models == 0
    assert "provider actual-model evidence is missing" in report.breaches
    assert report.action == "rollback"


def test_actual_builder_and_reviewer_models_must_be_disjoint(tmp_path):
    root, run_id = _ready_run(tmp_path)
    actual = "tencent/hy3-20260706:free"
    _worker_event(root, run_id, "started", "builder", "free-code-fleet")
    _worker_event(
        root,
        run_id,
        "completed",
        "builder",
        "free-code-fleet",
        actual_model=actual,
    )
    _worker_event(root, run_id, "started", "judge", "free-review-fleet")
    _worker_event(
        root,
        run_id,
        "completed",
        "judge",
        "free-review-fleet",
        actual_model=actual,
    )

    report = evaluate_run_reliability(root, run_id)

    assert report.metrics["builder_reviewer_overlap"] == 1
    assert "builder/reviewer independence threshold exceeded" in report.breaches
    assert report.action == "rollback"


@pytest.mark.parametrize(
    (
        "builder_fleet",
        "builder_actual",
        "reviewer_role",
        "reviewer_fleet",
        "reviewer_actual",
    ),
    [
        (
            "free-code-fleet",
            "google/gemma-4-26b-a4b-it-20260403:free",
            "final_judge",
            "free-review-fleet",
            "google/gemma-4-31b-it-20260415:free",
        ),
        (
            "free-review-fleet",
            "nvidia/nemotron-3-nano-30b-a3b:free",
            "judge",
            "free-review-fleet",
            "nvidia/nemotron-3-super-120b-a12b:free",
        ),
    ],
)
def test_correlated_provider_families_are_not_independent(
    tmp_path,
    builder_fleet,
    builder_actual,
    reviewer_role,
    reviewer_fleet,
    reviewer_actual,
):
    root, run_id = _ready_run(tmp_path)
    _worker_event(root, run_id, "started", "builder", builder_fleet)
    _worker_event(
        root,
        run_id,
        "completed",
        "builder",
        builder_fleet,
        actual_model=builder_actual,
    )
    _worker_event(root, run_id, "started", reviewer_role, reviewer_fleet)
    _worker_event(
        root,
        run_id,
        "completed",
        reviewer_role,
        reviewer_fleet,
        actual_model=reviewer_actual,
    )

    report = evaluate_run_reliability(root, run_id)

    assert report.metrics["builder_reviewer_overlap"] == 1
    assert "builder/reviewer independence threshold exceeded" in report.breaches
    assert report.action == "rollback"


def test_legacy_receipt_requires_explicit_operator_confirmed_migration(tmp_path):
    run_id = create_pipeline_run(tmp_path, {"test": "legacy-receipt"})
    receipt_file = "verification-receipt-legacy.json"
    legacy_receipt = VerificationReceipt(
        run_id=run_id,
        receipt_id="legacy",
        status=VerificationStatus.passed,
        summary="pre-attestation receipt",
        created_at="",
    )
    update_pipeline_run_record(
        tmp_path,
        run_id,
        receipt_file,
        legacy_receipt.model_dump(mode="json"),
    )
    state = load_loop_state(tmp_path, run_id).model_copy(update={
        "stage": LoopStage.human_decision,
        "builder_judge_passed": True,
        "verification_receipts": [receipt_file],
    })
    save_loop_state(tmp_path, state)

    before = evaluate_run_reliability(tmp_path, run_id)
    assert before.safe is False
    assert before.action == "hold"
    assert "legacy receipt attestation missing" in before.breaches
    with pytest.raises(ValueError, match="explicit operator confirmation"):
        migrate_legacy_receipt_attestations(
            tmp_path,
            run_id,
            operator_confirmed=False,
            note="Reviewed legacy evidence.",
        )
    with pytest.raises(ValueError, match="explicit reliability migration"):
        record_verification_receipt(tmp_path, legacy_receipt)

    migration = migrate_legacy_receipt_attestations(
        tmp_path,
        run_id,
        operator_confirmed=True,
        note="Reviewed the pre-gate receipt against its original run evidence.",
    )

    assert migration["receipts"] == [receipt_file]
    assert evaluate_run_reliability(tmp_path, run_id).safe is True


def test_dead_owner_recovery_preserves_failure_and_allows_clean_retry(tmp_path):
    root, run_id = _ready_run(tmp_path)
    _worker_event(root, run_id, "started", "builder")
    update_execution_control(
        root,
        run_id,
        status="running",
        active_role="builder",
        owner_pid=999999,
    )

    before = evaluate_run_reliability(root, run_id)
    assert before.safe is False
    assert before.action == "hold"

    recover_interrupted_run(root, run_id, owner_alive=False)
    _worker_event(root, run_id, "started", "builder")
    _worker_event(
        root,
        run_id,
        "completed",
        "builder",
        actual_model="tencent/hy3-20260706:free",
    )

    after = evaluate_run_reliability(root, run_id)
    control = read_execution_control(root, run_id)
    assert after.safe is True
    assert after.metrics["provider_faults"] == 0
    assert control["status"] == "idle"
    assert control["recovered_after_restart"] is True


def test_live_owner_cannot_be_recovered(tmp_path):
    root, run_id = _ready_run(tmp_path)
    update_execution_control(
        root,
        run_id,
        status="running",
        active_role="builder",
        owner_pid=123,
    )

    with pytest.raises(ValueError, match="owner is still alive"):
        recover_interrupted_run(root, run_id, owner_alive=True)

    assert read_execution_control(root, run_id)["status"] == "running"
