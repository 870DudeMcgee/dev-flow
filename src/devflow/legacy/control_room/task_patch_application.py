from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from devflow.legacy.control_room.locks import task_mutation_lock
from devflow.legacy.control_room.models import TASK_SCHEMA_VERSION, TaskRecord
from devflow.legacy.control_room.patch_applier import (
    PatchApplicationError,
    PatchSelectionError,
    apply_patch_files,
    parse_unified_diff,
)
from devflow.legacy.control_room.patch_evidence import read_patch_application_evidence
from devflow.legacy.control_room.paths import relative_path, task_dir
from devflow.legacy.control_room.persistence import atomic_write_text, get_task, utc_now
from devflow.legacy.control_room.task_lifecycle import (
    append_task_event,
    invalidate_verification_after_workspace_mutation,
)
from devflow.legacy.control_room.task_workspace import validated_task_workspace


ACCEPTABLE_PATCH_REVIEW_STATUSES = {"low_risk_candidate", "review_required"}
ACCEPTABLE_PATCH_DRY_RUN_STATUSES = {"would_apply_cleanly", "would_create_files", "would_modify_with_warnings"}


@dataclass(frozen=True)
class _SelectedPatch:
    patch_path: Path
    agent_id: str | None
    run_id: str | None


def apply_task_patch_command(
    root: Path,
    task_id: str,
    agent_id: str | None = None,
    run_id: str | None = None,
) -> TaskRecord:
    with task_mutation_lock(root, task_id, "apply-patch"):
        return _apply_task_patch_locked(root, task_id, agent_id, run_id)


def _apply_task_patch_locked(
    root: Path,
    task_id: str,
    agent_id: str | None = None,
    run_id: str | None = None,
) -> TaskRecord:
    task_path = task_dir(root, task_id)
    task = get_task(root, task_id)
    workspace = validated_task_workspace(root, task)

    selected = _select_patch(task_path, task_id, agent_id=agent_id, run_id=run_id)
    patch_content = selected.patch_path.read_text(encoding="utf-8")
    patch_hash = hashlib.sha256(patch_content.encode("utf-8")).hexdigest()
    review_gate = _require_patch_review_and_dry_run_gate(
        root,
        task_id,
        target_patch=selected.patch_path,
        patch_hash=patch_hash,
        run_id=selected.run_id,
    )

    _reject_duplicate_patch_application(task_path, patch_hash)

    patch_files = parse_unified_diff(patch_content)
    result = apply_patch_files(workspace, patch_files, patch_hash=patch_hash)
    changed_files_payload = _changed_file_payload(result.changed_files)
    selected_run_id = review_gate["run_id"]

    evidence_path = _write_patch_application_evidence(
        root,
        task_path,
        task,
        selected.agent_id,
        selected_run_id,
        selected.patch_path,
        result.patch_hash,
        changed_files_payload,
        review_gate["patch_review_path"],
        review_gate["patch_dry_run_path"],
    )

    append_task_event(
        root,
        task_id,
        "patch_applied",
        {
            "agent_id": selected.agent_id,
            "run_id": selected_run_id,
            "patch_path": relative_path(root, selected.patch_path),
            "patch_hash": result.patch_hash,
            "patch_review_path": relative_path(root, review_gate["patch_review_path"]),
            "patch_dry_run_path": relative_path(root, review_gate["patch_dry_run_path"]),
            "patch_evidence_path": relative_path(root, evidence_path),
            "changed_files": changed_files_payload,
        },
    )

    patch_application = read_patch_application_evidence(task_path) or {}
    return invalidate_verification_after_workspace_mutation(root, task, patch_application=patch_application)


