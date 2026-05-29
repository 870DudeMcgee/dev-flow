from __future__ import annotations

import datetime
import hashlib
import json
import os
import re
import subprocess
from dataclasses import dataclass
from typing import Any


ARTIFACT_ROOT = os.path.join(".devflow", "artifacts")
REQUIRED_ARTIFACT_FIELDS = {
    "artifact_id",
    "artifact_type",
    "task_id",
    "role",
    "created_at",
    "repo_head",
    "input_hash",
    "output_hash",
    "body_path",
    "metadata_path",
    "parent_artifacts",
    "allowed_paths",
    "touched_paths",
    "verification_status",
    "apply_status",
    "metadata",
}
HASH_PATTERN = re.compile(r"^sha256:[a-f0-9]{64}$")
ARTIFACT_ID_PATTERN = re.compile(r"^art_[0-9]{14}_[a-f0-9]{4}$")
VERIFICATION_STATUSES = {"not_run", "passing", "failing", "blocked"}
APPLY_STATUSES = {"not_applied", "applied", "rolled_back", "blocked"}
RISK_TIERS = {"low", "medium", "high", "critical"}


@dataclass(frozen=True)
class ArtifactRecord:
    artifact_id: str
    sequence: int
    metadata_path: str
    body_path: str
    metadata: dict[str, Any]


def sha256_text(value: str) -> str:
    """Return a stable sha256 digest string for UTF-8 text."""
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def _safe_segment(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    return safe.strip("._-") or "artifact"


def _artifact_timestamp(created_at: str) -> str:
    normalized = created_at.replace("Z", "+00:00")
    try:
        parsed = datetime.datetime.fromisoformat(normalized)
        return parsed.strftime("%Y%m%d%H%M%S")
    except ValueError:
        digits = re.sub(r"\D", "", created_at)
        return (digits + "00000000000000")[:14]


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


def generate_artifact_id(created_at: str | None = None, seed: str = "") -> str:
    """Generate a deterministic artifact id from a timestamp and caller-provided seed."""
    timestamp = _artifact_timestamp(created_at or _now_iso())
    short_hash = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:4]
    return f"art_{timestamp}_{short_hash}"


def _repo_head(cwd: str) -> str:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=cwd,
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError:
        return ""
    if proc.returncode != 0:
        return ""
    return proc.stdout.strip()


def _task_artifact_dir(task_id: str, root: str = ARTIFACT_ROOT) -> str:
    return os.path.join(root, _safe_segment(task_id))


def _next_sequence(task_dir: str) -> int:
    if not os.path.isdir(task_dir):
        return 1
    highest = 0
    for name in os.listdir(task_dir):
        match = re.match(r"^(\d{3})-", name)
        if match:
            highest = max(highest, int(match.group(1)))
    return highest + 1


def artifact_body_path(path: str) -> str:
    """Resolve an artifact body path from either a body path or metadata path."""
    if path.endswith(".metadata.json"):
        return path[: -len(".metadata.json")]
    return path


def artifact_metadata_path(path: str) -> str:
    """Resolve an artifact metadata path from either a body path or metadata path."""
    if path.endswith(".metadata.json"):
        return path
    return f"{path}.metadata.json"


def touched_paths_from_diff(diff_text: str) -> list[str]:
    """Extract touched repository paths from unified diff +++ headers."""
    paths: list[str] = []
    pattern = re.compile(r"^\+\+\+\s+b/(.+)$", re.MULTILINE)
    for match in pattern.finditer(diff_text):
        path = match.group(1).strip()
        if path != "/dev/null":
            paths.append(path)
    return sorted(set(paths))


