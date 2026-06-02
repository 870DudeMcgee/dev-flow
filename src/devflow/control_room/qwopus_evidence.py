from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from devflow.control_room.models import TaskRecord
from devflow.control_room.paths import relative_path, task_dir
from devflow.control_room.persistence import atomic_write_text


QWOPUS_AGENT_ID = "qwopus-implementer"


@dataclass(frozen=True)
class QwopusEvidence:
    agent_id: str
    task_path: Path
    agent_dir: Path
    proposal_patch_path: Path
    result_path: Path
    raw_output_path: Path
    run_metadata_path: Path
    worker_failed_path: Path
    run_metadata: dict[str, Any]

    @property
    def has_proposal_patch(self) -> bool:
        return self.proposal_patch_path.exists() and self.proposal_patch_path.stat().st_size > 0


def read_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def read_qwopus_evidence(root: Path, task_id: str, agent_id: str = QWOPUS_AGENT_ID) -> QwopusEvidence | None:
    path = task_dir(root, task_id)
    agent_dir = path / "agents" / agent_id
    if not agent_dir.exists() or not agent_dir.is_dir():
        return None

    evidence = QwopusEvidence(
        agent_id=agent_id,
        task_path=path,
        agent_dir=agent_dir,
        proposal_patch_path=agent_dir / "proposal.patch",
        result_path=agent_dir / "result.md",
        raw_output_path=agent_dir / "raw_output.md",
        run_metadata_path=agent_dir / "run.json",
        worker_failed_path=agent_dir / "worker_failed.json",
        run_metadata=read_json_object(agent_dir / "run.json"),
    )
    known_artifacts = (
        evidence.proposal_patch_path,
        evidence.result_path,
        evidence.raw_output_path,
        evidence.run_metadata_path,
        evidence.worker_failed_path,
    )
    if not any(path.exists() for path in known_artifacts):
        return None
    return evidence


def qwopus_result_summary(root: Path, task_id: str, agent_id: str = QWOPUS_AGENT_ID) -> str | None:
    evidence = read_qwopus_evidence(root, task_id, agent_id=agent_id)
    if evidence is None:
        return None

    result_summary = first_non_heading_line(evidence.result_path)
    if result_summary:
        return result_summary

    run_summary = evidence.run_metadata.get("summary")
    if isinstance(run_summary, str) and run_summary.strip():
        return run_summary.strip()

    if evidence.has_proposal_patch:
        return "Worker completed successfully and wrote proposal.patch"
    return None


def qwopus_patch_application_succeeded(root: Path, task_id: str, agent_id: str = QWOPUS_AGENT_ID) -> bool:
    evidence = read_qwopus_evidence(root, task_id, agent_id=agent_id)
    if evidence is None or not evidence.has_proposal_patch:
        return False

    patch_hash = _hash_file(evidence.proposal_patch_path)
    if _patch_evidence_matches(evidence.task_path / "patch-application.json", task_id, agent_id, patch_hash):
        return True
    return _patch_evidence_matches(evidence.task_path / "patches" / f"{patch_hash}.json", task_id, agent_id, patch_hash)


def qwopus_suggested_next_action(
    root: Path,
    task_id: str,
    *,
    task_status: str,
    verification_status: str,
    agent_id: str = QWOPUS_AGENT_ID,
) -> str | None:
    if task_status in {"created", "running", "promoted"}:
        return None

    evidence = read_qwopus_evidence(root, task_id, agent_id=agent_id)
    if evidence is None:
        return None

    if evidence.has_proposal_patch:
        if not qwopus_patch_application_succeeded(root, task_id, agent_id=agent_id):
            return f"devflow task apply-patch {task_id} --agent {agent_id}"
        if verification_status == "passed":
            return f"devflow task promote-preview {task_id}"
        return f"Verify the task using 'devflow task verify {task_id} -- <command>'"

    raw_path = relative_path(root, evidence.raw_output_path)
    return f"Inspect Qwopus raw output at {raw_path} or run 'devflow task packet {task_id}' for escalation context."


def qwopus_next_command(
    task_id: str,
    agent_id: str,
    status: str,
    patch_found: bool,
    patch_applied: bool,
    verification: Path,
) -> str:
    if status not in {"complete", "success"}:
        return f"devflow task escalation-packet {task_id} --agent {agent_id}"
    if patch_found and not patch_applied:
        return f"devflow task apply-patch {task_id} --agent {agent_id}"
    if patch_applied and verification.exists():
        data = read_json_object(verification)
        if data.get("status") == "passed":
            return f"devflow task promote-preview {task_id}"
        return f"devflow task escalation-packet {task_id} --agent {agent_id}"
    if patch_applied:
        return f"devflow task verify {task_id} --shell \"<focused test command>\""
    return f"devflow task escalation-packet {task_id} --agent {agent_id}"


