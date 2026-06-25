from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from devflow.control_room.git_worktree import branch_head, git_worker_lane_summary
from devflow.control_room.local_worker_lane import local_worker_lane_summary
from devflow.control_room.patch_dry_run import latest_patch_dry_run
from devflow.control_room.patch_review import latest_patch_review
from devflow.control_room.project_registry import project_task_ref
from devflow.control_room.proposal_normalizer import latest_normalized_proposal
from devflow.control_room.qwopus_evidence import build_qwopus_summary, qwopus_result_summary
from devflow.control_room.status_projection import build_task_status_projection
from devflow.control_room.task_closure import closure_next_action, read_closure


class TaskShowSummaryError(ValueError):
    pass


@dataclass(frozen=True)
class TaskShowSummary:
    root: Path
    task_id: str
    project_id: str | None
    lines: tuple[str, ...]


def build_task_show_summary(root: Path, task_id: str, project_id: str | None = None) -> TaskShowSummary:
    try:
        projection = build_task_status_projection(root, task_id)
    except KeyError as exc:
        raise TaskShowSummaryError(str(exc)) from exc

    task = projection.task
    task_path = projection.task_path
    lines: list[str] = []

    lines.append(f"task: {project_task_ref(task.id, project_id)}")
    if project_id:
        lines.append(f"project_root: {root}")
    lines.append(f"title: {task.title}")
    if task.definition_of_done:
        lines.append(f"definition_of_done: {task.definition_of_done}")
    lines.append(f"status: {task.status}")
    lines.append(f"worker: {task.worker}")
    lines.append(f"workspace: {task.workspace}")

    worker_lane = git_worker_lane_summary(root, task)
    if worker_lane:
        lines.append(f"worker_lane: {worker_lane['workspace_mode']}")
        lines.append(f"worker_branch: {worker_lane['worker_branch']}")
        lines.append(f"worktree_path: {worker_lane['worktree_path']}")
        lines.append(f"lane_readiness: {worker_lane['readiness_status']}")
        lines.append(f"lane_next_action: {worker_lane['next_safe_action']}")

    local_lane = local_worker_lane_summary(root, task)
    if local_lane:
        lines.append(f"local_worker_lane: {local_lane['lane_type']}")
        lines.append(f"local_worker: {local_lane['worker_id']}")
        lines.append(f"local_worker_readiness: {local_lane['readiness_status']}")
        lines.append(f"local_worker_next_action: {local_lane['next_safe_action']}")

    if task.branch_name:
        lines.append(f"branch_name: {task.branch_name}")
    if task.workspace_commit:
        lines.append(f"workspace_commit: {task.workspace_commit}")
    if task.workspace_dirty is not None:
        lines.append(f"workspace_dirty: {str(task.workspace_dirty).lower()}")
    lines.append(f"created_at: {task.created_at.isoformat()}")
    lines.append(f"updated_at: {task.updated_at.isoformat()}")
    lines.append(f"last_event: {task.last_event or ''}")
    lines.append(f"latest_log_line: {task.latest_log_line or ''}")
    lines.append(f"log_path: {task.log_path or ''}")
    lines.append(f"result_path: {task.result_path or ''}")
    lines.append(f"worker_command: {task.worker_command or ''}")

    closure = read_closure(root, task.id)
    closed_next_action = None
    if closure:
        closed_next_action = closure_next_action(root, task)
        lines.append("closed: yes")
        lines.append(f"outcome: {closure.get('outcome') or ''}")
        lines.append(f"reason: {closure.get('reason') or ''}")
        lines.append(f"closed_at: {closure.get('closed_at') or ''}")
        lines.append(f"next_action: {closed_next_action}")

    goal_link_yaml = task_path / "goal-link.yaml"
    _append_goal_link_lines(lines, goal_link_yaml)

    lines.append(f"verification_status: {projection.verification_status}")
    lines.append(f"verification_command: {projection.verification_command or ''}")
    if projection.verification_exit_code is not None:
        lines.append(f"verification_exit_code: {projection.verification_exit_code}")
    lines.append(f"verification_log_path: {projection.verification_log_path or ''}")
    lines.append(f"exit_code: {task.last_exit_code if task.last_exit_code is not None else ''}")

    finalization = _read_json_mapping(task_path / "finalization.json")
    promoted_event = _get_latest_promoted_event(task_path)
    suggested_next_action = projection.suggested_next_action
    if closure:
        suggested_next_action = closed_next_action or suggested_next_action
    finalized_commit = finalization.get("commit_hash")
    if isinstance(finalized_commit, str) and finalized_commit and not promoted_event and not closure:
        lines.append(f"finalized_commit: {finalized_commit}")
        if task.branch_name:
            lines.append(f"worker_branch_commit: {branch_head(root, task.branch_name) or 'unavailable'}")
        lines.append("promotion_status: main not promoted yet")
        suggested_next_action = f"devflow task promote-preview {task.id}"
    lines.append(f"suggested_next_action: {suggested_next_action}")

    if projection.manual_agent_state:
        lines.append(f"manual_agent_state: {projection.manual_agent_state}")
        if projection.manual_agent_handoff_path:
            lines.append(f"manual_agent_handoff: {projection.manual_agent_handoff_path}")
        if projection.manual_agent_result_path:
            lines.append(f"manual_agent_result: {projection.manual_agent_result_path}")
            lines.append("manual_agent_note: Dev-Flow verification required before promotion.")
        if projection.manual_agent_question:
            lines.append(f"manual_agent_question: {projection.manual_agent_question}")
        if projection.manual_agent_failure:
            lines.append(f"manual_agent_failure: {projection.manual_agent_failure}")

    if promoted_event:
        lines.append("promoted_changes:")
        added = promoted_event.get("added", [])
        modified = promoted_event.get("modified", [])
        deleted_applied = promoted_event.get("deleted_applied", [])
        if added:
            lines.append(f"  added: {', '.join(added)}")
        if modified:
            lines.append(f"  modified: {', '.join(modified)}")
        if deleted_applied:
            lines.append(f"  deleted_applied: {', '.join(deleted_applied)}")

    packet_json = task_path / "packet.json"
    if packet_json.exists():
        rel_path = _relative(root, packet_json)
        lines.append("packet_artifact: exists")
        lines.append(f"packet_path: {rel_path}")
        lines.append(f"packet_hint: run 'devflow task packet {task.id}' for the latest generated preview")
    else:
        lines.append("packet_artifact: missing")
        if goal_link_yaml.exists():
            lines.append(f"packet_hint: run 'devflow task packet {task.id}' to preview bounded worker context")

    _append_local_model_runs_lines(lines, root, task_path)
    _append_normalized_proposal_lines(lines, root, task.id)
    _append_patch_review_lines(lines, root, task.id)
    _append_patch_dry_run_lines(lines, root, task.id)
    _append_agent_patch_evidence_summary(lines, root, task_path)

    if projection.merge_ready is not None:
        ready_str = "yes" if projection.merge_ready else "no"
        lines.append(f"merge_ready: {ready_str}")
        if projection.readiness_reasons:
            lines.append("readiness_reasons:")
            for reason in projection.readiness_reasons:
                lines.append(f"  - {reason}")

    _append_jsonl_tail(lines, "latest_events", task_path / "events.jsonl")
    _append_jsonl_tail(lines, "open_questions", task_path / "questions.jsonl")
    _append_result_summary(lines, task_path / "result.md", summary=qwopus_result_summary(root, task.id))

    return TaskShowSummary(root=root, task_id=task.id, project_id=project_id, lines=tuple(lines))


