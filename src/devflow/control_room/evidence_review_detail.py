from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from devflow.control_room.agent_evidence import AgentEvidenceSummary, summarize_agent_evidence
from devflow.control_room.git_worktree import is_git_worktree_task, worker_id_for_task
from devflow.control_room.log_sanitizer import sanitize_log_line
from devflow.control_room.patch_dry_run import latest_patch_dry_run
from devflow.control_room.patch_review import latest_patch_review
from devflow.control_room.paths import absolute_path, relative_path, task_dir, task_worker_dir
from devflow.control_room.review_readiness import ReviewReadinessProjection, build_review_readiness_projection
from devflow.control_room.status_projection import TaskStatusProjection


class EvidenceReviewEvent(BaseModel):
    timestamp: str | None = None
    event: str
    summary: str = ""


class EvidenceReviewVerification(BaseModel):
    status: str
    task_status: str | None = None
    exit_code: int | None = None
    log_path: str | None = None


class EvidenceReviewSummaryItem(BaseModel):
    label: str
    value: str


class EvidenceReviewArtifact(BaseModel):
    kind: str
    label: str
    text: str = ""
    path: str | None = None
    command: str | None = None
    timestamp: str | None = None
    priority: int = 50


class EvidenceReviewDetail(BaseModel):
    schema_version: int = 1
    task_id: str
    title: str
    status: str
    display_status: str
    review_state: str
    review_score: int
    review_priority: str
    review_reason: str
    review_command: str | None = None
    verification_status: str
    verification_command: str | None = None
    promotion_ready: bool = False
    merge_ready: bool | None = None
    blockers: list[str] = Field(default_factory=list)
    promotion_blockers: list[str] = Field(default_factory=list)
    evidence_paths: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    proposal_patch_paths: list[str] = Field(default_factory=list)
    patch_review_path: str | None = None
    patch_dry_run_path: str | None = None
    patch_application_path: str | None = None
    promotion_preview_path: str | None = None
    git_facts_path: str | None = None
    changed_files: list[str] = Field(default_factory=list)
    changed_file_preview: str | None = None
    operator_summary: str
    events_path: str
    verification_path: str
    recent_events: list[EvidenceReviewEvent] = Field(default_factory=list)
    verification: EvidenceReviewVerification | None = None
    artifacts: list[EvidenceReviewArtifact] = Field(default_factory=list)
    review_summary: list[EvidenceReviewSummaryItem] = Field(default_factory=list)
    latest_worker_line: str | None = None
    latest_verification_line: str | None = None
    result_preview: str | None = None
    agent_evidence_summary: dict[str, Any] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


