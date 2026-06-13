from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from devflow.control_room.paths import relative_path, task_dir
from devflow.control_room.persistence import get_task


MANUAL_AGENT_ID = "devflow-manual-codex-worker"


@dataclass(frozen=True)
class LocalModelRunEvidence:
    run_id: str
    worker_id: str
    profile_id: str
    status: str
    model: str | None
    adapter: str | None
    permission_mode: str | None
    run_metadata_path: str
    response_path: str | None = None


@dataclass(frozen=True)
class LocalPatchAgentEvidence:
    agent_id: str
    proposal_patch_present: bool
    raw_output_present: bool
    result_present: bool
    run_metadata_present: bool
    proposal_patch_path: str | None = None
    result_path: str | None = None


@dataclass(frozen=True)
class ShellEvidence:
    log_path: str | None = None
    result_path: str | None = None
    worker: str | None = None


@dataclass(frozen=True)
class AgentEvidenceSummary:
    task_id: str
    has_worker_evidence: bool
    local_model_runs: list[LocalModelRunEvidence] = field(default_factory=list)
    local_patch_agents: list[LocalPatchAgentEvidence] = field(default_factory=list)
    manual_result_present: bool = False
    manual_result_path: str | None = None
    shell_evidence: ShellEvidence | None = None
    next_safe_action: str = "run a worker to produce evidence"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def summarize_agent_evidence(root: Path, task_id: str) -> AgentEvidenceSummary:
    task = get_task(root, task_id)
    base = task_dir(root, task_id)
    local_model_runs = _local_model_runs(root, base)
    local_patch_agents = _local_patch_agents(root, base)
    manual_result_path = base / "agents" / MANUAL_AGENT_ID / "result.md"
    manual_result_present = manual_result_path.exists()
    shell_evidence = _shell_evidence(root, task.log_path, task.result_path, task.worker)
    has_worker_evidence = any(
        [
            local_model_runs,
            local_patch_agents,
            manual_result_present,
            shell_evidence is not None,
        ]
    )
    return AgentEvidenceSummary(
        task_id=task_id,
        has_worker_evidence=has_worker_evidence,
        local_model_runs=local_model_runs,
        local_patch_agents=local_patch_agents,
        manual_result_present=manual_result_present,
        manual_result_path=relative_path(root, manual_result_path) if manual_result_present else None,
        shell_evidence=shell_evidence,
        next_safe_action=(
            "review worker evidence before verification or promotion"
            if has_worker_evidence
            else "run a worker to produce evidence"
        ),
    )


def compact_agent_evidence_summary(root: Path, task_id: str) -> dict[str, Any]:
    summary = summarize_agent_evidence(root, task_id)
    return {
        "has_worker_evidence": summary.has_worker_evidence,
        "local_model_run_count": len(summary.local_model_runs),
        "local_patch_agent_count": len(summary.local_patch_agents),
        "manual_result_present": summary.manual_result_present,
        "next_safe_action": summary.next_safe_action,
    }


def _local_model_runs(root: Path, base: Path) -> list[LocalModelRunEvidence]:
    runs_dir = base / "local-model-runs"
    if not runs_dir.is_dir():
        return []
    runs: list[LocalModelRunEvidence] = []
    for run_metadata_path in sorted(runs_dir.glob("*/run.json")):
        try:
            data = json.loads(run_metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        run_id = str(data.get("run_id") or run_metadata_path.parent.name)
        response_path = run_metadata_path.parent / "response.md"
        runs.append(
            LocalModelRunEvidence(
                run_id=run_id,
                worker_id=str(data.get("worker_id") or data.get("profile_id") or ""),
                profile_id=str(data.get("profile_id") or ""),
                status=str(data.get("status") or "unknown"),
                model=data.get("model"),
                adapter=data.get("adapter"),
                permission_mode=data.get("permission_mode"),
                run_metadata_path=relative_path(root, run_metadata_path),
                response_path=relative_path(root, response_path) if response_path.exists() else None,
            )
        )
    return runs


def _local_patch_agents(root: Path, base: Path) -> list[LocalPatchAgentEvidence]:
    agents_dir = base / "agents"
    if not agents_dir.is_dir():
        return []
    agents: list[LocalPatchAgentEvidence] = []
    for agent_dir in sorted(path for path in agents_dir.iterdir() if path.is_dir()):
        if agent_dir.name == MANUAL_AGENT_ID:
            continue
        proposal_patch = agent_dir / "proposal.patch"
        raw_output = agent_dir / "raw_output.md"
        result = agent_dir / "result.md"
        run_metadata = agent_dir / "run.json"
        if not any(path.exists() for path in (proposal_patch, raw_output, result, run_metadata)):
            continue
        agents.append(
            LocalPatchAgentEvidence(
                agent_id=agent_dir.name,
                proposal_patch_present=proposal_patch.exists(),
                raw_output_present=raw_output.exists(),
                result_present=result.exists(),
                run_metadata_present=run_metadata.exists(),
                proposal_patch_path=relative_path(root, proposal_patch) if proposal_patch.exists() else None,
                result_path=relative_path(root, result) if result.exists() else None,
            )
        )
    return agents


def _shell_evidence(root: Path, log_path: str | None, result_path: str | None, worker: str | None) -> ShellEvidence | None:
    if not log_path and not result_path:
        return None
    return ShellEvidence(
        log_path=_normalize_artifact_path(root, log_path),
        result_path=_normalize_artifact_path(root, result_path),
        worker=worker,
    )


def _normalize_artifact_path(root: Path, value: str | None) -> str | None:
    if not value:
        return None
    path = Path(value)
    return relative_path(root, path if path.is_absolute() else root / path)
