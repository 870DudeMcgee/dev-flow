from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

class PatchError(Exception):
    """Base class for all patch errors."""
    pass

class PatchSelectionError(PatchError):
    """Raised when there is an issue selecting/locating the patch."""
    pass

class PatchParseError(PatchError):
    """Raised when parsing the unified diff fails."""
    pass

class PatchApplicationError(PatchError):
    """Raised when patch application fails due to safety or mismatch conflicts."""
    pass

@dataclass
class Hunk:
    old_start: int
    old_lines: int
    new_start: int
    new_lines: int
    lines: list[str]  # prefixed with ' ', '-', '+'

@dataclass
class PatchFile:
    source_file: str  # e.g., 'a/file.py' or '/dev/null'
    target_file: str  # e.g., 'b/file.py' or '/dev/null'
    hunks: list[Hunk]

def parse_unified_diff(diff_text: str) -> list[PatchFile]:
    if not diff_text.strip():
        raise PatchParseError("Empty diff")
    return []