def build_evidence_review_detail(
    root: Path,
    projection: TaskStatusProjection,
    *,
    review_readiness: ReviewReadinessProjection | None = None,
    worker_lane: dict[str, Any] | None = None,
    local_worker_lane: dict[str, Any] | None = None,
    project_id: str | None = None,
) -> EvidenceReviewDetail:
    """Build the operator-facing story for task evidence and review readiness."""
    root = root.resolve()
    task = projection.task
    base = task_dir(root, task.id)
    notes: list[str] = []
    review = review_readiness or build_review_readiness_projection(
        root,
        task.id,
        task=task,
        status_projection=projection,
        project_id=project_id,
    )
    agent_summary = summarize_agent_evidence(root, task.id)
    recent_events = _recent_events(root, base / "events.jsonl", notes)
    latest_timestamp = recent_events[-1].timestamp if recent_events else None
    verification = _verification_detail(base / "verification.json", notes)
    latest_worker_line = _artifact_preview(root, task.log_path, notes)
    latest_verification_line = _artifact_preview(root, projection.verification_log_path, notes)
    result_preview = _artifact_preview(root, task.result_path, notes)
    patch_review = latest_patch_review(root, task.id)
    patch_dry_run = latest_patch_dry_run(root, task.id)
    patch_application_path = _optional_existing_path(root, base / "patch-application.json")
    promotion_preview, promotion_preview_path = _promotion_preview(root, task)
    git_facts_path = _git_facts_path(root, task)
    proposal_patch_paths = _proposal_patch_paths(root, task.id)
    patch_review_path = _latest_payload_path(patch_review, "_review_path")
    patch_dry_run_path = _latest_payload_path(patch_dry_run, "_dry_run_path")
    workspace_changed_files = _changed_workspace_files(root, task.workspace, notes)
    changed_files = _changed_files(
        root,
        promotion_preview=promotion_preview,
        patch_review=patch_review,
        patch_dry_run=patch_dry_run,
        workspace_changed_files=workspace_changed_files,
    )
    changed_file_preview = _changed_file_contents(root, task.workspace, workspace_changed_files, notes)
    missing_evidence: list[str] = []
    evidence_paths = _evidence_paths(
        root,
        task_id=task.id,
        task_log_path=task.log_path,
        result_path=task.result_path,
        verification_log_path=projection.verification_log_path,
        missing_evidence=missing_evidence,
        review=review,
        worker_lane=worker_lane,
        local_worker_lane=local_worker_lane,
        agent_summary=agent_summary,
        proposal_patch_paths=proposal_patch_paths,
        patch_review_path=patch_review_path,
        patch_dry_run_path=patch_dry_run_path,
        patch_application_path=patch_application_path,
        promotion_preview_path=promotion_preview_path,
        git_facts_path=git_facts_path,
    )
    blockers = _dedupe([*review.blockers, *projection.promotion_blockers])
    artifacts = _artifacts(
        root,
        projection=projection,
        review=review,
        agent_summary=agent_summary,
        patch_review_path=patch_review_path,
        patch_dry_run_path=patch_dry_run_path,
        patch_application_path=patch_application_path,
        latest_timestamp=latest_timestamp,
        latest_worker_line=latest_worker_line,
        latest_verification_line=latest_verification_line,
        result_preview=result_preview,
    )
    operator_summary = _operator_summary(
        projection,
        review_state=review.review_state,
        blockers=blockers,
        agent_summary=agent_summary,
    )

    return EvidenceReviewDetail(
        task_id=task.id,
        title=task.title,
        status=task.status,
        display_status=projection.display_status,
        review_state=review.review_state,
        review_score=review.score,
        review_priority=_review_priority(review.review_state),
        review_reason=_review_reason(projection, review, operator_summary=operator_summary),
        review_command=review.next_command,
        verification_status=projection.verification_status or "not_run",
        verification_command=projection.verification_command,
        promotion_ready=projection.promotion_ready,
        merge_ready=projection.merge_ready,
        blockers=blockers,
        promotion_blockers=projection.promotion_blockers,
        evidence_paths=evidence_paths,
        missing_evidence=missing_evidence,
        proposal_patch_paths=proposal_patch_paths,
        patch_review_path=patch_review_path,
        patch_dry_run_path=patch_dry_run_path,
        patch_application_path=patch_application_path,
        promotion_preview_path=promotion_preview_path,
        git_facts_path=git_facts_path,
        changed_files=changed_files,
        changed_file_preview=changed_file_preview or None,
        operator_summary=operator_summary,
        events_path=relative_path(root, base / "events.jsonl"),
        verification_path=relative_path(root, base / "verification.json"),
        recent_events=recent_events,
        verification=verification,
        artifacts=artifacts,
        review_summary=_review_summary(
            task_id=task.id,
            title=task.title,
            status=task.status,
            review_state=review.review_state,
            verification_status=projection.verification_status or "not_run",
            changed_files=changed_files,
            changed_file_preview=changed_file_preview,
            next_command=review.next_command or projection.dashboard_next_action.command or f"devflow task show {task.id}",
            worker_lane=worker_lane,
            local_worker_lane=local_worker_lane,
            agent_summary=agent_summary,
        ),
        latest_worker_line=latest_worker_line,
        latest_verification_line=latest_verification_line,
        result_preview=result_preview,
        agent_evidence_summary=_compact_agent_evidence_summary(agent_summary),
        notes=notes,
    )


