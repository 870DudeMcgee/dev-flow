from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
import json
import os
import shlex
import subprocess
import sys

import yaml

from devflow.control_room.machine_capability import MachineCapability, discover_machine_capability
from devflow.control_room.paths import relative_path
from devflow.control_room.persistence import atomic_write_text, utc_now


DEFAULT_MANIFEST_PATH = Path(__file__).with_name("data") / "local_model_expected_profiles.yaml"
EXPECTED_LANE_IDS = (
    "hermes-qwen32-latest",
    "hermes-gemma12b-latest",
    "hermes-qwopus-35b",
    "hermes-qwen36-27b-q5-mtp",
    "hermes-gemma4-e4b",
    "hermes-ornith-9b",
    "hermes-ornith-35b",
    "hermes-minimaxm3",
    "hermes-qwen37plus",
    "hermes-sonnet46",
    "hermes-opus48",
    "hermes-codex-gpt55",
)
SUPPORTED_PROVIDER_ONBOARDING_ADAPTERS = {"ollama_chat", "openai_compatible", "openai_chat", "anthropic_messages", "gemini"}
SAFE_PROVISION_COMMAND_PREFIXES = (
    ("agent", "add-provider"),
    ("agent", "add-model"),
    ("local-model", "start"),
)
MAX_EVIDENCE_OUTPUT_CHARS = 12_000

__all__ = [
    "DEFAULT_MANIFEST_PATH",
    "EXPECTED_LANE_IDS",
    "ExpectedLocalModelLane",
    "LocalModelExpectedProfilesManifest",
    "LocalModelReadinessError",
    "apply_local_model_readiness_plan",
    "build_local_model_readiness_plan",
    "load_expected_local_model_manifest",
    "render_local_model_readiness_apply_result",
    "render_local_model_readiness_plan",
]


class LocalModelReadinessError(ValueError):
    pass


@dataclass(frozen=True)
class ExpectedLocalModelLane:
    lane_id: str
    profile_id: str
    provider_id: str
    model_id: str
    adapter: str
    role: str
    authority: str
    min_ram_gb: int
    ideal_ram_gb: int
    weight_class: str
    quant_policy: str
    fallback_lanes: tuple[str, ...]
    base_url: str | None = None
    port: int | None = None
    local_server_backed: bool = False
    api_key_env: str | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "lane_id": self.lane_id,
            "profile_id": self.profile_id,
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "adapter": self.adapter,
            "role": self.role,
            "authority": self.authority,
            "min_ram_gb": self.min_ram_gb,
            "ideal_ram_gb": self.ideal_ram_gb,
            "weight_class": self.weight_class,
            "quant_policy": self.quant_policy,
            "base_url": self.base_url,
            "port": self.port,
            "local_server_backed": self.local_server_backed,
            "api_key_env": self.api_key_env,
            "fallback_lanes": list(self.fallback_lanes),
        }


@dataclass(frozen=True)
class LocalModelExpectedProfilesManifest:
    schema_version: int
    lanes: dict[str, ExpectedLocalModelLane]
    source_path: Path

    def require_lane(self, lane_id: str) -> ExpectedLocalModelLane:
        try:
            return self.lanes[lane_id]
        except KeyError as exc:
            raise LocalModelReadinessError(f"Unknown local model lane '{lane_id}'.") from exc

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source_path": self.source_path.as_posix(),
            "lanes": {lane_id: lane.to_payload() for lane_id, lane in self.lanes.items()},
        }


