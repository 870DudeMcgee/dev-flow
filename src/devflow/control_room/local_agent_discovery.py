from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
import subprocess
from typing import Any

from devflow.control_room.agent_registry import AgentDefinition, AgentRegistry
from devflow.control_room.agent_runtime import resolve_agent_runtime_definition
from devflow.control_room.paths import relative_path, task_dir
from devflow.control_room.persistence import atomic_write_text, utc_now


class LocalAgentDiscoveryError(ValueError):
    pass


@dataclass(frozen=True)
class InstalledLocalModel:
    name: str
    model_id: str
    size: str
    modified: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "model_id": self.model_id,
            "size": self.size,
            "modified": self.modified,
        }


@dataclass(frozen=True)
class LocalModelManifest:
    model: str
    architecture: str | None = None
    parameters: str | None = None
    parameter_count_billions: float | None = None
    context_length: int | None = None
    embedding_length: int | None = None
    quantization: str | None = None
    capabilities: list[str] = field(default_factory=list)
    raw_facts: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "architecture": self.architecture,
            "parameters": self.parameters,
            "parameter_count_billions": self.parameter_count_billions,
            "context_length": self.context_length,
            "embedding_length": self.embedding_length,
            "quantization": self.quantization,
            "capabilities": list(self.capabilities),
            "raw_facts": dict(self.raw_facts),
        }


@dataclass(frozen=True)
class ModelCapabilityProfile:
    model: str
    provider: str
    architecture: str | None
    weight_class: str
    allowed_roles: list[str]
    useful_context_tokens: int
    max_safe_context_tokens: int
    cost_class: str
    latency_class: str
    trust_level: str
    strengths: list[str] = field(default_factory=list)
    cautions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "provider": self.provider,
            "architecture": self.architecture,
            "weight_class": self.weight_class,
            "allowed_roles": list(self.allowed_roles),
            "useful_context_tokens": self.useful_context_tokens,
            "max_safe_context_tokens": self.max_safe_context_tokens,
            "cost_class": self.cost_class,
            "latency_class": self.latency_class,
            "trust_level": self.trust_level,
            "strengths": list(self.strengths),
            "cautions": list(self.cautions),
        }


@dataclass(frozen=True)
class LocalDiscoveryReport:
    installed_models: list[InstalledLocalModel]
    manifests: list[LocalModelManifest]
    capability_profiles: list[ModelCapabilityProfile]
    errors: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "provider": "ollama",
            "installed_models": [model.to_dict() for model in self.installed_models],
            "manifests": [manifest.to_dict() for manifest in self.manifests],
            "capability_profiles": [profile.to_dict() for profile in self.capability_profiles],
            "errors": list(self.errors),
        }


@dataclass(frozen=True)
class LocalAgentCandidate:
    agent_id: str
    model: str
    role: str
    adapter: str
    permission_mode: str
    execution_surface: str
    eligible: bool
    score: int
    reasons: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "model": self.model,
            "role": self.role,
            "adapter": self.adapter,
            "permission_mode": self.permission_mode,
            "execution_surface": self.execution_surface,
            "eligible": self.eligible,
            "score": self.score,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True)
class LocalAgentSelection:
    role: str
    status: str
    selected_agent_id: str | None
    selected_model: str | None
    candidates: list[LocalAgentCandidate]
    installed_models: list[str]
    unregistered_installed_models: list[str]

    def to_dict(self, *, task_id: str | None = None) -> dict[str, Any]:
        next_command = None
        if task_id and self.selected_agent_id:
            next_command = f"devflow task run {task_id} --worker {self.selected_agent_id}"
        return {
            "schema_version": 1,
            "role": self.role,
            "status": self.status,
            "selected_agent_id": self.selected_agent_id,
            "selected_model": self.selected_model,
            "next_command": next_command,
            "will_run_worker": False,
            "installed_models": list(self.installed_models),
            "unregistered_installed_models": list(self.unregistered_installed_models),
            "candidates": [candidate.to_dict() for candidate in self.candidates],
        }


def parse_ollama_list(text: str) -> list[InstalledLocalModel]:
    models: list[InstalledLocalModel] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.lower().startswith("name "):
            continue
        parts = re.split(r"\s{2,}", line, maxsplit=3)
        if len(parts) < 4:
            parts = line.split(maxsplit=3)
        if len(parts) < 4:
            continue
        models.append(
            InstalledLocalModel(
                name=parts[0],
                model_id=parts[1],
                size=parts[2],
                modified=parts[3],
            )
        )
    return models


