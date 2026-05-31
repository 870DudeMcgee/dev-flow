from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

from devflow.control_room.persistence import get_task
from devflow.control_room.paths import task_dir


def estimate_task_fit(root: Path, task_id: str) -> dict[str, Any]:
    """Perform a deterministic static scan of the task and codebase to estimate task fit and context size."""
    try:
        task = get_task(root, task_id)
    except KeyError:
        # Fallback if task is not in standard database
        raise ValueError(f"Task not found: {task_id}")

    # Gather task inputs
    title = task.title
    # We don't have a direct description field on TaskRecord, but the task directory might contain a description or task.yaml metadata.
    # Let's see if there is a task.yaml or details inside it. We can read task.yaml to extract more description if present.
    description = ""
    task_yaml_path = task_dir(root, task_id) / "task.yaml"
    if task_yaml_path.exists():
        try:
            content = task_yaml_path.read_text(encoding="utf-8")
            # If description is written as description: "..." or multiple lines, let's try to extract it
            desc_match = re.search(r"^description:\s*(.+)$", content, re.MULTILINE)
            if desc_match:
                description = desc_match.group(1).strip().strip('"\'')
        except Exception:
            pass

    combined_text = f"{title}\n{description}".lower()

    # 1. Estimate changed files using git
    changed_files: list[Path] = []
    try:
        status_proc = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if status_proc.returncode == 0:
            for line in status_proc.stdout.splitlines():
                stripped = line.strip()
                if not stripped:
                    continue
                # XY PATH format
                path_part = stripped[3:].strip() if len(stripped) > 3 else stripped
                if path_part.startswith(".devflow") or path_part.startswith('".devflow'):
                    continue
                file_path = root / path_part
                if file_path.exists() and file_path.is_file():
                    changed_files.append(file_path)
    except Exception:
        pass

    # 2. Extract referenced files from title and description
    # Pattern to find potential filenames: e.g. path/to/file.py or foo.py
    file_pattern = re.compile(r"\b[a-zA-Z0-9_\-./]+\.[a-zA-Z0-9]+\b")
    referenced_matches = file_pattern.findall(title + " " + description)

    referenced_files: list[Path] = []
    for match in referenced_matches:
        if match.startswith(".devflow"):
            continue
        # Search for file inside the repo
        candidate = root / match
        if candidate.exists() and candidate.is_file():
            if candidate not in referenced_files:
                referenced_files.append(candidate)
        else:
            # Maybe it is a relative path or file name somewhere in root, let's look for it
            try:
                for p in root.glob(f"**/{match}"):
                    if p.is_file() and not any(part.startswith('.') for part in p.relative_to(root).parts):
                        if p not in referenced_files:
                            referenced_files.append(p)
                            break
            except Exception:
                pass

    # Combine changed files and referenced files for "relevant files"
    relevant_files = list(set(changed_files + referenced_files))

    # Add related tests for any source files
    test_files_list: list[Path] = []
    for f in relevant_files:
        # Check if the file is a test file itself
        if "test" in f.name.lower() or f.parent.name == "tests":
            if f not in test_files_list:
                test_files_list.append(f)
            continue
        
        # If it is a python file, find potential matching test files
        if f.suffix == ".py":
            # E.g. tests/test_foo.py or test_foo.py
            test_candidate1 = root / "tests" / f"test_{f.name}"
            test_candidate2 = f.parent / f"test_{f.name}"
            if test_candidate1.exists() and test_candidate1.is_file():
                if test_candidate1 not in test_files_list:
                    test_files_list.append(test_candidate1)
            if test_candidate2.exists() and test_candidate2.is_file():
                if test_candidate2 not in test_files_list:
                    test_files_list.append(test_candidate2)

    # Let's make sure test files are included in relevant files count
    all_relevant_files = list(set(relevant_files + test_files_list))

    # Count docs needed
    docs_list: list[Path] = []
    # Always include product/MVP docs if they exist
    for doc_name in ["PRODUCT_NORTH_STAR.md", "docs/control-room-mvp.md", "docs/architecture/agent-registry-and-adapter-runtime.md"]:
        doc_path = root / doc_name
        if doc_path.exists() and doc_path.is_file():
            docs_list.append(doc_path)
    
    # Also find markdown files in the relevant files list
    for f in all_relevant_files:
        if f.suffix == ".md":
            if f not in docs_list:
                docs_list.append(f)

    # Estimate line count and tokens
    relevant_lines = 0
    relevant_tokens = 0
    for f in all_relevant_files:
        try:
            content = f.read_text(encoding="utf-8", errors="ignore")
            relevant_lines += len(content.splitlines())
            relevant_tokens += len(content) // 4
        except Exception:
            pass

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
    
    # task_fit block
    lines.append("task_fit:")
    task_fit = fit_data.get("task_fit", {})
    for key in sorted(task_fit.keys()):
        val = task_fit[key]
        if isinstance(val, bool):
            val_str = "true" if val else "false"
        elif isinstance(val, (int, float)):
            val_str = str(val)
        else:
            val_str = str(val)
        lines.append(f"  {key}: {val_str}")

    lines.append("")

    # repo_scan block
    lines.append("repo_scan:")
    repo_scan = fit_data.get("repo_scan", {})
    for key in sorted(repo_scan.keys()):
        val = repo_scan[key]
        lines.append(f"  {key}: {val}")

    yaml_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