def _evidence_paths(
    root: Path,
    *,
    task_id: str,
    task_log_path: str | None,
    result_path: str | None,
    verification_log_path: str | None,
    missing_evidence: list[str],
    review: ReviewReadinessProjection,
    worker_lane: dict[str, Any] | None,
    local_worker_lane: dict[str, Any] | None,
    agent_summary: AgentEvidenceSummary,
    proposal_patch_paths: list[str],
    patch_review_path: str | None,
    patch_dry_run_path: str | None,
    patch_application_path: str | None,
    promotion_preview_path: str | None,
    git_facts_path: str | None,
) -> list[str]:
    base = task_dir(root, task_id)
    task_metadata_path = _record_required_path(root, base / "task.yaml", missing_evidence)
    events_path = _record_required_path(root, base / "events.jsonl", missing_evidence)
    verification_path = _record_required_path(root, base / "verification.json", missing_evidence)
    paths = [
        task_metadata_path,
        events_path,
        _display_artifact_path(root, task_log_path),
        _display_artifact_path(root, result_path),
        _display_artifact_path(root, verification_log_path),
        verification_path,
        *review.evidence,
        *proposal_patch_paths,
        patch_review_path,
        patch_dry_run_path,
        patch_application_path,
        promotion_preview_path,
        git_facts_path,
    ]
    if worker_lane:
        paths.extend(str(path) for path in worker_lane.get("evidence_paths") or [])
    if local_worker_lane:
        paths.extend(str(path) for path in local_worker_lane.get("evidence_paths") or [])
    paths.extend(_agent_evidence_paths(agent_summary))
    return sorted(path for path in _dedupe(paths) if path)


def _agent_evidence_paths(summary: AgentEvidenceSummary) -> list[str]:
    paths: list[str] = []
    if summary.manual_result_path:
        paths.append(summary.manual_result_path)
    if summary.shell_evidence:
        paths.extend([summary.shell_evidence.log_path, summary.shell_evidence.result_path])
    for run in summary.local_model_runs:
        paths.extend([run.run_metadata_path, run.response_path])
    for agent in summary.local_patch_agents:
        paths.extend([agent.proposal_patch_path, agent.result_path])
    if summary.local_worker_lane:
        paths.extend(str(path) for path in summary.local_worker_lane.get("evidence_paths") or [])
    return [path for path in paths if path]


def _artifacts(
    root: Path,
    *,
    projection: TaskStatusProjection,
    review: ReviewReadinessProjection,
    agent_summary: AgentEvidenceSummary,
    patch_review_path: str | None,
    patch_dry_run_path: str | None,
    patch_application_path: str | None,
    latest_timestamp: str | None,
    latest_worker_line: str | None,
    latest_verification_line: str | None,
    result_preview: str | None,
) -> list[EvidenceReviewArtifact]:
    task = projection.task
    artifacts: list[EvidenceReviewArtifact] = []
    result_path = _display_artifact_path(root, task.result_path)
    if result_path:
        artifacts.append(
            EvidenceReviewArtifact(
                kind="result",
                label="Worker result",
                text=result_preview or result_path,
                path=result_path,
                timestamp=latest_timestamp,
                priority=10,
            )
        )
    log_path = _display_artifact_path(root, task.log_path)
    if log_path:
        artifacts.append(
            EvidenceReviewArtifact(
                kind="worker log",
                label="Worker log",
                text=latest_worker_line or log_path,
                path=log_path,
                timestamp=latest_timestamp,
                priority=20,
            )
        )
    verification_source = _artifact_path(root, projection.verification_log_path)
    verification_path = (
        _display_artifact_path(root, projection.verification_log_path)
        if verification_source and verification_source.exists()
        else None
    )
    has_verification_output = bool(
        projection.verification_command
        or latest_verification_line
        or (projection.verification_status and projection.verification_status not in {"not_run", "missing", "unknown"})
    )
    if has_verification_output and (verification_path or projection.verification_command):
        artifacts.append(
            EvidenceReviewArtifact(
                kind="verification",
                label="Verification",
                text=projection.verification_command or latest_verification_line or verification_path or "verification",
                path=verification_path,
                command=projection.verification_command,
                timestamp=latest_timestamp,
                priority=15,
            )
        )
    if patch_review_path:
        artifacts.append(
            EvidenceReviewArtifact(
                kind="patch review",
                label="Patch review",
                text=patch_review_path,
                path=patch_review_path,
                timestamp=latest_timestamp,
                priority=22,
            )
        )
    if patch_dry_run_path:
        artifacts.append(
            EvidenceReviewArtifact(
                kind="patch dry-run",
                label="Patch dry-run",
                text=patch_dry_run_path,
                path=patch_dry_run_path,
                timestamp=latest_timestamp,
                priority=23,
            )
        )
    if patch_application_path:
        artifacts.append(
            EvidenceReviewArtifact(
                kind="patch application",
                label="Patch application",
                text=patch_application_path,
                path=patch_application_path,
                timestamp=latest_timestamp,
                priority=24,
            )
        )
    if review.promotion_preview_path:
        artifacts.append(
            EvidenceReviewArtifact(
                kind="promotion preview",
                label="Promotion preview",
                text=review.promotion_preview_path,
                path=review.promotion_preview_path,
                timestamp=latest_timestamp,
                priority=30,
            )
        )
    artifacts.extend(_agent_artifacts(agent_summary, latest_timestamp=latest_timestamp))
    return _dedupe_artifacts(artifacts)


