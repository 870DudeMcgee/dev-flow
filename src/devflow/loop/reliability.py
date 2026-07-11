"""Deterministic reliability admission checks for one pipeline run.

This layer does not run models or choose routes. It verifies persisted runtime
evidence before final acceptance and provides one explicit dead-owner recovery
operation that preserves the interrupted call as failed evidence.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

from pydantic import BaseModel, Field

from devflow.loop.adapter import load_loop_state
from devflow.loop.pipeline_run import (
    append_worker_feed_entry,
    clear_worker_live_output,
    load_pipeline_run,
    pipeline_runs_dir,
    read_execution_control,
    update_execution_control,
    update_pipeline_run_record,
)
from devflow.loop.registry import get_registry


MODEL_ROLES = frozenset(
    {
        "brainstorm", "planner", "planning_judge", "builder", "judge",
        "verifier", "final_judge",
    }
)


class ReliabilityThresholds(BaseModel):
    """Production defaults that turn monitoring signals into rollback gates."""

    max_provider_faults: int = 2
    max_routing_drifts: int = 0
    max_concurrent_role_starts: int = 0
    max_replay_completions: int = 0
    max_unmatched_role_starts: int = 0
    max_provider_route_violations: int = 0
    max_builder_reviewer_overlap: int = 0
    max_missing_actual_models: int = 0


class ReliabilityReport(BaseModel):
    """Evidence-backed admission decision for one persisted run."""

    run_id: str
    safe: bool
    action: str
    breaches: list[str] = Field(default_factory=list)
    metrics: dict[str, int | str | bool] = Field(default_factory=dict)
    thresholds: ReliabilityThresholds = Field(default_factory=ReliabilityThresholds)
    recovery_actions: list[str] = Field(default_factory=list)


def _run_dir(root: Path | str, run_id: str) -> Path:
    runs_dir = pipeline_runs_dir(root).resolve()
    run_dir = (runs_dir / run_id).resolve()
    try:
        run_dir.relative_to(runs_dir)
    except ValueError as exc:
        raise ValueError("Pipeline run path escaped the runs directory.") from exc
    if not run_dir.is_dir():
        raise FileNotFoundError(f"Pipeline run not found: {run_id}")
    return run_dir


def _direct_file(run_dir: Path, file_name: str) -> Path:
    requested = Path(file_name)
    if requested.is_absolute() or requested.name != file_name:
        raise ValueError(f"Invalid pipeline evidence file: {file_name!r}")
    return run_dir / requested


def verification_attestation_name(receipt_file: str) -> str:
    prefix = "verification-receipt-"
    suffix = ".json"
    if not receipt_file.startswith(prefix) or not receipt_file.endswith(suffix):
        raise ValueError(f"Invalid verification receipt file: {receipt_file!r}")
    receipt_id = receipt_file[len(prefix):-len(suffix)]
    if not receipt_id or Path(receipt_id).name != receipt_id:
        raise ValueError(f"Invalid verification receipt file: {receipt_file!r}")
    return f"verification-attestation-{receipt_id}.json"


def attest_verification_receipt(
    root: Path | str,
    run_id: str,
    receipt_file: str,
) -> dict:
    """Write a deterministic SHA-256 attestation for a persisted receipt."""
    run_dir = _run_dir(root, run_id)
    receipt_path = _direct_file(run_dir, receipt_file)
    if not receipt_path.is_file():
        raise FileNotFoundError(f"Verification receipt not found: {receipt_file}")
    attestation = {
        "algorithm": "sha256",
        "digest": hashlib.sha256(receipt_path.read_bytes()).hexdigest(),
        "receipt_file": receipt_file,
        "run_id": run_id,
        "schema_version": 1,
    }
    update_pipeline_run_record(
        root,
        run_id,
        verification_attestation_name(receipt_file),
        attestation,
    )
    return attestation


def _receipt_integrity(
    root: Path | str,
    run_id: str,
    receipt_files: list[str],
) -> tuple[int, int, list[str], list[str]]:
    run_dir = _run_dir(root, run_id)
    valid = 0
    passing = 0
    failures: list[str] = []
    missing_attestations: list[str] = []
    for receipt_file in receipt_files:
        try:
            receipt_path = _direct_file(run_dir, receipt_file)
            attestation_path = _direct_file(
                run_dir, verification_attestation_name(receipt_file)
            )
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            if not attestation_path.is_file():
                missing_attestations.append(receipt_file)
                continue
            attestation = json.loads(attestation_path.read_text(encoding="utf-8"))
            digest = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
        except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError):
            failures.append(receipt_file)
            continue
        if not isinstance(receipt, dict) or not isinstance(attestation, dict):
            failures.append(receipt_file)
            continue
        if (
            attestation.get("algorithm") != "sha256"
            or attestation.get("digest") != digest
            or attestation.get("receipt_file") != receipt_file
            or attestation.get("run_id") != run_id
        ):
            failures.append(receipt_file)
            continue
        valid += 1
        if receipt.get("run_id") == run_id and receipt.get("status") == "passed":
            passing += 1
    return valid, passing, failures, missing_attestations


def _model_family(model_id: str) -> str:
    value = str(model_id or "").strip().lower()
    base, separator, suffix = value.partition(":")
    base = re.sub(r"-\d{8}$", "", base)
    if base.startswith("google/gemma-4-"):
        base = "google/gemma-4"
    elif base.startswith("nvidia/nemotron-3-"):
        base = "nvidia/nemotron-3"
    elif base.startswith("tencent/hy3"):
        base = "tencent/hy3"
    return f"{base}{separator}{suffix}" if separator else base


def _configured_model_family(model_name: str) -> tuple[set[str], str]:
    entry = get_registry().get(model_name)
    if entry is None:
        return set(), _model_family(model_name)
    allowed = {
        _model_family(model_id)
        for model_id in (entry.model_id, *entry.fallback_model_ids)
        if model_id
    }
    configured = _model_family(entry.model_id or entry.name)
    return allowed, configured


def _worker_metrics(feed: list[dict]) -> tuple[dict[str, int], list[dict]]:
    active: list[dict] = []
    first_model: dict[str, str] = {}
    metrics = {
        "provider_faults": 0,
        "routing_drifts": 0,
        "concurrent_role_starts": 0,
        "replay_completions": 0,
        "unmatched_role_starts": 0,
        "provider_route_violations": 0,
        "builder_reviewer_overlap": 0,
        "missing_actual_models": 0,
    }
    served_by_role: dict[str, set[str]] = {}
    for entry in feed:
        if not isinstance(entry, dict):
            continue
        role = str(entry.get("role") or "")
        event = str(entry.get("event") or "")
        model = str(entry.get("model") or "")
        if role not in MODEL_ROLES:
            continue
        if model == "deterministic-rules-engine":
            continue
        if event == "started":
            if active:
                metrics["concurrent_role_starts"] += 1
            active.append(entry)
            if role in first_model and model and model != first_model[role]:
                metrics["routing_drifts"] += 1
            elif model:
                first_model[role] = model
        elif event in {"completed", "failed", "cancelled"}:
            match = next(
                (index for index in range(len(active) - 1, -1, -1)
                 if active[index].get("role") == role),
                None,
            )
            if match is None:
                metrics["replay_completions"] += 1
            else:
                active.pop(match)
            if event == "failed" and entry.get("fault_kind") != "ownership_recovery":
                metrics["provider_faults"] += 1
            if event == "completed":
                usage = entry.get("usage") or {}
                actual_model = str(
                    (usage.get("actual_model") or "")
                    if isinstance(usage, dict) else ""
                )
                allowed, configured = _configured_model_family(model)
                registry_entry = get_registry().get(model)
                requires_actual_model = bool(
                    registry_entry
                    and registry_entry.cost_class == "free_cloud"
                    and registry_entry.transport == "openai-http"
                )
                if requires_actual_model and not actual_model:
                    metrics["missing_actual_models"] += 1
                    served = ""
                else:
                    served = _model_family(actual_model) if actual_model else configured
                if (
                    actual_model
                    and requires_actual_model
                    and (not allowed or served not in allowed)
                ):
                    metrics["provider_route_violations"] += 1
                if served:
                    served_by_role.setdefault(role, set()).add(served)
    metrics["unmatched_role_starts"] = len(active)
    builder_models = served_by_role.get("builder", set())
    reviewer_models = set().union(*(
        served_by_role.get(role, set())
        for role in ("planning_judge", "judge", "verifier", "final_judge")
    ))
    metrics["builder_reviewer_overlap"] = len(builder_models & reviewer_models)
    return metrics, active


def evaluate_run_reliability(
    root: Path | str,
    run_id: str,
    *,
    thresholds: ReliabilityThresholds | None = None,
) -> ReliabilityReport:
    """Fail closed when persisted ownership, routing, or evidence is unsafe."""
    thresholds = thresholds or ReliabilityThresholds()
    state = load_loop_state(root, run_id)
    control = read_execution_control(root, run_id)
    breaches: list[str] = []
    recovery_actions: list[str] = []
    try:
        data = load_pipeline_run(root, run_id)
        feed = data.get("worker-feed.jsonl") or []
        if not isinstance(feed, list):
            raise ValueError("worker feed is not a list")
    except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError):
        feed = []
        breaches.append("pipeline evidence is unreadable")

    worker_metrics, _active = _worker_metrics(feed)
    (
        valid_receipts,
        passing_receipts,
        integrity_failures,
        missing_attestations,
    ) = _receipt_integrity(
        root, run_id, list(state.verification_receipts)
    )
    execution_status = str(control.get("status") or "idle")
    active_owner = bool(
        control.get("active_role")
        or execution_status in {"running", "cancelling", "stalled"}
    )
    if active_owner:
        breaches.append("run ownership is still active or unresolved")
        recovery_actions.append("Validate the recorded owner before restart recovery.")
    if integrity_failures:
        breaches.append("verification receipt integrity failed")
        recovery_actions.append("Rollback and regenerate verification evidence.")
    if missing_attestations:
        breaches.append("legacy receipt attestation missing")
        recovery_actions.append(
            "Use the explicit operator-confirmed legacy receipt migration before acceptance."
        )
    if not state.verification_receipts or passing_receipts == 0:
        breaches.append("no integrity-verified passing verification receipt")
        recovery_actions.append("Run verification again before acceptance.")

    threshold_checks = (
        ("provider_faults", thresholds.max_provider_faults, "provider fault threshold exceeded"),
        ("routing_drifts", thresholds.max_routing_drifts, "routing drift threshold exceeded"),
        (
            "concurrent_role_starts",
            thresholds.max_concurrent_role_starts,
            "concurrent role ownership threshold exceeded",
        ),
        (
            "replay_completions",
            thresholds.max_replay_completions,
            "replayed completion threshold exceeded",
        ),
        (
            "unmatched_role_starts",
            thresholds.max_unmatched_role_starts,
            "unmatched role start threshold exceeded",
        ),
        (
            "provider_route_violations",
            thresholds.max_provider_route_violations,
            "provider actual-model route threshold exceeded",
        ),
        (
            "builder_reviewer_overlap",
            thresholds.max_builder_reviewer_overlap,
            "builder/reviewer independence threshold exceeded",
        ),
        (
            "missing_actual_models",
            thresholds.max_missing_actual_models,
            "provider actual-model evidence is missing",
        ),
    )
    for metric, limit, message in threshold_checks:
        if worker_metrics[metric] > limit:
            breaches.append(message)
    rollback_markers = (
        "verification receipt integrity failed",
        "routing drift",
        "concurrent role",
        "replayed completion",
        "provider fault",
        "provider actual-model",
        "builder/reviewer",
    )
    rollback = any(
        any(marker in breach for marker in rollback_markers)
        for breach in breaches
    )
    if rollback:
        recovery_actions.append("Rollback to the last accepted source state.")
    metrics: dict[str, int | str | bool] = {
        **worker_metrics,
        "active_owner": active_owner,
        "execution_status": execution_status,
        "passing_receipts": passing_receipts,
        "valid_receipts": valid_receipts,
    }
    return ReliabilityReport(
        run_id=run_id,
        safe=not breaches,
        action="proceed" if not breaches else ("rollback" if rollback else "hold"),
        breaches=breaches,
        metrics=metrics,
        thresholds=thresholds,
        recovery_actions=list(dict.fromkeys(recovery_actions)),
    )


def record_reliability_report(
    root: Path | str,
    run_id: str,
    *,
    thresholds: ReliabilityThresholds | None = None,
) -> ReliabilityReport:
    report = evaluate_run_reliability(root, run_id, thresholds=thresholds)
    update_pipeline_run_record(
        root,
        run_id,
        "reliability-report.json",
        report.model_dump(mode="json"),
    )
    return report


def migrate_legacy_receipt_attestations(
    root: Path | str,
    run_id: str,
    *,
    operator_confirmed: bool,
    note: str,
) -> dict:
    """Explicit compatibility path for receipts created before attestations."""
    if not operator_confirmed:
        raise ValueError("Legacy receipt migration requires explicit operator confirmation.")
    if not note.strip():
        raise ValueError("Legacy receipt migration requires an audit note.")
    state = load_loop_state(root, run_id)
    run_dir = _run_dir(root, run_id)
    migrated: list[str] = []
    for receipt_file in state.verification_receipts:
        attestation_file = verification_attestation_name(receipt_file)
        if _direct_file(run_dir, attestation_file).is_file():
            continue
        attest_verification_receipt(root, run_id, receipt_file)
        migrated.append(receipt_file)
    record = {
        "operator_confirmed": True,
        "note": note.strip(),
        "policy": "legacy-receipt-local-attestation-v1",
        "receipts": migrated,
        "run_id": run_id,
    }
    update_pipeline_run_record(
        root, run_id, "reliability-migration.json", record
    )
    return record


def _pid_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def recover_interrupted_run(
    root: Path | str,
    run_id: str,
    *,
    owner_alive: bool | None = None,
) -> dict:
    """Close dead-owner calls as failed evidence, then release run ownership."""
    control = read_execution_control(root, run_id)
    pid = int(control.get("owner_pid") or control.get("pid") or 0)
    if owner_alive is None:
        if pid <= 0:
            raise ValueError("Cannot recover ownership without a validated owner PID.")
        owner_alive = _pid_is_alive(pid)
    if owner_alive:
        raise ValueError("Cannot recover while the recorded owner is still alive.")
    data = load_pipeline_run(root, run_id)
    feed = data.get("worker-feed.jsonl") or []
    _metrics, active = _worker_metrics(feed if isinstance(feed, list) else [])
    for entry in active:
        append_worker_feed_entry(root, run_id, {
            "event": "failed",
            "role": entry.get("role") or "worker",
            "model": entry.get("model") or "unknown",
            "fault_kind": "ownership_recovery",
            "content": json.dumps({
                "status": "needs_review",
                "reason": "Recorded owner ended before this role produced a terminal event.",
                "recovered_after_restart": True,
            }),
        })
    clear_worker_live_output(root, run_id)
    return update_execution_control(
        root,
        run_id,
        status="idle",
        active_role=None,
        recovered_after_restart=True,
        recovered_owner_pid=pid or None,
    )


__all__ = [
    "ReliabilityReport",
    "ReliabilityThresholds",
    "attest_verification_receipt",
    "evaluate_run_reliability",
    "migrate_legacy_receipt_attestations",
    "record_reliability_report",
    "recover_interrupted_run",
    "verification_attestation_name",
]