def load_expected_local_model_manifest(path: Path | None = None) -> LocalModelExpectedProfilesManifest:
    source_path = (path or DEFAULT_MANIFEST_PATH).resolve()
    try:
        payload = yaml.safe_load(source_path.read_text(encoding="utf-8")) or {}
    except OSError as exc:
        raise LocalModelReadinessError(f"Could not read local model manifest: {source_path}") from exc
    if not isinstance(payload, dict):
        raise LocalModelReadinessError("Local model manifest root must be a mapping.")
    schema_version = payload.get("schema_version")
    if schema_version != 1:
        raise LocalModelReadinessError(f"Unsupported local model manifest schema_version: {schema_version!r}.")
    raw_lanes = payload.get("lanes")
    if not isinstance(raw_lanes, dict):
        raise LocalModelReadinessError("Local model manifest must contain a lanes mapping.")

    missing = [lane_id for lane_id in EXPECTED_LANE_IDS if lane_id not in raw_lanes]
    extra = [lane_id for lane_id in raw_lanes if lane_id not in EXPECTED_LANE_IDS]
    if missing or extra:
        details = []
        if missing:
            details.append(f"missing lanes: {', '.join(missing)}")
        if extra:
            details.append(f"unexpected lanes: {', '.join(extra)}")
        raise LocalModelReadinessError("; ".join(details))

    lanes = {lane_id: _parse_lane(lane_id, raw_lanes[lane_id]) for lane_id in EXPECTED_LANE_IDS}
    for lane in lanes.values():
        unknown_fallbacks = [fallback for fallback in lane.fallback_lanes if fallback not in lanes]
        if unknown_fallbacks:
            raise LocalModelReadinessError(
                f"Lane '{lane.lane_id}' references unknown fallback lanes: {', '.join(unknown_fallbacks)}."
            )
    return LocalModelExpectedProfilesManifest(schema_version=1, lanes=lanes, source_path=source_path)


def build_local_model_readiness_plan(
    root: Path,
    *,
    manifest: LocalModelExpectedProfilesManifest | None = None,
    agent_catalog: dict[str, Any] | None = None,
    inventory: dict[str, Any] | None = None,
    machine: MachineCapability | None = None,
) -> dict[str, Any]:
    manifest = manifest or load_expected_local_model_manifest()
    machine = machine or discover_machine_capability()
    if agent_catalog is None:
        from devflow.control_room.agent_catalog import build_agent_catalog

        agent_catalog = build_agent_catalog(root)
    if inventory is None:
        from devflow.control_room.local_model_inventory import build_local_model_inventory

        inventory = build_local_model_inventory(agent_catalog)

    provider_rows = _dict_rows(agent_catalog.get("providers"))
    profile_rows = _dict_rows(agent_catalog.get("profiles"))
    inventory_rows = _dict_rows(inventory.get("rows"))
    lanes = [
        _lane_readiness(
            lane,
            machine=machine,
            provider_rows=provider_rows,
            profile_rows=profile_rows,
            inventory_rows=inventory_rows,
        )
        for lane in manifest.lanes.values()
    ]
    commands = _unique_commands(lanes)
    start_commands = _unique_commands(lanes, field="start_commands")
    ready_count = sum(1 for lane in lanes if lane["ready"])
    return {
        "schema_version": 1,
        "manifest_schema_version": manifest.schema_version,
        "manifest_path": manifest.source_path.as_posix(),
        "machine": machine.to_payload(),
        "inventory_summary": dict(inventory.get("summary")) if isinstance(inventory.get("summary"), dict) else {},
        "lanes": lanes,
        "provision_commands": commands,
        "start_commands": start_commands,
        "summary": {
            "lane_count": len(lanes),
            "ready_count": ready_count,
            "blocked_count": sum(1 for lane in lanes if str(lane["readiness"]).startswith("blocked")),
            "needs_action_count": sum(1 for lane in lanes if lane["provision_commands"]),
            "start_command_count": len(start_commands),
        },
    }


