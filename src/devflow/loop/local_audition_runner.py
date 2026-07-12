"""Pure serial runner for dependency-injected local-model auditions."""

from __future__ import annotations

from copy import deepcopy
from typing import Callable, Mapping, Sequence


_RECEIPT_KEYS = (
    "case_id",
    "role",
    "requested_model",
    "actual_model",
    "status",
    "content",
    "usage",
    "finish_reason",
    "error_type",
    "error",
    "sequence",
)
_MAX_CONTENT_CHARS = 64_000
_MAX_ERROR_CHARS = 2_000
_CAPPED_FINISH_REASONS = {
    "length",
    "max_tokens",
    "max_output_tokens",
    "token_cap",
    "token_limit",
}


def _receipt(
    *,
    case_id: str,
    role: str,
    requested_model: str,
    sequence: int,
    actual_model: str = "",
    status: str = "failed",
    content: str = "",
    usage: dict | None = None,
    finish_reason: str = "",
    error_type: str = "",
    error: str = "",
) -> dict:
    values = {
        "case_id": case_id,
        "role": role,
        "requested_model": requested_model,
        "actual_model": actual_model,
        "status": status,
        "content": content[:_MAX_CONTENT_CHARS],
        "usage": deepcopy(usage or {}),
        "finish_reason": finish_reason,
        "error_type": error_type,
        "error": error[:_MAX_ERROR_CHARS],
        "sequence": sequence,
    }
    return {key: values[key] for key in _RECEIPT_KEYS}


def _failed(
    case_id: str,
    role: str,
    requested_model: str,
    sequence: int,
    error_type: str,
    error: str,
    *,
    actual_model: str = "",
    content: str = "",
    usage: dict | None = None,
    finish_reason: str = "",
) -> dict:
    return _receipt(
        case_id=case_id,
        role=role,
        requested_model=requested_model,
        actual_model=actual_model,
        sequence=sequence,
        content=content,
        usage=usage,
        finish_reason=finish_reason,
        error_type=error_type,
        error=error,
    )


def run_local_audition(
    cases: Sequence[Mapping],
    assignments: Mapping[str, str],
    invoke: Callable[[str, dict], Mapping],
) -> list[dict]:
    """Invoke one explicitly assigned model per case, strictly in input order.

    Transport and timing remain the caller's responsibility.  This function
    makes one attempt per valid assignment and turns every unusable result into
    a terminal failed receipt instead of retrying or choosing a fallback.
    """
    receipts: list[dict] = []
    for sequence, source_case in enumerate(cases, start=1):
        case = deepcopy(dict(source_case))
        case_id = str(case.get("case_id") or "")
        role = str(case.get("role") or "")
        requested_model = assignments.get(role, "")
        if not isinstance(requested_model, str) or not requested_model.strip():
            receipts.append(_failed(
                case_id,
                role,
                "",
                sequence,
                "MissingAssignment",
                f"No explicit model assignment exists for role '{role}'.",
            ))
            continue
        requested_model = requested_model.strip()

        try:
            raw = invoke(requested_model, deepcopy(case))
        except Exception as exc:
            receipts.append(_failed(
                case_id,
                role,
                requested_model,
                sequence,
                type(exc).__name__,
                str(exc),
            ))
            continue

        if not isinstance(raw, Mapping):
            receipts.append(_failed(
                case_id,
                role,
                requested_model,
                sequence,
                "MalformedResult",
                "The injected invocation did not return a mapping.",
            ))
            continue

        actual_model = raw.get("actual_model")
        content = raw.get("content")
        usage = raw.get("usage", {})
        finish_reason = raw.get("finish_reason", "")
        malformed_fields = [
            name
            for name, value, expected in (
                ("actual_model", actual_model, str),
                ("content", content, str),
                ("usage", usage, Mapping),
                ("finish_reason", finish_reason, str),
            )
            if not isinstance(value, expected)
        ]
        if malformed_fields:
            receipts.append(_failed(
                case_id,
                role,
                requested_model,
                sequence,
                "MalformedResult",
                "Invalid result fields: " + ", ".join(malformed_fields),
            ))
            continue

        actual_model = actual_model.strip()
        if not actual_model:
            receipts.append(_failed(
                case_id,
                role,
                requested_model,
                sequence,
                "MissingModelIdentity",
                "The invocation did not report the served model identity.",
                content=content,
                usage=dict(usage),
                finish_reason=finish_reason,
            ))
            continue
        if actual_model != requested_model:
            receipts.append(_failed(
                case_id,
                role,
                requested_model,
                sequence,
                "ModelIdentityMismatch",
                (
                    f"Requested model '{requested_model}' but the runtime served "
                    f"'{actual_model}'."
                ),
                actual_model=actual_model,
                content=content,
                usage=dict(usage),
                finish_reason=finish_reason,
            ))
            continue
        if not content.strip():
            receipts.append(_failed(
                case_id,
                role,
                requested_model,
                sequence,
                "BlankCompletion",
                "The invocation returned a blank completion.",
                actual_model=actual_model,
                usage=dict(usage),
                finish_reason=finish_reason,
            ))
            continue
        if finish_reason.strip().lower() in _CAPPED_FINISH_REASONS:
            receipts.append(_failed(
                case_id,
                role,
                requested_model,
                sequence,
                "CappedCompletion",
                f"The invocation stopped with finish reason '{finish_reason}'.",
                actual_model=actual_model,
                content=content,
                usage=dict(usage),
                finish_reason=finish_reason,
            ))
            continue

        receipts.append(_receipt(
            case_id=case_id,
            role=role,
            requested_model=requested_model,
            actual_model=actual_model,
            status="completed",
            content=content,
            usage=dict(usage),
            finish_reason=finish_reason,
            sequence=sequence,
        ))
    return receipts


__all__ = ["run_local_audition"]
