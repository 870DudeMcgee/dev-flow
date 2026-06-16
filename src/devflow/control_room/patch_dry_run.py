from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
from typing import Any

import yaml

from devflow.control_room.patch_proposal import (
    PatchProposalFile as PatchFile,
    PatchProposalHunk as PatchHunk,
    PatchProposalParseError,
    parse_patch_proposal,
    resolve_workspace_patch_target,
)
from devflow.control_room.patch_review import is_dangerous_path
from devflow.control_room.paths import absolute_path, relative_path, task_dir


REJECTED_REVIEW_STATUSES = {
    "dangerous_patch",
    "invalid_patch",
    "no_patch_candidate",
}

RISK_ORDER = {
    "low": 0,
    "medium": 1,
    "high": 2,
    "critical": 3,
    "unknown": -1,
}


@dataclass
class PatchDryRun:
    schema_version: int
    task_id: str
    run_id: str
    proposal_patch_path: str
    patch_review_path: str
    workspace_path: str
    dry_run_status: str
    risk: str
    files_checked: list[str]
    files_missing: list[str]
    files_would_create: list[str]
    files_would_modify: list[str]
    files_would_delete: list[str]
    hunks_checked: int
    hunks_matched: int
    hunks_failed: int
    hunk_results: list[dict[str, Any]]
    findings: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    next_action: dict[str, str] = field(default_factory=dict)

    def to_json_dict(self) -> dict[str, Any]:
        return asdict(self)


