from __future__ import annotations
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from devflow.legacy.control_room.patch_proposal import (
    PatchProposalFile as PatchFile,
    PatchProposalHunk as Hunk,
    PatchProposalParseError,
    parse_patch_proposal,
    resolve_workspace_patch_target,
)

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

def parse_unified_diff(diff_text: str) -> list[PatchFile]:
    try:
        return parse_patch_proposal(diff_text, reject_unsupported_apply_metadata=True).files
    except PatchProposalParseError as exc:
        raise PatchParseError(str(exc)) from exc


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
        
        try:
            target_abs = resolve_workspace_patch_target(workspace_root, rel_target_path)
        except ValueError as exc:
            raise PatchApplicationError(str(exc)) from exc

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
            expected_old_start = 0 if is_creation and hunk.old_start == 0 else hunk.old_start - 1
            hint_start = expected_old_start + line_offset
            
            if hint_start < 0 or (hint_start > len(modified_lines) and not is_creation and not hunk.original_lines):
                raise PatchApplicationError(
                    f"File {rel_target_path} Hunk #{idx+1} matching failed: "
                    f"Expected start {hint_start} beyond file length {len(modified_lines)}"
                )

            actual_start = _resolve_hunk_start(
                modified_lines,
                hunk,
                hint_start,
                rel_target_path,
                idx + 1,
                is_creation,
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
            non_empty = [ln for ln in modified_lines if ln.strip()]
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


def _resolve_hunk_start(
    file_lines: list[str],
    hunk: Hunk,
    hint_start: int,
    rel_target_path: str,
    hunk_number: int,
    is_creation: bool,
) -> int:
    original = [line.rstrip("\r\n") for line in hunk.original_lines]
    if not original:
        if hint_start < 0 or (hint_start > len(file_lines) and not is_creation):
            raise PatchApplicationError(
                f"File {rel_target_path} Hunk #{hunk_number} matching failed: "
                f"Expected start {hint_start} beyond file length {len(file_lines)}"
            )
        return hint_start

    if 0 <= hint_start <= len(file_lines) and _original_matches_at(file_lines, original, hint_start):
        return hint_start

    max_start = len(file_lines) - len(original)
    if max_start < 0:
        raise PatchApplicationError(
            f"File {rel_target_path} Hunk #{hunk_number} mismatch: original context is longer than the file"
        )

    matches = [start for start in range(max_start + 1) if _original_matches_at(file_lines, original, start)]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise PatchApplicationError(
            _hunk_context_mismatch_message(file_lines, original, hint_start, rel_target_path, hunk_number)
        )
    raise PatchApplicationError(
        f"File {rel_target_path} Hunk #{hunk_number} mismatch: original context matched multiple locations"
    )


def _original_matches_at(file_lines: list[str], original: list[str], start: int) -> bool:
    if start < 0 or start + len(original) > len(file_lines):
        return False
    return [line.rstrip("\r\n") for line in file_lines[start : start + len(original)]] == original


def _hunk_context_mismatch_message(
    file_lines: list[str],
    original: list[str],
    hint_start: int,
    rel_target_path: str,
    hunk_number: int,
) -> str:
    expected = original[0].strip() if original else ""
    if not file_lines:
        line_number = 1
        found = "EOF"
    else:
        line_index = min(max(hint_start, 0), len(file_lines) - 1)
        line_number = line_index + 1
        found = file_lines[line_index].strip()
    return (
        f"File {rel_target_path} Hunk #{hunk_number} mismatch: original context did not match at line {line_number}:\n"
        f"  Expected: '{expected}'\n"
        f"  Found:    '{found}'"
    )
