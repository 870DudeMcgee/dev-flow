from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any


def build_quality_gate_transcript_text(root: Path, session_id: str) -> str:
    transcript_path = root / ".devflow" / "brainstorms" / session_id / "transcript.jsonl"
    records = _read_transcript_records(transcript_path)
    if not records:
        raise ValueError(f"brainstorm session has no transcript: {session_id}")
    return format_quality_gate_transcript(records)


def format_quality_gate_transcript(records: list[Mapping[str, Any]]) -> str:
    transcript_lines = []
    for record in records:
        role = str(record.get("role") or "unknown")
        content = str(record.get("content") or "").strip()
        if content:
            transcript_lines.append(f"### {role.title()}\n\n{content}\n")
    return "\n".join(transcript_lines)


def _read_transcript_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            records.append(value)
    return records