def render_task_show_summary(summary: TaskShowSummary) -> list[str]:
    return list(summary.lines)


def _append_goal_link_lines(lines: list[str], goal_link_yaml: Path) -> None:
    if not goal_link_yaml.exists():
        return
    try:
        link_data = yaml.safe_load(goal_link_yaml.read_text(encoding="utf-8")) or {}
        lines.append("Goal Link:")
        lines.append(f"  Goal: {link_data.get('goal_id')}")
        lines.append(f"  Slice: {link_data.get('slice_id')}")
        lines.append(f"  Execution mode: {link_data.get('execution_mode')}")
        chk_req = str(link_data.get("human_checkpoint_required")).lower()
        lines.append(f"  Human checkpoint required: {chk_req}")
        promo_allowed = str(link_data.get("promotion_allowed")).lower()
        lines.append(f"  Promotion allowed: {promo_allowed}")
        lines.append(f"  Source: {link_data.get('slice_source_path')}")
    except Exception:
        return


def _append_local_model_runs_lines(lines: list[str], root: Path, task_path: Path) -> None:
    local_runs_dir = task_path / "local-model-runs"
    if not local_runs_dir.exists() or not local_runs_dir.is_dir():
        return
    runs = []
    for run_folder in local_runs_dir.iterdir():
        if run_folder.is_dir():
            response_md = run_folder / "response.md"
            if response_md.exists():
                runs.append((run_folder.name, response_md))
    if not runs:
        return
    runs.sort()
    _, latest_response_md = runs[-1]
    rel_response_md = _relative(root, latest_response_md)
    lines.append("Local Model Runs:")
    lines.append(f"  latest: {rel_response_md}")
    lines.append("  hint: review this evidence, then decide whether to run/apply/verify explicitly")


def _append_normalized_proposal_lines(lines: list[str], root: Path, task_id: str) -> None:
    normalized = latest_normalized_proposal(root, task_id)
    if not normalized:
        return
    proposal_path = normalized.get("proposal_path") or ""
    validation_label = "not_performed"
    validation_path = normalized.get("validation_path")
    if validation_path:
        validation_file = root / str(validation_path)
        try:
            validation_data = json.loads(validation_file.read_text(encoding="utf-8"))
            validation_label = "valid" if validation_data.get("valid") else "invalid"
        except Exception:
            validation_label = "unknown"
    lines.append("Normalized Proposals:")
    lines.append(f"  latest: {proposal_path}")
    lines.append(f"  classification: {normalized.get('classification')}")
    lines.append(f"  patch_candidate: {'yes' if normalized.get('has_patch_candidate') else 'no'}")
    lines.append(f"  validation: {validation_label}")
    lines.append("  hint: review proposal evidence before applying or verifying anything")