def build_qwopus_summary(root: Path, task_path: Path, agent_id: str) -> dict[str, Any] | None:
    agent_dir = task_path / "agents" / agent_id
    run_json = agent_dir / "run.json"
    if not run_json.exists():
        return None
    run_data = read_json_object(run_json)
    if not run_data:
        return {
            "status": "unreadable_run_json",
            "next_suggested_command": f"devflow task escalation-packet {task_path.name} --agent {agent_id}",
        }

    patch_application = task_path / "patch-application.json"
    verification = task_path / "verification.json"
    proposed_paths = run_data.get("proposed_file_paths") or []
    verification_data = read_json_object(verification)
    status = str(run_data.get("status") or "unknown")
    return {
        "status": status,
        "proposal_patch_byte_length": run_data.get("proposal_patch_byte_length", 0),
        "proposed_file_count": len(proposed_paths),
        "proposed_file_paths": proposed_paths,
        "failure_reason": run_data.get("failure_reason"),
        "patch_application_path": relative_path(root, patch_application) if patch_application.exists() else None,
        "latest_verification_status": verification_data.get("status") if verification_data else None,
        "next_suggested_command": qwopus_next_command(
            task_path.name,
            agent_id,
            status,
            bool(run_data.get("proposal_patch_found")),
            patch_application.exists(),
            verification,
        ),
    }


def write_qwopus_escalation_packet(root: Path, task: TaskRecord, agent_id: str) -> Path:
    task_path = root / ".devflow" / "tasks" / task.id
    agent_dir = task_path / "agents" / agent_id
    agent_dir.mkdir(parents=True, exist_ok=True)
    packet_path = agent_dir / "escalation-packet.md"

    run_data = read_json_object(agent_dir / "run.json")
    patch_application = read_json_object(task_path / "patch-application.json")
    verification = read_json_object(task_path / "verification.json")
    result_summary = first_non_heading_line(agent_dir / "result.md")
    proposed_files = ", ".join(str(p) for p in (run_data.get("proposed_file_paths") or [])) if run_data else "none"

    lines = [
        f"# Dev-Flow Escalation Packet: {task.id}",
        "",
        "## Task",
        "",
        f"- Task ID: {task.id}",
        f"- Title: {task.title}",
        f"- Status: {task.status}",
        f"- Worker: {agent_id}",
        "",
        "## Local Worker Evidence",
        "",
        f"- Original packet path: {_relative_or_missing(root, agent_dir / 'packet.json')}",
        f"- Result summary: {result_summary or 'missing'}",
        f"- Run status: {run_data.get('status', 'missing') if run_data else 'missing'}",
        f"- Failure reason: {_failure_reason(run_data)}",
        f"- Raw output path: {_relative_or_missing(root, agent_dir / 'raw_output.md')}",
        f"- Proposal patch path: {_relative_or_missing(root, agent_dir / 'proposal.patch')}",
        f"- Proposal patch bytes: {run_data.get('proposal_patch_byte_length', 0) if run_data else 0}",
        f"- Proposed files: {proposed_files}",
        "",
        "## Patch And Verification Evidence",
        "",
        f"- Patch application status: {'present' if patch_application else 'missing'}",
        f"- Patch application error summary: {_patch_application_error(patch_application)}",
        f"- Verification status: {verification.get('status', 'missing') if verification else 'missing'}",
        f"- Verification command: {verification.get('command', 'missing') if verification else 'missing'}",
        f"- Verification log path: {verification.get('log_path', 'missing') if verification else 'missing'}",
        "",
        "## Frontier Question",
        "",
        "Given this bounded Dev-Flow task, the local Qwopus worker output, and the failure evidence below, "
        "provide a minimal patch or concrete repair plan that preserves Dev-Flow's control-room contract. "
        "Do not suggest autonomous promotion, remote provider execution, dashboard work, database work, "
        "or broad architecture expansion.",
    ]
    atomic_write_text(packet_path, "\n".join(lines) + "\n")
    return packet_path


def first_non_heading_line(path: Path) -> str:
    if not path.exists():
        return ""
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and not stripped.startswith("Agent:") and not stripped.startswith("Status:"):
            return stripped
    return ""


def _patch_evidence_matches(path: Path, task_id: str, agent_id: str, patch_hash: str) -> bool:
    payload = read_json_object(path)
    return (
        payload.get("task_id") == task_id
        and payload.get("agent_id") == agent_id
        and payload.get("patch_hash") == patch_hash
        and isinstance(payload.get("applied_at"), str)
    )


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _relative_or_missing(root: Path, path: Path) -> str:
    return relative_path(root, path) if path.exists() else "missing"


def _failure_reason(run_data: dict[str, Any]) -> str:
    if not run_data:
        return "missing"
    return str(run_data.get("failure_reason") or run_data.get("summary") or "none")


def _patch_application_error(patch_application: dict[str, Any]) -> str:
    if not patch_application:
        return "none"
    return str(patch_application.get("error") or patch_application.get("summary") or "none")
