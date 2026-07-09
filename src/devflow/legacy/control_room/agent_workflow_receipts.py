"""Scout-first workflow receipts for agent-controlled repo work."""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MANUAL_FRONTIER_READ_BUDGET = 2


def _slug_task_id(task_id: str) -> str:
    slug = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in task_id.strip())
    return slug.strip("-") or "task"


def evidence_dir(root: Path | str) -> Path:
    return Path(root).resolve() / ".devflow" / "evidence"


def scout_packet_path(root: Path | str, task_id: str) -> Path:
    return evidence_dir(root) / f"scout-{_slug_task_id(task_id)}.json"


def preflight_receipt_path(root: Path | str, task_id: str) -> Path:
    return evidence_dir(root) / f"preflight-{_slug_task_id(task_id)}.json"


def _relative_or_absolute(root: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path)


def _context_map_available(root: Path) -> bool:
    return (root / ".context-map").is_dir()


def _context_map_source_index_status(root: Path) -> str:
    """Return compact source-index readiness for preflight receipts."""
    source_path = root / ".context-map" / "source-index.json"
    if not source_path.is_file():
        return "missing"
    try:
        data = json.loads(source_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "unreadable"
    files = data.get("files") if isinstance(data, dict) else None
    return "ok" if files else "empty"


def _slug_codebase_memory_part(value: str) -> str:
    slug = "".join(ch if ch.isalnum() else "-" for ch in value.strip())
    return "-".join(part for part in slug.split("-") if part)


def _expected_codebase_memory_project(root: Path) -> str:
    """Return the codebase-memory project name for an absolute repo path."""
    parts = [_slug_codebase_memory_part(part) for part in root.resolve().parts if part and part != root.anchor]
    return "-".join(part for part in parts if part)


def _json_object_from_output(output: str) -> dict[str, Any] | None:
    for start, char in enumerate(output):
        if char != "{":
            continue
        try:
            parsed = json.loads(output[start:])
        except json.JSONDecodeError:
            continue
        return parsed if isinstance(parsed, dict) else None
    return None


def _agent_proxy_index_status(root: Path) -> dict[str, Any]:
    """Check whether codebase-memory has an index for this repo without dumping it."""
    expected_project = _expected_codebase_memory_project(root)
    binary = os.environ.get("CBM_BINARY") or str(Path.home() / ".local" / "bin" / "codebase-memory-mcp")
    payload: dict[str, Any] = {
        "project": expected_project,
        "indexed": False,
        "status": "binary_missing",
    }
    if not Path(binary).is_file():
        return payload
    try:
        result = subprocess.run(
            [binary, "cli", "list_projects", "{}"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        payload["status"] = "unavailable"
        return payload
    data = _json_object_from_output(result.stdout)
    if result.returncode != 0 or data is None:
        payload["status"] = "unreadable"
        return payload
    projects = data.get("projects") if isinstance(data, dict) else None
    if not isinstance(projects, list):
        payload["status"] = "unreadable"
        return payload
    project_names = {str(project.get("name")) for project in projects if isinstance(project, dict)}
    payload["indexed"] = expected_project in project_names
    payload["status"] = "ok" if payload["indexed"] else "missing"
    return payload


def _fleet_state_captured(root: Path) -> bool:
    return (root / ".devflow" / "fleet-contract.json").is_file()


def _scout_packet_action_status(packet_path: Path) -> dict[str, Any]:
    """Return whether an existing ScoutPacket authorizes implementation routing."""
    if not packet_path.is_file():
        return {"actionable": False, "status": "missing", "recommended_lane": None}
    try:
        packet = json.loads(packet_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"actionable": False, "status": "unreadable", "recommended_lane": None}
    if not isinstance(packet, dict):
        return {"actionable": False, "status": "unreadable", "recommended_lane": None}
    recommended_lane = packet.get("recommended_lane")
    files_to_touch = packet.get("files_to_touch")
    has_files = isinstance(files_to_touch, list) and bool(files_to_touch)
    actionable = recommended_lane != "ask_user" and has_files
    status = "actionable" if actionable else "needs_scope"
    return {"actionable": actionable, "status": status, "recommended_lane": recommended_lane}


def build_agent_preflight_receipt(
    root: Path | str,
    task_id: str,
    *,
    handoff: str | None = None,
    skills_loaded: list[str] | None = None,
    manual_read_count: int = 0,
    scout_required: bool = True,
) -> dict[str, Any]:
    """Build the machine-checkable receipt that gates editing."""
    repo_root = Path(root).resolve()
    packet_path = scout_packet_path(repo_root, task_id)
    receipt_path = preflight_receipt_path(repo_root, task_id)
    handoff_path = (repo_root / handoff).resolve() if handoff else None
    handoff_read = bool(handoff_path and handoff_path.is_file())
    scout_packet_exists = packet_path.is_file()
    scout_packet_action = _scout_packet_action_status(packet_path)
    manual_budget_exceeded = manual_read_count > MANUAL_FRONTIER_READ_BUDGET
    context_map_source_index = _context_map_source_index_status(repo_root)
    agent_proxy = _agent_proxy_index_status(repo_root)
    mapping_tools_ready = context_map_source_index == "ok" or bool(agent_proxy["indexed"])
    scout_gate_open = bool(scout_packet_action["actionable"])
    allowed_to_edit = (not scout_required or (scout_gate_open and mapping_tools_ready)) and not manual_budget_exceeded

    if manual_budget_exceeded:
        next_action = f"run devflow agent scout --task {task_id} before more source reads"
    elif scout_required and not mapping_tools_ready:
        next_action = "repair repo map indexes before scout"
    elif scout_required and not scout_packet_exists:
        next_action = f"run devflow agent scout --task {task_id}"
    elif scout_required and not scout_gate_open:
        next_action = "provide scoped handoff or explicit file scope before editing"
    else:
        next_action = "route implementation with scout evidence"

    return {
        "task_id": task_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "handoff_path": _relative_or_absolute(repo_root, handoff_path) if handoff_path else None,
        "handoff_read": handoff_read,
        "skills_loaded": list(skills_loaded or []),
        "manual_frontier_reads": manual_read_count,
        "manual_frontier_reads_allowed_before_scout": MANUAL_FRONTIER_READ_BUDGET,
        "manual_read_budget_exceeded": manual_budget_exceeded,
        "scout_required": scout_required,
        "scout_packet_exists": scout_packet_exists,
        "scout_packet_actionable": scout_gate_open,
        "scout_packet_status": scout_packet_action["status"],
        "scout_recommended_lane": scout_packet_action["recommended_lane"],
        "scout_packet_path": _relative_or_absolute(repo_root, packet_path),
        "repo_root": str(repo_root),
        "agent_proxy_indexed": bool(agent_proxy["indexed"]),
        "agent_proxy_project": agent_proxy["project"],
        "agent_proxy_status": agent_proxy["status"],
        "context_map_available": _context_map_available(repo_root),
        "context_map_source_index": context_map_source_index,
        "mapping_tools_ready": mapping_tools_ready,
        "context_map_hint": f"mcp_context_map_orient(..., repo={str(repo_root)!r})",
        "agent_proxy_hint": f"mcp_agent_proxy_codebase_search(..., project={agent_proxy['project']!r})",
        "fleet_state_captured": _fleet_state_captured(repo_root),
        "allowed_to_edit": allowed_to_edit,
        "next_action": next_action,
        "evidence_path": _relative_or_absolute(repo_root, receipt_path),
    }


def write_agent_preflight_receipt(
    root: Path | str,
    task_id: str,
    *,
    handoff: str | None = None,
    skills_loaded: list[str] | None = None,
    manual_read_count: int = 0,
    scout_required: bool = True,
) -> tuple[dict[str, Any], Path]:
    payload = build_agent_preflight_receipt(
        root,
        task_id,
        handoff=handoff,
        skills_loaded=skills_loaded,
        manual_read_count=manual_read_count,
        scout_required=scout_required,
    )
    path = preflight_receipt_path(root, task_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload, path


def parse_read_next(values: list[str]) -> list[dict[str, str]]:
    parsed: list[dict[str, str]] = []
    for value in values:
        path, sep, reason = value.partition(":")
        parsed.append({"path": path.strip(), "reason": reason.strip() if sep else "needs focused scout follow-up"})
    return parsed


def build_agent_scout_packet(
    root: Path | str,
    task_id: str,
    *,
    map_source: str = "context_map",
    handoff_path: str | None = None,
    handoff_read: bool = False,
    map_freshness: dict[str, str] | None = None,
    files_to_touch: list[str] | None = None,
    files_to_read_next: list[dict[str, str]] | None = None,
    tests: list[str] | None = None,
    risks: list[str] | None = None,
    recommended_lane: str = "direct_tiny_edit",
    verification: str | None = None,
    evidence_paths: list[str] | None = None,
    context_brief: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    repo_root = Path(root).resolve()
    packet_path = scout_packet_path(repo_root, task_id)
    freshness = map_freshness or {"source_index": "missing", "graphify": "missing", "confidence": "low"}

    return {
        "task_id": task_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "handoff_path": handoff_path,
        "handoff_read": handoff_read,
        "map_source": map_source,
        "map_freshness": freshness,
        "files_to_touch": list(files_to_touch or []),
        "files_to_read_next": list(files_to_read_next or []),
        "tests": list(tests or []),
        "risks": list(risks or []),
        "recommended_lane": recommended_lane,
        "verification": verification
        or "python3 ~/.hermes/skills/software-development/local-fleet-efficiency/scripts/local_test_runner.py --project-root .",
        "evidence_paths": list(evidence_paths or [_relative_or_absolute(repo_root, packet_path)]),
        "context_brief": list(context_brief or []),
    }


def write_agent_scout_packet(
    root: Path | str,
    task_id: str,
    *,
    map_source: str = "context_map",
    handoff_path: str | None = None,
    handoff_read: bool = False,
    map_freshness: dict[str, str] | None = None,
    files_to_touch: list[str] | None = None,
    files_to_read_next: list[dict[str, str]] | None = None,
    tests: list[str] | None = None,
    risks: list[str] | None = None,
    recommended_lane: str = "direct_tiny_edit",
    verification: str | None = None,
    evidence_paths: list[str] | None = None,
    context_brief: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], Path]:
    payload = build_agent_scout_packet(
        root,
        task_id,
        map_source=map_source,
        handoff_path=handoff_path,
        handoff_read=handoff_read,
        map_freshness=map_freshness,
        files_to_touch=files_to_touch,
        files_to_read_next=files_to_read_next,
        tests=tests,
        risks=risks,
        recommended_lane=recommended_lane,
        verification=verification,
        evidence_paths=evidence_paths,
        context_brief=context_brief,
    )
    path = scout_packet_path(root, task_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload, path