def render_local_model_readiness_plan(plan: dict[str, Any]) -> list[str]:
    summary = dict(plan.get("summary")) if isinstance(plan.get("summary"), dict) else {}
    machine = dict(plan.get("machine")) if isinstance(plan.get("machine"), dict) else {}
    lane_count = int(summary.get("lane_count") or 0)
    ready_count = int(summary.get("ready_count") or 0)
    blocked_count = int(summary.get("blocked_count") or 0)
    needs_action_count = int(summary.get("needs_action_count") or 0)
    memory = machine.get("total_memory_gb")
    machine_label = f"{memory}GB {machine.get('machine_class')}" if memory is not None else str(machine.get("machine_class") or "unknown")

    lines = [
        "Local model readiness (dry run)",
        f"manifest: {plan.get('manifest_path')}",
        f"machine: {machine_label}",
        f"readiness: {ready_count}/{lane_count} lanes ready; {blocked_count} blocked; {needs_action_count} need onboarding",
    ]

    problem_lanes = [
        lane
        for lane in _dict_rows(plan.get("lanes"))
        if not bool(lane.get("ready")) or lane.get("ram_status") in {"minimum", "insufficient", "unknown"}
    ]
    lines.append("Missing / under-spec lanes:")
    if not problem_lanes:
        lines.append("  - none")
    for lane in problem_lanes:
        provider = "registered" if lane.get("provider_registered") else "missing"
        profile = "registered" if lane.get("profile_registered") else "missing"
        inventory = lane.get("inventory_status") or "unchecked"
        lines.append(
            "  - "
            f"{lane.get('lane_id')}: {lane.get('readiness')} "
            f"(ram={lane.get('ram_status')}, provider={provider}, profile={profile}, inventory={inventory})"
        )
        if lane.get("provider_missing_env"):
            api_key_env = lane.get("api_key_env") or "provider api key"
            lines.append(f"    env: set {api_key_env} before using this lane")

    _append_command_section(lines, "Onboarding commands:", _dict_rows(plan.get("provision_commands")))
    _append_command_section(lines, "Start commands:", _dict_rows(plan.get("start_commands")))
    lines.append("apply: devflow doctor --provision --apply")
    return lines


