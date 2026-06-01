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

    rejected_prefixes = (
        "Binary files ", "old mode ", "new mode ", "deleted file mode ",
        "new file mode ", "rename from ", "rename to ", "similarity index ",
        "dissimilarity index ", "copy from ", "copy to "
    )

    files: list[PatchFile] = []
    current_file: PatchFile | None = None
    current_hunk: Hunk | None = None

    lines = diff_text.splitlines(keepends=True)
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # Check for explicitly rejected prefixes
        if any(line.startswith(p) for p in rejected_prefixes):
            raise PatchParseError(f"Unsupported metadata: {line.strip()}")

        # Parse headers
        if line.startswith("--- "):
            # Extract path, stripping a/ prefix or handling /dev/null
            src_path = line[4:].strip()
            if src_path != "/dev/null":
                if src_path.startswith("a/"):
                    src_path = src_path[2:]
            
            if i + 1 >= len(lines) or not lines[i + 1].startswith("+++ "):
                raise PatchParseError("Missing matching +++ header line")
            
            next_line = lines[i + 1]
            dst_path = next_line[4:].strip()
            if dst_path != "/dev/null":
                if dst_path.startswith("b/"):
                    dst_path = dst_path[2:]

            current_file = PatchFile(source_file=src_path, target_file=dst_path, hunks=[])
            files.append(current_file)
            current_hunk = None
            i += 2
            continue

        elif line.startswith("@@ "):
            if not current_file:
                raise PatchParseError("Hunk starts without a file header")
            
            # Parse @@ -old_start,old_lines +new_start,new_lines @@
            parts = line.split(" ")
            if len(parts) < 4:
                raise PatchParseError(f"Malformed hunk header: {line.strip()}")
            
            try:
                # Parse old (source) spec
                old_spec = parts[1].removeprefix("-")
                if "," in old_spec:
                    old_start, old_lines = map(int, old_spec.split(","))
                else:
                    old_start, old_lines = int(old_spec), 1
                
                # Parse new (destination) spec
                new_spec = parts[2].removeprefix("+")
                if "," in new_spec:
                    new_start, new_lines = map(int, new_spec.split(","))
                else:
                    new_start, new_lines = int(new_spec), 1
            except ValueError as exc:
                raise PatchParseError(f"Malformed hunk integers: {line.strip()}") from exc

            current_hunk = Hunk(
                old_start=old_start,
                old_lines=old_lines,
                new_start=new_start,
                new_lines=new_lines,
                lines=[]
            )
            current_file.hunks.append(current_hunk)
            i += 1
            continue

        # Inside a hunk
        if current_hunk is not None:
            if line.startswith(("+", "-", " ")):
                current_hunk.lines.append(line)
            elif line.startswith("\\ No newline at end of file"):
                current_hunk.lines.append(line)
            else:
                current_hunk = None
        
        i += 1

    if not files:
        raise PatchParseError("No valid file patches parsed")
    return files