def latest_patch_dry_run(root: Path, task_id: str) -> dict[str, Any] | None:
    runs_dir = task_dir(root, task_id) / "local-model-runs"
    if not runs_dir.exists() or not runs_dir.is_dir():
        return None
    candidates = sorted(p for p in runs_dir.iterdir() if p.is_dir() and (p / "patch-dry-run.json").exists())
    if not candidates:
        return None
    latest = candidates[-1] / "patch-dry-run.json"
    try:
        data = json.loads(latest.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    data["_dry_run_path"] = relative_path(root, candidates[-1] / "patch-dry-run.md")
    return data


def preview_patch_dry_run(
    root: Path,
    task_id: str,
    *,
    run_id: str | None = None,
    project_id: str | None = None,
) -> PatchDryRun:
    repo_root = root.resolve()
    selected_run_id, run_path = _resolve_run(repo_root, task_id, run_id)
    patch_path = run_path / "proposal.patch"
    review_path = run_path / "patch-review.json"

    if not patch_path.exists():
        raise FileNotFoundError(f"proposal.patch not found for local model run '{selected_run_id}'.")

    try:
        review = json.loads(review_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"patch-review.json is malformed for local model run '{selected_run_id}'.") from exc
    if not isinstance(review, dict):
        raise ValueError(f"patch-review.json is malformed for local model run '{selected_run_id}'.")

    review_status = str(review.get("review_status") or "unknown")
    review_risk = _normalize_risk(str(review.get("risk") or "unknown"))
    base = _base_result(repo_root, task_id, selected_run_id, patch_path, review_path)

    if review_status in REJECTED_REVIEW_STATUSES:
        result = PatchDryRun(
            **base,
            workspace_path=_task_workspace_display(repo_root, task_id),
            dry_run_status="rejected_by_patch_review",
            risk="critical" if review_status == "dangerous_patch" else review_risk,
            files_checked=[],
            files_missing=[],
            files_would_create=[],
            files_would_modify=[],
            files_would_delete=[],
            hunks_checked=0,
            hunks_matched=0,
            hunks_failed=0,
            hunk_results=[],
            findings=["Patch review gate did not approve this as a reviewable candidate."],
            warnings=[],
            next_action=_next_action(task_id, project_id=project_id),
        )
        _write_dry_run(repo_root, run_path, result)
        return result

    workspace = _task_workspace_path(repo_root, task_id)
    workspace_display = relative_path(repo_root, workspace) if workspace else ""
    if workspace is None or not workspace.exists() or not workspace.is_dir():
        result = PatchDryRun(
            **base,
            workspace_path=workspace_display,
            dry_run_status="workspace_missing",
            risk=_higher_risk("medium", review_risk),
            files_checked=[],
            files_missing=[],
            files_would_create=[],
            files_would_modify=[],
            files_would_delete=[],
            hunks_checked=0,
            hunks_matched=0,
            hunks_failed=0,
            hunk_results=[],
            findings=["Cannot dry-run without isolated task workspace."],
            warnings=[],
            next_action=_next_action(task_id, project_id=project_id),
        )
        _write_dry_run(repo_root, run_path, result)
        return result

    patch_text = patch_path.read_text(encoding="utf-8")
    try:
        patch_files = parse_unified_diff(patch_text)
    except ValueError as exc:
        result = PatchDryRun(
            **base,
            workspace_path=workspace_display,
            dry_run_status="invalid_patch",
            risk=_higher_risk("medium", review_risk),
            files_checked=[],
            files_missing=[],
            files_would_create=[],
            files_would_modify=[],
            files_would_delete=[],
            hunks_checked=0,
            hunks_matched=0,
            hunks_failed=0,
            hunk_results=[],
            findings=["Patch candidate cannot be parsed."],
            warnings=[str(exc)],
            next_action=_next_action(task_id, project_id=project_id),
        )
        _write_dry_run(repo_root, run_path, result)
        return result

    if not patch_files:
        result = PatchDryRun(
            **base,
            workspace_path=workspace_display,
            dry_run_status="invalid_patch",
            risk=_higher_risk("medium", review_risk),
            files_checked=[],
            files_missing=[],
            files_would_create=[],
            files_would_modify=[],
            files_would_delete=[],
            hunks_checked=0,
            hunks_matched=0,
            hunks_failed=0,
            hunk_results=[],
            findings=["Patch candidate cannot be parsed."],
            warnings=[],
            next_action=_next_action(task_id, project_id=project_id),
        )
        _write_dry_run(repo_root, run_path, result)
        return result

    result = _inspect_patch_files(
        repo_root,
        workspace,
        task_id,
        selected_run_id,
        patch_path,
        review_path,
        patch_files,
        review,
        project_id=project_id,
    )
    _write_dry_run(repo_root, run_path, result)
    return result


def parse_unified_diff(patch_text: str) -> list[PatchFile]:
    try:
        return parse_patch_proposal(patch_text, reject_unsupported_apply_metadata=True).files
    except PatchProposalParseError as exc:
        raise ValueError(str(exc)) from exc


def render_patch_dry_run_markdown(result: PatchDryRun) -> str:
    lines = [
        "# Patch Dry-run Preview",
        "",
        f"Task: {result.task_id}",
        f"Run: {result.run_id}",
        f"Status: {result.dry_run_status}",
        f"Risk: {result.risk}",
        "",
        "## Workspace",
        "",
        result.workspace_path or "not_available",
        "",
        "## Files Checked",
        "",
        _render_bullets(result.files_checked),
        "",
        "## Hunk Results",
        "",
    ]
    if result.hunk_results:
        for hunk in result.hunk_results:
            lines.append(f"* {hunk.get('file')} hunk {hunk.get('hunk_index')}: {hunk.get('status')}")
    else:
        lines.append("* None")
    lines.extend(
        [
            "",
            "## Findings",
            "",
            _render_bullets(result.findings),
            "",
            "## Warnings",
            "",
            _render_bullets(result.warnings),
            "",
            "## Next Recommended Command",
            "",
            result.next_action.get("command") or "None",
            "",
        ]
    )
    return "\n".join(lines)


def _inspect_patch_files(
    root: Path,
    workspace: Path,
    task_id: str,
    run_id: str,
    patch_path: Path,
    review_path: Path,
    patch_files: list[PatchFile],
    review: dict[str, Any],
    *,
    project_id: str | None = None,
) -> PatchDryRun:
    files_checked: list[str] = []
    files_missing: list[str] = []
    files_would_create: list[str] = []
    files_would_modify: list[str] = []
    files_would_delete: list[str] = []
    hunk_results: list[dict[str, Any]] = []
    warnings: list[str] = []
    findings: list[str] = []
    dangerous_paths: list[str] = []
    hunks_checked = 0
    hunks_matched = 0
    hunks_failed = 0

    for file_patch in patch_files:
        target = file_patch.target_path or ""
        if is_dangerous_path(target):
            dangerous_paths.append(target)
            continue

        try:
            target_file = resolve_workspace_patch_target(workspace, target)
        except ValueError:
            dangerous_paths.append(target)
            continue

        files_checked.append(target)
        if file_patch.is_new_file:
            files_would_create.append(target)
            if target_file.exists():
                warnings.append(f"New-file patch targets existing file: {target}")
            for index, hunk in enumerate(file_patch.hunks, start=1):
                hunks_checked += 1
                hunks_matched += 1
                hunk_results.append(_hunk_result(target, index, hunk, "matched", "New-file hunk can be previewed without creating the file."))
            continue

        if file_patch.is_deletion:
            files_would_delete.append(target)
        else:
            files_would_modify.append(target)

        if not target_file.exists():
            if target not in files_missing:
                files_missing.append(target)
            for index, hunk in enumerate(file_patch.hunks, start=1):
                hunks_checked += 1
                hunks_failed += 1
                hunk_results.append(_hunk_result(target, index, hunk, "failed", "Target file is missing from the workspace."))
            continue

        file_lines = target_file.read_text(encoding="utf-8").splitlines()
        for index, hunk in enumerate(file_patch.hunks, start=1):
            hunks_checked += 1
            if _hunk_matches(file_lines, hunk):
                hunks_matched += 1
                hunk_results.append(_hunk_result(target, index, hunk, "matched", "Original hunk context matched workspace file."))
            else:
                hunks_failed += 1
                hunk_results.append(_hunk_result(target, index, hunk, "failed", "Original hunk context did not match workspace file."))

    review_risk = _normalize_risk(str(review.get("risk") or "unknown"))
    if dangerous_paths:
        status = "invalid_patch"
        risk = "critical"
        findings.append("Patch candidate targets dangerous or generated paths.")
        warnings.extend(f"Dangerous target path rejected: {path}" for path in dangerous_paths)
    elif files_missing:
        status = "missing_target_file"
        risk = _higher_risk("medium", review_risk)
        findings.append("One or more target files are missing from the workspace.")
    elif hunks_failed:
        status = "hunk_mismatch"
        risk = _higher_risk("medium", review_risk)
        findings.append("One or more original hunk contexts did not match the workspace.")
    elif files_would_create and not files_would_modify and not files_would_delete:
        status = "would_create_files"
        risk = review_risk if _risk_rank(review_risk) > _risk_rank("low") else "low"
        findings.append("Patch would create files without modifying the workspace.")
    else:
        generated_warnings = _review_warnings(review)
        warnings.extend(generated_warnings)
        if generated_warnings or review.get("high_risk_files"):
            status = "would_modify_with_warnings"
            risk = _higher_risk("medium", review_risk)
        else:
            status = "would_apply_cleanly"
            risk = review_risk
        findings.append("All checked hunks matched workspace content.")

    return PatchDryRun(
        schema_version=1,
        task_id=task_id,
        run_id=run_id,
        proposal_patch_path=relative_path(root, patch_path),
        patch_review_path=relative_path(root, review_path),
        workspace_path=relative_path(root, workspace),
        dry_run_status=status,
        risk=risk,
        files_checked=sorted(dict.fromkeys(files_checked)),
        files_missing=sorted(dict.fromkeys(files_missing)),
        files_would_create=sorted(dict.fromkeys(files_would_create)),
        files_would_modify=sorted(dict.fromkeys(files_would_modify)),
        files_would_delete=sorted(dict.fromkeys(files_would_delete)),
        hunks_checked=hunks_checked,
        hunks_matched=hunks_matched,
        hunks_failed=hunks_failed,
        hunk_results=hunk_results,
        findings=findings,
        warnings=warnings,
        next_action=_next_action(task_id, project_id=project_id),
    )


def _resolve_run(root: Path, task_id: str, run_id: str | None) -> tuple[str, Path]:
    task_path = task_dir(root, task_id)
    if not task_path.exists():
        raise KeyError(f"Task '{task_id}' not found.")
    runs_dir = task_path / "local-model-runs"
    if not runs_dir.exists() or not runs_dir.is_dir():
        raise FileNotFoundError(f"No local model runs found for task '{task_id}'.")
    if run_id is not None:
        run_path = runs_dir / run_id
        if not run_path.exists() or not run_path.is_dir():
            raise FileNotFoundError(f"Local model run '{run_id}' not found for task '{task_id}'.")
        if not (run_path / "patch-review.json").exists():
            raise FileNotFoundError(f"patch-review.json not found for local model run '{run_id}'.")
        return run_id, run_path

    candidates = sorted(p for p in runs_dir.iterdir() if p.is_dir() and (p / "patch-review.json").exists())
    if not candidates:
        raise FileNotFoundError(f"No local model runs with patch-review.json found for task '{task_id}'.")
    selected = candidates[-1]
    return selected.name, selected


def _task_workspace_path(root: Path, task_id: str) -> Path | None:
    task_yaml = task_dir(root, task_id) / "task.yaml"
    if not task_yaml.exists():
        return None
    data = yaml.safe_load(task_yaml.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        return None
    workspace_value = data.get("workspace_path") or data.get("workspace")
    if not isinstance(workspace_value, str) or not workspace_value:
        return None
    return absolute_path(root, workspace_value)


def _task_workspace_display(root: Path, task_id: str) -> str:
    workspace = _task_workspace_path(root, task_id)
    return relative_path(root, workspace) if workspace else ""


def _hunk_matches(file_lines: list[str], hunk: PatchHunk) -> bool:
    hint = hunk.old_start - 1
    if hint < 0 or (hint > len(file_lines) and not hunk.original_lines):
        return False
    original = hunk.original_lines
    if not original:
        return True
    if _lines_match_at(file_lines, original, hint):
        return True
    max_start = len(file_lines) - len(original)
    if max_start < 0:
        return False
    return sum(1 for start in range(max_start + 1) if _lines_match_at(file_lines, original, start)) == 1


def _lines_match_at(file_lines: list[str], original: list[str], start: int) -> bool:
    return file_lines[start : start + len(original)] == original


def _hunk_result(file_path: str, index: int, hunk: PatchHunk, status: str, reason: str) -> dict[str, Any]:
    return {
        "file": file_path,
        "hunk_index": index,
        "old_start": hunk.old_start,
        "new_start": hunk.new_start,
        "status": status,
        "reason": reason,
    }


def _base_result(root: Path, task_id: str, run_id: str, patch_path: Path, review_path: Path) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "task_id": task_id,
        "run_id": run_id,
        "proposal_patch_path": relative_path(root, patch_path),
        "patch_review_path": relative_path(root, review_path),
    }


def _write_dry_run(root: Path, run_path: Path, result: PatchDryRun) -> None:
    (run_path / "patch-dry-run.json").write_text(
        json.dumps(result.to_json_dict(), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (run_path / "patch-dry-run.md").write_text(render_patch_dry_run_markdown(result), encoding="utf-8")


def _review_warnings(review: dict[str, Any]) -> list[str]:
    warnings = list(review.get("warnings") or [])
    slice_alignment = review.get("slice_alignment") or {}
    if isinstance(slice_alignment, dict) and slice_alignment.get("undeclared_touched_files"):
        warnings.append("Patch touches files not declared in task slice metadata.")
    if review.get("high_risk_files"):
        warnings.append("Patch review marked one or more files as high risk.")
    return [str(warning) for warning in warnings]


def _normalize_risk(risk: str) -> str:
    return risk if risk in RISK_ORDER else "unknown"


def _risk_rank(risk: str) -> int:
    return RISK_ORDER.get(risk, RISK_ORDER["unknown"])


def _higher_risk(left: str, right: str) -> str:
    return left if _risk_rank(left) >= _risk_rank(right) else right


def _next_action(task_id: str, *, project_id: str | None = None) -> dict[str, str]:
    return {
        "label": "Review dry-run evidence manually",
        "command": _scope_project_command(f"devflow task show {task_id}", project_id),
    }


def _scope_project_command(command: str, project_id: str | None) -> str:
    if not project_id or "--project" in command:
        return command
    parts = command.split()
    if len(parts) < 4 or parts[0] != "devflow" or parts[1] != "task":
        return command
    return " ".join([*parts[:4], "--project", project_id, *parts[4:]])


def _render_bullets(values: list[str]) -> str:
    if not values:
        return "* None"
    return "\n".join(f"* {value}" for value in values)
