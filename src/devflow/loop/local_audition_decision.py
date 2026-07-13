"""Build and persist pending M1 audition Human Decision artifacts.

This module is deterministic and deliberately has no profile mutation path.
It records a proposed change for later human approval; it never applies one.
"""

from __future__ import annotations

from copy import deepcopy
import json
import math
import os
from pathlib import Path
import re
from tempfile import NamedTemporaryFile
from typing import Callable, Mapping, Sequence


_SAFE_COMPONENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_DISPOSITIONS = {"recommended", "ineligible", "provisional"}
_QUALIFICATION_STATUSES = {"qualified", "provisional"}
_QUALIFICATION_GATES = (
    "scorecard",
    "reliability",
    "three_repeat_evidence",
    "independent_review",
)
_METRICS = (
    "quality",
    "consistency",
    "mean_duration_seconds",
    "mean_total_tokens",
)
_PROFILE_TARGET_PREFIX = (
    "src/devflow/loop/profiles.yaml::profiles.mini-baseline.roles."
)


def _require_nonblank(name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a nonblank string")
    return value.strip()


def _safe_component(name: str, value: object) -> str:
    text = _require_nonblank(name, value)
    if not _SAFE_COMPONENT.fullmatch(text) or text in {".", ".."}:
        raise ValueError(f"{name} must be a safe path component")
    return text


def _unique_nonblank(name: str, values: object, *, required: bool = True) -> list[str]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise ValueError(f"{name} must be a sequence of unique nonblank strings")
    cleaned = [_require_nonblank(name, value) for value in values]
    if (required and not cleaned) or len(cleaned) != len(set(cleaned)):
        raise ValueError(f"{name} must contain unique nonblank strings")
    return cleaned


def _valid_metric(name: str, value: object) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value < 0
    ):
        raise ValueError(f"{name} must be finite and nonnegative")
    if name in {"quality", "consistency"} and value > 100:
        raise ValueError(f"{name} must not exceed 100")
    return float(value)


def _validated_role_results(role_results: object) -> list[dict]:
    if isinstance(role_results, (str, bytes)) or not isinstance(role_results, Sequence):
        raise ValueError("role_results must be a sequence")
    if not role_results:
        raise ValueError("role_results must not be empty")
    validated: list[dict] = []
    identities: set[tuple[str, str]] = set()
    for index, source in enumerate(role_results):
        if not isinstance(source, Mapping):
            raise ValueError("role_results must contain mappings")
        result = deepcopy(dict(source))
        role = _safe_component(f"role_results[{index}].role", result.get("role"))
        candidate = _require_nonblank(
            f"role_results[{index}].candidate_id", result.get("candidate_id")
        )
        identity = (role, candidate)
        if identity in identities:
            raise ValueError("role_results must have unique role/candidate identities")
        identities.add(identity)

        if result.get("disposition") not in _DISPOSITIONS:
            raise ValueError(f"role_results[{index}].disposition is invalid")
        if result.get("qualification_status") not in _QUALIFICATION_STATUSES:
            raise ValueError(f"role_results[{index}].qualification_status is invalid")

        gates = result.get("qualification_gates")
        if not isinstance(gates, Mapping):
            raise ValueError(f"role_results[{index}].qualification_gates is invalid")
        if set(gates) != set(_QUALIFICATION_GATES) or any(
            type(gates[gate]) is not bool for gate in _QUALIFICATION_GATES
        ):
            raise ValueError(
                f"role_results[{index}].qualification_gates must contain exact boolean gates"
            )

        reliability = result.get("reliability")
        if not isinstance(reliability, Mapping) or type(reliability.get("eligible")) is not bool:
            raise ValueError(f"role_results[{index}].reliability is invalid")
        reasons = _unique_nonblank(
            f"role_results[{index}].reliability.reasons",
            reliability.get("reasons"),
            required=False,
        )
        if reliability["eligible"] and reasons:
            raise ValueError("eligible reliability evidence cannot contain failure reasons")
        if not reliability["eligible"] and not reasons:
            raise ValueError("ineligible reliability evidence requires reasons")

        metrics = result.get("metrics")
        if not isinstance(metrics, Mapping) or set(metrics) != set(_METRICS):
            raise ValueError(f"role_results[{index}].metrics must contain exact metrics")
        normalized_metrics = {
            metric: _valid_metric(metric, metrics[metric]) for metric in _METRICS
        }
        result["role"] = role
        result["candidate_id"] = candidate
        result["qualification_gates"] = {
            gate: gates[gate] for gate in _QUALIFICATION_GATES
        }
        result["reliability"] = {
            "eligible": reliability["eligible"],
            "reasons": reasons,
        }
        result["metrics"] = normalized_metrics
        validated.append(result)
    return validated


