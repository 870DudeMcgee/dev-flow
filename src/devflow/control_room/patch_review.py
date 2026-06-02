from __future__ import annotations

from dataclasses import asdict, dataclass, field
import fnmatch
import json
from pathlib import Path
import re
from typing import Any

import yaml

from devflow.control_room.paths import relative_path, task_dir


REVIEW_STATUSES = {
    "no_patch_candidate",
    "invalid_patch",
    "dangerous_patch",
    "review_required",
    "low_risk_candidate",
    "unknown",
}

RISKS = {"low", "medium", "high", "critical", "unknown"}

DANGEROUS_EXACT_NAMES = {
    "packet.json",
    "packet.md",
    "prompt.md",
    "response.md",
    "request.json",
    "response.json",
    "run.json",
    "proposal.md",
    "proposal.json",
    "proposal.patch",
    "patch-review.md",
    "patch-review.json",
}

DANGEROUS_PATTERNS = [
    ".git/**",
    ".devflow/workspaces/**",
    ".devflow/tasks/**",
    ".devflow/agent-runs/**",
    ".devflow/artifacts/**",
    "local-model-runs/**",
    "logs/**",
    "__pycache__/**",
    ".pytest_cache/**",
    ".venv/**",
    ".venv-*/**",
    "node_modules/**",
    "dist/**",
    "build/**",
]

HIGH_RISK_PATTERNS = [
    "src/devflow/control_room/patch_applier.py",
    "src/devflow/control_room/verification.py",
    "src/devflow/control_room/persistence.py",
    "src/devflow/control_room/service.py",
    "src/devflow/control_room/worker_adapter.py",
    "src/devflow/control_room/agent_registry.py",
    "src/devflow/control_room/git_worktree.py",
    "src/devflow/cli.py",
    "pyproject.toml",
    ".github/workflows/**",
    ".devflow/project/**",
    "AGENTS.md",
    "README.md",
    "PRODUCT_NORTH_STAR.md",
    "CHANGELOG.md",
    "LICENSE",
]


@dataclass
class PatchReview:
    schema_version: int
    task_id: str
    run_id: str
    proposal_classification: str
    has_patch_candidate: bool
    patch_path: str | None
    review_status: str
    risk: str
    files_touched: list[str]
    hunk_count: int
    dangerous_paths: list[str] = field(default_factory=list)
    generated_or_forbidden_paths: list[str] = field(default_factory=list)
    high_risk_files: list[str] = field(default_factory=list)
    slice_alignment: dict[str, Any] = field(default_factory=dict)
    findings: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    next_action: dict[str, str | None] = field(default_factory=dict)

    def to_json_dict(self) -> dict[str, Any]:
        return asdict(self)


