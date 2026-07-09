from __future__ import annotations

import re
from pathlib import Path


ANSI_ESCAPE_RE = re.compile(r"\x1b(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
SPINNER_CHARS = set("⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏")
DEFAULT_LATEST_LOG_LINE_MAX_CHARS = 240
TRUNCATED_SUFFIX = " ...[truncated]"


def sanitize_log_line(line: str | None, *, max_chars: int | None = None) -> str:
    if not line:
        return ""
    cleaned = ANSI_ESCAPE_RE.sub("", line)
    cleaned = cleaned.replace("\r", " ")
    cleaned = CONTROL_CHAR_RE.sub("", cleaned)
    normalized = " ".join(cleaned.split())
    if normalized and set(normalized.replace(" ", "")) <= SPINNER_CHARS:
        return ""
    return truncate_log_line(normalized, max_chars=max_chars)


def truncate_log_line(line: str, *, max_chars: int | None = None) -> str:
    if max_chars is None or max_chars <= 0 or len(line) <= max_chars:
        return line
    keep_chars = max_chars - len(TRUNCATED_SUFFIX)
    if keep_chars <= 0:
        return TRUNCATED_SUFFIX[:max_chars]
    return line[:keep_chars].rstrip() + TRUNCATED_SUFFIX


def latest_visible_log_line(path: Path, *, max_chars: int | None = None) -> str:
    if not path.exists():
        return ""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    for line in reversed(lines):
        visible = sanitize_log_line(line, max_chars=max_chars)
        if visible:
            return visible
    return ""
