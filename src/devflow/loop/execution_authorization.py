"""Deterministic execution authorization after all Phase 3 host gates."""

from __future__ import annotations

import json
import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from devflow.loop.execution_plan import execution_plan_hash, load_execution_plan
from devflow.loop.packet_dag import PacketState, ready_packet_ids, validate_packet_dag
from devflow.loop.pipeline_run import pipeline_runs_dir
from devflow.loop.source_snapshot import (
    SnapshotError,
    SnapshotReceipt,
    load_source_snapshot_receipt,
)
from devflow.loop.validator_service import (
    ValidatorOutcome,
    ValidatorReceipt,
    load_validator_receipt,
)


_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]*$"


class ExecutionAuthorizationReceipt(BaseModel):
    """Immutable host verdict binding every required Phase 3 gate."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    authorization_id: str = Field(pattern=_ID_PATTERN)
    run_id: str = Field(pattern=_ID_PATTERN)
    snapshot_id: str = Field(pattern=_ID_PATTERN)
    snapshot_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    snapshot_commit: str = Field(pattern=r"^[0-9a-f]{40,64}$")
    execution_plan_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    packet_ids: tuple[str, ...]
    ready_packet_ids: tuple[str, ...]
    validator_receipt_ids: tuple[str, ...]
    authorized: bool = True

    @model_validator(mode="after")
    def require_authorized_verdict(self) -> "ExecutionAuthorizationReceipt":
        if not self.authorized:
            raise ValueError("execution authorization receipt cannot encode a denial")
        if not self.packet_ids or not self.ready_packet_ids:
            raise ValueError("execution authorization requires a nonempty packet DAG and ready set")
        return self


def _run_dir(root: Path | str, run_id: str) -> Path:
    runs = pipeline_runs_dir(root).resolve()
    run_dir = (runs / run_id).resolve()
    try:
        run_dir.relative_to(runs)
    except ValueError as exc:
        raise ValueError("execution authorization run escapes pipeline runs") from exc
    if not run_dir.is_dir():
        raise ValueError(f"execution authorization run {run_id!r} does not exist")
    return run_dir


def _authorization_path(root: Path | str, run_id: str, authorization_id: str) -> Path:
    if not authorization_id or any(
        char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
        for char in authorization_id
    ):
        raise ValueError("invalid execution authorization id")
    return _run_dir(root, run_id) / "execution-authorizations" / f"{authorization_id}.json"


def _load_snapshot(root: Path | str, run_id: str, snapshot_id: str) -> SnapshotReceipt:
    try:
        return load_source_snapshot_receipt(root, run_id, snapshot_id)
    except SnapshotError as exc:
        raise ValueError(
            f"source snapshot receipt {snapshot_id!r} is missing or corrupt"
        ) from exc


def load_execution_authorization(
    root: Path | str, run_id: str, authorization_id: str
) -> ExecutionAuthorizationReceipt:
    """Load one immutable execution authorization receipt."""

    path = _authorization_path(root, run_id, authorization_id)
    try:
        receipt = ExecutionAuthorizationReceipt.model_validate_json(
            path.read_text(encoding="utf-8")
        )
    except (OSError, ValueError) as exc:
        raise ValueError(
            f"execution authorization {authorization_id!r} is missing or corrupt"
        ) from exc
    if receipt.authorization_id != authorization_id or receipt.run_id != run_id:
        raise ValueError("execution authorization receipt does not match its path")
    return receipt


def _persist_authorization(
    root: Path | str, receipt: ExecutionAuthorizationReceipt
) -> ExecutionAuthorizationReceipt:
    path = _authorization_path(root, receipt.run_id, receipt.authorization_id)
    path.parent.mkdir(mode=0o755, exist_ok=True)
    payload = (
        json.dumps(receipt.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
    except FileExistsError:
        existing = load_execution_authorization(
            root, receipt.run_id, receipt.authorization_id
        )
        if existing == receipt:
            return existing
        raise ValueError(
            f"conflicting execution authorization: {receipt.authorization_id}"
        ) from None
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return receipt


def authorize_execution(
    root: Path | str,
    run_id: str,
    *,
    authorization_id: str,
    snapshot_id: str,
    validator_receipt_ids: list[str],
) -> ExecutionAuthorizationReceipt:
    """Authorize only when snapshot, plan, DAG, and validators match exactly."""

    existing_path = _authorization_path(root, run_id, authorization_id)
    if existing_path.exists():
        existing = load_execution_authorization(root, run_id, authorization_id)
        if (
            existing.snapshot_id != snapshot_id
            or existing.validator_receipt_ids != tuple(validator_receipt_ids)
        ):
            raise ValueError(f"conflicting execution authorization: {authorization_id}")

    plan = load_execution_plan(root, run_id)
    plan_hash = execution_plan_hash(plan)
    snapshot = _load_snapshot(root, run_id, snapshot_id)
    if snapshot.plan_hash != plan_hash:
        raise ValueError("source snapshot is stale for the approved execution plan")
    if snapshot.selected_paths != plan.target_files:
        raise ValueError("source snapshot paths do not exactly match the approved plan")

    packets = validate_packet_dag(plan.packets)
    states = {packet.id: PacketState.pending for packet in packets}
    ready = ready_packet_ids(packets, states)

    if len(validator_receipt_ids) != len(set(validator_receipt_ids)):
        raise ValueError("validator receipt ids must be unique")
    loaded = [
        load_validator_receipt(root, run_id, receipt_id)
        for receipt_id in validator_receipt_ids
    ]
    by_validator: dict[str, ValidatorReceipt] = {}
    for receipt in loaded:
        validator_id = receipt.validator.id
        if validator_id in by_validator:
            raise ValueError(f"duplicate validator evidence for {validator_id!r}")
        by_validator[validator_id] = receipt
    required_ids = {validator.id for validator in plan.validators}
    if set(by_validator) != required_ids:
        raise ValueError("validator receipts do not exactly cover plan validators")

    ordered_receipt_ids: list[str] = []
    for validator in plan.validators:
        receipt = by_validator[validator.id]
        if receipt.run_id != run_id:
            raise ValueError("validator receipt belongs to the wrong run")
        if receipt.snapshot_fingerprint != snapshot.fingerprint:
            raise ValueError("validator receipt is stale for the source snapshot")
        if receipt.execution_plan_hash != plan_hash:
            raise ValueError("validator receipt is stale for the execution plan")
        if receipt.validator != validator:
            raise ValueError("validator receipt declaration does not match the plan")
        if receipt.outcome is not ValidatorOutcome.passed or not receipt.passed:
            raise ValueError(f"validator {validator.id!r} did not pass")
        ordered_receipt_ids.append(receipt.receipt_id)

    result = ExecutionAuthorizationReceipt(
        authorization_id=authorization_id,
        run_id=run_id,
        snapshot_id=snapshot.snapshot_id,
        snapshot_fingerprint=snapshot.fingerprint,
        snapshot_commit=snapshot.commit,
        execution_plan_hash=plan_hash,
        packet_ids=tuple(packet.id for packet in packets),
        ready_packet_ids=ready,
        validator_receipt_ids=tuple(ordered_receipt_ids),
    )
    if existing_path.exists():
        existing = load_execution_authorization(root, run_id, authorization_id)
        if existing != result:
            raise ValueError(f"conflicting execution authorization: {authorization_id}")
        return existing
    return _persist_authorization(root, result)


__all__ = [
    "ExecutionAuthorizationReceipt",
    "authorize_execution",
    "load_execution_authorization",
]
