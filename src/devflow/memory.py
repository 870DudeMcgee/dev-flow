from __future__ import annotations

import datetime
import fnmatch
import hashlib
import json
import os
from typing import Any


MEMORY_DIR = os.path.join(".devflow", "memory")


def _utc_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


def _normalize_path(path: str) -> str:
    return path.strip().strip("`").replace(os.sep, "/")


def _memory_dir(cwd: str = ".") -> str:
    return os.path.join(cwd, MEMORY_DIR)


def _memory_path(memory_id: str, cwd: str = ".") -> str:
    return os.path.join(_memory_dir(cwd), f"{memory_id}.json")


def _generate_memory_id(memory_type: str, statement: str, evidence: str) -> str:
    seed = f"{memory_type}\n{statement}\n{evidence}"
    return f"mem_{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:12]}"


def _path_matches(path: str, pattern: str) -> bool:
    normalized_path = _normalize_path(path)
    normalized_pattern = _normalize_path(pattern)
    if normalized_path == normalized_pattern:
        return True
    if normalized_pattern.endswith("/**") and normalized_path.startswith(normalized_pattern[:-3]):
        return True
    return fnmatch.fnmatch(normalized_path, normalized_pattern)


def validate_memory_record(record: dict[str, Any]) -> None:
    required = {
        "memory_id",
        "type",
        "statement",
        "evidence",
        "confidence",
        "last_validated",
        "invalidated_by_paths",
        "status",
    }
    missing = sorted(required - set(record))
    if missing:
        raise ValueError(f"Memory record missing required fields: {', '.join(missing)}")
    if not isinstance(record["memory_id"], str) or not record["memory_id"].strip():
        raise ValueError("Memory record memory_id must be a non-empty string")
    if not isinstance(record["type"], str) or not record["type"].strip():
        raise ValueError("Memory record type must be a non-empty string")
    if not isinstance(record["statement"], str) or not record["statement"].strip():
        raise ValueError("Memory record statement must be a non-empty string")
    if not isinstance(record["evidence"], str) or not record["evidence"].strip():
        raise ValueError("Memory record evidence must be a non-empty string")
    if not isinstance(record["invalidated_by_paths"], list) or not all(isinstance(path, str) for path in record["invalidated_by_paths"]):
        raise ValueError("Memory record invalidated_by_paths must be a list of strings")
    confidence = record["confidence"]
    if not isinstance(confidence, (int, float)) or confidence < 0.0 or confidence > 1.0:
        raise ValueError("Memory record confidence must be between 0.0 and 1.0")
    if record["status"] not in {"active", "stale"}:
        raise ValueError("Memory record status must be active or stale")


def _read_memory_file(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        record = json.load(handle)
    validate_memory_record(record)
    return record


def _write_memory_file(record: dict[str, Any], cwd: str = ".") -> dict[str, Any]:
    validate_memory_record(record)
    os.makedirs(_memory_dir(cwd), exist_ok=True)
    path = _memory_path(record["memory_id"], cwd)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(record, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return record


def add_memory(
    memory_type: str,
    statement: str,
    evidence: str,
    invalidated_by_paths: list[str],
    confidence: float = 1.0,
    cwd: str = ".",
) -> dict[str, Any]:
    """Add or replace one architectural memory record."""
    record = {
        "memory_id": _generate_memory_id(memory_type, statement, evidence),
        "type": memory_type.strip(),
        "statement": statement.strip(),
        "evidence": evidence.strip(),
        "confidence": float(confidence),
        "last_validated": _utc_now(),
        "invalidated_by_paths": [_normalize_path(path) for path in invalidated_by_paths if path.strip()],
        "status": "active",
    }
    return _write_memory_file(record, cwd=cwd)


def list_memories(include_stale: bool = True, cwd: str = ".") -> list[dict[str, Any]]:
    """List stored memory records in deterministic order."""
    root = _memory_dir(cwd)
    if not os.path.isdir(root):
        return []
    records: list[dict[str, Any]] = []
    for filename in sorted(os.listdir(root)):
        if not filename.endswith(".json"):
            continue
        record = _read_memory_file(os.path.join(root, filename))
        if include_stale or record.get("status") == "active":
            records.append(record)
    return records


def inspect_memory(memory_id: str, cwd: str = ".") -> dict[str, Any]:
    """Read one memory record by id."""
    path = _memory_path(memory_id, cwd)
    if not os.path.exists(path):
        raise FileNotFoundError(f"Memory record not found: {memory_id}")
    return _read_memory_file(path)


def active_memories_for_paths(paths: list[str], cwd: str = ".") -> list[dict[str, Any]]:
    """Return active memories relevant to a set of task paths."""
    if not paths:
        return list_memories(include_stale=False, cwd=cwd)
    selected: list[dict[str, Any]] = []
    for record in list_memories(include_stale=False, cwd=cwd):
        invalidators = [str(path) for path in record.get("invalidated_by_paths", [])]
        if any(_path_matches(path, pattern) for path in paths for pattern in invalidators):
            selected.append(record)
    return selected


def invalidate_memories(paths: list[str], memory_ids: list[str] | None = None, cwd: str = ".") -> list[dict[str, Any]]:
    """Mark active memories stale when changed paths match their invalidation rules."""
    normalized_paths = [_normalize_path(path) for path in paths]
    id_filter = set(memory_ids or [])
    invalidated: list[dict[str, Any]] = []
    for record in list_memories(include_stale=True, cwd=cwd):
        if id_filter and record["memory_id"] not in id_filter:
            continue
        if record.get("status") == "stale":
            continue
        invalidators = [str(path) for path in record.get("invalidated_by_paths", [])]
        if not id_filter and not any(_path_matches(path, pattern) for path in normalized_paths for pattern in invalidators):
            continue
        updated = dict(record)
        updated["status"] = "stale"
        updated["confidence"] = 0.0
        updated["staled_at"] = _utc_now()
        updated["staled_by_paths"] = normalized_paths
        invalidated.append(_write_memory_file(updated, cwd=cwd))
    return invalidated