def apply_local_model_readiness_plan(
    root: Path,
    *,
    plan: dict[str, Any] | None = None,
    runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
) -> dict[str, Any]:
    readiness = plan or build_local_model_readiness_plan(root)
    run_id = _run_id()
    run_dir = root / ".devflow" / "local-model-readiness" / run_id
    command_runner = runner or subprocess.run
    started_at = utc_now().isoformat()
    results: list[dict[str, Any]] = []
    commands_to_apply = _dict_rows(readiness.get("provision_commands")) + _dict_rows(readiness.get("start_commands"))
    for index, command in enumerate(commands_to_apply, start=1):
        evidence = _apply_provision_command(
            root,
            command,
            index=index,
            run_id=run_id,
            run_dir=run_dir,
            runner=command_runner,
        )
        results.append(_command_result_summary(evidence))
        if evidence.get("status") in {"blocked", "failed"}:
            break

    applied_count = sum(1 for result in results if result["status"] == "succeeded")
    failed_count = sum(1 for result in results if result["status"] == "failed")
    blocked_count = sum(1 for result in results if result["status"] == "blocked")
    skipped_count = sum(1 for result in results if result["status"] == "skipped")
    if failed_count or blocked_count:
        status = "failed"
    elif applied_count:
        status = "applied"
    elif skipped_count:
        status = "no_supported_commands"
    else:
        status = "no_action"

    payload = {
        "schema_version": 1,
        "action": "doctor_provision_apply",
        "status": status,
        "run_id": run_id,
        "started_at": started_at,
        "completed_at": utc_now().isoformat(),
        "readiness_summary": dict(readiness.get("summary")) if isinstance(readiness.get("summary"), dict) else {},
        "command_count": len(results),
        "provision_command_count": len(_dict_rows(readiness.get("provision_commands"))),
        "start_command_count": len(_dict_rows(readiness.get("start_commands"))),
        "applied_count": applied_count,
        "failed_count": failed_count,
        "blocked_count": blocked_count,
        "skipped_count": skipped_count,
        "commands": results,
        "run_path": relative_path(root, run_dir / "run.json"),
    }
    atomic_write_text(run_dir / "run.json", json.dumps(payload, indent=2, sort_keys=True) + "\n")
    atomic_write_text(root / ".devflow" / "local-model-readiness" / "latest.json", json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return payload


def render_local_model_readiness_apply_result(result: dict[str, Any]) -> list[str]:
    lines = [
        "Local model readiness provision apply",
        f"status: {result.get('status')}",
        (
            f"commands: {result.get('command_count', 0)} "
            f"(applied={result.get('applied_count', 0)}, failed={result.get('failed_count', 0)}, "
            f"blocked={result.get('blocked_count', 0)}, skipped={result.get('skipped_count', 0)})"
        ),
        f"run_evidence: {result.get('run_path')}",
    ]
    for command in _dict_rows(result.get("commands")):
        lines.append(f"- {command.get('status')}: {command.get('command') or command.get('reason')}")
        if command.get("evidence_path"):
            lines.append(f"  evidence: {command.get('evidence_path')}")
        if command.get("exit_code") not in (None, 0):
            lines.append(f"  exit_code: {command.get('exit_code')}")
        if command.get("reason") and command.get("status") in {"blocked", "skipped"}:
            lines.append(f"  reason: {command.get('reason')}")
    return lines


def _parse_lane(lane_id: str, raw_lane: object) -> ExpectedLocalModelLane:
    if not isinstance(raw_lane, dict):
        raise LocalModelReadinessError(f"Lane '{lane_id}' must be a mapping.")
    min_ram_gb = _required_int(raw_lane, "min_ram_gb", lane_id)
    ideal_ram_gb = _required_int(raw_lane, "ideal_ram_gb", lane_id)
    if ideal_ram_gb < min_ram_gb:
        raise LocalModelReadinessError(f"Lane '{lane_id}' ideal_ram_gb must be greater than or equal to min_ram_gb.")
    return ExpectedLocalModelLane(
        lane_id=lane_id,
        profile_id=_required_text(raw_lane, "profile_id", lane_id),
        provider_id=_required_text(raw_lane, "provider_id", lane_id),
        model_id=_required_text(raw_lane, "model_id", lane_id),
        adapter=_required_text(raw_lane, "adapter", lane_id),
        role=_required_text(raw_lane, "role", lane_id),
        authority=_required_text(raw_lane, "authority", lane_id),
        min_ram_gb=min_ram_gb,
        ideal_ram_gb=ideal_ram_gb,
        weight_class=_required_text(raw_lane, "weight_class", lane_id),
        quant_policy=_required_text(raw_lane, "quant_policy", lane_id),
        base_url=_optional_text(raw_lane.get("base_url")),
        port=_optional_int(raw_lane.get("port"), field="port", lane_id=lane_id),
        local_server_backed=bool(raw_lane.get("local_server_backed", False)),
        api_key_env=_optional_text(raw_lane.get("api_key_env")),
        fallback_lanes=tuple(_required_string_list(raw_lane, "fallback_lanes", lane_id)),
    )


def _lane_readiness(
    lane: ExpectedLocalModelLane,
    *,
    machine: MachineCapability,
    provider_rows: list[dict[str, Any]],
    profile_rows: list[dict[str, Any]],
    inventory_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    ram_status = _ram_status(machine.total_memory_gb, min_ram_gb=lane.min_ram_gb, ideal_ram_gb=lane.ideal_ram_gb)
    provider = _provider_row(provider_rows, lane.provider_id)
    profile = _profile_row(profile_rows, lane.profile_id)
    inventory_row = _inventory_row(inventory_rows, lane)
    provider_registered = provider is not None
    profile_registered = profile is not None
    provider_missing_env = bool(provider and provider.get("api_key_env_missing"))
    inventory_status = _text(inventory_row.get("status")) if inventory_row else None

    readiness = _readiness_status(
        lane,
        ram_status=ram_status,
        provider_registered=provider_registered,
        profile_registered=profile_registered,
        provider_missing_env=provider_missing_env,
        inventory_status=inventory_status,
    )
    commands = _provision_commands(lane, provider_registered=provider_registered, profile_registered=profile_registered)
    start_commands = _start_commands(lane, readiness=readiness)
    return {
        "lane_id": lane.lane_id,
        "profile_id": lane.profile_id,
        "provider_id": lane.provider_id,
        "model_id": lane.model_id,
        "api_key_env": lane.api_key_env,
        "adapter": lane.adapter,
        "role": lane.role,
        "authority": lane.authority,
        "min_ram_gb": lane.min_ram_gb,
        "ideal_ram_gb": lane.ideal_ram_gb,
        "weight_class": lane.weight_class,
        "quant_policy": lane.quant_policy,
        "base_url": lane.base_url,
        "port": lane.port,
        "local_server_backed": lane.local_server_backed,
        "fallback_lanes": list(lane.fallback_lanes),
        "ram_status": ram_status,
        "readiness": readiness,
        "ready": readiness in {"ready", "ready_with_ram_caution"},
        "provider_registered": provider_registered,
        "profile_registered": profile_registered,
        "provider_missing_env": provider_missing_env,
        "inventory_status": inventory_status,
        "inventory_row_id": _text(inventory_row.get("row_id")) if inventory_row else None,
        "provision_commands": commands,
        "start_commands": start_commands,
    }


def _readiness_status(
    lane: ExpectedLocalModelLane,
    *,
    ram_status: str,
    provider_registered: bool,
    profile_registered: bool,
    provider_missing_env: bool,
    inventory_status: str | None,
) -> str:
    if ram_status == "insufficient":
        return "blocked_ram"
    if provider_missing_env:
        return "blocked_env"
    if not provider_registered:
        return "needs_provider"
    if not profile_registered:
        return "needs_profile"
    if inventory_status in {"available", "ready"}:
        return "ready_with_ram_caution" if ram_status == "minimum" else "ready"
    if inventory_status in {"unavailable", "missing"}:
        return "local_server_unavailable" if lane.local_server_backed else "model_unavailable"
    if inventory_status == "disabled":
        return "blocked_disabled"
    if inventory_status == "needs_profile":
        return "needs_profile"
    if lane.local_server_backed:
        return "local_server_unchecked"
    if lane.provider_id == "ollama" or lane.adapter == "ollama_chat":
        return "model_unchecked"
    return "ready_with_ram_caution" if ram_status == "minimum" else "ready"


def _ram_status(memory_gb: int | None, *, min_ram_gb: int, ideal_ram_gb: int) -> str:
    if min_ram_gb <= 0 and ideal_ram_gb <= 0:
        return "not_applicable"
    if memory_gb is None:
        return "unknown"
    if memory_gb < min_ram_gb:
        return "insufficient"
    if ideal_ram_gb > 0 and memory_gb < ideal_ram_gb:
        return "minimum"
    return "ideal"


def _provision_commands(
    lane: ExpectedLocalModelLane,
    *,
    provider_registered: bool,
    profile_registered: bool,
) -> list[dict[str, Any]]:
    commands: list[dict[str, Any]] = []
    if not provider_registered:
        if lane.adapter not in SUPPORTED_PROVIDER_ONBOARDING_ADAPTERS:
            commands.append(
                {
                    "kind": "provider",
                    "lane_id": lane.lane_id,
                    "provider_id": lane.provider_id,
                    "profile_id": lane.profile_id,
                    "supported": False,
                    "command": None,
                    "reason": f"Provider adapter '{lane.adapter}' is not supported by devflow agent add-provider.",
                }
            )
        elif lane.base_url:
            commands.append(
                {
                    "kind": "provider",
                    "lane_id": lane.lane_id,
                    "provider_id": lane.provider_id,
                    "profile_id": lane.profile_id,
                    "supported": True,
                    "command": _add_provider_command(lane),
                    "argv": _add_provider_argv(lane),
                    "reason": f"Register provider '{lane.provider_id}' for lane '{lane.lane_id}'.",
                }
            )
    if not profile_registered and lane.adapter in SUPPORTED_PROVIDER_ONBOARDING_ADAPTERS:
        commands.append(
            {
                "kind": "model",
                "lane_id": lane.lane_id,
                "provider_id": lane.provider_id,
                "profile_id": lane.profile_id,
                "supported": True,
                "command": _add_model_command(lane),
                "argv": _add_model_argv(lane),
                "reason": f"Register model profile '{lane.profile_id}' for lane '{lane.lane_id}'.",
            }
        )
    elif not profile_registered and lane.adapter not in SUPPORTED_PROVIDER_ONBOARDING_ADAPTERS:
        commands.append(
            {
                "kind": "model",
                "lane_id": lane.lane_id,
                "provider_id": lane.provider_id,
                "profile_id": lane.profile_id,
                "supported": False,
                "command": None,
                "reason": f"Profile adapter '{lane.adapter}' is not supported by devflow agent add-model.",
            }
        )
    return commands


def _start_commands(lane: ExpectedLocalModelLane, *, readiness: str) -> list[dict[str, Any]]:
    if not lane.local_server_backed or readiness in {"ready", "ready_with_ram_caution", "blocked_ram"}:
        return []
    profile = _managed_start_profile(lane)
    if not profile:
        return [
            {
                "kind": "start",
                "lane_id": lane.lane_id,
                "provider_id": lane.provider_id,
                "profile_id": lane.profile_id,
                "supported": False,
                "command": None,
                "reason": (
                    f"No managed devflow local-model start profile is registered for lane '{lane.lane_id}'. "
                    f"Start an OpenAI-compatible server at {lane.base_url} before using this lane."
                ),
            }
        ]
    argv = ["devflow", "local-model", "start", profile, "--replace", "--json"]
    return [
        {
            "kind": "start",
            "lane_id": lane.lane_id,
            "provider_id": lane.provider_id,
            "profile_id": lane.profile_id,
            "supported": True,
            "command": " ".join(shlex.quote(part) for part in argv),
            "argv": argv,
            "reason": f"Start managed local model server for lane '{lane.lane_id}'.",
        }
    ]


def _add_provider_command(lane: ExpectedLocalModelLane) -> str:
    return " ".join(shlex.quote(part) for part in _add_provider_argv(lane))


def _add_provider_argv(lane: ExpectedLocalModelLane) -> list[str]:
    parts = [
        "devflow",
        "agent",
        "add-provider",
        lane.provider_id,
        "--adapter",
        lane.adapter,
        "--base-url",
        lane.base_url or "",
    ]
    if lane.api_key_env:
        parts.extend(["--api-key-env", lane.api_key_env])
    parts.append("--json")
    return parts


def _add_model_command(lane: ExpectedLocalModelLane) -> str:
    return " ".join(shlex.quote(part) for part in _add_model_argv(lane))


def _add_model_argv(lane: ExpectedLocalModelLane) -> list[str]:
    return [
        "devflow",
        "agent",
        "add-model",
        "--provider",
        lane.provider_id,
        "--model",
        lane.model_id,
        "--authority",
        lane.authority,
        "--role",
        lane.role,
        "--profile-id",
        lane.profile_id,
        "--json",
    ]


def _unique_commands(lanes: list[dict[str, Any]], *, field: str = "provision_commands") -> list[dict[str, Any]]:
    seen: set[tuple[str, str | None]] = set()
    commands: list[dict[str, Any]] = []
    for lane in lanes:
        for command in _dict_rows(lane.get(field)):
            command_text = command.get("command") if isinstance(command.get("command"), str) else None
            key = (
                str(command.get("kind")),
                command_text or str(command.get("lane_id") or command.get("reason") or ""),
            )
            if key in seen:
                continue
            seen.add(key)
            commands.append(command)
    return commands


def _managed_start_profile(lane: ExpectedLocalModelLane) -> str | None:
    try:
        from devflow.control_room.local_model_server import known_local_model_server_profiles

        profiles = known_local_model_server_profiles()
    except Exception:
        return None
    for candidate in (lane.profile_id, lane.provider_id, lane.model_id):
        if candidate in profiles:
            return candidate
    return None


def _append_command_section(lines: list[str], title: str, commands: list[dict[str, Any]]) -> None:
    lines.append(title)
    if not commands:
        lines.append("  - none")
        return
    for command in commands:
        command_text = command.get("command")
        if command_text:
            lines.append(f"  - {command_text}")
        else:
            lines.append(f"  - unsupported {command.get('kind')}: {command.get('reason')}")


def _apply_provision_command(
    root: Path,
    command: dict[str, Any],
    *,
    index: int,
    run_id: str,
    run_dir: Path,
    runner: Callable[..., subprocess.CompletedProcess[str]],
) -> dict[str, Any]:
    evidence_path = run_dir / (
        f"command-{index:03d}-{_safe_slug(command.get('kind') or 'command')}-"
        f"{_safe_slug(command.get('profile_id') or command.get('provider_id') or 'unknown')}.json"
    )
    base: dict[str, Any] = {
        "schema_version": 1,
        "action": "doctor_provision_apply_command",
        "run_id": run_id,
        "index": index,
        "kind": command.get("kind"),
        "lane_id": command.get("lane_id"),
        "provider_id": command.get("provider_id"),
        "profile_id": command.get("profile_id"),
        "command": command.get("command"),
        "planner_argv": list(command.get("argv")) if isinstance(command.get("argv"), list) else None,
        "started_at": utc_now().isoformat(),
        "cwd": str(root.resolve()),
        "supported_by_planner": bool(command.get("supported")),
    }
    if not command.get("supported"):
        return _write_command_evidence(
            root,
            evidence_path,
            {
                **base,
                "status": "skipped",
                "reason": command.get("reason") or "Planner marked this command unsupported.",
                "completed_at": utc_now().isoformat(),
            },
        )

    planner_argv = command.get("argv")
    if not isinstance(planner_argv, list) or not all(isinstance(part, str) and part for part in planner_argv):
        return _write_command_evidence(
            root,
            evidence_path,
            {
                **base,
                "status": "blocked",
                "reason": "Provision apply requires a structured argv; shell command text is not executed.",
                "completed_at": utc_now().isoformat(),
            },
        )

    safe, reason = _safe_provision_argv(planner_argv)
    if not safe:
        return _write_command_evidence(
            root,
            evidence_path,
            {
                **base,
                "status": "blocked",
                "reason": reason,
                "completed_at": utc_now().isoformat(),
            },
        )

    executed_argv = _python_module_argv(planner_argv)
    try:
        completed = runner(
            executed_argv,
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
            env=_provision_subprocess_env(root),
        )
    except FileNotFoundError as exc:
        payload = {
            **base,
            "status": "failed",
            "reason": str(exc),
            "executed_argv": executed_argv,
            "exit_code": 127,
            "stdout": "",
            "stderr": str(exc),
            "completed_at": utc_now().isoformat(),
        }
    except OSError as exc:
        payload = {
            **base,
            "status": "failed",
            "reason": str(exc),
            "executed_argv": executed_argv,
            "exit_code": 1,
            "stdout": "",
            "stderr": str(exc),
            "completed_at": utc_now().isoformat(),
        }
    else:
        payload = {
            **base,
            "status": "succeeded" if completed.returncode == 0 else "failed",
            "reason": command.get("reason"),
            "executed_argv": executed_argv,
            "exit_code": int(completed.returncode),
            "stdout": _cap_output(completed.stdout),
            "stderr": _cap_output(completed.stderr),
            "completed_at": utc_now().isoformat(),
        }
    return _write_command_evidence(root, evidence_path, payload)


def _write_command_evidence(root: Path, evidence_path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    payload["evidence_path"] = relative_path(root, evidence_path)
    atomic_write_text(evidence_path, json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return payload


def _command_result_summary(evidence: dict[str, Any]) -> dict[str, Any]:
    evidence_path = evidence.get("evidence_path")
    return {
        "index": evidence.get("index"),
        "kind": evidence.get("kind"),
        "lane_id": evidence.get("lane_id"),
        "provider_id": evidence.get("provider_id"),
        "profile_id": evidence.get("profile_id"),
        "command": evidence.get("command"),
        "status": evidence.get("status"),
        "reason": evidence.get("reason"),
        "exit_code": evidence.get("exit_code"),
        "evidence_path": evidence_path if isinstance(evidence_path, str) else None,
    }


def _safe_provision_argv(argv: list[str]) -> tuple[bool, str | None]:
    if not argv or argv[0] != "devflow":
        return False, "Provision apply only runs planner commands that start with 'devflow'."
    command_prefix = tuple(argv[1:3])
    if command_prefix not in SAFE_PROVISION_COMMAND_PREFIXES:
        allowed = ", ".join("devflow " + " ".join(prefix) for prefix in SAFE_PROVISION_COMMAND_PREFIXES)
        return False, f"Refusing non-onboarding command '{' '.join(argv)}'. Allowed prefixes: {allowed}."
    if command_prefix == ("local-model", "start"):
        expected_length = 6
        if len(argv) != expected_length or argv[4:] != ["--replace", "--json"]:
            return (
                False,
                "Refusing local model start command that does not match the managed "
                "'devflow local-model start <profile> --replace --json' shape.",
            )
    return True, None


def _python_module_argv(planner_argv: list[str]) -> list[str]:
    return [sys.executable, "-m", "devflow.cli", *planner_argv[1:]]


def _provision_subprocess_env(root: Path) -> dict[str, str]:
    env = os.environ.copy()
    pythonpath_parts: list[str] = []
    src_path = root / "src"
    if src_path.exists():
        pythonpath_parts.append(src_path.as_posix())
    pythonpath_parts.append(root.as_posix())
    existing = env.get("PYTHONPATH")
    if existing:
        pythonpath_parts.append(existing)
    env["PYTHONPATH"] = os.pathsep.join(_dedupe_strings(pythonpath_parts))
    return env


def _cap_output(value: str | None) -> str:
    text = value or ""
    if len(text) <= MAX_EVIDENCE_OUTPUT_CHARS:
        return text
    return text[:MAX_EVIDENCE_OUTPUT_CHARS] + "\n[truncated]"


def _run_id() -> str:
    return "run-" + utc_now().strftime("%Y%m%dT%H%M%SZ")


def _safe_slug(value: object) -> str:
    text = str(value or "unknown").strip().lower()
    safe = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in text)
    return safe.strip("-") or "unknown"


def _dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _provider_row(rows: list[dict[str, Any]], provider_id: str) -> dict[str, Any] | None:
    for row in rows:
        if row.get("id") == provider_id:
            return row
    return None


def _profile_row(rows: list[dict[str, Any]], profile_id: str) -> dict[str, Any] | None:
    for row in rows:
        if row.get("id") == profile_id:
            return row
    return None


def _inventory_row(rows: list[dict[str, Any]], lane: ExpectedLocalModelLane) -> dict[str, Any] | None:
    for row in rows:
        if row.get("profile_id") == lane.profile_id:
            return row
    for row in rows:
        if row.get("provider_id") == lane.provider_id and row.get("model") == lane.model_id:
            return row
    return None


def _required_text(raw_lane: dict[str, Any], field: str, lane_id: str) -> str:
    value = _optional_text(raw_lane.get(field))
    if not value:
        raise LocalModelReadinessError(f"Lane '{lane_id}' missing required field '{field}'.")
    return value


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""


def _required_int(raw_lane: dict[str, Any], field: str, lane_id: str) -> int:
    value = _optional_int(raw_lane.get(field), field=field, lane_id=lane_id)
    if value is None:
        raise LocalModelReadinessError(f"Lane '{lane_id}' missing required integer field '{field}'.")
    return value


def _optional_int(value: object, *, field: str, lane_id: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise LocalModelReadinessError(f"Lane '{lane_id}' field '{field}' must be an integer.")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise LocalModelReadinessError(f"Lane '{lane_id}' field '{field}' must be an integer.") from exc
    if parsed < 0:
        raise LocalModelReadinessError(f"Lane '{lane_id}' field '{field}' must not be negative.")
    return parsed


def _required_string_list(raw_lane: dict[str, Any], field: str, lane_id: str) -> list[str]:
    value = raw_lane.get(field)
    if not isinstance(value, list):
        raise LocalModelReadinessError(f"Lane '{lane_id}' field '{field}' must be a list.")
    rows = [str(item).strip() for item in value if str(item).strip()]
    if len(rows) != len(value):
        raise LocalModelReadinessError(f"Lane '{lane_id}' field '{field}' must contain only non-empty strings.")
    return rows


def _dict_rows(value: object) -> list[dict[str, Any]]:
    return [dict(item) for item in value if isinstance(item, dict)] if isinstance(value, list) else []
