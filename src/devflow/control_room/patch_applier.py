from __future__ import annotations
import hashlib
import json
from dataclasses import asdict, dataclass
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


import tempfile

@dataclass
class ChangedFile:
    path: str
    operation: Literal["created", "modified", "deleted"]
    additions: int
    deletions: int

@dataclass
class PatchApplyResult:
    changed_files: list[ChangedFile]
    patch_hash: str

def apply_patch_files(
    workspace_root: Path,
    patch_files: list[PatchFile],
    dry_run: bool = False,
    patch_hash: str | None = None,
) -> PatchApplyResult:
    workspace_root = workspace_root.resolve()
    effective_patch_hash = patch_hash or _hash_patch_files(patch_files)
    
    # 1. Validate paths and resolve changes in-memory
    file_updates: dict[Path, list[str]] = {}
    changed_files_list: list[ChangedFile] = []
    deleted_files_list: list[Path] = []

    for pf in patch_files:
        is_creation = pf.source_file == "/dev/null"
        is_deletion = pf.target_file == "/dev/null"

        # Determine target path relative to workspace root
        rel_target_path = pf.target_file if not is_deletion else pf.source_file
        
        # Absolute targets are strictly rejected
        if Path(rel_target_path).is_absolute():
            raise PatchApplicationError(f"Absolute paths are rejected: {rel_target_path}")

        # Basic relative/traversal safety checks
        normalized_parts = Path(rel_target_path).parts
        if ".." in normalized_parts:
            raise PatchApplicationError(f"Target path escapes workspace boundary (traversal rejected): {rel_target_path}")

        target_abs = (workspace_root / rel_target_path).resolve()
        
        # Path safety: resolved target must be within workspace_root
        try:
            target_abs.relative_to(workspace_root)
        except ValueError as exc:
            raise PatchApplicationError(f"Target path escapes workspace boundary: {rel_target_path}") from exc

        # Symlink checks for target path
        p = target_abs
        while p != workspace_root:
            if p.is_symlink():
                raise PatchApplicationError(f"Writes through symlinks are rejected: {p}")
            p = p.parent

        if is_creation:
            if target_abs.exists():
                raise PatchApplicationError(f"File already exists: {rel_target_path}")
            original_lines: list[str] = []
        else:
            if not target_abs.exists():
                raise PatchApplicationError(f"File not found for modification: {rel_target_path}")
            original_lines = target_abs.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)

        # Hunk matching with offset shifting
        modified_lines = list(original_lines)
        line_offset = 0
        additions = 0
        deletions = 0

        for idx, hunk in enumerate(pf.hunks):
            # Check base index adjustment
            expected_old_start = hunk.old_start - 1  # 0-indexed
            actual_start = expected_old_start + line_offset
            
            if actual_start < 0 or (actual_start > len(modified_lines) and not is_creation):
                raise PatchApplicationError(
                    f"File {rel_target_path} Hunk #{idx+1} matching failed: "
                    f"Expected start {actual_start} beyond file length {len(modified_lines)}"
                )

            # Match lines and apply diff
            source_cursor = actual_start
            new_lines_hunk: list[str] = []
            
            for hl in hunk.lines:
                if hl.startswith("\\ No newline at end of file"):
                    # Handle newline truncation on previous written line
                    if new_lines_hunk:
                        last_line = new_lines_hunk[-1]
                        if last_line.endswith("\n"):
                            new_lines_hunk[-1] = last_line.rstrip("\r\n")
                    continue
                
                prefix = hl[0]
                content = hl[1:]
                
                if prefix in (" ", "-"):
                    # Must match exact original content
                    if source_cursor >= len(modified_lines):
                        raise PatchApplicationError(
                            f"File {rel_target_path} Hunk #{idx+1} mismatch at line {source_cursor+1}: "
                            f"Expected '{content.strip()}', Found EOF"
                        )
                    current_line = modified_lines[source_cursor]
                    if current_line.rstrip("\r\n") != content.rstrip("\r\n"):
                        raise PatchApplicationError(
                            f"File {rel_target_path} Hunk #{idx+1} mismatch at line {source_cursor+1-line_offset}:\n"
                            f"  Expected: '{content.strip()}'\n"
                            f"  Found:    '{current_line.strip()}'"
                        )
                    
                    if prefix == " ":
                        new_lines_hunk.append(current_line)
                        source_cursor += 1
                    else: # '-'
                        source_cursor += 1
                        deletions += 1
                elif prefix == "+":
                    # additions do not consume a source line
                    new_lines_hunk.append(content)
                    additions += 1

            # Check that we fully processed the hunk's old block length
            expected_consumed = hunk.old_lines
            actual_consumed = source_cursor - actual_start
            # (For new creations, we can tolerate zero matching context lines)
            if not is_creation and actual_consumed != expected_consumed:
                raise PatchApplicationError(
                    f"File {rel_target_path} Hunk #{idx+1} mismatch: "
                    f"Consumed {actual_consumed} lines, expected {expected_consumed}"
                )

            # Perform in-memory block replacement
            modified_lines[actual_start : source_cursor] = new_lines_hunk
            
            # Shift line_offset for subsequent hunks
            line_offset += len(new_lines_hunk) - (source_cursor - actual_start)

        if is_deletion:
            # For deletes, check that the resulting content is empty
            non_empty = [l for l in modified_lines if l.strip()]
            if non_empty:
                raise PatchApplicationError(f"Deleted file {rel_target_path} must be empty after deletion")
            deleted_files_list.append(target_abs)
            changed_files_list.append(ChangedFile(path=rel_target_path, operation="deleted", additions=additions, deletions=deletions))
        elif is_creation:
            file_updates[target_abs] = modified_lines
            changed_files_list.append(ChangedFile(path=rel_target_path, operation="created", additions=additions, deletions=deletions))
        else:
            file_updates[target_abs] = modified_lines
            changed_files_list.append(ChangedFile(path=rel_target_path, operation="modified", additions=additions, deletions=deletions))

    if dry_run:
        return PatchApplyResult(changed_files=changed_files_list, patch_hash=effective_patch_hash)

    # 2. Validation passed! Commit disk writes atomically using temp-file replacement
    for path, lines_content in file_updates.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        dir_path = path.parent
        
        # Write to temp file in the same folder first
        with tempfile.NamedTemporaryFile("w", dir=dir_path, delete=False, encoding="utf-8") as temp_f:
            temp_f.write("".join(lines_content))
            temp_path = Path(temp_f.name)
        
        # Rename atomically to target file
        temp_path.replace(path)

    for path in deleted_files_list:
        if path.exists():
            path.unlink()

    return PatchApplyResult(changed_files=changed_files_list, patch_hash=effective_patch_hash)


def _hash_patch_files(patch_files: list[PatchFile]) -> str:
    payload = json.dumps([asdict(patch_file) for patch_file in patch_files], sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