def validate_artifact_metadata(metadata: dict[str, Any]) -> None:
    """Validate the Phase 1 artifact metadata contract without external dependencies."""
    missing = sorted(REQUIRED_ARTIFACT_FIELDS - set(metadata))
    if missing:
        raise ValueError(f"Artifact metadata missing required fields: {', '.join(missing)}")

    if not isinstance(metadata.get("artifact_id"), str) or not ARTIFACT_ID_PATTERN.match(metadata["artifact_id"]):
        raise ValueError("Artifact metadata has invalid artifact_id")
    for key in ("artifact_type", "task_id", "created_at", "body_path", "metadata_path"):
        if not isinstance(metadata.get(key), str) or not metadata[key]:
            raise ValueError(f"Artifact metadata field must be a non-empty string: {key}")
    if not isinstance(metadata.get("role"), str):
        raise ValueError("Artifact metadata field must be a string: role")
    for key in ("input_hash", "output_hash"):
        if not isinstance(metadata.get(key), str) or not HASH_PATTERN.match(metadata[key]):
            raise ValueError(f"Artifact metadata has invalid hash field: {key}")
    for key in ("parent_artifacts", "allowed_paths", "touched_paths"):
        if not isinstance(metadata.get(key), list) or not all(isinstance(item, str) for item in metadata[key]):
            raise ValueError(f"Artifact metadata field must be a list of strings: {key}")
    if metadata.get("risk") not in RISK_TIERS:
        raise ValueError("Artifact metadata has invalid risk tier")
    confidence = metadata.get("confidence")
    if confidence is not None and not (isinstance(confidence, (int, float)) and 0 <= confidence <= 1):
        raise ValueError("Artifact metadata confidence must be null or between 0 and 1")
    if metadata.get("verification_status") not in VERIFICATION_STATUSES:
        raise ValueError("Artifact metadata has invalid verification_status")
    if metadata.get("apply_status") not in APPLY_STATUSES:
        raise ValueError("Artifact metadata has invalid apply_status")
    if not isinstance(metadata.get("metadata"), dict):
        raise ValueError("Artifact metadata field must be an object: metadata")


