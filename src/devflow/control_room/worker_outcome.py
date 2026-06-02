from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from devflow.control_room.models import TASK_SCHEMA_VERSION
from devflow.control_room.paths import outcome_validations_dir, relative_path, task_dir
from devflow.control_room.persistence import atomic_write_text, utc_now


ALLOWED_SOURCE_KINDS = {
    "shell_worker",
    "manual_proof_agent",
    "registry_agent",
    "local_patch_runtime",
    "local_advisory_worker",
    "patch_review",
    "patch_dry_run",
    "patch_application",
    "verification",
    "orchestration_plan",
    "manual_evidence",
}
ALLOWED_OUTCOMES = {
    "patch_proposed",
    "question",
    "evidence_only",
    "rejected",
    "duplicate",
    "validation_failed",
    "verification_failed",
    "verification_passed",
    "no_useful_result",
    "blocked",
    "completed",
}
ALLOWED_TOOL_STATUSES = {
    "success_with_result",
    "success_empty",
    "failed_retryable",
    "failed_terminal",
    "ambiguous_needs_human",
    "unsafe_path",
    "validation_failed",
}
REQUIRED_FIELDS = {
    "schema_version",
    "task_id",
    "worker",
    "source_kind",
    "source_path",
    "outcome",
    "files_touched",
    "commands_run",
    "tool_results",
    "verification_status",
    "retryable",
    "human_review_required",
    "notes",
    "created_at",
}
HUMAN_REVIEW_OUTCOMES = {
    "rejected",
    "validation_failed",
    "verification_failed",
    "no_useful_result",
    "blocked",
}
HUMAN_REVIEW_TOOL_STATUSES = {
    "failed_retryable",
    "failed_terminal",
    "ambiguous_needs_human",
    "unsafe_path",
    "validation_failed",
}
CANONICAL_TASK_FILES = {
    "task.yaml",
    "events.jsonl",
    "verification.json",
    "merge-readiness.json",
    "summary.json",
    "closure.json",
    "cleanup.json",
}


class WorkerOutcomeError(ValueError):
    pass


