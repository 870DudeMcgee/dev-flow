from __future__ import annotations

import re
from pathlib import Path


ANSI_ESCAPE_RE = re.compile(r"\x1b(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
SPINNER_CHARS = set("⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏")


def sanitize_log_line(line: str | None) -> str:
    if not line:
        return ""
    cleaned = ANSI_ESCAPE_RE.sub("", line)
    cleaned = cleaned.replace("\r", " ")
    cleaned = CONTROL_CHAR_RE.sub("", cleaned)
    normalized = " ".join(cleaned.split())
    if normalized and set(normalized.replace(" ", "")) <= SPINNER_CHARS:
        return ""
    return normalized


def latest_visible_log_line(path: Path) -> str:
    if not path.exists():
        return ""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    for line in reversed(lines):
        visible = sanitize_log_line(line)
        if visible:
            return visible
    return ""
