"""Immutable packet patches and deterministic Phase 5 integration.

The host captures successful packet worktrees as binary-safe immutable patches,
applies those patches once in dependency order to the Phase 4 integration
worktree, runs the approved typed validators, and records a separately-routed
read-only verification receipt.  All authoritative state is run-scoped,
append-only or immutable, and replayable after restart.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from devflow.loop.execution_plan import execution_plan_hash, load_execution_plan
from devflow.loop.git_sandbox import (
    SandboxKind,
    SandboxRequest,
    create_sandbox,
    load_sandbox_receipt,
)
from devflow.loop.pipeline_run import pipeline_runs_dir
from devflow.loop.run_advancement import ClaimState, load_advancement_snapshot
from devflow.loop.source_snapshot import load_source_snapshot_receipt
from devflow.loop.validator_service import (
    ValidatorRequest,
    load_validator_receipt,
    run_validator,
)
from devflow.loop.workflow_ledger import (
    EvidenceReference,
    NodeReceipt,
    WorkflowEvent,
    record_node_outcome,
    replay_workflow_run,
)

_ID = r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"
_SHA256 = r"^[0-9a-f]{64}$"
_GIT_SHA = r"^[0-9a-f]{40,64}$"
_PATCH_LIMIT = 16 * 1024 * 1024
_OUTPUT_LIMIT = 64_000


class IntegrationError(ValueError):
    """Fail-closed Phase 5 validation error."""


class IntegrationStatus(str, Enum):
    awaiting_verification = "awaiting_verification"
    conflict = "conflict"
    validator_failed = "validator_failed"


class PatchCaptureCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    command_id: str = Field(pattern=_ID)
    run_id: str = Field(pattern=_ID)
    packet_id: str = Field(pattern=_ID)
    claim_id: str = Field(pattern=_ID)
    attempt_id: str = Field(pattern=_ID)
    owner_id: str = Field(pattern=_ID)
    route: str = Field(pattern=_ID)
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    model_family: str = Field(min_length=1)
    max_patch_bytes: int = Field(default=_PATCH_LIMIT, ge=1, le=_PATCH_LIMIT)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PacketPatchReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    receipt_id: str = Field(pattern=_ID)
    command_id: str = Field(pattern=_ID)
    sequence: int = Field(ge=1)
    run_id: str = Field(pattern=_ID)
    packet_id: str = Field(pattern=_ID)
    claim_id: str = Field(pattern=_ID)
    attempt_id: str = Field(pattern=_ID)
    owner_id: str = Field(pattern=_ID)
    route: str
    provider: str
    model: str
    model_family: str
    authorization_id: str = Field(pattern=_ID)
    sandbox_id: str = Field(pattern=_ID)
    sandbox_receipt_id: str = Field(pattern=_ID)
    snapshot_commit: str = Field(pattern=_GIT_SHA)
    snapshot_fingerprint: str = Field(pattern=_SHA256)
    execution_plan_hash: str = Field(pattern=_SHA256)
    base_tree: str = Field(pattern=_GIT_SHA)
    result_tree: str = Field(pattern=_GIT_SHA)
    target_files: tuple[str, ...]
    changed_paths: tuple[str, ...]
    patch_path: str
    patch_sha256: str = Field(pattern=_SHA256)
    patch_bytes: int = Field(ge=1)
    captured_at: datetime


class IntegrationCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    command_id: str = Field(pattern=_ID)
    run_id: str = Field(pattern=_ID)
    integration_id: str = Field(pattern=_ID)
    authorization_id: str = Field(pattern=_ID)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    timeout_seconds: int = Field(default=120, ge=1, le=600)
    max_output_bytes: int = Field(default=_OUTPUT_LIMIT, ge=1024, le=_OUTPUT_LIMIT)
    max_sandboxes: int = Field(default=64, ge=1, le=64)


class ConflictReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    conflict_id: str = Field(pattern=_ID)
    run_id: str = Field(pattern=_ID)
    integration_id: str = Field(pattern=_ID)
    command_id: str = Field(pattern=_ID)
    packet_id: str = Field(pattern=_ID)
    patch_receipt_id: str = Field(pattern=_ID)
    patch_sha256: str = Field(pattern=_SHA256)
    order_index: int = Field(ge=0)
    base_commit: str = Field(pattern=_GIT_SHA)
    current_head: str = Field(pattern=_GIT_SHA)
    current_tree: str = Field(pattern=_GIT_SHA)
    conflicting_paths: tuple[str, ...]
    git_stderr: str
    created_at: datetime


class IntegrationRepairCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    command_id: str = Field(pattern=_ID)
    run_id: str = Field(pattern=_ID)
    integration_id: str = Field(pattern=_ID)
    conflict_id: str = Field(pattern=_ID)
    owner_id: str = Field(pattern=_ID)
    route: str = Field(pattern=_ID)
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    model_family: str = Field(min_length=1)
    evidence_reference: str = Field(min_length=1)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    max_attempts: int = Field(default=3, ge=1, le=3)


class IntegrationRepairReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    repair_id: str = Field(pattern=_ID)
    command_id: str = Field(pattern=_ID)
    run_id: str = Field(pattern=_ID)
    integration_id: str = Field(pattern=_ID)
    conflict_id: str = Field(pattern=_ID)
    packet_id: str = Field(pattern=_ID)
    attempt_number: int = Field(ge=1, le=3)
    owner_id: str
    route: str
    provider: str
    model: str
    model_family: str
    evidence_reference: str
    changed_paths: tuple[str, ...]
    head: str = Field(pattern=_GIT_SHA)
    tree: str = Field(pattern=_GIT_SHA)
    recorded_at: datetime


class IntegrationSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str = Field(pattern=_ID)
    integration_id: str | None = None
    sandbox_id: str | None = None
    base_commit: str | None = None
    integration_order: tuple[str, ...] = ()
    applied_packet_ids: tuple[str, ...] = ()
    patch_hashes: tuple[str, ...] = ()
    head: str | None = None
    tree: str | None = None
    fingerprint: str | None = None
    conflict_id: str | None = None
    repair_model_families: tuple[str, ...] = ()
    event_sequence: int = Field(default=0, ge=0)


class IntegrationOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    command_id: str = Field(pattern=_ID)
    run_id: str = Field(pattern=_ID)
    integration_id: str = Field(pattern=_ID)
    status: IntegrationStatus
    applied_packet_ids: tuple[str, ...]
    validator_receipt_ids: tuple[str, ...] = ()
    conflict_id: str | None = None
    head: str = Field(pattern=_GIT_SHA)
    tree: str = Field(pattern=_GIT_SHA)
    fingerprint: str = Field(pattern=_SHA256)
    decided_at: datetime


class IntegrationVerificationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    receipt_id: str = Field(pattern=_ID)
    run_id: str = Field(pattern=_ID)
    integration_id: str = Field(pattern=_ID)
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    model_family: str = Field(min_length=1)
    route: str = Field(min_length=1)
    verdict: Literal["pass", "fail"]
    findings: tuple[str, ...] = ()
    definition_of_done_sha256: str = Field(pattern=_SHA256)
    reviewed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class IntegrationVerificationReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    receipt_id: str = Field(pattern=_ID)
    run_id: str = Field(pattern=_ID)
    integration_id: str = Field(pattern=_ID)
    provider: str
    model: str
    model_family: str
    route: str
    independent_from_model_families: tuple[str, ...]
    head: str = Field(pattern=_GIT_SHA)
    tree: str = Field(pattern=_GIT_SHA)
    fingerprint: str = Field(pattern=_SHA256)
    patch_receipt_ids: tuple[str, ...]
    patch_hashes: tuple[str, ...]
    validator_receipt_ids: tuple[str, ...]
    definition_of_done_sha256: str = Field(pattern=_SHA256)
    findings: tuple[str, ...]
    verdict: Literal["pass", "fail"]
    reviewed_at: datetime


# ---------------------------------------------------------------------------
# Filesystem and Git helpers
# ---------------------------------------------------------------------------
def _run_dir(root: Path | str, run_id: str) -> Path:
    runs = pipeline_runs_dir(root).resolve()
    target = (runs / run_id).resolve()
    try:
        target.relative_to(runs)
    except ValueError as exc:
        raise IntegrationError("run id escapes pipeline runs") from exc
    if not target.is_dir():
        raise IntegrationError(f"pipeline run {run_id!r} does not exist")
    return target


def _safe_id(value: str) -> str:
    if not value or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-" for c in value):
        raise IntegrationError("unsafe record id")
    return value


def _record_path(root: Path | str, run_id: str, directory: str, record_id: str, suffix: str = ".json") -> Path:
    _safe_id(record_id)
    run_dir = _run_dir(root, run_id)
    parent = (run_dir / directory).resolve()
    target = (parent / f"{record_id}{suffix}").resolve()
    if target.parent != parent:
        raise IntegrationError("record path escapes its store")
    return target


def _persist_bytes(path: Path, data: bytes, mode: int = 0o444) -> bool:
    path.parent.mkdir(mode=0o755, exist_ok=True)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    except FileExistsError:
        return False
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return True


def _persist_model(path: Path, model: BaseModel) -> bool:
    return _persist_bytes(path, (json.dumps(model.model_dump(mode="json"), indent=2, sort_keys=True) + "\n").encode())


def _load_model(path: Path, model_type, *, label: str):
    try:
        return model_type.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise IntegrationError(f"{label} is missing or corrupt") from exc


def _git(repo: Path, *args: str, timeout: int = 120, env: dict[str, str] | None = None, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    try:
        result = subprocess.run(
            ["git", *args], cwd=repo, shell=False, capture_output=True,
            timeout=timeout, env=env,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise IntegrationError(f"git {args[0] if args else ''} could not complete: {exc}") from exc
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout)[-_OUTPUT_LIMIT:].decode("utf-8", "replace")
        raise IntegrationError(f"git {' '.join(args[:2])} failed: {detail.strip()}")
    return result


def _git_text(repo: Path, *args: str, **kwargs) -> str:
    return _git(repo, *args, **kwargs).stdout.decode("utf-8", "strict").strip()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _fingerprint(*, head: str, tree: str, applied: tuple[str, ...], hashes: tuple[str, ...], validators: tuple[str, ...] = ()) -> str:
    payload = json.dumps({"head": head, "tree": tree, "applied": applied, "patch_hashes": hashes, "validators": validators}, sort_keys=True, separators=(",", ":")).encode()
    return _sha256(payload)


def _topological_order(plan) -> tuple[str, ...]:
    by_id = {packet.id: packet for packet in plan.packets}
    pending = set(by_id)
    done: list[str] = []
    while pending:
        ready = sorted(packet_id for packet_id in pending if set(by_id[packet_id].depends_on) <= set(done))
        if not ready:
            raise IntegrationError("packet dependency graph cannot be ordered")
        done.extend(ready)
        pending.difference_update(ready)
    return tuple(done)


def _status_paths(worktree: Path) -> tuple[str, ...]:
    raw = _git(worktree, "status", "--porcelain=v1", "-z", "--untracked-files=all").stdout
    paths: list[str] = []
    entries = raw.split(b"\0")
    index = 0
    while index < len(entries):
        entry = entries[index]
        index += 1
        if not entry:
            continue
        text = entry.decode("utf-8", "surrogateescape")
        status = text[:2]
        value = text[3:]
        if status[0] in "RC" and index < len(entries):
            value = entries[index].decode("utf-8", "surrogateescape")
            index += 1
        paths.append(value)
    return tuple(sorted(set(paths)))


def _safe_relative_path(value: str) -> str:
    path = PurePosixPath(value)
    if not value or path.is_absolute() or ".." in path.parts or "\\" in value:
        raise IntegrationError(f"unsafe patch path: {value!r}")
    return value


def _tree_from_worktree(worktree: Path, targets: tuple[str, ...]) -> str:
    with tempfile.NamedTemporaryFile(prefix="devflow-index-", delete=False) as handle:
        index_path = Path(handle.name)
    index_path.unlink(missing_ok=True)
    env = dict(os.environ)
    env["GIT_INDEX_FILE"] = str(index_path)
    try:
        _git(worktree, "read-tree", "HEAD", env=env)
        _git(worktree, "add", "--all", "--", *targets, env=env)
        return _git_text(worktree, "write-tree", env=env)
    finally:
        index_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Packet patch capture
# ---------------------------------------------------------------------------
def save_patch_capture_command(root: Path | str, command: PatchCaptureCommand) -> PatchCaptureCommand:
    path = _record_path(root, command.run_id, "packet-patch-commands", command.command_id)
    if path.exists():
        existing = _load_model(path, PatchCaptureCommand, label="patch capture command")
        if existing == command:
            return existing
        raise IntegrationError("conflicting patch capture command; original preserved")
    if not _persist_model(path, command):
        return save_patch_capture_command(root, command)
    return command


def load_packet_patch_receipt(root: Path | str, run_id: str, packet_id: str) -> PacketPatchReceipt:
    path = _record_path(root, run_id, "packet-patch-receipts", packet_id)
    receipt = _load_model(path, PacketPatchReceipt, label=f"packet patch receipt {packet_id!r}")
    if receipt.run_id != run_id or receipt.packet_id != packet_id:
        raise IntegrationError("packet patch receipt does not match its path")
    return receipt


def capture_packet_patch(root: Path | str, repo: Path | str, run_id: str, command_id: str) -> PacketPatchReceipt:
    repo_path = Path(repo).resolve()
    command_path = _record_path(root, run_id, "packet-patch-commands", command_id)
    command = _load_model(command_path, PatchCaptureCommand, label="patch capture command")
    if command.run_id != run_id or command.command_id != command_id:
        raise IntegrationError("patch capture command does not match its path")
    receipt_path = _record_path(root, run_id, "packet-patch-receipts", command.packet_id)
    if receipt_path.exists():
        existing = load_packet_patch_receipt(root, run_id, command.packet_id)
        if existing.command_id == command_id:
            patch = (_run_dir(root, run_id) / existing.patch_path).read_bytes()
            if _sha256(patch) != existing.patch_sha256:
                raise IntegrationError("immutable packet patch bytes do not match receipt")
            return existing
        raise IntegrationError("packet already has a conflicting immutable patch receipt")

    lock_path = _run_dir(root, run_id) / ".packet-patches.lock"
    with lock_path.open("a+b") as lock_handle:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
        try:
            if receipt_path.exists():
                existing = load_packet_patch_receipt(root, run_id, command.packet_id)
                if existing.command_id != command_id:
                    raise IntegrationError(
                        "packet already has a conflicting immutable patch receipt"
                    )
                patch = (_run_dir(root, run_id) / existing.patch_path).read_bytes()
                if _sha256(patch) != existing.patch_sha256:
                    raise IntegrationError(
                        "immutable packet patch bytes do not match receipt"
                    )
                return existing
            plan = load_execution_plan(root, run_id)
            packet = next((item for item in plan.packets if item.id == command.packet_id), None)
            if packet is None:
                raise IntegrationError("patch command packet is outside the approved plan")
            snapshot = load_advancement_snapshot(root, run_id)
            claim = next((item for item in snapshot.claims if item.claim_id == command.claim_id), None)
            attempt = next((item for item in snapshot.attempts if item.attempt_id == command.attempt_id), None)
            if claim is None or attempt is None:
                raise IntegrationError("patch capture claim or attempt is missing")
            if claim.state is not ClaimState.completed:
                raise IntegrationError("only a successfully completed packet attempt may be captured")
            if (claim.run_id, claim.packet_id, claim.attempt_id, claim.owner_id) != (run_id, command.packet_id, command.attempt_id, command.owner_id):
                raise IntegrationError("stale owner or wrong claim/attempt binding")
            if (attempt.claim_id, attempt.packet_id, attempt.owner_id, attempt.route) != (claim.claim_id, command.packet_id, command.owner_id, command.route):
                raise IntegrationError("attempt owner/route binding does not match capture command")
            sandbox = load_sandbox_receipt(root, run_id, attempt.sandbox_id)
            if sandbox.kind is not SandboxKind.packet or sandbox.packet_id != command.packet_id:
                raise IntegrationError("packet sandbox receipt does not match the attempt")
            worktree = Path(sandbox.path).resolve()
            if not worktree.is_dir() or _git_text(worktree, "rev-parse", "HEAD") != sandbox.snapshot_commit:
                raise IntegrationError("packet sandbox is missing or at the wrong snapshot")
            source = load_source_snapshot_receipt(root, run_id, _authorization_snapshot_id(root, run_id, sandbox.authorization_id))
            if source.commit != sandbox.snapshot_commit or source.fingerprint == "":
                raise IntegrationError("packet sandbox snapshot binding is stale")
            changed = _status_paths(worktree)
            if not changed:
                raise IntegrationError("successful packet has no patch content")
            targets = tuple(_safe_relative_path(path) for path in packet.target_files)
            unexpected = set(changed) - set(targets)
            if unexpected:
                raise IntegrationError(f"packet changed paths outside approved targets: {sorted(unexpected)!r}")
            sensitive = [path for path in changed if Path(path).name.startswith(".env") or any(part in {".git", ".devflow"} for part in PurePosixPath(path).parts)]
            if sensitive:
                raise IntegrationError(f"sensitive or internal patch paths are forbidden: {sensitive!r}")
            for path in changed:
                candidate = worktree / path
                if candidate.is_symlink():
                    raise IntegrationError(f"symlink patch path is forbidden: {path!r}")
                ignored = _git(worktree, "check-ignore", "-q", "--", path, check=False)
                if ignored.returncode == 0:
                    raise IntegrationError(f"ignored patch path is forbidden: {path!r}")
            patch = _git(worktree, "diff", "--binary", "--full-index", "--no-ext-diff", sandbox.snapshot_commit, "--", *targets).stdout
            if not patch:
                raise IntegrationError("packet patch is empty")
            if len(patch) > command.max_patch_bytes:
                raise IntegrationError("packet patch exceeds the configured size limit")
            patch_hash = _sha256(patch)
            patch_rel = f"packet-patches/{command.packet_id}-{patch_hash}.patch"
            patch_path = _run_dir(root, run_id) / patch_rel
            if not _persist_bytes(patch_path, patch):
                if patch_path.read_bytes() != patch:
                    raise IntegrationError("conflicting immutable packet patch artifact")
            existing_receipts = (_run_dir(root, run_id) / "packet-patch-receipts")
            sequence = 1 + (len(list(existing_receipts.glob("*.json"))) if existing_receipts.is_dir() else 0)
            receipt = PacketPatchReceipt(
                receipt_id=f"patch-{command.packet_id}", command_id=command.command_id,
                sequence=sequence, run_id=run_id, packet_id=command.packet_id,
                claim_id=command.claim_id, attempt_id=command.attempt_id,
                owner_id=command.owner_id, route=command.route, provider=command.provider,
                model=command.model, model_family=command.model_family,
                authorization_id=sandbox.authorization_id, sandbox_id=sandbox.sandbox_id,
                sandbox_receipt_id=sandbox.sandbox_id, snapshot_commit=sandbox.snapshot_commit,
                snapshot_fingerprint=source.fingerprint, execution_plan_hash=sandbox.execution_plan_hash,
                base_tree=_git_text(repo_path, "rev-parse", f"{sandbox.snapshot_commit}^{{tree}}"),
                result_tree=_tree_from_worktree(worktree, targets), target_files=targets,
                changed_paths=changed, patch_path=patch_rel, patch_sha256=patch_hash,
                patch_bytes=len(patch), captured_at=command.created_at,
            )
            if not _persist_model(receipt_path, receipt):
                existing = load_packet_patch_receipt(root, run_id, command.packet_id)
                if existing != receipt:
                    raise IntegrationError("conflicting packet patch receipt; original preserved")
                return existing
            return receipt
        finally:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)


def _authorization_snapshot_id(root: Path | str, run_id: str, authorization_id: str) -> str:
    from devflow.loop.execution_authorization import load_execution_authorization
    return load_execution_authorization(root, run_id, authorization_id).snapshot_id


# ---------------------------------------------------------------------------
# Integration command/event replay
# ---------------------------------------------------------------------------
def save_integration_command(root: Path | str, command: IntegrationCommand) -> IntegrationCommand:
    path = _record_path(root, command.run_id, "integration-commands", command.command_id)
    if path.exists():
        existing = _load_model(path, IntegrationCommand, label="integration command")
        if existing == command:
            return existing
        raise IntegrationError("conflicting integration command; original preserved")
    if not _persist_model(path, command):
        return save_integration_command(root, command)
    return command


def _events_path(root: Path | str, run_id: str) -> Path:
    return _run_dir(root, run_id) / "integration-events.jsonl"


def _append_event(root: Path | str, run_id: str, sequence: int, kind: str, command_id: str, **fields) -> None:
    event = {"event_id": f"int-{sequence:06d}", "sequence": sequence, "kind": kind, "command_id": command_id, **fields}
    path = _events_path(root, run_id)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def load_integration_snapshot(root: Path | str, run_id: str) -> IntegrationSnapshot:
    path = _events_path(root, run_id)
    if not path.is_file():
        return IntegrationSnapshot(run_id=run_id)
    integration_id = sandbox_id = base_commit = head = tree = fingerprint = conflict_id = None
    order: tuple[str, ...] = ()
    applied: list[str] = []
    hashes: list[str] = []
    repair_families: list[str] = []
    event_count = 0
    for sequence, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
        event_count = sequence + 1
        if not line.strip():
            raise IntegrationError(f"integration event line {sequence + 1} is empty")
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise IntegrationError(f"integration event line {sequence + 1} is corrupt") from exc
        if event.get("event_id") != f"int-{sequence:06d}" or event.get("sequence") != sequence:
            raise IntegrationError("integration event sequence is missing, duplicate, or reordered")
        kind = event.get("kind")
        if kind == "integration.started":
            if integration_id is not None:
                raise IntegrationError("duplicate integration start event")
            integration_id, sandbox_id, base_commit = event["integration_id"], event["sandbox_id"], event["base_commit"]
            order = tuple(event["integration_order"])
            head, tree, fingerprint = event["head"], event["tree"], event["fingerprint"]
        elif kind in {"patch.applied", "repair.applied"}:
            packet_id = event["packet_id"]
            if packet_id in applied:
                raise IntegrationError("packet patch was applied more than once")
            expected = order[len(applied)] if len(applied) < len(order) else None
            if packet_id != expected:
                raise IntegrationError("packet patch application order violates the DAG")
            applied.append(packet_id)
            hashes.append(event["patch_sha256"])
            head, tree, fingerprint = event["head"], event["tree"], event["fingerprint"]
            conflict_id = None
            if kind == "repair.applied":
                repair_families.append(event["model_family"])
        elif kind == "patch.conflict":
            if event["packet_id"] in applied:
                raise IntegrationError("conflict recorded for an already-applied packet")
            conflict_id = event["conflict_id"]
        elif kind == "validators.completed":
            head, tree, fingerprint = event["head"], event["tree"], event["fingerprint"]
        else:
            raise IntegrationError(f"unknown integration event kind: {kind!r}")
    return IntegrationSnapshot(
        run_id=run_id, integration_id=integration_id, sandbox_id=sandbox_id,
        base_commit=base_commit, integration_order=order,
        applied_packet_ids=tuple(applied), patch_hashes=tuple(hashes), head=head,
        tree=tree, fingerprint=fingerprint, conflict_id=conflict_id,
        repair_model_families=tuple(repair_families), event_sequence=event_count,
    )


def _load_patch_set(root: Path | str, run_id: str):
    plan = load_execution_plan(root, run_id)
    order = _topological_order(plan)
    advancement = load_advancement_snapshot(root, run_id)
    if any(advancement.packet_state[packet_id].value != "succeeded" for packet_id in order):
        raise IntegrationError("all packets must have successful advancement outcomes before integration")
    receipts = {packet_id: load_packet_patch_receipt(root, run_id, packet_id) for packet_id in order}
    first = receipts[order[0]]
    for packet_id, receipt in receipts.items():
        if receipt.sequence < 1 or receipt.execution_plan_hash != execution_plan_hash(plan):
            raise IntegrationError(f"packet patch receipt {packet_id!r} has stale plan evidence")
        patch_path = _run_dir(root, run_id) / receipt.patch_path
        patch = patch_path.read_bytes()
        if len(patch) != receipt.patch_bytes or _sha256(patch) != receipt.patch_sha256:
            raise IntegrationError(f"packet patch {packet_id!r} failed hash revalidation")
        if receipt.snapshot_commit != first.snapshot_commit or receipt.snapshot_fingerprint != first.snapshot_fingerprint:
            raise IntegrationError("packet patches are not bound to one frozen snapshot")
    return plan, order, receipts


def _integration_worktree(root: Path | str, run_id: str, snapshot: IntegrationSnapshot) -> Path:
    if snapshot.sandbox_id is None:
        raise IntegrationError("integration sandbox has not been created")
    receipt = load_sandbox_receipt(root, run_id, snapshot.sandbox_id)
    if receipt.kind is not SandboxKind.integration:
        raise IntegrationError("integration state references a non-integration sandbox")
    return Path(receipt.path).resolve()


def _current_git_state(worktree: Path) -> tuple[str, str]:
    return _git_text(worktree, "rev-parse", "HEAD"), _git_text(worktree, "rev-parse", "HEAD^{tree}")


def _commit(worktree: Path, message: str, at: datetime) -> tuple[str, str]:
    env = dict(os.environ)
    stamp = at.astimezone(timezone.utc).isoformat()
    env.update({"GIT_AUTHOR_NAME": "DevFlow", "GIT_AUTHOR_EMAIL": "devflow@localhost", "GIT_COMMITTER_NAME": "DevFlow", "GIT_COMMITTER_EMAIL": "devflow@localhost", "GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp})
    _git(worktree, "-c", "commit.gpgsign=false", "commit", "-q", "-m", message, env=env)
    return _current_git_state(worktree)


def _outcome_path(root: Path | str, run_id: str, command_id: str) -> Path:
    return _record_path(root, run_id, "integration-outcomes", command_id)


def integrate_run(root: Path | str, repo: Path | str, run_id: str, command_id: str) -> IntegrationOutcome:
    command = _load_model(_record_path(root, run_id, "integration-commands", command_id), IntegrationCommand, label="integration command")
    if command.run_id != run_id or command.command_id != command_id:
        raise IntegrationError("integration command does not match its path")
    outcome_path = _outcome_path(root, run_id, command_id)
    if outcome_path.exists():
        return _load_model(outcome_path, IntegrationOutcome, label="integration outcome")
    repo_path = Path(repo).resolve()
    lock = _run_dir(root, run_id) / ".integration.lock"
    with lock.open("a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            if outcome_path.exists():
                return _load_model(outcome_path, IntegrationOutcome, label="integration outcome")
            plan, order, receipts = _load_patch_set(root, run_id)
            state = load_integration_snapshot(root, run_id)
            if state.integration_id is None:
                sandbox_id = f"integration-{command.integration_id}"
                sandbox = create_sandbox(SandboxRequest(repo=repo_path, root=Path(root).resolve(), run_id=run_id, sandbox_id=sandbox_id, kind=SandboxKind.integration, authorization_id=command.authorization_id, max_sandboxes=command.max_sandboxes))
                worktree = Path(sandbox.path).resolve()
                if _status_paths(worktree):
                    raise IntegrationError("new integration worktree is not clean")
                head, tree = _current_git_state(worktree)
                fp = _fingerprint(head=head, tree=tree, applied=(), hashes=())
                _append_event(root, run_id, state.event_sequence, "integration.started", command_id, integration_id=command.integration_id, sandbox_id=sandbox_id, base_commit=sandbox.snapshot_commit, integration_order=order, head=head, tree=tree, fingerprint=fp)
                state = load_integration_snapshot(root, run_id)
            elif state.integration_id != command.integration_id:
                raise IntegrationError("run already owns a different integration id")
            worktree = _integration_worktree(root, run_id, state)
            live_head, live_tree = _current_git_state(worktree)
            if (live_head, live_tree) != (state.head, state.tree):
                raise IntegrationError("integration worktree changed outside authoritative integration events")
            if state.conflict_id is not None:
                conflict = load_conflict_receipt(root, run_id, state.conflict_id)
                return _persist_integration_outcome(root, IntegrationOutcome(command_id=command_id, run_id=run_id, integration_id=command.integration_id, status=IntegrationStatus.conflict, applied_packet_ids=state.applied_packet_ids, conflict_id=conflict.conflict_id, head=live_head, tree=live_tree, fingerprint=state.fingerprint or _fingerprint(head=live_head, tree=live_tree, applied=state.applied_packet_ids, hashes=state.patch_hashes), decided_at=command.created_at))
            for packet_id in order[len(state.applied_packet_ids):]:
                receipt = receipts[packet_id]
                patch_path = _run_dir(root, run_id) / receipt.patch_path
                patch = patch_path.read_bytes()
                if _sha256(patch) != receipt.patch_sha256:
                    raise IntegrationError("packet patch hash changed immediately before application")
                check = _git(worktree, "apply", "--check", "--binary", str(patch_path), timeout=command.timeout_seconds, check=False)
                if check.returncode != 0:
                    conflict_id = f"conflict-{packet_id}-{len(state.applied_packet_ids) + 1}"
                    conflict = ConflictReceipt(conflict_id=conflict_id, run_id=run_id, integration_id=command.integration_id, command_id=command_id, packet_id=packet_id, patch_receipt_id=receipt.receipt_id, patch_sha256=receipt.patch_sha256, order_index=len(state.applied_packet_ids), base_commit=state.base_commit or receipt.snapshot_commit, current_head=live_head, current_tree=live_tree, conflicting_paths=receipt.changed_paths, git_stderr=(check.stderr or check.stdout)[-command.max_output_bytes:].decode("utf-8", "replace"), created_at=command.created_at)
                    conflict_path = _record_path(root, run_id, "integration-conflicts", conflict_id)
                    if not _persist_model(conflict_path, conflict):
                        existing = load_conflict_receipt(root, run_id, conflict_id)
                        if existing != conflict:
                            raise IntegrationError("conflicting integration conflict receipt")
                    _append_event(root, run_id, state.event_sequence, "patch.conflict", command_id, conflict_id=conflict_id, packet_id=packet_id, patch_sha256=receipt.patch_sha256)
                    state = load_integration_snapshot(root, run_id)
                    return _persist_integration_outcome(root, IntegrationOutcome(command_id=command_id, run_id=run_id, integration_id=command.integration_id, status=IntegrationStatus.conflict, applied_packet_ids=state.applied_packet_ids, conflict_id=conflict_id, head=live_head, tree=live_tree, fingerprint=state.fingerprint or _fingerprint(head=live_head, tree=live_tree, applied=state.applied_packet_ids, hashes=state.patch_hashes), decided_at=command.created_at))
                _git(worktree, "apply", "--index", "--binary", str(patch_path), timeout=command.timeout_seconds)
                staged = tuple(sorted(filter(None, _git_text(worktree, "diff", "--cached", "--name-only").splitlines())))
                if staged != receipt.changed_paths:
                    raise IntegrationError(f"applied paths for {packet_id!r} do not match its patch receipt")
                head, tree = _commit(worktree, f"devflow: integrate {packet_id}", command.created_at)
                applied = state.applied_packet_ids + (packet_id,)
                hashes = state.patch_hashes + (receipt.patch_sha256,)
                fp = _fingerprint(head=head, tree=tree, applied=applied, hashes=hashes)
                _append_event(root, run_id, state.event_sequence, "patch.applied", command_id, packet_id=packet_id, patch_receipt_id=receipt.receipt_id, patch_sha256=receipt.patch_sha256, head=head, tree=tree, fingerprint=fp)
                state = load_integration_snapshot(root, run_id)
                live_head, live_tree = head, tree
            validator_ids: list[str] = []
            validators_pass = True
            if state.fingerprint is None:
                raise IntegrationError("integration fingerprint is missing before validators")
            for validator in plan.validators:
                receipt_id = f"integration-{command.integration_id}-{validator.id}"
                validator_receipt = run_validator(root, worktree, ValidatorRequest(receipt_id=receipt_id, run_id=run_id, snapshot_fingerprint=state.fingerprint, execution_plan_hash=execution_plan_hash(plan), validator=validator))
                validator_ids.append(validator_receipt.receipt_id)
                validators_pass = validators_pass and validator_receipt.passed
            validator_tuple = tuple(validator_ids)
            final_fp = _fingerprint(head=live_head, tree=live_tree, applied=state.applied_packet_ids, hashes=state.patch_hashes, validators=validator_tuple)
            _append_event(root, run_id, state.event_sequence, "validators.completed", command_id, validator_receipt_ids=validator_tuple, passed=validators_pass, head=live_head, tree=live_tree, fingerprint=final_fp)
            status = IntegrationStatus.awaiting_verification if validators_pass else IntegrationStatus.validator_failed
            return _persist_integration_outcome(root, IntegrationOutcome(command_id=command_id, run_id=run_id, integration_id=command.integration_id, status=status, applied_packet_ids=state.applied_packet_ids, validator_receipt_ids=validator_tuple, head=live_head, tree=live_tree, fingerprint=final_fp, decided_at=command.created_at))
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _persist_integration_outcome(root: Path | str, outcome: IntegrationOutcome) -> IntegrationOutcome:
    path = _outcome_path(root, outcome.run_id, outcome.command_id)
    if not _persist_model(path, outcome):
        existing = _load_model(path, IntegrationOutcome, label="integration outcome")
        if existing != outcome:
            raise IntegrationError("conflicting immutable integration outcome")
        return existing
    return outcome


def load_conflict_receipt(root: Path | str, run_id: str, conflict_id: str) -> ConflictReceipt:
    receipt = _load_model(_record_path(root, run_id, "integration-conflicts", conflict_id), ConflictReceipt, label="integration conflict receipt")
    if receipt.run_id != run_id or receipt.conflict_id != conflict_id:
        raise IntegrationError("integration conflict receipt does not match its path")
    return receipt


# ---------------------------------------------------------------------------
# Bounded conflict repair
# ---------------------------------------------------------------------------
def save_integration_repair_command(root: Path | str, command: IntegrationRepairCommand) -> IntegrationRepairCommand:
    path = _record_path(root, command.run_id, "integration-repair-commands", command.command_id)
    if path.exists():
        existing = _load_model(path, IntegrationRepairCommand, label="integration repair command")
        if existing == command:
            return existing
        raise IntegrationError("conflicting integration repair command")
    if not _persist_model(path, command):
        return save_integration_repair_command(root, command)
    return command


def record_integration_repair(root: Path | str, repo: Path | str, run_id: str, command_id: str) -> IntegrationRepairReceipt:
    command = _load_model(_record_path(root, run_id, "integration-repair-commands", command_id), IntegrationRepairCommand, label="integration repair command")
    receipt_path = _record_path(root, run_id, "integration-repair-receipts", command_id)
    if receipt_path.exists():
        return _load_model(receipt_path, IntegrationRepairReceipt, label="integration repair receipt")
    state = load_integration_snapshot(root, run_id)
    if state.integration_id != command.integration_id or state.conflict_id != command.conflict_id:
        raise IntegrationError("repair command does not own the active integration conflict")
    conflict = load_conflict_receipt(root, run_id, command.conflict_id)
    attempts_dir = _run_dir(root, run_id) / "integration-repair-receipts"
    previous = []
    if attempts_dir.is_dir():
        for child in sorted(attempts_dir.glob("*.json")):
            item = _load_model(child, IntegrationRepairReceipt, label="integration repair receipt")
            if item.conflict_id == command.conflict_id:
                previous.append(item)
    attempt_number = len(previous) + 1
    if attempt_number > command.max_attempts:
        raise IntegrationError("integration repair retry cap exhausted; human action required")
    evidence = Path(command.evidence_reference)
    if evidence.is_absolute() or evidence.name != command.evidence_reference or not (_run_dir(root, run_id) / evidence).is_file():
        raise IntegrationError("repair requires an existing direct run evidence file")
    patch = load_packet_patch_receipt(root, run_id, conflict.packet_id)
    worktree = _integration_worktree(root, run_id, state)
    if _git(worktree, "diff", "--check", check=False).returncode != 0:
        raise IntegrationError("repair has unresolved diff errors")
    changed = _status_paths(worktree)
    if not changed or set(changed) - set(patch.target_files):
        raise IntegrationError("repair must change only the conflicted packet targets")
    if previous and changed == previous[-1].changed_paths and _tree_from_worktree(worktree, patch.target_files) == previous[-1].tree:
        raise IntegrationError("integration repair made no progress")
    _git(worktree, "add", "--all", "--", *patch.target_files)
    staged = tuple(sorted(filter(None, _git_text(worktree, "diff", "--cached", "--name-only").splitlines())))
    if staged != changed:
        raise IntegrationError("repair staged paths do not match live repair changes")
    head, tree = _commit(worktree, f"devflow: repair {conflict.packet_id}", command.created_at)
    applied = state.applied_packet_ids + (conflict.packet_id,)
    hashes = state.patch_hashes + (patch.patch_sha256,)
    fp = _fingerprint(head=head, tree=tree, applied=applied, hashes=hashes)
    receipt = IntegrationRepairReceipt(repair_id=f"repair-{command_id}", command_id=command_id, run_id=run_id, integration_id=command.integration_id, conflict_id=command.conflict_id, packet_id=conflict.packet_id, attempt_number=attempt_number, owner_id=command.owner_id, route=command.route, provider=command.provider, model=command.model, model_family=command.model_family, evidence_reference=command.evidence_reference, changed_paths=changed, head=head, tree=tree, recorded_at=command.created_at)
    if not _persist_model(receipt_path, receipt):
        existing = _load_model(receipt_path, IntegrationRepairReceipt, label="integration repair receipt")
        if existing != receipt:
            raise IntegrationError("conflicting integration repair receipt")
        return existing
    _append_event(root, run_id, state.event_sequence, "repair.applied", command_id, packet_id=conflict.packet_id, conflict_id=conflict.conflict_id, patch_sha256=patch.patch_sha256, model_family=command.model_family, head=head, tree=tree, fingerprint=fp)
    return receipt


# ---------------------------------------------------------------------------
# Independent read-only integration verification
# ---------------------------------------------------------------------------
def _latest_successful_integration_outcome(root: Path | str, run_id: str, integration_id: str) -> IntegrationOutcome:
    directory = _run_dir(root, run_id) / "integration-outcomes"
    found: list[IntegrationOutcome] = []
    if directory.is_dir():
        for path in sorted(directory.glob("*.json")):
            outcome = _load_model(path, IntegrationOutcome, label="integration outcome")
            if outcome.integration_id == integration_id and outcome.status is IntegrationStatus.awaiting_verification:
                found.append(outcome)
    if not found:
        raise IntegrationError("integration has no passing validator outcome to verify")
    return found[-1]


def _advance_verified_workflow(
    root: Path | str,
    receipt_path: Path,
    receipt: IntegrationVerificationReceipt,
) -> None:
    if receipt.verdict != "pass":
        return
    workflow = replay_workflow_run(root, receipt.run_id)
    if (
        workflow.current_node_id == "human_decision"
        and "verification" in workflow.completed_node_ids
    ):
        return
    if workflow.current_node_id != "verification":
        raise IntegrationError(
            "passing integration verification cannot advance a workflow outside verification"
        )
    evidence_name = f"integration-verification-{receipt.receipt_id}.json"
    evidence_path = _run_dir(root, receipt.run_id) / evidence_name
    evidence_payload = (
        json.dumps(
            {
                "receipt_path": str(
                    receipt_path.relative_to(_run_dir(root, receipt.run_id))
                ),
                "receipt_sha256": _sha256(receipt_path.read_bytes()),
                "integration_fingerprint": receipt.fingerprint,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode()
    if not _persist_bytes(evidence_path, evidence_payload):
        if evidence_path.read_bytes() != evidence_payload:
            raise IntegrationError("conflicting workflow verification evidence")
    workflow_receipt_id = f"workflow-{receipt.receipt_id}"
    record_node_outcome(
        root,
        receipt.run_id,
        receipt=NodeReceipt(
            receipt_id=workflow_receipt_id,
            node_id="verification",
            outcome="success",
            evidence=(
                EvidenceReference(
                    key="verification-receipt", reference=evidence_name
                ),
            ),
        ),
        event=WorkflowEvent(
            event_id=workflow_receipt_id,
            node_id="verification",
            outcome="success",
            receipt_id=workflow_receipt_id,
        ),
    )


def record_integration_verification(root: Path | str, repo: Path | str, request: IntegrationVerificationRequest) -> IntegrationVerificationReceipt:
    path = _record_path(root, request.run_id, "integration-verification-receipts", request.receipt_id)
    if path.exists():
        existing = _load_model(path, IntegrationVerificationReceipt, label="integration verification receipt")
        if (existing.provider, existing.model, existing.model_family, existing.route, existing.verdict, existing.findings, existing.definition_of_done_sha256) == (request.provider, request.model, request.model_family, request.route, request.verdict, request.findings, request.definition_of_done_sha256):
            state = load_integration_snapshot(root, request.run_id)
            worktree = _integration_worktree(root, request.run_id, state)
            if _status_paths(worktree):
                raise IntegrationError("integration verification receipt is stale")
            if (*_current_git_state(worktree), state.fingerprint) != (
                existing.head,
                existing.tree,
                existing.fingerprint,
            ):
                raise IntegrationError("integration verification receipt is stale")
            _advance_verified_workflow(root, path, existing)
            return existing
        raise IntegrationError("conflicting integration verification receipt")
    outcome = _latest_successful_integration_outcome(root, request.run_id, request.integration_id)
    state = load_integration_snapshot(root, request.run_id)
    worktree = _integration_worktree(root, request.run_id, state)
    if _status_paths(worktree):
        raise IntegrationError("integration verification inputs are stale")
    head, tree = _current_git_state(worktree)
    if (head, tree, outcome.fingerprint) != (outcome.head, outcome.tree, state.fingerprint):
        raise IntegrationError("integration verification inputs are stale")
    for receipt_id in outcome.validator_receipt_ids:
        validator = load_validator_receipt(root, request.run_id, receipt_id)
        if not validator.passed:
            raise IntegrationError("independent verification cannot waive a failed validator")
    _, order, patches = _load_patch_set(root, request.run_id)
    builder_families = tuple(sorted({patches[packet_id].model_family for packet_id in order}))
    all_prior_families = tuple(sorted(set(builder_families) | set(state.repair_model_families)))
    if request.model_family in all_prior_families:
        raise IntegrationError("integration verifier model family is not independent")
    receipt = IntegrationVerificationReceipt(receipt_id=request.receipt_id, run_id=request.run_id, integration_id=request.integration_id, provider=request.provider, model=request.model, model_family=request.model_family, route=request.route, independent_from_model_families=all_prior_families, head=head, tree=tree, fingerprint=outcome.fingerprint, patch_receipt_ids=tuple(patches[packet_id].receipt_id for packet_id in order), patch_hashes=tuple(patches[packet_id].patch_sha256 for packet_id in order), validator_receipt_ids=outcome.validator_receipt_ids, definition_of_done_sha256=request.definition_of_done_sha256, findings=request.findings, verdict=request.verdict, reviewed_at=request.reviewed_at)
    if not _persist_model(path, receipt):
        return record_integration_verification(root, repo, request)
    _advance_verified_workflow(root, path, receipt)
    return receipt


__all__ = [
    "ConflictReceipt", "IntegrationCommand", "IntegrationError", "IntegrationOutcome",
    "IntegrationRepairCommand", "IntegrationRepairReceipt", "IntegrationSnapshot",
    "IntegrationStatus", "IntegrationVerificationReceipt", "IntegrationVerificationRequest",
    "PacketPatchReceipt", "PatchCaptureCommand", "capture_packet_patch", "integrate_run",
    "load_conflict_receipt", "load_integration_snapshot", "load_packet_patch_receipt",
    "record_integration_repair", "record_integration_verification", "save_integration_command",
    "save_integration_repair_command", "save_patch_capture_command",
]