def _agent_artifacts(summary: AgentEvidenceSummary, *, latest_timestamp: str | None) -> list[EvidenceReviewArtifact]:
    artifacts: list[EvidenceReviewArtifact] = []
    for run in summary.local_model_runs:
        identity = run.worker_id or run.profile_id or "local model"
        model = f" - {run.model}" if run.model else ""
        artifacts.append(
            EvidenceReviewArtifact(
                kind="model run",
                label=f"{identity} run",
                text=f"{run.status}{model}",
                path=run.run_metadata_path,
                timestamp=latest_timestamp,
                priority=25,
            )
        )
        if run.response_path:
            artifacts.append(
                EvidenceReviewArtifact(
                    kind="model response",
                    label=f"{identity} response",
                    text=run.response_path,
                    path=run.response_path,
                    timestamp=latest_timestamp,
                    priority=26,
                )
            )
    for agent in summary.local_patch_agents:
        if agent.proposal_patch_path:
            artifacts.append(
                EvidenceReviewArtifact(
                    kind="patch proposal",
                    label=f"{agent.agent_id} proposal",
                    text=agent.proposal_patch_path,
                    path=agent.proposal_patch_path,
                    timestamp=latest_timestamp,
                    priority=24,
                )
            )
        if agent.result_path:
            artifacts.append(
                EvidenceReviewArtifact(
                    kind="agent result",
                    label=f"{agent.agent_id} result",
                    text=agent.result_path,
                    path=agent.result_path,
                    timestamp=latest_timestamp,
                    priority=27,
                )
            )
    if summary.manual_result_path:
        artifacts.append(
            EvidenceReviewArtifact(
                kind="manual result",
                label="Manual worker result",
                text=summary.manual_result_path,
                path=summary.manual_result_path,
                timestamp=latest_timestamp,
                priority=28,
            )
        )
    return artifacts


def _review_summary(
    *,
    task_id: str,
    title: str,
    status: str,
    review_state: str,
    verification_status: str,
    changed_files: list[str],
    changed_file_preview: str,
    next_command: str,
    worker_lane: dict[str, Any] | None,
    local_worker_lane: dict[str, Any] | None,
    agent_summary: AgentEvidenceSummary,
) -> list[EvidenceReviewSummaryItem]:
    items = [
        EvidenceReviewSummaryItem(label="Task", value=f"{task_id} - {title}"),
        EvidenceReviewSummaryItem(label="Status", value=status),
        EvidenceReviewSummaryItem(label="Review state", value=review_state),
        EvidenceReviewSummaryItem(label="Verification", value=verification_status),
        EvidenceReviewSummaryItem(
            label="Changed files",
            value="\n".join(changed_files) if changed_files else "No file changes detected",
        ),
        EvidenceReviewSummaryItem(label="Task contents", value=changed_file_preview or "No changed file preview available"),
        EvidenceReviewSummaryItem(label="Next action", value=next_command),
    ]
    if worker_lane:
        items.insert(4, EvidenceReviewSummaryItem(label="Worker lane", value=str(worker_lane["workspace_mode"])))
        items.insert(5, EvidenceReviewSummaryItem(label="Lane readiness", value=str(worker_lane["readiness_status"])))
    if local_worker_lane:
        items.insert(4, EvidenceReviewSummaryItem(label="Local worker", value=str(local_worker_lane["worker_id"])))
        items.insert(
            5,
            EvidenceReviewSummaryItem(
                label="Local worker readiness",
                value=str(local_worker_lane["readiness_status"]),
            ),
        )
    if agent_summary.has_worker_evidence:
        items.insert(
            4,
            EvidenceReviewSummaryItem(
                label="Worker evidence",
                value=agent_summary.next_safe_action,
            ),
        )
    return items


