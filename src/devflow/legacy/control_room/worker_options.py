"""Canonical worker-options projection for the task launchpad.

Populates a list of WorkerOption records from routing-decision, agent-selection
registry, and local-worker evidence.  Always includes a shell fallback.  Blocked
workers are listed with their concrete reason rather than disappearing silently.

This is a read-only projection; no command here auto-runs.  Consumers (JS,
operating-layer) decide how to present the options.
"""

from __future__ import annotations

import json
import shlex
import uuid
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator

from devflow.legacy.control_room.agent_catalog_hermes import configured_hermes_agents
from devflow.legacy.control_room.hermes_profile_resolver import resolve_hermes_profile_for_historical_cleanup
from devflow.legacy.control_room.paths import relative_path, task_dir, workspace_path


class WorkerOption(BaseModel):
    worker_id: str
    label: str
    command: str | None = None
    source: str  # routing-decision | agent-selection | registry | fallback-shell
    model: str | None = None
    provider: str | None = None
    is_local: bool = False
    enabled: bool = True
    safety_class: str = "read_only"
    requires_human_approval: bool = True
    supervisor_may_auto_run: bool = False
    reason: str | None = None
    blocked_reason: str | None = None
    evidence_paths: list[str] = Field(default_factory=list)
    action_kind: str | None = None
    runtime_kind: str | None = None
    hermes_profile: str | None = None
    toolsets: list[str] = Field(default_factory=list)
    recommended_allowed_files: list[str] = Field(default_factory=list)
    recommended_verification_commands: list[str] = Field(default_factory=list)
    needs_operator_inputs: list[str] = Field(default_factory=list)
    option_id: str = ""

    @field_validator("option_id", mode="before")
    @classmethod
    def _ensure_option_id(cls, v):
        if not v:
            return f"w-uuid-{uuid.uuid4().hex[:8]}"
        return v