def review_patch_candidate(root: Path, task_id: str, *, run_id: str | None = None) -> PatchReview:
    repo_root = root.resolve()
    selected_run_id, run_path = _resolve_run(repo_root, task_id, run_id)
    proposal_path = run_path / "proposal.json"
    try:
        proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"proposal.json is malformed for local model run '{selected_run_id}'.") from exc
    if not isinstance(proposal, dict):
        raise ValueError(f"proposal.json is malformed for local model run '{selected_run_id}'.")

    classification = str(proposal.get("classification") or "unknown")
    has_patch_candidate = bool(proposal.get("has_patch_candidate"))
    patch_file = run_path / "proposal.patch"
    patch_rel = relative_path(repo_root, patch_file) if patch_file.exists() else None
    optional_warnings = _read_optional_run_evidence(run_path)

    if not has_patch_candidate or not patch_file.exists():
        review = PatchReview(
            schema_version=1,
            task_id=task_id,
            run_id=selected_run_id,
            proposal_classification=classification,
            has_patch_candidate=False,
            patch_path=None,
            review_status="no_patch_candidate",
            risk="low",
            files_touched=[],
            hunk_count=0,
            slice_alignment=_slice_alignment(repo_root, task_id, []),
            findings=["No patch candidate was available for review."],
            warnings=optional_warnings,
            next_action={
                "label": "Review proposal manually",
                "command": f"devflow task show {task_id}",
            },
        )
        _write_review(repo_root, run_path, review)
        return review

    patch_text = patch_file.read_text(encoding="utf-8")
    files_touched = extract_touched_files(patch_text)
    hunk_count = len(re.findall(r"^@@", patch_text, flags=re.MULTILINE))
    has_header = "diff --git " in patch_text or ("--- " in patch_text and "+++ " in patch_text)
    structurally_valid = bool(files_touched and hunk_count > 0 and has_header)
    slice_alignment = _slice_alignment(repo_root, task_id, files_touched)
    warnings = optional_warnings + list(slice_alignment.pop("_warnings", []))

    if not structurally_valid:
        review = PatchReview(
            schema_version=1,
            task_id=task_id,
            run_id=selected_run_id,
            proposal_classification=classification,
            has_patch_candidate=True,
            patch_path=patch_rel,
            review_status="invalid_patch",
            risk="medium",
            files_touched=files_touched,
            hunk_count=hunk_count,
            slice_alignment=slice_alignment,
            findings=["Patch candidate exists but does not look like unified diff."],
            warnings=warnings,
            next_action={
                "label": "Review proposal manually",
                "command": f"devflow task show {task_id}",
            },
        )
        _write_review(repo_root, run_path, review)
        return review

    dangerous_paths = [path for path in files_touched if is_dangerous_path(path)]
    high_risk_files = [path for path in files_touched if is_high_risk_file(path)]
    findings: list[str] = ["Patch structure looks valid."]
    generated = list(dangerous_paths)

    if dangerous_paths:
        findings.append("Dangerous or generated paths detected.")
        review_status = "dangerous_patch"
        risk = "critical"
        next_label = "Review proposal manually"
    elif high_risk_files:
        findings.append("Patch touches high-risk control-room or release contract files.")
        review_status = "review_required"
        risk = "high"
        next_label = "Review patch candidate manually"
    elif _only_docs_or_tests(files_touched):
        findings.append("No dangerous paths detected.")
        findings.append("Patch touches documentation/tests only.")
        review_status = "low_risk_candidate"
        risk = "low"
        next_label = "Review patch candidate manually"
    else:
        findings.append("No dangerous paths detected.")
        review_status = "review_required"
        risk = "medium"
        next_label = "Review patch candidate manually"

    review = PatchReview(
        schema_version=1,
        task_id=task_id,
        run_id=selected_run_id,
        proposal_classification=classification,
        has_patch_candidate=True,
        patch_path=patch_rel,
        review_status=review_status,
        risk=risk,
        files_touched=files_touched,
        hunk_count=hunk_count,
        dangerous_paths=dangerous_paths,
        generated_or_forbidden_paths=generated,
        high_risk_files=high_risk_files,
        slice_alignment=slice_alignment,
        findings=findings,
        warnings=warnings,
        next_action={
            "label": next_label,
            "command": f"devflow task show {task_id}",
        },
    )
    _write_review(repo_root, run_path, review)
    return review