def parse_ollama_show(model: str, text: str) -> LocalModelManifest:
    section = ""
    facts: dict[str, str] = {}
    capabilities: list[str] = []

    for raw_line in text.splitlines():
        if not raw_line.strip():
            continue
        stripped = raw_line.strip()
        if raw_line.startswith("  ") and not raw_line.startswith("    "):
            section = _normalize_key(stripped)
            continue
        if raw_line.startswith("    "):
            parts = re.split(r"\s{2,}", stripped, maxsplit=1)
            if len(parts) == 2:
                key = f"{section}.{_normalize_key(parts[0])}" if section else _normalize_key(parts[0])
                facts[key] = parts[1].strip()
            elif section == "capabilities":
                capabilities.append(stripped)

    architecture = facts.get("model.architecture")
    parameters = facts.get("model.parameters")
    return LocalModelManifest(
        model=model,
        architecture=architecture,
        parameters=parameters,
        parameter_count_billions=_parse_billions(parameters),
        context_length=_parse_int(facts.get("model.context_length")),
        embedding_length=_parse_int(facts.get("model.embedding_length")),
        quantization=facts.get("model.quantization"),
        capabilities=capabilities,
        raw_facts=facts,
    )


def classify_local_model(manifest: LocalModelManifest) -> ModelCapabilityProfile:
    parameter_count = manifest.parameter_count_billions
    weight_class = _weight_class(parameter_count)
    allowed_roles: list[str] = []
    strengths: list[str] = []
    cautions: list[str] = []

    has_completion = not manifest.capabilities or "completion" in manifest.capabilities
    if has_completion:
        allowed_roles.extend(["summarizer", "reviewer"])
        strengths.extend(["summarization", "review"])
    if has_completion and (manifest.context_length or 0) >= 8192:
        allowed_roles.append("bounded_worker")
        strengths.append("bounded task packets")
    if has_completion and _looks_patch_capable(manifest):
        allowed_roles.append("patch_proposer_candidate")
        cautions.append("Patch proposal still requires registry permission, review, dry-run, and verification gates.")

    if "vision" in manifest.capabilities:
        strengths.append("multimodal review")
    if "thinking" in manifest.capabilities:
        strengths.append("reasoning")
    if manifest.architecture is None or manifest.parameters is None:
        cautions.append("Manifest is partial; treat capability as low-trust until ollama show has full facts.")

    useful_context = min(manifest.context_length or 8192, 32768)
    max_safe_context = min(manifest.context_length or useful_context, 65536)
    return ModelCapabilityProfile(
        model=manifest.model,
        provider="ollama",
        architecture=manifest.architecture,
        weight_class=weight_class,
        allowed_roles=sorted(set(allowed_roles)),
        useful_context_tokens=useful_context,
        max_safe_context_tokens=max_safe_context,
        cost_class="local",
        latency_class=_latency_class(weight_class),
        trust_level="manifest_verified" if manifest.raw_facts else "name_only",
        strengths=sorted(set(strengths)),
        cautions=cautions,
    )


def discover_local_ollama_models() -> LocalDiscoveryReport:
    list_result = _run_ollama(["ollama", "list"])
    installed_models = parse_ollama_list(list_result.stdout)
    manifests: list[LocalModelManifest] = []
    profiles: list[ModelCapabilityProfile] = []
    errors: list[dict[str, str]] = []

    for model in installed_models:
        show_result = _run_ollama(["ollama", "show", model.name], check=False)
        if show_result.returncode != 0:
            errors.append({"model": model.name, "error": show_result.stderr.strip() or "ollama show failed"})
            continue
        manifest = parse_ollama_show(model.name, show_result.stdout)
        manifests.append(manifest)
        profiles.append(classify_local_model(manifest))

    return LocalDiscoveryReport(
        installed_models=installed_models,
        manifests=manifests,
        capability_profiles=profiles,
        errors=errors,
    )


