from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from devflow.legacy.control_room.models import TaskRecord
from devflow.legacy.control_room.paths import relative_path


# Local Qwen-class workers are run with large contexts on the operator's machine.
# Keep safety bounds, but do not silently neuter task packets to ~8K tokens.
MAX_INCLUDED_SOURCE_CHARS = 64_000
MAX_OUT_OF_SCOPE_CHARS = 32_000
MAX_TOTAL_INCLUDED_SOURCE_CHARS = 200_000
_EXCLUDED_GENERATED_NAME_FRAGMENTS = {
    "raw_output.md",
    "run.json",
    "proposal.patch",
    "proposal.md",
    "proposal.json",
    "patch-review.md",
    "patch-review.json",
    "patch-dry-run.md",
    "patch-dry-run.json",
    "prompt.md",
    "response.md",
    "request.json",
    "response.json",
}
_GOAL_LINK_OPERATOR_WARNINGS = [
    "Do not load the entire repo by default.",
    "Do not load archived context unless explicitly requested.",
    "Promotion remains human-controlled.",
]


def load_slice_from_goal(goal_dir: Path, slice_id: str, warnings: list[str]) -> dict[str, Any] | None:
    slices_file = goal_dir / "task-slices.yaml"
    if not slices_file.exists():
        warnings.append(f"warning: task-slices.yaml is missing in {goal_dir.name}")
        return None
    try:
        data = yaml.safe_load(slices_file.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("task_slices"), list):
            for s in data["task_slices"]:
                if isinstance(s, dict) and s.get("task_id") == slice_id:
                    return s
            warnings.append(f"warning: slice_id '{slice_id}' not found in task-slices.yaml")
        else:
            warnings.append(f"warning: task-slices.yaml in {goal_dir.name} is malformed")
    except Exception as exc:
        warnings.append(f"warning: failed to parse task-slices.yaml: {exc}")
    return None