def _select_patch(
    task_path: Path,
    task_id: str,
    *,
    agent_id: str | None,
    run_id: str | None,
) -> _SelectedPatch:
    agents_dir = task_path / "agents"
    local_runs_dir = task_path / "local-model-runs"
    if run_id is None and (not agents_dir.exists() or not list(agents_dir.iterdir())):
        raise PatchSelectionError(f"No patches found for task {task_id}")

    selected_run_id: str | None = run_id

    if run_id is not None and agent_id is None:
        run_patch = local_runs_dir / run_id / "proposal.patch"
        if not run_patch.exists():
            raise PatchSelectionError(f"No proposal.patch found for local model run {run_id}")
        return _SelectedPatch(patch_path=run_patch, agent_id=None, run_id=selected_run_id)

    if agent_id:
        agent_patch = agents_dir / agent_id / "proposal.patch"
        if not agent_patch.exists():
            raise PatchSelectionError(f"No patch found for agent {agent_id}")
        return _SelectedPatch(patch_path=agent_patch, agent_id=agent_id, run_id=selected_run_id)

    found_patches: list[tuple[str, Path]] = []
    for child in agents_dir.iterdir():
        if child.is_dir() and (child / "proposal.patch").exists():
            found_patches.append((child.name, child / "proposal.patch"))

    if not found_patches:
        raise PatchSelectionError(f"No patches found under {agents_dir}")
    if len(found_patches) > 1:
        agents_list = ", ".join(f"'{name}'" for name, _ in found_patches)
        raise PatchSelectionError(
            f"Multiple proposal patches found: {agents_list}. "
            "Please specify which one to apply using --agent."
        )
    selected_agent, target_patch = found_patches[0]
    return _SelectedPatch(patch_path=target_patch, agent_id=selected_agent, run_id=selected_run_id)


def _reject_duplicate_patch_application(task_path: Path, patch_hash: str) -> None:
    events_file = task_path / "events.jsonl"
    if not events_file.exists():
        return
    for line in events_file.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("event") == "patch_applied" and event.get("patch_hash") == patch_hash:
            raise PatchApplicationError("Patch was already applied to this workspace")


def _changed_file_payload(changed_files: list[Any]) -> list[dict[str, Any]]:
    return [
        {"path": file.path, "operation": file.operation, "additions": file.additions, "deletions": file.deletions}
        for file in changed_files
    ]


def _write_patch_application_evidence(
    root: Path,
    task_path: Path,
    task: TaskRecord,
    agent_id: str | None,
    run_id: str | None,
    patch_path: Path,
    patch_hash: str,
    changed_files: list[dict[str, Any]],
    patch_review_path: Path,
    patch_dry_run_path: Path,
) -> Path:
    evidence = {
        "schema_version": TASK_SCHEMA_VERSION,
        "task_id": task.id,
        "agent_id": agent_id,
        "run_id": run_id,
        "patch_path": relative_path(root, patch_path),
        "patch_hash": patch_hash,
        "patch_review_path": relative_path(root, patch_review_path),
        "patch_dry_run_path": relative_path(root, patch_dry_run_path),
        "workspace": task.workspace,
        "changed_files": changed_files,
        "operation_summary": {
            "created": sum(1 for item in changed_files if item.get("operation") == "created"),
            "modified": sum(1 for item in changed_files if item.get("operation") == "modified"),
            "deleted": sum(1 for item in changed_files if item.get("operation") == "deleted"),
        },
        "applied_at": utc_now().isoformat(),
    }
    patches_dir = task_path / "patches"
    evidence_path = patches_dir / f"{patch_hash}.json"
    body = json.dumps(evidence, indent=2, sort_keys=True) + "\n"
    atomic_write_text(evidence_path, body)
    atomic_write_text(task_path / "patch-application.json", body)
    return evidence_path