def human_decision_paths(root: Path | str, run_id: str) -> tuple[Path, Path]:
    """Return the stable JSON and Markdown paths for one audition run."""
    safe_run_id = _safe_component("run_id", run_id)
    directory = (
        Path(root)
        / ".devflow"
        / "dogfood"
        / "m1-role-audition"
        / safe_run_id
    )
    return directory / "human-decision.json", directory / "human-decision.md"


def build_pending_human_decision(
    *,
    run_id: str,
    proposed_role_mappings: Mapping[str, str],
    role_results: Sequence[Mapping],
    evidence_fingerprints: Sequence[str],
    verification_commands: Sequence[str],
    approval_patch: str,
    rollback_patch: str,
    remaining_risks: Sequence[str],
) -> dict:
    """Build a validated pending decision without applying its proposal."""
    safe_run_id = _safe_component("run_id", run_id)
    if not isinstance(proposed_role_mappings, Mapping):
        raise ValueError("proposed_role_mappings must be a mapping")
    mappings: dict[str, str] = {}
    for raw_role, raw_candidate in proposed_role_mappings.items():
        role = _safe_component("proposed role", raw_role)
        candidate = _require_nonblank("proposed candidate", raw_candidate)
        mappings[role] = candidate

    results = _validated_role_results(role_results)
    for role, candidate in mappings.items():
        matches = [
            result
            for result in results
            if result["role"] == role and result["candidate_id"] == candidate
        ]
        if len(matches) != 1:
            raise ValueError(
                f"proposed mapping {role} -> {candidate} requires one matching role result"
            )
        result = matches[0]
        if result["disposition"] != "recommended":
            raise ValueError(f"proposed mapping {role} is not recommended")
        if result["qualification_status"] != "qualified":
            raise ValueError(f"proposed mapping {role} is not qualified")
        for gate in _QUALIFICATION_GATES:
            if result["qualification_gates"][gate] is not True:
                raise ValueError(f"proposed mapping {role} failed {gate}")
        if result["reliability"]["eligible"] is not True:
            raise ValueError(f"proposed mapping {role} failed reliability")

    return {
        "schema_version": 1,
        "run_id": safe_run_id,
        "status": "pending",
        "proposed_role_mappings": dict(sorted(mappings.items())),
        "evidence_fingerprints": _unique_nonblank(
            "evidence_fingerprints", evidence_fingerprints
        ),
        "approved_at": None,
        "verification_commands": _unique_nonblank(
            "verification_commands", verification_commands
        ),
        "rollback_patch": _require_nonblank("rollback_patch", rollback_patch),
        "no_profile_changes_applied": True,
        "role_results": results,
        "profile_targets": {
            role: f"{_PROFILE_TARGET_PREFIX}{role}" for role in sorted(mappings)
        },
        "approval_patch": _require_nonblank("approval_patch", approval_patch),
        "remaining_risks": _unique_nonblank("remaining_risks", remaining_risks),
    }


