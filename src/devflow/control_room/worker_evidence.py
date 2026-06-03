from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from devflow.control_room.persistence import atomic_write_text, utc_now


DEFAULT_RAW_OUTPUT_CAP_CHARS = 200_000


@dataclass(frozen=True)
class WorkerEvidence:
    worker_type: str
    profile_id: str
    worker_id: str
    task_id: str
    task_path: Path
    run_id: str
    evidence_dir: Path
    run_metadata_path: Path
    raw_output_path: Path
    response_path: Path
    packet_path: Path
    error_path: Path
    run_metadata: dict[str, Any]
    model: str
    adapter: str
    adapter_maturity: str
    permission_mode: str
    hermes_delegable: bool
    machine_class: str | None = None
    weight_class: str | None = None
    model_role_name: str | None = None
    required_verification_command: str | None = None
    model_alias_group: str | None = None
    quality_notes: str | None = None
    quality_score: float | None = None


def worker_evidence_paths(root: Path, task_id: str, run_id: str) -> dict[str, Path]:
    task_path = root / ".devflow" / "tasks" / task_id
    evidence_dir = task_path / "local-model-runs" / run_id
    return {
        "task_path": task_path,
        "evidence_dir": evidence_dir,
        "run_metadata_path": evidence_dir / "run.json",
        "raw_output_path": evidence_dir / "raw_output.txt",
        "response_path": evidence_dir / "response.md",
        "packet_path": evidence_dir / "packet.md",
        "error_path": evidence_dir / "error.txt",
    }


def expected_worker_evidence_outputs(root: Path, task_id: str, run_id: str) -> dict[str, str]:
    paths = worker_evidence_paths(root, task_id, run_id)
    return {
        key: str(path)
        for key, path in paths.items()
        if key
        in {
            "evidence_dir",
            "run_metadata_path",
            "raw_output_path",
            "response_path",
            "packet_path",
            "error_path",
        }
    }


def write_worker_evidence(
    *,
    root: Path,
    worker_type: str,
    profile_id: str,
    worker_id: str,
    task_id: str,
    run_id: str,
    packet_text: str,
    raw_output: str,
    response_text: str,
    model: str,
    adapter: str,
    adapter_maturity: str,
    permission_mode: str,
    hermes_delegable: bool,
    runtime: str,
    status: str,
    started_at: str,
    machine_class: str | None = None,
    weight_class: str | None = None,
    model_role_name: str | None = None,
    required_verification_command: str | None = None,
    model_alias_group: str | None = None,
    base_url: str | None = None,
    error_message: str | None = None,
    quality_notes: str | None = None,
    quality_score: float | None = None,
    max_raw_output_chars: int = DEFAULT_RAW_OUTPUT_CAP_CHARS,
) -> WorkerEvidence:
    paths = worker_evidence_paths(root, task_id, run_id)
    evidence_dir = paths["evidence_dir"]
    evidence_dir.mkdir(parents=True, exist_ok=True)

    capped_raw_output, raw_output_capped = _cap_text(raw_output, max_raw_output_chars)
    atomic_write_text(paths["packet_path"], packet_text)
    atomic_write_text(paths["raw_output_path"], capped_raw_output)
    atomic_write_text(paths["response_path"], response_text)
    if error_message is not None:
        atomic_write_text(paths["error_path"], error_message)

    run_metadata: dict[str, Any] = {
        "schema_version": 1,
        "worker_type": worker_type,
        "profile_id": profile_id,
        "worker_id": worker_id,
        "task_id": task_id,
        "run_id": run_id,
        "status": status,
        "started_at": started_at,
        "finished_at": utc_now().isoformat(),
        "model": model,
        "adapter": adapter,
        "runtime": runtime,
        "adapter_maturity": adapter_maturity,
        "permission_mode": permission_mode,
        "hermes_delegable": hermes_delegable,
        "machine_class": machine_class,
        "weight_class": weight_class,
        "model_role_name": model_role_name,
        "required_verification_command": required_verification_command,
        "model_alias_group": model_alias_group,
        "base_url": base_url,
        "evidence_dir": str(evidence_dir),
        "run_metadata_path": str(paths["run_metadata_path"]),
        "raw_output_path": str(paths["raw_output_path"]),
        "response_path": str(paths["response_path"]),
        "packet_path": str(paths["packet_path"]),
        "error_path": str(paths["error_path"]) if error_message is not None else None,
        "raw_output_char_length": len(raw_output),
        "raw_output_cap_chars": max_raw_output_chars,
        "raw_output_capped": raw_output_capped,
        "failure_captured": error_message is not None,
        "quality_notes": quality_notes,
        "quality_score": quality_score,
    }
    if error_message is not None:
        run_metadata["error_message"] = error_message
    atomic_write_text(paths["run_metadata_path"], json.dumps(run_metadata, indent=2, sort_keys=True) + "\n")

    return WorkerEvidence(
        worker_type=worker_type,
        profile_id=profile_id,
        worker_id=worker_id,
        task_id=task_id,
        task_path=paths["task_path"],
        run_id=run_id,
        evidence_dir=evidence_dir,
        run_metadata_path=paths["run_metadata_path"],
        raw_output_path=paths["raw_output_path"],
        response_path=paths["response_path"],
        packet_path=paths["packet_path"],
        error_path=paths["error_path"],
        run_metadata=run_metadata,
        model=model,
        adapter=adapter,
        adapter_maturity=adapter_maturity,
        permission_mode=permission_mode,
        hermes_delegable=hermes_delegable,
        machine_class=machine_class,
        weight_class=weight_class,
        model_role_name=model_role_name,
        required_verification_command=required_verification_command,
        model_alias_group=model_alias_group,
        quality_notes=quality_notes,
        quality_score=quality_score,
    )


def _cap_text(value: str, max_chars: int) -> tuple[str, bool]:
    if max_chars < 1:
        max_chars = DEFAULT_RAW_OUTPUT_CAP_CHARS
    if len(value) <= max_chars:
        return value, False
    suffix = f"\n\n[raw output capped at {max_chars} characters]\n"
    keep = max(0, max_chars - len(suffix))
    return value[:keep] + suffix, True