def _require_patch_review_and_dry_run_gate(
    root: Path,
    task_id: str,
    *,
    target_patch: Path,
    patch_hash: str,
    run_id: str | None,
) -> dict[str, Any]:
    task_path = task_dir(root, task_id)
    runs_dir = task_path / "local-model-runs"
    if not runs_dir.exists() or not runs_dir.is_dir():
        raise PatchApplicationError(
            "Patch application requires fresh acceptable patch-review and patch-dry-run evidence before mutating the workspace."
        )

    if run_id is not None:
        run_path = runs_dir / run_id
        if not run_path.exists() or not run_path.is_dir():
            raise PatchApplicationError(f"Local model run '{run_id}' not found for task '{task_id}'.")
        candidates = [run_path]
    else:
        candidates = sorted(path for path in runs_dir.iterdir() if path.is_dir())

    matching: list[Path] = []
    for run_path in candidates:
        proposal_path = run_path / "proposal.patch"
        if proposal_path.exists() and _file_sha256(proposal_path) == patch_hash:
            matching.append(run_path)

    if not matching:
        raise PatchApplicationError(
            "Patch application requires matching reviewed dry-run evidence for the selected patch."
        )

    errors: list[str] = []
    for run_path in reversed(matching):
        try:
            review_path, dry_run_path = _validate_patch_gate_run(root, task_id, run_path, target_patch)
            return {
                "run_id": run_path.name,
                "patch_review_path": review_path,
                "patch_dry_run_path": dry_run_path,
            }
        except PatchApplicationError as exc:
            errors.append(str(exc))

    details = f" Last checked: {errors[-1]}" if errors else ""
    raise PatchApplicationError(
        "Patch application requires fresh acceptable patch-review and patch-dry-run evidence before mutating the workspace."
        + details
    )


def _validate_patch_gate_run(root: Path, task_id: str, run_path: Path, target_patch: Path) -> tuple[Path, Path]:
    proposal_path = run_path / "proposal.patch"
    review_path = run_path / "patch-review.json"
    dry_run_path = run_path / "patch-dry-run.json"
    if not review_path.exists() or not dry_run_path.exists():
        raise PatchApplicationError("patch-review.json and patch-dry-run.json are both required.")

    try:
        review = json.loads(review_path.read_text(encoding="utf-8"))
        dry_run = json.loads(dry_run_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PatchApplicationError("Patch review or dry-run evidence is malformed.") from exc
    if not isinstance(review, dict) or not isinstance(dry_run, dict):
        raise PatchApplicationError("Patch review or dry-run evidence is malformed.")

    if str(review.get("task_id") or "") != task_id or str(dry_run.get("task_id") or "") != task_id:
        raise PatchApplicationError("Patch review and dry-run evidence must match the task id.")
    if str(review.get("run_id") or "") != run_path.name or str(dry_run.get("run_id") or "") != run_path.name:
        raise PatchApplicationError("Patch review and dry-run evidence must match the local model run id.")

    review_status = str(review.get("review_status") or "unknown")
    if review_status not in ACCEPTABLE_PATCH_REVIEW_STATUSES:
        raise PatchApplicationError(f"Patch review status is not acceptable: {review_status}")

    dry_run_status = str(dry_run.get("dry_run_status") or "unknown")
    if dry_run_status not in ACCEPTABLE_PATCH_DRY_RUN_STATUSES:
        raise PatchApplicationError(f"Patch dry-run status is not acceptable: {dry_run_status}")
    if int(dry_run.get("hunks_failed") or 0) != 0:
        raise PatchApplicationError("Patch dry-run evidence has failed hunks.")

    proposal_rel = relative_path(root, proposal_path)
    review_rel = relative_path(root, review_path)
    if str(dry_run.get("proposal_patch_path") or "") != proposal_rel:
        raise PatchApplicationError("Patch dry-run evidence does not reference the reviewed proposal.patch.")
    if str(dry_run.get("patch_review_path") or "") != review_rel:
        raise PatchApplicationError("Patch dry-run evidence does not reference the matching patch-review.json.")

    proposal_mtime = proposal_path.stat().st_mtime_ns
    if review_path.stat().st_mtime_ns < proposal_mtime or dry_run_path.stat().st_mtime_ns < proposal_mtime:
        raise PatchApplicationError("Patch review or dry-run evidence is stale for the selected proposal.patch.")

    target_rel = relative_path(root, target_patch)
    review_patch_rel = str(review.get("patch_path") or "")
    if review_patch_rel and review_patch_rel not in {proposal_rel, target_rel}:
        raise PatchApplicationError("Patch review evidence references a different proposal.patch.")

    return review_path, dry_run_path


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
