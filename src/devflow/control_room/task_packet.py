from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any
import yaml

from pydantic import BaseModel, Field

from devflow.control_room.models import TaskRecord
from devflow.control_room.paths import relative_path
from devflow.control_room.status_projection import TaskStatusProjection, build_task_status_projection
from devflow.control_room.agent_registry import AgentDefinition
from devflow.control_room.agent_runtime import agent_runtime_contract
from devflow.control_room.devmode_bridge import devmode_discipline_lines

_relative = relative_path


DOCS_POLISH_ANTI_PLACEHOLDER_INSTRUCTION = (
    "For docs/polish tasks, do not invent new docs files, quickstarts, README sections, commands, "
    "install steps, or usage examples unless the task explicitly asks for them or the packet contains "
    "evidence that those files/commands already exist. If a task explicitly requires a new file, "
    "creating it is allowed. If referencing commands, only reference commands present in the packet, "
    "existing docs, pyproject/scripts, Makefile, or tests. Prefer modifying existing relevant files "
    "over creating placeholder docs."
)

# Local Qwen-class workers are run with large contexts on the operator's machine.
# Keep safety bounds, but do not silently neuter task packets to ~8K tokens.
MAX_INCLUDED_SOURCE_CHARS = 64_000
MAX_OUT_OF_SCOPE_CHARS = 32_000
MAX_TOTAL_INCLUDED_SOURCE_CHARS = 200_000


class TaskPacketLimits(BaseModel):
    recent_events_limit: int = Field(default=20, ge=0)
    worker_log_tail_lines: int = Field(default=20, ge=0)
    verify_log_tail_lines: int = Field(default=20, ge=0)
    log_tail_bytes: int = Field(default=32768, ge=0)
    code_map_excerpt_lines: int = Field(default=80, ge=0)


class TaskPacketLog(BaseModel):
    path: str
    tail: list[str]
    line_count: int
    omitted_lines: int
    omitted_bytes: int
    truncated: bool


class TaskPacket(BaseModel):
    task_id: str
    title: str
    status: str
    agent_id: str | None = None
    role: str | None = None
    execution_mode: str | None = None
    adapter: str
    workspace_path: str
    worker_adapter: str
    allowed_reads: list[str] = Field(default_factory=list)
    allowed_writes: list[str] = Field(default_factory=list)
    forbidden_writes: list[str] = Field(default_factory=list)
    required_outputs: list[str] = Field(default_factory=list)
    completion_rules: list[str] = Field(default_factory=list)
    manual_instructions: str | None = None
    runtime_contract: dict[str, Any] | None = None
    task: dict[str, Any]
    summary: str | None
    recent_events: list[dict[str, Any]]
    verification: dict[str, Any]
    derived_summary: dict[str, Any] | None
    result_summary: str | None
    logs: dict[str, TaskPacketLog]
    constraints: list[str]
    allowed_artifacts: list[str]
    omitted_counts: dict[str, int]
    truncation_notes: list[str]
    schema_version: int = 1
    goal_context: dict[str, Any] | None = None
    task_slice: dict[str, Any] | None = None
    context_budget: dict[str, Any] | None = None
    verification_policy: dict[str, Any] | None = None
    bounded_sources: dict[str, Any] | None = None
    code_map_excerpt: dict[str, Any] | None = None
    operator_warnings: list[str] = Field(default_factory=list)
    next_action: dict[str, Any] | None = None
    devmode_discipline: list[str] = Field(default_factory=list)


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
        estimated_tokens = budget.get("estimated_tokens")
        risk = budget.get("risk") or budget.get("context_risk") or budget.get("context risk") or "medium"
        strategy = budget.get("strategy") or "focused_task_packet"

        return {
            "estimated_tokens": estimated_tokens,
            "risk": risk,
            "strategy": strategy,
            "required_context": data.get("required_context") or [],
            "optional_context": data.get("optional_context") or [],
            "forbidden_context": data.get("forbidden_context") or default_budget["forbidden_context"],
            "stale_or_archived_context": data.get("stale_or_archived_context") or [],
            "warnings": data.get("warnings") or default_budget["warnings"]
        }
    except Exception as exc:
        warnings.append(f"warning: failed to parse context-pointers.yaml: {exc}")
        return default_budget


def is_path_excluded(path_str: str) -> bool:
    normalized = path_str.replace("\\", "/").lower()
    
    # Exclude .devflow/workspaces/**
    if ".devflow/workspaces/" in normalized:
        return True
        
    # Exclude packet.json and packet.md
    if "/packet.json" in normalized or normalized.endswith("packet.json") or "/packet.md" in normalized or normalized.endswith("packet.md"):
        return True
        
    # Exclude local-model-runs/**
    if "local-model-runs/" in normalized:
        return True
        
    # Exclude logs/**
    if "/logs/" in normalized or normalized.startswith("logs/"):
        return True
        
    # Exclude generated proposal/review artifacts.
    generated_names = {
        "raw_output.md",
        "run.json",
        "proposal.patch",
        "proposal.md",
        "proposal.json",
        "patch-review.md",
        "patch-review.json",
        "patch-dry-run.md",
        "patch-dry-run.json",
    }
    if any(name in normalized for name in generated_names):
        return True
        
    # Exclude prompt.md, response.md, request.json, response.json, run.json
    if "prompt.md" in normalized or "response.md" in normalized or "request.json" in normalized or "response.json" in normalized:
        return True
        
    return False