def build_pending_human_decision_from_audition(
    *,
    run_id: str,
    rankings: Sequence[Mapping],
    qualifications: Sequence[Mapping],
    verification_commands: Sequence[str],
    approval_patch: str,
    rollback_patch: str,
    remaining_risks: Sequence[str],
) -> dict:
    """Assemble a pending decision directly from scorecard and gate outputs."""

    if isinstance(rankings, (str, bytes)) or not isinstance(rankings, Sequence):
        raise ValueError("rankings must be a sequence")
    if isinstance(qualifications, (str, bytes)) or not isinstance(qualifications, Sequence):
        raise ValueError("qualifications must be a sequence")
    qualification_by_identity: dict[tuple[str, str], Mapping] = {}
    for source in qualifications:
        if not isinstance(source, Mapping):
            raise ValueError("qualifications must contain mappings")
        role = _safe_component("qualification role", source.get("role"))
        candidate = _require_nonblank("qualification model", source.get("model"))
        identity = (role, candidate)
        if identity in qualification_by_identity:
            raise ValueError("qualifications must have unique role/model identities")
        qualification_by_identity[identity] = source

    role_results: list[dict] = []
    evidence_fingerprints: list[str] = []
    mappings: dict[str, str] = {}
    seen_roles: set[str] = set()
    for ranking in rankings:
        if not isinstance(ranking, Mapping):
            raise ValueError("rankings must contain mappings")
        role = _safe_component("ranking role", ranking.get("role"))
        if role in seen_roles:
            raise ValueError("rankings must have unique roles")
        seen_roles.add(role)
        ranked = ranking.get("ranked")
        ineligible = ranking.get("ineligible")
        if not isinstance(ranked, list) or not isinstance(ineligible, list):
            raise ValueError("ranking must contain ranked and ineligible lists")
        identities: set[str] = set()
        for candidate_data in ranked:
            if not isinstance(candidate_data, Mapping):
                raise ValueError("ranked candidates must be mappings")
            candidate = _require_nonblank("ranked candidate_id", candidate_data.get("candidate_id"))
            if candidate in identities:
                raise ValueError("ranking candidates must be unique per role")
            identities.add(candidate)
            artifact = _require_nonblank("artifact_fingerprint", candidate_data.get("artifact_fingerprint"))
            runtime = _require_nonblank("runtime_fingerprint", candidate_data.get("runtime_fingerprint"))
            evidence_fingerprints.append(f"{artifact}:{runtime}")
            qualification = qualification_by_identity.get((role, candidate), {})
            gates = qualification.get("qualification_gates") if isinstance(qualification, Mapping) else None
            normalized_gates = {
                gate: gates.get(gate) is True if isinstance(gates, Mapping) else False
                for gate in _QUALIFICATION_GATES
            }
            qualified = qualification.get("status") == "qualified" and all(normalized_gates.values())
            if qualified and role not in mappings:
                disposition = "recommended"
                mappings[role] = candidate
            else:
                disposition = "provisional"
            reasons = [] if normalized_gates["reliability"] else ["reliability_not_passed"]
            role_results.append({
                "role": role,
                "candidate_id": candidate,
                "disposition": disposition,
                "qualification_status": "qualified" if qualified else "provisional",
                "qualification_gates": normalized_gates,
                "reliability": {"eligible": normalized_gates["reliability"], "reasons": reasons},
                "metrics": {
                    "quality": _valid_metric("quality", candidate_data.get("quality")),
                    "consistency": _valid_metric("consistency", candidate_data.get("repeat_consistency")),
                    "mean_duration_seconds": _valid_metric("mean_duration_seconds", candidate_data.get("mean_duration_seconds")),
                    "mean_total_tokens": _valid_metric("mean_total_tokens", candidate_data.get("mean_total_tokens")),
                },
            })
        for candidate_data in ineligible:
            if not isinstance(candidate_data, Mapping):
                raise ValueError("ineligible candidates must be mappings")
            candidate = _require_nonblank("ineligible candidate_id", candidate_data.get("candidate_id"))
            if candidate in identities:
                raise ValueError("ranking candidates must be unique per role")
            identities.add(candidate)
            artifact = _require_nonblank("artifact_fingerprint", candidate_data.get("artifact_fingerprint"))
            runtime = _require_nonblank("runtime_fingerprint", candidate_data.get("runtime_fingerprint"))
            evidence_fingerprints.append(f"{artifact}:{runtime}")
            reasons = _unique_nonblank("ineligible reasons", candidate_data.get("reasons"))
            role_results.append({
                "role": role,
                "candidate_id": candidate,
                "disposition": "ineligible",
                "qualification_status": "provisional",
                "qualification_gates": {gate: False for gate in _QUALIFICATION_GATES},
                "reliability": {"eligible": False, "reasons": reasons},
                "metrics": {metric: 0.0 for metric in _METRICS},
            })
    return build_pending_human_decision(
        run_id=run_id,
        proposed_role_mappings=mappings,
        role_results=role_results,
        evidence_fingerprints=list(dict.fromkeys(evidence_fingerprints)),
        verification_commands=verification_commands,
        approval_patch=approval_patch,
        rollback_patch=rollback_patch,
        remaining_risks=remaining_risks,
    )


def _validate_pending_record(record: object) -> dict:
    if not isinstance(record, Mapping):
        raise ValueError("record must be a mapping")
    required = {
        "schema_version",
        "run_id",
        "status",
        "proposed_role_mappings",
        "evidence_fingerprints",
        "approved_at",
        "verification_commands",
        "rollback_patch",
        "no_profile_changes_applied",
        "role_results",
        "profile_targets",
        "approval_patch",
        "remaining_risks",
    }
    if set(record) != required:
        raise ValueError("record must contain the exact pending decision fields")
    if record.get("schema_version") != 1 or type(record.get("schema_version")) is not int:
        raise ValueError("schema_version must be 1")
    if record.get("status") != "pending":
        raise ValueError("status must remain pending until human action")
    if record.get("approved_at") is not None:
        raise ValueError("pending approved_at must be null")
    if record.get("no_profile_changes_applied") is not True:
        raise ValueError("pending record must state no profile changes applied")
    rebuilt = build_pending_human_decision(
        run_id=record.get("run_id"),
        proposed_role_mappings=record.get("proposed_role_mappings"),
        role_results=record.get("role_results"),
        evidence_fingerprints=record.get("evidence_fingerprints"),
        verification_commands=record.get("verification_commands"),
        approval_patch=record.get("approval_patch"),
        rollback_patch=record.get("rollback_patch"),
        remaining_risks=record.get("remaining_risks"),
    )
    if dict(record) != rebuilt:
        raise ValueError("record is not canonical pending decision data")
    return rebuilt


