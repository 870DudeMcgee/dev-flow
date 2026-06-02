from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import re

from devflow.control_room.paths import relative_path, task_dir


CLASSIFICATIONS = {
    "advisory_only",
    "blocker_question",
    "implementation_plan",
    "patch_candidate",
    "unknown",
}


@dataclass
class PatchValidation:
    valid: bool
    reason: str
    files_touched: list[str] = field(default_factory=list)
    hunk_count: int | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass
class ProposalClassification:
    task_id: str
    run_id: str
    response_path: str
    classification: str
    confidence: str
    has_patch_candidate: bool
    patch_candidate_path: str | None
    proposal_path: str
    proposal_json_path: str
    validation_path: str | None
    warnings: list[str]
    next_action_label: str
    next_action_command: str | None


def normalize_proposal(
    root: Path,
    task_id: str,
    *,
    run_id: str | None = None,
    response_path: Path | None = None,
) -> ProposalClassification:
    task_path = task_dir(root, task_id)
    if not task_path.exists():
        raise KeyError(f"Task '{task_id}' not found.")

    selected_run_id, run_path, selected_response = _resolve_run(root, task_path, run_id, response_path)
    response_text = selected_response.read_text(encoding="utf-8")
    classification, confidence = classify_response(response_text)
    patch_text = extract_patch_candidate(response_text) if classification == "patch_candidate" else None

    warnings: list[str] = []
    patch_path = run_path / "proposal.patch"
    validation_path = run_path / "validation.json"
    validation: PatchValidation | None = None

    if patch_text is not None:
        patch_path.write_text(patch_text, encoding="utf-8")
        validation = validate_patch_candidate(patch_text)
        warnings.extend(validation.warnings)
        validation_path.write_text(
            json.dumps(
                {
                    "valid": validation.valid,
                    "reason": validation.reason,
                    "files_touched": validation.files_touched,
                    "hunk_count": validation.hunk_count,
                    "warnings": validation.warnings,
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
    else:
        if patch_path.exists():
            patch_path.unlink()
        if validation_path.exists():
            validation_path.unlink()

    proposal_path = run_path / "proposal.md"
    proposal_json_path = run_path / "proposal.json"
    next_command = f"devflow task show {task_id}"

    result = ProposalClassification(
        task_id=task_id,
        run_id=selected_run_id,
        response_path=relative_path(root, selected_response),
        classification=classification,
        confidence=confidence,
        has_patch_candidate=patch_text is not None,
        patch_candidate_path=relative_path(root, patch_path) if patch_text is not None else None,
        proposal_path=relative_path(root, proposal_path),
        proposal_json_path=relative_path(root, proposal_json_path),
        validation_path=relative_path(root, validation_path) if validation is not None else None,
        warnings=warnings,
        next_action_label="Review normalized proposal",
        next_action_command=next_command,
    )

    proposal_path.write_text(
        render_proposal_markdown(result, response_text, validation=validation),
        encoding="utf-8",
    )
    proposal_json_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "task_id": task_id,
                "run_id": selected_run_id,
                "response_path": result.response_path,
                "classification": classification,
                "confidence": confidence,
                "has_patch_candidate": result.has_patch_candidate,
                "patch_candidate_path": result.patch_candidate_path,
                "proposal_path": result.proposal_path,
                "proposal_json_path": result.proposal_json_path,
                "validation_path": result.validation_path,
                "warnings": warnings,
                "next_action": {
                    "label": result.next_action_label,
                    "command": result.next_action_command,
                },
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return result


def classify_response(text: str) -> tuple[str, str]:
    stripped = text.strip()
    if len(stripped) < 12:
        return "unknown", "low"
    if extract_patch_candidate(stripped) is not None:
        return "patch_candidate", "high"

    lowered = stripped.lower()
    blocker_markers = [
        "questions",
        "blocked",
        "need clarification",
        "i need",
        "cannot proceed",
    ]
    if any(marker in lowered for marker in blocker_markers):
        return "blocker_question", "medium"

    plan_markers = [
        "proposed approach",
        "implementation plan",
        "files likely affected",
        "acceptance criteria mapping",
        "verification plan",
    ]
    if any(marker in lowered for marker in plan_markers):
        return "implementation_plan", "medium"

    return "advisory_only", "medium"


def extract_patch_candidate(text: str) -> str | None:
    fenced = re.search(r"```diff\s*\n(.*?)\n```", text, flags=re.IGNORECASE | re.DOTALL)
    if fenced:
        return fenced.group(1).rstrip() + "\n"

    lines = text.splitlines()
    start_index: int | None = None
    for index, line in enumerate(lines):
        if line.startswith("diff --git ") or line.startswith("--- "):
            start_index = index
            break
    if start_index is None:
        return None

    candidate = "\n".join(lines[start_index:]).strip()
    if "@@" not in candidate:
        return None
    return candidate + "\n"


def validate_patch_candidate(patch_text: str) -> PatchValidation:
    warnings: list[str] = []
    has_header = "diff --git " in patch_text or ("--- " in patch_text and "+++ " in patch_text)
    hunk_count = len(re.findall(r"^@@", patch_text, flags=re.MULTILINE))
    files = _extract_touched_files(patch_text)

    if not has_header:
        return PatchValidation(False, "Patch candidate is missing diff headers.", files, hunk_count, warnings)
    if hunk_count < 1:
        return PatchValidation(False, "Patch candidate is missing hunks.", files, hunk_count, warnings)
    if not files:
        warnings.append("No touched files could be extracted from the patch headers.")

    for file_path in files:
        reason = _unsafe_patch_path_reason(file_path)
        if reason:
            warnings.append(reason)
            return PatchValidation(False, reason, files, hunk_count, warnings)

    return PatchValidation(True, "Patch candidate has unified diff structure.", files, hunk_count, warnings)


def render_proposal_markdown(
    result: ProposalClassification,
    response_text: str,
    *,
    validation: PatchValidation | None,
) -> str:
    validation_label = "not_performed"
    if validation is not None:
        validation_label = "valid" if validation.valid else "invalid"

    files_mentioned = validation.files_touched if validation is not None else _extract_file_mentions(response_text)
    blockers = _extract_section(response_text, ["questions", "blockers", "blocked", "need clarification"])
    acceptance = _extract_section(response_text, ["acceptance criteria mapping", "acceptance criteria"])
    verification = _extract_section(response_text, ["verification plan", "verification"])

    lines = [
        "# Normalized Proposal",
        "",
        f"Task: {result.task_id}",
        f"Run: {result.run_id}",
        "",
        f"Classification: {result.classification}",
        f"Patch candidate: {'yes' if result.has_patch_candidate else 'no'}",
        f"Validation: {validation_label}",
        "",
        "## Summary",
        "",
        _summarize_response(response_text),
        "",
        "## Questions / Blockers",
        "",
        blockers or "None detected.",
        "",
        "## Files Mentioned",
        "",
        _render_bullets(files_mentioned),
        "",
        "## Acceptance Criteria Mapping",
        "",
        acceptance or "None detected.",
        "",
        "## Verification Plan",
        "",
        verification or "None detected.",
        "",
        "## Patch Candidate",
        "",
    ]
    if result.patch_candidate_path:
        lines.extend(["Saved to:", result.patch_candidate_path])
    else:
        lines.append("None detected.")

    lines.extend(
        [
            "",
            "## Next Recommended Command",
            "",
            result.next_action_command or "None",
            "",
        ]
    )
    return "\n".join(lines)


def latest_normalized_proposal(root: Path, task_id: str) -> dict[str, object] | None:
    runs_dir = task_dir(root, task_id) / "local-model-runs"
    if not runs_dir.exists():
        return None
    candidates = sorted(p for p in runs_dir.iterdir() if p.is_dir() and (p / "proposal.json").exists())
    if not candidates:
        return None
    latest = candidates[-1]
    try:
        data = json.loads((latest / "proposal.json").read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return data


def _resolve_run(
    root: Path,
    task_path: Path,
    run_id: str | None,
    response_path: Path | None,
) -> tuple[str, Path, Path]:
    if response_path is not None:
        selected_response = response_path if response_path.is_absolute() else root / response_path
        if not selected_response.exists():
            raise FileNotFoundError(f"response.md not found: {relative_path(root, selected_response)}")
        run_path = selected_response.parent
        return run_id or run_path.name, run_path, selected_response

    runs_dir = task_path / "local-model-runs"
    if not runs_dir.exists() or not runs_dir.is_dir():
        raise FileNotFoundError(f"No local model runs found for task '{task_path.name}'.")

    if run_id is not None:
        run_path = runs_dir / run_id
        if not run_path.exists() or not run_path.is_dir():
            raise FileNotFoundError(f"Local model run '{run_id}' not found for task '{task_path.name}'.")
    else:
        runs = sorted(p for p in runs_dir.iterdir() if p.is_dir())
        if not runs:
            raise FileNotFoundError(f"No local model runs found for task '{task_path.name}'.")
        run_path = runs[-1]
        run_id = run_path.name

    selected_response = run_path / "response.md"
    if not selected_response.exists():
        raise FileNotFoundError(f"response.md not found for local model run '{run_path.name}'.")
    return run_id, run_path, selected_response


def _extract_touched_files(patch_text: str) -> list[str]:
    files: list[str] = []
    for line in patch_text.splitlines():
        if line.startswith("diff --git "):
            parts = line.split()
            if len(parts) >= 4:
                files.append(_strip_patch_prefix(parts[3]))
        elif line.startswith("+++ "):
            value = line[4:].split("\t", 1)[0].strip()
            if value != "/dev/null":
                files.append(_strip_patch_prefix(value))
    return sorted(dict.fromkeys(file for file in files if file))


def _strip_patch_prefix(path: str) -> str:
    path = path.strip().strip('"')
    if path.startswith("a/") or path.startswith("b/"):
        return path[2:]
    return path


def _unsafe_patch_path_reason(path: str) -> str | None:
    normalized = path.replace("\\", "/")
    path_obj = Path(normalized)
    if path_obj.is_absolute():
        return f"Rejected unsafe absolute patch path: {path}"
    if ".." in path_obj.parts:
        return f"Rejected unsafe parent traversal patch path: {path}"
    if normalized == ".git" or normalized.startswith(".git/"):
        return f"Rejected unsafe .git patch path: {path}"
    if normalized.startswith(".devflow/workspaces/"):
        return f"Rejected unsafe generated workspace patch path: {path}"
    generated_names = {
        "packet.json",
        "packet.md",
        "prompt.md",
        "response.md",
        "request.json",
        "response.json",
        "run.json",
    }
    parts = set(path_obj.parts)
    if "local-model-runs" in parts or "logs" in parts:
        return f"Rejected generated artifact patch path: {path}"
    if path_obj.name in generated_names:
        return f"Rejected generated artifact patch path: {path}"
    return None


def _extract_file_mentions(text: str) -> list[str]:
    matches = re.findall(r"(?:src|tests|docs)/[A-Za-z0-9_./-]+", text)
    return sorted(dict.fromkeys(matches))[:20]


def _extract_section(text: str, names: list[str]) -> str:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        normalized = line.strip().strip("#:").lower()
        if any(name in normalized for name in names):
            section: list[str] = []
            for following in lines[index + 1 :]:
                if following.startswith("#") and section:
                    break
                section.append(following)
            return "\n".join(section).strip()[:1200]
    return ""


def _summarize_response(text: str) -> str:
    cleaned = text.strip()
    if not cleaned:
        return "No usable response text."
    without_fences = re.sub(r"```.*?```", "", cleaned, flags=re.DOTALL)
    summary = without_fences.strip() or cleaned
    return summary[:1200]


def _render_bullets(items: list[str]) -> str:
    if not items:
        return "None detected."
    return "\n".join(f"- {item}" for item in items)