def load_context_pointers(goal_dir: Path, warnings: list[str]) -> dict[str, Any]:
    cp_file = goal_dir / "context-pointers.yaml"
    default_budget = {
        "estimated_tokens": None,
        "risk": "medium",
        "strategy": "focused_task_packet",
        "required_context": [],
        "optional_context": [],
        "forbidden_context": [
            "archived_docs",
            "previous_failed_attempts_unless_explicitly_relevant",
            "unrelated_brainstorming"
        ],
        "stale_or_archived_context": [],
        "warnings": ["do_not_load_entire_repo"]
    }
    if not cp_file.exists():
        warnings.append(f"warning: context-pointers.yaml is missing in {goal_dir.name}")
        return default_budget

    try:
        data = yaml.safe_load(cp_file.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            warnings.append(f"warning: context-pointers.yaml in {goal_dir.name} is malformed")
            return default_budget

        budget = data.get("context_budget") or {}
        if not isinstance(budget, dict):
            budget = {}
        estimated_tokens = budget.get("estimated_tokens")
        risk = budget.get("risk") or budget.get("context_risk") or budget.get("context risk") or "medium"
        strategy = budget.get("strategy") or "focused_task_packet"

        return {
            "estimated_tokens": estimated_tokens,
            "risk": risk,
            "strategy": strategy,
            "required_context": _normalize_context_pointer_list(data, "required_context", default_budget["required_context"], warnings),
            "optional_context": _normalize_context_pointer_list(data, "optional_context", default_budget["optional_context"], warnings),
            "forbidden_context": _normalize_context_pointer_list(data, "forbidden_context", default_budget["forbidden_context"], warnings),
            "stale_or_archived_context": _normalize_context_pointer_list(data, "stale_or_archived_context", default_budget["stale_or_archived_context"], warnings),
            "warnings": _normalize_context_pointer_list(data, "warnings", default_budget["warnings"], warnings),
        }
    except Exception as exc:
        warnings.append(f"warning: failed to parse context-pointers.yaml: {exc}")
        return default_budget


def _normalize_context_pointer_list(
    data: dict[str, Any],
    field: str,
    default: list[str],
    warnings: list[str],
) -> list[str]:
    if field not in data:
        return list(default)
    value = data[field]
    if isinstance(value, list):
        return value
    warnings.append(f"warning: context-pointers.yaml {field} must be a list")
    return list(default)


def is_path_excluded(path_str: str) -> bool:
    normalized = path_str.replace("\\", "/").lower()
    return (
        ".devflow/workspaces/" in normalized
        or "local-model-runs/" in normalized
        or "/logs/" in normalized
        or normalized.startswith("logs/")
        or "/packet.json" in normalized
        or "/packet.md" in normalized
        or normalized.endswith(("packet.json", "packet.md"))
        or any(name in normalized for name in _EXCLUDED_GENERATED_NAME_FRAGMENTS)
    )


def build_bounded_sources(
    root: Path,
    goal_path: Path,
    task_path: Path,
    context_budget_data: dict[str, Any],
    warnings: list[str],
    operator_warnings: list[str]
) -> dict[str, Any]:
    included_summaries = []
    source_pointers = []
    excluded_sources = list(context_budget_data.get("forbidden_context") or [])

    total_loaded_chars = 0

    for path, max_chars, missing_warning in (
        (task_path / "slice.md", MAX_INCLUDED_SOURCE_CHARS, None),
        (goal_path / "prd.md", MAX_INCLUDED_SOURCE_CHARS, f"warning: prd.md is missing in {goal_path.name}"),
        (goal_path / "out-of-scope.md", MAX_OUT_OF_SCOPE_CHARS, None),
    ):
        total_loaded_chars = _include_text_summary(
            root,
            path,
            max_chars,
            total_loaded_chars,
            included_summaries,
            source_pointers,
            warnings,
            missing_warning=missing_warning,
        )

    # Decisions.yaml and open-questions.yaml as parsed YAML summaries
    decisions_yaml = goal_path / "decisions.yaml"
    decisions_rel = relative_path(root, decisions_yaml)
    if decisions_yaml.exists() and not is_path_excluded(decisions_rel):
        try:
            dec_data = yaml.safe_load(decisions_yaml.read_text(encoding="utf-8")) or {}
            dec_str = yaml.safe_dump(dec_data)
            if total_loaded_chars + len(dec_str) <= MAX_TOTAL_INCLUDED_SOURCE_CHARS:
                total_loaded_chars += len(dec_str)
                included_summaries.append({
                    "source": decisions_rel,
                    "kind": "yaml_summary",
                    "content": dec_data
                })
                source_pointers.append(decisions_rel)
            else:
                warnings.append("warning: decisions.yaml skipped due to total character cap")
        except Exception as exc:
            warnings.append(f"warning: failed to read decisions.yaml: {exc}")

    oq_yaml = goal_path / "open-questions.yaml"
    oq_rel = relative_path(root, oq_yaml)
    if oq_yaml.exists() and not is_path_excluded(oq_rel):
        try:
            oq_data = yaml.safe_load(oq_yaml.read_text(encoding="utf-8")) or {}
            oq_str = yaml.safe_dump(oq_data)
            if total_loaded_chars + len(oq_str) <= MAX_TOTAL_INCLUDED_SOURCE_CHARS:
                total_loaded_chars += len(oq_str)
                included_summaries.append({
                    "source": oq_rel,
                    "kind": "yaml_summary",
                    "content": oq_data
                })
                source_pointers.append(oq_rel)
            else:
                warnings.append("warning: open-questions.yaml skipped due to total character cap")
        except Exception as exc:
            warnings.append(f"warning: failed to read open-questions.yaml: {exc}")

    cp_yaml = goal_path / "context-pointers.yaml"
    if cp_yaml.exists() and not is_path_excluded(relative_path(root, cp_yaml)):
        source_pointers.append(relative_path(root, cp_yaml))

    stale_terms = ["archive", "archived", "stale", "deprecated", "old"]

    all_context_pointers = []
    if "required_context" in context_budget_data:
        all_context_pointers.extend(context_budget_data["required_context"])
    if "optional_context" in context_budget_data:
        all_context_pointers.extend(context_budget_data["optional_context"])

    for p in all_context_pointers:
        if not isinstance(p, str):
            continue
        if is_path_excluded(p):
            continue
        is_forbidden = False
        for f in excluded_sources:
            if f in p:
                is_forbidden = True
                break
        if is_forbidden:
            continue

        is_stale = False
        for term in stale_terms:
            if term in p.lower():
                is_stale = True
                break

        if is_stale:
            if p not in source_pointers:
                source_pointers.append(p)
            operator_warnings.append(f"Archived context pointer excluded from loading: {p}")
        else:
            if p not in source_pointers:
                source_pointers.append(p)

    return {
        "included_summaries": included_summaries,
        "source_pointers": source_pointers[:50],  # MAX_CONTEXT_POINTERS
        "excluded_sources": excluded_sources
    }


def _include_text_summary(
    root: Path,
    path: Path,
    max_chars: int,
    total_loaded_chars: int,
    included_summaries: list[dict[str, Any]],
    source_pointers: list[str],
    warnings: list[str],
    *,
    missing_warning: str | None = None,
) -> int:
    rel_path = relative_path(root, path)
    if not path.exists():
        if missing_warning:
            warnings.append(missing_warning)
        return total_loaded_chars
    if is_path_excluded(rel_path):
        return total_loaded_chars
    try:
        content = path.read_text(encoding="utf-8")
    except Exception as exc:
        warnings.append(f"warning: failed to read {path.name}: {exc}")
        return total_loaded_chars

    original_chars = len(content)
    truncated = False
    included_chars = original_chars
    if original_chars > max_chars:
        content = content[:max_chars]
        truncated = True
        included_chars = max_chars
    if total_loaded_chars + len(content) > MAX_TOTAL_INCLUDED_SOURCE_CHARS:
        remaining = max(0, MAX_TOTAL_INCLUDED_SOURCE_CHARS - total_loaded_chars)
        content = content[:remaining]
        truncated = True
        included_chars = len(content)

    total_loaded_chars += len(content)
    entry: dict[str, Any] = {
        "source": rel_path,
        "kind": "summary",
        "content": content,
    }
    if truncated:
        entry["truncated"] = True
        entry["original_chars"] = original_chars
        entry["included_chars"] = included_chars
    included_summaries.append(entry)
    source_pointers.append(rel_path)
    return total_loaded_chars


def _goal_link_packet_fields(repo_root: Path, task_path: Path, task: TaskRecord, task_id: str) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "goal_context": None,
        "task_slice": None,
        "context_budget": None,
        "verification_policy": None,
        "bounded_sources": None,
        "operator_warnings": [],
        "next_action": None,
    }
    goal_link_yaml = task_path / "goal-link.yaml"
    if not goal_link_yaml.exists():
        return fields

    parsed_op_warnings: list[str] = []
    try:
        link_data = yaml.safe_load(goal_link_yaml.read_text(encoding="utf-8")) or {}
        goal_id = link_data.get("goal_id")
        slice_id = link_data.get("slice_id")
        goal_path_str = link_data.get("goal_path") or f".devflow/goals/{goal_id}"
        goal_path = repo_root / goal_path_str

        fields["goal_context"] = {
            "linked": True,
            "goal_id": goal_id,
            "slice_id": slice_id,
            "goal_path": goal_path_str,
            "slice_source_path": link_data.get("slice_source_path") or f".devflow/goals/{goal_id}/task-slices.yaml",
            "execution_mode": link_data.get("execution_mode") or "HITL",
            "human_checkpoint_required": link_data.get("human_checkpoint_required") if link_data.get("human_checkpoint_required") is not None else True,
            "checkpoint_reason": link_data.get("checkpoint_reason") or "",
            "promotion_allowed": link_data.get("promotion_allowed") or False,
            "risk": link_data.get("risk") or "medium"
        }

        slice_data = load_slice_from_goal(goal_path, slice_id, parsed_op_warnings) or {}
        fields["task_slice"] = {
            "title": slice_data.get("title") or task.title or "",
            "summary": slice_data.get("summary") or "",
            "acceptance_criteria": slice_data.get("acceptance_criteria") or [],
            "required_artifacts": slice_data.get("required_artifacts") or [],
            "shared_files": slice_data.get("shared_files") or [],
            "blocked_by": slice_data.get("blocked_by") or [],
            "blocks": slice_data.get("blocks") or [],
            "parallel_safe": slice_data.get("parallel_safe") or False,
            "workspace_isolation_required": slice_data.get("workspace_isolation_required") or False
        }

        context_budget = load_context_pointers(goal_path, parsed_op_warnings)
        fields["context_budget"] = context_budget

        vp = slice_data.get("verification_policy") or {}
        if isinstance(vp, str):
            vp_dict = {"policy_type": vp}
        elif isinstance(vp, dict):
            vp_dict = vp
        else:
            vp_dict = {}
        fields["verification_policy"] = {
            "test_first_required": vp_dict.get("test_first_required", True),
            "red_green_required": vp_dict.get("red_green_required", True),
            "required_evidence": vp_dict.get("required_evidence") or []
        }

        fields["bounded_sources"] = build_bounded_sources(
            repo_root,
            goal_path,
            task_path,
            context_budget,
            parsed_op_warnings,
            parsed_op_warnings
        )

        fields["operator_warnings"] = _GOAL_LINK_OPERATOR_WARNINGS + parsed_op_warnings + (context_budget.get("warnings") or [])
        fields["next_action"] = {
            "label": "Review packet, then run task explicitly",
            "command": f"devflow task run {task_id} --worker shell -- <command>"
        }
    except Exception as exc:
        parsed_op_warnings.append(f"warning: failed to process goal link context: {exc}")
        fields["operator_warnings"] = _GOAL_LINK_OPERATOR_WARNINGS + parsed_op_warnings
    return fields