def _append_patch_review_lines(lines: list[str], root: Path, task_id: str) -> None:
    patch_review = latest_patch_review(root, task_id)
    if not patch_review:
        return
    lines.append("Patch Reviews:")
    lines.append(f"  latest: {patch_review.get('_review_path')}")
    lines.append(f"  status: {patch_review.get('review_status')}")
    lines.append(f"  risk: {patch_review.get('risk')}")
    lines.append(f"  files_touched: {len(patch_review.get('files_touched') or [])}")
    lines.append("  hint: review patch candidate before applying anything")


def _append_patch_dry_run_lines(lines: list[str], root: Path, task_id: str) -> None:
    patch_dry_run = latest_patch_dry_run(root, task_id)
    if not patch_dry_run:
        return
    lines.append("Patch Dry-runs:")
    lines.append(f"  latest: {patch_dry_run.get('_dry_run_path')}")
    lines.append(f"  status: {patch_dry_run.get('dry_run_status')}")
    lines.append(f"  risk: {patch_dry_run.get('risk')}")
    lines.append(
        f"  hunks: {patch_dry_run.get('hunks_matched', 0)} matched / "
        f"{patch_dry_run.get('hunks_failed', 0)} failed"
    )
    lines.append("  hint: dry-run only; review before applying anything")


def _append_agent_patch_evidence_summary(lines: list[str], root: Path, task_path: Path) -> None:
    agents_dir = task_path / "agents"
    if not agents_dir.exists() or not agents_dir.is_dir():
        return

    tracked_artifacts = (
        ("packet_path", "packet.json"),
        ("raw_output_path", "raw_output.md"),
        ("proposal_patch_path", "proposal.patch"),
        ("run_metadata_path", "run.json"),
        ("agent_result_path", "result.md"),
        ("agent_log_path", "logs/worker.log"),
        ("worker_failed_path", "worker_failed.json"),
        ("questions_path", "questions.jsonl"),
    )

    entries: list[tuple[str, list[tuple[str, Path]]]] = []
    for agent_dir in sorted(path for path in agents_dir.iterdir() if path.is_dir()):
        existing = [
            (label, agent_dir / artifact)
            for label, artifact in tracked_artifacts
            if (agent_dir / artifact).exists()
        ]
        if existing:
            entries.append((agent_dir.name, existing))

    if not entries:
        return

    lines.append("agent_evidence:")
    for agent_id, paths in entries:
        lines.append(f"  {agent_id}:")
        for label, artifact_path in paths:
            lines.append(f"    {label}: {_relative(root, artifact_path)}")
        if agent_id == "qwopus-implementer":
            _append_qwopus_latest_summary(lines, root, task_path, agent_id)


def _append_qwopus_latest_summary(lines: list[str], root: Path, task_path: Path, agent_id: str) -> None:
    summary = build_qwopus_summary(root, task_path, agent_id)
    if not summary:
        return
    lines.append(f"    latest_run_status: {summary['status']}")
    lines.append(f"    proposal_patch_bytes: {summary.get('proposal_patch_byte_length', 0)}")
    proposed_paths = summary.get("proposed_file_paths") or []
    lines.append(f"    proposed_file_count: {summary.get('proposed_file_count', 0)}")
    if proposed_paths:
        lines.append(f"    proposed_files: {', '.join(str(p) for p in proposed_paths)}")
    if summary.get("failure_reason"):
        lines.append(f"    failure_reason: {summary.get('failure_reason')}")
    if summary.get("patch_application_path"):
        lines.append(f"    patch_application_path: {summary.get('patch_application_path')}")
    if summary.get("latest_verification_status"):
        lines.append(f"    latest_verification_status: {summary.get('latest_verification_status')}")
    lines.append(f"    next_suggested_command: {summary.get('next_suggested_command')}")


def _append_jsonl_tail(lines: list[str], label: str, path: Path, limit: int = 5) -> None:
    lines.append(f"{label}:")
    if not path.exists() or not path.read_text(encoding="utf-8").strip():
        lines.append("  none")
        return
    jsonl_lines = path.read_text(encoding="utf-8").splitlines()[-limit:]
    for line in jsonl_lines:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            lines.append(f"  {line}")
            continue
        lines.append(f"  {event.get('timestamp', '')} {event.get('event', '')}")


def _append_result_summary(lines: list[str], path: Path, summary: str | None = None) -> None:
    lines.append("result_summary:")
    if summary:
        lines.append(f"  {summary}")
        return
    if not path.exists():
        lines.append("  none")
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and stripped not in {"## Summary", "## Status"}:
            lines.append(f"  {stripped}")
            return
    lines.append("  none")


def _get_latest_promoted_event(task_path: Path) -> dict[str, Any] | None:
    events_file = task_path / "events.jsonl"
    if not events_file.exists():
        return None
    latest_event = None
    try:
        with events_file.open("r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                    if event.get("event") == "task_promoted":
                        latest_event = event
                except Exception:
                    pass
    except Exception:
        pass
    return latest_event


def _read_json_mapping(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _relative(root: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path)
