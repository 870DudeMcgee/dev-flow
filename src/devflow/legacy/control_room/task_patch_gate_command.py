from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from devflow.legacy.control_room.patch_dry_run import PatchDryRun, preview_patch_dry_run
from devflow.legacy.control_room.patch_review import PatchReview, normalize_agent_patch_candidate, review_patch_candidate
from devflow.legacy.control_room.paths import relative_path
from devflow.legacy.control_room.project_registry import project_task_ref


class TaskPatchGateCommandError(ValueError):
    """User-facing task patch review/dry-run command error."""


@dataclass(frozen=True)
class _TaskPatchReviewCommandResult:
    root: Path
    task_id: str
    task_ref: str
    project_id: str | None
    review: PatchReview
    patch_review_path: str
    patch_review_json_path: str


@dataclass(frozen=True)
class _TaskPatchDryRunCommandResult:
    root: Path
    task_id: str
    task_ref: str
    project_id: str | None
    dry_run: PatchDryRun
    patch_review_status: str
    dry_run_path: str
    dry_run_json_path: str


def build_task_patch_review_result(
    root: Path,
    task_id: str,
    *,
    run_id: str | None = None,
    agent_id: str | None = None,
    project_id: str | None = None,
) -> _TaskPatchReviewCommandResult:
    repo_root = Path(root)
    selected_run_id = run_id
    try:
        if agent_id:
            selected_run_id = normalize_agent_patch_candidate(
                repo_root,
                task_id,
                agent_id,
                project_id=project_id,
            )
        review = review_patch_candidate(repo_root, task_id, run_id=selected_run_id, project_id=project_id)
    except (KeyError, FileNotFoundError, ValueError) as exc:
        raise TaskPatchGateCommandError(str(exc)) from exc

    run_dir = _run_dir(repo_root, task_id, review.run_id)
    return _TaskPatchReviewCommandResult(
        root=repo_root,
        task_id=task_id,
        task_ref=project_task_ref(task_id, project_id),
        project_id=project_id,
        review=review,
        patch_review_path=relative_path(repo_root, run_dir / "patch-review.md"),
        patch_review_json_path=relative_path(repo_root, run_dir / "patch-review.json"),
    )


def render_task_patch_review_lines(result: _TaskPatchReviewCommandResult) -> tuple[str, ...]:
    review = result.review
    lines = [f"Patch Review for {result.task_ref}"]
    if result.project_id:
        lines.append(f"project_root: {result.root}")
    lines.extend(
        [
            "",
            f"Run: {review.run_id}",
            f"Proposal classification: {review.proposal_classification}",
            f"Patch candidate: {'yes' if review.has_patch_candidate else 'no'}",
            f"Review status: {review.review_status}",
            f"Risk: {review.risk}",
            "",
            "Files touched:",
        ]
    )
    if review.files_touched:
        lines.extend(f"- {file_path}" for file_path in review.files_touched)
    else:
        lines.append("- None")
    if review.generated_or_forbidden_paths:
        lines.extend(["", "Artifact paths:"])
        lines.extend(f"- {file_path}" for file_path in review.generated_or_forbidden_paths)
    lines.extend(
        [
            "",
            "Artifacts:",
            f"patch_review: {result.patch_review_path}",
            f"patch_review_json: {result.patch_review_json_path}",
            "",
            "Next:",
            review.next_action.get("command") or "None",
        ]
    )
    return tuple(lines)


def build_task_patch_dry_run_result(
    root: Path,
    task_id: str,
    *,
    run_id: str | None = None,
    agent_id: str | None = None,
    project_id: str | None = None,
) -> _TaskPatchDryRunCommandResult:
    repo_root = Path(root)
    selected_run_id = run_id
    try:
        if agent_id:
            selected_run_id = normalize_agent_patch_candidate(
                repo_root,
                task_id,
                agent_id,
                project_id=project_id,
            )
        dry_run = preview_patch_dry_run(repo_root, task_id, run_id=selected_run_id, project_id=project_id)
    except (KeyError, FileNotFoundError, ValueError) as exc:
        raise TaskPatchGateCommandError(str(exc)) from exc

    run_dir = _run_dir(repo_root, task_id, dry_run.run_id)
    return _TaskPatchDryRunCommandResult(
        root=repo_root,
        task_id=task_id,
        task_ref=project_task_ref(task_id, project_id),
        project_id=project_id,
        dry_run=dry_run,
        patch_review_status=_patch_review_status(repo_root, task_id, dry_run.run_id),
        dry_run_path=relative_path(repo_root, run_dir / "patch-dry-run.md"),
        dry_run_json_path=relative_path(repo_root, run_dir / "patch-dry-run.json"),
    )


def render_task_patch_dry_run_lines(result: _TaskPatchDryRunCommandResult) -> tuple[str, ...]:
    dry_run = result.dry_run
    lines = [f"Patch Dry-run Preview for {result.task_ref}"]
    if result.project_id:
        lines.append(f"project_root: {result.root}")
    lines.extend(
        [
            "",
            f"Run: {dry_run.run_id}",
            f"Patch review status: {result.patch_review_status}",
            f"Dry-run status: {dry_run.dry_run_status}",
            f"Risk: {dry_run.risk}",
            "",
            "Files checked:",
        ]
    )
    if dry_run.files_checked:
        lines.extend(f"- {file_path}" for file_path in dry_run.files_checked)
    else:
        lines.append("- None")
    lines.extend(
        [
            "",
            "Hunks:",
            f"checked: {dry_run.hunks_checked}",
            f"matched: {dry_run.hunks_matched}",
            f"failed: {dry_run.hunks_failed}",
        ]
    )
    if dry_run.findings:
        lines.extend(["", "Findings:"])
        lines.extend(f"- {finding}" for finding in dry_run.findings)
    if dry_run.warnings:
        lines.extend(["", "Warnings:"])
        lines.extend(f"- {warning}" for warning in dry_run.warnings)
    lines.extend(
        [
            "",
            "Artifacts:",
            f"dry_run: {result.dry_run_path}",
            f"dry_run_json: {result.dry_run_json_path}",
            "",
            "Next:",
            "Review dry-run evidence manually. Do not apply anything automatically.",
        ]
    )
    return tuple(lines)


def _run_dir(root: Path, task_id: str, run_id: str) -> Path:
    return root / ".devflow" / "tasks" / task_id / "local-model-runs" / run_id


def _patch_review_status(root: Path, task_id: str, run_id: str) -> str:
    review_path = _run_dir(root, task_id, run_id) / "patch-review.json"
    try:
        data = json.loads(review_path.read_text(encoding="utf-8"))
    except Exception:
        return "unknown"
    if not isinstance(data, dict):
        return "unknown"
    return str(data.get("review_status") or "unknown")