def rank_local_agent_candidates(
    registry: AgentRegistry,
    installed_models: list[InstalledLocalModel],
    role: str,
) -> LocalAgentSelection:
    installed_names = {model.name for model in installed_models}
    registered_models = {agent.model for agent in registry.agents.values() if agent.provider == "ollama"}
    candidates = [
        _candidate_for_agent(agent, installed_names, role=role)
        for agent in registry.agents.values()
        if agent.provider == "ollama" and (agent.role == role or role in agent.secondary_roles)
    ]
    candidates.sort(key=lambda candidate: (not candidate.eligible, -candidate.score, candidate.agent_id))
    eligible = [candidate for candidate in candidates if candidate.eligible]
    if len(eligible) == 1:
        status = "selected"
        selected_agent_id = eligible[0].agent_id
        selected_model = eligible[0].model
    elif len(eligible) > 1:
        status = "ambiguous"
        selected_agent_id = None
        selected_model = None
    else:
        status = "no_eligible_agent"
        selected_agent_id = None
        selected_model = None
    return LocalAgentSelection(
        role=role,
        status=status,
        selected_agent_id=selected_agent_id,
        selected_model=selected_model,
        candidates=candidates,
        installed_models=sorted(installed_names),
        unregistered_installed_models=sorted(installed_names - registered_models),
    )


def write_selected_agent_evidence(root: Path, task_id: str, selection: LocalAgentSelection) -> Path:
    root = root.resolve()
    path = task_dir(root, task_id)
    if not path.exists():
        raise FileNotFoundError(f"Unknown task '{task_id}'.")
    selection_path = path / "agent-selection.json"
    payload = selection.to_dict(task_id=task_id)
    payload["task_id"] = task_id
    payload["selected_at"] = utc_now().isoformat()
    payload["selection_path"] = relative_path(root, selection_path)
    atomic_write_text(selection_path, _json_dumps(payload))
    return selection_path


def selection_payload_with_path(root: Path, task_id: str, selection: LocalAgentSelection, path: Path) -> dict[str, Any]:
    payload = selection.to_dict(task_id=task_id)
    payload["task_id"] = task_id
    payload["selection_path"] = relative_path(root, path)
    return payload


def _candidate_for_agent(agent: AgentDefinition, installed_names: set[str], *, role: str) -> LocalAgentCandidate:
    runtime = resolve_agent_runtime_definition(agent, None)
    reasons: list[str] = []
    if not agent.enabled:
        reasons.append("agent_disabled")
    if agent.model not in installed_names:
        reasons.append("model_not_installed")
    if agent.role != role and role not in agent.secondary_roles:
        reasons.append("role_not_matched")
    if not runtime.task_run_allowed:
        reasons.append(f"not_task_run_runtime:{runtime.execution_surface}")
    eligible = not reasons
    return LocalAgentCandidate(
        agent_id=agent.id,
        model=agent.model,
        role=agent.role,
        adapter=agent.adapter,
        permission_mode=agent.default_mode,
        execution_surface=runtime.execution_surface,
        eligible=eligible,
        score=_candidate_score(agent, eligible=eligible),
        reasons=reasons or ["eligible"],
    )


def _candidate_score(agent: AgentDefinition, *, eligible: bool) -> int:
    if not eligible:
        return 0
    score = 100
    if agent.default_mode == "workspace_write":
        score += 25
    if agent.tier in {"strong_local", "premium_local"}:
        score += 10
    return score


def _run_ollama(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(args, capture_output=True, text=True, check=False)
    if check and result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or f"{args[0]} failed"
        raise LocalAgentDiscoveryError(detail)
    return result


def _looks_patch_capable(manifest: LocalModelManifest) -> bool:
    model_text = f"{manifest.model} {manifest.architecture or ''}".lower()
    if any(token in model_text for token in ("coder", "qwen", "qwopus", "gemma")):
        return (manifest.parameter_count_billions or 0) >= 7
    return False


def _weight_class(parameter_count_billions: float | None) -> str:
    if parameter_count_billions is None:
        return "unknown"
    if parameter_count_billions < 3:
        return "tiny"
    if parameter_count_billions < 10:
        return "small"
    if parameter_count_billions < 20:
        return "medium"
    return "heavy"


def _latency_class(weight_class: str) -> str:
    if weight_class in {"tiny", "small"}:
        return "fast"
    if weight_class == "medium":
        return "medium"
    return "slow"


def _parse_billions(value: str | None) -> float | None:
    if not value:
        return None
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*B", value, re.IGNORECASE)
    return float(match.group(1)) if match else None


def _parse_int(value: str | None) -> int | None:
    if not value:
        return None
    digits = re.sub(r"[^0-9]", "", value)
    return int(digits) if digits else None


def _normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def _json_dumps(payload: dict[str, Any]) -> str:
    import json

    return json.dumps(payload, indent=2, sort_keys=True) + "\n"