def build_bounded_sources(
    root: Path,
    task_id: str,
    goal_id: str,
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

    # Let's check for slice.md
    slice_md = task_path / "slice.md"
    slice_rel = relative_path(root, slice_md)
    if slice_md.exists() and not is_path_excluded(slice_rel):
        try:
            content = slice_md.read_text(encoding="utf-8")
            if len(content) > MAX_INCLUDED_SOURCE_CHARS:
                content = content[:MAX_INCLUDED_SOURCE_CHARS]
            
            if total_loaded_chars + len(content) > MAX_TOTAL_INCLUDED_SOURCE_CHARS:
                remaining = MAX_TOTAL_INCLUDED_SOURCE_CHARS - total_loaded_chars
                content = content[:remaining]
            
            total_loaded_chars += len(content)
            
            included_summaries.append({
                "source": slice_rel,
                "kind": "summary",
                "content": content
            })
            source_pointers.append(slice_rel)
        except Exception as exc:
            warnings.append(f"warning: failed to read slice.md: {exc}")

    # Let's check for prd.md
    prd_md = goal_path / "prd.md"
    prd_rel = relative_path(root, prd_md)
    if prd_md.exists() and not is_path_excluded(prd_rel):
        try:
            content = prd_md.read_text(encoding="utf-8")
            original_chars = len(content)
            truncated = False
            included_chars = original_chars
            if original_chars > MAX_INCLUDED_SOURCE_CHARS:
                content = content[:MAX_INCLUDED_SOURCE_CHARS]
                truncated = True
                included_chars = MAX_INCLUDED_SOURCE_CHARS
            
            if total_loaded_chars + len(content) > MAX_TOTAL_INCLUDED_SOURCE_CHARS:
                remaining = MAX_TOTAL_INCLUDED_SOURCE_CHARS - total_loaded_chars
                content = content[:remaining]
                truncated = True
                included_chars = len(content)
            
            total_loaded_chars += len(content)
            
            entry = {
                "source": prd_rel,
                "kind": "summary",
                "content": content,
            }
            if truncated:
                entry["truncated"] = True
                entry["original_chars"] = original_chars
                entry["included_chars"] = included_chars
            included_summaries.append(entry)
            source_pointers.append(prd_rel)
        except Exception as exc:
            warnings.append(f"warning: failed to read prd.md: {exc}")
    else:
        warnings.append(f"warning: prd.md is missing in {goal_path.name}")

    # Let's check for out-of-scope.md
    oos_md = goal_path / "out-of-scope.md"
    oos_rel = relative_path(root, oos_md)
    if oos_md.exists() and not is_path_excluded(oos_rel):
        try:
            content = oos_md.read_text(encoding="utf-8")
            original_chars = len(content)
            truncated = False
            included_chars = original_chars
            if original_chars > MAX_OUT_OF_SCOPE_CHARS:
                content = content[:MAX_OUT_OF_SCOPE_CHARS]
                truncated = True
                included_chars = MAX_OUT_OF_SCOPE_CHARS
            
            if total_loaded_chars + len(content) > MAX_TOTAL_INCLUDED_SOURCE_CHARS:
                remaining = MAX_TOTAL_INCLUDED_SOURCE_CHARS - total_loaded_chars
                content = content[:remaining]
                truncated = True
                included_chars = len(content)
            
            total_loaded_chars += len(content)
            
            entry = {
                "source": oos_rel,
                "kind": "summary",
                "content": content,
            }
            if truncated:
                entry["truncated"] = True
                entry["original_chars"] = original_chars
                entry["included_chars"] = included_chars
            included_summaries.append(entry)
            source_pointers.append(oos_rel)
        except Exception as exc:
            warnings.append(f"warning: failed to read out-of-scope.md: {exc}")

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

    # Let's add context-pointers.yaml to source_pointers
    cp_yaml = goal_path / "context-pointers.yaml"
    if cp_yaml.exists() and not is_path_excluded(relative_path(root, cp_yaml)):
        source_pointers.append(relative_path(root, cp_yaml))

    # Let's evaluate required_context and optional_context from context_budget_data
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


def read_goal_link(root: Path, task_id: str) -> dict | None:
    task_path = root / ".devflow" / "tasks" / task_id
    goal_link_yaml = task_path / "goal-link.yaml"
    if not goal_link_yaml.exists():
        return None
    try:
        return yaml.safe_load(goal_link_yaml.read_text(encoding="utf-8")) or {}
    except Exception:
        return None


def render_task_packet_text(packet: TaskPacket) -> str:
    lines = []
    lines.append(f"# Task Packet: {packet.task_id}")
    lines.append(f"- **Title**: {packet.title}")
    lines.append(f"- **Status**: {packet.status}")
    lines.append(f"- **Worker/Adapter**: {packet.worker_adapter}")
    lines.append(f"- **Workspace Path**: {packet.workspace_path}")
    lines.append("")

    if packet.goal_context and packet.goal_context.get("linked"):
        lines.append("## Goal Link Details")
        gc = packet.goal_context
        lines.append(f"- **Goal ID**: {gc.get('goal_id')}")
        lines.append(f"- **Slice ID**: {gc.get('slice_id')}")
        lines.append(f"- **Execution Mode**: {gc.get('execution_mode')}")
        lines.append(f"- **Checkpoint Required**: {gc.get('human_checkpoint_required')}")
        if gc.get("checkpoint_reason"):
            lines.append(f"- **Checkpoint Reason**: {gc.get('checkpoint_reason')}")
        lines.append(f"- **Promotion Allowed**: {gc.get('promotion_allowed')}")
        lines.append(f"- **Risk**: {gc.get('risk')}")
        lines.append("")

    if packet.task_slice:
        lines.append("## Task Slice metadata")
        ts = packet.task_slice
        lines.append(f"- **Summary**: {ts.get('summary')}")
        lines.append("- **Acceptance Criteria**:")
        for ac in ts.get("acceptance_criteria") or ["None"]:
            lines.append(f"  - {ac}")
        lines.append("- **Required Artifacts**:")
        for art in ts.get("required_artifacts") or ["None"]:
            lines.append(f"  - {art}")
        lines.append("")

    if packet.context_budget:
        lines.append("## Bounded Context Budget")
        cb = packet.context_budget
        lines.append(f"- **Strategy**: {cb.get('strategy')}")
        lines.append(f"- **Risk**: {cb.get('risk')}")
        lines.append(f"- **Estimated Tokens**: {cb.get('estimated_tokens')}")
        lines.append("- **Forbidden Context**:")
        for fc in cb.get("forbidden_context") or ["None"]:
            lines.append(f"  - {fc}")
        lines.append("")

    if packet.verification_policy:
        lines.append("## Verification Policy")
        vp = packet.verification_policy
        lines.append(f"- **Test-First Required**: {vp.get('test_first_required')}")
        lines.append(f"- **Red-Green-Refactor Required**: {vp.get('red_green_required')}")
        lines.append("- **Required Evidence**:")
        for ev in vp.get("required_evidence") or ["None"]:
            lines.append(f"  - {ev}")
        lines.append("")

    if packet.bounded_sources:
        lines.append("## Bounded Sources")
        bs = packet.bounded_sources
        lines.append("- **Source Pointers**:")
        for sp in bs.get("source_pointers") or []:
            lines.append(f"  - {sp}")
        lines.append("")
        
        lines.append("- **Included Summaries**:")
        for isum in bs.get("included_summaries") or []:
            lines.append(f"  ### Source: {isum.get('source')} ({isum.get('kind')})")
            if isum.get("truncated"):
                lines.append(f"  *(Truncated to {isum.get('included_chars')} of {isum.get('original_chars')} chars)*")
            content = isum.get("content")
            if isinstance(content, dict):
                content_str = yaml.safe_dump(content, default_flow_style=False)
            else:
                content_str = str(content)
            for line in content_str.splitlines():
                lines.append(f"  > {line}")
            lines.append("")

    if packet.code_map_excerpt:
        cm = packet.code_map_excerpt
        lines.append("## Project Code Map")
        lines.append(f"- **Path**: {cm.get('path')}")
        if cm.get("truncated"):
            lines.append(f"- **Excerpt**: first {cm.get('included_lines')} of {cm.get('line_count')} line(s)")
        else:
            lines.append(f"- **Excerpt**: {cm.get('included_lines')} line(s)")
        lines.append("")
        for line in cm.get("lines") or []:
            lines.append(f"> {line}")
        lines.append("")
            
    if packet.devmode_discipline:
        lines.append("## DevMode Discipline")
        for line in packet.devmode_discipline:
            lines.append(f"- {line}")
        lines.append("")

    if packet.operator_warnings:
        lines.append("## Operator Warnings")
        for ow in packet.operator_warnings:
            lines.append(f"- **[WARNING]**: {ow}")
        lines.append("")

    if packet.next_action:
        lines.append("## Next Action Recommendation")
        na = packet.next_action
        lines.append(f"- **Action**: {na.get('label')}")
        lines.append(f"- **Command**: `{na.get('command')}`")
        lines.append("")

    return "\n".join(lines)


def save_task_packet(root: Path, task_id: str, packet: TaskPacket, text_only: bool = False, text_md: str | None = None) -> list[Path]:
    task_dir = root / ".devflow" / "tasks" / task_id
    written_paths = []
    
    if not text_only:
        packet_json_path = task_dir / "packet.json"
        packet_json_path.write_text(
            json.dumps(packet.model_dump(mode="json"), sort_keys=True, indent=2),
            encoding="utf-8"
        )
        written_paths.append(packet_json_path)
        
    if text_md is not None:
        packet_md_path = task_dir / "packet.md"
        packet_md_path.write_text(text_md, encoding="utf-8")
        written_paths.append(packet_md_path)
        
    return written_paths


def build_task_packet(task_id: str, limits: TaskPacketLimits | None = None, *, root: Path | None = None) -> TaskPacket:
    repo_root = (root or Path.cwd()).resolve()
    packet_limits = limits or TaskPacketLimits()
    projection = build_task_status_projection(repo_root, task_id)
    task = projection.task
    task_path = projection.task_path
    notes: list[str] = []

    summary_data = _read_matching_summary(task_path / "summary.json", task, notes)
    recent_events, omitted_events, malformed_events = _read_recent_events(task_path / "events.jsonl", packet_limits.recent_events_limit, notes)
    verification = _read_verification(task_path / "verification.json", task, projection, notes)
    worker_log = _tail_log(
        repo_root,
        task_path / "logs" / "worker.log",
        "worker.log",
        packet_limits.worker_log_tail_lines,
        packet_limits.log_tail_bytes,
        notes,
    )
    verify_log = _tail_log(
        repo_root,
        task_path / "logs" / "verify.log",
        "verify.log",
        packet_limits.verify_log_tail_lines,
        packet_limits.log_tail_bytes,
        notes,
    )
    code_map_excerpt = _read_code_map_excerpt(repo_root, packet_limits.code_map_excerpt_lines, notes)
    adapter = task.worker_adapter or task.worker

    # Path Virtualization Slices
    raw_workspace_path = task.workspace_path or task.workspace
    virtual_workspace_path = _virtualize_path(raw_workspace_path, repo_root, task.id)

    task_data = task.model_dump(mode="json")
    for k in ["workspace", "workspace_path", "log_path", "result_path", "verification_log_path"]:
        if k in task_data and task_data[k] is not None:
            task_data[k] = _virtualize_path(task_data[k], repo_root, task.id)

    for key in ["workspace", "workspace_path", "log_path", "result_path", "verification_log_path"]:
        if key in verification and verification[key] is not None:
            verification[key] = _virtualize_path(verification[key], repo_root, task.id)

    worker_log = worker_log.model_copy(update={"path": _virtualize_path(worker_log.path, repo_root, task.id)})
    verify_log = verify_log.model_copy(update={"path": _virtualize_path(verify_log.path, repo_root, task.id)})

    allowed_artifacts = [
        _virtualize_path(p, repo_root, task.id)
        for p in _allowed_artifacts(repo_root, task_path)
    ]

    goal_link_yaml = task_path / "goal-link.yaml"
    goal_context = None
    task_slice = None
    context_budget = None
    verification_policy = None
    bounded_sources = None
    parsed_op_warnings = []
    operator_warnings = []
    next_action = None

    if goal_link_yaml.exists():
        try:
            link_data = yaml.safe_load(goal_link_yaml.read_text(encoding="utf-8")) or {}
            goal_id = link_data.get("goal_id")
            slice_id = link_data.get("slice_id")
            goal_path_str = link_data.get("goal_path") or f".devflow/goals/{goal_id}"
            goal_path = repo_root / goal_path_str
            
            goal_context = {
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
            task_slice = {
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
            
            vp = slice_data.get("verification_policy") or {}
            if isinstance(vp, str):
                vp_dict = {"policy_type": vp}
            elif isinstance(vp, dict):
                vp_dict = vp
            else:
                vp_dict = {}
            verification_policy = {
                "test_first_required": vp_dict.get("test_first_required", True),
                "red_green_required": vp_dict.get("red_green_required", True),
                "required_evidence": vp_dict.get("required_evidence") or []
            }
            
            bounded_sources = build_bounded_sources(
                repo_root,
                task_id,
                goal_id,
                goal_path,
                task_path,
                context_budget,
                parsed_op_warnings,
                parsed_op_warnings
            )
            
            operator_warnings = [
                "Do not load the entire repo by default.",
                "Do not load archived context unless explicitly requested.",
                "Promotion remains human-controlled."
            ] + parsed_op_warnings + (context_budget.get("warnings") or [])
            
            next_action = {
                "label": "Review packet, then run task explicitly",
                "command": f"devflow task run {task_id} --worker shell -- <command>"
            }
        except Exception as exc:
            parsed_op_warnings.append(f"warning: failed to process goal link context: {exc}")
            operator_warnings = [
                "Do not load the entire repo by default.",
                "Do not load archived context unless explicitly requested.",
                "Promotion remains human-controlled."
            ] + parsed_op_warnings

    try:
        from devflow.control_room.context_pack import build_context_pack
        pack_data = build_context_pack(repo_root, task_id, "worker", persist_task_fit=False)
        cp = pack_data.get("context_pack", {})
        has_includes = any(m.get("mode") == "full" for m in cp.get("sources_metadata", []))
    except Exception:
        has_includes = False

    if not has_includes:
        operator_warnings.append("No relevant file excerpt is available. Do not invent file content.")

    return _redact_secrets_in_value(
        TaskPacket(
            task_id=task.id,
            title=task.title,
            status=task.status,
            agent_id=None,
            role=None,
            execution_mode=None,
            adapter=adapter,
            workspace_path=virtual_workspace_path,
            worker_adapter=adapter,
            task=task_data,
            summary=_packet_summary(task, summary_data),
            recent_events=recent_events,
            verification=verification,
            derived_summary=summary_data or None,
            result_summary=None,
            logs={"worker": worker_log, "verify": verify_log},
            constraints=_constraints(virtual_workspace_path or ""),
            allowed_artifacts=allowed_artifacts,
            omitted_counts={
                "events": omitted_events,
                "malformed_events": malformed_events,
                "worker_log_lines": worker_log.omitted_lines,
                "worker_log_bytes": worker_log.omitted_bytes,
                "verify_log_lines": verify_log.omitted_lines,
                "verify_log_bytes": verify_log.omitted_bytes,
            },
            truncation_notes=notes,
            schema_version=1,
            goal_context=goal_context,
            task_slice=task_slice,
            context_budget=context_budget,
            verification_policy=verification_policy,
            bounded_sources=bounded_sources,
            code_map_excerpt=code_map_excerpt,
            operator_warnings=operator_warnings,
            next_action=next_action,
            devmode_discipline=devmode_discipline_lines(repo_root),
        )
    )


def build_agent_packet(
    task_id: str,
    agent: AgentDefinition,
    *,
    root: Path | None = None,
) -> TaskPacket:
    packet = build_task_packet(task_id, root=root)
    can_see = agent.can_see or []
    completion_rules = list(agent.completion_rules)
    if _needs_docs_polish_anti_placeholder_instruction(packet, agent):
        completion_rules.append(DOCS_POLISH_ANTI_PLACEHOLDER_INSTRUCTION)
    packet = packet.model_copy(
        update={
            "agent_id": agent.id,
            "role": agent.role,
            "execution_mode": agent.execution_mode,
            "adapter": agent.adapter,
            "worker_adapter": agent.adapter,
            "allowed_reads": agent.allowed_reads,
            "allowed_writes": agent.allowed_writes,
            "forbidden_writes": agent.forbidden_writes,
            "required_outputs": agent.required_outputs,
            "completion_rules": completion_rules,
            "manual_instructions": _manual_instructions(agent, root or Path.cwd()),
            "runtime_contract": agent_runtime_contract(root or Path.cwd(), agent),
        }
    )

    if "task_packet" not in can_see:
        packet = packet.model_copy(update={"task": {}})
    if "assigned_workspace" not in can_see:
        packet = packet.model_copy(update={"workspace_path": "[REDACTED]"})
    if "recent_events" not in can_see:
        packet = packet.model_copy(update={"recent_events": []})
    if "verification_summary" not in can_see and "verification_plan" not in can_see:
        packet = packet.model_copy(update={"verification": {}})

    if agent.adapter == "ollama_chat" and agent.default_mode == "workspace_write":
        packet = packet.model_copy(
            update={
                "required_outputs": [
                    *packet.required_outputs,
                    f"<task>/agents/{agent.id}/raw_output.md",
                    f"<task>/agents/{agent.id}/proposal.patch",
                    f"<task>/agents/{agent.id}/run.json",
                    f"<task>/agents/{agent.id}/result.md",
                ],
                "completion_rules": [
                    *packet.completion_rules,
                    "Produce a unified diff only in the JSON diff field.",
                    "Do not include prose outside the JSON response.",
                    "Do not modify files outside the task boundary.",
                    "Do not claim success unless proposal.patch can be written from a non-empty unified diff.",
                    "Dev-Flow applies patches, runs verification, and controls promotion separately.",
                    "Exclude stale patch dry-run artifacts, unrelated logs, prior raw outputs, archived context, caches, virtualenvs, binaries, .git, and _legacy unless explicitly in scope.",
                ],
                "next_action": {
                    "label": "Run local patch proposal worker",
                    "command": f"devflow task run {task_id} --worker {agent.id}",
                },
            }
        )

    return packet


def _needs_docs_polish_anti_placeholder_instruction(packet: TaskPacket, agent: AgentDefinition) -> bool:
    if agent.id != "qwopus-implementer":
        return False
    if agent.adapter != "ollama_chat" or agent.role != "implementation_worker":
        return False
    return _is_docs_polish_task(packet)


def _is_docs_polish_task(packet: TaskPacket) -> bool:
    parts = [packet.title]
    if packet.task_slice:
        for key in ("title", "summary"):
            value = packet.task_slice.get(key)
            if isinstance(value, str):
                parts.append(value)
    combined = "\n".join(part for part in parts if part).lower()
    return "docs/polish" in combined or (("docs" in combined or "documentation" in combined) and "polish" in combined)


def _manual_instructions(agent: AgentDefinition, root: Path) -> str | None:
    if agent.adapter != "manual" or agent.execution_mode != "human_launched_agent":
        return None
    devmode_lines = devmode_discipline_lines(root)
    return "\n".join(
        [
            f"You are {agent.id}.",
            f"Role: {agent.role}",
            f"Adapter: {agent.adapter}",
            f"Execution mode: {agent.execution_mode}",
            "",
            "Purpose:",
            agent.purpose or "",
            "",
            "DevMode discipline:",
            *devmode_lines[1:],
            "",
            "Workspace boundary:",
            "Edit only files under <workspace>.",
            "Do not edit the main checkout.",
            "Do not edit <task>/task.yaml.",
            "Do not edit <task>/events.jsonl, <task>/verification.json, or promotion artifacts.",
            "",
            "Required terminal outputs:",
            "When complete, write <task>/agents/devflow-manual-codex-worker/result.md.",
            "When blocked, append one JSON line to <task>/agents/devflow-manual-codex-worker/questions.jsonl.",
            "When failed, write <task>/agents/devflow-manual-codex-worker/worker_failed.json.",
            "",
            "Stop after writing exactly one terminal evidence artifact. Dev-Flow will verify independently.",
        ]
    )


def _read_matching_summary(path: Path, task: TaskRecord, notes: list[str]) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        notes.append("Ignored summary.json because it is malformed; canonical task.yaml was used.")
        return {}
    if not isinstance(data, dict):
        notes.append("Ignored summary.json because it is malformed; canonical task.yaml was used.")
        return {}

    expected_values = {
        "task_id": task.id,
        "title": task.title,
        "status": task.status,
        "workspace_path": task.workspace_path or task.workspace,
        "latest_verification_status": task.verification_status,
    }
    for key, expected in expected_values.items():
        if key in data and data[key] != expected:
            notes.append("Ignored summary.json because it conflicts with canonical task state.")
            return {}
    allowed_keys = {
        "workspace_dirty",
        "workspace_branch",
        "workspace_commit",
        "updated_at",
        "summary",
    }
    return {key: data[key] for key in sorted(allowed_keys) if key in data}


def _packet_summary(task: TaskRecord, summary_data: dict[str, Any]) -> str:
    summary = summary_data.get("summary")
    if isinstance(summary, str) and summary.strip():
        return summary.strip()
    return f"{task.id} {task.status}: {task.title}"


def _read_recent_events(path: Path, limit: int, notes: list[str]) -> tuple[list[dict[str, Any]], int, int]:
    if not path.exists():
        return [], 0, 0
    events: list[dict[str, Any]] = []
    malformed_lines = 0
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        notes.append(f"events.jsonl could not be read: {exc}")
        return [], 0, 0

    for line in lines:
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            malformed_lines += 1
            continue
        if isinstance(event, dict):
            events.append(event)
        else:
            malformed_lines += 1

    if malformed_lines:
        notes.append(f"Omitted {malformed_lines} malformed event line(s).")

    omitted_events = max(len(events) - limit, 0)
    recent_events = events[-limit:] if limit else []
    if omitted_events:
        notes.append(f"Omitted {omitted_events} older event(s); included the {len(recent_events)} most recent event(s).")
    return recent_events, omitted_events, malformed_lines


def _read_verification(
    path: Path,
    task: TaskRecord,
    projection: TaskStatusProjection,
    notes: list[str],
) -> dict[str, Any]:
    fallback = {
        "task_id": task.id,
        "status": projection.verification_status,
        "task_status": task.status,
        "exit_code": projection.verification_exit_code,
        "log_path": projection.verification_log_path,
        "command": projection.verification_command,
        "latest_log_line": task.latest_log_line,
    }
    if not path.exists():
        return fallback
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        notes.append("verification.json was unreadable; task.yaml verification fields were used.")
        return fallback
    if not isinstance(data, dict):
        notes.append("verification.json was unreadable; task.yaml verification fields were used.")
        return fallback
    if data.get("task_id") not in (None, task.id):
        notes.append("verification.json task_id did not match task.yaml; task.yaml verification fields were used.")
        return fallback
    return {**fallback, **data}


def _tail_log(repo_root: Path, path: Path, label: str, line_limit: int, byte_limit: int, notes: list[str]) -> TaskPacketLog:
    if not path.exists():
        return TaskPacketLog(
            path=_relative(repo_root, path),
            tail=[],
            line_count=0,
            omitted_lines=0,
            omitted_bytes=0,
            truncated=False,
        )
    try:
        raw = path.read_bytes()
    except OSError as exc:
        notes.append(f"{label} could not be read: {exc}")
        return TaskPacketLog(
            path=_relative(repo_root, path),
            tail=[],
            line_count=0,
            omitted_lines=0,
            omitted_bytes=0,
            truncated=False,
        )

    decoded = raw.decode("utf-8", errors="replace")
    decoded = _redact_string(decoded)
    lines = decoded.splitlines()
    omitted_lines = max(len(lines) - line_limit, 0)
    tail = lines[-line_limit:] if line_limit else []
    omitted_bytes = 0
    if byte_limit:
        tail_text = "\n".join(tail)
        tail_bytes = tail_text.encode("utf-8")
        omitted_bytes = max(len(tail_bytes) - byte_limit, 0)
        if omitted_bytes:
            tail = tail_bytes[-byte_limit:].decode("utf-8", errors="replace").splitlines()
    elif tail:
        omitted_bytes = len("\n".join(tail).encode("utf-8"))
        tail = []

    if omitted_lines:
        notes.append(f"Tail-limited {label} to last {len(tail)} of {len(lines)} line(s).")
    if omitted_bytes:
        notes.append(f"Tail-limited {label} to last {byte_limit} byte(s) of selected log text.")
    return TaskPacketLog(
        path=_relative(repo_root, path),
        tail=tail,
        line_count=len(lines),
        omitted_lines=omitted_lines,
        omitted_bytes=omitted_bytes,
        truncated=omitted_lines > 0 or omitted_bytes > 0,
    )


def _read_code_map_excerpt(repo_root: Path, line_limit: int, notes: list[str]) -> dict[str, Any] | None:
    path = repo_root / "CODE_MAP.md"
    if not path.exists() or not path.is_file():
        return None
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        notes.append(f"CODE_MAP.md could not be read: {exc}")
        return None
    included = lines[:line_limit] if line_limit else []
    omitted = max(len(lines) - len(included), 0)
    if omitted:
        notes.append(f"Included first {len(included)} of {len(lines)} CODE_MAP.md line(s).")
    return {
        "path": "CODE_MAP.md",
        "lines": included,
        "line_count": len(lines),
        "included_lines": len(included),
        "omitted_lines": omitted,
        "truncated": omitted > 0,
    }


def _constraints(virtual_workspace_path: str) -> list[str]:
    return [
        "Task packets are derived read-only projections, not state stores.",
        "task.yaml, events.jsonl, verification.json, worker.log, and verify.log remain canonical.",
        "summary.json is derived/cache only and cannot override canonical state.",
        f"Worker execution must stay inside {virtual_workspace_path}.",
        "Dev-Flow owns verification, merge readiness, and human approval gates.",
        "DevMode is the agent-facing discipline layer; load `using-devmode` before modifying files.",
    ]


def _allowed_artifacts(repo_root: Path, task_path: Path) -> list[str]:
    candidates = [
        task_path / "task.yaml",
        task_path / "events.jsonl",
        task_path / "verification.json",
        task_path / "logs" / "worker.log",
        task_path / "logs" / "verify.log",
    ]
    return [_relative(repo_root, path) for path in candidates if path.exists()]





def _normalize_to_posix(path_str: str) -> str:
    if path_str.startswith("file://"):
        path_str = path_str[7:]

    # Check for Windows path start (e.g. C:\... or similar) or backslashes
    if "\\" in path_str or (len(path_str) > 1 and path_str[1] == ":" and path_str[0].isalpha()):
        from pathlib import PureWindowsPath
        pure = PureWindowsPath(path_str)
        parts = list(pure.parts)
        if parts and len(parts[0]) > 1 and parts[0][1] == ":" and parts[0][0].isalpha():
            parts[0] = "/"
        path_str = "/".join(parts)
        import re
        path_str = re.sub(r'/+', '/', path_str)
    else:
        path_str = path_str.replace("\\", "/")
    return path_str


def _virtualize_path(path_str: str | None, repo_root: Path, task_id: str, workspace_path: Path | None = None) -> str | None:
    if path_str is None:
        return None
    if not isinstance(path_str, str) or not path_str.strip():
        return path_str

    if path_str.startswith("<workspace>") or path_str.startswith("<task>") or path_str.startswith("<devflow>"):
        return path_str

    normalized = _normalize_to_posix(path_str)

    try:
        p = Path(normalized)
        if not p.is_absolute():
            abs_p = (repo_root / p).resolve()
        else:
            abs_p = p.resolve()
    except Exception:
        abs_p = None

    resolved_repo = repo_root.resolve()
    resolved_task = (resolved_repo / ".devflow" / "tasks" / task_id).resolve()
    resolved_workspace = (workspace_path or (resolved_repo / ".devflow" / "workspaces" / task_id)).resolve()
    resolved_devflow = (resolved_repo / ".devflow").resolve()

    if abs_p is not None:
        try:
            rel = abs_p.relative_to(resolved_task)
            return f"<task>/{rel.as_posix()}"
        except ValueError:
            pass

        try:
            rel = abs_p.relative_to(resolved_workspace)
            return f"<workspace>/{rel.as_posix()}" if rel.as_posix() != "." else "<workspace>"
        except ValueError:
            pass

        try:
            rel = abs_p.relative_to(resolved_devflow)
            return f"<devflow>/{rel.as_posix()}" if rel.as_posix() != "." else "<devflow>"
        except ValueError:
            pass

        try:
            rel = abs_p.relative_to(resolved_repo)
            return rel.as_posix()
        except ValueError:
            pass

    task_rel_prefix = f".devflow/tasks/{task_id}"
    workspace_rel_prefix = f".devflow/workspaces/{task_id}"
    devflow_rel_prefix = ".devflow"

    clean_norm = normalized.lstrip("/")
    if clean_norm.startswith("./"):
        clean_norm = clean_norm[2:]

    if clean_norm == task_rel_prefix:
        return "<task>"
    elif clean_norm.startswith(task_rel_prefix + "/"):
        return f"<task>/{clean_norm[len(task_rel_prefix)+1:]}"
    elif clean_norm == workspace_rel_prefix:
        return "<workspace>"
    elif clean_norm.startswith(workspace_rel_prefix + "/"):
        return f"<workspace>/{clean_norm[len(workspace_rel_prefix)+1:]}"
    elif clean_norm == devflow_rel_prefix:
        return "<devflow>"
    elif clean_norm.startswith(devflow_rel_prefix + "/"):
        return f"<devflow>/{clean_norm[len(devflow_rel_prefix)+1:]}"

    # Scrub potential absolute OS secrets/user paths
    import re
    scrubbed = normalized
    scrubbed = re.sub(r'^[a-zA-Z]:/', '', scrubbed)
    scrubbed = re.sub(r'^/Users/[^/]+', '<home>', scrubbed)
    scrubbed = re.sub(r'^/home/[^/]+', '<home>', scrubbed)
    scrubbed = re.sub(r'^/tmp', '<temp>', scrubbed)
    scrubbed = re.sub(r'^/private/var/folders/[^/]+/[^/]+/[^/]+', '<temp>', scrubbed)
    scrubbed = re.sub(r'^/var/folders/[^/]+/[^/]+/[^/]+', '<temp>', scrubbed)

    scrubbed = re.sub(r'/+', '/', scrubbed)
    if scrubbed.startswith('/'):
        scrubbed = scrubbed.lstrip('/')
    return scrubbed


def _is_sensitive_key(key: str) -> bool:
    if not isinstance(key, str):
        return False
    # Tight matching to avoid false positives on words like monkey, keyboard, keynote, etc.
    # Matches:
    # 1. Standalone secret words: key, token, secret, password, passwd, authorization, apikey
    # 2. Key names ending with _key, _token, _secret, _password, _passwd
    # 3. Key names starting with key_, token_, secret_, password_, passwd_
    # 4. Standalone combinations: api_key, access_key, secret_key, access_token, refresh_token, auth_token
    pattern = r'(?i)^_*(?:key|token|secret|password|passwd|authorization|apikey|api_?key|access_?key|secret_?key|access_?token|refresh_?token|auth_?token|\w+(?:_key|_token|_secret|_password|_passwd)|(?:key|token|secret|password|passwd)_\w+)_*$'
    return bool(re.match(pattern, key))


def _redact_string(text: str) -> str:
    if not isinstance(text, str):
        return text

    # 1. Bearer <token>
    text = re.sub(r'(?i)\bbearer\s+\S+', 'Bearer [REDACTED]', text)

    # 2. Authorization: <token>
    text = re.sub(r'(?i)\bauthorization\s*:\s*(?!\s*bearer\b)[^\r\n]+', 'Authorization: [REDACTED]', text)

    # 3. .env and JSON/YAML style: KEY="value" or "KEY": "value"
    def repl_quoted(match):
        key = match.group(2)
        if _is_sensitive_key(key):
            return f"{match.group(1)}{match.group(2)}{match.group(1)}{match.group(3)}{match.group(4)}{match.group(5)}[REDACTED]{match.group(5)}"
        return match.group(0)

    text = re.sub(
        r'(?i)(["\']?)\b(\w+)\1\s*([=:])(\s*)(["\'])(.*?)\5',
        repl_quoted,
        text
    )

    # 4. .env style: KEY=value or "KEY": value
    def repl_unquoted(match):
        key = match.group(2)
        val = match.group(5)
        if _is_sensitive_key(key) and val != "[REDACTED]":
            return f"{match.group(1)}{match.group(2)}{match.group(1)}{match.group(3)}{match.group(4)}[REDACTED]"
        return match.group(0)

    text = re.sub(
        r'(?i)(["\']?)\b(\w+)\1\s*([=:])(\s*)([^\s"\'`]+)',
        repl_unquoted,
        text
    )

    # 5. OpenAI sk-... keys
    text = re.sub(r'\bsk-(?:proj-)?[a-zA-Z0-9_-]{12,}\b', '[REDACTED]', text)

    # 6. GitHub ghp_... and other tokens
    text = re.sub(r'\b(?:gh[pousr]_[a-zA-Z0-9]{20,}|github_pat_[a-zA-Z0-9_]{20,})\b', '[REDACTED]', text)

    # 7. Private key blocks
    text = re.sub(
        r'(?s)-----BEGIN\s+(?:[A-Z0-9\s_-]+\s+)?PRIVATE\s+KEY-----.*?-----END\s+(?:[A-Z0-9\s_-]+\s+)?PRIVATE\s+KEY-----',
        '[REDACTED PRIVATE KEY]',
        text
    )
    text = re.sub(r'-----BEGIN\s+(?:[A-Z0-9\s_-]+\s+)?PRIVATE\s+KEY-----', '[REDACTED PRIVATE KEY HEADER]', text)
    text = re.sub(r'-----END\s+(?:[A-Z0-9\s_-]+\s+)?PRIVATE\s+KEY-----', '[REDACTED PRIVATE KEY FOOTER]', text)

    return text


def _redact_secrets_in_value(val: Any, is_under_sensitive_key: bool = False) -> Any:
    if isinstance(val, str):
        if is_under_sensitive_key:
            return "[REDACTED]"
        return _redact_string(val)
    elif isinstance(val, list):
        return [_redact_secrets_in_value(item, is_under_sensitive_key) for item in val]
    elif isinstance(val, dict):
        updated = {}
        for k, v in val.items():
            sensitive_child = is_under_sensitive_key or _is_sensitive_key(k)
            if sensitive_child:
                if isinstance(v, str):
                    updated[k] = "[REDACTED]"
                else:
                    updated[k] = _redact_secrets_in_value(v, is_under_sensitive_key=True)
            else:
                updated[k] = _redact_secrets_in_value(v, is_under_sensitive_key=False)
        return updated
    elif isinstance(val, BaseModel):
        updated = {}
        for field_name in type(val).model_fields:
            field_val = getattr(val, field_name)
            sensitive_child = is_under_sensitive_key or _is_sensitive_key(field_name)
            if sensitive_child:
                if isinstance(field_val, str):
                    updated[field_name] = "[REDACTED]"
                else:
                    updated[field_name] = _redact_secrets_in_value(field_val, is_under_sensitive_key=True)
            else:
                updated[field_name] = _redact_secrets_in_value(field_val, is_under_sensitive_key=False)
        return val.model_copy(update=updated)
    return val