def render_human_decision_markdown(record: Mapping) -> str:
    """Render the validated pending decision for human review."""
    data = _validate_pending_record(record)
    lines = [
        "# Pending Human Decision",
        "",
        "> **NO PROFILE CHANGES APPLIED**",
        "",
        f"Run: `{data['run_id']}`",
        "",
        "## Role recommendations and ineligibility",
        "",
    ]
    for result in data["role_results"]:
        disposition = result["disposition"].upper()
        lines.append(
            f"### {result['role']} / {result['candidate_id']}: {disposition}"
        )
        lines.extend(
            [
                "",
                f"- Qualification: {result['qualification_status']}",
                f"- Reliability: {'eligible' if result['reliability']['eligible'] else 'ineligible'}",
                f"- Quality: {result['metrics']['quality']}",
                f"- Consistency: {result['metrics']['consistency']}",
                f"- Duration: {result['metrics']['mean_duration_seconds']} seconds mean",
                f"- Token use: {result['metrics']['mean_total_tokens']} mean total tokens",
            ]
        )
        reasons = result["reliability"]["reasons"]
        if reasons:
            lines.append(f"- Reasons: {', '.join(reasons)}")
        if result["disposition"] == "recommended":
            lines.append(f"- Proposed mapping: {result['role']} -> {result['candidate_id']}")
        lines.append("")

    lines.extend(["## Exact profile targets", ""])
    if data["profile_targets"]:
        for role, target in data["profile_targets"].items():
            lines.append(f"- `{role}`: `{target}`")
    else:
        lines.append("- No eligible role mapping is proposed.")

    lines.extend(["", "## Verification commands", ""])
    for command in data["verification_commands"]:
        lines.append(f"- `{command}`")
    lines.extend(
        [
            "",
            "## First approval patch",
            "",
            "```diff",
            data["approval_patch"],
            "```",
            "",
            "## Remaining risks",
            "",
        ]
    )
    lines.extend(f"- {risk}" for risk in data["remaining_risks"])
    lines.extend(["", "## Evidence fingerprints", ""])
    lines.extend(f"- `{fingerprint}`" for fingerprint in data["evidence_fingerprints"])
    lines.extend(
        [
            "",
            "## Rollback patch",
            "",
            "```diff",
            data["rollback_patch"],
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def persist_human_decision(
    root: Path | str,
    record: Mapping,
    *,
    commit: Callable[[Path, Path], None] = os.link,
) -> tuple[Path, Path]:
    """Transactionally publish a write-once, crash-recoverable artifact pair."""
    data = _validate_pending_record(record)
    json_path, markdown_path = human_decision_paths(root, data["run_id"])
    json_path.parent.mkdir(parents=True, exist_ok=True)
    payloads = (
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        render_human_decision_markdown(data),
    )

    existing = (json_path.exists(), markdown_path.exists())
    if existing == (True, True):
        raise FileExistsError(json_path)
    if existing[0] and json_path.read_text(encoding="utf-8") != payloads[0]:
        raise FileExistsError(json_path)
    if existing[1] and markdown_path.read_text(encoding="utf-8") != payloads[1]:
        raise FileExistsError(markdown_path)

    targets = (json_path, markdown_path)
    missing_indexes = [index for index, present in enumerate(existing) if not present]
    temporary_paths: dict[int, Path] = {}
    published_indexes: set[int] = set()

    def published_by_this_call(index: int) -> bool:
        temporary_path = temporary_paths[index]
        target = targets[index]
        try:
            return target.exists() and os.path.samefile(temporary_path, target)
        except OSError:
            return False

    def publish(index: int) -> None:
        try:
            commit(temporary_paths[index], targets[index])
        except BaseException:
            if published_by_this_call(index):
                published_indexes.add(index)
            raise
        published_indexes.add(index)
    try:
        for index in missing_indexes:
            target = targets[index]
            with NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=target.parent,
                prefix=f".{target.stem}-",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                temporary_paths[index] = temporary_path
                temporary.write(payloads[index])
                temporary.flush()
                os.fsync(temporary.fileno())

        if existing[0]:
            publish(1)
            return json_path, markdown_path
        if existing[1]:
            publish(0)
            return json_path, markdown_path

        publish(0)
        try:
            publish(1)
        except BaseException:
            for index in sorted(published_indexes, reverse=True):
                if published_by_this_call(index):
                    targets[index].unlink(missing_ok=True)
            raise
        return json_path, markdown_path
    finally:
        for temporary_path in temporary_paths.values():
            temporary_path.unlink(missing_ok=True)


__all__ = [
    "build_pending_human_decision",
    "build_pending_human_decision_from_audition",
    "human_decision_paths",
    "persist_human_decision",
    "render_human_decision_markdown",
]