def validate_worker_outcome_file(root: Path, outcome_path: Path) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    outcome: dict[str, Any] | None = None
    try:
        raw = outcome_path.read_text(encoding="utf-8")
        loaded = json.loads(raw)
        if not isinstance(loaded, dict):
            errors.append("outcome JSON must be an object")
        else:
            outcome = loaded
    except json.JSONDecodeError as exc:
        errors.append(f"malformed JSON: {exc.msg}")
    except OSError as exc:
        errors.append(f"could not read outcome JSON: {exc}")

    if outcome is not None:
        errors.extend(validate_worker_outcome(root, outcome))
        if outcome.get("tool_results") in ({}, []):
            warnings.append("tool_results is empty")

    output_path = _validation_output_path(root, outcome_path, outcome)
    result = {
        "schema_version": TASK_SCHEMA_VERSION,
        "output_path": relative_path(root, output_path),
        "status": "failed" if errors else "passed",
        "errors": errors,
        "warnings": warnings,
        "observed_tool_statuses": _tool_statuses(outcome.get("tool_results")) if outcome else [],
        "input_path": relative_path(root, outcome_path),
        "input_task_id": outcome.get("task_id") if outcome else None,
        "created_at": utc_now().isoformat(),
    }
    atomic_write_text(output_path, json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def validate_worker_outcome(root: Path, outcome: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    missing = sorted(REQUIRED_FIELDS - set(outcome))
    if missing:
        errors.append(f"missing required fields: {', '.join(missing)}")
        return errors

    if outcome.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    task_id = outcome.get("task_id")
    if not isinstance(task_id, str) or not task_id.strip():
        errors.append("task_id must be a non-empty string")
    if outcome.get("source_kind") not in ALLOWED_SOURCE_KINDS:
        errors.append(f"unknown source_kind: {outcome.get('source_kind')}")
    if outcome.get("outcome") not in ALLOWED_OUTCOMES:
        errors.append(f"unknown outcome: {outcome.get('outcome')}")

    files_touched = outcome.get("files_touched")
    if not isinstance(files_touched, list):
        errors.append("files_touched must be a list")
    else:
        for item in files_touched:
            if not isinstance(item, str):
                errors.append("files_touched entries must be strings")
                continue
            error = _relative_path_error(item, task_id=str(task_id) if isinstance(task_id, str) else None)
            if error:
                errors.append(f"files_touched {item!r}: {error}")

    tool_statuses = _tool_statuses(outcome.get("tool_results"))
    for status in tool_statuses:
        if status not in ALLOWED_TOOL_STATUSES:
            errors.append(f"unknown tool/result status: {status}")

    if _requires_human_review(outcome, tool_statuses) and outcome.get("human_review_required") is not True:
        errors.append("human_review_required must be true for ambiguous, unsafe, failed, blocked, or no-useful-result states")

    source_path = outcome.get("source_path")
    if isinstance(source_path, str) and isinstance(task_id, str):
        path_task = _task_id_from_task_path(root, source_path)
        if path_task and path_task != task_id:
            errors.append(f"source_path task id mismatch: {path_task} != {task_id}")

    if outcome.get("source_kind") == "orchestration_plan" and outcome.get("outcome") not in {
        "evidence_only",
        "blocked",
        "validation_failed",
        "no_useful_result",
    }:
        errors.append("orchestration_plan source_kind may only use evidence_only, blocked, validation_failed, or no_useful_result outcomes")

    if outcome.get("source_kind") == "local_patch_runtime" and outcome.get("outcome") == "patch_proposed":
        if not _has_patch_evidence(root, str(source_path)):
            errors.append("local_patch_runtime patch_proposed outcomes require proposal.patch evidence")

    if not isinstance(outcome.get("commands_run"), list):
        errors.append("commands_run must be a list")
    if not isinstance(outcome.get("retryable"), bool):
        errors.append("retryable must be boolean")
    if not isinstance(outcome.get("human_review_required"), bool):
        errors.append("human_review_required must be boolean")
    return errors


def _requires_human_review(outcome: dict[str, Any], tool_statuses: list[str]) -> bool:
    return outcome.get("outcome") in HUMAN_REVIEW_OUTCOMES or any(
        status in HUMAN_REVIEW_TOOL_STATUSES for status in tool_statuses
    )


def _tool_statuses(tool_results: Any) -> list[str]:
    statuses: list[str] = []
    if tool_results is None:
        return statuses
    if isinstance(tool_results, list):
        for item in tool_results:
            statuses.extend(_tool_statuses(item))
        return statuses
    if isinstance(tool_results, dict):
        status = tool_results.get("status") or tool_results.get("result_status")
        if isinstance(status, str):
            statuses.append(status)
        for value in tool_results.values():
            if isinstance(value, (dict, list)):
                statuses.extend(_tool_statuses(value))
        return statuses
    return statuses


def _relative_path_error(path_text: str, *, task_id: str | None) -> str | None:
    normalized = path_text.replace("\\", "/")
    path = Path(normalized)
    if path.is_absolute():
        return "absolute paths are rejected"
    parts = [part for part in path.parts if part not in {"", "."}]
    if ".." in parts:
        return "parent traversal is rejected"
    if ".git" in parts or normalized.startswith(".git/"):
        return ".git paths are rejected"
    if _targets_canonical_task_file(parts, task_id=task_id):
        return "canonical task files are not worker-touched paths"
    return None


def _targets_canonical_task_file(parts: list[str], *, task_id: str | None) -> bool:
    if not parts:
        return False
    filename = parts[-1]
    if filename not in CANONICAL_TASK_FILES:
        return False
    if len(parts) >= 4 and parts[0] == ".devflow" and parts[1] == "tasks":
        return task_id is None or parts[2] == task_id
    return False


def _task_id_from_task_path(root: Path, source_path: str) -> str | None:
    path = Path(source_path)
    if path.is_absolute():
        try:
            rel = path.resolve().relative_to(root.resolve())
        except ValueError:
            return None
    else:
        rel = path
    parts = rel.parts
    if len(parts) >= 3 and parts[0] == ".devflow" and parts[1] == "tasks":
        return parts[2]
    return None


def _has_patch_evidence(root: Path, source_path: str) -> bool:
    if not source_path:
        return False
    path = Path(source_path)
    if not path.is_absolute():
        path = root / path
    candidates = []
    if path.name == "proposal.patch":
        candidates.append(path)
    if path.is_dir():
        candidates.append(path / "proposal.patch")
    else:
        candidates.append(path.parent / "proposal.patch")
    return any(candidate.exists() and candidate.is_file() for candidate in candidates)


def _validation_output_path(root: Path, input_path: Path, outcome: dict[str, Any] | None) -> Path:
    if outcome and isinstance(outcome.get("task_id"), str):
        candidate = task_dir(root, outcome["task_id"])
        if candidate.exists():
            return candidate / "worker-outcome-validation.json"
    safe_stem = re.sub(r"[^A-Za-z0-9_.-]+", "-", input_path.stem).strip("-") or "outcome"
    return outcome_validations_dir(root) / f"{safe_stem}-validation.json"


def render_worker_outcome_validation(result: dict[str, Any]) -> str:
    lines = [
        f"status: {result['status']}",
        f"validation_path: {result['output_path']}",
        "patches_applied: no",
        "verification_run: no",
        "promotion_run: no",
        "provider_calls: none",
    ]
    if result["errors"]:
        lines.append("errors:")
        lines.extend(f"  - {error}" for error in result["errors"])
    if result["warnings"]:
        lines.append("warnings:")
        lines.extend(f"  - {warning}" for warning in result["warnings"])
    return "\n".join(lines) + "\n"
