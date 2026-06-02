from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from devflow.control_room.paths import task_dir


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
        run_metadata=_read_json_object(agent_dir / "run.json"),
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

    result_summary = _first_result_summary_line(evidence.result_path)
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

    raw_path = _relative(root, evidence.raw_output_path)
    return f"Inspect Qwopus raw output at {raw_path} or run 'devflow task packet {task_id}' for escalation context."


def _first_result_summary_line(path: Path) -> str | None:
    if not path.exists():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and stripped not in {"## Summary", "## Status"}:
            return stripped
    return None


def _patch_evidence_matches(path: Path, task_id: str, agent_id: str, patch_hash: str) -> bool:
    payload = _read_json_object(path)
    return (
        payload.get("task_id") == task_id
        and payload.get("agent_id") == agent_id
        and payload.get("patch_hash") == patch_hash
        and isinstance(payload.get("applied_at"), str)
    )


def _read_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_text(encoding="utf-8").encode("utf-8")).hexdigest()


def _relative(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)