from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from devflow.control_room.agent_registry import (
    AgentDefinition,
    AgentRegistryError,
    is_local_model_worker_pool_agent,
    load_agent_registry,
    load_provider_registry,
)
from devflow.control_room.git_state import inspect_git_state
from devflow.control_room.local_agent_discovery import (
    LocalDiscoveryReport,
    LocalAgentDiscoveryError,
    discover_local_ollama_models,
)
from devflow.control_room.local_model_worker_pool import LocalModelWorkerPoolError, run_local_model_profile
from devflow.control_room.paths import relative_path, task_dir
from devflow.control_room.persistence import atomic_write_text, get_task, utc_now


MODEL_AUDITION_SCHEMA_VERSION = 1
DEFAULT_CANDIDATE_CAP = 3


class ModelAuditionError(ValueError):
    pass


@dataclass(frozen=True)
class CandidateSpec:
    alias: str
    profile_id: str
    intent: str


JOB_CANDIDATES: dict[str, tuple[CandidateSpec, ...]] = {
    "planning": (
        CandidateSpec("local-long-context", "local-gemma4-qat", "local long-context planning/review"),
        CandidateSpec("local-code-fallback", "local-qwen25-coder-14b", "local code-aware planning fallback"),
    ),
    "small-code": (
        CandidateSpec("local-code-fallback", "local-qwen25-coder-14b", "local code-tuned review/test planning"),
        CandidateSpec("local-long-context", "local-gemma4-qat", "local long-context review fallback"),
    ),
    "hard-code": (
        CandidateSpec("local-code-fallback", "local-qwen25-coder-14b", "strongest retained local code fallback"),
        CandidateSpec("local-long-context", "local-gemma4-qat", "long-context local reasoning fallback"),
    ),
    "review-debug": (
        CandidateSpec("local-long-context", "local-gemma4-qat", "long-context local review/judgment"),
        CandidateSpec("local-code-fallback", "local-qwen25-coder-14b", "local code review/debugging fallback"),
    ),
    "summary-status": (
        CandidateSpec("local-long-context", "local-gemma4-qat", "grounded task status summary"),
        CandidateSpec("local-code-fallback", "local-qwen25-coder-14b", "code-aware status fallback"),
    ),
}


def valid_model_audition_job_types() -> list[str]:
    return sorted(JOB_CANDIDATES)