def build_worker_options(
    root: Path,
    task_id: str,
    *,
    project_id: str | None = None,
    configured_hermes_agent_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return worker options for *task_id* separated by category.

    Returns a dict with keys:
        - ``ai_workers``   -- all eligible AI workers (enabled or not), grouped
          by source order: routing-decision, agent-selection, registry.
        - ``fallback_shell``  -- the shell fallback, always present, enabled=True.
        - ``blocked_details`` -- blocked options keyed by worker_id for inline
          display of rejection reasons.
    """
    root = root.resolve()
    task_path = task_dir(root, task_id)
    packet_contract = _packet_input_contract(root, task_id)

    ai_options: list[WorkerOption] = []
    blocked: dict[str, WorkerOption] = {}

    _inject_routing_decision(task_path, ai_options, blocked, packet_contract=packet_contract)
    _inject_agent_selection(task_path, ai_options, blocked, packet_contract=packet_contract)
    _inject_local_worker_evidence(root, task_id, task_path, ai_options, blocked, packet_contract=packet_contract)
    _inject_configured_hermes_agents(
        root,
        task_id,
        ai_options,
        blocked,
        configured_hermes_agent_rows=configured_hermes_agent_rows,
        packet_contract=packet_contract,
    )

    # Always present fallback shell (right below AI workers in render order).
    shell_cmd = f"devflow task run {task_id} --worker shell -- <command>"
    if project_id and "--project" not in shell_cmd:
        before_sep, sep, after_sep = shell_cmd.partition(" -- ")
        shell_cmd = f"{before_sep} --project {project_id}{sep}{after_sep}"

    fallback_shell = WorkerOption(
        worker_id="shell",
        label="Shell",
        command=shell_cmd,
        source="fallback-shell",
        is_local=True,
        enabled=True,
        safety_class="approval_required",
        requires_human_approval=True,
        supervisor_may_auto_run=False,
        reason="Manual shell worker -- operator provides the exact command.",
    )

    return {
        "ai_workers": ai_options,
        "fallback_shell": fallback_shell,
        "blocked_details": blocked,
    }


# ---------------------------------------------------------------------------
# Source: routing-decision.yaml  (highest priority source)
# ---------------------------------------------------------------------------


def _inject_routing_decision(
    task_path: Path,
    ai_options: list[WorkerOption],
    blocked: dict[str, WorkerOption],
    *,
    packet_contract: dict[str, list[str]],
) -> None:
    rd_file = task_path / "routing-decision.yaml"
    if not rd_file.exists():
        return
    try:
        rd = _read_yaml_routing(rd_file)
    except Exception:
        return

    selected = rd.get("selected") or {}
    is_selected = isinstance(selected, dict)

    # Add the selected agent first.
    if is_selected and selected:
        worker_id = str(selected.get("agent_id", selected.get("worker_id", "unknown")))
        reason_msg = _fmt_reason(selected.get("reason"))
        provider = _optional_text(selected.get("provider"))
        model = _optional_text(selected.get("model"))
        is_local = _is_local_worker(provider, model, worker_id)
        ai_options.append(
            _worker_option(
                task_id=task_path.name,
                worker_id=worker_id,
                label=_option_label(selected, worker_id),
                model=model,
                provider=provider,
                source="routing-decision",
                enabled=True,
                is_local=is_local,
                reason=reason_msg or "Routing decision recommends this worker.",
                packet_contract=packet_contract,
            )
        )

    # Add rejected agents as blocked-with-reason entries (visible).
    rejected = rd.get("rejected") or []
    if isinstance(rejected, list):
        for item in rejected:
            wid = str(item.get("agent_id", ""))
            if not wid or wid in {opt.worker_id for opt in ai_options}:
                continue
            reason_msg = _fmt_reason(
                f"rejected: {item.get('reason', 'no reason given')}"
            )
            entry = WorkerOption(
                worker_id=wid,
                label=_plain_worker_name(wid),
                source="routing-decision",
                enabled=False,
                is_local=_is_local_provider(item.get("provider")),
                supervisor_may_auto_run=False,
                blocked_reason=reason_msg,
                reason="Routing decision rejected this worker.",
            )
            blocked[wid] = entry

    # Add unresolved as blocked.
    unresolved = rd.get("unresolved") or []
    if isinstance(unresolved, list):
        for item in unresolved:
            wid = str(item.get("role", item.get("worker_id", "")))
            if not wid or wid in {opt.worker_id for opt in ai_options}:
                continue
            reason_msg = _fmt_reason(
                f"unresolved: {item.get('reason', 'no reason given')}"
            )
            entry = WorkerOption(
                worker_id=wid,
                label=_plain_worker_name(wid),
                source="routing-decision",
                enabled=False,
                is_local=False,
                supervisor_may_auto_run=False,
                blocked_reason=reason_msg,
                reason="Routing decision left this worker unresolved.",
            )
            blocked[wid] = entry


def _is_local_provider(provider: Any) -> bool:
    if provider is None:
        return False
    return str(provider).lower() in {"ollama", "local"}


# ---------------------------------------------------------------------------
# Source: agent-selection.json  (second priority)
# ---------------------------------------------------------------------------


def _inject_agent_selection(
    task_path: Path,
    ai_options: list[WorkerOption],
    blocked: dict[str, WorkerOption],
    *,
    packet_contract: dict[str, list[str]],
) -> None:
    sel_file = task_path / "agent-selection.json"
    if not sel_file.exists():
        return
    try:
        data = json.loads(sel_file.read_text(encoding="utf-8"))
    except Exception:
        return

    selected_model = None
    if isinstance(data, dict):
        selected_model = data.get("model") or data.get("selected_model")

    if isinstance(data, dict):
        worker_id = str(data.get("worker_id", data.get("agent_id", "local-model")))
        model = _optional_text(selected_model)
        ai_options.append(
            _worker_option(
                task_id=task_path.name,
                worker_id=worker_id,
                label=_option_label(data, str(data.get("model", "local-model"))),
                model=model,
                provider="ollama",
                source="agent-selection",
                enabled=True,
                is_local=True,
                reason="Local agent-selection indicates the active worker.",
                packet_contract=packet_contract,
            )
        )
    else:
        ai_options.append(
            WorkerOption(
                worker_id="local-model",
                label="Local model",
                provider="ollama",
                source="agent-selection",
                enabled=True,
                is_local=True,
                supervisor_may_auto_run=False,
                reason="Local agent-selection indicates the active worker.",
            )
        )


# ---------------------------------------------------------------------------
# Source: local-worker evidence (qwopus etc.) -- third priority
# ---------------------------------------------------------------------------


def _inject_local_worker_evidence(
    root: Path,
    task_id: str,
    task_path: Path,
    ai_options: list[WorkerOption],
    blocked: dict[str, WorkerOption],
    *,
    packet_contract: dict[str, list[str]],
) -> None:
    """Walk .devflow/tasks/<task>/agents/ for local-model evidence.

    Only agents that reference local-model or Ollama are included; others
    stay outside this file's scope.
    """
    agent_dir = task_path / "agents"
    run_dirs: list[Path] = []
    if agent_dir.exists() and agent_dir.is_dir():
        run_dirs.extend(path for path in agent_dir.iterdir() if path.is_dir())
    runs_dir = task_path / "local-model-runs"
    if runs_dir.exists() and runs_dir.is_dir():
        run_dirs.extend(path for path in runs_dir.iterdir() if path.is_dir())
        if (runs_dir / "run.json").exists():
            run_dirs.append(runs_dir)
    if not run_dirs:
        return

    for agent_subdir in run_dirs:
        if not agent_subdir.is_dir():
            continue
        run_json = agent_subdir / "run.json"
        run_data: dict[str, Any] = {}
        if run_json.exists():
            try:
                loaded = json.loads(run_json.read_text(encoding="utf-8"))
            except Exception:
                loaded = {}
            if isinstance(loaded, dict):
                run_data = loaded

        adapter = str(run_data.get("adapter", "") or "")
        # Only local adapters.
        if "remote" in adapter or "cloud" in adapter:
            continue
        if adapter and adapter != "ollama_chat":
            # Could add other local adapters later; for now only ollama.
            pass

        worker_id = str(run_data.get("agent_id") or agent_subdir.name)
        model = str(run_data.get("model") or run_data.get("selected_model") or "")
        status = str(run_data.get("status", "") or "unknown")

        # Evidence paths.
        evid_paths: list[str] = []
        if run_json.exists():
            evid_paths.append(str(run_json.relative_to(root)) if run_json.is_relative_to(root) else str(run_json))
        for name in ("proposal.patch", "result.md", "raw_output.md", "worker_failed.json"):
            candidate = agent_subdir / name
            if candidate.exists() and candidate.is_relative_to(root):
                evid_paths.append(str(candidate.relative_to(root)))

        # Check for blocked evidence even if run.json is absent.
        worker_failed = agent_subdir / "worker_failed.json"
        if worker_failed.exists():
            try:
                fail_data = json.loads(worker_failed.read_text(encoding="utf-8"))
            except Exception:
                fail_data = {}
            reason_msg = (
                f"{fail_data.get('error', fail_data.get('message', 'local model run failed'))}"
            ) if isinstance(fail_data, dict) else "local model run failed"
            blocked[f"run-{worker_id}"] = WorkerOption(
                worker_id=f"run-{worker_id}",
                label=_plain_worker_name(worker_id),
                model=model or None,
                provider="ollama",
                source="registry",
                enabled=False,
                is_local=True,
                supervisor_may_auto_run=False,
                blocked_reason=reason_msg,
                reason=f"Local model run reported failure (status={status}).",
                evidence_paths=evid_paths[:5],
            )
            continue

        if not run_data:
            continue

        # If the run completed successfully or had a proposal, prefer it as enabled.
        has_proposal = bool(
            agent_subdir.joinpath("run.json").exists()
            and run_data.get("proposal_patch_found") is True
        ) or (agent_subdir / "proposal.patch").exists()

        ai_options.append(
            _worker_option(
                task_id=task_path.name,
                worker_id=worker_id,
                label=_plain_worker_name(worker_id),
                model=model if model else None,
                provider="ollama",
                source="registry",
                enabled=True if has_proposal or status in ("complete", "succeeded") else False,
                is_local=True,
                reason=f"Local model run (status={status}).",
                evidence_paths=evid_paths[:5],  # cap at 5 paths
                packet_contract=packet_contract,
            )
        )


# ---------------------------------------------------------------------------
# Source: configured Hermes agents -- packet-only task options
# ---------------------------------------------------------------------------


def _inject_configured_hermes_agents(
    root: Path,
    task_id: str,
    ai_options: list[WorkerOption],
    blocked: dict[str, WorkerOption],
    *,
    configured_hermes_agent_rows: list[dict[str, Any]] | None = None,
    packet_contract: dict[str, list[str]],
) -> None:
    existing_ids = {option.worker_id for option in ai_options} | set(blocked)
    agents = (
        configured_hermes_agent_rows
        if configured_hermes_agent_rows is not None
        else configured_hermes_agents(root)
    )
    for agent in agents:
        worker_id = str(agent.get("id") or "")
        if not worker_id or worker_id in existing_ids:
            continue
        provider = _optional_text(agent.get("provider"))
        model = _optional_text(agent.get("model"))
        hermes_profile = _optional_text(agent.get("hermes_profile"))
        if not provider or not model or not hermes_profile:
            continue
        status = str(agent.get("status") or "available")
        is_local = _is_local_provider(provider) or _is_local_base_url(agent.get("base_url"))
        if status != "available":
            blocked[worker_id] = WorkerOption(
                worker_id=worker_id,
                label=str(agent.get("label") or _plain_worker_name(worker_id)),
                source="hermes",
                model=model,
                provider=provider,
                enabled=False,
                is_local=is_local,
                supervisor_may_auto_run=False,
                blocked_reason=str(agent.get("blocked_reason") or "Hermes agent is not launch-ready."),
                reason="Configured Hermes agent is not launch-ready.",
            )
            existing_ids.add(worker_id)
            continue
        ai_options.append(
            _hermes_worker_option(
                task_id=task_id,
                worker_id=worker_id,
                label=str(agent.get("label") or _plain_worker_name(worker_id)),
                provider=provider,
                model=model,
                hermes_profile=hermes_profile,
                is_local=is_local,
                reason="Configured Hermes agent; create a bounded packet for Hermes profile launch.",
                packet_contract=packet_contract,
            )
        )
        existing_ids.add(worker_id)


# ---------------------------------------------------------------------------
# Packet input contract helpers
# ---------------------------------------------------------------------------


def _empty_packet_input_contract() -> dict[str, list[str]]:
    return {
        "recommended_allowed_files": [],
        "recommended_verification_commands": [],
        "needs_operator_inputs": ["allowed_files", "verification_commands"],
    }


def _packet_input_contract(root: Path, task_id: str) -> dict[str, list[str]]:
    allowed_files = _recommended_allowed_files(root, task_id)
    verification_commands: list[str] = []
    needs: list[str] = []
    if not allowed_files:
        needs.append("allowed_files")
    if not verification_commands:
        needs.append("verification_commands")
    return {
        "recommended_allowed_files": allowed_files,
        "recommended_verification_commands": verification_commands,
        "needs_operator_inputs": needs,
    }


def _recommended_allowed_files(root: Path, task_id: str) -> list[str]:
    workspace = workspace_path(root, task_id)
    if not workspace.exists() or not workspace.is_dir():
        return []
    paths: list[str] = []
    seen: set[str] = set()

    def add_file(path: Path) -> None:
        if not path.exists() or not path.is_file():
            return
        rel = relative_path(root, path)
        if rel not in seen:
            seen.add(rel)
            paths.append(rel)

    add_file(workspace / "implementation-context.md")
    for path in sorted(workspace.rglob("*")):
        if path.name.startswith(".") or path.name == "implementation-context.md":
            continue
        add_file(path)
    return paths[:20]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_yaml_routing(path: Path) -> dict[str, Any]:
    """Minimal YAML reader for routing-decision files (dict only)."""
    try:
        import yaml

        with path.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        if isinstance(data, dict):
            return data.get("routing_decision", data)
    except ImportError:
        # Fallback: strip "routing_decision:" prefix and parse as JSON.
        try:
            text = path.read_text(encoding="utf-8")
            lines = []
            for line in text.splitlines():
                stripped = line.lstrip()
                current_indent = len(line) - len(stripped)
                if current_indent == 0 and "routing_decision:" in line:
                    # Start at the routing_decision block.
                    if not lines or "routing_decision" not in "".join(lines):
                        pass
                lines.append(line)
            raw = "\n".join(lines)
            data = _strip_yaml_and_parse(raw)
            return data
        except Exception:
            return {}

    return data


def _strip_yaml_and_parse(text: str) -> dict[str, Any]:
    """Best-effort YAML->JSON extraction for routing-decision files."""
    # Find the first `{` and matching `}` that look like a JSON body.
    brace_start = text.find("{")
    if brace_start == -1:
        return {}
    # Try to find the closing brace that balances.
    depth = 0
    end = -1
    for i, ch in enumerate(text[brace_start:], brace_start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
    if end == -1:
        return {}
    candidate = text[brace_start : end + 1]
    data = json.loads(candidate)
    return data if isinstance(data, dict) else {}


def _fmt_reason(value: str | None) -> str | None:
    if not value:
        return None
    return str(value).strip()


def _plain_worker_name(worker_id: str) -> str:
    parts = [part for part in worker_id.replace("_", " ").split() if part]
    return " ".join((part[0].upper() + part[1:] if part else "") for part in parts) or "Worker"


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _is_local_worker(provider: Any, model: Any, worker_id: Any) -> bool:
    if _is_local_provider(provider):
        return True
    value = " ".join(str(part or "").lower() for part in (model, worker_id))
    return any(token in value for token in ("ollama", "qwopus", "qwen", "local"))


def _is_local_base_url(value: Any) -> bool:
    text = _optional_text(value)
    if not text:
        return False
    try:
        from urllib.parse import urlparse

        parsed = urlparse(text)
    except Exception:
        return False
    return parsed.scheme in {"http", "https"} and parsed.hostname in {"127.0.0.1", "localhost", "::1"}


def _option_label(payload: dict[str, Any], fallback: str) -> str:
    for key in ("label", "name", "display_name"):
        value = _optional_text(payload.get(key))
        if value:
            return value
    return _plain_worker_name(fallback)


def _worker_option(
    *,
    task_id: str,
    worker_id: str,
    label: str,
    model: str | None,
    provider: str | None,
    source: str,
    enabled: bool,
    is_local: bool,
    reason: str,
    evidence_paths: list[str] | None = None,
    packet_contract: dict[str, list[str]] | None = None,
) -> WorkerOption:
    command = None
    action_kind = None
    runtime_kind = None
    hermes_profile = _canonical_hermes_profile(worker_id)
    toolsets: list[str] = []
    recommended_allowed_files: list[str] = []
    recommended_verification_commands: list[str] = []
    needs_operator_inputs: list[str] = []
    if enabled and is_local:
        runtime_kind = "hermes-profile"
        toolsets = ["file", "terminal"]
        action_kind = "serial_packet"
        command = _serial_packet_command(
            task_id=task_id,
            worker_id=worker_id,
            provider=provider or "ollama",
            model=model or "<model>",
            hermes_profile=hermes_profile,
            toolsets=toolsets,
        )
        contract = packet_contract or _empty_packet_input_contract()
        recommended_allowed_files = list(contract.get("recommended_allowed_files", []))
        recommended_verification_commands = list(contract.get("recommended_verification_commands", []))
        needs_operator_inputs = list(contract.get("needs_operator_inputs", []))
    return WorkerOption(
        worker_id=worker_id,
        label=label,
        command=command,
        model=model,
        provider=provider,
        source=source,
        enabled=enabled,
        is_local=is_local,
        supervisor_may_auto_run=False,
        reason=reason,
        evidence_paths=evidence_paths or [],
        action_kind=action_kind,
        runtime_kind=runtime_kind,
        hermes_profile=hermes_profile,
        toolsets=toolsets,
        recommended_allowed_files=recommended_allowed_files,
        recommended_verification_commands=recommended_verification_commands,
        needs_operator_inputs=needs_operator_inputs,
    )


def _hermes_worker_option(
    *,
    task_id: str,
    worker_id: str,
    label: str,
    provider: str,
    model: str,
    hermes_profile: str,
    is_local: bool,
    reason: str,
    packet_contract: dict[str, list[str]],
) -> WorkerOption:
    hermes_profile = _canonical_hermes_profile(hermes_profile) or hermes_profile
    toolsets = ["file", "terminal"]
    command = _serial_packet_command(
        task_id=task_id,
        worker_id=worker_id,
        provider=provider,
        model=model,
        hermes_profile=hermes_profile,
        toolsets=toolsets,
    )
    return WorkerOption(
        worker_id=worker_id,
        label=label,
        command=command,
        model=model,
        provider=provider,
        source="hermes",
        enabled=True,
        is_local=is_local,
        supervisor_may_auto_run=False,
        reason=reason,
        action_kind="serial_packet",
        runtime_kind="hermes-profile",
        hermes_profile=hermes_profile,
        toolsets=toolsets,
        recommended_allowed_files=list(packet_contract.get("recommended_allowed_files", [])),
        recommended_verification_commands=list(packet_contract.get("recommended_verification_commands", [])),
        needs_operator_inputs=list(packet_contract.get("needs_operator_inputs", [])),
    )


def _serial_packet_command(
    *,
    task_id: str,
    worker_id: str,
    provider: str,
    model: str,
    hermes_profile: str,
    toolsets: list[str],
) -> str:
    parts = [
        "devflow",
        "agent",
        "serial-packet",
        "--phase",
        "implementer",
        "--provider",
        provider,
        "--model",
        model,
        "--task-id",
        task_id,
        "--worker-id",
        worker_id,
        "--runtime",
        "hermes-profile",
        "--hermes-profile",
        hermes_profile,
    ]
    for toolset in toolsets:
        parts.extend(["--toolset", toolset])
    parts.extend(["--allowed-file", "<allowed-file>", "--verify", "<verification-command>"])
    return " ".join(_quote_command_part(part) for part in parts)


def _canonical_hermes_profile(profile_id: str | None) -> str | None:
    candidate = _optional_text(profile_id)
    if not candidate:
        return None
    profile = resolve_hermes_profile_for_historical_cleanup(candidate)
    return profile.hermes_profile if profile is not None else candidate


def _quote_command_part(value: str) -> str:
    if value.startswith("<") and value.endswith(">"):
        return value
    return shlex.quote(value)


__all__ = ["build_worker_options", "WorkerOption"]
