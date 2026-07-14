"""Typed validator execution with immutable run-scoped receipts."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from devflow.loop.execution_plan import ExecutionValidator
from devflow.loop.pipeline_run import pipeline_runs_dir


_RECEIPT_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]*$"
_COMBINED_OUTPUT_EVIDENCE = {"output", "pytest-output"}
_OUTPUT_LIMIT = 64_000


class ValidatorOutcome(str, Enum):
    """Exhaustive host outcomes; only ``passed`` can authorize execution."""

    passed = "passed"
    spawn_error = "spawn_error"
    timeout = "timeout"
    nonzero = "nonzero"
    malformed_evidence = "malformed_evidence"
    invalid_cwd = "invalid_cwd"


class ValidatorRequest(BaseModel):
    """Exact immutable inputs bound to one validator attempt receipt."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    receipt_id: str = Field(min_length=1, pattern=_RECEIPT_ID_PATTERN)
    run_id: str = Field(min_length=1, pattern=_RECEIPT_ID_PATTERN)
    snapshot_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    execution_plan_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    validator: ExecutionValidator


class ValidatorReceipt(BaseModel):
    """Immutable persisted result for one exact validator request."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    receipt_id: str = Field(pattern=_RECEIPT_ID_PATTERN)
    run_id: str = Field(pattern=_RECEIPT_ID_PATTERN)
    snapshot_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    execution_plan_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    validator: ExecutionValidator
    outcome: ValidatorOutcome
    passed: bool
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""

    @model_validator(mode="after")
    def validate_pass_semantics(self) -> "ValidatorReceipt":
        if self.passed != (self.outcome is ValidatorOutcome.passed):
            raise ValueError("validator passed flag does not match outcome")
        if self.outcome is ValidatorOutcome.passed and self.exit_code != 0:
            raise ValueError("passing validator receipt requires exit_code=0")
        return self


def _run_dir(root: Path | str, run_id: str) -> Path:
    runs = pipeline_runs_dir(root).resolve()
    run_dir = (runs / run_id).resolve()
    try:
        run_dir.relative_to(runs)
    except ValueError as exc:
        raise ValueError("validator request run does not match the repository") from exc
    if not run_dir.is_dir():
        raise ValueError("validator request run does not match an existing run")
    return run_dir


def _receipt_path(root: Path | str, run_id: str, receipt_id: str) -> Path:
    if not receipt_id or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-" for ch in receipt_id):
        raise ValueError("invalid validator receipt id")
    return _run_dir(root, run_id) / "validator-receipts" / f"{receipt_id}.json"


def load_validator_receipt(
    root: Path | str, run_id: str, receipt_id: str
) -> ValidatorReceipt:
    """Load and validate one immutable validator receipt."""

    path = _receipt_path(root, run_id, receipt_id)
    try:
        receipt = ValidatorReceipt.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"validator receipt {receipt_id!r} is missing or corrupt") from exc
    if receipt.receipt_id != receipt_id or receipt.run_id != run_id:
        raise ValueError(f"validator receipt {receipt_id!r} does not match its path")
    return receipt


def _request_matches(receipt: ValidatorReceipt, request: ValidatorRequest) -> bool:
    return (
        receipt.receipt_id == request.receipt_id
        and receipt.run_id == request.run_id
        and receipt.snapshot_fingerprint == request.snapshot_fingerprint
        and receipt.execution_plan_hash == request.execution_plan_hash
        and receipt.validator == request.validator
    )


def _persist_receipt(root: Path | str, receipt: ValidatorReceipt) -> ValidatorReceipt:
    path = _receipt_path(root, receipt.run_id, receipt.receipt_id)
    path.parent.mkdir(mode=0o755, exist_ok=True)
    payload = (json.dumps(receipt.model_dump(mode="json"), indent=2, sort_keys=True) + "\n").encode()
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
    except FileExistsError:
        existing = load_validator_receipt(root, receipt.run_id, receipt.receipt_id)
        if existing == receipt:
            return existing
        raise ValueError(f"conflicting validator receipt: {receipt.receipt_id}") from None
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return receipt


def _evidence_complete(validator: ExecutionValidator, stdout: str, stderr: str) -> bool:
    evidence = set(validator.evidence)
    if "stdout" in evidence and not stdout:
        return False
    if "stderr" in evidence and not stderr:
        return False
    if evidence & _COMBINED_OUTPUT_EVIDENCE and not (stdout or stderr):
        return False
    return True


def run_validator(
    root: Path | str,
    workspace: Path | str,
    request: ValidatorRequest,
) -> ValidatorReceipt:
    """Execute one typed argv validator and persist its immutable outcome."""

    run_dir = _run_dir(root, request.run_id)
    path = _receipt_path(root, request.run_id, request.receipt_id)
    if path.exists():
        existing = load_validator_receipt(root, request.run_id, request.receipt_id)
        if _request_matches(existing, request):
            return existing
        raise ValueError(f"conflicting validator receipt: {request.receipt_id}")
    if run_dir != path.parents[1]:
        raise ValueError("validator request run does not match receipt path")

    workspace_root = Path(workspace).resolve()
    cwd = (workspace_root / request.validator.cwd).resolve()
    try:
        cwd.relative_to(workspace_root)
    except ValueError:
        cwd_valid = False
    else:
        cwd_valid = cwd.is_dir()

    kwargs = dict(
        receipt_id=request.receipt_id,
        run_id=request.run_id,
        snapshot_fingerprint=request.snapshot_fingerprint,
        execution_plan_hash=request.execution_plan_hash,
        validator=request.validator,
    )
    if not cwd_valid:
        return _persist_receipt(
            root,
            ValidatorReceipt(
                **kwargs,
                outcome=ValidatorOutcome.invalid_cwd,
                passed=False,
                stderr=f"validator cwd {request.validator.cwd!r} is not a directory inside the workspace",
            ),
        )

    env = dict(os.environ)
    env["PATH"] = f"{Path(sys.executable).parent}{os.pathsep}{env.get('PATH', '')}"
    # Validators are evidence collectors, not builders.  Prevent Python-based
    # validators (including ``py_compile``/pytest imports) from leaving
    # ``__pycache__`` mutations in an otherwise immutable integration tree.
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    pycache_dir = Path(tempfile.mkdtemp(prefix="devflow-validator-pycache-"))
    env["PYTHONPYCACHEPREFIX"] = str(pycache_dir)
    def _execute() -> ValidatorReceipt:
        try:
            completed = subprocess.run(
                request.validator.argv,
                shell=False,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=request.validator.timeout_seconds,
                env=env,
            )
        except subprocess.TimeoutExpired as exc:
            return ValidatorReceipt(
                **kwargs,
                outcome=ValidatorOutcome.timeout,
                passed=False,
                stdout=(exc.stdout if isinstance(exc.stdout, str) else "")[-_OUTPUT_LIMIT:],
                stderr=f"timed out after {request.validator.timeout_seconds} seconds",
            )
        except OSError as exc:
            return ValidatorReceipt(
                **kwargs,
                outcome=ValidatorOutcome.spawn_error,
                passed=False,
                stderr=f"could not start validator: {exc}",
            )
        stdout = completed.stdout[-_OUTPUT_LIMIT:]
        stderr = completed.stderr[-_OUTPUT_LIMIT:]
        if completed.returncode != 0:
            outcome = ValidatorOutcome.nonzero
        elif not _evidence_complete(request.validator, stdout, stderr):
            outcome = ValidatorOutcome.malformed_evidence
        else:
            outcome = ValidatorOutcome.passed
        return ValidatorReceipt(
            **kwargs,
            outcome=outcome,
            passed=outcome is ValidatorOutcome.passed,
            exit_code=completed.returncode,
            stdout=stdout,
            stderr=stderr,
        )

    try:
        receipt = _execute()
    finally:
        shutil.rmtree(pycache_dir, ignore_errors=True)
    return _persist_receipt(root, receipt)


__all__ = [
    "ValidatorOutcome",
    "ValidatorReceipt",
    "ValidatorRequest",
    "load_validator_receipt",
    "run_validator",
]