def write_artifact(
    task_id: str,
    artifact_type: str,
    body: str,
    role: str = "",
    input_text: str = "",
    parent_artifacts: list[str] | None = None,
    allowed_paths: list[str] | None = None,
    touched_paths: list[str] | None = None,
    risk: str = "low",
    confidence: float | None = None,
    metadata: dict[str, Any] | None = None,
    agent_profile: str = "",
    model: str = "",
    prompt_version: str = "",
    schema_version: str = "artifact@0.1.0",
    verification_status: str = "not_run",
    apply_status: str = "not_applied",
    created_at: str | None = None,
    root: str = ARTIFACT_ROOT,
    cwd: str | None = None,
) -> ArtifactRecord:
    """Write an artifact body plus JSON metadata under `.devflow/artifacts/<task_id>/`."""
    cwd = cwd or os.getcwd()
    created_at = created_at or _now_iso()
    parent_artifacts = parent_artifacts or []
    allowed_paths = allowed_paths or []
    touched_paths = touched_paths if touched_paths is not None else touched_paths_from_diff(body)
    metadata = metadata or {}

    input_hash = sha256_text(input_text)
    output_hash = sha256_text(body)
    seed = "|".join([task_id, artifact_type, role, input_hash, output_hash])
    artifact_id = generate_artifact_id(created_at, seed)

    task_dir = _task_artifact_dir(task_id, root=root)
    os.makedirs(task_dir, exist_ok=True)
    sequence = _next_sequence(task_dir)
    body_filename = f"{sequence:03d}-{_safe_segment(artifact_type)}"
    body_path = os.path.join(task_dir, body_filename)
    metadata_path = artifact_metadata_path(body_path)

    payload: dict[str, Any] = {
        "artifact_id": artifact_id,
        "artifact_type": artifact_type,
        "task_id": task_id,
        "role": role,
        "agent_profile": agent_profile,
        "model": model,
        "prompt_version": prompt_version,
        "schema_version": schema_version,
        "created_at": created_at,
        "repo_head": _repo_head(cwd),
        "input_hash": input_hash,
        "output_hash": output_hash,
        "parent_artifacts": parent_artifacts,
        "allowed_paths": allowed_paths,
        "touched_paths": touched_paths,
        "risk": risk,
        "confidence": confidence,
        "verification_status": verification_status,
        "apply_status": apply_status,
        "body_path": body_path,
        "metadata_path": metadata_path,
        "metadata": metadata,
    }
    validate_artifact_metadata(payload)

    temp_body = f"{body_path}.tmp"
    temp_metadata = f"{metadata_path}.tmp"
    with open(temp_body, "w", encoding="utf-8") as handle:
        handle.write(body)
    with open(temp_metadata, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
    os.replace(temp_body, body_path)
    os.replace(temp_metadata, metadata_path)

    return ArtifactRecord(
        artifact_id=artifact_id,
        sequence=sequence,
        metadata_path=metadata_path,
        body_path=body_path,
        metadata=payload,
    )


def read_artifact(path: str) -> tuple[dict[str, Any], str]:
    """Read an artifact by metadata or body path, validating metadata and body hash."""
    metadata_path = artifact_metadata_path(path)
    body_path = artifact_body_path(path)
    if not os.path.exists(metadata_path):
        raise FileNotFoundError(f"Artifact metadata not found: {metadata_path}")
    if not os.path.exists(body_path):
        raise FileNotFoundError(f"Artifact body not found: {body_path}")

    with open(metadata_path, "r", encoding="utf-8") as handle:
        metadata = json.load(handle)
    validate_artifact_metadata(metadata)
    with open(body_path, "r", encoding="utf-8") as handle:
        body = handle.read()

    actual_hash = sha256_text(body)
    expected_hash = metadata.get("output_hash", "")
    if expected_hash and actual_hash != expected_hash:
        raise ValueError(f"Artifact body hash mismatch: expected {expected_hash}, got {actual_hash}")
    return metadata, body


def _record_from_metadata_path(metadata_path: str) -> ArtifactRecord:
    metadata, _ = read_artifact(metadata_path)
    body_path = artifact_body_path(metadata_path)
    sequence_match = re.search(r"(?:^|/)(\d{3})-", body_path.replace("\\", "/"))
    sequence = int(sequence_match.group(1)) if sequence_match else 0
    return ArtifactRecord(
        artifact_id=str(metadata.get("artifact_id", "")),
        sequence=sequence,
        metadata_path=metadata_path,
        body_path=body_path,
        metadata=metadata,
    )


def list_artifacts(task_id: str, root: str = ARTIFACT_ROOT) -> list[ArtifactRecord]:
    """List task artifacts in task-local sequence order."""
    task_dir = _task_artifact_dir(task_id, root=root)
    if not os.path.isdir(task_dir):
        return []
    records = []
    for name in os.listdir(task_dir):
        if not name.endswith(".metadata.json"):
            continue
        records.append(_record_from_metadata_path(os.path.join(task_dir, name)))
    return sorted(records, key=lambda record: (record.sequence, record.metadata.get("created_at", "")))


def find_artifact(identifier: str, root: str = ARTIFACT_ROOT) -> ArtifactRecord:
    """Find an artifact by id, metadata path, or body path."""
    if os.path.exists(identifier):
        metadata_path = artifact_metadata_path(identifier)
        return _record_from_metadata_path(metadata_path)

    if not os.path.isdir(root):
        raise FileNotFoundError(f"Artifact root not found: {root}")

    matches: list[ArtifactRecord] = []
    for current_root, _, files in os.walk(root):
        for name in files:
            if not name.endswith(".metadata.json"):
                continue
            record = _record_from_metadata_path(os.path.join(current_root, name))
            if record.artifact_id == identifier:
                matches.append(record)

    if not matches:
        raise FileNotFoundError(f"Artifact not found: {identifier}")
    if len(matches) > 1:
        raise ValueError(f"Artifact id is ambiguous: {identifier}")
    return matches[0]
