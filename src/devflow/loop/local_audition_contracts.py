"""Versioned structured-output contracts for measured local-model roles."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable

from devflow.loop.local_audition_host_gates import (
    FINAL_JUDGE_NEXT_DECISION_BY_ACTION,
)


SCHEMA_VERSION = 1
FINAL_JUDGE_SCHEMA_VERSION = 3
FINAL_JUDGE_NEXT_ACTIONS = (
    "none",
    "repair_and_reverify",
    "provide_missing_evidence",
    "reconcile_conflicting_evidence",
    "human_choice_required",
)
_ROLES = {
    "planner",
    "builder",
    "planning_judge",
    "build_judge",
    "verifier",
    "final_judge",
}


def _string_array(*, enum: list[str] | None = None) -> dict[str, Any]:
    items: dict[str, Any] = {"type": "string"}
    if enum is not None:
        items["enum"] = enum
    return {"type": "array", "items": items, "uniqueItems": True}


def _object(properties: dict[str, Any], required: Iterable[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": list(required),
        "additionalProperties": False,
    }


def _schema_for(
    role: str,
    *,
    schema_version: int,
    target_files: list[str],
    evidence_ids: list[str],
) -> dict[str, Any]:
    if role == "planner":
        packet = _object(
            {
                "id": {"type": "string", "minLength": 1},
                "files": _string_array(enum=target_files or None),
            },
            ("id", "files"),
        )
        return _object(
            {
                "schema_version": {"const": schema_version},
                "decision": {"const": "plan"},
                "target_files": _string_array(enum=target_files or None),
                "packets": {
                    "type": "array",
                    "items": packet,
                    "minItems": 1,
                    "maxItems": 1,
                },
                "verification_command": {"type": "string", "minLength": 1},
                "constraints": _string_array(),
            },
            (
                "schema_version",
                "decision",
                "target_files",
                "packets",
                "verification_command",
                "constraints",
            ),
        )
    if role == "builder":
        file_packet = _object(
            {
                "path": {
                    "type": "string",
                    **({"enum": target_files} if target_files else {"minLength": 1}),
                },
                "content": {"type": "string", "minLength": 1},
            },
            ("path", "content"),
        )
        return _object(
            {
                "schema_version": {"const": schema_version},
                "files": {
                    "type": "array",
                    "items": file_packet,
                    "minItems": len(target_files) or 1,
                    **({"maxItems": len(target_files)} if target_files else {}),
                },
            },
            ("schema_version", "files"),
        )

    evidence = _string_array(enum=evidence_ids or None)
    common = {
        "schema_version": {"const": schema_version},
        "rationale": {"type": "string", "minLength": 1},
    }
    if role == "planning_judge":
        properties = {
            **common,
            "decision": {"type": "string", "enum": ["approve", "revise", "block"]},
            "evidence_refs": evidence,
            "required_changes": _string_array(),
        }
        return _object(properties, properties)
    if role in {"build_judge", "verifier"}:
        properties = {
            **common,
            "status": {"type": "string", "enum": ["passed", "failed", "needs_review"]},
            "evidence_refs": evidence,
            "missing_evidence": _string_array(enum=evidence_ids or None),
        }
        return _object(properties, properties)
    if role == "final_judge":
        properties = {
            **common,
            "decision": {"type": "string", "enum": ["qualify", "hold", "block"]},
            "evidence_refs": evidence,
            "residual_risks": _string_array(),
            "next_action": {"type": "string", "enum": list(FINAL_JUDGE_NEXT_ACTIONS)},
        }
        return _object(properties, properties)
    raise ValueError(f"No local-audition contract for role {role!r}.")


def build_audition_contract(
    role: str,
    *,
    target_files: Iterable[str] = (),
    evidence_ids: Iterable[str] = (),
) -> dict[str, Any]:
    """Return a fresh llama.cpp JSON-Schema response contract for ``role``."""
    if role not in _ROLES:
        raise ValueError(f"Unsupported measured role: {role!r}.")
    targets = list(dict.fromkeys(str(item) for item in target_files))
    evidence = list(dict.fromkeys(str(item) for item in evidence_ids))
    schema_version = FINAL_JUDGE_SCHEMA_VERSION if role == "final_judge" else SCHEMA_VERSION
    schema_id = f"devflow.{role}.v{schema_version}"
    schema = _schema_for(
        role,
        schema_version=schema_version,
        target_files=targets,
        evidence_ids=evidence,
    )
    return deepcopy(
        {
            "schema_id": schema_id,
            "schema_version": schema_version,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_id.replace(".", "_"),
                    "strict": True,
                    "schema": schema,
                },
            },
        }
    )


def validate_audition_packet(
    role: str,
    packet: Any,
    *,
    target_files: Iterable[str] = (),
    evidence_ids: Iterable[str] = (),
) -> dict[str, Any]:
    """Fail closed on the exact invariants needed before semantic scoring."""
    errors: list[str] = []
    if not isinstance(packet, dict):
        return {"valid": False, "errors": ["packet_not_object"]}
    expected_version = FINAL_JUDGE_SCHEMA_VERSION if role == "final_judge" else SCHEMA_VERSION
    if packet.get("schema_version") != expected_version or type(packet.get("schema_version")) is not int:
        errors.append("schema_version_invalid")

    targets = list(dict.fromkeys(str(item) for item in target_files))
    allowed_evidence = set(str(item) for item in evidence_ids)
    contract = build_audition_contract(role, target_files=targets, evidence_ids=allowed_evidence)
    schema = contract["response_format"]["json_schema"]["schema"]
    required = set(schema["required"])
    if set(packet) != required:
        errors.append("keys_invalid")

    verdict_key = "decision" if role in {"planner", "planning_judge", "final_judge"} else "status"
    verdict_schema = schema["properties"].get(verdict_key, {})
    if "const" in verdict_schema and packet.get(verdict_key) != verdict_schema["const"]:
        errors.append("verdict_invalid")
    if "enum" in verdict_schema and packet.get(verdict_key) not in verdict_schema["enum"]:
        errors.append("verdict_invalid")

    if role == "planner":
        packet_targets = packet.get("target_files")
        packets = packet.get("packets")
        if (
            packet_targets != targets
            or not isinstance(packet_targets, list)
            or any(not isinstance(item, str) for item in packet_targets or [])
            or len(packet_targets) != len(set(packet_targets or []))
        ):
            errors.append("target_files_mismatch")
        covered = [
            path
            for item in packets or []
            if isinstance(item, dict) and isinstance(item.get("files"), list)
            for path in item["files"]
        ]
        if (
            not isinstance(packets, list)
            or len(packets) != 1
            or any(
                not isinstance(item, dict)
                or set(item) != {"id", "files"}
                or not isinstance(item.get("id"), str)
                or not item["id"].strip()
                or not isinstance(item.get("files"), list)
                or not item["files"]
                or any(not isinstance(path, str) or path not in targets for path in item["files"])
                or len(item["files"]) != len(set(item["files"]))
                for item in packets or []
            )
            or sorted(covered) != sorted(targets)
            or len(covered) != len(set(covered))
        ):
            errors.append("packet_coupling_invalid")
        if not isinstance(packet.get("verification_command"), str) or not packet["verification_command"].strip():
            errors.append("verification_command_invalid")
        if (
            not isinstance(packet.get("constraints"), list)
            or not all(isinstance(item, str) for item in packet.get("constraints", []))
            or len(packet.get("constraints", [])) != len(set(packet.get("constraints", [])))
        ):
            errors.append("constraints_invalid")
    elif role == "builder":
        files = packet.get("files")
        paths = [item.get("path") for item in files or [] if isinstance(item, dict)]
        if paths != targets or len(paths) != len(set(paths)):
            errors.append("builder_paths_invalid")
        if not isinstance(files, list) or any(
            not isinstance(item, dict)
            or set(item) != {"path", "content"}
            or not isinstance(item.get("content"), str)
            or not item["content"].strip()
            or "```" in item["content"]
            for item in files or []
        ):
            errors.append("builder_files_invalid")
    else:
        if not isinstance(packet.get("rationale"), str) or not packet["rationale"].strip():
            errors.append("rationale_invalid")
        refs = packet.get("evidence_refs")
        if (
            not isinstance(refs, list)
            or any(not isinstance(ref, str) or ref not in allowed_evidence for ref in refs or [])
            or len(refs) != len(set(refs or []))
        ):
            errors.append("evidence_refs_invalid")
        if role in {"planning_judge", "build_judge", "verifier"}:
            list_key = "required_changes" if role == "planning_judge" else "missing_evidence"
            values = packet.get(list_key)
            if (
                not isinstance(values, list)
                or not all(isinstance(item, str) for item in values or [])
                or len(values) != len(set(values or []))
                or (
                    role in {"build_judge", "verifier"}
                    and any(item not in allowed_evidence for item in values or [])
                )
            ):
                errors.append(f"{list_key}_invalid")
        if role == "final_judge":
            risks = packet.get("residual_risks")
            if (
                not isinstance(risks, list)
                or not all(isinstance(item, str) for item in risks or [])
                or len(risks) != len(set(risks or []))
            ):
                errors.append("residual_risks_invalid")
            if packet.get("next_action") not in FINAL_JUDGE_NEXT_ACTIONS:
                errors.append("next_action_invalid")

    return {"valid": not errors, "errors": list(dict.fromkeys(errors))}


__all__ = [
    "FINAL_JUDGE_NEXT_ACTIONS",
    "FINAL_JUDGE_NEXT_DECISION_BY_ACTION",
    "FINAL_JUDGE_SCHEMA_VERSION",
    "SCHEMA_VERSION",
    "build_audition_contract",
    "validate_audition_packet",
]