def normalize_agent_patch_candidate(root: Path, task_id: str, agent_id: str) -> str:
    repo_root = root.resolve()
    task_path = task_dir(repo_root, task_id)
    if not task_path.exists():
        raise KeyError(f"Task '{task_id}' not found.")
    if Path(agent_id).is_absolute() or ".." in Path(agent_id).parts:
        raise ValueError(f"Invalid agent id: {agent_id}")

    agent_dir = task_path / "agents" / agent_id
    agent_patch = agent_dir / "proposal.patch"
    if not agent_patch.exists():
        raise FileNotFoundError(f"proposal.patch not found for agent '{agent_id}'.")

    run_id = f"agent-{_slug(agent_id)}"
    run_path = task_path / "local-model-runs" / run_id
    run_path.mkdir(parents=True, exist_ok=True)
    patch_path = run_path / "proposal.patch"
    patch_text = agent_patch.read_text(encoding="utf-8")
    if not patch_path.exists() or patch_path.read_text(encoding="utf-8") != patch_text:
        patch_path.write_text(patch_text, encoding="utf-8")

    proposal = {
        "schema_version": 1,
        "task_id": task_id,
        "run_id": run_id,
        "response_path": _agent_response_path(repo_root, agent_dir),
        "classification": "patch_candidate",
        "confidence": "high",
        "has_patch_candidate": True,
        "patch_candidate_path": relative_path(repo_root, patch_path),
        "proposal_path": relative_path(repo_root, run_path / "proposal.md"),
        "proposal_json_path": relative_path(repo_root, run_path / "proposal.json"),
        "validation_path": None,
        "warnings": [f"Normalized from agent proposal evidence: {agent_id}"],
        "next_action": {
            "label": "Review patch candidate",
            "command": f"devflow task review-patch {task_id} --run-id {run_id}",
        },
    }
    (run_path / "proposal.json").write_text(json.dumps(proposal, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (run_path / "proposal.md").write_text(
        "# Normalized Agent Patch Candidate\n\n"
        f"Task: {task_id}\n"
        f"Agent: {agent_id}\n"
        f"Patch: {relative_path(repo_root, patch_path)}\n",
        encoding="utf-8",
    )
    return run_id


def latest_patch_review(root: Path, task_id: str) -> dict[str, Any] | None:
    runs_dir = task_dir(root, task_id) / "local-model-runs"
    if not runs_dir.exists() or not runs_dir.is_dir():
        return None
    candidates = sorted(p for p in runs_dir.iterdir() if p.is_dir() and (p / "patch-review.json").exists())
    if not candidates:
        return None
    latest = candidates[-1] / "patch-review.json"
    try:
        data = json.loads(latest.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    data["_review_path"] = relative_path(root, candidates[-1] / "patch-review.md")
    return data


def extract_touched_files(patch_text: str) -> list[str]:
    files: list[str] = []
    for line in patch_text.splitlines():
        if line.startswith("diff --git "):
            parts = line.split()
            if len(parts) >= 4:
                files.append(_strip_patch_prefix(parts[3]))
        elif line.startswith("--- ") or line.startswith("+++ "):
            value = line[4:].split("\t", 1)[0].strip()
            if value != "/dev/null":
                files.append(_strip_patch_prefix(value))
    return sorted(dict.fromkeys(path for path in files if path))


def is_dangerous_path(path: str) -> bool:
    normalized = _normalize_patch_path(path)
    if Path(normalized).is_absolute():
        return True
    if ".." in Path(normalized).parts:
        return True
    if Path(normalized).name in DANGEROUS_EXACT_NAMES:
        return True
    return any(fnmatch.fnmatch(normalized, pattern) for pattern in DANGEROUS_PATTERNS)


def is_high_risk_file(path: str) -> bool:
    normalized = _normalize_patch_path(path)
    return any(fnmatch.fnmatch(normalized, pattern) for pattern in HIGH_RISK_PATTERNS)


def render_patch_review_markdown(review: PatchReview) -> str:
    lines = [
        "# Patch Candidate Review",
        "",
        f"Task: {review.task_id}",
        f"Run: {review.run_id}",
        f"Status: {review.review_status}",
        f"Risk: {review.risk}",
        "",
        "## Files Touched",
        "",
        _render_bullets(review.files_touched),
        "",
        "## Findings",
        "",
        _render_bullets(review.findings),
        "",
        "## Warnings",
        "",
        _render_bullets(review.warnings),
        "",
        "## Slice Alignment",
        "",
        f"Status: {review.slice_alignment.get('status', 'not_available')}",
        f"Declared files: {len(review.slice_alignment.get('declared_files') or [])}",
        f"Undeclared touched files: {len(review.slice_alignment.get('undeclared_touched_files') or [])}",
        "",
        "## Next Recommended Command",
        "",
        review.next_action.get("command") or "None",
        "",
    ]
    return "\n".join(lines)


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
        if not (run_path / "proposal.json").exists():
            raise FileNotFoundError(f"proposal.json not found for local model run '{run_id}'.")
        return run_id, run_path

    candidates = sorted(p for p in runs_dir.iterdir() if p.is_dir() and (p / "proposal.json").exists())
    if not candidates:
        raise FileNotFoundError(f"No local model runs with proposal.json found for task '{task_id}'.")
    selected = candidates[-1]
    return selected.name, selected


def _write_review(root: Path, run_path: Path, review: PatchReview) -> None:
    data = review.to_json_dict()
    (run_path / "patch-review.json").write_text(
        json.dumps(data, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (run_path / "patch-review.md").write_text(render_patch_review_markdown(review), encoding="utf-8")


def _read_optional_run_evidence(run_path: Path) -> list[str]:
    warnings: list[str] = []
    proposal_md = run_path / "proposal.md"
    if proposal_md.exists():
        proposal_md.read_text(encoding="utf-8")
    validation_json = run_path / "validation.json"
    if validation_json.exists():
        try:
            data = json.loads(validation_json.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                warnings.append("validation.json is present but not a JSON object.")
        except json.JSONDecodeError:
            warnings.append("validation.json is present but malformed.")
    return warnings


def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-")
    return slug or "agent"


def _agent_response_path(root: Path, agent_dir: Path) -> str | None:
    for name in ("raw_output.md", "result.md"):
        candidate = agent_dir / name
        if candidate.exists():
            return relative_path(root, candidate)
    return None


def _slice_alignment(root: Path, task_id: str, files_touched: list[str]) -> dict[str, Any]:
    task_path = task_dir(root, task_id)
    goal_link_path = task_path / "goal-link.yaml"
    slice_md_path = task_path / "slice.md"
    declared_files: set[str] = set()

    if not goal_link_path.exists() and not slice_md_path.exists():
        return {"status": "not_available"}

    if goal_link_path.exists():
        try:
            link_data = yaml.safe_load(goal_link_path.read_text(encoding="utf-8")) or {}
        except Exception:
            link_data = {}
        declared_files.update(_as_string_list(link_data.get("required_artifacts")))
        declared_files.update(_as_string_list(link_data.get("shared_files")))
        goal_id = link_data.get("goal_id")
        slice_id = link_data.get("slice_id")
        goal_path = root / str(link_data.get("goal_path") or f".devflow/goals/{goal_id}")
        slices_path = goal_path / "task-slices.yaml"
        if goal_id and slice_id and slices_path.exists():
            try:
                slices_data = yaml.safe_load(slices_path.read_text(encoding="utf-8")) or {}
                for item in slices_data.get("task_slices") or []:
                    if isinstance(item, dict) and item.get("task_id") == slice_id:
                        declared_files.update(_as_string_list(item.get("required_artifacts")))
                        declared_files.update(_as_string_list(item.get("shared_files")))
                        break
            except Exception:
                pass

    declared = sorted(declared_files)
    undeclared = [path for path in files_touched if path not in declared_files]
    alignment = {
        "status": "checked",
        "declared_files": declared,
        "undeclared_touched_files": undeclared,
    }
    if undeclared:
        alignment["_warnings"] = ["Patch touches files not declared in task slice metadata."]
    return alignment


def _as_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def _only_docs_or_tests(files_touched: list[str]) -> bool:
    return bool(files_touched) and all(
        path.startswith("docs/")
        or path.startswith("tests/")
        or path.endswith(".md")
        or path.endswith(".rst")
        or path.endswith(".txt")
        for path in files_touched
    )


def _strip_patch_prefix(path: str) -> str:
    path = path.strip().strip('"')
    if path.startswith("a/") or path.startswith("b/"):
        return path[2:]
    return path


def _normalize_patch_path(path: str) -> str:
    return path.strip().strip('"').replace("\\", "/")


def _render_bullets(items: list[str]) -> str:
    if not items:
        return "* None"
    return "\n".join(f"* {item}" for item in items)
