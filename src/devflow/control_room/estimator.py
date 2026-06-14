from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from devflow.control_room.persistence import get_task
from devflow.control_room.paths import task_dir


_FILE_ESTIMATE_SAMPLE_BYTES = 64 * 1024


def _relative(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _line_and_token_estimate(paths: list[Path]) -> tuple[int, int]:
    line_count = 0
    token_count = 0
    for path in paths:
        try:
            size = path.stat().st_size
            with path.open("rb") as handle:
                sample = handle.read(_FILE_ESTIMATE_SAMPLE_BYTES)
        except Exception:
            continue
        content = sample.decode("utf-8", errors="ignore")
        sample_lines = len(content.splitlines())
        sample_size = len(sample)
        if sample_size and size > sample_size:
            estimated_lines = (sample_lines * size + sample_size - 1) // sample_size
        else:
            estimated_lines = sample_lines
        line_count += estimated_lines
        token_count += max(1, size // 4)
    return line_count, token_count


def _yaml_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if value is None:
        return "null"
    return json.dumps(str(value))


def _tier_for_summarizer(context_requirement: str) -> str:
    if context_requirement in {"high", "critical"}:
        return "strong_local"
    return "local"


def _tier_for_scout(task_type: str, repo_scope: str, architectural_risk: str) -> str:
    if task_type in {"architecture_change", "model_routing_change", "repo_refactor"}:
        return "strong_local"
    if repo_scope in {"medium", "large"} or architectural_risk in {"high", "critical"}:
        return "strong_local"
    return "local"


def estimate_task_fit(root: Path, task_id: str) -> dict[str, Any]:
    """Perform a deterministic static scan of the task and codebase to estimate task fit and context size."""
    from devflow.control_room.scout import RepoScout

    try:
        task = get_task(root, task_id)
    except KeyError:
        # Fallback if task is not in standard database
        raise ValueError(f"Task not found: {task_id}")

    scout = RepoScout(root)

    # Gather task inputs
    title = task.title
    description = scout.get_task_description(task_id)
    combined_text = f"{title}\n{description}".lower()

    # 1. Estimate changed files using git
    changed_files = [root / f for f in scout.get_changed_files()]
    # Filter existing files
    changed_files = [p for p in changed_files if p.exists() and p.is_file()]

    # 2. Extract referenced files from title and description
    referenced_files = scout.get_referenced_files(title, description)

    # Combine changed files and referenced files for "relevant files"
    relevant_files = list(set(changed_files + referenced_files))

    # Add related tests for any source files
    test_files_list = scout.get_test_files(relevant_files)

    # Let's make sure test files are included in relevant files count
    all_relevant_files = list(set(relevant_files + test_files_list))

    # Count docs needed
    docs_list = scout.get_strategic_files()
    
    # Also find markdown files in the relevant files list
    for f in all_relevant_files:
        if f.suffix == ".md":
            if f not in docs_list:
                docs_list.append(f)

    evidence_inputs = ["task.yaml"]
    missing_inputs = []

    code_map_path = root / "CODE_MAP.md"
    if code_map_path.exists() and code_map_path.is_file():
        evidence_inputs.append("CODE_MAP.md")
    else:
        missing_inputs.append("CODE_MAP.md")

    if referenced_files:
        evidence_inputs.extend(sorted(_relative(root, path) for path in referenced_files))
    else:
        missing_inputs.append("explicit referenced files")

    if test_files_list:
        evidence_inputs.extend(sorted(_relative(root, path) for path in test_files_list))
    else:
        missing_inputs.append("matched test files")

    evidence_inputs.extend(sorted(_relative(root, path) for path in docs_list))
    evidence_inputs = list(dict.fromkeys(evidence_inputs))

    # Estimate line count and tokens
    relevant_lines, relevant_tokens = _line_and_token_estimate(all_relevant_files)

    # Read events.jsonl for task history tokens
    task_history_tokens = 0
    events_path = task_dir(root, task_id) / "events.jsonl"
    if events_path.exists():
        try:
            task_history_tokens = events_path.stat().st_size // 4
        except Exception:
            pass

    # Prompt and system overhead estimate
    overhead_tokens = 4000
    total_context_estimate = relevant_tokens + task_history_tokens + overhead_tokens

    # Formulate Repo Scan
    repo_scan = {
        "changed_files_count": len(changed_files),
        "relevant_files_count": len(all_relevant_files),
        "relevant_lines_estimate": relevant_lines,
        "relevant_tokens_estimate": relevant_tokens,
        "test_files_needed": len(test_files_list),
        "docs_needed": len(docs_list),
        "evidence_inputs": evidence_inputs,
        "missing_inputs": missing_inputs,
        "task_history_tokens": task_history_tokens,
        "total_context_estimate": total_context_estimate,
    }

    # 3. Task Type Vocabulary Classification Heuristics
    task_type = "feature_implementation"  # default
    if any(k in combined_text for k in ["model routing", "agent selection", "router", "routing"]):
        task_type = "model_routing_change"
    elif any(k in combined_text for k in ["architecture", "adr", "design document", "contract"]):
        task_type = "architecture_change"
    elif any(k in combined_text for k in ["refactor", "cleanup", "reorganize", "consolidate", "restructure"]):
        task_type = "repo_refactor"
    elif any(k in combined_text for k in ["verify", "run tests only", "verification run"]):
        task_type = "verification_only"
    elif any(k in combined_text for k in ["test", "tests", "pytest", "unittest"]) and any(k in combined_text for k in ["fix", "repair", "broken", "failing", "fail"]):
        task_type = "test_repair"
    elif any(k in combined_text for k in ["fix", "bug", "issue", "crash", "error", "fail", "regression", "exception"]):
        task_type = "bug_fix"
    elif any(k in combined_text for k in ["docs", "documentation", "readme", "comment"]):
        # Verify if mostly md/rst files
        if all(f.suffix in (".md", ".rst", ".txt") for f in all_relevant_files) if all_relevant_files else True:
            task_type = "documentation_cleanup"
    elif any(k in combined_text for k in ["typo", "format", "whitespace", "style", "rename", "dead code"]):
        task_type = "trivial_edit"
    elif any(k in combined_text for k in ["research", "explain", "investigate", "where is", "how does"]):
        task_type = "research_or_current_info"
    elif any(k in combined_text for k in ["add", "implement", "support", "create"]):
        if len(all_relevant_files) <= 3:
            task_type = "small_feature"
        else:
            task_type = "feature_implementation"

    # Repo Scope
    if len(all_relevant_files) <= 3:
        repo_scope = "small"
    elif len(all_relevant_files) <= 10:
        repo_scope = "medium"
    else:
        repo_scope = "large"

    # Context Requirement
    if total_context_estimate < 8000:
        context_requirement = "low"
    elif total_context_estimate < 24000:
        context_requirement = "medium"
    elif total_context_estimate < 64000:
        context_requirement = "high"
    else:
        context_requirement = "critical"

    # Reasoning Requirement
    if task_type in ("trivial_edit", "documentation_cleanup", "verification_only"):
        reasoning_requirement = "low"
    elif task_type in ("small_feature", "bug_fix", "test_repair", "research_or_current_info"):
        reasoning_requirement = "medium"
    elif task_type in ("feature_implementation", "repo_refactor"):
        reasoning_requirement = "high"
    else:
        reasoning_requirement = "critical"

    # Code Edit Risk
    if task_type in ("documentation_cleanup", "verification_only", "research_or_current_info", "trivial_edit"):
        code_edit_risk = "low"
    elif task_type in ("small_feature", "bug_fix", "test_repair"):
        code_edit_risk = "medium"
    elif task_type in ("feature_implementation", "repo_refactor"):
        code_edit_risk = "high"
    else:
        code_edit_risk = "critical"

    # Architectural Risk
    if task_type in ("documentation_cleanup", "trivial_edit", "bug_fix", "test_repair", "verification_only", "research_or_current_info"):
        architectural_risk = "low"
    elif task_type in ("small_feature", "feature_implementation"):
        architectural_risk = "medium"
    elif task_type in ("repo_refactor",):
        architectural_risk = "high"
    else:
        architectural_risk = "critical"

    # Verification Complexity
    if not task.verification_command:
        verification_complexity = "low"
    elif "pytest" in task.verification_command or "unittest" in task.verification_command:
        verification_complexity = "medium"
    else:
        verification_complexity = "high"

    # Flags
    requires_big_picture = task_type in ("architecture_change", "model_routing_change", "repo_refactor")
    requires_current_repo_state = task_type != "research_or_current_info"
    requires_historical_project_context = task_type in ("architecture_change", "model_routing_change", "repo_refactor")

    # Context Layer
    if total_context_estimate < 2000 and code_edit_risk == "low":
        context_layer = "L0"
    elif total_context_estimate < 8000 and code_edit_risk in ("low", "medium"):
        context_layer = "L1"
    elif total_context_estimate < 16000 and code_edit_risk != "critical":
        context_layer = "L2"
    elif total_context_estimate < 32000 and code_edit_risk != "critical":
        context_layer = "L3"
    elif reasoning_requirement == "critical" or total_context_estimate >= 32000:
        context_layer = "L4"
    else:
        context_layer = "L5"

    # Recommended Tiers
    if task_type in ("trivial_edit", "documentation_cleanup"):
        recommended_planner_tier = "local"
    elif task_type in ("small_feature", "bug_fix", "test_repair"):
        recommended_planner_tier = "strong_local"
    else:
        recommended_planner_tier = "frontier"

    if code_edit_risk == "low":
        recommended_worker_tier = "local"
    elif code_edit_risk == "medium" and context_layer in ("L0", "L1", "L2"):
        recommended_worker_tier = "strong_local"
    else:
        recommended_worker_tier = "frontier"

    if code_edit_risk == "low":
        recommended_reviewer_tier = "local"
    elif code_edit_risk == "medium":
        recommended_reviewer_tier = "strong_local"
    else:
        recommended_reviewer_tier = "frontier"

    recommended_verifier_tier = "deterministic"
    recommended_summarizer_tier = _tier_for_summarizer(context_requirement)
    recommended_scout_tier = _tier_for_scout(task_type, repo_scope, architectural_risk)

    # Confidence calculation
    confidence = 0.85
    if len(referenced_files) > 0:
        confidence += 0.05
    if not task.workspace_dirty:
        confidence += 0.05
    if len(title) < 15:
        confidence -= 0.15
    confidence = max(0.1, min(1.0, round(confidence, 2)))

    task_fit = {
        "task_type": task_type,
        "repo_scope": repo_scope,
        "context_requirement": context_requirement,
        "reasoning_requirement": reasoning_requirement,
        "code_edit_risk": code_edit_risk,
        "architectural_risk": architectural_risk,
        "verification_complexity": verification_complexity,
        "requires_big_picture": requires_big_picture,
        "requires_current_repo_state": requires_current_repo_state,
        "requires_historical_project_context": requires_historical_project_context,
        "context_layer": context_layer,
        "recommended_planner_tier": recommended_planner_tier,
        "recommended_worker_tier": recommended_worker_tier,
        "recommended_reviewer_tier": recommended_reviewer_tier,
        "recommended_verifier_tier": recommended_verifier_tier,
        "recommended_summarizer_tier": recommended_summarizer_tier,
        "recommended_scout_tier": recommended_scout_tier,
        "confidence": confidence,
    }

    return {
        "task_fit": task_fit,
        "repo_scan": repo_scan,
    }


def save_task_fit(root: Path, task_id: str, fit_data: dict[str, Any]) -> None:
    """Save the task fit estimation into task-fit.yaml inside the task directory."""
    task_directory = task_dir(root, task_id)
    task_directory.mkdir(parents=True, exist_ok=True)
    yaml_file = task_directory / "task-fit.yaml"

    lines = []
    
    def append_yaml_value(key: str, val: Any) -> None:
        if isinstance(val, list):
            if not val:
                lines.append(f"  {key}: []")
                return
            lines.append(f"  {key}:")
            for item in val:
                lines.append(f"    - {_yaml_scalar(item)}")
            return
        lines.append(f"  {key}: {_yaml_scalar(val)}")

    # task_fit block
    lines.append("task_fit:")
    task_fit = fit_data.get("task_fit", {})
    for key in sorted(task_fit.keys()):
        append_yaml_value(key, task_fit[key])

    lines.append("")

    # repo_scan block
    lines.append("repo_scan:")
    repo_scan = fit_data.get("repo_scan", {})
    for key in sorted(repo_scan.keys()):
        append_yaml_value(key, repo_scan[key])

    yaml_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
