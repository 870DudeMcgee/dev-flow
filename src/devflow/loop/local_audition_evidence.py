"""Persist complete, write-once evidence for atomic local-model attempts."""

from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Callable, Mapping, Sequence

from .local_audition_matrix import MatrixReceipt


FAILURE_CATEGORIES = (
    "model_capability",
    "prompt_context_packaging",
    "tool_runtime",
    "orchestration_guardrail",
    "ground_truth_scorer",
    "infrastructure",
)


def _require_nonblank(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a nonblank string")


def attempt_evidence_path(root: Path, sequence: int) -> Path:
    """Return the stable write-once path for an atomic attempt."""
    if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence <= 0:
        raise ValueError("sequence must be a positive integer")
    return Path(root) / "attempts" / f"{sequence:06d}.json"


def build_attempt_evidence(
    receipt: MatrixReceipt,
    runtime_fingerprint: str,
    reliability_outcome: Mapping,
    quality_outcome: Mapping,
    failure_category: str | None = None,
    failure_reason: str | None = None,
    classification_evidence: Sequence[str] = (),
) -> dict:
    """Build one complete record without guessing a failure's root cause."""
    if not isinstance(receipt, MatrixReceipt):
        raise ValueError("receipt must be a MatrixReceipt")
    _require_nonblank("runtime_fingerprint", runtime_fingerprint)
    if not isinstance(reliability_outcome, Mapping):
        raise ValueError("reliability_outcome must be a mapping")
    if not isinstance(quality_outcome, Mapping):
        raise ValueError("quality_outcome must be a mapping")

    runner = receipt.runner_receipt
    status = runner.get("status")
    refs = tuple(classification_evidence)
    if status == "completed":
        if failure_category is not None or failure_reason is not None or refs:
            raise ValueError("completed attempts cannot carry failure classification")
        _require_nonblank("served model identity", runner.get("actual_model"))
        failure_classification = None
    elif status == "failed":
        if failure_category not in FAILURE_CATEGORIES:
            raise ValueError("failed attempts require an allowed failure category")
        _require_nonblank("failure_reason", failure_reason)
        if (
            not refs
            or any(not isinstance(ref, str) or not ref.strip() for ref in refs)
            or len(refs) != len(set(refs))
        ):
            raise ValueError("failed attempts require unique nonblank evidence refs")
        failure_classification = {
            "category": failure_category,
            "reason": failure_reason,
            "evidence_refs": list(refs),
        }
    else:
        raise ValueError("runner receipt has an unsupported terminal status")

    attempt = receipt.attempt
    return {
        "schema_version": 1,
        "attempt": {
            "sequence": attempt.sequence,
            "candidate_id": attempt.candidate_id,
            "role": attempt.role,
            "case_id": attempt.case_id,
            "repeat": attempt.repeat,
        },
        "request": attempt.case_data(),
        "expected_model": attempt.expected_model,
        "served_model": runner.get("actual_model", ""),
        "artifact_fingerprint": attempt.fingerprint,
        "runtime_fingerprint": runtime_fingerprint,
        "timing": {
            "scheduled_at": receipt.scheduled_at,
            "started_at": receipt.started_at,
            "finished_at": receipt.finished_at,
            "queue_duration_seconds": receipt.queue_duration_seconds,
            "duration_seconds": receipt.duration_seconds,
            "total_duration_seconds": receipt.total_duration_seconds,
        },
        "usage": deepcopy(runner.get("usage", {})),
        "raw_output": runner.get("content", ""),
        "request_evidence": deepcopy(runner.get("request_evidence", {})),
        "parsed_packet": deepcopy(runner.get("parsed_packet", {})),
        "protocol_validation": deepcopy(runner.get("protocol_validation", {})),
        "deterministic_gates": deepcopy(runner.get("deterministic_gates", {})),
        "reliability_outcome": deepcopy(dict(reliability_outcome)),
        "quality_outcome": deepcopy(dict(quality_outcome)),
        "failure_classification": failure_classification,
        "terminal_status": status,
        "runner_receipt": deepcopy(runner),
    }


def persist_attempt_evidence(
    root: Path,
    evidence: Mapping,
    commit: Callable[[Path, Path], None] = os.link,
) -> Path:
    """Atomically publish canonical JSON without replacing existing evidence."""
    if not isinstance(evidence, Mapping):
        raise ValueError("evidence must be a mapping")
    attempt = evidence.get("attempt")
    if not isinstance(attempt, Mapping):
        raise ValueError("evidence must contain attempt metadata")
    target = attempt_evidence_path(Path(root), attempt.get("sequence"))
    target.parent.mkdir(parents=True, exist_ok=True)

    temporary_path: Path | None = None
    try:
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=target.parent,
            prefix=f".{target.stem}-",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            json.dump(evidence, temporary, ensure_ascii=False, indent=2, sort_keys=True)
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
        commit(temporary_path, target)
        return target
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


__all__ = [
    "FAILURE_CATEGORIES",
    "attempt_evidence_path",
    "build_attempt_evidence",
    "persist_attempt_evidence",
]