def _operator_summary(
    projection: TaskStatusProjection,
    *,
    review_state: str,
    blockers: list[str],
    agent_summary: AgentEvidenceSummary,
) -> str:
    if agent_summary.has_worker_evidence and review_state == "not_ready":
        return "Worker/model evidence is captured; review it before the next gate."
    if blockers:
        return blockers[0]
    if projection.ready_to_promote or review_state == "ready_for_review":
        return "Verification and promotion evidence are ready for review."
    if review_state == "needs_promotion_preview":
        return "Verification passed; generate a promotion preview next."
    if projection.needs_verification or review_state == "needs_verification":
        return "Worker output is captured; verification is the next gate."
    if review_state == "verification_failed":
        return "Verification failed; inspect logs or rerun verification."
    if agent_summary.has_worker_evidence:
        return "Worker/model evidence is captured; review it before the next gate."
    if projection.task.status == "running":
        return "Worker is still running."
    return projection.dashboard_next_action.reason or projection.display_status


def _review_reason(
    projection: TaskStatusProjection,
    review: ReviewReadinessProjection,
    *,
    operator_summary: str,
) -> str:
    if review.blockers:
        return "; ".join(review.blockers)
    if projection.promotion_blockers:
        return "; ".join(projection.promotion_blockers)
    if projection.dashboard_next_action.reason:
        return projection.dashboard_next_action.reason
    return operator_summary


def _review_priority(review_state: str) -> str:
    if review_state in {"blocked", "worker_failed", "verification_failed", "ready_for_review"}:
        return "high"
    if review_state in {"needs_promotion_preview", "needs_verification"}:
        return "medium"
    return "low"


def _compact_agent_evidence_summary(summary: AgentEvidenceSummary) -> dict[str, Any]:
    return {
        "has_worker_evidence": summary.has_worker_evidence,
        "local_model_run_count": len(summary.local_model_runs),
        "local_patch_agent_count": len(summary.local_patch_agents),
        "manual_result_present": summary.manual_result_present,
        "next_safe_action": summary.next_safe_action,
    }


def _record_required_path(root: Path, path: Path, missing_evidence: list[str]) -> str | None:
    rel = relative_path(root, path)
    if path.exists():
        return rel
    missing_evidence.append(rel)
    return None


def _optional_existing_path(root: Path, path: Path) -> str | None:
    return relative_path(root, path) if path.exists() else None


def _latest_payload_path(payload: dict[str, Any] | None, key: str) -> str | None:
    if not payload:
        return None
    value = payload.get(key)
    return value if isinstance(value, str) and value else None


def _proposal_patch_paths(root: Path, task_id: str) -> list[str]:
    base = task_dir(root, task_id)
    paths: list[Path] = []
    for parent_name in ("agents", "local-model-runs"):
        parent = base / parent_name
        if not parent.exists():
            continue
        paths.extend(
            path
            for path in parent.glob("*/proposal.patch")
            if path.exists() and path.is_file() and path.stat().st_size > 0
        )
    return sorted({relative_path(root, path) for path in paths})


def _promotion_preview(root: Path, task: Any) -> tuple[dict[str, Any] | None, str | None]:
    for path in _promotion_preview_candidates(root, task):
        payload = _read_json_object(path)
        if payload:
            return payload, relative_path(root, path)
    return None, None