def write_model_audition_dry_run_plan(
    root: Path,
    task_id: str,
    job_type: str,
    *,
    project_id: str | None = None,
    candidate_cap: int = DEFAULT_CANDIDATE_CAP,
    discovery_report: LocalDiscoveryReport | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    if candidate_cap < 1:
        candidate_cap = DEFAULT_CANDIDATE_CAP
    candidate_cap = min(candidate_cap, DEFAULT_CANDIDATE_CAP)
    specs = _job_specs(job_type)

    try:
        task = get_task(root, task_id)
        registry = load_agent_registry(root)
        providers = load_provider_registry(root)
        discovery = discovery_report or discover_local_ollama_models()
    except (KeyError, AgentRegistryError, LocalAgentDiscoveryError, OSError) as exc:
        raise ModelAuditionError(str(exc)) from exc

    installed_models = [model.name for model in discovery.installed_models]
    installed_set = set(installed_models)
    selected: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    seen_profiles: set[str] = set()

    for rank, spec in enumerate(specs, start=1):
        candidate = _candidate_payload(
            spec,
            task_id=task_id,
            rank=rank,
            registry=registry,
            providers=providers.providers,
            installed_models=installed_set,
            duplicate=spec.profile_id in seen_profiles,
        )
        seen_profiles.add(spec.profile_id)
        if candidate["eligible"] and len(selected) < candidate_cap:
            candidate["rank"] = len(selected) + 1
            selected.append(candidate)
        else:
            if candidate["eligible"]:
                candidate = {**candidate, "eligible": False, "reasons": ["candidate_cap_reached"]}
            rejected.append(candidate)

    audition_id = f"dry-run-{job_type}"
    audition_dir = task_dir(root, task_id) / "model-auditions" / audition_id
    plan_path = audition_dir / "plan.json"
    payload: dict[str, Any] = {
        "schema_version": MODEL_AUDITION_SCHEMA_VERSION,
        "artifact_type": "model_audition_plan",
        "audition_id": audition_id,
        "task_id": task_id,
        "task_title": task.title,
        "task_status": task.status,
        "project_id": project_id,
        "job_type": job_type,
        "status": "planned" if selected else "no_eligible_candidates",
        "dry_run": True,
        "candidate_cap": candidate_cap,
        "candidate_aliases": [spec.alias for spec in specs],
        "installed_models": installed_models,
        "selected_candidates": selected,
        "rejected_candidates": rejected,
        "audition_dir": relative_path(root, audition_dir),
        "plan_path": relative_path(root, plan_path),
        "valid_job_types": valid_model_audition_job_types(),
        "created_at": utc_now().isoformat(),
        "will_call_models": False,
        "will_write_source": False,
        "will_write_workspace": False,
        "will_write_proposal_patch": False,
        "will_apply_patch": False,
        "will_verify": False,
        "will_commit_merge_push_or_promote": False,
        "next_command": None,
    }
    audition_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_text(plan_path, json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return payload


def execute_model_audition(
    root: Path,
    task_id: str,
    job_type: str,
    *,
    project_id: str | None = None,
    base_url: str | None = None,
    timeout_seconds: float | None = None,
    temperature: float | None = None,
    max_packet_chars: int = 200_000,
    discovery_report: LocalDiscoveryReport | None = None,
    run_profile: Any | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    state = inspect_git_state(root)
    if not state.safe_for_worker_writes:
        raise ModelAuditionError(
            "Git/Dev-Flow state is unsafe for worker writes. "
            "Next safe action: run `devflow git status`, then checkpoint or clean unrelated changes before --execute."
        )

    source_plan = _read_dry_run_plan(root, task_id, job_type)
    if source_plan is None:
        source_plan = write_model_audition_dry_run_plan(
            root,
            task_id,
            job_type,
            project_id=project_id,
            discovery_report=discovery_report,
        )
    selected = list(source_plan.get("selected_candidates") or [])
    if not selected:
        raise ModelAuditionError(f"No eligible candidates for job type '{job_type}'. Run --dry-run for refusal details.")
    selected_run_profile = run_profile or run_local_model_profile

    task = get_task(root, task_id)
    audition_id = f"execute-{job_type}"
    audition_dir = task_dir(root, task_id) / "model-auditions" / audition_id
    plan_path = audition_dir / "plan.json"
    runs_path = audition_dir / "runs.json"
    scorecard_path = audition_dir / "scorecard.json"
    report_path = audition_dir / "report.md"
    started_at = utc_now().isoformat()
    audition_dir.mkdir(parents=True, exist_ok=True)

    execute_plan = dict(source_plan)
    execute_plan.update(
        {
            "artifact_type": "model_audition_execute_plan",
            "audition_id": audition_id,
            "dry_run": False,
            "status": "running",
            "source_plan_path": source_plan.get("plan_path"),
            "audition_dir": relative_path(root, audition_dir),
            "plan_path": relative_path(root, plan_path),
            "runs_path": relative_path(root, runs_path),
            "scorecard_path": relative_path(root, scorecard_path),
            "report_path": relative_path(root, report_path),
            "started_at": started_at,
            "will_call_models": True,
        }
    )
    atomic_write_text(plan_path, _json_dumps(execute_plan))

    run_records: list[dict[str, Any]] = []
    score_records: list[dict[str, Any]] = []
    status = "completed"

    for candidate in selected:
        profile_id = str(candidate["profile_id"])
        try:
            run_payload = selected_run_profile(
                root=root,
                task_id=task_id,
                profile_id=profile_id,
                base_url=base_url,
                timeout_seconds=timeout_seconds,
                temperature=temperature,
                max_packet_chars=max_packet_chars,
            )
            response_text = _read_response_text(root, run_payload)
            score = score_model_audition_response(
                response_text=response_text,
                run_payload=run_payload,
                candidate=candidate,
                task_id=task.id,
                task_title=task.title,
                task_status=task.status,
            )
            run_record = _run_record(candidate, run_payload, score)
            if str(run_payload.get("status")) == "failed":
                status = "failed"
        except (LocalModelWorkerPoolError, OSError, ValueError) as exc:
            status = "failed"
            run_payload = {
                "task_id": task_id,
                "profile_id": profile_id,
                "worker_id": profile_id,
                "status": "failed",
                "error_message": str(exc),
            }
            score = score_model_audition_response(
                response_text="",
                run_payload=run_payload,
                candidate=candidate,
                task_id=task.id,
                task_title=task.title,
                task_status=task.status,
            )
            run_record = _run_record(candidate, run_payload, score)
        run_records.append(run_record)
        score_records.append(score)
        if status == "failed":
            break

    finished_at = utc_now().isoformat()
    runs_payload = {
        "schema_version": MODEL_AUDITION_SCHEMA_VERSION,
        "artifact_type": "model_audition_runs",
        "audition_id": audition_id,
        "task_id": task_id,
        "job_type": job_type,
        "status": status,
        "started_at": started_at,
        "finished_at": finished_at,
        "runs": run_records,
    }
    scorecard_payload = _scorecard_payload(
        audition_id=audition_id,
        task_id=task_id,
        job_type=job_type,
        status=status,
        score_records=score_records,
    )
    report_text = _render_report(
        task_id=task_id,
        job_type=job_type,
        status=status,
        runs=run_records,
        scorecard=scorecard_payload,
    )
    atomic_write_text(runs_path, _json_dumps(runs_payload))
    atomic_write_text(scorecard_path, _json_dumps(scorecard_payload))
    atomic_write_text(report_path, report_text)

    payload = {
        "schema_version": MODEL_AUDITION_SCHEMA_VERSION,
        "artifact_type": "model_audition_execute_result",
        "audition_id": audition_id,
        "task_id": task_id,
        "task_title": task.title,
        "task_status": task.status,
        "project_id": project_id,
        "job_type": job_type,
        "status": status,
        "dry_run": False,
        "selected_candidate_count": len(selected),
        "run_count": len(run_records),
        "plan_path": relative_path(root, plan_path),
        "runs_path": relative_path(root, runs_path),
        "scorecard_path": relative_path(root, scorecard_path),
        "report_path": relative_path(root, report_path),
        "runs": run_records,
        "advisory_ranking": scorecard_payload["advisory_ranking"],
        "will_call_models": True,
        "will_write_source": False,
        "will_write_workspace": False,
        "will_write_proposal_patch": False,
        "will_apply_patch": False,
        "will_verify": False,
        "will_commit_merge_push_or_promote": False,
    }
    return payload


def score_model_audition_response(
    *,
    response_text: str,
    run_payload: dict[str, Any],
    candidate: dict[str, Any],
    task_id: str,
    task_title: str,
    task_status: str,
) -> dict[str, Any]:
    text = response_text.strip()
    lowered = text.lower()
    score = 1.0
    deductions: list[str] = []

    status = str(run_payload.get("status") or "unknown")
    if status == "failed":
        score -= 0.75
        deductions.append("run_failed")
    elif status == "low_quality":
        score -= 0.35
        deductions.append("worker_low_quality")

    required_sections = (
        "## Task Grounding",
        "## Summary",
        "## Findings",
        "## Risks Or Questions",
        "## Suggested Next Dev-Flow Action",
    )
    for section in required_sections:
        if section.lower() not in lowered:
            score -= 0.08
            deductions.append(f"missing_section:{section}")
    if task_id not in text:
        score -= 0.25
        deductions.append("missing_task_id")
    if task_title and task_title.lower() not in lowered:
        score -= 0.10
        deductions.append("missing_task_title")
    if task_status and task_status.lower() not in lowered:
        score -= 0.10
        deductions.append("missing_task_status")
    if _has_false_claim(lowered):
        score -= 0.80
        deductions.append("false_claim")
    if "devflow " not in lowered and "human review" not in lowered:
        score -= 0.10
        deductions.append("missing_concrete_next_action")

    final_score = max(0.0, round(score, 2))
    return {
        "profile_id": candidate["profile_id"],
        "candidate_alias": candidate["candidate_alias"],
        "model": candidate.get("model"),
        "status": status,
        "score": final_score,
        "deductions": deductions or ["none"],
        "estimated_human_rework": _human_rework(final_score),
        "latency_resource_class": {
            "machine_class": candidate.get("machine_class"),
            "weight_class": candidate.get("weight_class"),
        },
    }


def _job_specs(job_type: str) -> tuple[CandidateSpec, ...]:
    try:
        return JOB_CANDIDATES[job_type]
    except KeyError as exc:
        valid = ", ".join(valid_model_audition_job_types())
        raise ModelAuditionError(f"Unknown job type '{job_type}'. Valid job types: {valid}") from exc


def _read_dry_run_plan(root: Path, task_id: str, job_type: str) -> dict[str, Any] | None:
    path = task_dir(root, task_id) / "model-auditions" / f"dry-run-{job_type}" / "plan.json"
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if payload.get("task_id") != task_id or payload.get("job_type") != job_type:
        return None
    return payload


def _read_response_text(root: Path, run_payload: dict[str, Any]) -> str:
    response_path = run_payload.get("response_path")
    if not isinstance(response_path, str) or not response_path:
        return ""
    path = Path(response_path)
    if not path.is_absolute():
        path = root / path
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _run_record(
    candidate: dict[str, Any],
    run_payload: dict[str, Any],
    score: dict[str, Any],
) -> dict[str, Any]:
    record = {
        "candidate_alias": candidate["candidate_alias"],
        "profile_id": candidate["profile_id"],
        "model": run_payload.get("model") or candidate.get("model"),
        "adapter": run_payload.get("adapter") or candidate.get("adapter"),
        "status": run_payload.get("status", "unknown"),
        "run_id": run_payload.get("run_id"),
        "evidence_dir": run_payload.get("evidence_dir"),
        "run_metadata_path": run_payload.get("run_metadata_path"),
        "response_path": run_payload.get("response_path"),
        "score": score["score"],
        "estimated_human_rework": score["estimated_human_rework"],
    }
    if run_payload.get("error_message"):
        record["error_message"] = run_payload["error_message"]
    return record


def _scorecard_payload(
    *,
    audition_id: str,
    task_id: str,
    job_type: str,
    status: str,
    score_records: list[dict[str, Any]],
) -> dict[str, Any]:
    ranking = sorted(score_records, key=lambda item: (-float(item["score"]), item["profile_id"]))
    return {
        "schema_version": MODEL_AUDITION_SCHEMA_VERSION,
        "artifact_type": "model_audition_scorecard",
        "audition_id": audition_id,
        "task_id": task_id,
        "job_type": job_type,
        "status": status,
        "scoring_mode": "deterministic_advisory",
        "advisory_ranking": ranking,
        "will_update_routing_policy": False,
    }


def _render_report(
    *,
    task_id: str,
    job_type: str,
    status: str,
    runs: list[dict[str, Any]],
    scorecard: dict[str, Any],
) -> str:
    lines = [
        "# Model Audition Report",
        "",
        f"- Task ID: {task_id}",
        f"- Job Type: {job_type}",
        f"- Status: {status}",
        "- Routing Policy Updated: no",
        "",
        "## Advisory Ranking",
    ]
    for item in scorecard["advisory_ranking"]:
        lines.append(
            f"- {item['profile_id']}: score {item['score']} "
            f"({item['estimated_human_rework']} human rework)"
        )
    lines.extend(["", "## Runs"])
    for run in runs:
        lines.append(f"- {run['profile_id']}: {run['status']} ({run.get('run_id') or 'no-run-id'})")
    return "\n".join(lines) + "\n"


def _has_false_claim(lowered: str) -> bool:
    false_claim_markers = (
        "i edited",
        "edited files",
        "i ran verification",
        "ran verification",
        "verification passed",
        "committed",
        "merged",
        "pushed",
        "promoted",
        "applied patch",
    )
    return any(marker in lowered for marker in false_claim_markers)


def _human_rework(score: float) -> str:
    if score >= 0.80:
        return "low"
    if score >= 0.55:
        return "medium"
    return "high"


def _candidate_payload(
    spec: CandidateSpec,
    *,
    task_id: str,
    rank: int,
    registry: Any,
    providers: dict[str, Any],
    installed_models: set[str],
    duplicate: bool,
) -> dict[str, Any]:
    agent = registry.agents.get(spec.profile_id)
    reasons: list[str] = []
    if agent is None:
        reasons.append("missing_profile")
    else:
        if duplicate:
            reasons.append("duplicate_profile")
        if not agent.enabled:
            reasons.append("agent_disabled")
        if agent.model not in installed_models:
            reasons.append("model_not_installed")
        provider = providers.get(agent.provider)
        if not is_local_model_worker_pool_agent(agent, provider=provider):
            reasons.append("unsafe_profile")

    eligible = not reasons
    payload = {
        "candidate_alias": spec.alias,
        "profile_id": spec.profile_id,
        "intent": spec.intent,
        "rank": rank,
        "eligible": eligible,
        "reasons": ["eligible"] if eligible else reasons,
    }
    if agent is not None:
        payload.update(_agent_fields(agent, task_id=task_id))
    return payload


def _agent_fields(agent: AgentDefinition, *, task_id: str) -> dict[str, Any]:
    return {
        "model": agent.model,
        "provider": agent.provider,
        "adapter": agent.adapter,
        "role": agent.role,
        "permission_mode": agent.default_mode,
        "machine_class": agent.machine_class,
        "weight_class": agent.weight_class,
        "model_role_name": agent.model_role_name,
        "hermes_delegable": agent.hermes_delegable,
        "expected_command": f"devflow agent run --task {task_id} --profile {agent.id} --json",
    }


def _json_dumps(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"
