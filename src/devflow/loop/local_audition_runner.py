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
    "request_evidence",
    "parsed_packet",
    "protocol_validation",
    "deterministic_gates",
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
    request_evidence: dict | None = None,
    parsed_packet: dict | None = None,
    protocol_validation: dict | None = None,
    deterministic_gates: dict | None = None,
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
        "request_evidence": deepcopy(request_evidence or {}),
        "parsed_packet": deepcopy(parsed_packet or {}),
        "protocol_validation": deepcopy(protocol_validation or {}),
        "deterministic_gates": deepcopy(deterministic_gates or {}),
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
    request_evidence: dict | None = None,
    parsed_packet: dict | None = None,
    protocol_validation: dict | None = None,
    deterministic_gates: dict | None = None,
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
        request_evidence=request_evidence,
        parsed_packet=parsed_packet,
        protocol_validation=protocol_validation,
        deterministic_gates=deterministic_gates,
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
        request_evidence = raw.get("request_evidence", {})
        parsed_packet = raw.get("parsed_packet", {})
        protocol_validation = raw.get("protocol_validation", {})
        deterministic_gates = raw.get("deterministic_gates", {})
        malformed_fields = [
            name
            for name, value, expected in (
                ("actual_model", actual_model, str),
                ("content", content, str),
                ("usage", usage, Mapping),
                ("finish_reason", finish_reason, str),
                ("request_evidence", request_evidence, Mapping),
                ("parsed_packet", parsed_packet, Mapping),
                ("protocol_validation", protocol_validation, Mapping),
                ("deterministic_gates", deterministic_gates, Mapping),
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
                request_evidence=dict(request_evidence),
                parsed_packet=dict(parsed_packet),
                protocol_validation=dict(protocol_validation),
                deterministic_gates=dict(deterministic_gates),
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
                request_evidence=dict(request_evidence),
                parsed_packet=dict(parsed_packet),
                protocol_validation=dict(protocol_validation),
                deterministic_gates=dict(deterministic_gates),
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
                request_evidence=dict(request_evidence),
                parsed_packet=dict(parsed_packet),
                protocol_validation=dict(protocol_validation),
                deterministic_gates=dict(deterministic_gates),
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
                request_evidence=dict(request_evidence),
                parsed_packet=dict(parsed_packet),
                protocol_validation=dict(protocol_validation),
                deterministic_gates=dict(deterministic_gates),
            ))
            continue

        if protocol_validation and protocol_validation.get("valid") is not True:
            receipts.append(_failed(
                case_id,
                role,
                requested_model,
                sequence,
                "ProtocolValidationFailed",
                "The structured output packet failed its versioned contract.",
                actual_model=actual_model,
                content=content,
                usage=dict(usage),
                finish_reason=finish_reason,
                request_evidence=dict(request_evidence),
                parsed_packet=dict(parsed_packet),
                protocol_validation=dict(protocol_validation),
                deterministic_gates=dict(deterministic_gates),
            ))
            continue
        host_outcome = deterministic_gates.get("outcome")
        if host_outcome in {"failed", "needs_review", "block"}:
            receipts.append(_failed(
                case_id,
                role,
                requested_model,
                sequence,
                "HostGateTerminal",
                f"Deterministic host outcome: {host_outcome}.",
                actual_model=actual_model,
                content=content,
                usage=dict(usage),
                finish_reason=finish_reason,
                request_evidence=dict(request_evidence),
                parsed_packet=dict(parsed_packet),
                protocol_validation=dict(protocol_validation),
                deterministic_gates=dict(deterministic_gates),
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
            request_evidence=dict(request_evidence),
            parsed_packet=dict(parsed_packet),
            protocol_validation=dict(protocol_validation),
            deterministic_gates=dict(deterministic_gates),
        ))
    return receipts


__all__ = ["run_local_audition"]