def _promotion_preview_candidates(root: Path, task: Any) -> list[Path]:
    candidates: list[Path] = []
    if is_git_worktree_task(task):
        candidates.append(task_worker_dir(root, task.id, worker_id_for_task(task)) / "promotion-preview.json")
    candidates.append(task_dir(root, task.id) / "promotion-preview.json")
    return candidates


def _git_facts_path(root: Path, task: Any) -> str | None:
    if not is_git_worktree_task(task):
        return None
    path = task_worker_dir(root, task.id, worker_id_for_task(task)) / "git.json"
    return relative_path(root, path) if path.exists() else None


def _read_json_object(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _changed_files(
    root: Path,
    *,
    promotion_preview: dict[str, Any] | None,
    patch_review: dict[str, Any] | None,
    patch_dry_run: dict[str, Any] | None,
    workspace_changed_files: list[str],
) -> list[str]:
    files: list[str] = []
    if promotion_preview:
        for key in ("changed_files", "added", "modified", "deleted", "untracked", "binary"):
            value = promotion_preview.get(key)
            if isinstance(value, list):
                files.extend(_metadata_file_value(root, item) for item in value)
        renamed = promotion_preview.get("renamed")
        if isinstance(renamed, list):
            for item in renamed:
                if isinstance(item, dict):
                    files.append(_metadata_file_value(root, item.get("to") or item.get("path") or item))
                else:
                    files.append(_metadata_file_value(root, item))
    if patch_review and isinstance(patch_review.get("files_touched"), list):
        files.extend(_metadata_file_value(root, item) for item in patch_review["files_touched"])
    if patch_dry_run:
        for key in ("files_checked", "files_would_create", "files_would_modify", "files_would_delete"):
            value = patch_dry_run.get(key)
            if isinstance(value, list):
                files.extend(_metadata_file_value(root, item) for item in value)
    files.extend(workspace_changed_files)
    return sorted({path for path in files if path})


def _metadata_file_value(root: Path, value: Any) -> str:
    if isinstance(value, dict):
        return _scrub_project_root(root, str(value))
    text = str(value)
    path = Path(text)
    if path.is_absolute():
        try:
            return path.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            return _scrub_project_root(root, text)
    return text


def _changed_workspace_files(root: Path, workspace_value: str, notes: list[str], *, limit: int = 20) -> list[str]:
    workspace = absolute_path(root, workspace_value).resolve()
    if not workspace.is_dir():
        notes.append(f"workspace unavailable for review summary: {workspace_value}")
        return []

    changed: list[str] = []
    for path in sorted(workspace.rglob("*")):
        if not path.is_file():
            continue
        try:
            name = path.relative_to(workspace).as_posix()
        except ValueError:
            continue
        if _is_ignored_review_name(name):
            continue
        target = root / name
        try:
            if not target.exists() or (target.is_file() and path.read_bytes() != target.read_bytes()):
                changed.append(name)
        except OSError:
            changed.append(name)
        if len(changed) >= limit:
            break
    return changed


def _changed_file_contents(
    root: Path,
    workspace_value: str,
    changed_files: list[str],
    notes: list[str],
    *,
    limit: int = 5,
) -> str:
    workspace = absolute_path(root, workspace_value).resolve()
    previews: list[str] = []
    for name in changed_files[:limit]:
        path = workspace / name
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            notes.append(f"{name} preview unavailable: {exc}")
            continue
        lines = []
        for line in raw.splitlines():
            preview = sanitize_log_line(line, max_chars=180)
            if preview:
                lines.append(preview)
        if lines:
            previews.append(f"{name}: " + "\n".join(lines[:4]))
    return "\n".join(previews)


def _is_ignored_review_name(name: str) -> bool:
    ignored = {".git", ".devflow", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".venv"}
    return any(part in ignored for part in Path(name).parts)


def _recent_events(root: Path, path: Path, notes: list[str], *, limit: int = 5) -> list[EvidenceReviewEvent]:
    if not path.exists():
        notes.append("events.jsonl is missing")
        return []
    events: list[EvidenceReviewEvent] = []
    malformed = 0
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        notes.append(f"events.jsonl unreadable: {exc}")
        return []
    for raw_line in lines:
        if not raw_line.strip():
            continue
        try:
            event = json.loads(raw_line)
        except json.JSONDecodeError:
            malformed += 1
            continue
        if not isinstance(event, dict):
            malformed += 1
            continue
        events.append(
            EvidenceReviewEvent(
                timestamp=str(event.get("timestamp")) if event.get("timestamp") else None,
                event=str(event.get("event") or "unknown"),
                summary=_event_summary(root, event),
            )
        )
    if malformed:
        notes.append(f"{malformed} malformed event line(s) omitted")
    return events[-limit:]


def _event_summary(root: Path, event: dict[str, Any]) -> str:
    safe_keys = ("status", "task_status", "exit_code", "log_path", "result_path", "cwd", "outcome", "reason")
    parts: list[str] = []
    for key in safe_keys:
        value = event.get(key)
        if value is None:
            continue
        parts.append(f"{key}={_safe_summary_value(root, value)}")
    return ", ".join(parts)


def _verification_detail(path: Path, notes: list[str]) -> EvidenceReviewVerification | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        notes.append(f"verification.json unreadable: {exc}")
        return None
    if not isinstance(payload, dict):
        notes.append("verification.json is not an object")
        return None
    return EvidenceReviewVerification(
        status=str(payload.get("status") or "unknown"),
        task_status=str(payload.get("task_status")) if payload.get("task_status") is not None else None,
        exit_code=payload.get("exit_code") if isinstance(payload.get("exit_code"), int) else None,
        log_path=str(payload.get("log_path")) if payload.get("log_path") is not None else None,
    )


def _artifact_preview(root: Path, relative_or_absolute_path: str | None, notes: list[str]) -> str | None:
    path = _artifact_path(root, relative_or_absolute_path)
    if path is None:
        return None
    if not path.exists():
        notes.append(f"{relative_or_absolute_path} is missing")
        return None
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        notes.append(f"{relative_or_absolute_path} unreadable: {exc}")
        return None
    for line in reversed(lines):
        preview = sanitize_log_line(line, max_chars=220)
        if preview.startswith("$ "):
            continue
        if preview:
            return _scrub_project_root(root, preview)
    return None


def _artifact_path(root: Path, relative_or_absolute_path: str | None) -> Path | None:
    if not relative_or_absolute_path:
        return None
    path = Path(relative_or_absolute_path)
    candidate = path if path.is_absolute() else root / path
    try:
        candidate.resolve().relative_to(root.resolve())
    except ValueError:
        return None
    return candidate


def _display_artifact_path(root: Path, relative_or_absolute_path: str | None) -> str | None:
    path = _artifact_path(root, relative_or_absolute_path)
    if path is None:
        return relative_or_absolute_path
    return relative_path(root, path)


def _safe_summary_value(root: Path, value: Any) -> str:
    if isinstance(value, (dict, list)):
        return "<structured>"
    return _scrub_project_root(root, sanitize_log_line(str(value), max_chars=120))


def _scrub_project_root(root: Path, value: str) -> str:
    scrubbed = _scrub_quarantined_checkout(value)
    candidates = {root.as_posix(), root.resolve().as_posix()}
    for candidate in sorted(candidates, key=len, reverse=True):
        scrubbed = scrubbed.replace(candidate, "<repo-root>")
    return scrubbed


def _scrub_quarantined_checkout(value: str) -> str:
    return value.replace("/Users/jewelbait/Desktop/DevFlow", "<quarantined-devflow>")


def _dedupe(values: list[str | None]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def _dedupe_artifacts(artifacts: list[EvidenceReviewArtifact]) -> list[EvidenceReviewArtifact]:
    seen: set[tuple[str, str, str]] = set()
    deduped: list[EvidenceReviewArtifact] = []
    for artifact in sorted(artifacts, key=lambda item: (item.priority, item.kind, item.path or "")):
        key = (artifact.kind, artifact.path or "", artifact.command or "")
        if key in seen:
            continue
        seen.add(key)
        deduped.append(artifact)
    return deduped
